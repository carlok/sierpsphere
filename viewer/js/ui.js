import { THREE } from "./three-adapter.js";
import { buildOps, evalSDF, PRIMS } from "./sdf.js";
import { filterLargestComponent, marchingCubes } from "./marching-cubes.js";
import { renderHQSnapshot, MATERIALS } from "./hq-snapshot.js";

const state = {
  activePreset: null,
  activeGrammar: null,
  customProfile: {
    seedType: "sphere",
    iterPrimitive: "sphere",
    opTemplate: ["subtract", "add", "subtract"],
    smoothTemplate: [0.02, 0.01, 0.005],
  },
  debounce: null,
};

const API_BASE = window.location.hostname === "localhost"
  ? "http://localhost:5000"
  : `http://${window.location.hostname}:5000`;
const GPU_GUARD = {
  maxOpsRealtime: 1400,
  maxOpsSnapshot: 900,
  maxResolution: 96,
  safeResolution: 64,
};

export function initViewer() {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  document.body.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a0f);
  const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.01, 100);

  scene.add(new THREE.AmbientLight(0xffffff, 0.25));
  const dir = new THREE.DirectionalLight(0xfff5e0, 2.2);
  dir.position.set(3, 5, 4);
  scene.add(dir);
  const fill = new THREE.DirectionalLight(0x8ab0ff, 0.6);
  fill.position.set(-3, -2, -3);
  scene.add(fill);

  let needsRender = true;

  const meshMat = new THREE.MeshStandardMaterial({ side: THREE.DoubleSide });

  const applyMaterial = (key) => {
    const m = MATERIALS[key] || MATERIALS.bronze;
    meshMat.color.setRGB(...m.albedo);
    meshMat.metalness = m.metallic;
    meshMat.roughness = m.roughness;
    meshMat.needsUpdate = true;
    needsRender = true;
  };

  applyMaterial(document.getElementById("mat-select")?.value || "bronze");

  let currentMesh = null;
  let currentOps = [];
  let currentSeedFn = PRIMS.sphere;
  let currentSeedR = 1.0;
  let currentSeedC = [0, 0, 0];
  let isDragging = false;
  let prevMouse = { x: 0, y: 0 };
  const sph = { theta: 0.4, phi: 0.4, r: 3.5 };

  const presetBtn = document.getElementById("preset-btn");
  const presetDrop = document.getElementById("preset-dropdown");

  const setStatus = (msg) => { document.getElementById("status").textContent = msg; };
  const opChoices = ["subtract", "add", "intersect"];
  const primChoices = ["sphere", "cube", "octahedron"];
  const applyChoices = ["new", "all", "surface"];

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

  const normalizeIteration = (it, defaults) => ({
    operation: opChoices.includes(it?.operation) ? it.operation : defaults.operation,
    primitive: primChoices.includes(it?.primitive) ? it.primitive : defaults.primitive,
    scale_factor: Number.isFinite(Number(it?.scale_factor)) ? Number(it.scale_factor) : defaults.scale_factor,
    distance_factor: Number.isFinite(Number(it?.distance_factor)) ? Number(it.distance_factor) : defaults.distance_factor,
    smooth_radius: Number.isFinite(Number(it?.smooth_radius)) ? Number(it.smooth_radius) : defaults.smooth_radius,
    apply_to: applyChoices.includes(it?.apply_to) ? it.apply_to : defaults.apply_to,
  });

  const grammarFromUI = () => {
    const sym = document.getElementById("sym-select").value;
    const iters = Number.parseInt(document.getElementById("iter-range").value, 10);
    const sf = Number.parseFloat(document.getElementById("sf-range").value);
    const res = Number.parseInt(document.getElementById("res-range").value, 10);
    const opTemplate = state.customProfile.opTemplate.length
      ? state.customProfile.opTemplate
      : ["subtract", "add", "subtract"];
    const smoothTemplate = state.customProfile.smoothTemplate.length
      ? state.customProfile.smoothTemplate
      : [0.02, 0.01, 0.005];
    const decay = 0.6;
    const defaults = {
      operation: "subtract",
      primitive: state.customProfile.iterPrimitive,
      scale_factor: sf,
      distance_factor: 1.0,
      smooth_radius: 0.02,
      apply_to: "new",
    };
    return {
      seed: { type: state.customProfile.seedType, radius: 1.0, center: [0, 0, 0] },
      symmetry_group: sym,
      iterations: Array.from({ length: iters }, (_, i) => {
        const templateOp = i < opTemplate.length ? opTemplate[i] : opTemplate[opTemplate.length - 1];
        const templateSmooth = i < smoothTemplate.length
          ? smoothTemplate[i]
          : smoothTemplate[smoothTemplate.length - 1] * (decay ** (i - smoothTemplate.length + 1));
        return normalizeIteration({
          operation: templateOp,
          primitive: state.customProfile.iterPrimitive,
          scale_factor: sf,
          distance_factor: 1.0,
          smooth_radius: Number(templateSmooth.toFixed(6)),
          apply_to: "new",
        }, defaults);
      }),
      render: { resolution: res, bounds: 1.8 },
    };
  };

  const markCustomFromGrammar = (grammar) => {
    state.customProfile.seedType = grammar?.seed?.type || "sphere";
    state.customProfile.iterPrimitive = grammar?.iterations?.[0]?.primitive || "sphere";
    const iters = grammar?.iterations || [];
    state.customProfile.opTemplate = iters.length ? iters.map((it) => it.operation || "subtract") : ["subtract", "add", "subtract"];
    state.customProfile.smoothTemplate = iters.length ? iters.map((it) => Number(it.smooth_radius ?? 0.0)) : [0.02, 0.01, 0.005];
  };

  const renderJSONView = (grammar) => {
    const el = document.getElementById("grammar-json");
    el.textContent = `${JSON.stringify(grammar, null, 2)}\n`;
  };

  const renderStepEditor = (grammar) => {
    const body = document.getElementById("step-body");
    const rows = grammar.iterations || [];
    body.innerHTML = rows.map((it, i) => `
      <tr data-idx="${i}">
        <td><select data-field="operation">${opChoices.map((v) => `<option value="${v}" ${it.operation === v ? "selected" : ""}>${v}</option>`).join("")}</select></td>
        <td><select data-field="primitive">${primChoices.map((v) => `<option value="${v}" ${it.primitive === v ? "selected" : ""}>${v}</option>`).join("")}</select></td>
        <td><input data-field="scale_factor" type="number" min="0.05" max="1.0" step="0.01" value="${it.scale_factor}"></td>
        <td><input data-field="distance_factor" type="number" min="0.0" max="2.0" step="0.01" value="${it.distance_factor ?? 1.0}"></td>
        <td><input data-field="smooth_radius" type="number" min="0.0" max="1.0" step="0.001" value="${it.smooth_radius ?? 0.0}"></td>
        <td><select data-field="apply_to">${applyChoices.map((v) => `<option value="${v}" ${it.apply_to === v ? "selected" : ""}>${v}</option>`).join("")}</select></td>
        <td><div class="row-actions">
          <button data-act="up">&#8593;</button>
          <button data-act="down">&#8595;</button>
          <button data-act="dup">+</button>
          <button data-act="del">x</button>
        </div></td>
      </tr>
    `).join("");
  };

  const syncEditorIntoActiveGrammar = () => {
    if (!state.activeGrammar) return;
    const rows = [...document.querySelectorAll("#step-body tr")];
    const defaults = {
      operation: "subtract",
      primitive: state.customProfile.iterPrimitive,
      scale_factor: Number.parseFloat(document.getElementById("sf-range").value),
      distance_factor: 1.0,
      smooth_radius: 0.02,
      apply_to: "new",
    };
    state.activeGrammar.iterations = rows.map((row) => {
      const valueFor = (field) => row.querySelector(`[data-field="${field}"]`)?.value;
      return normalizeIteration({
        operation: valueFor("operation"),
        primitive: valueFor("primitive"),
        scale_factor: Number.parseFloat(valueFor("scale_factor")),
        distance_factor: Number.parseFloat(valueFor("distance_factor")),
        smooth_radius: Number.parseFloat(valueFor("smooth_radius")),
        apply_to: valueFor("apply_to"),
      }, defaults);
    });
    document.getElementById("iter-range").value = String(state.activeGrammar.iterations.length);
    document.getElementById("iter-val").textContent = String(state.activeGrammar.iterations.length);
    renderGrammarView(state.activeGrammar);
    renderJSONView(state.activeGrammar);
  };

  const renderGrammar = (grammar) => {
    state.activeGrammar = {
      ...grammar,
      iterations: [...(grammar.iterations || [])].map((it) => ({ ...it })),
      seed: { ...grammar.seed },
      render: { ...(grammar.render || {}) },
    };
    if (currentMesh) {
      scene.remove(currentMesh);
      currentMesh.geometry.dispose();
      currentMesh = null;
    }

    const ops = buildOps(state.activeGrammar);
    currentOps = ops;
    currentSeedR = state.activeGrammar.seed.radius;
    currentSeedC = state.activeGrammar.seed.center || [0, 0, 0];
    currentSeedFn = PRIMS[state.activeGrammar.seed?.type || "sphere"] || PRIMS.sphere;
    let res = Number.parseInt(document.getElementById("res-range").value, 10);
    const bounds = state.activeGrammar.render?.bounds ?? 1.8;

    if (res > GPU_GUARD.maxResolution) {
      res = GPU_GUARD.safeResolution;
      document.getElementById("res-range").value = String(res);
      updateLabels();
      setStatus(`Safe mode: clamped resolution to ${res}.`);
    }
    if (ops.length > GPU_GUARD.maxOpsRealtime) {
      setStatus(`Safety stop: ${ops.length} ops too heavy for realtime.`);
      document.getElementById("info").textContent = `${ops.length.toLocaleString()} ops blocked (GPU safety)`;
      renderGrammarView(state.activeGrammar);
      renderStepEditor(state.activeGrammar);
      renderJSONView(state.activeGrammar);
      return;
    }

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

    renderGrammarView(state.activeGrammar);
    renderStepEditor(state.activeGrammar);
    renderJSONView(state.activeGrammar);
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
      if (state.activeGrammar && !clearPreset) {
        syncEditorIntoActiveGrammar();
        renderGrammar(state.activeGrammar);
      } else {
        renderGrammar(grammarFromUI());
      }
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
  document.getElementById("mat-select")?.addEventListener("change", (e) => applyMaterial(e.target.value));

  document.getElementById("btn-apply").addEventListener("click", () => queueApply(true));
  document.getElementById("btn-save").addEventListener("click", () => {
    syncEditorIntoActiveGrammar();
    const grammar = state.activeGrammar || grammarFromUI();
    const payload = `${JSON.stringify(grammar, null, 2)}\n`;
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const base = state.activePreset ? state.activePreset : "sierpsphere_custom";
    a.href = url;
    a.download = `${base}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setStatus("Grammar JSON saved.");
    setTimeout(() => setStatus(""), 2500);
  });
  document.getElementById("btn-mesh").addEventListener("click", async () => {
    syncEditorIntoActiveGrammar();
    const grammar = state.activeGrammar || grammarFromUI();
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
    const opsForCheck = currentOps.length
      ? currentOps.length
      : (state.activeGrammar ? buildOps(state.activeGrammar).length : 0);
    if (opsForCheck > GPU_GUARD.maxOpsSnapshot) {
      setStatus(`Snapshot blocked: ${opsForCheck} ops exceeds safety limit.`);
      return;
    }
    const materialKey = document.getElementById("mat-select")?.value || "bronze";
    renderHQSnapshot({ currentOps, activeGrammar: state.activeGrammar, currentSeedC, currentSeedR, camera, setStatus, materialKey });
  });

  document.getElementById("step-body").addEventListener("change", () => {
    state.activePreset = null;
    document.getElementById("active-preset").textContent = "custom";
    syncEditorIntoActiveGrammar();
  });

  document.getElementById("step-body").addEventListener("click", (evt) => {
    const button = evt.target.closest("button[data-act]");
    if (!button) return;
    const row = button.closest("tr");
    const idx = Number.parseInt(row?.dataset?.idx || "-1", 10);
    if (!state.activeGrammar || idx < 0) return;
    const arr = state.activeGrammar.iterations;
    const act = button.dataset.act;
    if (act === "up" && idx > 0) [arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]];
    if (act === "down" && idx < arr.length - 1) [arr[idx + 1], arr[idx]] = [arr[idx], arr[idx + 1]];
    if (act === "dup") arr.splice(idx + 1, 0, { ...arr[idx] });
    if (act === "del" && arr.length > 1) arr.splice(idx, 1);
    document.getElementById("iter-range").value = String(arr.length);
    updateLabels();
    renderStepEditor(state.activeGrammar);
    renderGrammarView(state.activeGrammar);
    renderJSONView(state.activeGrammar);
    state.activePreset = null;
    document.getElementById("active-preset").textContent = "custom";
  });

  document.getElementById("btn-add-step").addEventListener("click", () => {
    if (!state.activeGrammar) state.activeGrammar = grammarFromUI();
    const last = state.activeGrammar.iterations[state.activeGrammar.iterations.length - 1];
    const defaults = {
      operation: "subtract",
      primitive: state.customProfile.iterPrimitive,
      scale_factor: Number.parseFloat(document.getElementById("sf-range").value),
      distance_factor: 1.0,
      smooth_radius: 0.02,
      apply_to: "new",
    };
    state.activeGrammar.iterations.push(normalizeIteration(last || defaults, defaults));
    document.getElementById("iter-range").value = String(state.activeGrammar.iterations.length);
    updateLabels();
    renderStepEditor(state.activeGrammar);
    renderGrammarView(state.activeGrammar);
    renderJSONView(state.activeGrammar);
    state.activePreset = null;
    document.getElementById("active-preset").textContent = "custom";
  });

  updateLabels();
  animate();
  loadPresetList();
}

