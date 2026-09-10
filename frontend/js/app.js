/* DocRAGFlow app shell: hash routing, sidebar drawer, and global search.
   Hash routes are used because the workspace is served as static files —
   real paths would 404 on refresh without a server rewrite. */

const AppShell = (() => {
  const ROUTES = [
    { id: "overview", label: "Overview", title: "Overview" },
    { id: "documents", label: "Documents", title: "Documents" },
    { id: "chat", label: "AI Chat", title: "AI Chat" },
    { id: "agents", label: "Agents", title: "AI Agents" },
    { id: "analysis", label: "Analysis", title: "Analysis" },
    { id: "history", label: "History", title: "Query History" },
    { id: "knowledge", label: "Knowledge Base", title: "Knowledge Base" },
    { id: "settings", label: "Settings", title: "Settings" },
  ];

  const DEFAULT_ROUTE = "overview";
  const enterHandlers = new Map();
  let documentNames = [];
  let currentRoute = null;

  const byId = (id) => document.getElementById(id);
  const routeExists = (id) => ROUTES.some((route) => route.id === id);

  function routeFromHash() {
    const raw = (window.location.hash || "").replace(/^#\/?/, "").split("?")[0];
    return routeExists(raw) ? raw : DEFAULT_ROUTE;
  }

  function setActiveNav(routeId) {
    for (const link of document.querySelectorAll(".side-item[data-route-link]")) {
      const target = (link.getAttribute("href") || "").replace(/^#\/?/, "");
      // Secondary links (e.g. "API Configuration") point at an existing page
      // section and should not steal the active state from the page itself.
      link.classList.toggle("is-active", target === routeId && !link.dataset.focus);
    }
  }

  function render(routeId) {
    for (const view of document.querySelectorAll(".view")) {
      view.hidden = view.dataset.view !== routeId;
    }

    setActiveNav(routeId);
    const route = ROUTES.find((item) => item.id === routeId);
    document.title = `DocRAGFlow — ${route ? route.title : "Workspace"}`;

    if (currentRoute !== routeId) {
      currentRoute = routeId;
      window.scrollTo({ top: 0, behavior: "auto" });
    }

    for (const handler of enterHandlers.get(routeId) || []) {
      try {
        handler();
      } catch (error) {
        console.error(`Route handler failed for ${routeId}`, error);
      }
    }
  }

  function navigate(routeId, { focus } = {}) {
    const next = routeExists(routeId) ? routeId : DEFAULT_ROUTE;
    if (window.location.hash === `#/${next}`) {
      render(next);
    } else {
      window.location.hash = `#/${next}`;
    }
    if (focus) {
      requestAnimationFrame(() => {
        byId(focus)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }

  /* ── Mobile drawer ── */
  function initDrawer() {
    const sidebar = byId("sidebar");
    const scrim = byId("scrim");
    const toggle = byId("drawerToggle");
    if (!sidebar || !toggle) return;

    const setOpen = (open) => {
      sidebar.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      if (scrim) scrim.hidden = !open;
    };

    toggle.addEventListener("click", () => setOpen(!sidebar.classList.contains("is-open")));
    scrim?.addEventListener("click", () => setOpen(false));
    sidebar.addEventListener("click", (event) => {
      if (event.target.closest("[data-route-link]")) setOpen(false);
    });
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setOpen(false);
    });
    window.addEventListener("resize", () => {
      if (window.innerWidth > 900) setOpen(false);
    });
  }

  /* ── Route links ── */
  function initLinks() {
    document.addEventListener("click", (event) => {
      const link = event.target.closest("[data-route-link]");
      if (!link) return;
      const href = link.getAttribute("href") || "";
      if (!href.startsWith("#/")) return;
      event.preventDefault();
      navigate(href.replace(/^#\/?/, ""), { focus: link.dataset.focus });
    });
  }

  /* ── Global search over pages and documents ── */
  function initSearch() {
    const input = byId("globalSearch");
    const results = byId("searchResults");
    if (!input || !results) return;

    const close = () => {
      results.hidden = true;
      results.innerHTML = "";
      input.setAttribute("aria-expanded", "false");
    };

    const run = () => {
      const query = input.value.trim().toLowerCase();
      if (!query) return close();

      const pages = ROUTES.filter((route) => route.label.toLowerCase().includes(query)).map(
        (route) => ({ kind: "Page", label: route.label, route: route.id })
      );
      const docs = documentNames
        .filter((name) => name.toLowerCase().includes(query))
        .slice(0, 6)
        .map((name) => ({ kind: "Document", label: name, route: "documents", doc: name }));

      const items = [...pages, ...docs].slice(0, 9);
      results.innerHTML = "";

      if (!items.length) {
        const empty = document.createElement("li");
        empty.className = "res-empty";
        empty.textContent = "No matches";
        results.appendChild(empty);
      }

      for (const item of items) {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.innerHTML =
          `<span>${item.label.replace(/[<>&]/g, "")}</span>` +
          `<span class="res-kind">${item.kind}</span>`;
        button.addEventListener("click", () => {
          navigate(item.route);
          if (item.doc) {
            const docSearch = byId("docSearch");
            if (docSearch) {
              docSearch.value = item.doc;
              docSearch.dispatchEvent(new Event("input", { bubbles: true }));
            }
          }
          input.value = "";
          close();
        });
        li.appendChild(button);
        results.appendChild(li);
      }

      results.hidden = false;
      input.setAttribute("aria-expanded", "true");
    };

    input.addEventListener("input", run);
    input.addEventListener("focus", run);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        input.value = "";
        close();
        input.blur();
      }
      if (event.key === "Enter") {
        results.querySelector("button")?.click();
      }
    });

    document.addEventListener("click", (event) => {
      if (!event.target.closest(".topbar-search")) close();
    });

    window.addEventListener("keydown", (event) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
      if (event.key === "/" && !typing) {
        event.preventDefault();
        input.focus();
      }
    });
  }

  function initMenus() {
    const menu = document.getElementById("userMenu");
    if (!menu) return;
    document.addEventListener("click", (event) => {
      if (!event.target.closest("#userMenu")) menu.removeAttribute("open");
    });
    menu.addEventListener("click", (event) => {
      if (event.target.closest("a")) menu.removeAttribute("open");
    });
  }

  function start() {
    initDrawer();
    initLinks();
    initSearch();
    initMenus();

    window.addEventListener("hashchange", () => render(routeFromHash()));

    // Legacy deep link: app.html?settings=1 opened the settings dialog.
    const wantsSettings = new URLSearchParams(window.location.search).get("settings") === "1";
    if (wantsSettings && !window.location.hash) {
      navigate("settings");
    } else {
      render(routeFromHash());
    }
  }

  return {
    ROUTES,
    start,
    navigate,
    get route() {
      return currentRoute;
    },
    onEnter(routeId, handler) {
      if (!enterHandlers.has(routeId)) enterHandlers.set(routeId, []);
      enterHandlers.get(routeId).push(handler);
    },
    setDocuments(names) {
      documentNames = Array.isArray(names) ? names : [];
    },
  };
})();
