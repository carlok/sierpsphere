import * as THREE from "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.module.min.js";
import { buildOps, evalSDF, PRIMS } from "./sdf.js";
import { filterLargestComponent, marchingCubes } from "./marching-cubes.js";
import { renderHQSnapshot } from "./hq-snapshot.js";

const state = {
  activePreset: null,
  activeGrammar: null,
  customProfile: { seedType: "sphere", iterPrimitive: "sphere" },
  debounce: null,
};

const API_BASE = window.location.hostname === "localhost"
  ? "http://localhost:5000"
  : `http://${window.location.hostname}:5000`;

export function initViewer() {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  document.body.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a0f);
  const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.01, 100);

  scene.add(new THREE.AmbientLight(0xffffff, 0.35));
  const dir = new THREE.DirectionalLight(0xaaccff, 1.3);
  dir.position.set(3, 5, 4);
  scene.add(dir);
  const fill = new THREE.DirectionalLight(0xffaa66, 0.35);
  fill.position.set(-3, -2, -3);
  scene.add(fill);

  const meshMat = new THREE.MeshPhongMaterial({
    color: 0x2266dd, specular: 0x88aaff, shininess: 60, side: THREE.DoubleSide,
  });

  let currentMesh = null;
  let currentOps = [];
  let currentSeedFn = PRIMS.sphere;
  let currentSeedR = 1.0;
  let currentSeedC = [0, 0, 0];
  let needsRender = true;
  let isDragging = false;
  let prevMouse = { x: 0, y: 0 };
  const sph = { theta: 0.4, phi: 0.4, r: 3.5 };

  const presetBtn = document.getElementById("preset-btn");
  const presetDrop = document.getElementById("preset-dropdown");

  const setStatus = (msg) => { document.getElementById("status").textContent = msg; };

  const renderGrammarView = (grammar) => {
    const el = document.getElementById("grammar-view");
    if (!grammar?.iterations?.length) {
      el.textContent = "-";
      return;
    }
    el.innerHTML = grammar.iterations.map((it, i) => {
      const cls = it.operation === "subtract" ? "sub" : it.operation === "add" ? "add" : "int";
      return `<div class="iter-row">
        <span style="color:#446">Step ${i + 1}</span>
        <span class="tag ${cls}">${it.operation.toUpperCase()}</span>
        <span style="color:#557">${it.primitive || "sphere"} x${it.scale_factor}</span>
      </div>`;
    }).join("");
  };

  const grammarFromUI = () => {
    const sym = document.getElementById("sym-select").value;
    const iters = Number.parseInt(document.getElementById("iter-range").value, 10);
    const sf = Number.parseFloat(document.getElementById("sf-range").value);
    return {
      seed: { type: state.customProfile.seedType, radius: 1.0, center: [0, 0, 0] },
      symmetry_group: sym,
      iterations: Array.from({ length: iters }, (_, i) => ({
        operation: i % 2 === 0 ? "subtract" : "add",
        primitive: state.customProfile.iterPrimitive,
        scale_factor: sf,
        distance_factor: 1.0,
        smooth_radius: 0.02,
        apply_to: "new",
      })),
      render: { resolution: 128, bounds: 1.8 },
    };
  };

  const markCustomFromGrammar = (grammar) => {
    state.customProfile.seedType = grammar?.seed?.type || "sphere";
    state.customProfile.iterPrimitive = grammar?.iterations?.[0]?.primitive || "sphere";
  };

  const renderGrammar = (grammar) => {
    state.activeGrammar = grammar;
    if (currentMesh) {
      scene.remove(currentMesh);
      currentMesh.geometry.dispose();
      currentMesh = null;
    }

    const ops = buildOps(grammar);
    currentOps = ops;
    currentSeedR = grammar.seed.radius;
    currentSeedC = grammar.seed.center || [0, 0, 0];
    currentSeedFn = PRIMS[grammar.seed?.type || "sphere"] || PRIMS.sphere;
    const res = Number.parseInt(document.getElementById("res-range").value, 10);
    const bounds = grammar.render?.bounds ?? 1.8;

    setStatus(`Meshing ${ops.length} ops at ${res}^3...`);
    requestAnimationFrame(() => {
      const t0 = performance.now();
      const rawVerts = marchingCubes(
        (px, py, pz) => evalSDF(ops, currentSeedFn, currentSeedR, currentSeedC, px, py, pz),
        res,
        bounds,
      );
      const verts = filterLargestComponent(rawVerts);
      const dt = ((performance.now() - t0) / 1000).toFixed(2);

      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(verts, 3));
      geo.computeVertexNormals();
      currentMesh = new THREE.Mesh(geo, meshMat);
      scene.add(currentMesh);

      const triCount = verts.length / 9;
      document.getElementById("info").textContent = `${triCount.toLocaleString()} tris | ${ops.length} ops | ${dt}s | drag to orbit`;
      setStatus("");
      needsRender = true;
    });

    renderGrammarView(grammar);
  };

  const updateCamera = () => {
    camera.position.set(
      sph.r * Math.cos(sph.phi) * Math.sin(sph.theta),
      sph.r * Math.sin(sph.phi),
      sph.r * Math.cos(sph.phi) * Math.cos(sph.theta),
    );
    camera.lookAt(0, 0, 0);
  };

  const animate = () => {
    requestAnimationFrame(animate);
    if (!needsRender) return;
    updateCamera();
    renderer.render(scene, camera);
    needsRender = false;
  };

  const updateLabels = () => {
    document.getElementById("sym-val").textContent = document.getElementById("sym-select").value;
    document.getElementById("iter-val").textContent = document.getElementById("iter-range").value;
    document.getElementById("sf-val").textContent = Number.parseFloat(document.getElementById("sf-range").value).toFixed(2);
    document.getElementById("res-val").textContent = document.getElementById("res-range").value;
  };

  const queueApply = (clearPreset) => {
    if (clearPreset) {
      state.activePreset = null;
      document.getElementById("active-preset").textContent = "custom";
      presetDrop.querySelectorAll(".item").forEach((el) => el.classList.remove("active"));
    }
    clearTimeout(state.debounce);
    state.debounce = setTimeout(() => {
      renderGrammar(state.activeGrammar && !clearPreset ? state.activeGrammar : grammarFromUI());
    }, 350);
  };

  const loadPreset = async (name) => {
    presetDrop.classList.remove("open");
    setStatus(`Loading ${name}...`);
    try {
      const res = await fetch(`${API_BASE}/api/grammar/${name}`);
      const grammar = await res.json();
      state.activePreset = name;
      markCustomFromGrammar(grammar);
      document.getElementById("active-preset").textContent = name.replace(/_/g, " ");
      presetDrop.querySelectorAll(".item").forEach((el) => el.classList.toggle("active", el.dataset.name === name));
      renderGrammar(grammar);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  };

  const loadPresetList = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/grammar`);
      const names = await res.json();
      presetDrop.innerHTML = names.map((n) => `<div class="item" data-name="${n}">${n.replace(/_/g, " ")}</div>`).join("");
      presetDrop.querySelectorAll(".item").forEach((el) => el.addEventListener("click", () => loadPreset(el.dataset.name)));
      if (names.length > 0) loadPreset(names[0]);
    } catch {
      setStatus("API not reachable - using custom mode");
      renderGrammar(grammarFromUI());
    }
  };

  renderer.domElement.addEventListener("pointerdown", (e) => { isDragging = true; prevMouse = { x: e.clientX, y: e.clientY }; });
  renderer.domElement.addEventListener("pointerup", () => { isDragging = false; });
  renderer.domElement.addEventListener("pointermove", (e) => {
    if (!isDragging) return;
    sph.theta -= (e.clientX - prevMouse.x) * 0.005;
    sph.phi = Math.max(-1.4, Math.min(1.4, sph.phi + (e.clientY - prevMouse.y) * 0.005));
    prevMouse = { x: e.clientX, y: e.clientY };
    needsRender = true;
  });
  renderer.domElement.addEventListener("wheel", (e) => {
    e.preventDefault();
    sph.r = Math.max(1.0, Math.min(12, sph.r + e.deltaY * 0.005));
    needsRender = true;
  }, { passive: false });
  window.addEventListener("resize", () => {
    renderer.setSize(window.innerWidth, window.innerHeight);
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    needsRender = true;
  });

  presetBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    presetDrop.classList.toggle("open");
  });
  document.addEventListener("click", () => presetDrop.classList.remove("open"));

  for (const id of ["sym-select", "iter-range", "sf-range"]) {
    document.getElementById(id).addEventListener("input", updateLabels);
    document.getElementById(id).addEventListener("change", () => queueApply(true));
  }
  document.getElementById("res-range").addEventListener("input", updateLabels);
  document.getElementById("res-range").addEventListener("change", () => queueApply(false));

  document.getElementById("btn-apply").addEventListener("click", () => queueApply(true));
  document.getElementById("btn-mesh").addEventListener("click", async () => {
    const grammar = state.activePreset
      ? await fetch(`${API_BASE}/api/grammar/${state.activePreset}`).then((r) => r.json())
      : grammarFromUI();
    setStatus("Generating mesh...");
    try {
      const resp = await fetch(`${API_BASE}/api/mesh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(grammar),
      });
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${state.activePreset || "sierpsphere"}.glb`;
      a.click();
      URL.revokeObjectURL(url);
      setStatus("Downloaded.");
      setTimeout(() => setStatus(""), 3000);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  });

  document.getElementById("btn-snap").addEventListener("click", () => {
    renderHQSnapshot({ currentOps, activeGrammar: state.activeGrammar, currentSeedC, currentSeedR, camera, setStatus });
  });

  updateLabels();
  animate();
  loadPresetList();
}

