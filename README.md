# Self-Healing Data Pipeline

A local dbt and DuckDB example with an AI-assisted repair loop and a browser dashboard.

## Project Overview

The pipeline initializes a sample `raw_orders` table in DuckDB, runs the dbt staging model, and runs configured dbt tests. The sample includes an invalid amount; `stg_orders` converts it to `NULL` instead of failing. No dbt data tests are currently configured, so `dbt test` does not enforce a data-quality assertion yet.

When a pipeline command fails, `run_pipeline.py` saves its diagnostics to `error_logs.txt`. `agent_repair.py` uses those logs and the observed DuckDB schema to propose a targeted change. It validates changes in a temporary project copy with source initialization, `dbt run`, and `dbt test`. Only validated changes are promoted, unless dry-run mode is selected. This is application-level isolation, not an OS security sandbox.

The local dashboard can run the pipeline, show the latest dbt result and DuckDB tables, and launch the repair agent. Repair runs default to dry-run; promotion requires confirmation in the dashboard.

## Components

| Component | Purpose |
| --- | --- |
| `scripts/init_source.py` | Creates the sample `raw_orders` table and data. |
| `models/staging/stg_orders.sql` | Casts `total_amount` to a numeric `amount`, preserving invalid values as `NULL`. |
| `run_pipeline.py` | Initializes the source, runs dbt, and records failure diagnostics. |
| `agent_repair.py` | Runs the bounded, LLM-assisted repair and validation loop. |
| `dashboard.py` and `dashboard/` | Serve the local browser dashboard and its static assets. |
| `test_agent_repair.py` | Unit tests for repair targeting, permissions, and DuckDB schema inspection. |

The repair agent may edit the failing SQL model or dbt metadata. It may edit `scripts/init_source.py` only for a logged resource or timeout failure. It does not create Git branches, deploy changes, or open pull requests.

## Requirements

- Python 3.10 or later
- A Google Gemini API key to use the repair agent with the default model

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For repair-agent use, create a `.env` file in the project root and set:

```dotenv
GEMINI_API_KEY=your-api-key
```

The pipeline and dashboard work without an API key; the key is needed only for LLM repair. The default model is `gemini/gemini-3.1-flash-lite`. Set `LITELLM_MODEL` or pass `--model` to use another LiteLLM-supported model. API quotas and charges depend on the provider and account.

## Run

Run the sample pipeline:

```bash
python run_pipeline.py
```

Run the unit tests:

```bash
python -m unittest discover -v
```

Start the browser dashboard:

```bash
python dashboard.py
```

Open the localhost URL printed by the server (default port `8765`). Set `DASHBOARD_PORT` to request another port; if it is unavailable, the server selects an available one. The server binds to `127.0.0.1` only.

After a pipeline failure, preview a repair from the saved diagnostic before promoting it:

```bash
python agent_repair.py --dry-run
python agent_repair.py
```

The agent defaults to at most 3 dbt validation attempts and 16 tool steps. Adjust these with `--max-iterations` and `--max-steps`. The CLI expects a recent `error_logs.txt`, normally written by a failed pipeline run.