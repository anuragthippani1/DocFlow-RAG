/* DocRAGFlow workspace logic.
   Every backend call, storage key, and behaviour is unchanged from the
   previous single-screen dashboard; only the rendering targets moved into
   the routed views defined in app.html. */

const $ = (id) => document.getElementById(id);

const SUGGESTED_QUESTIONS = [
  "What are the main supply chain risks?",
  "Summarize the key findings.",
  "What actions should we take first?",
];

const AGENTS = [
  { key: "supplier", prefix: "supplier", label: "Supplier Agent" },
  { key: "inventory", prefix: "inventory", label: "Inventory Agent" },
  { key: "logistics", prefix: "logistics", label: "Logistics Agent" },
  { key: "external_risk", prefix: "externalRisk", label: "External Risk Agent" },
];

const HISTORY_KEY = "docflow_query_history";
const MAX_HISTORY = 20;

const state = {
  documents: [],
  statuses: {},
  filter: "all",
  search: "",
  lastPayload: null,
  health: null,
  toastTimer: 0,
};

/* ── Small helpers ─────────────────────────────────────────────────────── */
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function safeJson(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function setStatus(el, message, kind) {
  if (!el) return;
  el.classList.remove("ok", "err");
  if (kind) el.classList.add(kind);
  el.textContent = message || "";
}

function showToast(message, kind, { spinner = false, sticky = false } = {}) {
  const toast = $("uploadStatus");
  if (!toast) return;
  toast.hidden = false;
  toast.classList.remove("ok", "err");
  if (kind) toast.classList.add(kind);
  toast.innerHTML = spinner
    ? `<span class="spinner" aria-hidden="true"></span><span>${escapeHtml(message)}</span>`
    : `<span>${escapeHtml(message)}</span>`;

  clearTimeout(state.toastTimer);
  if (!sticky && !spinner) {
    state.toastTimer = setTimeout(() => {
      toast.hidden = true;
    }, 4200);
  }
}

function normalizeRisk(value) {
  const raw = String(value || "").trim();
  return raw ? raw[0].toUpperCase() + raw.slice(1).toLowerCase() : "";
}

function riskClass(value) {
  const risk = normalizeRisk(value).toLowerCase();
  if (risk === "high") return "high";
  if (risk === "medium") return "medium";
  if (risk === "low") return "low";
  return "skipped";
}

function riskPill(value) {
  const risk = normalizeRisk(value);
  return risk ? `<span class="risk ${riskClass(risk)}">${risk}</span>` : "";
}

function relativeTime(seconds) {
  if (!seconds) return "—";
  const diff = Date.now() - seconds * 1000;
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

function formatUptime(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

/* ── Health, stats, metrics ────────────────────────────────────────────── */
function paintApiStatus(online, data) {
  const version = data?.version ? `v${data.version}` : "";
  const pill = $("apiBasePill");
  if (pill) {
    pill.classList.toggle("online", online);
    pill.classList.toggle("offline", !online);
    pill.textContent = online ? `Online ${version}`.trim() : "API offline";
  }

  const sideStatus = $("sidebarApiStatus");
  if (sideStatus) {
    sideStatus.classList.toggle("online", online);
    sideStatus.classList.toggle("offline", !online);
    sideStatus.textContent = online ? "Online" : "Offline";
  }

  const metric = $("apiStatusMetric");
  if (metric) {
    metric.textContent = online ? "Online" : "Offline";
    metric.className = `stat-value ${online ? "ok" : "bad"}`;
  }

  const indexNote = $("indexNote");
  if (indexNote) {
    indexNote.textContent = online
      ? data?.vector_db_ready
        ? "vector index ready"
        : "vector index empty"
      : "backend unreachable";
  }

  const kbIndex = $("kbIndexState");
  if (kbIndex) {
    kbIndex.textContent = !online ? "Unknown" : data?.vector_db_ready ? "Ready" : "Not built";
    kbIndex.className = `stat-value ${online && data?.vector_db_ready ? "ok" : "warn"}`;
  }

  for (const id of ["kbVersion", "aboutVersion"]) {
    const el = $(id);
    if (el) el.textContent = data?.version || "—";
  }

  for (const id of ["sidebarApiBase", "userMenuApi", "settingsApiBase"]) {
    const el = $(id);
    if (el) el.textContent = API_BASE;
  }
}

async function checkApiHealth() {
  try {
    const res = await apiFetch("/health");
    if (!res.ok) throw new Error(`Health check failed (${res.status})`);
    const data = await safeJson(res);
    state.health = data;
    paintApiStatus(true, data);
  } catch {
    state.health = null;
    paintApiStatus(false, null);
  }
}

async function refreshServerStats() {
  const rate = $("cacheHitRate");
  const note = $("cacheNote");
  try {
    const res = await apiFetch("/stats");
    if (!res.ok) throw new Error("stats unavailable");
    const data = await safeJson(res);
    const total = data?.total_queries ?? 0;
    const hits = data?.cache_hits ?? 0;

    if (rate) {
      rate.textContent = total ? `${Math.round((hits / total) * 100)}%` : "—";
    }
    if (note) {
      note.textContent = total ? `${hits} hits / ${total} server queries` : "no server queries yet";
    }
    const uptime = $("kbUptime");
    if (uptime) uptime.textContent = formatUptime(data?.uptime_seconds);
  } catch {
    if (rate) rate.textContent = "—";
    if (note) note.textContent = "stats unavailable";
  }
}

async function refreshMetrics() {
  const summary = $("metricsPanel");
  const list = $("kbFlags");
  try {
    const res = await apiFetch("/metrics");
    if (!res.ok) throw new Error("metrics unavailable");
    const data = await safeJson(res);

    if (summary) {
      summary.textContent =
        `Hybrid retrieval ${data?.hybrid_retrieval_enabled ? "on" : "off"} · ` +
        `Reranking ${data?.rerank_enabled ? "on" : "off"} · ` +
        `Worker ${data?.celery_enabled ? "on" : "off"} · ` +
        `Cached queries ${data?.cache_size ?? 0}`;
    }

    if (list) {
      const flags = [
        ["Hybrid retrieval", data?.hybrid_retrieval_enabled],
        ["Cross-encoder rerank", data?.rerank_enabled],
        ["Background worker", data?.celery_enabled],
        ["Graph extraction", data?.graph_extraction_enabled],
        ["LangSmith tracing", data?.langsmith_tracing],
      ];
      list.innerHTML = flags
        .map(
          ([label, on]) =>
            `<li><span>${label}</span><span class="${on ? "flag-on" : "flag-off"}">${
              on ? "Enabled" : "Disabled"
            }</span></li>`
        )
        .join("");
    }
  } catch {
    if (summary) summary.textContent = "System metrics unavailable.";
    if (list) list.innerHTML = '<li><span>Metrics unavailable</span></li>';
  }
}

/* ── Documents ─────────────────────────────────────────────────────────── */
function statusMeta(name) {
  const record = state.statuses?.[name];
  const status = String(record?.status || "").toLowerCase();

  if (status === "done") {
    return { key: "indexed", label: "Indexed", cls: "badge--indexed", detail: record?.detail };
  }
  if (status === "processing" || status === "queued") {
    return {
      key: "processing",
      label: record.status,
      cls: "badge--processing",
      detail: record?.detail,
    };
  }
  if (status === "failed") {
    return { key: "failed", label: "Failed", cls: "badge--failed", detail: record?.detail };
  }
  return {
    key: "unknown",
    label: "In library",
    cls: "badge--unknown",
    detail: "No ingestion record for this file",
  };
}

function documentRow(name, { compact = false } = {}) {
  const meta = statusMeta(name);
  const record = state.statuses?.[name];
  const tr = document.createElement("tr");

  tr.innerHTML = `
    <td>
      <div class="doc-cell">
        <span class="pdf-badge" aria-hidden="true">PDF</span>
        <div>
          <div class="doc-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
          ${meta.detail ? `<div class="doc-detail">${escapeHtml(meta.detail)}</div>` : ""}
        </div>
      </div>
    </td>
    <td><span class="type-tag">PDF</span></td>
    <td><span class="badge ${meta.cls}">${escapeHtml(meta.label)}</span></td>
    <td class="cell-muted">${escapeHtml(relativeTime(record?.updated_at))}</td>
    <td class="col-actions">
      <div class="row-actions">
        <button class="row-btn" type="button" data-act="ask" title="Ask about this document" aria-label="Ask about ${escapeHtml(name)}">
          <svg class="ic"><use href="#i-chat" /></svg>
        </button>
        ${
          compact
            ? ""
            : `<button class="row-btn" type="button" data-act="reindex" title="Re-index knowledge base" aria-label="Re-index">
                 <svg class="ic"><use href="#i-refresh" /></svg>
               </button>`
        }
        <button class="row-btn row-btn--danger" type="button" data-act="delete" title="Delete document" aria-label="Delete ${escapeHtml(name)}">
          <svg class="ic"><use href="#i-trash" /></svg>
        </button>
      </div>
    </td>
  `;

  tr.querySelector('[data-act="ask"]').addEventListener("click", () => askAboutDocument(name));
  tr.querySelector('[data-act="reindex"]')?.addEventListener("click", forceReindex);
  tr.querySelector('[data-act="delete"]').addEventListener("click", () => deleteDocument(name));
  return tr;
}

function emptyRow(message, columns = 5) {
  const tr = document.createElement("tr");
  tr.className = "table-empty";
  tr.innerHTML = `<td colspan="${columns}">${escapeHtml(message)}</td>`;
  return tr;
}

function visibleDocuments() {
  const query = state.search.trim().toLowerCase();
  return state.documents.filter((name) => {
    const matchesQuery = !query || name.toLowerCase().includes(query);
    const matchesFilter = state.filter === "all" || statusMeta(name).key === state.filter;
    return matchesQuery && matchesFilter;
  });
}

function renderDocuments() {
  const table = $("docList");
  const recent = $("recentDocs");
  const total = state.documents.length;

  if (table) {
    const rows = visibleDocuments();
    table.innerHTML = "";
    if (!total) {
      table.appendChild(emptyRow("No documents yet. Upload a PDF to build your knowledge base."));
    } else if (!rows.length) {
      table.appendChild(emptyRow("No documents match this search or filter."));
    } else {
      rows.forEach((name) => table.appendChild(documentRow(name)));
    }
  }

  if (recent) {
    recent.innerHTML = "";
    if (!total) {
      recent.appendChild(emptyRow("No documents yet — upload your first PDF."));
    } else {
      state.documents.slice(0, 5).forEach((name) => {
        recent.appendChild(documentRow(name, { compact: true }));
      });
    }
  }

  const shown = visibleDocuments().length;
  const pill = $("docCountPill");
  if (pill) {
    pill.textContent =
      shown === total ? `${total} document${total === 1 ? "" : "s"}` : `${shown} of ${total} shown`;
  }

  const metric = $("docCountMetric");
  if (metric) metric.textContent = String(total);
  const note = $("docCountNote");
  if (note) note.textContent = total ? "in knowledge base" : "nothing indexed yet";
  const sideCount = $("sideDocCount");
  if (sideCount) sideCount.textContent = total ? String(total) : "";
  const kbCount = $("kbDocCount");
  if (kbCount) kbCount.textContent = String(total);
}

async function refreshDocuments() {
  try {
    const res = await apiFetch("/documents");
    if (!res.ok) throw new Error("documents unavailable");
    const data = await safeJson(res);
    state.documents = Array.isArray(data?.documents) ? data.documents : [];
    state.statuses = data?.statuses && typeof data.statuses === "object" ? data.statuses : {};
    AppShell.setDocuments(state.documents);
    renderDocuments();
  } catch {
    state.documents = [];
    state.statuses = {};
    const table = $("docList");
    if (table) {
      table.innerHTML = "";
      table.appendChild(emptyRow("Could not load documents. Check the API connection."));
    }
    const pill = $("docCountPill");
    if (pill) pill.textContent = "Documents unavailable";
  }
}

async function uploadPdf(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast("Only PDF files are supported.", "err");
    return;
  }

  const buttons = [...document.querySelectorAll("[data-upload-trigger]")];
  buttons.forEach((button) => (button.disabled = true));
  showToast(`Uploading ${file.name}…`, null, { spinner: true });

  try {
    const form = new FormData();
    form.append("file", file);
    const res = await apiFetch("/upload", { method: "POST", body: form });
    const data = await safeJson(res);
    if (!res.ok) {
      const detail = data?.detail ? JSON.stringify(data.detail) : JSON.stringify(data);
      throw new Error(detail || `Upload failed (${res.status})`);
    }
    showToast(data?.message || "Upload successful.", "ok");
    await Promise.all([refreshDocuments(), checkApiHealth()]);
  } catch (error) {
    showToast(`Upload error: ${error?.message || error}`, "err", { sticky: true });
  } finally {
    buttons.forEach((button) => (button.disabled = false));
  }
}

async function deleteDocument(filename) {
  if (!confirm(`Delete ${filename} from the index?`)) return;
  showToast(`Deleting ${filename}…`, null, { spinner: true });
  try {
    const res = await apiFetch(`/documents/${encodeURIComponent(filename)}`, { method: "DELETE" });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data?.detail || `Delete failed (${res.status})`);
    showToast(data?.message || "Document deleted.", "ok");
    await Promise.all([refreshDocuments(), checkApiHealth()]);
  } catch (error) {
    showToast(`Delete error: ${error?.message || error}`, "err", { sticky: true });
  }
}

async function forceReindex() {
  const button = $("reindexBtn");
  if (button) button.disabled = true;
  showToast("Rebuilding vector index…", null, { spinner: true });
  try {
    const res = await apiFetch("/documents/reindex", { method: "POST" });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data?.detail || `Re-index failed (${res.status})`);
    showToast(data?.message || "Re-index complete.", "ok");
    await Promise.all([refreshDocuments(), checkApiHealth()]);
  } catch (error) {
    showToast(`Re-index error: ${error?.message || error}`, "err", { sticky: true });
  } finally {
    if (button) button.disabled = false;
  }
}

