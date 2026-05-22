const $ = (id) => document.getElementById(id);

const SUGGESTED_QUESTIONS = [
  "What are the main supply chain risks?",
  "Summarize key findings from the documents.",
  "What actions should we take first?",
];

const HISTORY_KEY = "docflow_query_history";
const MAX_HISTORY = 20;

let lastAnswerText = "";

function setStatus(el, message, kind) {
  if (!el) return;
  el.classList.remove("ok", "err");
  if (kind) el.classList.add(kind);
  el.textContent = message || "";
}

async function safeJson(res) {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function setLoading(button, isLoading, label) {
  if (!button) return;
  button.disabled = isLoading;
  if (button.id === "askBtn") return;
  button.textContent = isLoading ? "Processing..." : label;
}

function setProcessing(el, message) {
  if (!el) return;
  el.classList.remove("ok", "err");
  el.innerHTML = `<span class="spinner" aria-hidden="true"></span>${message || "Processing..."}`;
}

function normalizeRisk(value) {
  const raw = String(value || "").trim();
  return raw ? raw[0].toUpperCase() + raw.slice(1).toLowerCase() : "";
}

function riskClass(value) {
  const risk = normalizeRisk(value).toLowerCase();
  if (risk === "high") return "high";
  if (risk === "medium") return "medium";
  return "low";
}

function setRiskBadge(id, value) {
  const el = $(id);
  if (!el) return;
  const risk = normalizeRisk(value);
  el.innerHTML = risk ? `<span class="risk ${riskClass(risk)}">${risk}</span>` : "";
}

function updateDashboard(decision) {
  const risk = normalizeRisk(decision?.final_risk) || "Low";
  dashboardState.totalQueries += 1;
  dashboardState.riskCounts[risk] = (dashboardState.riskCounts[risk] || 0) + 1;
  dashboardState.lastRisk = risk;
  renderDashboard();
}

function renderDashboard() {
  $("totalQueries").textContent = String(dashboardState.totalQueries);

  const riskEl = $("riskLevelMetric");
  const dominant = dominantRisk();
  if (riskEl) {
    riskEl.textContent = dominant;
    riskEl.className = `metric-value ${dominant !== "—" ? riskClass(dominant) : ""}`;
  }

  const low = $("lowRiskCount");
  const med = $("mediumRiskCount");
  const high = $("highRiskCount");
  if (low) low.textContent = String(dashboardState.riskCounts.Low);
  if (med) med.textContent = String(dashboardState.riskCounts.Medium);
  if (high) high.textContent = String(dashboardState.riskCounts.High);
}

function resetDashboard() {
  dashboardState.totalQueries = 0;
  dashboardState.riskCounts = { Low: 0, Medium: 0, High: 0 };
  dashboardState.lastRisk = "—";
  renderDashboard();
  setStatus($("queryStatus"), "Dashboard reset.", "ok");
}

function updateApiStatusMetric(online, version = "") {
  const el = $("apiStatusMetric");
  if (!el) return;
  el.textContent = online ? `Online${version ? " v" + version : ""}` : "Offline";
  el.className = `metric-value ${online ? "low" : "high"}`;
}

async function checkApiHealth() {
  const pill = $("apiBasePill");
  if (!pill) return;
  pill.classList.remove("online", "offline");
  pill.textContent = "Checking API…";

  try {
    const res = await apiFetch("/health");
    if (!res.ok) throw new Error(`Health check failed (${res.status})`);
    const data = await safeJson(res);
    const version = data?.version ? ` v${data.version}` : "";
    const dbNote = data?.vector_db_ready === false ? " · No index" : "";
    pill.classList.add("online");
    pill.textContent = `Online${version}${dbNote}`;
    updateApiStatusMetric(true, data?.version || "");
  } catch {
    pill.classList.add("offline");
    pill.textContent = "API offline";
    updateApiStatusMetric(false);
  }
}

async function refreshMetrics() {
  const panel = $("metricsPanel");
  if (!panel) return;
  try {
    const res = await apiFetch("/metrics");
    if (!res.ok) throw new Error("metrics unavailable");
    const data = await safeJson(res);
    panel.textContent =
      `Hybrid ${data?.hybrid_retrieval_enabled ? "on" : "off"} · ` +
      `Rerank ${data?.rerank_enabled ? "on" : "off"} · ` +
      `Worker ${data?.celery_enabled ? "on" : "off"}`;
  } catch {
    panel.textContent = "Metrics unavailable.";
  }
}

async function refreshServerStats() {
  const el = $("cacheHitRate");
  if (!el) return;
  try {
    const res = await apiFetch("/stats");
    if (!res.ok) throw new Error("stats unavailable");
    const data = await safeJson(res);
    const total = data?.total_queries ?? 0;
    const hits = data?.cache_hits ?? 0;
    if (!total) {
      el.textContent = "—";
      return;
    }
    const pct = Math.round((hits / total) * 100);
    el.textContent = `${pct}%`;
    el.title = `${hits} hits / ${total} queries`;
  } catch {
    el.textContent = "—";
  }
}

async function clearServerCache() {
  const status = $("queryStatus");
  try {
    const res = await apiFetch("/cache/clear", { method: "POST" });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data?.detail || `Clear failed (${res.status})`);
    setStatus(status, data?.message || "Cache cleared.", "ok");
    await refreshServerStats();
  } catch (e) {
    setStatus(status, `Cache error: ${e?.message || e}`, "err");
  }
}

