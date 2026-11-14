const statusLabel = document.querySelector("#status-label");
const statusDot = document.querySelector("#status-dot");
const eventList = document.querySelector("#event-list");
const runState = document.querySelector("#run-state");
const buttons = ["#run-pipeline", "#repair-dry-run", "#repair-promote"].map((selector) => document.querySelector(selector));
let lastEventId = 0;

const labels = {
  operation_started: "Opération lancée",
  operation_finished: "Opération terminée",
  operation_failed: "Opération en échec",
  pipeline_started: "Pipeline démarré",
  pipeline_step_started: "Étape en cours",
  pipeline_step_succeeded: "Étape réussie",
  pipeline_failed: "Échec du pipeline",
  pipeline_succeeded: "Pipeline réussi",
  repair_started: "Réparation démarrée",
  agent_waiting: "Analyse de l’agent",
  agent_action: "Décision de l’agent",
  validation_started: "Validation démarrée",
  validation_step_started: "Contrôle dbt en cours",
  validation_step_succeeded: "Contrôle dbt réussi",
  validation_failed: "Validation échouée",
  validation_succeeded: "Correctif validé",
  repair_succeeded: "Réparation terminée",
};

function setBusy(isBusy, status = "idle") {
  buttons.forEach((button) => { button.disabled = isBusy; });
  const label = isBusy ? "EN COURS" : status === "failed" ? "ÉCHEC" : status === "succeeded" ? "RÉUSSI" : "EN ATTENTE";
  const stateClass = isBusy ? "running" : status === "failed" ? "failed" : status === "succeeded" ? "succeeded" : "";
  runState.textContent = label;
  runState.className = `run-state${stateClass ? ` ${stateClass}` : ""}`;
}

function classify(event) {
  if (["pipeline_failed", "operation_failed", "validation_failed"].includes(event.type)) return "error";
  if (["pipeline_succeeded", "validation_succeeded", "repair_succeeded", "operation_finished", "pipeline_step_succeeded", "validation_step_succeeded"].includes(event.type)) return "success";
  if (["agent_waiting", "validation_started", "pipeline_step_started", "validation_step_started"].includes(event.type)) return "running";
  return "info";
}

function addEvent(event) {
  if (eventList.querySelector(".empty-state")) eventList.replaceChildren();
  const item = document.createElement("li");
  item.className = `event ${classify(event)}`;
  const time = document.createElement("time");
  time.className = "event-time";
  time.dateTime = event.timestamp || "";
  time.textContent = event.timestamp ? new Date(event.timestamp).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "maintenant";
  const marker = document.createElement("span");
  marker.className = "event-marker";
  const content = document.createElement("div");
  const title = document.createElement("p");
  title.className = "event-title";
  title.textContent = labels[event.type] || event.type;
  content.append(title);
  if (event.action || event.model) {
    const meta = document.createElement("p");
    meta.className = "event-reason";
    meta.textContent = [event.action ? `Action : ${event.action}` : "", event.model || ""].filter(Boolean).join(" · ");
    content.append(meta);
  }
  const reason = document.createElement("p");
  reason.className = "event-reason";
  reason.textContent = event.message || "";
  content.append(reason);
  if (event.reason && event.reason !== event.message) {
    const rationale = document.createElement("p");
    rationale.className = "event-reason";
    rationale.textContent = `Pourquoi : ${event.reason}`;
    content.append(rationale);
  }
  if (event.output || event.error) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Détails techniques";
    const pre = document.createElement("pre");
    pre.className = "event-detail";
    pre.textContent = event.output || event.error;
    details.append(summary, pre);
    content.append(details);
  }
  item.append(time, marker, content);
  eventList.prepend(item);
  while (eventList.children.length > 100) eventList.lastElementChild.remove();
  if (event.id) lastEventId = Math.max(lastEventId, event.id);
  if (event.type === "pipeline_step_started") setFlowStep(event.step, "active", "En cours");
  if (event.type === "pipeline_step_succeeded") setFlowStep(event.step, "succeeded", "Réussi");
  if (event.type === "pipeline_failed") setFlowStep(event.step, "failed", "Échec");
  if (event.type === "pipeline_succeeded") runState.className = "run-state succeeded";
  if (event.type === "repair_started" || event.type === "agent_action") setFlowStep("repair", "active", "En cours");
  if (event.type === "repair_succeeded") setFlowStep("repair", "succeeded", "Validé");
  if (event.type === "validation_failed") setFlowStep("repair", "failed", "Validation en échec");
}

function setFlowStep(step, className, status) {
  const item = document.querySelector(`[data-step="${CSS.escape(step)}"]`);
  if (!item) return;
  item.className = className;
  item.querySelector(".flow-status").textContent = status;
}

