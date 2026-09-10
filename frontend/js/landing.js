/* DocRAGFlow landing page — navigation, scroll reveal, pipeline animation,
   parallax, and lazy loading of the WebGL hero scene. */

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const isCompact = () => window.matchMedia("(max-width: 860px)").matches;

/* ── Navbar ─────────────────────────────────────────────────────────────── */
function initNav() {
  const nav = document.getElementById("siteNav");
  const toggle = document.getElementById("navToggle");
  const links = document.getElementById("navLinks");

  const onScroll = () => nav.classList.toggle("is-scrolled", window.scrollY > 16);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const closeMenu = () => {
    links.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
  };

  toggle.addEventListener("click", () => {
    const open = links.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(open));
  });

  links.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeMenu();
  });

  window.addEventListener("resize", () => {
    if (!isCompact()) closeMenu();
  });
}

/* ── Scroll reveal ──────────────────────────────────────────────────────── */
function initReveal() {
  const targets = document.querySelectorAll(".reveal");

  if (reduceMotion.matches || !("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    },
    { rootMargin: "0px 0px -12% 0px", threshold: 0.12 }
  );

  targets.forEach((el) => observer.observe(el));
}

/* ── "How it works" connector line ─────────────────────────────────────── */
function initSteps() {
  const steps = document.getElementById("steps");
  if (!steps) return;

  if (reduceMotion.matches || !("IntersectionObserver" in window)) {
    steps.classList.add("is-drawn");
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      if (!entries[0].isIntersecting) return;
      steps.classList.add("is-drawn");
      observer.disconnect();
    },
    { threshold: 0.3 }
  );

  observer.observe(steps);
}

/* ── RAG pipeline: draw-in plus travelling data pulses ─────────────────── */
function initFlow() {
  const flow = document.getElementById("flow");
  if (!flow) return;

  const svg = flow.querySelector(".flow-svg");
  const paths = [...flow.querySelectorAll(".flow-line")];

  if (reduceMotion.matches || !("IntersectionObserver" in window)) {
    flow.classList.add("is-drawn");
    return;
  }

  // Query -> embedding -> vector search -> middle chunk -> LLM
  const route = [paths[0], paths[1], paths[3], paths[6]].filter(Boolean);
  const lengths = route.map((p) => p.getTotalLength());
  const pulses = route.map(() => {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("r", "4");
    dot.setAttribute("class", "flow-pulse");
    dot.style.opacity = "0";
    svg.appendChild(dot);
    return dot;
  });

  let raf = 0;
  let start = 0;
  const legDuration = 620;

  const tick = (now) => {
    if (!start) start = now;
    const cycle = (now - start) % (legDuration * route.length + 700);

    route.forEach((path, index) => {
      const from = legDuration * index;
      const t = (cycle - from) / legDuration;
      const dot = pulses[index];
      if (t < 0 || t > 1) {
        dot.style.opacity = "0";
        return;
      }
      const point = path.getPointAtLength(lengths[index] * t);
      dot.setAttribute("cx", point.x);
      dot.setAttribute("cy", point.y);
      dot.style.opacity = String(Math.sin(t * Math.PI));
    });

    raf = requestAnimationFrame(tick);
  };

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries[0].isIntersecting;
      if (visible) {
        flow.classList.add("is-drawn");
        if (!raf) raf = requestAnimationFrame(tick);
      } else if (raf) {
        cancelAnimationFrame(raf);
        raf = 0;
        start = 0;
        pulses.forEach((dot) => (dot.style.opacity = "0"));
      }
    },
    { threshold: 0.25 }
  );

  observer.observe(flow);
}

/* ── Pointer parallax + card tilt ──────────────────────────────────────── */
function initPointerEffects() {
  if (reduceMotion.matches || window.matchMedia("(hover: none)").matches) return;

  const layers = [...document.querySelectorAll("[data-parallax]")];
  const pointer = { x: 0, y: 0 };
  const current = { x: 0, y: 0 };
  let raf = 0;

  const loop = () => {
    current.x += (pointer.x - current.x) * 0.08;
    current.y += (pointer.y - current.y) * 0.08;

    for (const layer of layers) {
      const strength = Number(layer.dataset.parallaxStrength || 9);
      layer.style.transform =
        `perspective(1200px) rotateY(${current.x * strength}deg) ` +
        `rotateX(${-current.y * strength * 0.6}deg)`;
    }

    raf = Math.abs(pointer.x - current.x) + Math.abs(pointer.y - current.y) > 0.001
      ? requestAnimationFrame(loop)
      : 0;
  };

  window.addEventListener(
    "pointermove",
    (event) => {
      pointer.x = (event.clientX / window.innerWidth - 0.5) * 2;
      pointer.y = (event.clientY / window.innerHeight - 0.5) * 2;
      if (!raf) raf = requestAnimationFrame(loop);
    },
    { passive: true }
  );

  for (const card of document.querySelectorAll("[data-tilt]")) {
    card.addEventListener("pointermove", (event) => {
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      card.style.transform = `translateY(-6px) rotateY(${x * 6}deg) rotateX(${-y * 6}deg)`;
    });
    card.addEventListener("pointerleave", () => {
      card.style.transform = "";
    });
  }
}

/* ── Hero WebGL scene (lazy, optional) ─────────────────────────────────── */
function supportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function initHeroScene() {
  const stage = document.getElementById("heroScene");
  const canvas = document.getElementById("heroCanvas");
  if (!stage || !canvas) return;

  // The CSS scene stays in place when 3D is unnecessary or unsupported.
  if (reduceMotion.matches || isCompact() || !supportsWebGL()) return;

  const observer = new IntersectionObserver(
    (entries) => {
      if (!entries[0].isIntersecting) return;
      observer.disconnect();
      import("./hero-scene.js")
        .then(({ mountHeroScene }) => mountHeroScene(canvas, stage))
        .catch(() => {
          /* Offline or CDN blocked — keep the CSS fallback visual. */
        });
    },
    { rootMargin: "200px" }
  );

  observer.observe(stage);
}

/* ── Boot ───────────────────────────────────────────────────────────────── */
document.getElementById("year").textContent = String(new Date().getFullYear());
initNav();
initReveal();
initSteps();
initFlow();
initPointerEffects();
initHeroScene();
