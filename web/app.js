const ICONS = {
  intake: '<path d="M4 4h16v10l-3 6H7l-3-6V4z"/><path d="M4 14h4l2 3h4l2-3h4"/>',
  watchlist: '<path d="M12 2 4 5v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V5z"/>',
  compliance: '<rect x="6" y="4" width="12" height="16" rx="2"/><path d="M9 4V2h6v2"/><path d="m9 12 2 2 4-4"/>',
  risk: '<path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15 16 11"/><circle cx="12" cy="15" r="1.2"/>',
  alert: '<path d="M6 10a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  report: '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h6"/>',
};

const STEPS = [
  { id: "intake", label: "Payment Ingestion" },
  { id: "watchlist", label: "Sanctions &amp; Watchlist Screening" },
  { id: "compliance", label: "AML Rule Evaluation" },
  { id: "risk", label: "Composite Risk Rating" },
  { id: "alert", label: "Alert Escalation" },
  { id: "report", label: "Case Disposition" },
];

const pipelineEl = document.getElementById("pipeline");
const resultsEl = document.getElementById("results");
const txnListEl = document.getElementById("txn-list");
const pipelineTitle = document.getElementById("pipeline-title");
const pipelineSubtitle = document.getElementById("pipeline-subtitle");
const statusText = document.getElementById("status-text");

let currentSource = null;
let currentRun = 0;
let transactions = [];

function svgIcon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
}

function flagEmoji(cc) {
  if (!cc || cc.length !== 2) return "";
  const points = [...cc.toUpperCase()].map((c) => 127397 + c.charCodeAt(0));
  return String.fromCodePoint(...points);
}

// Built-in ISO 3166-1 alpha-2 -> display name, so there is no country
// table to keep in sync with config.py. Older browsers fall back to the code.
const REGION_NAMES = (() => {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" });
  } catch {
    return null;
  }
})();

function countryName(cc) {
  if (!cc || cc.length !== 2) return "";
  const code = cc.toUpperCase();
  if (!REGION_NAMES) return code;
  try {
    const name = REGION_NAMES.of(code);
    // Unassigned codes come back as the code itself; "ZZ" resolves to the
    // literal "Unknown Region", which reads worse than the raw code.
    return !name || name === "Unknown Region" ? code : name;
  } catch {
    return code;
  }
}

// Flag + full country name, e.g. "\u{1F1E9}\u{1F1EA} Germany".
function countryLabel(cc) {
  const flag = flagEmoji(cc);
  const name = countryName(cc);
  return flag ? `${flag} ${name}` : name;
}

function money(amount, currency) {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
  } catch (e) {
    return `${amount.toLocaleString()} ${currency}`;
  }
}

function buildPipeline() {
  pipelineEl.innerHTML = "";
  STEPS.forEach((step, i) => {
    const node = document.createElement("div");
    node.className = "pnode";
    node.id = `pnode-${step.id}`;
    node.innerHTML = `
      <div class="pnode-body">
        <div class="pnode-circle">${svgIcon(step.id)}</div>
        <div class="pnode-label">${step.label}</div>
        <div class="pnode-sub" id="pnode-sub-${step.id}"></div>
      </div>`;
    pipelineEl.appendChild(node);
    if (i < STEPS.length - 1) {
      const connector = document.createElement("div");
      connector.className = "pconnector";
      pipelineEl.appendChild(connector);
    }
  });
}

function resetPipeline() {
  STEPS.forEach((step) => {
    const node = document.getElementById(`pnode-${step.id}`);
    node.className = "pnode";
    document.getElementById(`pnode-sub-${step.id}`).textContent = "";
  });
  document.querySelectorAll(".pconnector").forEach((c) => (c.style.background = ""));
  resultsEl.innerHTML = "";
}

function setNodeState(stepId, state, sub) {
  const node = document.getElementById(`pnode-${stepId}`);
  node.className = `pnode ${state}`;
  document.getElementById(`pnode-sub-${stepId}`).textContent = sub || "";
}

