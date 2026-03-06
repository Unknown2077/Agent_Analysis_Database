from __future__ import annotations

import json
from pathlib import Path

MAX_PREFERENCES = 10
MAX_PREFERENCE_CHARS = 200
TOOL_RESULT_PLACEHOLDER = "[tool result cleared]"
ASSISTANT_CONTENT_MAX_CHARS = 500

COMPACTION_PROMPT = """\
Summarize the conversation below into concise bullet points.
Preserve: questions asked, answers given, SQL patterns, table names, unresolved issues.
Discard: raw query result rows, greetings, repeated information.
Stay under {max_chars} characters.

{existing_summary_block}\
Conversation:
{conversation_block}

Bullet-point summary:"""


def clip_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0.")
    text = value.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3].rstrip()}..."


def clear_tool_results(
    history: list[dict[str, str]],
    max_content_chars: int = ASSISTANT_CONTENT_MAX_CHARS,
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for message in history:
        role = message.get("role", "")
        content = message.get("content", "")
        if role == "tool":
            cleaned.append({"role": "tool", "content": TOOL_RESULT_PLACEHOLDER})
            continue
        if role == "assistant" and len(content) > max_content_chars:
            cleaned.append({"role": role, "content": clip_text(content, max_content_chars)})
            continue
        cleaned.append(message)
    return cleaned


def compact_history(
    existing_summary: str,
    history_to_compact: list[dict[str, str]],
    max_summary_chars: int,
) -> str:
    if max_summary_chars <= 0:
        raise ValueError("max_summary_chars must be greater than 0.")

    new_lines: list[str] = []
    for message in history_to_compact:
        role = message["role"].upper()
        content = clip_text(message["content"], 180)
        if content:
            new_lines.append(f"- {role}: {content}")

    summary_lines: list[str] = new_lines
    if existing_summary.strip():
        summary_lines.append(existing_summary.strip())

    merged_summary = "\n".join(summary_lines).strip()
    return clip_text(merged_summary, max_summary_chars)


def compact_history_with_llm(
    llm: object,
    existing_summary: str,
    history_to_compact: list[dict[str, str]],
    max_summary_chars: int,
) -> str:
    if max_summary_chars <= 0:
        raise ValueError("max_summary_chars must be greater than 0.")
    if not history_to_compact:
        return existing_summary.strip()

    existing_block = ""
    if existing_summary.strip():
        existing_block = f"Previous summary:\n{existing_summary.strip()}\n\n"

    conversation_lines: list[str] = []
    for message in history_to_compact:
        role = message["role"].upper()
        content = clip_text(message["content"], 300)
        if content:
            conversation_lines.append(f"{role}: {content}")

    prompt = COMPACTION_PROMPT.format(
        max_chars=max_summary_chars,
        existing_summary_block=existing_block,
        conversation_block="\n".join(conversation_lines),
    )

    try:
        response = llm.invoke(prompt)  # type: ignore[union-attr]
        summary_text = ""
        if hasattr(response, "content"):
            summary_text = response.content  # type: ignore[union-attr]
        elif isinstance(response, str):
            summary_text = response
        summary_text = summary_text.strip()
        if not summary_text:
            return compact_history(existing_summary, history_to_compact, max_summary_chars)
        return clip_text(summary_text, max_summary_chars)
    except Exception:
        return compact_history(existing_summary, history_to_compact, max_summary_chars)


def build_agent_messages(
    user_input: str,
    history_summary: str,
    recent_history: list[dict[str, str]],
    preferences: list[str] | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    pref_block = build_preference_context(preferences or [])
    if pref_block:
        messages.append({"role": "system", "content": pref_block})
    if history_summary.strip():
        messages.append(
            {
                "role": "system",
                "content": "Conversation summary from previous turns:\n" + history_summary.strip(),
            }
        )
    messages.extend(recent_history)
    messages.append({"role": "user", "content": user_input})
    return messages


def is_memory_instruction(user_input: str) -> bool:
    normalized = user_input.strip().lower()
    memory_starts = (
        "remember",
        "keep in mind",
        "note this",
        "note that",
        "from now on",
        "always ",
        "never ",
        "i prefer",
        "i want you to",
    )
    return normalized.startswith(memory_starts)


def build_memory_ack(user_input: str) -> str:
    remembered_text = clip_text(user_input, 240)
    return (
        "Noted. I will keep this preference:\n"
        f"- {remembered_text}\n"
        "I will not run any query until you ask for analysis."
    )


def load_preferences(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise TypeError(f"Preferences file must contain a JSON array: {path}")
    return [str(item) for item in data]


def save_preferences(path: Path, preferences: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(preferences, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def store_preference(
    preferences: list[str],
    user_input: str,
    preferences_path: Path | None = None,
) -> None:
    cleaned = clip_text(user_input, MAX_PREFERENCE_CHARS)
    if cleaned and cleaned not in preferences:
        if len(preferences) >= MAX_PREFERENCES:
            preferences.pop(0)
        preferences.append(cleaned)
    if preferences_path is not None:
        save_preferences(preferences_path, preferences)


def build_preference_context(preferences: list[str]) -> str:
    if not preferences:
        return ""
    lines = ["Active user preferences:"] + [f"- {p}" for p in preferences]
    return "\n".join(lines)