function askAboutDocument(name) {
  const input = $("chatInput");
  if (input) input.value = `In "${name}", what are the key findings?`;
  AppShell.navigate("chat");
  input?.focus();
}

/* ── Chat ──────────────────────────────────────────────────────────────── */
function chatEmptyState() {
  return (
    '<div class="empty" data-chat-empty>' +
    '<span class="empty-art"><svg class="ic"><use href="#i-chat" /></svg></span>' +
    "<h3>Ask your first question</h3>" +
    "<p>Answers are generated from your indexed documents and include source citations.</p>" +
    "</div>"
  );
}

function ensureChatReady() {
  const log = $("chatMessages");
  if (!log) return null;
  log.querySelector("[data-chat-empty]")?.remove();
  return log;
}

function appendUserBubble(text) {
  const log = ensureChatReady();
  if (!log) return;
  const wrap = document.createElement("div");
  wrap.className = "bubble bubble-user";
  wrap.innerHTML = `<span class="bubble-role">You</span><div class="bubble-text">${escapeHtml(
    text
  )}</div>`;
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

function appendPendingBubble() {
  const log = ensureChatReady();
  if (!log) return;
  const wrap = document.createElement("div");
  wrap.className = "bubble bubble-ai";
  wrap.id = "pendingBubble";
  wrap.innerHTML =
    '<span class="bubble-role">DocRAGFlow</span>' +
    '<div class="chat-skeleton"><span></span><span></span><span></span></div>';
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

function removePendingBubble() {
  $("pendingBubble")?.remove();
}

function appendAnswerBubble(answer, sources, meta) {
  const log = ensureChatReady();
  if (!log) return;

  const wrap = document.createElement("div");
  wrap.className = "bubble bubble-ai";
  const sourceTags = sources.length
    ? `<div class="bubble-sources">${sources
        .map((source) => `<em>${escapeHtml(source)}</em>`)
        .join("")}</div>`
    : "";

  wrap.innerHTML = `
    <span class="bubble-role">DocRAGFlow</span>
    <div class="bubble-text">${escapeHtml(answer)}</div>
    ${sourceTags}
    <div class="bubble-foot">
      <span class="bubble-meta">${escapeHtml(
        [meta.time, meta.cache].filter(Boolean).join(" · ")
      )}</span>
      <div class="bubble-actions">
        <button class="act-btn" type="button" data-act="copy" title="Copy answer">⧉</button>
        <button class="act-btn" type="button" data-act="like" title="Helpful">👍</button>
        <button class="act-btn" type="button" data-act="dislike" title="Not helpful">👎</button>
      </div>
    </div>
  `;

  wrap.querySelector('[data-act="copy"]').addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(answer);
      setStatus($("queryStatus"), "Answer copied.", "ok");
    } catch {
      setStatus($("queryStatus"), "Copy failed.", "err");
    }
  });

  const like = wrap.querySelector('[data-act="like"]');
  const dislike = wrap.querySelector('[data-act="dislike"]');
  like.addEventListener("click", () => {
    like.classList.toggle("is-on");
    dislike.classList.remove("is-on");
  });
  dislike.addEventListener("click", () => {
    dislike.classList.toggle("is-on");
    like.classList.remove("is-on");
  });

  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

