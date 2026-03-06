from __future__ import annotations

from dataclasses import dataclass

from .skill_loader import SkillDefinition

BASE_SYSTEM_PROMPT = """\
## Role
You are a database analysis agent. Use tools only when needed. Keep answers concise.
- Read-only SQL only.
- Never invent table or column names.

## Tools
- `list_table` — returns all table names. Call first to discover available tables.
- `table_info(table_name)` — returns column metadata. Use to verify columns before querying.
- `execute_query(query)` — runs a read-only SELECT query. Always the final step to get data.

## Exploration Strategy
For every data request, follow this sequence:
1. Call `list_table` to see available tables.
2. Call `table_info` on relevant tables to confirm columns and types.
3. Build and run a validated SELECT query via `execute_query`.
Skip steps 1-2 only if the schema was already confirmed in this conversation.

## Output Format
- For data requests, MUST call `execute_query` and return actual result rows.
- Show results first, then optionally include the SQL used.
- Do not stop at schema explanation or SQL draft only.

## Examples
User: "How many albums are there?"
Steps: execute_query("SELECT COUNT(*) AS album_count FROM Album")
Answer: There are 347 albums. | SQL: SELECT COUNT(*) AS album_count FROM Album

User: "Top 3 artists by number of tracks"
Steps: list_table -> table_info(Artist, Album, Track) -> execute_query(...)
Answer: 1. Iron Maiden (213) 2. U2 (135) 3. Led Zeppelin (114) | SQL: SELECT ..."""


@dataclass(frozen=True)
class PromptBuildResult:
    prompt: str
    included_skill_ids: tuple[str, ...]
    truncated_skill_ids: tuple[str, ...]
    dropped_skill_ids: tuple[str, ...]


def build_system_prompt(
    selected_skill_sections: list[tuple[SkillDefinition, str]],
    max_total_chars: int = 6000,
) -> PromptBuildResult:
    if max_total_chars <= 0:
        raise ValueError("max_total_chars must be greater than 0.")
    if len(BASE_SYSTEM_PROMPT) > max_total_chars:
        raise ValueError(
            f"Base prompt size exceeded budget ({len(BASE_SYSTEM_PROMPT)} > {max_total_chars}). "
            "Increase max_total_chars."
        )

    sections: list[str] = [BASE_SYSTEM_PROMPT.strip()]
    included_skill_ids: list[str] = []
    truncated_skill_ids: list[str] = []
    dropped_skill_ids: list[str] = []

    current_prompt = sections[0]
    for skill, content in selected_skill_sections:
        cleaned_content = content.strip()
        if not cleaned_content:
            raise ValueError(f"Selected skill '{skill.id}' has empty content.")

        skill_header = f"# Skill: {skill.id}\n"
        full_section = f"{skill_header}{cleaned_content}"
        full_candidate_prompt = f"{current_prompt}\n\n{full_section}"
        if len(full_candidate_prompt) <= max_total_chars:
            sections.append(full_section)
            included_skill_ids.append(skill.id)
            current_prompt = full_candidate_prompt
            continue

        remaining_chars = max_total_chars - len(current_prompt) - 2 - len(skill_header)
        if remaining_chars <= 0:
            dropped_skill_ids.append(skill.id)
            continue

        truncated_content = cleaned_content[:remaining_chars].strip()
        if not truncated_content:
            dropped_skill_ids.append(skill.id)
            continue

        truncated_section = f"{skill_header}{truncated_content}"
        truncated_candidate_prompt = f"{current_prompt}\n\n{truncated_section}"
        if len(truncated_candidate_prompt) <= max_total_chars:
            sections.append(truncated_section)
            included_skill_ids.append(skill.id)
            truncated_skill_ids.append(skill.id)
            current_prompt = truncated_candidate_prompt
        else:
            dropped_skill_ids.append(skill.id)

    prompt = "\n\n".join(sections).strip()
    return PromptBuildResult(
        prompt=prompt,
        included_skill_ids=tuple(included_skill_ids),
        truncated_skill_ids=tuple(truncated_skill_ids),
        dropped_skill_ids=tuple(dropped_skill_ids),
    )