async function loadTransactions() {
  let res;
  try {
    res = await fetch("/api/transactions");
  } catch (e) {
    txnListEl.innerHTML = `<div class="txn-error">Could not reach the server. Make sure you opened this page as <strong>http://127.0.0.1:5057/</strong> (not as a local file) and that <code>python3 server.py</code> is still running.</div>`;
    statusText.textContent = "Server unreachable.";
    return;
  }
  if (!res.ok) {
    txnListEl.innerHTML = `<div class="txn-error">Server responded with an error (HTTP ${res.status}) while loading transactions.</div>`;
    statusText.textContent = `Error loading transactions (${res.status}).`;
    return;
  }
  transactions = await res.json();
  txnListEl.innerHTML = "";
  transactions.forEach((t) => {
    const card = document.createElement("button");
    card.className = "txn-card";
    card.id = `txn-${t.transaction_id}`;
    card.innerHTML = `
      <div class="txn-card-row1">
        <span>${t.sender}</span>
        <span class="txn-amount">${money(t.amount, t.currency)}</span>
      </div>
      <div class="txn-card-row2">
        <span>${countryLabel(t.sender_country)} → ${countryLabel(t.beneficiary_country)}</span>
        <span class="txn-type">${t.type}</span>
      </div>`;
    card.addEventListener("click", () => runInvestigation(t));
    txnListEl.appendChild(card);
  });
}

function runInvestigation(txn) {
  if (currentSource) {
    currentSource.close();
    currentSource = null;
  }
  document.querySelectorAll(".txn-card").forEach((c) => c.classList.remove("active", "running"));
  const card = document.getElementById(`txn-${txn.transaction_id}`);
  card.classList.add("active", "running");

  resetPipeline();
  pipelineTitle.textContent = `Investigating ${txn.sender} → ${txn.beneficiary}`;
  pipelineSubtitle.textContent = `${money(txn.amount, txn.currency)} · ${countryLabel(txn.sender_country)} → ${countryLabel(txn.beneficiary_country)} · ${txn.type}`;
  statusText.textContent = `Running pipeline for ${txn.transaction_id}…`;

  setNodeState(STEPS[0].id, "active");

  const runId = ++currentRun;
  const source = new EventSource(`/api/investigate/${txn.transaction_id}`);
  currentSource = source;

  source.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    handleEvent(event, runId);
    if (event.step === "report") {
      source.close();
      currentSource = null;
      card.classList.remove("running");
      statusText.textContent = `Investigation complete — ${txn.transaction_id}`;
    }
  };

  source.onerror = () => {
    if (runId !== currentRun) return;
    statusText.textContent = "Connection lost.";
    source.close();
    currentSource = null;
    card.classList.remove("running");
  };
}

function handleEvent(event, runId) {
  if (runId !== currentRun) return;
  const nextIndex = STEPS.findIndex((s) => s.id === event.step) + 1;
  if (nextIndex < STEPS.length) {
    setNodeState(STEPS[nextIndex].id, "active");
  }
  setTimeout(() => {
    if (runId === currentRun) applyEvent(event);
  }, 420);
}

function applyEvent(event) {
  switch (event.step) {
    case "intake": return renderIntake(event.data);
    case "watchlist": return renderWatchlist(event.data);
    case "compliance": return renderCompliance(event.data);
    case "risk": return renderRisk(event.data);
    case "alert": return renderAlert(event);
    case "report": return renderReport(event.data);
  }
}

function addCard(html) {
  const wrap = document.createElement("div");
  wrap.innerHTML = html;
  resultsEl.appendChild(wrap.firstElementChild);
}

function renderIntake(d) {
  setNodeState("intake", "clear", "RECEIVED");
  addCard(`
    <div class="card">
      <div class="card-head"><h3>${svgIcon("intake")} Payment Ingestion</h3><span class="badge badge-blue">${d.transaction_id}</span></div>
      <div class="intake-row">
        <span class="intake-amount">${money(d.amount, d.currency)}</span>
        <span class="intake-arrow">·</span>
        <span>${d.sender} (${countryLabel(d.sender_country)})</span>
        <span class="intake-arrow">→</span>
        <span>${d.beneficiary} (${countryLabel(d.beneficiary_country)})</span>
        <span class="badge badge-dim">${d.type}</span>
      </div>
    </div>`);
}