function renderSources(sources) {
  const list = $("sourcesList");
  const empty = $("sourcesEmpty");
  if (!list) return;
  list.innerHTML = "";
  for (const source of sources) {
    const li = document.createElement("li");
    li.textContent = source;
    list.appendChild(li);
  }
  if (empty) empty.hidden = sources.length > 0;
}

/* ── Agents + analysis ─────────────────────────────────────────────────── */
function renderAgent(agent, data) {
  const output = data || {};
  const skipped = String(output.reason || "").toLowerCase().includes("skipped");
  const card = document.querySelector(`.agent-card[data-agent="${agent.key}"]`);
  if (card) card.classList.toggle("is-skipped", skipped);

  const badge = $(`${agent.prefix}Risk`);
  if (badge) {
    badge.innerHTML = skipped
      ? '<span class="risk skipped">Skipped</span>'
      : riskPill(output.risk_level);
  }

  const reason = $(`${agent.prefix}Reason`);
  const action = $(`${agent.prefix}Action`);
  if (reason) reason.textContent = output.reason || "No reason returned.";
  if (action) action.textContent = output.recommended_action || "No action returned.";
}

function renderAnalysis(payload) {
  const empty = $("analysisEmpty");
  const content = $("analysisContent");
  if (!payload) {
    if (empty) empty.hidden = false;
    if (content) content.hidden = true;
    return;
  }

  if (empty) empty.hidden = true;
  if (content) content.hidden = false;

  const decision = payload.decision || {};
  const agents = payload.agents || {};

  const risk = $("decisionRisk");
  if (risk) risk.innerHTML = riskPill(decision.final_risk) || '<span class="risk skipped">—</span>';

  const decisionText = $("decisionText");
  const priority = $("priorityAction");
  if (decisionText) decisionText.textContent = decision.final_decision || "No final decision.";
  if (priority) priority.textContent = decision.priority_action || "No priority action.";

  const domain = $("analysisDomain");
  if (domain) {
    const run = Array.isArray(payload.agents_run) ? payload.agents_run.join(", ") : "";
    domain.textContent = run
      ? `${payload.domain || "general"} · agents: ${run}`
      : payload.domain || "general";
  }

  const grid = $("findingGrid");
  if (grid) {
    grid.innerHTML = "";
    for (const agent of AGENTS) {
      const output = agents[agent.key] || {};
      const skipped = String(output.reason || "").toLowerCase().includes("skipped");
      const card = document.createElement("article");
      card.className = "finding";
      card.innerHTML = `
        <header>
          <h3>${agent.label}</h3>
          ${skipped ? '<span class="risk skipped">Skipped</span>' : riskPill(output.risk_level)}
        </header>
        <p class="panel-label">Reason</p>
        <p>${escapeHtml(output.reason || "Not available.")}</p>
        <p class="panel-label">Recommended action</p>
        <p>${escapeHtml(output.recommended_action || "Not available.")}</p>
      `;
      grid.appendChild(card);
    }
  }

  const actions = $("actionList");
  if (actions) {
    actions.innerHTML = "";
    const items = [];
    if (decision.priority_action) items.push(["Priority", decision.priority_action]);
    for (const agent of AGENTS) {
      const output = agents[agent.key];
      const recommended = output?.recommended_action;
      if (!recommended) continue;
      if (String(output.reason || "").toLowerCase().includes("skipped")) continue;
      items.push([agent.label, recommended]);
    }

    if (!items.length) {
      actions.innerHTML = '<li>No recommended actions returned.</li>';
    } else {
      actions.innerHTML = items
        .map(([label, text]) => `<li><strong>${label}:</strong> ${escapeHtml(text)}</li>`)
        .join("");
    }
  }
}

