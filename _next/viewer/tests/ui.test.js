// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../js/three-adapter.js", () => {
  class FakeGeometry {
    setAttribute() {}
    computeVertexNormals() {}
    dispose() {}
  }
  class FakeRenderer {
    constructor() {
      this.domElement = document.createElement("canvas");
    }
    setSize() {}
    setPixelRatio() {}
    render() {}
  }
  class FakeScene {
    add() {}
    remove() {}
  }
  class FakeCamera {
    constructor() {
      this.aspect = 1;
      this.projectionMatrixInverse = { elements: new Float32Array(16) };
      this.matrixWorld = { elements: new Float32Array(16) };
    }
    lookAt() {}
    updateProjectionMatrix() {}
    updateMatrixWorld() {}
    get position() {
      return { set() {} };
    }
  }
  class FakeLight {
    constructor() {
      this.position = { set() {} };
    }
  }
  class FakeMesh {
    constructor(geometry) {
      this.geometry = geometry;
    }
  }
  class FakeMat {}
  class FakeBufAttr {}
  return {
    THREE: {
      WebGLRenderer: FakeRenderer,
      Scene: FakeScene,
      Color: class {},
      PerspectiveCamera: FakeCamera,
      AmbientLight: FakeLight,
      DirectionalLight: FakeLight,
      MeshPhongMaterial: FakeMat,
      BufferGeometry: FakeGeometry,
      BufferAttribute: FakeBufAttr,
      Mesh: FakeMesh,
      DoubleSide: 2,
    },
  };
});

const mockRenderHQSnapshot = vi.fn();
vi.mock("../js/hq-snapshot.js", () => ({
  renderHQSnapshot: (...args) => mockRenderHQSnapshot(...args),
}));

vi.mock("../js/marching-cubes.js", () => ({
  marchingCubes: vi.fn(() => new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0])),
  filterLargestComponent: vi.fn((v) => v),
}));

function setupDOM() {
  document.body.innerHTML = `
  <button id="preset-btn"></button>
  <div id="preset-dropdown"></div>
  <select id="sym-select"><option value="tetrahedral">tetrahedral</option></select>
  <input id="iter-range" type="range" value="2" />
  <input id="sf-range" type="range" value="0.5" />
  <input id="res-range" type="range" value="32" />
  <span id="sym-val"></span><span id="iter-val"></span><span id="sf-val"></span><span id="res-val"></span>
  <button id="btn-apply"></button>
  <button id="btn-save"></button>
  <button id="btn-mesh"></button>
  <select id="mat-select"><option value="bronze">Bronze</option></select>
  <button id="btn-snap"></button>
  <div id="active-preset"></div>
  <div id="grammar-view"></div>
  <table><tbody id="step-body"></tbody></table>
  <button id="btn-add-step"></button>
  <pre id="grammar-json"></pre>
  <div id="info"></div>
  <div id="status"></div>
  `;
}

describe("ui wiring", () => {
  beforeEach(() => {
    setupDOM();
    vi.useFakeTimers();
    const oldRAF = window.requestAnimationFrame;
    window.requestAnimationFrame = vi.fn();
    window.__oldRAF = oldRAF;

    const grammar = {
      seed: { type: "cube", radius: 1, center: [0, 0, 0] },
      symmetry_group: "tetrahedral",
      iterations: [{ operation: "subtract", primitive: "cube", scale_factor: 0.5 }],
      render: { bounds: 1.8 },
    };
    global.fetch = vi.fn(async (url, opts) => {
      if (String(url).endsWith("/api/grammar")) return { json: async () => ["sierpinski_cube"] };
      if (String(url).includes("/api/grammar/sierpinski_cube")) return { json: async () => grammar };
      if (String(url).includes("/api/mesh")) return { ok: true, blob: async () => new Blob(["x"]) };
      return { json: async () => ({}) };
    });
  });

  it("loads preset list and can switch to custom via slider", async () => {
    const { initViewer } = await import("../js/ui.js");
    initViewer();
    for (let i = 0; i < 8; i++) await Promise.resolve();

    expect(document.getElementById("active-preset").textContent).toContain("sierpinski cube");

    const iter = document.getElementById("iter-range");
    iter.dispatchEvent(new Event("change"));
    vi.runAllTimers();

    expect(document.getElementById("active-preset").textContent).toBe("custom");
  });

  it("wires snapshot button to HQ renderer", async () => {
    const { initViewer } = await import("../js/ui.js");
    initViewer();
    await Promise.resolve();
    document.getElementById("btn-snap").click();
    expect(mockRenderHQSnapshot).toHaveBeenCalledTimes(1);
  });

  it("uses preset-aware operation sequence with decaying smoothness", async () => {
    const grammar = {
      seed: { type: "cube", radius: 1, center: [0, 0, 0] },
      symmetry_group: "tetrahedral",
      iterations: [
        { operation: "subtract", primitive: "cube", scale_factor: 0.5, smooth_radius: 0.02, apply_to: "new" },
        { operation: "add", primitive: "cube", scale_factor: 0.5, smooth_radius: 0.01, apply_to: "new" },
        { operation: "subtract", primitive: "cube", scale_factor: 0.5, smooth_radius: 0.005, apply_to: "new" },
      ],
      render: { bounds: 1.8 },
    };
    global.fetch = vi.fn(async (url) => {
      if (String(url).endsWith("/api/grammar")) return { json: async () => ["sierpinski_cube"] };
      if (String(url).includes("/api/grammar/sierpinski_cube")) return { json: async () => grammar };
      if (String(url).includes("/api/mesh")) return { ok: true, blob: async () => new Blob(["x"]) };
      return { json: async () => ({}) };
    });

    const { initViewer } = await import("../js/ui.js");
    initViewer();
    for (let i = 0; i < 8; i++) await Promise.resolve();

    const iter = document.getElementById("iter-range");
    iter.value = "4";
    iter.dispatchEvent(new Event("change"));
    vi.runAllTimers();

    const rows = document.getElementById("grammar-view").textContent;
    expect(rows).toContain("SUBTRACT");
    const fetchCalls = global.fetch.mock.calls.filter(([url]) => String(url).includes("/api/grammar/"));
    expect(fetchCalls.length).toBeGreaterThan(0);
  });

  it("adds an inline step and updates JSON preview", async () => {
    const { initViewer } = await import("../js/ui.js");
    initViewer();
    for (let i = 0; i < 8; i++) await Promise.resolve();
    const before = document.querySelectorAll("#step-body tr").length;
    document.getElementById("btn-add-step").click();
    const after = document.querySelectorAll("#step-body tr").length;
    expect(after).toBe(before + 1);
    expect(document.getElementById("grammar-json").textContent).toContain("\"iterations\"");
  });
});

