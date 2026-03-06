# Agent Analysis DB

Minimal database analysis agent using LangChain + NVIDIA NIM over SQLite (`chinook.db`).

## Project Structure

```text
agent-analysis-db/
├── main.py
├── chinook.db
├── requirements.txt
├── .env.example
├── core/
│   ├── agent_cache.py
│   ├── observability.py
│   ├── prompt_builder.py
│   ├── skill_loader.py
│   └── skill_router.py
├── tests/
│   ├── test_agent_cache.py
│   └── test_skill_router.py
├── skills/
│   ├── manifest.json
│   ├── data_quality_checker.md
│   ├── query_builder.md
│   ├── schema_analyzer.md
│   ├── segment_analyzer.md
│   └── time_series_analyst.md
└── tools/
    ├── execute_query.py
    ├── list_table.py
    └── table_info.py
```

## Prerequisites

- Python 3.12 or 3.13 recommended
- NVIDIA NIM API key

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Environment Variables

1. Copy example file:

```bash
cp .env.example .env
```

2. Edit `.env`:

```env
NVIDIA_API_KEY=your_real_nvidia_api_key
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
DB_PATH=/absolute/path/to/chinook.db
AGENT_CACHE_TTL_SECONDS=900
AGENT_CACHE_MAX_SIZE=8
AGENT_MAX_SKILLS=2
AGENT_MAX_PROMPT_CHARS=6000
AGENT_MEMORY_TURNS=3
AGENT_MEMORY_SUMMARY_MAX_CHARS=2000
```

If `DB_PATH` is not set, `main.py` defaults to local `chinook.db` in this project.
If `AGENT_CACHE_TTL_SECONDS` or `AGENT_CACHE_MAX_SIZE` is not set, defaults are `900` and `8`.
If `AGENT_MAX_SKILLS` or `AGENT_MAX_PROMPT_CHARS` is not set, defaults are `2` and `6000`.
If `AGENT_MEMORY_TURNS` or `AGENT_MEMORY_SUMMARY_MAX_CHARS` is not set, defaults are `3` and `2000`.

## Run

```bash
python main.py
```

## Runtime Flow

```text
Start
  |
  v
Receive user question
  |
  v
Route relevant skills
  |
  v
Build prompt (budget-aware)
  |
  v
Get cached agent by skill set (TTL + LRU)
  |
  v
Attach memory (recent turns + compact summary)
  |
  v
Run tools and return answer
  |
  v
Write telemetry log (skills, cache, latency, tokens)
```

Type questions in plain English, for example:

- `List all tables in this database.`
- `Show table_info for the Customer table.`
- `Top 5 genres by total sales revenue.`

Exit with:

- `exit`
- `quit`

## Notes

- `execute_query` only allows `SELECT` queries.
- This project targets latest LangChain (`langchain` package in `requirements.txt`).
- Python 3.14 may show compatibility warnings in some transitive dependencies.
- Skills are selected per user request using `skills/manifest.json` + `core/skill_router.py`.
- System prompt is composed dynamically by `core/prompt_builder.py` with selected skills only and context budget handling.
- Selected skills now validate `required_tools` from `skills/manifest.json` against registered agent tools.
- Agent instances are cached by active skill combination with TTL + LRU eviction.
- Conversation context keeps recent turns and compacts older turns into a bounded summary.
- Request telemetry is written to `logs/agent_events.jsonl` via `core/observability.py`.
- Skill files:
- `skills/data_quality_checker.md`
  - `skills/schema_analyzer.md`
  - `skills/query_builder.md`
- `skills/segment_analyzer.md`
- `skills/time_series_analyst.md`