/* ── Session dashboard ─────────────────────────────────────────────────── */
function renderDashboard() {
  const total = $("totalQueries");
  if (total) total.textContent = String(dashboardState.totalQueries);

  const dominant = dominantRisk();
  const level = $("riskLevelMetric");
  if (level) level.textContent = dominant;

  const counts = dashboardState.riskCounts;
  const max = Math.max(1, counts.Low + counts.Medium + counts.High);
  for (const [key, value] of Object.entries(counts)) {
    const row = document.querySelector(`#riskBars li[data-risk="${key.toLowerCase()}"]`);
    if (!row) continue;
    row.querySelector("b").style.width = `${(value / max) * 100}%`;
    row.querySelector("em").textContent = String(value);
  }
}

function updateDashboard(decision) {
  const risk = normalizeRisk(decision?.final_risk) || "Low";
  dashboardState.totalQueries += 1;
  dashboardState.riskCounts[risk] = (dashboardState.riskCounts[risk] || 0) + 1;
  dashboardState.lastRisk = risk;
  renderDashboard();
}

function resetDashboard() {
  dashboardState.totalQueries = 0;
  dashboardState.riskCounts = { Low: 0, Medium: 0, High: 0 };
  dashboardState.lastRisk = "—";
  renderDashboard();
  showToast("Session metrics reset.", "ok");
}

