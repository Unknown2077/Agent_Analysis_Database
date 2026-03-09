from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from time import monotonic, perf_counter
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from core.agent_cache import get_or_create_cached_agent
from core.memory_utils import (
    MemoryCompactionError,
    build_agent_messages as _build_agent_messages,
    build_memory_ack as _build_memory_ack,
    clear_tool_results as _clear_tool_results,
    compact_history_with_llm as _compact_history_with_llm,
    load_preferences as _load_preferences,
    parse_pref_command as _parse_pref_command,
    store_preference as _store_preference,
)
from core.observability import append_event
from core.prompt_builder import PromptBuildResult, build_system_prompt
from core.skill_loader import SkillDefinition, load_skill_manifest, read_skill_content
from core.skill_router import route_skills
from tools.execute_query import execute_readonly_query
from tools.list_table import list_tables
from tools.table_info import get_table_info


def _require_env(variable_name: str) -> str:
    value = os.getenv(variable_name, "").strip()
    if not value:
        raise EnvironmentError(
            f"Missing environment variable '{variable_name}'. "
            f"Set it in shell or .env before running this program."
        )
    return value


def _build_dynamic_system_prompt(
    user_input: str,
    skills_dir: Path,
    skill_catalog: list[SkillDefinition],
    llm: ChatNVIDIA,
    max_skills: int,
    max_prompt_chars: int,
) -> tuple[PromptBuildResult, tuple[SkillDefinition, ...], int]:
    router_start = perf_counter()
    selected_skills = route_skills(
        query=user_input,
        available_skills=skill_catalog,
        llm=llm,
        max_skills=max_skills,
    )
    router_latency_ms = int((perf_counter() - router_start) * 1000)
    selected_sections: list[tuple[SkillDefinition, str]] = []
    for skill in selected_skills:
        selected_sections.append((skill, read_skill_content(skills_dir, skill)))
    prompt_result = build_system_prompt(selected_sections, max_total_chars=max_prompt_chars)
    return prompt_result, tuple(selected_skills), router_latency_ms


def _read_positive_int_env(variable_name: str, default_value: int) -> int:
    raw_value = os.getenv(variable_name, "").strip()
    if not raw_value:
        return default_value
    try:
        parsed_value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"Environment variable '{variable_name}' must be an integer.") from error
    if parsed_value <= 0:
        raise ValueError(f"Environment variable '{variable_name}' must be greater than 0.")
    return parsed_value


def _extract_text_output(result: dict[str, object]) -> str:
    messages = result.get("messages")
    if not isinstance(messages, list):
        raise RuntimeError("Agent response does not contain a valid 'messages' list.")

    last_ai_message: object | None = None
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai":
            last_ai_message = message
            break

    if last_ai_message is None:
        raise RuntimeError("Agent response does not contain an AI message.")

    content = getattr(last_ai_message, "content", "")
    if isinstance(content, str):
        output_text = content.strip()
    elif isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                part_text = part.get("text", "")
                if isinstance(part_text, str) and part_text.strip():
                    text_parts.append(part_text.strip())
        output_text = "\n".join(text_parts).strip()
    else:
        output_text = ""

    if not output_text:
        raise RuntimeError("Agent returned empty output.")
    return output_text


def _extract_token_usage(result: dict[str, object]) -> tuple[int, int, int]:
    messages = result.get("messages")
    if not isinstance(messages, list):
        raise RuntimeError("Agent response does not contain a valid 'messages' list for token usage.")

    last_ai_message: object | None = None
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai":
            last_ai_message = message
            break

    if last_ai_message is None:
        raise RuntimeError("Agent response does not contain an AI message for token usage.")

    usage_metadata = getattr(last_ai_message, "usage_metadata", None)
    if not isinstance(usage_metadata, dict):
        raise RuntimeError("AI message does not include usage_metadata for token usage logging.")

    input_tokens = usage_metadata.get("input_tokens")
    output_tokens = usage_metadata.get("output_tokens")
    total_tokens = usage_metadata.get("total_tokens")
    if not isinstance(input_tokens, int) or input_tokens < 0:
        raise RuntimeError("Invalid input_tokens in usage_metadata.")
    if not isinstance(output_tokens, int) or output_tokens < 0:
        raise RuntimeError("Invalid output_tokens in usage_metadata.")
    if not isinstance(total_tokens, int) or total_tokens < 0:
        raise RuntimeError("Invalid total_tokens in usage_metadata.")

    return input_tokens, output_tokens, total_tokens