function renderWatchlist(d) {
  const hit = d.screening_status === "HIT";
  setNodeState("watchlist", hit ? "hit" : "clear", hit ? `${d.total_hits} HIT` : "CLEAR");

  let body;
  if (!hit) {
    body = `<p class="summary-text">No matches against the global criminal watchlist (OFAC, EU Sanctions, FBI, Interpol, BaFin Watch, UN Security Council).</p>`;
  } else {
    const items = d.watchlist_hits.map((h) => `
      <li class="hit-item">
        <div class="hit-item-name">⚠ ${h.matched_name} <span class="badge badge-red" style="margin-left:6px;">${h.risk_level}</span></div>
        <div class="hit-item-meta">${h.category} · match confidence ${h.match_score}% · nationality: ${h.nationality}</div>
        <div class="sanction-tags">${(h.sanctions || []).map((s) => `<span class="sanction-tag">${s}</span>`).join("")}</div>
      </li>`).join("");
    body = `<ul class="hit-list">${items}</ul>`;
  }

  addCard(`
    <div class="card ${hit ? "card-hit" : "card-clear"}">
      <div class="card-head"><h3>${svgIcon("watchlist")} Sanctions &amp; Watchlist Screening</h3><span class="badge ${hit ? "badge-red" : "badge-green"}">${hit ? "🔴 HIT" : "🟢 CLEAR"}</span></div>
      ${body}
    </div>`);
}

function renderCompliance(d) {
  const sevClass = { CRITICAL: "hit", HIGH: "hit", MEDIUM: "warn", NONE: "clear" }[d.highest_severity] || "clear";
  setNodeState("compliance", sevClass, d.total_issues > 0 ? `${d.total_issues} ISSUE${d.total_issues > 1 ? "S" : ""}` : "CLEAR");

  const issues = d.compliance_issues.length
    ? d.compliance_issues.map((i) => `<li class="issue-item sev-${i.severity.toLowerCase()}"><span class="issue-rule">${i.rule}</span>${i.description}</li>`).join("")
    : `<li class="issue-item">No regulatory issues triggered.</li>`;

  const badgeClass = sevClass === "hit" ? "badge-red" : sevClass === "warn" ? "badge-amber" : "badge-green";

  addCard(`
    <div class="card ${sevClass === "hit" ? "card-hit" : sevClass === "warn" ? "card-warn" : ""}">
      <div class="card-head"><h3>${svgIcon("compliance")} AML Rule Evaluation</h3><span class="badge ${badgeClass}">${d.highest_severity}</span></div>
      <p class="summary-text" style="margin-top:0;">≈ ${money(d.eur_equivalent, "EUR")} · ${countryLabel(d.sender_country)} ${d.sender_high_risk ? "(high-risk)" : ""} → ${countryLabel(d.beneficiary_country)} ${d.beneficiary_high_risk ? "(high-risk)" : ""}</p>
      <ul class="issue-list">${issues}</ul>
    </div>`);
}

function renderRisk(d) {
  const sevClass = { CRITICAL: "hit", HIGH: "hit", MEDIUM: "warn", LOW: "clear", MINIMAL: "clear" }[d.risk_level] || "clear";
  setNodeState("risk", sevClass, `${d.risk_score}/100`);

  const color = { CRITICAL: "var(--red)", HIGH: "var(--red)", MEDIUM: "var(--amber)", LOW: "var(--accent)", MINIMAL: "var(--green)" }[d.risk_level] || "var(--green)";
  const r = 46, c = 2 * Math.PI * r;
  const offset = c - (d.risk_score / 100) * c;
  const badgeClass = sevClass === "hit" ? "badge-red" : sevClass === "warn" ? "badge-amber" : "badge-green";

  const factors = d.risk_factors.length
    ? d.risk_factors.map((f) => `<li class="factor-item">${f}</li>`).join("")
    : `<li class="factor-item">No elevated risk factors identified.</li>`;

  addCard(`
    <div class="card ${sevClass === "hit" ? "card-hit" : sevClass === "warn" ? "card-warn" : ""}">
      <div class="card-head"><h3>${svgIcon("risk")} Composite Risk Rating</h3><span class="badge ${badgeClass}">${d.risk_level}</span></div>
      <div class="risk-layout">
        <svg viewBox="0 0 120 120" class="gauge">
          <circle cx="60" cy="60" r="${r}" class="gauge-bg"/>
          <circle cx="60" cy="60" r="${r}" class="gauge-fg" style="stroke:${color}; stroke-dasharray:${c}; stroke-dashoffset:${offset}"/>
          <text x="60" y="58" class="gauge-score">${d.risk_score}</text>
          <text x="60" y="76" class="gauge-max">/ 100</text>
        </svg>
        <ul class="factor-list">${factors}</ul>
      </div>
    </div>`);
}