function formatDocSize(name) {
  return "PDF document";
}

async function refreshDocuments() {
  const pill = $("docCountPill");
  const list = $("docList");
  if (!list) return;

  try {
    const res = await apiFetch("/documents");
    if (!res.ok) throw new Error("documents unavailable");
    const data = await safeJson(res);
    const docs = Array.isArray(data?.documents) ? data.documents : [];
    const count = data?.count ?? docs.length;
    if (pill) pill.textContent = count === 1 ? "1 document indexed" : `${count} documents indexed`;

    list.innerHTML = "";
    if (!docs.length) {
      list.innerHTML = '<li class="doc-empty">No PDFs uploaded yet.</li>';
      return;
    }

    for (const name of docs) {
      const li = document.createElement("li");
      li.className = "doc-card";
      li.innerHTML = `
        <div class="doc-icon">PDF</div>
        <div class="doc-info">
          <div class="doc-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
          <div class="doc-size">${formatDocSize(name)}</div>
        </div>
        <button type="button" class="doc-delete" aria-label="Delete ${escapeHtml(name)}">✕</button>
      `;
      li.querySelector(".doc-delete").addEventListener("click", (e) => {
        e.stopPropagation();
        deleteDocument(name);
      });
      list.appendChild(li);
    }
  } catch {
    if (pill) pill.textContent = "Documents unavailable";
    list.innerHTML = '<li class="doc-empty">Could not load documents.</li>';
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function initSuggestions() {
  const container = $("suggestions");
  if (!container) return;
  container.innerHTML = "";
  for (const q of SUGGESTED_QUESTIONS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "suggestion-chip";
    chip.textContent = q;
    chip.addEventListener("click", () => {
      $("questionInput").value = q;
      $("questionInput").focus();
    });
    container.appendChild(chip);
  }
}

function renderAgent(agentKey, prefix, data) {
  const agent = data || {};
  const skipped = String(agent.reason || "").toLowerCase().includes("skipped");
  const accordion = document.querySelector(`[data-agent="${agentKey}"]`);
  if (accordion) {
    accordion.classList.toggle("agent-skipped", skipped);
    if (!skipped && agent.risk_level) accordion.open = false;
  }
  setRiskBadge(`${prefix}Risk`, skipped ? "" : agent.risk_level);
  const reasonEl = $(`${prefix}Reason`);
  const actionEl = $(`${prefix}Action`);
  if (reasonEl) reasonEl.textContent = agent.reason || "No reason returned.";
  if (actionEl) actionEl.textContent = agent.recommended_action || "No action returned.";
}

function clearChatWelcome() {
  const welcome = document.querySelector(".chat-welcome");
  if (welcome) welcome.remove();
}

function appendUserBubble(text) {
  const container = $("chatMessages");
  if (!container) return;
  clearChatWelcome();
  const wrap = document.createElement("div");
  wrap.className = "bubble bubble-user fade-in";
  wrap.innerHTML = `
    <div class="bubble-inner">
      <div class="bubble-label">You</div>
      <div class="bubble-answer">${escapeHtml(text)}</div>
    </div>
  `;
  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
}

function appendLoadingBubble() {
  const container = $("chatMessages");
  if (!container) return;
  clearChatWelcome();
  const id = "loading-bubble";
  let existing = document.getElementById(id);
  if (existing) existing.remove();
  const wrap = document.createElement("div");
  wrap.id = id;
  wrap.className = "bubble bubble-ai";
  wrap.innerHTML = `<div class="bubble-inner"><div class="skeleton" style="min-height:80px"></div></div>`;
  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
}

function removeLoadingBubble() {
  document.getElementById("loading-bubble")?.remove();
}

function appendAiBubble(payload, meta = {}) {
  const container = $("chatMessages");
  if (!container) return;
  removeLoadingBubble();
  clearChatWelcome();

  const answer = (payload?.answer ?? "").trim().replace(/\n{3,}/g, "\n\n");
  const sources = Array.isArray(payload?.sources) ? payload.sources : [];
  const uniqueSources = Array.from(new Set(sources.filter(Boolean)));

  const sourcesHtml = uniqueSources.length
    ? `<div class="bubble-sources"><div class="bubble-sources-title">Sources</div><ul>${uniqueSources
        .map((s) => `<li>${escapeHtml(s)}</li>`)
        .join("")}</ul></div>`
    : "";

  const wrap = document.createElement("div");
  wrap.className = "bubble bubble-ai fade-in";
  wrap.innerHTML = `
    <div class="bubble-inner">
      <div class="bubble-label">DocFlow AI</div>
      <div class="bubble-answer">${escapeHtml(answer || "No answer returned.")}</div>
      ${sourcesHtml}
      <div class="bubble-meta">
        <span>${escapeHtml(meta.serverTime || "")}</span>
        <span>${escapeHtml(meta.cacheStatus || "")}</span>
      </div>
      <div class="bubble-actions">
        <button type="button" class="feedback-btn" data-action="copy" title="Copy answer">⎘</button>
        <button type="button" class="feedback-btn" data-action="like" title="Like">👍</button>
        <button type="button" class="feedback-btn" data-action="dislike" title="Dislike">👎</button>
      </div>
    </div>
  `;

  wrap.querySelector('[data-action="copy"]')?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(answer);
      setStatus($("queryStatus"), "Answer copied.", "ok");
    } catch {
      setStatus($("queryStatus"), "Copy failed.", "err");
    }
  });

  wrap.querySelector('[data-action="like"]')?.addEventListener("click", (e) => {
    e.currentTarget.classList.toggle("active-like");
    wrap.querySelector('[data-action="dislike"]')?.classList.remove("active-dislike");
  });

  wrap.querySelector('[data-action="dislike"]')?.addEventListener("click", (e) => {
    e.currentTarget.classList.toggle("active-dislike");
    wrap.querySelector('[data-action="like"]')?.classList.remove("active-like");
  });

  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
}