async function clearServerCache() {
  try {
    const res = await apiFetch("/cache/clear", { method: "POST" });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data?.detail || `Clear failed (${res.status})`);
    showToast(data?.message || "Cache cleared.", "ok");
    await refreshServerStats();
    await refreshMetrics();
  } catch (error) {
    showToast(`Cache error: ${error?.message || error}`, "err", { sticky: true });
  }
}

/* ── History ───────────────────────────────────────────────────────────── */
function loadHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveHistory(history) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY)));
}

function addHistoryEntry(question, responseTimeMs, riskLevel, sourceCount) {
  const history = loadHistory();
  history.unshift({
    q: question,
    time: responseTimeMs,
    risk: normalizeRisk(riskLevel),
    sources: sourceCount,
    ts: new Date().toLocaleTimeString(),
  });
  saveHistory(history);
  renderHistory();
}

function renderHistory() {
  const history = loadHistory();
  const table = $("historyList");

  if (table) {
    table.innerHTML = "";
    if (!history.length) {
      table.appendChild(emptyRow("No queries yet. Ask a question to build your history."));
    } else {
      for (const entry of history) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><div class="q-cell" title="${escapeHtml(entry.q)}">${escapeHtml(entry.q)}</div></td>
          <td>${entry.risk ? riskPill(entry.risk) : '<span class="cell-muted">—</span>'}</td>
          <td class="cell-muted">${
            entry.sources ? `${entry.sources} source${entry.sources === 1 ? "" : "s"}` : "—"
          }</td>
          <td class="cell-muted">${escapeHtml(entry.ts || "")}${
            entry.time ? ` · ${entry.time}ms` : ""
          }</td>
          <td class="col-actions">
            <div class="row-actions">
              <button class="row-btn" type="button" data-act="reopen" title="Reopen in chat" aria-label="Reopen query">
                <svg class="ic"><use href="#i-send" /></svg>
              </button>
            </div>
          </td>
        `;
        tr.querySelector('[data-act="reopen"]').addEventListener("click", () => {
          const input = $("chatInput");
          if (input) input.value = entry.q;
          AppShell.navigate("chat");
          input?.focus();
        });
        table.appendChild(tr);
      }
    }
  }

  const rail = $("chatSessions");
  if (rail) {
    rail.innerHTML = "";
    if (!history.length) {
      const li = document.createElement("li");
      li.className = "rail-meta";
      li.textContent = "No conversations yet.";
      rail.appendChild(li);
      return;
    }
    for (const entry of history.slice(0, 10)) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.innerHTML =
        `<span class="rail-q">${escapeHtml(entry.q)}</span>` +
        `<span class="rail-meta">${escapeHtml(entry.ts || "")}${
          entry.risk ? ` · ${entry.risk}` : ""
        }</span>`;
      button.addEventListener("click", () => {
        const input = $("chatInput");
        if (input) input.value = entry.q;
        input?.focus();
      });
      li.appendChild(button);
      rail.appendChild(li);
    }
  }
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
  showToast("Query history cleared.", "ok");
}

/* ── Query pipeline ────────────────────────────────────────────────────── */
function renderResult(payload) {
  state.lastPayload = payload;

  const answer = (payload?.answer ?? "").trim().replace(/\n{3,}/g, "\n\n");
  const agents = payload?.agents ?? {};
  const sources = Array.from(new Set((payload?.sources ?? []).filter(Boolean)));

  const answerText = $("answerText");
  if (answerText) answerText.textContent = answer;

  const mode = $("queryModePill");
  if (mode) {
    const run = Array.isArray(payload?.agents_run) ? payload.agents_run.length : 0;
    mode.textContent = `${payload?.domain || "general"} · ${run} agent${run === 1 ? "" : "s"}`;
  }

  renderSources(sources);
  for (const agent of AGENTS) renderAgent(agent, agents[agent.key]);
  renderAnalysis(payload);
  updateDashboard(payload?.decision);

  return { answer, sources };
}

async function askQuestion(inputId) {
  const input = $(inputId) || $("chatInput");
  const question = (input?.value || "").trim();
  const status = $("queryStatus");
  const buttons = [$("askBtn"), $("chatSendBtn")].filter(Boolean);

  if (!question) {
    setStatus(status, "Please type a question.", "err");
    input?.focus();
    return;
  }

  AppShell.navigate("chat");
  appendUserBubble(question);
  appendPendingBubble();
  setStatus(status, "Retrieving context and running agents…");
  buttons.forEach((button) => (button.disabled = true));

  const startedAt = performance.now();

  try {
    const res = await apiFetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    const elapsedMs = Math.round(performance.now() - startedAt);
    const serverTime = res.headers.get("X-Response-Time") || "";
    const cacheStatus = res.headers.get("X-Cache");
    const data = await safeJson(res);

    if (!res.ok) {
      if (res.status === 503 && data?.error) throw new Error(data.error);
      const detail = data?.detail ? JSON.stringify(data.detail) : JSON.stringify(data);
      throw new Error(detail || data?.error || `Query failed (${res.status})`);
    }

    const { answer, sources } = renderResult(data);
    const timeLabel = serverTime ? `Server ${serverTime}` : `${elapsedMs}ms`;
    const cacheLabel = cacheStatus === "HIT" ? "Cached" : cacheStatus === "MISS" ? "Fresh" : "";

    removePendingBubble();
    appendAnswerBubble(answer || "No answer returned.", sources, {
      time: timeLabel,
      cache: cacheLabel,
    });

    const responseTime = $("responseTime");
    const cacheIndicator = $("cacheIndicator");
    const meta = $("responseMeta");
    if (responseTime) responseTime.textContent = timeLabel;
    if (cacheIndicator) cacheIndicator.textContent = cacheLabel;
    if (meta) meta.hidden = false;

    addHistoryEntry(question, elapsedMs, data?.decision?.final_risk, sources.length);
    setStatus(status, "Done.", "ok");
    if (input) input.value = "";
    const other = $("questionInput");
    if (other && other !== input) other.value = "";
    await refreshServerStats();
  } catch (error) {
    removePendingBubble();
    const message = error?.message || String(error);
    setStatus(status, `Error: ${message}`, "err");
    appendAnswerBubble(`Sorry — this question could not be answered: ${message}`, [], {
      time: "",
      cache: "",
    });
  } finally {
    buttons.forEach((button) => (button.disabled = false));
  }
}

/* ── Settings ──────────────────────────────────────────────────────────── */
function paintKeyState() {
  const label = $("settingsKeyState");
  if (label) label.textContent = getApiKey() ? "Saved in this browser" : "Not set";
}

function initSettings() {
  const urlInput = $("apiUrlInput");
  const keyInput = $("apiKeyInput");
  if (urlInput) urlInput.value = API_BASE;
  if (keyInput) keyInput.value = getApiKey();
  paintKeyState();

  $("saveApiUrlBtn")?.addEventListener("click", async () => {
    setApiBase(urlInput.value.trim());
    urlInput.value = API_BASE;
    showToast("API URL saved.", "ok");
    await Promise.all([checkApiHealth(), refreshDocuments(), refreshServerStats(), refreshMetrics()]);
  });

  $("saveApiKeyBtn")?.addEventListener("click", async () => {
    localStorage.setItem(API_KEY_STORAGE, keyInput.value.trim());
    paintKeyState();
    showToast("API key saved.", "ok");
    await Promise.all([checkApiHealth(), refreshDocuments()]);
  });

  $("toggleKeyBtn")?.addEventListener("click", (event) => {
    const button = event.currentTarget;
    const shown = keyInput.type === "text";
    keyInput.type = shown ? "password" : "text";
    button.textContent = shown ? "Show" : "Hide";
    button.setAttribute("aria-pressed", String(!shown));
  });
}

/* ── Suggestions ───────────────────────────────────────────────────────── */
function initSuggestions() {
  const container = $("suggestions");
  if (!container) return;
  container.innerHTML = "";
  for (const question of SUGGESTED_QUESTIONS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = question;
    chip.addEventListener("click", () => {
      const input = $("questionInput");
      if (input) input.value = question;
      askQuestion("questionInput");
    });
    container.appendChild(chip);
  }
}

function initGreeting() {
  const greeting = $("greeting");
  if (!greeting) return;
  const hour = new Date().getHours();
  const part = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  greeting.textContent = part;
}

/* ── Boot ──────────────────────────────────────────────────────────────── */
function initApp() {
  initGreeting();
  initSuggestions();
  initSettings();

  const log = $("chatMessages");
  if (log && !log.children.length) log.innerHTML = chatEmptyState();

  for (const trigger of document.querySelectorAll("[data-upload-trigger]")) {
    trigger.addEventListener("click", () => $("pdfFile")?.click());
  }

  $("pdfFile")?.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) uploadPdf(file);
    event.target.value = "";
  });

  $("reindexBtn")?.addEventListener("click", forceReindex);
  $("askBtn")?.addEventListener("click", () => askQuestion("questionInput"));
  $("chatSendBtn")?.addEventListener("click", () => askQuestion("chatInput"));
  $("resetDashboardBtn")?.addEventListener("click", resetDashboard);
  $("clearCacheBtn")?.addEventListener("click", clearServerCache);
  $("clearHistoryBtn")?.addEventListener("click", clearHistory);

  $("questionInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") askQuestion("questionInput");
  });
  $("chatInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") askQuestion("chatInput");
  });

  $("newChatBtn")?.addEventListener("click", () => {
    const chatLog = $("chatMessages");
    if (chatLog) chatLog.innerHTML = chatEmptyState();
    renderSources([]);
    const meta = $("responseMeta");
    if (meta) meta.hidden = true;
    setStatus($("queryStatus"), "");
    $("chatInput")?.focus();
  });

  $("docSearch")?.addEventListener("input", (event) => {
    state.search = event.target.value;
    renderDocuments();
  });

  for (const button of document.querySelectorAll("[data-doc-filter]")) {
    button.addEventListener("click", () => {
      state.filter = button.dataset.docFilter;
      for (const other of document.querySelectorAll("[data-doc-filter]")) {
        const active = other === button;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", String(active));
      }
      renderDocuments();
    });
  }

  AppShell.onEnter("documents", refreshDocuments);
  AppShell.onEnter("overview", () => {
    refreshDocuments();
    refreshServerStats();
  });
  AppShell.onEnter("knowledge", () => {
    checkApiHealth();
    refreshServerStats();
    refreshMetrics();
  });
  AppShell.onEnter("settings", () => {
    const urlInput = $("apiUrlInput");
    if (urlInput) urlInput.value = API_BASE;
    paintKeyState();
    refreshMetrics();
  });
  AppShell.onEnter("history", renderHistory);
  AppShell.onEnter("analysis", () => renderAnalysis(state.lastPayload));
  AppShell.onEnter("chat", () => $("chatInput")?.focus());

  AppShell.start();

  renderDashboard();
  renderHistory();
  renderAnalysis(null);
  renderSources([]);
  checkApiHealth();
  refreshDocuments();
  refreshServerStats();
  refreshMetrics();
  setInterval(checkApiHealth, 30000);
}

document.addEventListener("DOMContentLoaded", initApp);
