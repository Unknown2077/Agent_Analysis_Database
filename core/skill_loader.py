from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    file: str
    description: str
    when_to_use: tuple[str, ...]
    priority: int
    required_tools: tuple[str, ...]
    max_chars: int


def _validate_non_empty_string(value: str, field_name: str, skill_id: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"Skill '{skill_id}' has empty '{field_name}'.")
    return normalized_value


def _parse_skill(raw_skill: object) -> SkillDefinition:
    if not isinstance(raw_skill, dict):
        raise TypeError("Each skill in manifest must be an object.")

    raw_id = raw_skill.get("id")
    raw_file = raw_skill.get("file")
    raw_description = raw_skill.get("description")
    raw_keywords = raw_skill.get("when_to_use")
    raw_priority = raw_skill.get("priority")
    raw_tools = raw_skill.get("required_tools")
    raw_max_chars = raw_skill.get("max_chars")

    if not isinstance(raw_id, str):
        raise TypeError("Skill field 'id' must be a string.")
    skill_id = _validate_non_empty_string(raw_id, "id", "<unknown>")

    if not isinstance(raw_file, str):
        raise TypeError(f"Skill '{skill_id}' field 'file' must be a string.")
    file_name = _validate_non_empty_string(raw_file, "file", skill_id)

    if not isinstance(raw_description, str):
        raise TypeError(f"Skill '{skill_id}' field 'description' must be a string.")
    description = _validate_non_empty_string(raw_description, "description", skill_id)

    if not isinstance(raw_keywords, list) or not raw_keywords:
        raise TypeError(f"Skill '{skill_id}' field 'when_to_use' must be a non-empty list of strings.")
    keywords: list[str] = []
    for raw_keyword in raw_keywords:
        if not isinstance(raw_keyword, str):
            raise TypeError(f"Skill '{skill_id}' has a non-string keyword in 'when_to_use'.")
        keywords.append(_validate_non_empty_string(raw_keyword, "when_to_use keyword", skill_id).lower())

    if not isinstance(raw_priority, int):
        raise TypeError(f"Skill '{skill_id}' field 'priority' must be an integer.")

    if not isinstance(raw_tools, list):
        raise TypeError(f"Skill '{skill_id}' field 'required_tools' must be a list of strings.")
    required_tools: list[str] = []
    for raw_tool_name in raw_tools:
        if not isinstance(raw_tool_name, str):
            raise TypeError(f"Skill '{skill_id}' has a non-string tool in 'required_tools'.")
        required_tools.append(_validate_non_empty_string(raw_tool_name, "required_tools tool", skill_id))

    if not isinstance(raw_max_chars, int) or raw_max_chars <= 0:
        raise TypeError(f"Skill '{skill_id}' field 'max_chars' must be a positive integer.")

    return SkillDefinition(
        id=skill_id,
        file=file_name,
        description=description,
        when_to_use=tuple(keywords),
        priority=raw_priority,
        required_tools=tuple(required_tools),
        max_chars=raw_max_chars,
    )


def load_skill_manifest(skills_dir: Path) -> list[SkillDefinition]:
    manifest_path = skills_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Skill manifest not found: {manifest_path}")

    manifest_text = manifest_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(manifest_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in skill manifest: {manifest_path}") from error

    if not isinstance(payload, dict):
        raise TypeError("Skill manifest root must be an object.")

    raw_skills = payload.get("skills")
    if not isinstance(raw_skills, list) or not raw_skills:
        raise ValueError("Skill manifest must contain a non-empty 'skills' list.")

    skills = [_parse_skill(raw_skill) for raw_skill in raw_skills]
    seen_ids: set[str] = set()
    for skill in skills:
        if skill.id in seen_ids:
            raise ValueError(f"Duplicate skill id in manifest: {skill.id}")
        seen_ids.add(skill.id)
        if not (skills_dir / skill.file).exists():
            raise FileNotFoundError(f"Skill file not found for '{skill.id}': {skills_dir / skill.file}")

    return skills


def read_skill_content(skills_dir: Path, skill: SkillDefinition) -> str:
    skill_file_path = skills_dir / skill.file
    skill_text = skill_file_path.read_text(encoding="utf-8").strip()
    if not skill_text:
        raise ValueError(f"Skill file is empty for '{skill.id}': {skill_file_path}")
    return skill_text[: skill.max_chars].strip()
