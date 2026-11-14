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

import agent_repair
import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parent
ERROR_LOG_PATH = PROJECT_ROOT / "error_logs.txt"
MAX_VISIBLE_LOG_CHARS = 14000
STAGES = (
    ("introspection", "SCHÉMA SOURCE", "DuckDB · colonnes et types"),
    ("strategy", "STRATÉGIE", "Analyse du diagnostic"),
    ("patch", "CORRECTIF", "Fichier concerné"),
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
        --forest: #1e584d;
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
    .agent-feed { max-height:320px; overflow-y:auto; padding:.15rem .65rem; border-left:1px solid var(--line); }
    .agent-event { padding:.62rem .25rem; border-bottom:1px solid var(--line); }
    .agent-event:last-child { border-bottom:0; }
    .agent-event-label { color:var(--forest); font: .62rem var(--mono); letter-spacing:.04em; }
    .agent-event-message { margin:.25rem 0 0; color:var(--ink); font-size:.83rem; line-height:1.45; overflow-wrap:anywhere; }
    .agent-event-reason { margin:.25rem 0 0; color:var(--muted); font-size:.74rem; line-height:1.45; overflow-wrap:anywhere; }
    .agent-event.action .agent-event-label { color:var(--amber); }
    .agent-event.error .agent-event-label { color:var(--coral); }
    .modal-heading { margin:0 0 .3rem; font:500 1.65rem 'Playfair Display', Georgia, serif; }
    .modal-subtitle { color:var(--muted); font-size:.82rem; }
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
      .code-label { color:var(--muted); font: .66rem var(--mono); letter-spacing:.06em; text-transform:uppercase; margin-bottom:.35rem; }
      div[data-testid="stCode"] { border:1px solid var(--line); border-radius:3px; }
      .success-banner { padding:1rem 1.1rem; background:#e2eee6; border-left:4px solid var(--forest); color:#204c39; font-weight:600; }
      .failure-banner { padding:1rem 1.1rem; background:#f7e7e2; border-left:4px solid var(--coral); color:#843c34; font-weight:600; }
      .notice { padding:.85rem 1rem; background:#fff4df; border-left:3px solid var(--amber); color:#6f4a1f; font-size:.85rem; }
      .status-pill { display:inline-flex; align-items:center; gap:.6rem; margin-top:1.1rem; padding:.4rem .7rem; border:1px solid var(--line); background:rgba(255,255,255,.35); border-radius: 999px; color: var(--muted); font: 600 .7rem var(--mono); letter-spacing: .08em; text-transform: uppercase; }
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
    labels = {"pending": "EN ATTENTE", "active": "EN COURS", "done": "TERMINÉ", "error": "ÉCHEC"}
    for index, (key, title, copy) in enumerate(STAGES, start=1):
        state = states.get(key, "pending")
        cards.append(
            f'<div class="stage {state}">'
            f'<div class="stage-no">0{index} / ÉTAPE</div>'
            f'<div class="stage-title">{title}</div>'
            f'<div class="stage-copy">{copy}</div>'
            f'<div class="stage-state">{labels.get(state, "EN ATTENTE")}</div>'
            "</div>"
        )
    return f'<div class="stage-list">{"".join(cards)}</div>'


def render_metrics(values: dict[str, str]) -> str:
    items = (
        ("INCIDENT", values.get("incident", "—")),
        ("PIPELINE", values.get("pipeline", "En attente")),
        ("RÉPARATION", values.get("repair", "En attente")),
        ("MODE", values.get("mode", "Dry-run")),
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
        + node("target", "03 · TARGET", "stg_orders", "Table validée par dbt", status)
        + "</div>"
    )


class EventView:
    def __init__(self, timeline_slot: Any, activity_slot: Any, pipeline_slot: Any | None = None):
        self.timeline_slot = timeline_slot
        self.activity_slot = activity_slot
        self.pipeline_slot = pipeline_slot
        self.states = default_stages()
        self.pipeline_states = default_pipeline_states()
        self.events: list[dict[str, Any]] = []
        self.pipeline = "En attente"
        self.repair = "En attente"

    def _render(self) -> None:
        if self.timeline_slot is not None:
            self.timeline_slot.markdown(render_stages(self.states), unsafe_allow_html=True)
        if self.pipeline_slot is not None:
            self.pipeline_slot.markdown(
                render_pipeline_map(self.pipeline_states),
                unsafe_allow_html=True,
            )
        if self.activity_slot is not None:
            with self.activity_slot.container(height=280, border=False):
                for event in self.events[-12:]:
                    event_type = str(event.get("type", "event"))
                    message = str(event.get("message", ""))
                    action = str(event.get("action", ""))
                    reason = str(event.get("reason", ""))
                    css_class = "action" if action else (
                        "error" if "failed" in event_type else ""
                    )
                    safe_type = html.escape(event_type.replace("_", " ").upper())
                    safe_message = html.escape(message)
                    detail = " · ".join(item for item in (action, reason) if item)
                    safe_detail = html.escape(detail)
                    st.markdown(
                        f'<div class="agent-event {css_class}">'
                        f'<div class="agent-event-label">{safe_type}</div>'
                        f'<p class="agent-event-message">{safe_message}</p>'
                        f'<p class="agent-event-reason">{safe_detail}</p>'
                        "</div>",
                        unsafe_allow_html=True,
                    )

    def on_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        event_type = event.get("type")
        action = event.get("action")
        step = event.get("step")

        if event_type == "pipeline_started":
            self.pipeline = "En cours"
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
            self.pipeline = "Réussi"
            self.states = {key: "done" for key, _, _ in STAGES}
            self.pipeline_states.update(
                source="done", transform="done", target="done"
            )
        elif event_type == "pipeline_failed":
            self.pipeline = "Échec détecté"
            if step == "source":
                self.pipeline_states["source"] = "failed"
            elif step == "dbt test":
                self.pipeline_states["target"] = "failed"
            else:
                self.pipeline_states["transform"] = "failed"
        elif event_type == "repair_started":
            self.states["introspection"] = "done"
            self.states["strategy"] = "active"
            self.repair = "Analyse en cours"
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
            self.repair = "Nouvelle tentative"
        elif event_type == "validation_succeeded":
            self.states["validation"] = "done"
        elif event_type == "repair_succeeded":
            self.states = {key: "done" for key, _, _ in STAGES}
            self.repair = "Validée"
        self._render()


class LiveOutput(io.TextIOBase):
    def __init__(self, output_slot: Any):
        self.output_slot = output_slot
        self.parts: list[str] = []

    def write(self, text: str) -> int:
        if text:
            self.parts.append(text)
            visible = "".join(self.parts)[-MAX_VISIBLE_LOG_CHARS:]
            self.output_slot.code(visible or "En attente des sorties…", language="text")
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
        "error": "" if pipeline_code == 0 or fresh_log else "Échec sans journal récent.",
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
    raw_log_slot = st.empty()
    raw_log_slot.code(log_text[-MAX_VISIBLE_LOG_CHARS:] or "Journal vide", language="text")
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
            error_message = f"Réparation interrompue : {type(error).__name__}: {error}"
            event_view.repair = "Échec"

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
    timeline_slot: Any,
    activity_slot: Any,
    output_slot: Any,
) -> dict[str, Any]:
    presenter = EventView(timeline_slot, activity_slot, pipeline_slot)
    presenter.events = list(state.get("events", []))
    presenter.states = dict(state.get("stages", default_stages()))
    presenter.pipeline_states = default_pipeline_states()
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
            "Validée · pipeline relancé"
            if pipeline_code == 0
            else "Correctif validé · échec à la relance"
        ),
        output=(state.get("output", "") + output.getvalue())[-MAX_VISIBLE_LOG_CHARS:],
    )
    if pipeline_code != 0 and ERROR_LOG_PATH.is_file():
        result["log_text"] = ERROR_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    return result


@st.dialog("Réparation de l’incident", width="large")
def show_agent_dialog() -> None:
    state = st.session_state.get("pipeline_result", {})
    pipeline_slot = st.empty()
    timeline_slot = st.empty()
    activity_slot = st.empty()
    output_slot = st.empty()
    pipeline_slot.markdown(
        render_pipeline_map(state.get("pipeline_states", default_pipeline_states())),
        unsafe_allow_html=True,
    )
    presenter = EventView(timeline_slot, activity_slot, pipeline_slot)
    presenter.events = list(state.get("events", []))
    presenter.pipeline_states = dict(state.get("pipeline_states", default_pipeline_states()))
    presenter.states = dict(state.get("stages", default_stages()))
    presenter.states["introspection"] = "done"
    presenter.states["strategy"] = "active"
    presenter.repair = "Analyse en cours"
    presenter._render()

    st.markdown('<p class="modal-heading">Réparation</p>', unsafe_allow_html=True)
    with st.spinner("Réparation en cours…"):
        result = run_agent_repair(state, presenter, output_slot)
    result["modal_complete"] = True
    st.session_state["pipeline_result"] = result
    st.session_state["agent_dialog_open"] = False
    if result.get("repair_code") == 0 and result.get("promoted"):
        st.session_state["restart_after_repair"] = True
    else:
        st.session_state["pipeline_running"] = False
    st.rerun()


def render_comparison(result: dict[str, Any]) -> None:
    before_files = result.get("before_files", {})
    after_files = result.get("after_files", {})
    changed = [
        path for path, content in after_files.items()
        if path not in before_files or before_files[path] != content
    ]
    if not changed:
        st.info("Aucun patch vérifié n’est disponible pour afficher un diff.")
        return

    for path in changed:
        before = before_files.get(path, "")
        after = after_files[path]
        left, right = st.columns(2)
        with left:
            st.markdown(f'<div class="code-label">AVANT · {html.escape(path)}</div>', unsafe_allow_html=True)
            st.code(before or "(fichier absent)", language=path.rsplit(".", 1)[-1])
        with right:
            st.markdown(f'<div class="code-label">APRÈS · {html.escape(path)}</div>', unsafe_allow_html=True)
            st.code(after, language=path.rsplit(".", 1)[-1])
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"avant/{path}",
                tofile=f"après/{path}",
            )
        )
        with st.expander("Voir le diff", expanded=False):
            st.code(diff or "Aucune différence", language="diff")


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
        spacer, launch_column = st.columns([1, 1])
        with launch_column:
            launch = st.button(
                "Lancer",
                icon=":material/play_arrow:",
                help="Lancer le pipeline",
                type="secondary",
                disabled=bool(st.session_state.get("pipeline_running")),
            )

    state = st.session_state.get("pipeline_result", {})
    last_code = state.get("pipeline_code")
    if last_code is None:
        status_label = "Pipeline opérationnelle"
        status_class = "ok"
    elif last_code == 0:
        status_label = "Dernier run OK"
        status_class = "ok"
    else:
        status_label = "Dernier run en erreur"
        status_class = "issue"
    st.markdown(
        f'<div class="status-pill"><span class="status-dot {status_class}"></span><span>{html.escape(status_label)}</span></div>',
        unsafe_allow_html=True,
    )
    pipeline_slot = st.empty()
    pipeline_slot.markdown(
        render_pipeline_map(
            state.get("pipeline_states", default_pipeline_states()),
            status_class,
        ),
        unsafe_allow_html=True,
    )

    timeline_slot = None
    event_slot = None
    if state.get("events"):
        presenter = EventView(timeline_slot, event_slot, pipeline_slot)
        presenter.events = list(state["events"])
        presenter.pipeline_states = dict(state.get("pipeline_states", default_pipeline_states()))
        presenter.states = dict(state.get("stages", default_stages()))
        presenter._render()

    if state.get("output"):
        with st.expander("Logs", expanded=False):
            st.code(state["output"][-MAX_VISIBLE_LOG_CHARS:], language="text")
    if state.get("log_text") and state.get("pipeline_code") != 0:
        with st.expander("Diagnostic", expanded=False):
            st.code(state["log_text"][-MAX_VISIBLE_LOG_CHARS:], language="text")

    if state.get("repair_code") == 0:
        if state.get("pipeline_code") == 0:
            st.success("Pipeline réparé et relancé.")
        elif not st.session_state.get("restart_after_repair"):
            st.error("Correctif appliqué, mais le pipeline a de nouveau échoué.")
        render_comparison(state)
    elif state.get("pipeline_code") == 0:
        st.success("Pipeline terminé.")
    elif state.get("pipeline_code") not in (None, 0):
        st.error(state.get("error") or "Le pipeline a échoué.")

    if launch:
        event_view = EventView(timeline_slot, event_slot, pipeline_slot)
        output_slot = st.empty()
        st.session_state["pipeline_running"] = True
        with st.spinner("Pipeline en cours…"):
            result = run_pipeline_once(event_view, output_slot)
        result.update(
            repair_code=None,
            repair_status="En attente",
            stages=event_view.states,
            before_files={},
            after_files={},
            promoted=False,
        )
        st.session_state["pipeline_result"] = result
        if result["pipeline_failed"] and result["fresh_log"]:
            st.session_state["agent_dialog_open"] = True
        else:
            st.session_state["pipeline_running"] = False
        st.rerun()

    if st.session_state.get("restart_after_repair"):
        st.session_state["restart_after_repair"] = False
        event_view = EventView(None, None, pipeline_slot)
        output_slot = st.empty()
        with st.spinner("Pipeline relancé…"):
            result = run_promoted_pipeline(
                st.session_state.get("pipeline_result", {}),
                pipeline_slot,
                timeline_slot,
                event_slot,
                output_slot,
            )
        st.session_state["pipeline_result"] = result
        st.session_state["pipeline_running"] = False
        st.rerun()

    if st.session_state.get("agent_dialog_open"):
        show_agent_dialog()


if __name__ == "__main__":
    main()
