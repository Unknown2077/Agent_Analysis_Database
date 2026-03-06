from __future__ import annotations


def clip_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0.")
    text = value.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3].rstrip()}..."


def compact_history(
    existing_summary: str,
    history_to_compact: list[dict[str, str]],
    max_summary_chars: int,
) -> str:
    if max_summary_chars <= 0:
        raise ValueError("max_summary_chars must be greater than 0.")

    summary_lines: list[str] = []
    if existing_summary.strip():
        summary_lines.append(existing_summary.strip())

    for message in history_to_compact:
        role = message["role"].upper()
        content = clip_text(message["content"], 180)
        if content:
            summary_lines.append(f"- {role}: {content}")

    merged_summary = "\n".join(summary_lines).strip()
    return clip_text(merged_summary, max_summary_chars)


def build_agent_messages(
    user_input: str,
    history_summary: str,
    recent_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
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
        "remember this",
        "remember that",
        "keep in mind",
        "note this",
        "note that",
        "from now on",
    )
    return normalized.startswith(memory_starts)


def build_memory_ack(user_input: str) -> str:
    remembered_text = clip_text(user_input, 240)
    return (
        "Noted. I will keep this preference for the current session:\n"
        f"- {remembered_text}\n"
        "I will not run any query until you ask for analysis."
    )
