/* Hero WebGL scene: a knowledge core surrounded by orbiting documents,
   connecting links, travelling data pulses, and a light particle field.

   Loaded on demand by landing.js. Three.js comes from a CDN because this
   frontend has no build step; if the import fails the CSS scene stays. */

import * as THREE from "https://esm.sh/three@0.169.0";

const DOC_COUNT = 5;
const PARTICLE_COUNT = 320;
const easeOut = (t) => 1 - Math.pow(1 - t, 3);

export function mountHeroScene(canvas, stage) {
  const host = stage || canvas.parentElement;

  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: window.devicePixelRatio < 2,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0, 8.2);

  const root = new THREE.Group();
  root.scale.setScalar(0.82);
  scene.add(root);

  /* ── Lighting ── */
  scene.add(new THREE.AmbientLight(0x8fa2ff, 0.55));
  const key = new THREE.DirectionalLight(0xffffff, 1.15);
  key.position.set(3.5, 4.5, 5);
  scene.add(key);
  const violetLight = new THREE.PointLight(0x8b5cf6, 22, 14);
  violetLight.position.set(-3.2, 1.4, 2.2);
  scene.add(violetLight);
  const cyanLight = new THREE.PointLight(0x06b6d4, 16, 14);
  cyanLight.position.set(3.2, -2, 1.6);
  scene.add(cyanLight);

  /* ── Knowledge core ── */
  const coreGeometry = new THREE.IcosahedronGeometry(1.05, 1);
  const core = new THREE.Mesh(
    coreGeometry,
    new THREE.MeshStandardMaterial({
      color: 0x6d5cff,
      metalness: 0.45,
      roughness: 0.22,
      flatShading: true,
    })
  );
  root.add(core);

  const coreWire = new THREE.Mesh(
    coreGeometry,
    new THREE.MeshBasicMaterial({
      color: 0x67e8f9,
      wireframe: true,
      transparent: true,
      opacity: 0.28,
    })
  );
  coreWire.scale.setScalar(1.07);
  root.add(coreWire);

  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(1.62, 24, 16),
    new THREE.MeshBasicMaterial({
      color: 0x8b5cf6,
      transparent: true,
      opacity: 0.075,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
  );
  root.add(halo);

  /* ── Orbit rings ── */
  const ringGeometry = new THREE.TorusGeometry(2.05, 0.0075, 6, 120);
  const ringMaterial = new THREE.MeshBasicMaterial({
    color: 0x9db2ff,
    transparent: true,
    opacity: 0.32,
  });
  const ringA = new THREE.Mesh(ringGeometry, ringMaterial);
  ringA.rotation.set(Math.PI / 2.35, 0.2, 0);
  root.add(ringA);

  const ringB = new THREE.Mesh(ringGeometry, ringMaterial);
  ringB.rotation.set(Math.PI / 1.9, -0.5, 0.6);
  ringB.scale.setScalar(1.22);
  root.add(ringB);

  /* ── Floating documents (shared geometry/material = few draw calls) ── */
  const cardGeometry = new THREE.BoxGeometry(0.62, 0.84, 0.028);
  const cardMaterial = new THREE.MeshStandardMaterial({
    color: 0xe4eaff,
    metalness: 0.2,
    roughness: 0.18,
    transparent: true,
    opacity: 0.52,
  });
  const lineGeometry = new THREE.PlaneGeometry(0.34, 0.028);
  const lineMaterial = new THREE.MeshBasicMaterial({
    color: 0x7dd3fc,
    transparent: true,
    opacity: 0.75,
  });

  const linkMaterial = new THREE.LineBasicMaterial({
    color: 0x8ab4ff,
    transparent: true,
    opacity: 0.24,
  });
  const pulseGeometry = new THREE.SphereGeometry(0.045, 8, 8);
  const pulseMaterial = new THREE.MeshBasicMaterial({
    color: 0xa5f3fc,
    transparent: true,
    opacity: 0.95,
  });

  const docs = [];

  for (let i = 0; i < DOC_COUNT; i += 1) {
    const angle = (i / DOC_COUNT) * Math.PI * 2;
    const radius = 2.35 + (i % 2) * 0.35;
    const height = Math.sin(i * 1.7) * 0.75;

    const card = new THREE.Mesh(cardGeometry, cardMaterial);
    card.position.set(Math.cos(angle) * radius, height, Math.sin(angle) * radius);

    for (let row = 0; row < 3; row += 1) {
      const textLine = new THREE.Mesh(lineGeometry, lineMaterial);
      textLine.position.set(-0.04, 0.16 - row * 0.14, 0.02);
      textLine.scale.x = 1 - row * 0.25;
      card.add(textLine);
    }
    root.add(card);

    const link = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
      linkMaterial
    );
    root.add(link);

    const pulse = new THREE.Mesh(pulseGeometry, pulseMaterial);
    root.add(pulse);

    docs.push({ card, link, pulse, angle, radius, height, offset: i * 0.9 });
  }

  /* ── Particle field ── */
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const colors = new Float32Array(PARTICLE_COUNT * 3);
  const violet = new THREE.Color(0x8b5cf6);
  const cyan = new THREE.Color(0x22d3ee);

  for (let i = 0; i < PARTICLE_COUNT; i += 1) {
    const r = 2.8 + Math.random() * 3.4;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.cos(phi) * 0.6;
    positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);

    const tint = violet.clone().lerp(cyan, Math.random());
    colors[i * 3] = tint.r;
    colors[i * 3 + 1] = tint.g;
    colors[i * 3 + 2] = tint.b;
  }

  const particleGeometry = new THREE.BufferGeometry();
  particleGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  particleGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const particles = new THREE.Points(
    particleGeometry,
    new THREE.PointsMaterial({
      size: 0.032,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
  );
  scene.add(particles);

  /* ── Sizing ── */
  const resize = () => {
    const { clientWidth: width, clientHeight: height } = host;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };
  resize();

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(host);

  /* ── Pointer parallax ── */
  const pointer = { x: 0, y: 0 };
  const smoothed = { x: 0, y: 0 };
  const onPointerMove = (event) => {
    pointer.x = (event.clientX / window.innerWidth - 0.5) * 2;
    pointer.y = (event.clientY / window.innerHeight - 0.5) * 2;
  };
  window.addEventListener("pointermove", onPointerMove, { passive: true });

  /* ── Render loop (paused off-screen and on hidden tabs) ── */
  const clock = new THREE.Clock();
  let raf = 0;
  let intro = 0;
  let visible = true;

  const frame = () => {
    raf = requestAnimationFrame(frame);
    const delta = Math.min(clock.getDelta(), 0.05);
    const time = clock.elapsedTime;

    if (intro < 1) {
      intro = Math.min(intro + delta / 1.2, 1);
      const eased = easeOut(intro);
      root.scale.setScalar(0.82 + eased * 0.18);
      camera.position.z = 8.2 - eased * 1.8;
    }

    smoothed.x += (pointer.x - smoothed.x) * 0.045;
    smoothed.y += (pointer.y - smoothed.y) * 0.045;

    root.rotation.y = time * 0.12 + smoothed.x * 0.32;
    root.rotation.x = smoothed.y * 0.18;

    core.rotation.y += delta * 0.25;
    core.rotation.x += delta * 0.1;
    coreWire.rotation.y -= delta * 0.18;
    halo.scale.setScalar(1 + Math.sin(time * 1.4) * 0.03);

    ringA.rotation.z += delta * 0.08;
    ringB.rotation.z -= delta * 0.05;

    particles.rotation.y = time * 0.02;

    for (const doc of docs) {
      const { card, link, pulse } = doc;
      const angle = doc.angle + time * 0.16;
      card.position.set(
        Math.cos(angle) * doc.radius,
        doc.height + Math.sin(time * 0.8 + doc.offset) * 0.16,
        Math.sin(angle) * doc.radius
      );
      card.lookAt(camera.position);

      const points = link.geometry.attributes.position;
      const toCore = card.position.clone().setLength(1.15);
      points.setXYZ(0, toCore.x, toCore.y, toCore.z);
      points.setXYZ(1, card.position.x, card.position.y, card.position.z);
      points.needsUpdate = true;

      // Data flowing from the document into the core.
      const t = ((time * 0.42 + doc.offset * 0.2) % 1);
      pulse.position.lerpVectors(card.position, toCore, easeOut(t));
      pulse.scale.setScalar(0.6 + Math.sin(t * Math.PI) * 0.8);
    }

    renderer.render(scene, camera);
  };

  const start = () => {
    if (!raf && visible && !document.hidden) {
      clock.getDelta();
      raf = requestAnimationFrame(frame);
    }
  };
  const stop = () => {
    if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
  };

  const viewObserver = new IntersectionObserver(
    (entries) => {
      visible = entries[0].isIntersecting;
      visible ? start() : stop();
    },
    { threshold: 0.01 }
  );
  viewObserver.observe(host);

  const onVisibility = () => (document.hidden ? stop() : start());
  document.addEventListener("visibilitychange", onVisibility);

  host.classList.add("is-live");
  start();

  return function dispose() {
    stop();
    resizeObserver.disconnect();
    viewObserver.disconnect();
    window.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("visibilitychange", onVisibility);
    scene.traverse((object) => {
      if (object.isMesh || object.isLine || object.isPoints) {
        object.geometry?.dispose?.();
        const material = object.material;
        Array.isArray(material) ? material.forEach((m) => m.dispose()) : material?.dispose?.();
      }
    });
    renderer.dispose();
    host.classList.remove("is-live");
  };
}
