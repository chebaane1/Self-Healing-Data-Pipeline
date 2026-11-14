from __future__ import annotations

import contextlib
import difflib
import html
import io
import os
import time
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

import agent_repair
import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parent
ERROR_LOG_PATH = PROJECT_ROOT / "error_logs.txt"
MAX_VISIBLE_LOG_CHARS = 14000
STAGES = (
    ("introspection", "SOURCE SCHEMA", "DuckDB · columns and types"),
    ("strategy", "STRATEGY", "Failure analysis"),
    ("patch", "PATCH", "Target file"),
    ("validation", "VALIDATION", "dbt run + dbt test"),
)

st.set_page_config(
    page_title="Self-Healing Pipeline",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@500;600&display=swap');
      :root {
        --ink: #1b2d29;
        --ink-soft: #233d37;
        --muted: #556a64;
        --paper: #f3f4f1;
        --panel: #fbfbf9;
        --line: #d8dfd9;
        --forest: #0d5c46;
        --forest-deep: #163f39;
        --mint: #dfeee6;
        --coral: #c95d4d;
        --amber: #bf7a2d;
        --mono: 'DM Mono', 'SFMono-Regular', Consolas, monospace;
        --sans: 'DM Sans', 'Segoe UI', sans-serif;
      }
      html, body, [class*="css"] { font-family: var(--sans); color: var(--ink); }
      .stApp { background: var(--paper); color: var(--ink); }
      [data-testid="stHeader"] { background: rgba(243,244,241,.94); }
    [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], [data-testid="stAppDeployButton"] { display:none !important; }
    [data-testid="stHeader"] { display:none !important; height:0 !important; }
    [data-testid="stSidebar"], [data-testid="collapsedControl"] { display:none !important; }
      .block-container { max-width: 1440px; padding-top: 0rem; padding-bottom: 3rem; }
      h1, h2, h3 { letter-spacing: 0 !important; color: var(--ink); }
      h1 { font-family: 'Playfair Display', Georgia, serif !important; font-size: 2.45rem !important; font-weight: 600 !important; color: var(--ink-soft); }
      h2 { font-family: 'Playfair Display', Georgia, serif !important; font-size: 1.5rem !important; font-weight: 500 !important; }
      .eyebrow { color: var(--forest); font: 600 .69rem var(--mono); letter-spacing: .12em; text-transform: uppercase; }
    .hero { display:flex; justify-content:space-between; align-items:flex-start; gap:2rem; padding: 1rem 0 1.7rem; border-bottom: 1px solid var(--line); }
      .hero-copy { max-width: 760px; }
      .hero-copy p:last-child { color: var(--muted); margin: .35rem 0 0; }
    .hero-mark { color: var(--forest-deep); font: 600 .8rem var(--mono); white-space:nowrap; margin:0 0 .45rem; text-align:right; letter-spacing: .12em; }
    .pipeline-map { display:grid; grid-template-columns:minmax(0,1fr) 70px minmax(0,1.15fr) 70px minmax(0,1fr); align-items:center; gap:.7rem; margin:1.15rem 0 1.8rem; padding:1.15rem; background:var(--panel); border-top:2px solid var(--forest); border-bottom:1px solid var(--line); }
    .pipe-node { min-width:0; min-height:112px; padding:.9rem 1rem; border:1px solid var(--line); background:#f9faf8; }
    .pipe-node.active { border-color:var(--amber); box-shadow:inset 0 0 0 1px var(--amber); }
    .pipe-node.failed { border-color:var(--coral); box-shadow:inset 0 0 0 1px var(--coral); }
    .pipe-kicker { color: var(--muted); font: 600 .61rem var(--mono); letter-spacing:.08em; }
    .pipe-name { margin:.52rem 0 .28rem; color:var(--ink-soft); font-size:.95rem; font-weight:700; overflow-wrap:anywhere; }
    .pipe-detail { color:var(--muted); font: 500 .68rem/1.5 var(--mono); overflow-wrap:anywhere; }
    .pipe-center { text-align:center; }
    .pipe-center .pipe-name { font-size:.8rem; }
    .pipe-arrow { position:relative; height:2px; background:var(--line); overflow:hidden; display:block; }
    .pipe-arrow:after { content:'›'; position:absolute; right:-2px; top:-14px; color:var(--forest); font: 1.7rem var(--sans); }
    .pipe-arrow.active { background:var(--forest); animation:flow 1.2s ease-in-out infinite; }
      .metric-band { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); margin:1.15rem 0 1.8rem; background:var(--panel); border-top:2px solid var(--forest); border-bottom:1px solid var(--line); }
      .metric-cell { padding: .9rem 1rem; border-right:1px solid var(--line); }
      .metric-cell:last-child { border-right:0; }
      .metric-label { color:var(--muted); font: .64rem var(--mono); letter-spacing:.06em; text-transform:uppercase; }
      .metric-value { margin-top:.4rem; color:var(--ink); font-size:1.02rem; font-weight:600; }
      .stage-list { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.7rem; margin:.4rem 0 1.25rem; }
      .stage { min-height:112px; padding:.9rem; border:1px solid var(--line); background:var(--panel); position:relative; overflow:hidden; }
      .stage:before { content:''; position:absolute; inset:0 auto 0 0; width:3px; background:#b9c5bd; }
      .stage.done:before { background:var(--forest); }
      .stage.active:before { background:var(--amber); animation:pulse 1.1s ease-in-out infinite alternate; }
      .stage.error:before { background:var(--coral); }
      .stage-no { color:var(--muted); font: .62rem var(--mono); }
      .stage-title { margin:.48rem 0 .25rem; color:var(--ink); font-size:.78rem; font-weight:700; }
      .stage-copy { color:var(--muted); font-size:.68rem; line-height:1.4; }
      .stage-state { margin-top:.55rem; color:var(--forest); font: .58rem var(--mono); text-transform:uppercase; }
      .stage.active .stage-state { color:var(--amber); }
      .stage.error .stage-state { color:var(--coral); }
      .section-rule { margin:1.6rem 0 .8rem; border-top:1px solid var(--line); }
      .caption { color:var(--muted); font-size:.82rem; }
    .code-label { color:var(--muted); font:600 .82rem var(--mono); letter-spacing:.07em; text-transform:uppercase; margin-bottom:.45rem; }
    .code-label.before { color:var(--coral); }
    .code-label.after { color:var(--forest); }
      div[data-testid="stCode"] { border:1px solid var(--line); border-radius:3px; }
    div[data-testid="column"]:has(.code-label.before) div[data-testid="stCode"] { border:2px solid var(--coral); border-radius:4px; box-shadow:0 0 0 1px rgba(201,93,77,.12); }
    div[data-testid="column"]:has(.code-label.after) div[data-testid="stCode"] { border:2px solid var(--forest); border-radius:4px; box-shadow:0 0 0 1px rgba(13,92,70,.12); }
      .success-banner { padding:1rem 1.1rem; background:#e2eee6; border-left:4px solid var(--forest); color:#204c39; font-weight:600; }
      .failure-banner { padding:1rem 1.1rem; background:#f7e7e2; border-left:4px solid var(--coral); color:#843c34; font-weight:600; }
      .notice { padding:.85rem 1rem; background:#fff4df; border-left:3px solid var(--amber); color:#6f4a1f; font-size:.85rem; }
    .status-pill { display:inline-flex; align-items:center; gap:.6rem; margin-top:0; padding:.4rem .7rem; border:1px solid var(--line); background:rgba(255,255,255,.35); border-radius: 999px; color: var(--muted); font: 600 .7rem var(--mono); letter-spacing: .08em; text-transform: uppercase; transform:translateY(-.5rem); }
      .status-dot { width:.62rem; height:.62rem; border-radius:50%; display:inline-block; box-shadow: 0 0 0 2px rgba(255,255,255,.7); }
      .status-dot.ok { background:#2e9c63; }
      .status-dot.issue { background:#d85c4a; }
      .status-dot.idle { background:#a5b0aa; }
      .pipe-node.flowing { position:relative; overflow:hidden; }
    .pipe-node.flowing::before { content:""; position:absolute; inset:0; background:linear-gradient(90deg, rgba(46,156,99,0), rgba(46,156,99,.24), rgba(46,156,99,0)); transform:translateX(-100%); animation: dataFlow 2.8s ease-in-out infinite; }
      .pipe-node.error-flow { border-color:var(--coral); box-shadow: inset 0 0 0 1px rgba(216,92,74,.6); }
    .pipe-node.error-flow::before { content:""; position:absolute; inset:0; background:linear-gradient(90deg, rgba(216,92,74,0), rgba(216,92,74,.24), rgba(216,92,74,0)); transform:translateX(-100%); animation: errorPulse 2.8s ease-in-out infinite; }
    .pipe-arrow.flowing, .pipe-arrow.error-flow { background:var(--line); }
    .pipe-arrow.flowing::before, .pipe-arrow.error-flow::before { content:""; position:absolute; inset:0 auto 0 0; width:38%; background:linear-gradient(90deg, transparent, currentColor, transparent); animation: arrowParticle 2.8s ease-in-out infinite; }
    .pipe-arrow.flowing { color:#2e9c63; }
    .pipe-arrow.error-flow { color:#d85c4a; }
    .pipeline-map > :nth-child(1)::before { animation-delay:0s; }
    .pipeline-map > :nth-child(2)::before { animation-delay:.55s; }
    .pipeline-map > :nth-child(3)::before { animation-delay:1.1s; }
    .pipeline-map > :nth-child(4)::before { animation-delay:1.65s; }
    .pipeline-map > :nth-child(5)::before { animation-delay:2.2s; }
    .stButton > button { border-radius:4px; min-height:2.4rem; padding:0 .95rem; font-size:.82rem; font-weight:600; background:var(--ink-soft); color:#ffffff !important; border:1px solid var(--ink-soft); }
    .stButton > button:hover { background:var(--forest-deep); color:#ffffff !important; border-color:var(--forest-deep); }
    .stButton > button[kind="secondary"] { background:var(--ink-soft); border-color:var(--ink-soft); color:#ffffff !important; }
    .stButton > button[kind="secondary"]:hover { background:var(--forest-deep); border-color:var(--forest-deep); color:#ffffff !important; }
    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-secondary"] *,
    button[data-testid="stBaseButton-secondary"] p,
    button[data-testid="stBaseButton-secondary"] span,
    button[data-testid="stBaseButton-secondary"] div,
    button[data-testid="stBaseButton-secondary"] svg {
      color: #ffffff !important;
      fill: #ffffff !important;
      stroke: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
    }
      [data-testid="stExpander"] { border:1px solid var(--line); border-radius:3px; background:var(--panel); }
      @keyframes pulse { from { opacity:.45; } to { opacity:1; } }
            @keyframes flow { 0%, 100% { opacity:.4; } 50% { opacity:1; } }
      @keyframes dataFlow { 0% { transform:translateX(-100%); opacity:0; } 20% { opacity:1; } 100% { transform:translateX(120%); opacity:0; } }
      @keyframes errorPulse { 0% { transform:translateX(-100%); opacity:0; } 20% { opacity:1; } 100% { transform:translateX(120%); opacity:0; } }
    @keyframes arrowParticle { 0% { transform:translateX(-110%); opacity:0; } 20% { opacity:1; } 100% { transform:translateX(280%); opacity:0; } }
      @media (max-width: 850px) {
                .pipeline-map { grid-template-columns:minmax(0,1fr) 34px minmax(0,1.1fr) 34px minmax(0,1fr); gap:.4rem; padding:.7rem; }
                .pipe-node { min-height:120px; padding:.7rem; }
        .stage-list { grid-template-columns:repeat(2,minmax(0,1fr)); }
        .metric-band { grid-template-columns:repeat(2,minmax(0,1fr)); }
        .metric-cell:nth-child(2) { border-right:0; }
        .metric-cell:nth-child(-n+2) { border-bottom:1px solid var(--line); }
        .hero { align-items:flex-start; flex-direction:column; gap:.3rem; }
      }
      @media (max-width: 520px) {
                .pipeline-map { grid-template-columns:1fr; }
                .pipe-arrow { width:2px; height:22px; margin:auto; }
                .pipe-arrow:after { content:'⌄'; right:-8px; top:0; }
        .stage-list { grid-template-columns:1fr; }
        h1 { font-size:2rem !important; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def default_stages() -> dict[str, str]:
    return {key: "pending" for key, _, _ in STAGES}


def default_pipeline_states() -> dict[str, str]:
    return {
        "source": "pending",
        "transform": "pending",
        "target": "pending",
    }


def render_stages(states: dict[str, str]) -> str:
    cards = []
    labels = {"pending": "PENDING", "active": "IN PROGRESS", "done": "COMPLETE", "error": "FAILED"}
    for index, (key, title, copy) in enumerate(STAGES, start=1):
        state = states.get(key, "pending")
        cards.append(
            f'<div class="stage {state}">'
            f'<div class="stage-no">0{index} / STEP</div>'
            f'<div class="stage-title">{title}</div>'
            f'<div class="stage-copy">{copy}</div>'
            f'<div class="stage-state">{labels.get(state, "PENDING")}</div>'
            "</div>"
        )
    return f'<div class="stage-list">{"".join(cards)}</div>'


def render_metrics(values: dict[str, str]) -> str:
    items = (
        ("INCIDENT", values.get("incident", "—")),
        ("PIPELINE", values.get("pipeline", "Pending")),
        ("REPAIR", values.get("repair", "Pending")),
        ("MODE", values.get("mode", "Dry run")),
    )
    return '<div class="metric-band">' + "".join(
        f'<div class="metric-cell"><div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{html.escape(value)}</div></div>'
        for label, value in items
    ) + "</div>"


def render_pipeline_map(states: dict[str, str], status: str = "idle") -> str:
    flow_mode = "flowing" if status == "ok" else "error-flow" if status == "issue" else ""

    def node(key: str, kicker: str, title: str, detail: str, status_mode: str = "idle") -> str:
        state = states.get(key, "pending")
        class_name = f"pipe-node {state}"
        if status_mode in {"ok", "issue"}:
            class_name += " flowing"
            if status_mode == "issue":
                class_name = class_name.replace(" flowing", " error-flow")
        return (
            f'<div class="{class_name}"><div class="pipe-kicker">{html.escape(kicker)}</div>'
            f'<div class="pipe-name">{html.escape(title)}</div>'
            f'<div class="pipe-detail">{html.escape(detail)}</div></div>'
        )

    arrow_class = flow_mode
    return (
        '<div class="pipeline-map">'
        + node("source", "01 · SOURCE", "raw_orders", "DuckDB · main", status)
        + f'<div class="pipe-arrow {arrow_class}"></div>'
        + node("transform", "02 · TRANSFORMATION", "dbt", "stg_orders · validation", status)
        + f'<div class="pipe-arrow {arrow_class}"></div>'
        + node("target", "03 · TARGET", "stg_orders", "dbt-validated table", status)
        + "</div>"
    )


def render_reasoning(events: list[dict[str, Any]], status: str = "running") -> str:
    relevant_types = {
        "pipeline_failed", "agent_waiting", "agent_action", "validation_started",
        "validation_step_started", "validation_step_succeeded", "validation_failed",
        "validation_succeeded", "repair_succeeded",
    }
    relevant = [event for event in events if event.get("type") in relevant_types]
    if not relevant:
        return ""

    agent_started = any(
        event.get("type") in {"agent_waiting", "agent_action"} for event in relevant
    )

    def short(value: Any, limit: int = 170) -> str:
        text = " ".join(str(value or "").split())
        return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"

    entries: list[dict[str, str]] = []

    def add(key: str, icon: str, message: str, state: str) -> None:
        entries.append({"key": key, "icon": icon, "message": message, "state": state})

    def update(key: str, state: str, message: str | None = None) -> None:
        for entry in reversed(entries):
            if entry["key"] == key:
                entry["state"] = state
                if message is not None:
                    entry["message"] = message
                return

    def complete_active(prefixes: tuple[str, ...]) -> None:
        for entry in entries:
            if entry["state"] == "active" and entry["key"].startswith(prefixes):
                entry["state"] = "done"

    schema_added = False
    thinking_step = None
    repair_succeeded = False
    step_labels = {"source": "source preparation", "dbt run": "dbt run", "dbt test": "dbt test"}
    action_labels = {
        "read_sql_file": "Reviewing the target model",
        "write_sql_file": "Applying the proposed change",
        "read_project_file": "Reviewing project configuration",
        "write_project_file": "Updating project configuration",
        "finish_repair": "Checking the validated repair",
    }

    for event in relevant:
        event_type = event.get("type")
        iteration = event.get("iteration", 0)
        if event_type == "pipeline_failed":
            failed_step = step_labels.get(event.get("step"), "pipeline execution")
            add("diagnostic", "🔍", f"Reading dbt logs and traceback · {failed_step} failed.", "done" if agent_started else "active")
        elif event_type == "agent_waiting":
            if not schema_added:
                add("schema", "🧠", "Inspecting DuckDB schema (PRAGMA table_info).", "done")
                schema_added = True
            complete_active(("thinking:", "action:"))
            step = event.get("step", 1)
            thinking_step = step
            message = (
                "Reviewing validation results and refining the repair strategy."
                if step > 1 else "Analyzing the failure and selecting a repair strategy."
            )
            add(f"thinking:{step}", "💡", message, "active")
        elif event_type == "agent_action":
            if thinking_step is not None:
                update(f"thinking:{thinking_step}", "done")
            action_name = event.get("action", "")
            action_text = action_labels.get(action_name, "Preparing a targeted repair")
            reason = short(event.get("reason"), 150)
            if reason:
                action_text += f" · {reason}"
            add(f"strategy:{event.get('step', 0)}", "💡", action_text, "done")
            target = event.get("model")
            target_text = f" · {target}" if target else ""
            add(
                f"action:{event.get('step', 0)}",
                "🛠️",
                f"{action_labels.get(action_name, 'Applying repair action')}{target_text}.",
                "active",
            )
        elif event_type == "validation_started":
            complete_active(("action:",))
            add(
                f"validation:{iteration}",
                "🧪",
                f"Starting sandbox validation · iteration {iteration}.",
                "active",
            )
        elif event_type == "validation_step_started":
            command = event.get("command", "dbt")
            message = (
                "Preparing source data in the sandbox."
                if command == "init_source"
                else f"Running dbt {command} in the sandbox."
            )
            add(f"check:{iteration}:{command}", "🧪", message, "active")
        elif event_type == "validation_step_succeeded":
            command = event.get("command", "dbt")
            message = (
                "Source data prepared in the sandbox."
                if command == "init_source"
                else f"dbt {command} passed in the sandbox."
            )
            update(f"check:{iteration}:{command}", "done", message)
        elif event_type == "validation_failed":
            command = event.get("command", "dbt")
            key = f"check:{iteration}:{command}"
            failed_check = "source initialization" if command == "init_source" else f"dbt {command}"
            message = f"{failed_check} failed · the agent is refining the fix."
            if any(entry["key"] == key for entry in entries):
                update(key, "error", message)
            else:
                add(key, "🧪", message, "error")
            update(f"validation:{iteration}", "error", "Sandbox validation failed; the agent is revising the repair.")
        elif event_type == "validation_succeeded":
            update(
                f"validation:{iteration}",
                "done",
                "Sandbox checks passed · dbt run and dbt test.",
            )
        elif event_type == "repair_succeeded":
            repair_succeeded = True
            complete_active(("thinking:", "action:", "validation:", "check:"))
            target = event.get("model") or "target file"
            add("promotion", "🎉", f"Validation passed · promoted the verified fix to {target}.", "done")

    if status == "failed" and not repair_succeeded and not any(entry["state"] == "error" for entry in entries):
        add("repair-failed", "⚠️", "Repair stopped before validation completed.", "error")

    if repair_succeeded or status == "resolved":
        state_class = "resolved"
        heading = "Issue resolved and validated"
    elif status == "failed":
        state_class = "failed"
        heading = "Repair stopped · diagnostic retained"
    elif agent_started:
        state_class = "running"
        heading = "AI agent is fixing the issue…"
    else:
        state_class = "running"
        heading = "Issue detected · preparing repair"

    items = "".join(
        f'<li class="activity-item {entry["state"]}">'
        f'<span class="activity-symbol" aria-hidden="true">{html.escape(entry["icon"])}</span>'
        f'<p class="activity-copy">{html.escape(entry["message"])}</p>'
        f'<span class="activity-state" aria-hidden="true"></span></li>'
        for entry in entries[-100:]
    )
    success = (
        '<div class="reasoning-success">✓ Issue resolved and validated · dbt checks passed</div>'
        if repair_succeeded or status == "resolved" else ""
    )
    styles = """
      :root { color-scheme:light; --paper:#fbfbf9; --ink:#1b2d29; --muted:#556a64; --line:#d8dfd9; --forest:#0d5c46; --coral:#c95d4d; --mono:Consolas,monospace; }
      * { box-sizing:border-box; }
      html, body { margin:0; background:transparent; color:var(--ink); font-family:Aptos,'Segoe UI',sans-serif; }
      .agent-reasoning { overflow:hidden; border:1px solid var(--line); border-top:2px solid var(--forest); background:var(--paper); }
      .agent-reasoning.failed { border-top-color:var(--coral); }
      .reasoning-head { display:flex; align-items:center; gap:.65rem; min-height:46px; padding:.7rem 1rem; border-bottom:1px solid var(--line); color:var(--ink); font:600 .72rem var(--mono); }
      .reasoning-pulse { width:.8rem; height:.8rem; flex:0 0 auto; border:2px solid rgba(13,92,70,.2); border-top-color:var(--forest); border-radius:50%; animation:spin .8s linear infinite; }
      .failed .reasoning-pulse { border-color:var(--coral); animation:none; }
      .resolved .reasoning-pulse { border:0; border-radius:50%; background:var(--forest); animation:none; }
      .reasoning-feed { max-height:218px; overflow-y:auto; overscroll-behavior:contain; scroll-behavior:smooth; margin:0; padding:.25rem 1rem .45rem; list-style:none; }
    .activity-item { display:grid; grid-template-columns:20px minmax(0,1fr) 16px; align-items:start; gap:.55rem; padding:.65rem .1rem; border-bottom:1px solid var(--line); }
    .activity-item:last-child { border-bottom:0; animation:arrive .22s ease both; }
      .activity-symbol { font-size:.82rem; line-height:1.35; text-align:center; }
      .activity-copy { margin:0; font-size:.75rem; line-height:1.45; overflow-wrap:anywhere; }
      .activity-state { width:.72rem; height:.72rem; margin-top:.15rem; }
      .activity-item.active .activity-state { border:2px solid rgba(13,92,70,.2); border-top-color:var(--forest); border-radius:50%; animation:spin .8s linear infinite; }
      .activity-item.done .activity-state::before { content:'✓'; color:var(--forest); font-size:.78rem; font-weight:700; }
      .activity-item.error .activity-state::before { content:'×'; color:var(--coral); font-size:.9rem; font-weight:700; }
      .reasoning-success { padding:.68rem 1rem; border-top:1px solid #c9ded0; background:#e2eee6; color:#204c39; font-size:.76rem; font-weight:600; }
    .resolution-summary { margin:0 0 1.2rem; padding:.75rem 1rem; border:1px solid var(--line); border-left:3px solid var(--forest); background:var(--panel); }
    .resolution-summary.failed { border-left-color:var(--coral); }
    .resolution-summary h3 { margin:0 0 .45rem; color:var(--ink-soft); font:600 .68rem var(--mono); letter-spacing:.06em; text-transform:uppercase; }
    .resolution-summary p { margin:.25rem 0 0; color:var(--muted); font-size:.76rem; line-height:1.5; overflow-wrap:anywhere; }
    .resolution-summary strong { color:var(--ink); font-weight:650; }
      .resolved .reasoning-feed { display:none; }
      @keyframes spin { to { transform:rotate(360deg); } }
      @keyframes arrive { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
      @media (prefers-reduced-motion:reduce) { *,*::before,*::after { animation-duration:.01ms !important; scroll-behavior:auto !important; } }
    """
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<style>{styles}</style></head><body>'
        f'<section class="agent-reasoning {state_class}" role="status" aria-live="polite">'
        f'<div class="reasoning-head"><span class="reasoning-pulse" aria-hidden="true"></span>'
        f'<span>{html.escape(heading)}</span></div>'
        f'<ol class="reasoning-feed">{items}</ol>{success}</section>'
        '<script>const feed=document.querySelector(".reasoning-feed");'
        'if(feed)requestAnimationFrame(()=>feed.scrollTo({top:feed.scrollHeight,behavior:"smooth"}));</script>'
        '</body></html>'
    )


class EventView:
    def __init__(self, pipeline_slot: Any | None = None, reasoning_slot: Any | None = None):
        self.pipeline_slot = pipeline_slot
        self.reasoning_slot = reasoning_slot
        self.states = default_stages()
        self.pipeline_states = default_pipeline_states()
        self.events: list[dict[str, Any]] = []
        self.pipeline = "Pending"
        self.repair = "Pending"

    def _render(self) -> None:
        if self.pipeline_slot is not None:
            self.pipeline_slot.markdown(
                render_pipeline_map(self.pipeline_states, "ok" if self.pipeline == "PIPELINE OPERATIONAL" else "idle"),
                unsafe_allow_html=True,
            )
        if self.reasoning_slot is not None:
            reasoning_status = "resolved" if self.repair == "Validated" else "failed" if self.repair == "Failed" else "running"
            self.reasoning_slot.empty()
            with self.reasoning_slot.container():
                components.html(
                    render_reasoning(self.events, reasoning_status),
                    height=98 if reasoning_status == "resolved" else 306,
                    scrolling=False,
                )

    def on_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        event_type = event.get("type")
        action = event.get("action")
        step = event.get("step")

        if event_type == "pipeline_started":
            self.pipeline = "In progress"
            self.pipeline_states.update(
                source="active", transform="pending", target="pending"
            )
        elif event_type == "pipeline_step_started":
            if step == "source":
                self.pipeline_states["source"] = "active"
            elif step == "dbt run":
                self.pipeline_states["source"] = "done"
                self.pipeline_states["transform"] = "active"
            elif step == "dbt test":
                self.pipeline_states["transform"] = "done"
                self.pipeline_states["target"] = "active"
        elif event_type == "pipeline_succeeded":
            self.pipeline = "Succeeded"
            self.states = {key: "done" for key, _, _ in STAGES}
            self.pipeline_states.update(
                source="done", transform="done", target="done"
            )
        elif event_type == "pipeline_failed":
            self.pipeline = "Failure detected"
            if step == "source":
                self.pipeline_states["source"] = "failed"
            elif step == "dbt test":
                self.pipeline_states["target"] = "failed"
            else:
                self.pipeline_states["transform"] = "failed"
        elif event_type == "repair_started":
            self.states["introspection"] = "done"
            self.states["strategy"] = "active"
            self.repair = "Analyzing"
        elif event_type == "agent_action":
            if action in {"write_sql_file", "write_project_file"}:
                self.states["strategy"] = "done"
                self.states["patch"] = "done"
            elif action in {"read_sql_file", "read_project_file"}:
                self.states["strategy"] = "active"
        elif event_type == "validation_started":
            self.states["strategy"] = "done"
            self.states["patch"] = "done"
            self.states["validation"] = "active"
        elif event_type == "validation_failed":
            self.states["validation"] = "error"
            self.repair = "Retrying"
        elif event_type == "validation_succeeded":
            self.states["validation"] = "done"
        elif event_type == "repair_succeeded":
            self.states = {key: "done" for key, _, _ in STAGES}
            self.repair = "Validated"
            self.pipeline = "PIPELINE OPERATIONAL"
            self.pipeline_states.update(source="done", transform="done", target="done")
        self._render()


class LiveOutput(io.TextIOBase):
    def __init__(self, output_slot: Any):
        self.output_slot = output_slot
        self.parts: list[str] = []

    def write(self, text: str) -> int:
        if text:
            self.parts.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return "".join(self.parts)


def collect_allowed_paths(log_text: str) -> list[str]:
    paths = set(agent_repair.DBT_METADATA_PATHS)
    try:
        target, is_model = agent_repair.identify_repair_target(log_text, PROJECT_ROOT)
        paths.add(target.relative_to(PROJECT_ROOT).as_posix())
    except ValueError:
        pass
    if agent_repair.is_resource_failure(log_text):
        paths.add(agent_repair.INIT_SOURCE_PATH)
    return sorted(path for path in paths if (PROJECT_ROOT / path).is_file())


def run_pipeline_once(
    event_view: EventView,
    output_slot: Any,
) -> dict[str, Any]:
    output = LiveOutput(output_slot)
    log_before = ERROR_LOG_PATH.stat().st_mtime_ns if ERROR_LOG_PATH.exists() else None
    run_started_ns = time.time_ns()
    log_text = ""

    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        pipeline_code = run_pipeline.main(on_event=event_view.on_event)
    fresh_log = False
    if pipeline_code != 0 and ERROR_LOG_PATH.is_file():
        log_mtime = ERROR_LOG_PATH.stat().st_mtime_ns
        fresh_log = log_mtime != log_before and log_mtime >= run_started_ns
        if fresh_log:
            log_text = ERROR_LOG_PATH.read_text(encoding="utf-8", errors="replace")

    return {
        "pipeline_code": pipeline_code,
        "pipeline_failed": pipeline_code != 0,
        "fresh_log": fresh_log,
        "log_text": log_text,
        "events": event_view.events,
        "pipeline_states": event_view.pipeline_states,
        "output": output.getvalue(),
        "error": "" if pipeline_code == 0 or fresh_log else "Failure without a recent diagnostic log.",
    }


def run_agent_repair(
    state: dict[str, Any],
    event_view: EventView,
    output_slot: Any,
) -> dict[str, Any]:
    output = LiveOutput(output_slot)
    log_text = state.get("log_text", "")
    allowed_paths = collect_allowed_paths(log_text)
    before_files = {
        relative_path: (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in allowed_paths
    }
    error_message = ""
    repair_code: int | None = 1

    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            model_name = os.environ.get("LITELLM_MODEL", "gemini/gemini-3.1-flash-lite")
            repair_code = agent_repair.repair_model(
                Path("error_logs.txt"),
                model_name,
                False,
                16,
                3,
                on_event=event_view.on_event,
            )
        except Exception as error:
            error_message = f"Repair interrupted: {type(error).__name__}: {error}"
            event_view.repair = "Failed"

    after_files = {
        relative_path: (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in allowed_paths
    } if repair_code == 0 else {}
    return {
        **state,
        "pipeline_code": state.get("pipeline_code"),
        "repair_code": repair_code,
        "log_text": log_text,
        "before_files": before_files,
        "after_files": after_files,
        "promoted": repair_code == 0,
        "error": error_message,
        "events": event_view.events,
        "stages": event_view.states,
        "pipeline_states": event_view.pipeline_states,
        "repair_status": event_view.repair,
        "output": (state.get("output", "") + output.getvalue())[-MAX_VISIBLE_LOG_CHARS:],
        "schema": agent_repair.read_duckdb_schema(PROJECT_ROOT),
    }


def run_promoted_pipeline(
    state: dict[str, Any],
    pipeline_slot: Any,
    reasoning_slot: Any,
    output_slot: Any,
) -> dict[str, Any]:
    presenter = EventView(pipeline_slot, reasoning_slot)
    presenter.events = list(state.get("events", []))
    presenter.states = dict(state.get("stages", default_stages()))
    presenter.pipeline_states = default_pipeline_states()
    presenter.repair = "Validated"
    output = LiveOutput(output_slot)
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        pipeline_code = run_pipeline.main(on_event=presenter.on_event)

    result = dict(state)
    result.update(
        pipeline_code=pipeline_code,
        pipeline_states=presenter.pipeline_states,
        stages=presenter.states,
        events=presenter.events,
        repair_status=(
            "Validated · pipeline rerun"
            if pipeline_code == 0
            else "Fix validated · rerun failed"
        ),
        output=(state.get("output", "") + output.getvalue())[-MAX_VISIBLE_LOG_CHARS:],
    )
    if pipeline_code != 0 and ERROR_LOG_PATH.is_file():
        result["log_text"] = ERROR_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    return result


def render_comparison(result: dict[str, Any]) -> None:
    before_files = result.get("before_files", {})
    after_files = result.get("after_files", {})
    changed = [
        path for path, content in after_files.items()
        if path not in before_files or before_files[path] != content
    ]
    if not changed:
        st.info("No verified patch is available to display a diff.")
        return

    for path in changed:
        before = before_files.get(path, "")
        after = after_files[path]
        left, right = st.columns(2)
        with left:
            st.markdown(f'<div class="code-label before">BEFORE · {html.escape(path)}</div>', unsafe_allow_html=True)
            st.code(before or "(file missing)", language=path.rsplit(".", 1)[-1])
        with right:
            st.markdown(f'<div class="code-label after">AFTER · {html.escape(path)}</div>', unsafe_allow_html=True)
            st.code(after, language=path.rsplit(".", 1)[-1])
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"before/{path}",
                tofile=f"after/{path}",
            )
        )
        with st.expander("View diff", expanded=False):
            st.code(diff or "No changes", language="diff")


def render_resolution_summary(result: dict[str, Any]) -> str:
    events = result.get("events", [])
    pipeline_failures = [event for event in events if event.get("type") == "pipeline_failed"]
    validation_failures = [event for event in events if event.get("type") == "validation_failed"]
    write_actions = [
        event for event in events
        if event.get("type") == "agent_action"
        and event.get("action") in {"write_sql_file", "write_project_file"}
    ]
    repair_succeeded = next(
        (event for event in reversed(events) if event.get("type") == "repair_succeeded"),
        None,
    )
    if not pipeline_failures and not result.get("repair_code"):
        return ""

    def short(value: Any, limit: int = 220) -> str:
        text = " ".join(str(value or "").split())
        return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"

    original_failure = pipeline_failures[0] if pipeline_failures else {}
    step = original_failure.get("step", "pipeline execution")
    output = str(original_failure.get("output", ""))
    error_detail = ""
    for line in output.splitlines():
        for marker in ("Binder Error:", "Compilation Error:", "Database Error:", "Runtime Error:"):
            if marker in line:
                error_detail = short(line.split(marker, 1)[1].strip())
                break
        if error_detail:
            break
    issue = f"{step} failed"
    if error_detail:
        issue += f": {error_detail}"

    fix_action = write_actions[-1] if write_actions else None
    if fix_action:
        file_path = fix_action.get("model") or "the affected project file"
        reason = short(fix_action.get("reason"))
        verb = "Updated" if result.get("repair_code") == 0 else "Attempted to update"
        fix = f"{verb} {file_path}"
        if reason:
            fix += f" · {reason}"
    elif result.get("repair_code") == 0:
        fix = "The agent confirmed the repair without reporting a file write."
    else:
        fix = "The agent did not complete a validated file change."

    failed_validation = validation_failures[-1] if validation_failures else None
    if result.get("repair_code") == 0 and repair_succeeded:
        validation = "dbt run and dbt test passed in the sandbox."
        if repair_succeeded.get("dry_run"):
            validation += " The project file was not changed (dry run)."
        elif result.get("promoted") and result.get("pipeline_code") == 0:
            validation += " The fix was promoted and the pipeline rerun succeeded."
        elif result.get("promoted"):
            rerun_failure = pipeline_failures[-1] if len(pipeline_failures) > 1 else {}
            rerun_step = rerun_failure.get("step", "pipeline")
            validation += f" The fix was promoted, but the {rerun_step} rerun failed."
        else:
            validation += " The fix was validated but not promoted."
        failed = False
    elif failed_validation:
        command = failed_validation.get("command", "sandbox validation")
        validation = f"{command} failed in the sandbox; the agent could not complete a validated repair."
        failed = True
    else:
        validation = short(result.get("error")) or "The agent stopped before validation completed."
        failed = True

    return (
        f'<section class="resolution-summary{" failed" if failed else ""}" aria-label="Resolution summary">'
        '<h3>Resolution summary</h3>'
        f'<p><strong>Issue:</strong> {html.escape(issue)}</p>'
        f'<p><strong>Fix:</strong> {html.escape(fix)}</p>'
        f'<p><strong>Validation:</strong> {html.escape(validation)}</p>'
        '</section>'
    )


def main() -> None:
    header_left, header_right = st.columns([3, 1])
    with header_left:
        st.markdown(
            '<div class="hero-copy"><p class="eyebrow">DATA PIPELINE</p>'
            '<h1>Self-Healing Pipeline</h1></div>',
            unsafe_allow_html=True,
        )
    with header_right:
        st.markdown('<div class="hero-mark">DUCKDB&nbsp; / &nbsp;DBT</div>', unsafe_allow_html=True)

    state = st.session_state.get("pipeline_result", {})
    last_code = state.get("pipeline_code")
    if state.get("repair_code") == 0 and last_code == 0:
        status_label = "Pipeline operational"
        status_class = "ok"
    elif state.get("repair_code") == 0 and "failed" in str(state.get("repair_status", "")).lower():
        status_label = "Rerun failed"
        status_class = "issue"
    elif state.get("repair_code") == 0:
        status_label = "Fix validated"
        status_class = "ok"
    elif last_code is None:
        status_label = "Pipeline operational"
        status_class = "ok"
    elif last_code == 0:
        status_label = "Last run passed"
        status_class = "ok"
    else:
        status_label = "Last run failed"
        status_class = "issue"
    status_column, launch_column, auto_column = st.columns([5, 1, 1.25], vertical_alignment="center")
    with status_column:
        st.markdown(
            f'<div class="status-pill"><span class="status-dot {status_class}"></span><span>{html.escape(status_label)}</span></div>',
            unsafe_allow_html=True,
        )
    with launch_column:
        launch = st.button(
            "Run pipeline",
            icon=":material/play_arrow:",
            help="Run the pipeline",
            type="secondary",
            disabled=bool(st.session_state.get("pipeline_running")),
        )
    auto_enabled = bool(st.session_state.get("auto_pipeline_enabled", False))
    with auto_column:
        toggle_auto = st.button(
            "Auto: ON" if auto_enabled else "Auto: OFF",
            icon=":material/autorenew:",
            help="Start after 60 seconds, then run every 60 seconds while enabled.",
            type="primary" if auto_enabled else "secondary",
            key="auto_pipeline_toggle",
        )
    if toggle_auto:
        st.session_state["auto_pipeline_enabled"] = not auto_enabled
        if not auto_enabled:
            st.session_state["auto_pipeline_next_run_at"] = time.monotonic() + 60
        else:
            st.session_state["auto_pipeline_next_run_at"] = None
        st.rerun()
    pipeline_slot = st.empty()
    pipeline_slot.markdown(
        render_pipeline_map(
            state.get("pipeline_states", default_pipeline_states()),
            status_class,
        ),
        unsafe_allow_html=True,
    )
    reasoning_slot = st.empty()

    if state.get("events"):
        presenter = EventView(pipeline_slot, reasoning_slot)
        presenter.events = list(state["events"])
        presenter.pipeline_states = dict(state.get("pipeline_states", default_pipeline_states()))
        presenter.states = dict(state.get("stages", default_stages()))
        presenter.repair = (
            "Validated" if state.get("repair_code") == 0
            else "Failed" if state.get("repair_code") not in (None, 0)
            else state.get("repair_status", "Pending")
        )
        presenter.pipeline = "PIPELINE OPERATIONAL" if state.get("repair_code") == 0 else state.get("repair_status", "Pending")
        presenter._render()

    if state.get("repair_code") == 0:
        st.markdown(render_resolution_summary(state), unsafe_allow_html=True)
        render_comparison(state)
    elif state.get("repair_code") is not None:
        st.markdown(render_resolution_summary(state), unsafe_allow_html=True)
    elif state.get("pipeline_code") == 0:
        st.success("Pipeline completed.")

    def schedule_next_auto_run() -> None:
        if st.session_state.get("auto_pipeline_enabled"):
            st.session_state["auto_pipeline_next_run_at"] = time.monotonic() + 60

    @st.fragment(run_every=60 if auto_enabled else None, key="auto_pipeline_timer")
    def run_pipeline_automatically() -> None:
        if not st.session_state.get("auto_pipeline_enabled"):
            return
        if (
            st.session_state.get("pipeline_running")
            or st.session_state.get("agent_running")
            or st.session_state.get("restart_after_repair")
        ):
            return

        now = time.monotonic()
        next_run_at = st.session_state.get("auto_pipeline_next_run_at")
        if next_run_at is None or now < next_run_at:
            return

        st.session_state["auto_pipeline_next_run_at"] = None
        auto_reasoning_slot = st.empty()
        event_view = EventView(None, auto_reasoning_slot)
        output_slot = st.empty()
        st.session_state["pipeline_running"] = True
        with st.spinner("Automatic pipeline run is starting…"):
            result = run_pipeline_once(event_view, output_slot)
        result.update(
            repair_code=None,
            repair_status="Pending",
            stages=event_view.states,
            before_files={},
            after_files={},
            promoted=False,
        )
        st.session_state["pipeline_result"] = result
        if result["pipeline_failed"] and result["fresh_log"]:
            st.session_state["agent_running"] = True
        else:
            st.session_state["pipeline_running"] = False
            schedule_next_auto_run()
        st.rerun()

    if launch:
        event_view = EventView(pipeline_slot, reasoning_slot)
        output_slot = st.empty()
        st.session_state["pipeline_running"] = True
        with st.spinner("Pipeline is running…"):
            result = run_pipeline_once(event_view, output_slot)
        result.update(
            repair_code=None,
            repair_status="Pending",
            stages=event_view.states,
            before_files={},
            after_files={},
            promoted=False,
        )
        st.session_state["pipeline_result"] = result
        if result["pipeline_failed"] and result["fresh_log"]:
            st.session_state["agent_running"] = True
        else:
            st.session_state["pipeline_running"] = False
            schedule_next_auto_run()
        st.rerun()

    run_pipeline_automatically()

    if st.session_state.get("agent_running"):
        repair_state = st.session_state.get("pipeline_result", {})
        presenter = EventView(pipeline_slot, reasoning_slot)
        presenter.events = list(repair_state.get("events", []))
        presenter.pipeline_states = dict(repair_state.get("pipeline_states", default_pipeline_states()))
        presenter.states = dict(repair_state.get("stages", default_stages()))
        output_slot = st.empty()
        result = run_agent_repair(repair_state, presenter, output_slot)
        st.session_state["pipeline_result"] = result
        st.session_state["agent_running"] = False
        if result.get("repair_code") == 0 and result.get("promoted"):
            st.session_state["restart_after_repair"] = True
        else:
            st.session_state["pipeline_running"] = False
            schedule_next_auto_run()
        st.rerun()

    if st.session_state.get("restart_after_repair"):
        st.session_state["restart_after_repair"] = False
        event_view = EventView(pipeline_slot, reasoning_slot)
        output_slot = st.empty()
        result = run_promoted_pipeline(
            st.session_state.get("pipeline_result", {}),
            pipeline_slot,
            reasoning_slot,
            output_slot,
        )
        st.session_state["pipeline_result"] = result
        st.session_state["pipeline_running"] = False
        schedule_next_auto_run()
        st.rerun()


if __name__ == "__main__":
    main()