function renderAlert(event) {
  if (event.status === "skipped") {
    setNodeState("alert", "clear", "NOT REQUIRED");
    addCard(`
      <div class="card card-clear">
        <div class="card-head"><h3>${svgIcon("alert")} Alert Escalation</h3><span class="badge badge-green">🟢 NOT REQUIRED</span></div>
        <p class="summary-text">Risk below threshold and no watchlist hit — no escalation to top management needed.</p>
      </div>`);
    return;
  }

  const d = event.data;
  setNodeState("alert", "hit", `SENT · ${d.priority}`);
  addCard(`
    <div class="card card-hit">
      <div class="card-head"><h3>${svgIcon("alert")} Alert Escalation</h3><span class="badge badge-red">🔴 DISPATCHED · ${d.priority}</span></div>
      <div class="alert-subject">${d.subject || ""}</div>
      <div class="alert-meta-grid">
        <div><span>Alert ID</span>${d.alert_id || "N/A"}</div>
        <div><span>Timestamp</span>${(d.timestamp || "").replace("T", " ").slice(0, 19)}</div>
      </div>
      <div class="recipients">${(d.recipients || []).map((r) => `✓ ${r}`).join("<br/>")}</div>
      <div class="recommended-action"><strong>Recommended action:</strong> ${d.recommended_action || "N/A"}</div>
    </div>`);
}

function renderReport(d) {
  setNodeState("report", "clear", "COMPLETE");

  const obligations = (d.regulatory_obligations || []).map((o) => `<li class="oblig-item">${o}</li>`).join("");

  addCard(`
    <div class="card">
      <div class="card-head">
        <h3>${svgIcon("report")} Case Disposition</h3>
        <span class="badge badge-blue">${d.fraud_pattern}</span>
      </div>
      <p class="summary-text">${d.investigator_summary}</p>
      ${obligations ? `<ul class="oblig-list">${obligations}</ul>` : ""}
      ${d.bafin_sar_required ? `<div class="recommended-action" style="margin-top:10px;">📋 BaFin SAR filing required within 24h.</div>` : ""}
      <div class="confidence-row">
        <span>Confidence</span>
        <div class="confidence-bar"><div class="confidence-fill" style="width:${d.confidence}%"></div></div>
        <span>${d.confidence}/100</span>
      </div>
    </div>`);
}

function setupInfoToggle() {
  const panel = document.getElementById("info-panel");
  const toggle = document.getElementById("info-toggle");
  let collapsed = false;
  try {
    collapsed = localStorage.getItem("fraudDemoInfoCollapsed") === "1";
  } catch (e) {}
  if (collapsed) {
    panel.classList.add("collapsed");
    toggle.textContent = "Show";
    toggle.setAttribute("aria-expanded", "false");
  }
  toggle.addEventListener("click", () => {
    const nowCollapsed = panel.classList.toggle("collapsed");
    toggle.textContent = nowCollapsed ? "Show" : "Hide";
    toggle.setAttribute("aria-expanded", String(!nowCollapsed));
    try {
      localStorage.setItem("fraudDemoInfoCollapsed", nowCollapsed ? "1" : "0");
    } catch (e) {}
  });
}

buildPipeline();
loadTransactions();
setupInfoToggle();
