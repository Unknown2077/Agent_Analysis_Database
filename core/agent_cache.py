from __future__ import annotations

from collections import OrderedDict
from typing import Callable


def get_or_create_cached_agent(
    agent_cache: OrderedDict[tuple[str, ...], tuple[object, float]],
    cache_key: tuple[str, ...],
    create_agent: Callable[[], object],
    now_seconds: float,
    ttl_seconds: int,
    max_cache_size: int,
) -> tuple[object, bool, int, int]:
    evicted_expired_entries = 0
    evicted_lru_entries = 0

    expired_keys: list[tuple[str, ...]] = []
    for existing_key, (_, last_access_seconds) in agent_cache.items():
        if now_seconds - last_access_seconds > ttl_seconds:
            expired_keys.append(existing_key)
    for expired_key in expired_keys:
        del agent_cache[expired_key]
        evicted_expired_entries += 1

    cached_entry = agent_cache.get(cache_key)
    if cached_entry is not None:
        cached_agent, _ = cached_entry
        agent_cache[cache_key] = (cached_agent, now_seconds)
        agent_cache.move_to_end(cache_key)
        return cached_agent, True, evicted_expired_entries, evicted_lru_entries

    created_agent = create_agent()
    agent_cache[cache_key] = (created_agent, now_seconds)
    agent_cache.move_to_end(cache_key)

    while len(agent_cache) > max_cache_size:
        agent_cache.popitem(last=False)
        evicted_lru_entries += 1

    return created_agent, False, evicted_expired_entries, evicted_lru_entries
