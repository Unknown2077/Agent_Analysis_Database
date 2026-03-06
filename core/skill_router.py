from __future__ import annotations

from .skill_loader import SkillDefinition


def _score_skill(query_lower: str, skill: SkillDefinition) -> int:
    score = 0
    for keyword in skill.when_to_use:
        if keyword in query_lower:
            score += 1
    return score


def route_skills(query: str, available_skills: list[SkillDefinition], max_skills: int = 2) -> list[SkillDefinition]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        raise ValueError("query must not be empty.")
    if max_skills <= 0:
        raise ValueError("max_skills must be greater than 0.")
    if not available_skills:
        raise ValueError("available_skills must not be empty.")

    scored_skills: list[tuple[SkillDefinition, int]] = []
    for skill in available_skills:
        scored_skills.append((skill, _score_skill(normalized_query, skill)))

    matched_skills = [item for item in scored_skills if item[1] > 0]
    sorted_matches = sorted(matched_skills, key=lambda item: (item[1], item[0].priority), reverse=True)

    if sorted_matches:
        return [item[0] for item in sorted_matches[:max_skills]]

    sorted_by_priority = sorted(available_skills, key=lambda skill: skill.priority, reverse=True)
    return sorted_by_priority[:1]
