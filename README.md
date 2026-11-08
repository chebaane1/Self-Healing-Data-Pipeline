# 🛠️ Zero-Downtime Self-Healing Data Pipeline

> A local dbt and DuckDB pipeline with a bounded LLM agent that diagnoses failures, tests SQL repairs in a temporary sandbox, and promotes only validated changes.

---

## 📌 Executive Summary

`run_pipeline.py` initializes a sample DuckDB source and runs the dbt models and tests. On failure, it writes diagnostics to `error_logs.txt`. `agent_repair.py` reads those logs, edits the identified SQL model in a temporary project copy, and retries dbt validation. The change is copied back to `models/` only after both `dbt run` and `dbt test` succeed. There is no GitHub or pull request integration.

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
| **LLM** | **Ollama or a LiteLLM-compatible provider** | Local or hosted model inference. |

---

## 🔄 How It Works: Step-by-Step

1. `run_pipeline.py` initializes `raw_orders` and runs dbt. The sample `INVALID` amount reproduces a cast failure.
2. The orchestrator records the failure in `error_logs.txt`.
3. The repair agent identifies the failing model and reads or edits only that SQL file in a temporary copy.
4. It runs `dbt run` and `dbt test`, returning failure output to the model for another attempt, up to the configured limit.
5. The SQL is promoted to the working tree only if both commands pass. No Git branch, deployment, or pull request is created.

---

## 🚀 Quickstart (Local venv)

### Prerequisites
* Python 3.12 with `venv`
* Ollama for the default local model, or credentials for another LiteLLM provider

### Step-by-Step Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Optional: install the default local model used by agent_repair.py
ollama pull qwen2.5-coder:7b

# This sample pipeline is expected to fail on the INVALID amount and write error_logs.txt.
python run_pipeline.py

# Test the proposed repair without promoting it, then run without --dry-run to promote.
python agent_repair.py --dry-run
python agent_repair.py
```

The agent defaults to `ollama_chat/qwen2.5-coder:7b`. Set `LITELLM_MODEL` or pass `--model` to use another provider. Validation is limited to three attempts by default; adjust it with `--max-iterations`.