function renderResult(payload) {
  const answer = (payload?.answer ?? "").trim().replace(/\n{3,}/g, "\n\n");
  lastAnswerText = answer;
  const agents = payload?.agents ?? {};
  const decision = payload?.decision ?? {};
  const sources = Array.isArray(payload?.sources) ? payload.sources : [];
  const domain = payload?.domain || "general";
  const agentsRun = Array.isArray(payload?.agents_run) ? payload.agents_run.join(", ") : "";

  const answerEl = $("answerText");
  if (answerEl) answerEl.textContent = answer || "No answer returned.";

  const modePill = $("queryModePill");
  if (modePill) {
    modePill.textContent = agentsRun
      ? `Domain: ${domain} · ${agentsRun}`
      : `Domain: ${domain}`;
  }

  setRiskBadge("decisionRisk", decision.final_risk);
  const decisionText = $("decisionText");
  const priorityAction = $("priorityAction");
  if (decisionText) decisionText.textContent = decision.final_decision || "No final decision.";
  if (priorityAction) priorityAction.textContent = decision.priority_action || "No priority action.";

  updateDashboard(decision);

  renderAgent("supplier", "supplier", agents.supplier);
  renderAgent("inventory", "inventory", agents.inventory);
  renderAgent("logistics", "logistics", agents.logistics);
  renderAgent("external_risk", "externalRisk", agents.external_risk);

  const ul = $("sourcesList");
  if (ul) {
    ul.innerHTML = "";
    const uniqueSources = Array.from(new Set(sources.filter(Boolean)));
    for (const src of uniqueSources) {
      const li = document.createElement("li");
      li.textContent = src;
      ul.appendChild(li);
    }
  }
}