def _validate_required_tools(
    selected_skills: tuple[SkillDefinition, ...],
    available_tool_names: tuple[str, ...],
) -> tuple[str, ...]:
    available_tools = set(available_tool_names)
    required_tools: list[str] = []
    for skill in selected_skills:
        for tool_name in skill.required_tools:
            if tool_name not in required_tools:
                required_tools.append(tool_name)
            if tool_name not in available_tools:
                raise RuntimeError(
                    f"Skill '{skill.id}' requires tool '{tool_name}', but it is not registered in the agent."
                )
    return tuple(required_tools)


def create_database_agent(
    database_path: str,
    llm: ChatNVIDIA,
    system_prompt: str,
    max_rows: int = 50,
    max_cell_chars: int = 200,
) -> object:
    db_file = Path(database_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Database file not found: {database_path}")

    def list_table() -> list[str]:
        """Return all table names from the configured SQLite database."""
        return list_tables(str(db_file))

    def table_info(table_name: str) -> list[dict[str, str | int | None]]:
        """Return column metadata for a table name."""
        return get_table_info(str(db_file), table_name)

    def execute_query(query: str) -> object:
        """Execute a read-only SELECT query and return columns and rows."""
        return execute_readonly_query(
            str(db_file), query, max_rows=max_rows, max_cell_chars=max_cell_chars
        )

    tools = [list_table, table_info, execute_query]
    return create_agent(model=llm, tools=tools, system_prompt=system_prompt)


def run_cli() -> None:
    load_dotenv()
    default_database_path = str((Path(__file__).parent / "chinook.db").resolve())
    database_path = os.getenv("DB_PATH", default_database_path).strip()
    skills_dir = Path(__file__).parent / "skills"
    skill_catalog = load_skill_manifest(skills_dir)
    event_log_path = Path(__file__).parent / "logs" / "agent_events.jsonl"

    nvidia_api_key = _require_env("NVIDIA_API_KEY")
    model_name = os.getenv("NVIDIA_MODEL", "qwen/qwen3-next-80b-a3b-instruct").strip()
    cache_ttl_seconds = _read_positive_int_env("AGENT_CACHE_TTL_SECONDS", 900)
    cache_max_size = _read_positive_int_env("AGENT_CACHE_MAX_SIZE", 8)
    max_skills = _read_positive_int_env("AGENT_MAX_SKILLS", 2)
    max_prompt_chars = _read_positive_int_env("AGENT_MAX_PROMPT_CHARS", 6000)
    memory_turns = _read_positive_int_env("AGENT_MEMORY_TURNS", 3)
    memory_summary_max_chars = _read_positive_int_env("AGENT_MEMORY_SUMMARY_MAX_CHARS", 2000)
    tool_max_rows = _read_positive_int_env("AGENT_TOOL_MAX_ROWS", 50)
    tool_max_cell_chars = _read_positive_int_env("AGENT_TOOL_MAX_CELL_CHARS", 200)
    context_notes_max_items = _read_positive_int_env("AGENT_CONTEXT_NOTES_MAX_ITEMS", 5)
    context_notes_max_chars = _read_positive_int_env("AGENT_CONTEXT_NOTES_MAX_CHARS", 800)
    available_tool_names = ("list_table", "table_info", "execute_query")
    llm = ChatNVIDIA(model=model_name, nvidia_api_key=nvidia_api_key, temperature=0.0)
    agent_cache: OrderedDict[tuple[str, ...], tuple[object, float]] = OrderedDict()
    conversation_history: list[dict[str, str]] = []
    history_summary = ""
    preferences_path = Path(__file__).parent / "preferences.json"
    user_preferences: list[str] = _load_preferences(preferences_path)

    print("Database analysis agent is ready. Type 'exit' to quit.")
    while True:
        user_input = input(">> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Bye.")
            break
        if not user_input:
            continue
        request_id = str(uuid.uuid4())
        request_started_at = perf_counter()
        try:
            pref_payload = _parse_pref_command(user_input)
        except ValueError as err:
            print(str(err))
            continue
        if pref_payload is not None:
            _store_preference(user_preferences, pref_payload, preferences_path=preferences_path)
            output_text = _build_memory_ack(pref_payload)
            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": output_text})
            append_event(
                event_path=event_log_path,
                event={
                    "request_id": request_id,
                    "query": user_input,
                    "event_type": "memory_instruction",
                    "selected_skill_ids": [],
                    "included_skill_ids": [],
                    "truncated_skill_ids": [],
                    "dropped_skill_ids": [],
                    "prompt_chars": 0,
                    "cache_key": ["__memory_only__"],
                    "cache_hit": False,
                    "cache_size": len(agent_cache),
                    "cache_ttl_seconds": cache_ttl_seconds,
                    "cache_max_size": cache_max_size,
                    "cache_expired_evictions": 0,
                    "cache_lru_evictions": 0,
                    "max_skills": max_skills,
                    "max_prompt_chars": max_prompt_chars,
                    "memory_turns": memory_turns,
                    "history_summary_chars": len(history_summary),
                    "history_messages_sent": 0,
                    "required_tool_names": [],
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "compaction_attempted": False,
                    "compaction_status": "skipped",
                    "compaction_provider": "none",
                    "compaction_input_messages": 0,
                    "compaction_input_chars": 0,
                    "compaction_output_chars": 0,
                    "compaction_latency_ms": 0,
                    "history_messages_compacted": 0,
                    "history_messages_kept": len(conversation_history),
                    "latency_ms": int((perf_counter() - request_started_at) * 1000),
                },
            )
            print(output_text)
            continue
        try:
            prompt_result, selected_skills, router_latency_ms = _build_dynamic_system_prompt(
                user_input=user_input,
                skills_dir=skills_dir,
                skill_catalog=skill_catalog,
                llm=llm,
                max_skills=max_skills,
                max_prompt_chars=max_prompt_chars,
            )
            selected_skill_ids = tuple(skill.id for skill in selected_skills)
            required_tool_names = _validate_required_tools(selected_skills, available_tool_names)
            cache_key = prompt_result.included_skill_ids or ("__base_prompt__",)
            agent, cache_hit, expired_evictions, lru_evictions = get_or_create_cached_agent(
                agent_cache=agent_cache,
                cache_key=cache_key,
                create_agent=lambda: create_database_agent(
                    database_path=database_path,
                    llm=llm,
                    system_prompt=prompt_result.prompt,
                    max_rows=tool_max_rows,
                    max_cell_chars=tool_max_cell_chars,
                ),
                now_seconds=monotonic(),
                ttl_seconds=cache_ttl_seconds,
                max_cache_size=cache_max_size,
            )
            recent_window_size = memory_turns * 2
            history_to_keep = conversation_history[-recent_window_size:]
            history_to_compact = conversation_history[:-recent_window_size]
            compaction_attempted = bool(history_to_compact)
            compaction_status = "skipped"
            compaction_provider = "none"
            compaction_input_messages = 0
            compaction_input_chars = 0
            compaction_output_chars = 0
            compaction_latency_ms = 0
            if history_to_compact:
                cleared_history = _clear_tool_results(history_to_compact)
                compaction_input_messages = len(history_to_compact)
                compaction_input_chars = sum(
                    len(m.get("content", "")) for m in cleared_history
                )
                compaction_start = perf_counter()
                history_summary = _compact_history_with_llm(
                    llm=llm,
                    existing_summary=history_summary,
                    history_to_compact=cleared_history,
                    max_summary_chars=memory_summary_max_chars,
                )
                compaction_latency_ms = int((perf_counter() - compaction_start) * 1000)
                compaction_output_chars = len(history_summary)
                compaction_status = "success"
                compaction_provider = "llm"
                conversation_history = history_to_keep

            request_messages = _build_agent_messages(
                user_input=user_input,
                history_summary=history_summary,
                recent_history=conversation_history,
                preferences=user_preferences,
                context_notes_max_items=context_notes_max_items,
                context_notes_max_chars=context_notes_max_chars,
            )
            response = agent.invoke({"messages": request_messages})
            output_text = _extract_text_output(response)
            prompt_tokens, completion_tokens, total_tokens = _extract_token_usage(response)
            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": output_text})
            append_event(
                event_path=event_log_path,
                event={
                    "request_id": request_id,
                    "query": user_input,
                    "event_type": "analysis_success",
                    "router_latency_ms": router_latency_ms,
                    "router_selected_skill_ids": list(selected_skill_ids),
                    "selected_skill_ids": list(selected_skill_ids),
                    "included_skill_ids": list(prompt_result.included_skill_ids),
                    "truncated_skill_ids": list(prompt_result.truncated_skill_ids),
                    "dropped_skill_ids": list(prompt_result.dropped_skill_ids),
                    "prompt_chars": len(prompt_result.prompt),
                    "cache_key": list(cache_key),
                    "cache_hit": cache_hit,
                    "cache_size": len(agent_cache),
                    "cache_ttl_seconds": cache_ttl_seconds,
                    "cache_max_size": cache_max_size,
                    "cache_expired_evictions": expired_evictions,
                    "cache_lru_evictions": lru_evictions,
                    "max_skills": max_skills,
                    "max_prompt_chars": max_prompt_chars,
                    "memory_turns": memory_turns,
                    "history_summary_chars": len(history_summary),
                    "history_messages_sent": len(request_messages),
                    "required_tool_names": list(required_tool_names),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "compaction_attempted": compaction_attempted,
                    "compaction_status": compaction_status,
                    "compaction_provider": compaction_provider,
                    "compaction_input_messages": compaction_input_messages,
                    "compaction_input_chars": compaction_input_chars,
                    "compaction_output_chars": compaction_output_chars,
                    "compaction_latency_ms": compaction_latency_ms,
                    "history_messages_compacted": compaction_input_messages,
                    "history_messages_kept": len(history_to_keep),
                    "latency_ms": int((perf_counter() - request_started_at) * 1000),
                },
            )
            print(output_text)
        except MemoryCompactionError as err:
            error_msg = str(err)
            print(f"Error: {error_msg}")
            print("Use /pref add <text> for preferences. Try rephrasing your query.")
            append_event(
                event_path=event_log_path,
                event={
                    "request_id": request_id,
                    "query": user_input,
                    "event_type": "runtime_error",
                    "error_message": error_msg,
                    "error_stage": "memory_compaction",
                    "latency_ms": int((perf_counter() - request_started_at) * 1000),
                },
            )
        except RuntimeError as err:
            error_msg = str(err)
            print(f"Error: {error_msg}")
            print("Use /pref add <text> for preferences. Try rephrasing your query.")
            append_event(
                event_path=event_log_path,
                event={
                    "request_id": request_id,
                    "query": user_input,
                    "event_type": "runtime_error",
                    "error_message": error_msg,
                    "error_stage": "unknown",
                    "latency_ms": int((perf_counter() - request_started_at) * 1000),
                },
            )


if __name__ == "__main__":
    run_cli()
