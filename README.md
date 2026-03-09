# Agent Analysis DB

Minimal database analysis agent using LangChain + NVIDIA NIM over SQLite (`chinook.db`).

## Project Structure

```text
agent-analysis-db/
├── main.py
├── chinook.db
├── preferences.json
├── requirements.txt
├── .env.example
├── core/
│   ├── __init__.py
│   ├── agent_cache.py
│   ├── memory_utils.py
│   ├── observability.py
│   ├── prompt_builder.py
│   ├── skill_loader.py
│   └── skill_router.py
├── skills/
│   ├── manifest.json
│   ├── data_quality_checker.md
│   ├── query_builder.md
│   ├── schema_analyzer.md
│   ├── segment_analyzer.md
│   └── time_series_analyst.md
├── tools/
│   ├── execute_query.py
│   ├── list_table.py
│   └── table_info.py
└── logs/
    └── agent_events.jsonl
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
AGENT_TOOL_MAX_ROWS=50
AGENT_TOOL_MAX_CELL_CHARS=200
AGENT_CONTEXT_NOTES_MAX_ITEMS=5
AGENT_CONTEXT_NOTES_MAX_CHARS=800
```

| Variable | Default | Description |
|---|---|---|
| `NVIDIA_API_KEY` | *(required)* | NVIDIA NIM API key |
| `NVIDIA_MODEL` | `meta/llama-3.1-70b-instruct` | Model endpoint |
| `DB_PATH` | `./chinook.db` | Path to SQLite database |
| `AGENT_CACHE_TTL_SECONDS` | `900` | Agent cache time-to-live |
| `AGENT_CACHE_MAX_SIZE` | `8` | Max cached agent instances |
| `AGENT_MAX_SKILLS` | `2` | Max skills per request |
| `AGENT_MAX_PROMPT_CHARS` | `6000` | System prompt character budget |
| `AGENT_MEMORY_TURNS` | `3` | Recent conversation turns kept in full |
| `AGENT_MEMORY_SUMMARY_MAX_CHARS` | `2000` | Max characters for compacted history summary |
| `AGENT_TOOL_MAX_ROWS` | `50` | Max rows returned by `execute_query` (truncation metadata when exceeded) |
| `AGENT_TOOL_MAX_CELL_CHARS` | `200` | Max characters per cell in query results |
| `AGENT_CONTEXT_NOTES_MAX_ITEMS` | `5` | Max context note lines injected per turn |
| `AGENT_CONTEXT_NOTES_MAX_CHARS` | `800` | Max characters for just-in-time context notes |

## Run

```bash
python main.py
```

## Runtime Flow

```text
User Input
  │
  ├─► Preference command (/pref add <text>)? ──► Store preference (preferences.json) ──► Ack
  │
  └─► Analysis query
        │
        ├─► Route relevant skills (LLM-based, manifest.json, strict JSON validation)
        ├─► Build system prompt (budget-aware, with few-shot examples)
        ├─► Get/create cached agent (TTL + LRU by skill set)
        │
        ├─► Memory pipeline:
        │     ├─► Clear tool results from old turns
        │     ├─► LLM-based compaction (fail-fast, no fallback)
        │     └─► Inject preferences + relevant context notes + recent turns
        │
        ├─► Invoke agent (tools: list_table, table_info, execute_query with row/cell bounds)
        └─► Log telemetry (request_id, router_latency_ms, compaction_*, error_stage, cache stats, tokens, latency)
```

Example queries:

- `List all tables in this database.`
- `Top 5 genres by total sales revenue.`
- `Show yearly revenue trend.`
- `Are there null emails in customers?`
- `/pref add I prefer results in markdown table format`

Exit with `exit` or `quit`.

## Tests

```bash
python -m pytest tests/ -v
```

100 tests covering: tools, skill routing, prompt building, agent caching, memory utilities (compaction, preferences, tool clearing), observability, and live agent simulation.

## Architecture Notes

- `execute_query` only allows `SELECT` queries. Results are bounded by `AGENT_TOOL_MAX_ROWS` and `AGENT_TOOL_MAX_CELL_CHARS`; truncation metadata (`truncated`, `returned_rows`, `row_limit`) is returned when applicable.
- Skills are selected per request via LLM-based routing (`core/skill_router.py`): user query and skill catalog are sent to the model with a strict JSON prompt; output is validated and fails fast on invalid shape. Prompt uses delimiters and an anti-instruction rule to reduce per-request injection risk. On invalid router output, the error is reported to the user and the session continues.
- System prompt is composed dynamically by `core/prompt_builder.py` with structured sections (Role, Tools, adaptive Exploration Strategy, Output Format, Examples) and selected skill content within a character budget.
- Agent instances are cached by active skill combination with TTL + LRU eviction (`core/agent_cache.py`).
- Conversation memory keeps recent turns in full and compacts older turns via LLM-based summarization (`core/memory_utils.py`). Compaction fails fast with `MemoryCompactionError`; no silent fallback.
- Just-in-time context notes: relevant summary lines are selected per turn by keyword overlap with user input and injected within a char budget.
- Tool results are cleared from old history before compaction to reduce context noise.
- User preferences are set via explicit `/pref add <text>` commands, persisted to `preferences.json`, and survive restarts.
- Request telemetry (`request_id`, router latency, compaction status/latency, `error_stage`, selected skills, cache stats, token usage, latency) is appended to `logs/agent_events.jsonl`.
