# 🛠️ Zero-Downtime Self-Healing Data Pipeline

> A local dbt and DuckDB pipeline with a bounded LLM agent that diagnoses failures, tests SQL repairs in a temporary sandbox, and promotes only validated changes.

---

## 📌 Executive Summary

`run_pipeline.py` initializes a sample DuckDB source and runs the dbt models and tests. On failure, it writes diagnostics to `error_logs.txt`. `agent_repair.py` reads those logs and the current `raw_orders` schema from DuckDB, then edits only an explicitly allowed file in a temporary project copy: the identified SQL model, the dbt source/model YAML metadata, or `scripts/init_source.py` when logs indicate a resource/volume failure. Each successful edit is checked with `dbt run` and `dbt test`; only the changed, validated files are copied back. There is no OS-level sandbox, GitHub integration, or pull request workflow.

---

## 🏗️ System Architecture

```
                scripts/init_source.py
                    |
                    v
                data/pipeline.duckdb --> dbt run + dbt test --> error_logs.txt on failure
                                           |
                                           v
                                      agent_repair.py
                                           |
                                  temporary project sandbox
                                  dbt run + dbt test retry loop
                                           |
                                      both pass -> promote SQL
```

---

## 🧰 Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Runtime** | **Python 3.12** | Local virtual environment for the pipeline and repair agent. |
| **Data Engine** | **DuckDB** | Local source and staging data. |
| **Transformation** | **dbt Core + dbt-duckdb** | SQL models and data quality tests. |
| **Agent** | **Instructor + Pydantic + LiteLLM** | Structured tool calls and bounded repair loop. |
| **LLM** | **Google Gemini via LiteLLM** | Hosted model inference using the Gemini API. |

---

## 🔄 How It Works: Step-by-Step

1. `run_pipeline.py` initializes `raw_orders` and runs dbt. The sample `INVALID` amount reproduces a cast failure.
2. The orchestrator records the failure in `error_logs.txt`.
3. The repair agent identifies a failing model or explicitly reported dbt/ingestion file, and reads or edits only files permitted for that failure in a temporary copy. It receives the observed `raw_orders` column names and types as diagnostic metadata.
4. It runs `dbt run` and `dbt test` after each write, returning failure output to the model for another attempt, up to the configured limit.
5. Changed files are promoted to the working tree only if both commands pass and the source files have not changed during repair. This is application-level isolation, not an OS sandbox; no Git branch, deployment, or pull request is created.

---

## 🚀 Quickstart (Local venv)

### Prerequisites
* Python 3.12 with `venv`
* A Google Gemini API key, available from Google AI Studio

### Step-by-Step Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Add GEMINI_API_KEY=your-api-key to the ignored .env file

# This sample pipeline is expected to fail on the INVALID amount and write error_logs.txt.
python run_pipeline.py

# Test the proposed repair without promoting it, then run without --dry-run to promote.
python agent_repair.py --dry-run
python agent_repair.py
```

The agent defaults to `gemini/gemini-3.1-flash-lite`, a Gemini API free-tier model suited to agentic tasks. LiteLLM reads the API key from `GEMINI_API_KEY`. Set `LITELLM_MODEL` or pass `--model` to select another LiteLLM-supported model. Free-tier quotas apply. Validation is limited to three attempts by default; adjust it with `--max-iterations`.

## Local Dashboard

Start the local dashboard after installing the project dependencies:

```bash
python dashboard.py
```

Open the printed `http://127.0.0.1` address. The dashboard can run the pipeline, inspect the latest dbt result and DuckDB tables, and launch the repair agent in dry-run or promotion mode. Agent actions include short, evidence-based reasons; detailed dbt output stays in expandable event entries. The service binds to localhost only. Set `DASHBOARD_PORT` to choose a port; if it is occupied, the server selects an available one.