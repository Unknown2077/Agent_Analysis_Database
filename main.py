from __future__ import annotations

import os
from collections import OrderedDict
from time import monotonic, perf_counter
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from core.agent_cache import get_or_create_cached_agent
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
    max_skills: int,
    max_prompt_chars: int,
) -> tuple[PromptBuildResult, tuple[SkillDefinition, ...]]:
    selected_skills = route_skills(query=user_input, available_skills=skill_catalog, max_skills=max_skills)
    selected_sections: list[tuple[SkillDefinition, str]] = []
    for skill in selected_skills:
        selected_sections.append((skill, read_skill_content(skills_dir, skill)))
    prompt_result = build_system_prompt(selected_sections, max_total_chars=max_prompt_chars)
    return prompt_result, tuple(selected_skills)


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


def create_database_agent(database_path: str, llm: ChatNVIDIA, system_prompt: str) -> object:
    db_file = Path(database_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Database file not found: {database_path}")

    def list_table() -> list[str]:
        """Return all table names from the configured SQLite database."""
        return list_tables(str(db_file))

    def table_info(table_name: str) -> list[dict[str, str | int | None]]:
        """Return column metadata for a table name."""
        return get_table_info(str(db_file), table_name)

    def execute_query(query: str) -> dict[str, list[str] | list[dict[str, str | int | float | None]]]:
        """Execute a read-only SELECT query and return columns and rows."""
        return execute_readonly_query(str(db_file), query)

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
    model_name = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct").strip()
    cache_ttl_seconds = _read_positive_int_env("AGENT_CACHE_TTL_SECONDS", 900)
    cache_max_size = _read_positive_int_env("AGENT_CACHE_MAX_SIZE", 8)
    max_skills = _read_positive_int_env("AGENT_MAX_SKILLS", 2)
    max_prompt_chars = _read_positive_int_env("AGENT_MAX_PROMPT_CHARS", 6000)
    available_tool_names = ("list_table", "table_info", "execute_query")
    llm = ChatNVIDIA(model=model_name, nvidia_api_key=nvidia_api_key, temperature=0.0)
    agent_cache: OrderedDict[tuple[str, ...], tuple[object, float]] = OrderedDict()

    print("Database analysis agent is ready. Type 'exit' to quit.")
    while True:
        user_input = input(">> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Bye.")
            break
        if not user_input:
            continue
        request_started_at = perf_counter()
        prompt_result, selected_skills = _build_dynamic_system_prompt(
            user_input=user_input,
            skills_dir=skills_dir,
            skill_catalog=skill_catalog,
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
            ),
            now_seconds=monotonic(),
            ttl_seconds=cache_ttl_seconds,
            max_cache_size=cache_max_size,
        )
        response = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
        output_text = _extract_text_output(response)
        append_event(
            event_path=event_log_path,
            event={
                "query": user_input,
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
                "required_tool_names": list(required_tool_names),
                "latency_ms": int((perf_counter() - request_started_at) * 1000),
            },
        )
        print(output_text)


if __name__ == "__main__":
    run_cli()
