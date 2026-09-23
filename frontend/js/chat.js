/* Persistent conversational RAG workspace.
   Conversations and messages are stored by the API; this module renders them
   and streams POST /query/stream without faking tokens. */

const ChatWorkspace = (() => {
  const LAST_KEY = "docflow_last_conversation";

  const state = {
    conversations: [],
    activeId: null,
    messages: [],
    sending: false,
    muteLoads: false,
    abort: null,
    followScroll: true,
    activeSources: [],
    bound: false,
  };

  const $ = (id) => document.getElementById(id);

  function hasDocuments() {
    return Number($("sideDocCount")?.textContent || 0) > 0;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatMessage(text) {
    let html = escapeHtml(text);
    html = html.replace(
      /```(?:\w+)?\n([\s\S]*?)```/g,
      (_, code) =>
        `<div class="code-block"><button type="button" class="code-copy" data-copy-code>Copy</button><pre><code>${code.trim()}</code></pre></div>`
    );
    const blocks = html.split(/(<div class="code-block">[\s\S]*?<\/div>)/);
    return blocks
      .map((block, blockIndex) => {
        if (blockIndex % 2 === 1) return block;
        const withCode = block.replace(/`([^`]+)`/g, "<code>$1</code>");
        const parts = withCode.split(/(<code>[\s\S]*?<\/code>)/);
        return parts
          .map((part, index) => {
            if (index % 2 === 1) return part;
            let chunk = part.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
            chunk = chunk.replace(/^### (.+)$/gm, "<h3>$1</h3>");
            chunk = chunk.replace(/^## (.+)$/gm, "<h2>$1</h2>");
            chunk = chunk.replace(
              /\[(\d+)\]/g,
              '<button type="button" class="cite" data-cite="$1" aria-label="Open source $1">[$1]</button>'
            );
            return chunk;
          })
          .join("");
      })
      .join("");
  }

  function dayGroup(iso) {
    const date = iso ? new Date(iso) : new Date();
    if (Number.isNaN(date.getTime())) return "Older";
    const now = new Date();
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startThat = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diff = (startToday - startThat) / 86400000;
    if (diff < 1) return "Today";
    if (diff < 2) return "Yesterday";
    if (diff < 7) return "Previous 7 days";
    return "Older";
  }

  function resizeComposer() {
    const input = $("chatInput");
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  }

  function setSendEnabled() {
    const input = $("chatInput");
    const button = $("chatSendBtn");
    if (!input || !button) return;
    const filled = Boolean(input.value.trim());
    button.disabled = state.sending ? false : !filled;
    const sendIcon = button.querySelector('[data-icon="send"]');
    const stopIcon = button.querySelector('[data-icon="stop"]');
    if (sendIcon) sendIcon.hidden = state.sending;
    if (stopIcon) stopIcon.hidden = !state.sending;
    button.setAttribute("aria-label", state.sending ? "Stop generating" : "Send question");
    button.classList.toggle("is-stopping", state.sending);
  }

  function setStatus(message, kind) {
    const el = $("queryStatus");
    if (!el) return;
    el.classList.remove("ok", "err");
    if (kind) el.classList.add(kind);
    el.textContent = message || "";
  }

  function isCompactLayout() {
    return window.matchMedia("(max-width: 1180px)").matches;
  }

  function closeDrawers() {
    $("chatRail")?.classList.remove("is-open");
    $("chatSources")?.classList.remove("is-open");
    const scrim = $("chatScrim");
    if (scrim) scrim.hidden = true;
  }

  function openRail() {
    if (!isCompactLayout()) return;
    $("chatRail")?.classList.add("is-open");
    const scrim = $("chatScrim");
    if (scrim) scrim.hidden = false;
  }

  function openSources() {
    if (!$("chatSources") || $("chatSources").hidden) return;
    if (!isCompactLayout()) return;
    $("chatSources")?.classList.add("is-open");
    const scrim = $("chatScrim");
    if (scrim) scrim.hidden = false;
  }

  function emptyState() {
    if (!hasDocuments()) {
      return (
        '<div class="empty empty--chat" data-chat-empty>' +
        "<h3>Upload a document to begin</h3>" +
        "<p>Grounded conversations need at least one indexed PDF in your knowledge base.</p>" +
        '<button class="btn btn-primary btn-sm" type="button" data-upload-trigger>Upload PDF</button>' +
        "</div>"
      );
    }
    if (!state.conversations.length && !state.messages.length) {
      return (
        '<div class="empty empty--chat" data-chat-empty>' +
        "<h3>Create your first conversation</h3>" +
        "<p>Ask a question about your documents. Follow-ups stay in this thread.</p>" +
        "</div>"
      );
    }
    return (
      '<div class="empty empty--chat" data-chat-empty>' +
      "<h3>Ask anything about your documents</h3>" +
      "<p>Answers are retrieved from your indexed files and include citations you can open.</p>" +
      "</div>"
    );
  }

  function renderSources(details) {
    const list = $("sourcesList");
    const panel = $("chatSources");
    const grid = $("chatGrid");
    const toggle = $("chatSourcesToggle");
    const meta = $("responseMeta");
    state.activeSources = Array.isArray(details) ? details : [];
    if (!list || !panel || !grid) return;

    list.innerHTML = "";
    const has = state.activeSources.length > 0;
    panel.hidden = !has;
    grid.classList.toggle("chat-grid--no-sources", !has);
    if (toggle) toggle.hidden = !has;
    if (!has) {
      panel.classList.remove("is-open");
      if (meta) meta.hidden = true;
      return;
    }

    for (const item of state.activeSources) {
      const li = document.createElement("li");
      li.id = `source-${item.n}`;
      li.innerHTML =
        `<button type="button" class="source-card" data-cite="${item.n}">` +
        `<span class="source-n">[${item.n}]</span>` +
        `<strong>${escapeHtml(item.document || "Document")}</strong>` +
        (item.page ? `<span class="source-page">Page ${item.page}</span>` : "") +
        (item.excerpt ? `<span class="source-excerpt">${escapeHtml(item.excerpt)}</span>` : "") +
        "</button>";
      list.appendChild(li);
    }
  }

  function highlightSource(n) {
    if (isCompactLayout()) openSources();
    const card = document.getElementById(`source-${n}`);
    if (!card) return;
    card.classList.add("is-active");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setTimeout(() => card.classList.remove("is-active"), 1600);
  }

  function bindLogClicks(log) {
    log.addEventListener("click", (event) => {
      const copyCode = event.target.closest("[data-copy-code]");
      if (copyCode) {
        const code = copyCode.parentElement?.querySelector("code")?.textContent || "";
        navigator.clipboard.writeText(code).then(
          () => {
            copyCode.textContent = "Copied";
            setTimeout(() => {
              copyCode.textContent = "Copy";
            }, 1200);
          },
          () => setStatus("Copy failed.", "err")
        );
        return;
      }
      const cite = event.target.closest("[data-cite]");
      if (cite) {
        highlightSource(cite.getAttribute("data-cite"));
        return;
      }
      const action = event.target.closest("[data-msg-act]");
      if (!action) return;
      const wrap = action.closest(".bubble");
      const act = action.dataset.msgAct;
      if (act === "copy") copyMessage(wrap);
      if (act === "regenerate") regenerate();
      if (act === "edit") beginEdit(wrap);
      if (act === "retry") retryLast();
      if (act === "more") wrap?.querySelector(".msg-menu")?.classList.toggle("is-open");
    });
  }

  function copyMessage(wrap) {
    const text = wrap?.dataset.raw || wrap?.querySelector(".bubble-text")?.textContent || "";
    navigator.clipboard.writeText(text).then(
      () => setStatus("Copied.", "ok"),
      () => setStatus("Copy failed.", "err")
    );
  }

  function messageActions(role, { failed = false } = {}) {
    if (role === "assistant") {
      return (
        '<div class="bubble-actions">' +
        '<button class="act-btn" type="button" data-msg-act="copy" title="Copy" aria-label="Copy answer"><svg class="ic"><use href="#i-copy" /></svg></button>' +
        (failed
          ? '<button class="act-btn" type="button" data-msg-act="retry" title="Try again" aria-label="Try again"><svg class="ic"><use href="#i-refresh" /></svg></button>'
          : '<button class="act-btn" type="button" data-msg-act="regenerate" title="Regenerate" aria-label="Regenerate"><svg class="ic"><use href="#i-refresh" /></svg></button>') +
        '<button class="act-btn msg-more" type="button" data-msg-act="more" title="More" aria-label="More actions"><svg class="ic"><use href="#i-dots" /></svg></button>' +
        '<div class="msg-menu">' +
        '<button type="button" data-msg-act="copy">Copy</button>' +
        (failed
          ? '<button type="button" data-msg-act="retry">Try again</button>'
          : '<button type="button" data-msg-act="regenerate">Regenerate</button>') +
        "</div></div>"
      );
    }
    return (
      '<div class="bubble-actions">' +
      '<button class="act-btn" type="button" data-msg-act="copy" title="Copy" aria-label="Copy message"><svg class="ic"><use href="#i-copy" /></svg></button>' +
      '<button class="act-btn" type="button" data-msg-act="edit" title="Edit" aria-label="Edit message"><svg class="ic"><use href="#i-edit" /></svg></button>' +
      '<button class="act-btn msg-more" type="button" data-msg-act="more" title="More" aria-label="More actions"><svg class="ic"><use href="#i-dots" /></svg></button>' +
      '<div class="msg-menu">' +
      '<button type="button" data-msg-act="copy">Copy</button>' +
      '<button type="button" data-msg-act="edit">Edit</button>' +
      "</div></div>"
    );
  }

  function appendBubble(message, { pending = false, failed = false } = {}) {
    const log = $("chatMessages");
    if (!log) return null;
    log.querySelector("[data-chat-empty]")?.remove();
    const wrap = document.createElement("div");
    wrap.className = `bubble ${message.role === "user" ? "bubble-user" : "bubble-ai"}`;
    if (message.id) wrap.dataset.id = message.id;
    wrap.dataset.role = message.role;
    wrap.dataset.raw = message.content || "";
    if (pending) wrap.id = "pendingBubble";
    const roleLabel = message.role === "user" ? "You" : "DocRAGFlow";
    const body = pending
      ? '<div class="chat-skeleton"><span></span><span></span><span></span></div>'
      : `<div class="bubble-text">${
          message.role === "assistant" ? formatMessage(message.content || "") : escapeHtml(message.content || "")
        }</div>`;
    const error = failed
      ? '<p class="bubble-error">This question could not be answered. <button type="button" class="text-link" data-msg-act="retry">Try again</button></p>'
      : "";
    wrap.innerHTML =
      `<span class="bubble-role">${roleLabel}</span>${body}${error}` +
      `<div class="bubble-foot">${messageActions(message.role, { failed })}</div>`;
    log.appendChild(wrap);
    if (state.followScroll) log.scrollTop = log.scrollHeight;
    return wrap;
  }

  function renderMessages() {
    const log = $("chatMessages");
    if (!log) return;
    log.innerHTML = "";
    if (!state.messages.length) {
      log.innerHTML = emptyState();
      renderSources([]);
      return;
    }
    for (const message of state.messages) {
      appendBubble(message, { failed: Boolean(message.failed) });
    }
    const lastAssistant = [...state.messages].reverse().find((item) => item.role === "assistant" && item.sources);
    renderSources(lastAssistant?.sources || []);
    if (state.followScroll) log.scrollTop = log.scrollHeight;
  }

  function renderRail() {
    const root = $("chatSessions");
    if (!root) return;
    root.innerHTML = "";
    if (!state.conversations.length) {
      const empty = document.createElement("p");
      empty.className = "rail-meta";
      empty.textContent = "No conversations yet.";
      root.appendChild(empty);
      return;
    }

    const groups = [
      ["Today", []],
      ["Yesterday", []],
      ["Previous 7 days", []],
      ["Older", []],
    ];
    const buckets = Object.fromEntries(groups);
    for (const item of state.conversations) {
      buckets[dayGroup(item.updatedAt)].push(item);
    }

    for (const [label, items] of groups) {
      if (!items.length) continue;
      const heading = document.createElement("p");
      heading.className = "rail-group";
      heading.textContent = label;
      root.appendChild(heading);
      for (const item of items) {
        const row = document.createElement("div");
        row.className = "rail-item" + (item.id === state.activeId ? " is-active" : "");
        row.innerHTML =
          `<button type="button" class="rail-open" data-id="${item.id}">` +
          `<span class="rail-q">${escapeHtml(item.title || "New conversation")}</span>` +
          `</button>` +
          `<details class="rail-menu"><summary aria-label="Conversation actions">···</summary>` +
          `<div class="rail-menu-panel">` +
          `<button type="button" data-conv-act="rename" data-id="${item.id}">Rename</button>` +
          `<button type="button" data-conv-act="delete" data-id="${item.id}">Delete</button>` +
          `</div></details>`;
        root.appendChild(row);
      }
    }
  }

  async function apiJson(path, options = {}) {
    const res = await apiFetch(path, options);
    const data = await safeJson(res);
    if (!res.ok) {
      throw new Error(userFacingError(data, data?.detail || `Request failed (${res.status})`));
    }
    return data;
  }

  async function refreshList() {
    try {
      const data = await apiJson("/conversations");
      state.conversations = data.conversations || [];
      renderRail();
    } catch (error) {
      setStatus(error.message, "err");
    }
  }

  async function ensureConversation() {
    if (state.activeId) return state.activeId;
    const created = await apiJson("/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New conversation" }),
    });
    state.activeId = created.id;
    localStorage.setItem(LAST_KEY, created.id);
    AppShell.navigate("chat", { conversationId: created.id });
    await refreshList();
    return created.id;
  }

  async function loadConversation(id) {
    if (state.sending || state.muteLoads) return;
    const target = id || AppShell.conversationId || localStorage.getItem(LAST_KEY);
    await refreshList();
    if (!target) {
      state.activeId = null;
      state.messages = [];
      $("chatTitle").textContent = "AI Chat";
      renderMessages();
      return;
    }
    try {
      const data = await apiJson(`/conversations/${target}`);
      state.activeId = data.id;
      state.messages = data.messages || [];
      localStorage.setItem(LAST_KEY, data.id);
      if (AppShell.conversationId !== data.id) {
        AppShell.navigate("chat", { conversationId: data.id });
      }
      $("chatTitle").textContent = data.title || "AI Chat";
      renderRail();
      renderMessages();
    } catch {
      state.activeId = null;
      state.messages = [];
      localStorage.removeItem(LAST_KEY);
      renderMessages();
      renderRail();
    }
  }

  async function newChat() {
    if (state.sending) stop();
    const created = await apiJson("/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New conversation" }),
    });
    state.activeId = created.id;
    state.messages = [];
    localStorage.setItem(LAST_KEY, created.id);
    AppShell.navigate("chat", { conversationId: created.id });
    $("chatTitle").textContent = created.title;
    await refreshList();
    renderMessages();
    $("chatInput")?.focus();
    closeDrawers();
  }

  function parseSSEBlock(block, onEvent) {
    let event = "message";
    const dataLines = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let payload = {};
    try {
      payload = JSON.parse(dataLines.join(""));
    } catch {
      payload = { raw: dataLines.join("") };
    }
    onEvent(event, payload);
  }

  async function parseSSE(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split(/\r?\n\r?\n/);
      buffer = chunks.pop() || "";
      for (const block of chunks) {
        if (block.trim()) parseSSEBlock(block, onEvent);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) parseSSEBlock(buffer, onEvent);
  }

  /** Attach the live answer node once; used for both streamed tokens and done-only replies. */
  function materializePendingAnswer(pending, textEl) {
    if (!pending) return textEl;
    if (pending.id === "pendingBubble") pending.id = "";
    const skeleton = pending.querySelector(".chat-skeleton");
    if (skeleton) {
      skeleton.replaceWith(textEl);
      return textEl;
    }
    return pending.querySelector(".bubble-text") || textEl;
  }

  function lastUserText() {
    const user = [...state.messages].reverse().find((item) => item.role === "user");
    return user?.content || "";
  }

  async function hydrateActive() {
    if (!state.activeId) return;
    try {
      const data = await apiJson(`/conversations/${state.activeId}`);
      const failed = state.messages.filter((item) => item.failed);
      state.messages = [...(data.messages || []), ...failed];
      $("chatTitle").textContent = data.title || "AI Chat";
      renderRail();
      renderMessages();
    } catch {
      /* keep local messages if the refresh fails */
    }
  }

  async function send(question, { regenerate = false } = {}) {
    const text = (question || "").trim();
    const input = $("chatInput");
    if (!text || state.sending) return;
    if (!hasDocuments()) {
      setStatus("Upload a document before asking a grounded question.", "err");
      return;
    }

    state.muteLoads = true;
    AppShell.navigate("chat", { conversationId: state.activeId || undefined });
    await ensureConversation();

    if (input) {
      input.value = "";
      resizeComposer();
    }
    $("questionInput") && ($("questionInput").value = "");

    state.followScroll = true;
    if (!regenerate) {
      state.messages.push({ role: "user", content: text, id: `local-u-${Date.now()}` });
      appendBubble({ role: "user", content: text });
    }

    const pending = appendBubble({ role: "assistant", content: "" }, { pending: true });
    const textEl = document.createElement("div");
    textEl.className = "bubble-text";
    let streamed = "";

    state.sending = true;
    state.abort = new AbortController();
    setSendEnabled();
    setStatus("Retrieving context…");

    const history = state.messages
      .filter((item) => (item.role === "user" || item.role === "assistant") && !item.failed)
      .slice(0, -1)
      .slice(-10)
      .map((item) => ({ role: item.role, content: item.content }));

    let succeeded = false;
    try {
      const res = await apiFetch("/query/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          conversation_id: state.activeId,
          messages: history,
        }),
        signal: state.abort.signal,
      });

      if (!res.ok) {
        const data = await safeJson(res);
        if (res.status === 503 && data?.error) throw new Error(data.error);
        throw new Error(userFacingError(data, data?.detail || data?.error || `Query failed (${res.status})`));
      }

      let finalPayload = null;
      await parseSSE(res, (event, payload) => {
        if (event === "sources") {
          renderSources(payload.source_details || []);
          setStatus("Writing answer…");
        }
        if (event === "token") {
          materializePendingAnswer(pending, textEl);
          streamed += payload.content || "";
          textEl.innerHTML = formatMessage(streamed);
          const log = $("chatMessages");
          if (state.followScroll && log) log.scrollTop = log.scrollHeight;
        }
        if (event === "done") finalPayload = payload;
        if (event === "error") throw new Error(payload.detail || "Query failed.");
      });

      if (!finalPayload) throw new Error("The response ended before an answer was returned.");

      if (typeof renderResult === "function") renderResult(finalPayload);
      const answer = finalPayload.answer || streamed || "No answer returned.";
      const body = materializePendingAnswer(pending, textEl);
      if (pending) {
        pending.dataset.raw = answer;
        body.innerHTML = formatMessage(answer);
        pending.querySelector(".chat-skeleton")?.remove();
        if (!pending.contains(body) && body === textEl) {
          pending.insertBefore(textEl, pending.querySelector(".bubble-foot"));
        }
      }
      state.messages.push({
        role: "assistant",
        content: answer,
        sources: finalPayload.source_details || state.activeSources || [],
      });
      renderSources(finalPayload.source_details || []);
      const time = $("responseTime");
      const cache = $("cacheIndicator");
      const meta = $("responseMeta");
      if (time) time.textContent = "";
      if (cache) cache.textContent = "Live";
      if (meta) meta.hidden = false;
      if (typeof addHistoryEntry === "function") {
        addHistoryEntry(text, 0, finalPayload?.decision?.final_risk, (finalPayload.sources || []).length);
      }
      const log = $("chatMessages");
      if (state.followScroll && log) log.scrollTop = log.scrollHeight;
      setStatus("");
      await refreshList();
      const current = state.conversations.find((item) => item.id === state.activeId);
      if (current) $("chatTitle").textContent = current.title;
      succeeded = true;
    } catch (error) {
      if (error?.name === "AbortError") {
        setStatus("Generation stopped.");
        if (streamed && pending) {
          const body = materializePendingAnswer(pending, textEl);
          pending.dataset.raw = streamed;
          body.innerHTML = formatMessage(streamed);
          if (!pending.contains(body) && body === textEl) {
            pending.insertBefore(textEl, pending.querySelector(".bubble-foot"));
          }
          state.messages.push({ role: "assistant", content: streamed, sources: state.activeSources });
        } else {
          pending?.remove();
        }
      } else {
        pending?.remove();
        const failed = { role: "assistant", content: "", failed: true };
        state.messages.push(failed);
        appendBubble(failed, { failed: true });
        setStatus(error.message || "Request failed.", "err");
      }
    } finally {
      state.sending = false;
      state.abort = null;
      $("pendingBubble")?.removeAttribute("id");
      setSendEnabled();
      if (typeof refreshServerStats === "function") refreshServerStats();
      if (succeeded) await hydrateActive();
      state.muteLoads = false;
    }
  }

  function stop() {
    state.abort?.abort();
  }

  async function regenerate() {
    const lastUser = lastUserText();
    if (!lastUser || !state.activeId) return;
    const last = state.messages[state.messages.length - 1];
    if (last?.role === "assistant" && last.id && !String(last.id).startsWith("local-")) {
      try {
        await apiJson(`/conversations/${state.activeId}/messages/${last.id}`, { method: "DELETE" });
      } catch {
        /* keep going so regenerate still calls RAG */
      }
      state.messages.pop();
      $("chatMessages")?.querySelector(".bubble:last-child")?.remove();
    } else if (last?.role === "assistant") {
      state.messages.pop();
      $("chatMessages")?.querySelector(".bubble:last-child")?.remove();
    }
    await send(lastUser, { regenerate: true });
  }

  async function retryLast() {
    const lastUser = lastUserText();
    const last = state.messages[state.messages.length - 1];
    if (last?.failed) {
      state.messages.pop();
      $("chatMessages")?.querySelector(".bubble:last-child")?.remove();
    }
    await send(lastUser, { regenerate: true });
  }

  function beginEdit(wrap) {
    if (wrap?.dataset.role !== "user" || state.sending) return;
    const current = wrap.dataset.raw || "";
    const field = document.createElement("textarea");
    field.className = "edit-input";
    field.value = current;
    const text = wrap.querySelector(".bubble-text");
    if (!text) return;
    text.replaceWith(field);
    field.focus();
    let closed = false;
    const save = async () => {
      if (closed) return;
      closed = true;
      const next = field.value.trim();
      if (!next || next === current) {
        field.replaceWith(text);
        return;
      }
      const id = wrap.dataset.id;
      if (id && !id.startsWith("local-") && state.activeId) {
        await apiJson(`/conversations/${state.activeId}/messages/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: next }),
        });
        const index = state.messages.findIndex((item) => item.id === id);
        if (index >= 0) {
          state.messages = state.messages.slice(0, index + 1);
          state.messages[index].content = next;
        }
      }
      wrap.dataset.raw = next;
      const body = document.createElement("div");
      body.className = "bubble-text";
      body.textContent = next;
      field.replaceWith(body);
      await send(next, { regenerate: true });
    };
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        save();
      }
      if (event.key === "Escape") {
        closed = true;
        field.replaceWith(text);
      }
    });
    field.addEventListener("blur", () => save());
  }

  async function renameConversation(id, button) {
    const current = state.conversations.find((item) => item.id === id);
    const row = button?.closest(".rail-item");
    const label = row?.querySelector(".rail-q");
    if (!label) return;
    const field = document.createElement("input");
    field.className = "rail-rename";
    field.value = current?.title || "";
    label.replaceWith(field);
    field.focus();
    field.select();
    let committed = false;
    const commit = async () => {
      if (committed) return;
      committed = true;
      const title = field.value.trim();
      if (!title || title === current?.title) {
        await refreshList();
        return;
      }
      await apiJson(`/conversations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      await refreshList();
      if (id === state.activeId) $("chatTitle").textContent = title;
    };
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      }
      if (event.key === "Escape") refreshList();
    });
    field.addEventListener("blur", commit);
  }

  async function deleteConversation(id) {
    const ok = await confirmAction({
      title: "Delete conversation?",
      body: "This removes the thread and its messages. It does not delete your documents.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    await apiJson(`/conversations/${id}`, { method: "DELETE" });
    if (state.activeId === id) {
      localStorage.removeItem(LAST_KEY);
      state.activeId = null;
      state.messages = [];
      AppShell.navigate("chat");
      renderMessages();
    }
    await refreshList();
  }

  function onChatEnter() {
    loadConversation(AppShell.conversationId);
    $("chatInput")?.focus();
  }

  function bind() {
    if (state.bound) return;
    state.bound = true;
    const form = $("chatForm");
    const input = $("chatInput");
    const log = $("chatMessages");

    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      if (state.sending) stop();
      else send(input?.value);
    });

    input?.addEventListener("input", () => {
      resizeComposer();
      setSendEnabled();
    });
    input?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (state.sending) return;
        send(input.value);
      }
    });

    $("newChatBtn")?.addEventListener("click", () => newChat().catch((error) => setStatus(error.message, "err")));
    $("chatConvToggle")?.addEventListener("click", openRail);
    $("chatSourcesToggle")?.addEventListener("click", openSources);
    $("chatSourcesClose")?.addEventListener("click", closeDrawers);
    $("chatScrim")?.addEventListener("click", closeDrawers);

    $("chatSessions")?.addEventListener("click", (event) => {
      const rename = event.target.closest("[data-conv-act='rename']");
      const remove = event.target.closest("[data-conv-act='delete']");
      const open = event.target.closest(".rail-open");
      if (rename) {
        event.preventDefault();
        renameConversation(rename.dataset.id, rename);
      } else if (remove) {
        event.preventDefault();
        deleteConversation(remove.dataset.id);
      } else if (open) {
        closeDrawers();
        loadConversation(open.dataset.id);
      }
    });

    const jump = $("chatJumpBtn");
    log?.addEventListener("scroll", () => {
      const distance = log.scrollHeight - log.scrollTop - log.clientHeight;
      state.followScroll = distance < 72;
      if (jump) jump.hidden = state.followScroll;
    });
    jump?.addEventListener("click", () => {
      state.followScroll = true;
      log.scrollTop = log.scrollHeight;
      jump.hidden = true;
    });

    document.addEventListener("click", (event) => {
      if (!event.target.closest(".msg-menu") && !event.target.closest("[data-msg-act='more']")) {
        for (const menu of document.querySelectorAll(".msg-menu.is-open")) {
          menu.classList.remove("is-open");
        }
      }
    });

    window.addEventListener("resize", () => {
      if (!isCompactLayout()) closeDrawers();
    });

    if (log) bindLogClicks(log);
    setSendEnabled();
    resizeComposer();
  }

  function refreshEmpty() {
    if (!state.messages.length) renderMessages();
  }

  function init() {
    bind();
    AppShell.onEnter("chat", onChatEnter);
    refreshList();
    if (AppShell.route === "chat") onChatEnter();
  }

  return { init, send, newChat, loadConversation, refreshEmpty };
})();

window.ChatWorkspace = ChatWorkspace;