function renderOverview(data) {
  const results = data.dbt?.results || [];
  const failed = results.find((result) => ["error", "fail", "failed"].includes(result.status));
  const passed = results.length > 0 && results.every((result) => ["success", "pass", "warn"].includes(result.status));
  const dbtResult = document.querySelector("#dbt-result");
  dbtResult.textContent = failed ? "Échec" : passed ? "Réussi" : "En attente";
  dbtResult.className = failed ? "bad" : passed ? "good" : "";
  document.querySelector("#dbt-time").textContent = data.dbt?.generated_at ? new Date(data.dbt.generated_at).toLocaleString("fr-FR") : "—";
  document.querySelector("#source-rows").textContent = data.source?.row_count ?? "—";
  const invalid = document.querySelector("#invalid-count");
  invalid.textContent = data.source?.invalid_amounts ?? "—";
  invalid.className = Number(data.source?.invalid_amounts) > 0 ? "bad" : "good";

  const errorTitle = document.querySelector("#error-title");
  const errorMessage = document.querySelector("#error-message");
  if (failed) {
    errorTitle.textContent = failed.unique_id || "Échec dbt";
    errorMessage.textContent = failed.message || "dbt a signalé un échec sans détail.";
  } else {
    errorTitle.textContent = "Aucune erreur dbt récente";
    errorMessage.textContent = data.dbt?.error || "Les détails du dernier résultat dbt apparaîtront ici.";
  }

  const tables = document.querySelector("#data-tables");
  tables.replaceChildren();
  if (!data.tables?.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = data.data_error || "Aucune table disponible. Lance le pipeline pour initialiser la source.";
    tables.append(empty);
    return;
  }
  for (const table of data.tables) {
    const section = document.createElement("section");
    const heading = document.createElement("div");
    heading.className = "table-heading";
    const name = document.createElement("span");
    name.textContent = table.name;
    const count = document.createElement("span");
    count.textContent = table.error ? "non disponible" : `${table.count} lignes · aperçu ${table.rows.length}`;
    heading.append(name, count);
    if (table.error) {
      const error = document.createElement("p");
      error.className = "empty-state";
      error.textContent = table.error;
      section.append(heading, error);
      tables.append(section);
      continue;
    }
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    const node = document.createElement("table");
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    table.columns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column;
      headRow.append(th);
    });
    thead.append(headRow);
    const tbody = document.createElement("tbody");
    table.rows.forEach((row) => {
      const tr = document.createElement("tr");
      table.columns.forEach((column) => {
        const td = document.createElement("td");
        td.textContent = row[column] === null ? "NULL" : String(row[column]);
        if (column === "amount" && table.name === "raw_orders" && Number.isNaN(Number(row[column]))) td.className = "invalid";
        tr.append(td);
      });
      tbody.append(tr);
    });
    node.append(thead, tbody);
    wrap.append(node);
    section.append(heading, wrap);
    tables.append(section);
  }
}

async function refreshOverview() {
  try {
    const response = await fetch("/api/overview", { cache: "no-store" });
    renderOverview(await response.json());
  } catch {
    document.querySelector("#data-tables").textContent = "API locale indisponible.";
  }
}

async function refreshState() {
  try {
    const response = await fetch(`/api/state?after=${lastEventId}`, { cache: "no-store" });
    const payload = await response.json();
    payload.events.forEach(addEvent);
    setBusy(payload.state.running, payload.state.status);
    statusLabel.textContent = payload.state.running ? `${payload.state.operation} en cours` : "service connecté";
    statusDot.className = `status-dot${payload.state.running ? " online" : payload.state.status === "failed" ? " failed" : " online"}`;
    if (!payload.state.running && payload.events.length) refreshOverview();
  } catch {
    statusLabel.textContent = "service indisponible";
    statusDot.className = "status-dot failed";
  }
}

async function startOperation(path, payload = {}) {
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Impossible de démarrer l’opération.");
    setBusy(true);
  } catch (error) {
    window.alert(error.message);
    buttons.forEach((button) => { button.disabled = false; });
  }
}

document.querySelector("#run-pipeline").addEventListener("click", () => startOperation("/api/pipeline"));
document.querySelector("#repair-dry-run").addEventListener("click", () => startOperation("/api/repair", { dry_run: true }));
document.querySelector("#repair-promote").addEventListener("click", () => {
  const confirmed = window.confirm("Le SQL validé sera copié dans models/. Continuer ?");
  if (confirmed) startOperation("/api/repair", { dry_run: false, confirm: true });
});
document.querySelector("#refresh-data").addEventListener("click", refreshOverview);
document.querySelector("#clock").textContent = new Date().toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
refreshOverview();
refreshState();
window.setInterval(refreshState, 1200);
window.setInterval(refreshOverview, 8000);