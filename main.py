from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from tools.execute_query import execute_readonly_query
from tools.list_table import list_tables
from tools.table_info import get_table_info


def _read_skill(skill_file_path: Path) -> str:
    if not skill_file_path.exists():
        raise FileNotFoundError(f"Skill file not found: {skill_file_path}")
    return skill_file_path.read_text(encoding="utf-8").strip()


def _build_system_prompt(skills_dir: Path) -> str:
    schema_analyzer_skill = _read_skill(skills_dir / "schema_analyzer.md")
    query_builder_skill = _read_skill(skills_dir / "query_builder.md")

    return (
        "You are a database analysis agent.\n"
        "Use tools only when needed and keep answers concise.\n"
        "Rules:\n"
        "- Read-only SQL only.\n"
        "- Never invent table or column names.\n"
        "- Validate schema using tools before complex queries.\n\n"
        f"{schema_analyzer_skill}\n\n{query_builder_skill}"
    )


def _require_env(variable_name: str) -> str:
    value = os.getenv(variable_name, "").strip()
    if not value:
        raise EnvironmentError(
            f"Missing environment variable '{variable_name}'. "
            f"Set it in shell or .env before running this program."
        )
    return value


def _extract_text_output(result: dict[str, Any]) -> str:
    messages = result.get("messages")
    if not isinstance(messages, list):
        raise RuntimeError("Agent response does not contain a valid 'messages' list.")

    last_ai_message: Any = None
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


def create_database_agent(database_path: str) -> Any:
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

    skills_dir = Path(__file__).parent / "skills"
    system_prompt = _build_system_prompt(skills_dir)

    nvidia_api_key = _require_env("NVIDIA_API_KEY")
    model_name = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct").strip()

    llm = ChatNVIDIA(model=model_name, nvidia_api_key=nvidia_api_key, temperature=0.0)
    tools = [list_table, table_info, execute_query]
    return create_agent(model=llm, tools=tools, system_prompt=system_prompt)


def run_cli() -> None:
    load_dotenv()
    default_database_path = str((Path(__file__).parent / "chinook.db").resolve())
    database_path = os.getenv("DB_PATH", default_database_path).strip()
    agent = create_database_agent(database_path)

    print("Database analysis agent is ready. Type 'exit' to quit.")
    while True:
        user_input = input(">> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Bye.")
            break
        if not user_input:
            continue
        response = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
        output_text = _extract_text_output(response)
        print(output_text)


if __name__ == "__main__":
    run_cli()