async function deleteDocument(filename) {
  const status = $("uploadStatus");
  if (!confirm(`Delete ${filename} from the index?`)) return;
  setProcessing(status, "Deleting…");
  try {
    const res = await apiFetch(`/documents/${encodeURIComponent(filename)}`, { method: "DELETE" });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data?.detail || `Delete failed (${res.status})`);
    setStatus(status, data?.message || "Document deleted.", "ok");
    await refreshDocuments();
  } catch (e) {
    setStatus(status, `Delete error: ${e?.message || e}`, "err");
  }
}

async function forceReindex() {
  const status = $("uploadStatus");
  setProcessing(status, "Rebuilding index…");
  try {
    const res = await apiFetch("/documents/reindex", { method: "POST" });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data?.detail || `Re-index failed (${res.status})`);
    setStatus(status, data?.message || "Re-index complete.", "ok");
    await refreshDocuments();
    await checkApiHealth();
  } catch (e) {
    setStatus(status, `Re-index error: ${e?.message || e}`, "err");
  }
}

async function uploadPdf(file) {
  const status = $("uploadStatus");
  const btn = $("uploadBtn");

  if (!file) {
    setStatus(status, "Choose a PDF first.", "err");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    setStatus(status, "Only PDF files are supported.", "err");
    return;
  }

  setLoading(btn, true, "Upload");
  setProcessing(status, "Uploading…");

  try {
    const form = new FormData();
    form.append("file", file);
    const res = await apiFetch("/upload", { method: "POST", body: form });
    const data = await safeJson(res);
    if (!res.ok) {
      const detail = data?.detail ? JSON.stringify(data.detail) : JSON.stringify(data);
      throw new Error(detail || `Upload failed (${res.status})`);
    }
    setStatus(status, data?.message || "Upload successful.", "ok");
    await refreshDocuments();
  } catch (e) {
    setStatus(status, `Upload error: ${e?.message || e}`, "err");
  } finally {
    setLoading(btn, false, "Upload");
    if (btn) btn.innerHTML = '<span class="btn-icon">+</span> Upload PDF';
  }
}

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveHistory(history) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY)));
}

function addHistoryEntry(question, responseTimeMs, riskLevel) {
  const history = loadHistory();
  history.unshift({
    q: question,
    time: responseTimeMs,
    risk: normalizeRisk(riskLevel),
    ts: new Date().toLocaleTimeString(),
  });
  saveHistory(history);
  renderHistory();
}

function renderHistory() {
  const list = $("historyList");
  if (!list) return;
  const history = loadHistory();
  list.innerHTML = "";

  if (!history.length) {
    list.innerHTML = '<li class="doc-empty" style="list-style:none">No queries yet.</li>';
    return;
  }

  for (const entry of history) {
    const li = document.createElement("li");
    li.className = "history-item";
    li.innerHTML = `
      <span class="history-q">${escapeHtml(entry.q)}</span>
      <span class="history-meta">
        <span class="risk ${riskClass(entry.risk)}">${entry.risk || "—"}</span>
        <span>${entry.time ? entry.time + "ms" : ""}</span>
      </span>
    `;
    li.addEventListener("click", () => {
      $("questionInput").value = entry.q;
      $("questionInput").focus();
    });
    list.appendChild(li);
  }
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
}

