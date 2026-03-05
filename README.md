# Agent Analysis DB

Minimal database analysis agent using LangChain + NVIDIA NIM over SQLite (`chinook.db`).

## Project Structure

```text
agent-analysis-db/
├── main.py
├── chinook.db
├── requirements.txt
├── .env.example
├── skills/
│   ├── query_builder.md
│   └── schema_analyzer.md
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
```

If `DB_PATH` is not set, `main.py` defaults to local `chinook.db` in this project.

## Run

```bash
python main.py
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
- Agent behavior is guided by:
  - `skills/schema_analyzer.md`
  - `skills/query_builder.md`
