// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { renderHQSnapshot } from "../js/hq-snapshot.js";

function makeFakeGL() {
  return {
    VERTEX_SHADER: 1,
    FRAGMENT_SHADER: 2,
    ARRAY_BUFFER: 3,
    STATIC_DRAW: 4,
    TRIANGLE_STRIP: 5,
    COMPILE_STATUS: 6,
    createShader: vi.fn(() => ({})),
    shaderSource: vi.fn(),
    compileShader: vi.fn(),
    getShaderParameter: vi.fn(() => true),
    createProgram: vi.fn(() => ({})),
    attachShader: vi.fn(),
    linkProgram: vi.fn(),
    useProgram: vi.fn(),
    createBuffer: vi.fn(() => ({})),
    bindBuffer: vi.fn(),
    bufferData: vi.fn(),
    getAttribLocation: vi.fn(() => 0),
    enableVertexAttribArray: vi.fn(),
    vertexAttribPointer: vi.fn(),
    getUniformLocation: vi.fn(() => ({})),
    uniform2f: vi.fn(),
    uniformMatrix4fv: vi.fn(),
    viewport: vi.fn(),
    drawArrays: vi.fn(),
    finish: vi.fn(),
    deleteProgram: vi.fn(),
    deleteShader: vi.fn(),
    deleteBuffer: vi.fn(),
  };
}

describe("hq-snapshot", () => {
  it("reports nothing to render when ops are empty", () => {
    const setStatus = vi.fn();
    renderHQSnapshot({
      currentOps: [],
      activeGrammar: null,
      currentSeedC: [0, 0, 0],
      currentSeedR: 1,
      camera: {},
      setStatus,
    });
    expect(setStatus).toHaveBeenCalledWith("Nothing to render");
  });

  it("runs snapshot flow and reports saved", () => {
    const fakeGL = makeFakeGL();
    const fakeCanvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => fakeGL),
      toBlob: vi.fn((cb) => cb(new Blob(["x"], { type: "image/png" }))),
    };
    const originalCreateElement = document.createElement.bind(document);
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag === "canvas") return fakeCanvas;
      if (tag === "a") return { click: vi.fn() };
      return originalCreateElement(tag);
    });
    const oldRAF = window.requestAnimationFrame;
    window.requestAnimationFrame = (cb) => cb();
    const oldCreateObjectURL = URL.createObjectURL;
    const oldRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => "blob:test");
    URL.revokeObjectURL = vi.fn();

    const camera = {
      aspect: 1,
      updateProjectionMatrix: vi.fn(),
      updateMatrixWorld: vi.fn(),
      projectionMatrixInverse: { elements: new Float32Array(16) },
      matrixWorld: { elements: new Float32Array(16) },
    };
    const setStatus = vi.fn();
    renderHQSnapshot({
      currentOps: [{ boolFn: () => 0, prim: "sphere", cx: 0, cy: 0, cz: 0, r: 0.5, k: 0.01 }],
      activeGrammar: { seed: { type: "sphere" } },
      currentSeedC: [0, 0, 0],
      currentSeedR: 1,
      camera,
      setStatus,
    });

    expect(setStatus).toHaveBeenCalledWith("Rendering HQ snapshot...");
    expect(setStatus).toHaveBeenCalledWith("Snapshot saved.");

    window.requestAnimationFrame = oldRAF;
    URL.createObjectURL = oldCreateObjectURL;
    URL.revokeObjectURL = oldRevokeObjectURL;
    createElement.mockRestore();
  });
});