async function askQuestion() {
  const q = $("questionInput").value.trim();
  const status = $("queryStatus");
  const btn = $("askBtn");

  if (!q) {
    setStatus(status, "Please type a question.", "err");
    return;
  }

  appendUserBubble(q);
  setLoading(btn, true, "Submit");
  setStatus(status, "Thinking…", "");
  appendLoadingBubble();

  const t0 = performance.now();

  try {
    const res = await apiFetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });

    const elapsedMs = Math.round(performance.now() - t0);
    const serverTime = res.headers.get("X-Response-Time") || "";
    const cacheStatus = res.headers.get("X-Cache");
    const data = await safeJson(res);

    if (!res.ok) {
      removeLoadingBubble();
      if (res.status === 503 && data?.error) throw new Error(data.error);
      const detail = data?.detail ? JSON.stringify(data.detail) : JSON.stringify(data);
      throw new Error(detail || data?.error || `Query failed (${res.status})`);
    }

    renderResult(data);

    const timeLabel = serverTime ? `Server: ${serverTime}` : `${elapsedMs}ms`;
    const cacheLabel =
      cacheStatus === "HIT" ? "Cached" : cacheStatus === "MISS" ? "Fresh" : "";

    $("responseTime").textContent = timeLabel;
    $("cacheIndicator").textContent = cacheLabel;
    const meta = $("responseMeta");
    if (meta) meta.style.display = "flex";

    appendAiBubble(data, { serverTime: timeLabel, cacheStatus: cacheLabel });

    addHistoryEntry(q, elapsedMs, data?.decision?.final_risk);
    await refreshServerStats();
    setStatus(status, "Done.", "ok");
  } catch (e) {
    removeLoadingBubble();
    setStatus(status, `Error: ${e?.message || e}`, "err");
    appendAiBubble(
      { answer: `Sorry, something went wrong: ${e?.message || e}`, sources: [] },
      { serverTime: "", cacheStatus: "" }
    );
  } finally {
    setLoading(btn, false, "Submit");
  }
}

function openSettingsDialog() {
  const dialog = $("settingsDialog");
  if (!dialog) return;
  const urlIn = $("apiUrlInputDialog");
  const keyIn = $("apiKeyInputDialog");
  if (urlIn) urlIn.value = API_BASE;
  if (keyIn) keyIn.value = getApiKey();
  if (typeof dialog.showModal === "function") dialog.showModal();
}

function applySettingsFromDialog() {
  const url = $("apiUrlInputDialog")?.value.trim();
  const key = $("apiKeyInputDialog")?.value.trim() ?? "";
  if (url) {
    setApiBase(url);
    if ($("apiUrlInput")) $("apiUrlInput").value = API_BASE;
    checkApiHealth();
    refreshMetrics();
  }
  localStorage.setItem(API_KEY_STORAGE, key);
  if ($("apiKeyInput")) $("apiKeyInput").value = key;
}

function initApp() {
  if ($("apiUrlInput")) $("apiUrlInput").value = API_BASE;
  if ($("apiKeyInput")) $("apiKeyInput").value = getApiKey();

  $("saveApiUrlBtn")?.addEventListener("click", () => {
    setApiBase($("apiUrlInput").value.trim());
    checkApiHealth();
    refreshMetrics();
    setStatus($("uploadStatus"), "API URL saved.", "ok");
  });

  $("saveApiKeyBtn")?.addEventListener("click", () => {
    localStorage.setItem(API_KEY_STORAGE, $("apiKeyInput").value.trim());
    setStatus($("uploadStatus"), "API key saved.", "ok");
  });

  $("settingsToggleBtn")?.addEventListener("click", openSettingsDialog);
  $("settingsDialog")?.addEventListener("close", applySettingsFromDialog);

  $("uploadBtn")?.addEventListener("click", () => $("pdfFile")?.click());

  $("pdfFile")?.addEventListener("change", (ev) => {
    const file = ev.target.files?.[0];
    if (file) uploadPdf(file);
    ev.target.value = "";
  });

  $("reindexBtn")?.addEventListener("click", forceReindex);
  $("askBtn")?.addEventListener("click", askQuestion);
  $("resetDashboardBtn")?.addEventListener("click", resetDashboard);
  $("clearCacheBtn")?.addEventListener("click", clearServerCache);
  $("clearHistoryBtn")?.addEventListener("click", clearHistory);

  $("questionInput")?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") askQuestion();
  });

  initSuggestions();
  checkApiHealth();
  refreshDocuments();
  refreshServerStats();
  refreshMetrics();
  setInterval(checkApiHealth, 30000);
  renderHistory();
  renderDashboard();
}

document.addEventListener("DOMContentLoaded", initApp);
