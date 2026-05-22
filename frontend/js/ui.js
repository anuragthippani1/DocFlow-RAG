const $ = (id) => document.getElementById(id);

      function setStatus(el, message, kind) {
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
        button.disabled = isLoading;
        button.textContent = isLoading ? "Processing..." : label;
      }

      function setProcessing(el, message) {
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
        const risk = normalizeRisk(value);
        $(id).innerHTML = risk ? `<span class="risk ${riskClass(risk)}">${risk}</span>` : "";
      }

      function updateDashboard(decision) {
        const risk = normalizeRisk(decision?.final_risk) || "Low";
        dashboardState.totalQueries += 1;
        dashboardState.riskCounts[risk] = (dashboardState.riskCounts[risk] || 0) + 1;

        renderDashboard();
      }

      function renderDashboard() {
        $("totalQueries").textContent = String(dashboardState.totalQueries);
        $("lowRiskCount").textContent = String(dashboardState.riskCounts.Low);
        $("mediumRiskCount").textContent = String(dashboardState.riskCounts.Medium);
        $("highRiskCount").textContent = String(dashboardState.riskCounts.High);
      }

      function resetDashboard() {
        dashboardState.totalQueries = 0;
        dashboardState.riskCounts.Low = 0;
        dashboardState.riskCounts.Medium = 0;
        dashboardState.riskCounts.High = 0;
        renderDashboard();
        setStatus($("queryStatus"), "Dashboard reset.", "ok");
      }

      async function checkApiHealth() {
        const pill = $("apiBasePill");
        pill.classList.remove("online", "offline");
        pill.textContent = `API: checking ${API_BASE}`;

        try {
          const res = await apiFetch("/health");
          if (!res.ok) throw new Error(`Health check failed (${res.status})`);
          const data = await safeJson(res);
          const version = data?.version ? ` v${data.version}` : "";
          const dbNote = data?.vector_db_ready === false ? " · no vector DB" : "";
          pill.classList.add("online");
          pill.textContent = `API online${version}${dbNote}: ${API_BASE}`;
        } catch {
          pill.classList.add("offline");
          pill.textContent = `API offline: ${API_BASE}`;
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
            `Uptime ${data?.uptime_seconds ?? 0}s · Queries ${data?.total_queries ?? 0} · ` +
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
          el.title = `${hits} hits / ${total} queries · cache size ${data?.cache_size ?? 0}`;
        } catch {
          el.textContent = "—";
        }
      }

      async function clearServerCache() {
        const status = $("queryStatus");
        try {
          const res = await apiFetch("/cache/clear", { method: "POST" });
          const data = await safeJson(res);
          if (!res.ok) {
            throw new Error(data?.detail || `Clear failed (${res.status})`);
          }
          setStatus(status, data?.message || "Query cache cleared.", "ok");
          await refreshServerStats();
        } catch (e) {
          setStatus(status, `Cache clear error: ${e?.message || e}`, "err");
        }
      }

      async function refreshDocuments() {
        const pill = $("docCountPill");
        const list = $("docList");
        if (!pill) return;
        try {
          const res = await apiFetch("/documents");
          if (!res.ok) throw new Error("documents unavailable");
          const data = await safeJson(res);
          const docs = Array.isArray(data?.documents) ? data.documents : [];
          const count = data?.count ?? docs.length;
          pill.textContent = count === 1 ? "1 PDF indexed" : `${count} PDFs indexed`;
          if (list) {
            list.innerHTML = "";
            if (!docs.length) {
              const li = document.createElement("li");
              li.textContent = "No PDFs uploaded yet.";
              list.appendChild(li);
            } else {
              for (const name of docs) {
                const li = document.createElement("li");
                li.className = "doc-item";
                const label = document.createElement("span");
                label.textContent = name;
                const del = document.createElement("button");
                del.type = "button";
                del.className = "secondary";
                del.style.fontSize = "11px";
                del.textContent = "Delete";
                del.addEventListener("click", () => deleteDocument(name));
                li.appendChild(label);
                li.appendChild(del);
                list.appendChild(li);
              }
            }
          }
        } catch {
          pill.textContent = "Documents: unavailable";
          if (list) list.innerHTML = "";
        }
      }

      const SUGGESTED_QUESTIONS = [
        "What are the main supply chain risks?",
        "Summarize key findings from the documents.",
        "What actions should we take first?",
      ];

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

      function renderAgent(prefix, data) {
        const agent = data || {};
        setRiskBadge(`${prefix}Risk`, agent.risk_level);
        $(`${prefix}Reason`).textContent = agent.reason || "No reason returned.";
        $(`${prefix}Action`).textContent = agent.recommended_action || "No action returned.";
      }

      function renderResult(payload) {
        const answer = payload?.answer ?? "";
        const agents = payload?.agents ?? {};
        const decision = payload?.decision ?? {};
        const sources = Array.isArray(payload?.sources) ? payload.sources : [];

        $("answerText").textContent = answer || "No answer returned.";
        setRiskBadge("decisionRisk", decision.final_risk);
        $("decisionText").textContent = decision.final_decision || "No final decision returned.";
        $("priorityAction").textContent = decision.priority_action || "No priority action returned.";
        updateDashboard(decision);

        renderAgent("supplier", agents.supplier);
        renderAgent("inventory", agents.inventory);
        renderAgent("logistics", agents.logistics);
        renderAgent("externalRisk", agents.external_risk);

        const ul = $("sourcesList");
        ul.innerHTML = "";
        const uniqueSources = Array.from(new Set(sources.filter(Boolean)));
        if (!uniqueSources.length) {
          const li = document.createElement("li");
          li.textContent = "No sources returned.";
          ul.appendChild(li);
          return;
        }

        for (const src of uniqueSources) {
          const li = document.createElement("li");
          const a = document.createElement("a");
          a.href = "#";
          a.className = "source-link";
          a.textContent = src;
          a.addEventListener("click", async (ev) => {
            ev.preventDefault();
            try {
              await navigator.clipboard.writeText(src);
              setStatus($("queryStatus"), `Copied source: ${src}`, "ok");
            } catch {
              setStatus($("queryStatus"), `Source: ${src}`, "ok");
            }
          });
          li.appendChild(a);
          ul.appendChild(li);
        }
      }

      async function deleteDocument(filename) {
        const status = $("uploadStatus");
        if (!confirm(`Delete ${filename} from the index?`)) return;
        setProcessing(status, "Deleting document...");
        try {
          const res = await apiFetch(`/documents/${encodeURIComponent(filename)}`, {
            method: "DELETE",
          });
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
        setProcessing(status, "Rebuilding vector index...");
        try {
          const res = await apiFetch("/documents/reindex", { method: "POST" });
          const data = await safeJson(res);
          if (!res.ok) throw new Error(data?.detail || `Re-index failed (${res.status})`);
          setStatus(status, data?.message || "Re-index complete.", "ok");
          await refreshDocuments();
        } catch (e) {
          setStatus(status, `Re-index error: ${e?.message || e}`, "err");
        }
      }

      async function uploadPdf() {
        const file = $("pdfFile").files?.[0];
        const status = $("uploadStatus");
        const btn = $("uploadBtn");

        if (!file) {
          setStatus(status, "Please choose a PDF file first.", "err");
          return;
        }
        if (!file.name.toLowerCase().endsWith(".pdf")) {
          setStatus(status, "Only PDF uploads are supported.", "err");
          return;
        }

        setLoading(btn, true, "Upload");
        setProcessing(status, "Processing upload...");

        try {
          const form = new FormData();
          form.append("file", file);

          const res = await apiFetch("/upload", {
            method: "POST",
            body: form,
          });

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
        }
      }

      const HISTORY_KEY = "docflow_query_history";
      const MAX_HISTORY = 20;

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
        const history = loadHistory();
        list.innerHTML = "";

        if (!history.length) {
          const li = document.createElement("li");
          li.style.cssText = "font-size:13px;color:var(--muted)";
          li.textContent = "No queries yet.";
          list.appendChild(li);
          return;
        }

        for (const entry of history) {
          const li = document.createElement("li");
          li.className = "history-item";
          li.innerHTML =
            `<span class="history-q">${entry.q}</span>` +
            `<span class="history-meta">` +
            `<span class="risk ${riskClass(entry.risk)}" style="font-size:11px;padding:2px 8px">${entry.risk || "—"}</span>` +
            `<span>${entry.time ? entry.time + "ms" : ""}</span>` +
            `<span>${entry.ts || ""}</span>` +
            `</span>`;
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

        setLoading(btn, true, "Submit");
        setProcessing(status, "Processing question...");
        $("answerText").innerHTML = '<div class="skeleton" style="height:72px"></div>';
        $("responseMeta").style.display = "none";

        const t0 = performance.now();

        try {
          const res = await apiFetch("/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: q }),
          });

          const elapsedMs = Math.round(performance.now() - t0);
          const serverTime = res.headers.get("X-Response-Time") || "";

          const data = await safeJson(res);
          if (!res.ok) {
            if (res.status === 503 && data?.error) {
              throw new Error(data.error);
            }
            const detail = data?.detail ? JSON.stringify(data.detail) : JSON.stringify(data);
            throw new Error(detail || data?.error || `Query failed (${res.status})`);
          }

          renderResult(data);

          $("responseTime").textContent = serverTime ? `Server: ${serverTime}` : `${elapsedMs}ms`;
          const cacheStatus = res.headers.get("X-Cache");
          $("cacheIndicator").textContent =
            cacheStatus === "HIT" ? "Cached response" : cacheStatus === "MISS" ? "Fresh response" : "";
          $("responseMeta").style.display = "flex";

          addHistoryEntry(q, elapsedMs, data?.decision?.final_risk);
          await refreshServerStats();
          setStatus(status, "Done.", "ok");
        } catch (e) {
          setStatus(status, `Query error: ${e?.message || e}`, "err");
        } finally {
          setLoading(btn, false, "Submit");
        }
      }

      if ($("apiUrlInput")) $("apiUrlInput").value = API_BASE;
      $("saveApiUrlBtn")?.addEventListener("click", () => {
        setApiBase($("apiUrlInput").value.trim());
        checkApiHealth();
        refreshMetrics();
        setStatus($("uploadStatus"), "API URL saved.", "ok");
      });

      $("apiKeyInput").value = getApiKey();
      $("saveApiKeyBtn").addEventListener("click", () => {
        localStorage.setItem(API_KEY_STORAGE, $("apiKeyInput").value.trim());
        setStatus($("uploadStatus"), "API key saved for this browser.", "ok");
      });
      $("reindexBtn").addEventListener("click", forceReindex);
      $("uploadBtn").addEventListener("click", uploadPdf);
      $("askBtn").addEventListener("click", askQuestion);
      $("resetDashboardBtn").addEventListener("click", resetDashboard);
      $("clearCacheBtn").addEventListener("click", clearServerCache);
      $("clearHistoryBtn").addEventListener("click", clearHistory);
      $("questionInput").addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") askQuestion();
      });
      initSuggestions();
      checkApiHealth();
      refreshDocuments();
      refreshServerStats();
      refreshMetrics();
      setInterval(checkApiHealth, 30000);
      renderHistory();
