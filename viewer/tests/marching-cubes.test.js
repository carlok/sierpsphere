import { describe, expect, it } from "vitest";
import { marchingCubes } from "../js/marching-cubes.js";

describe("marching-cubes module", () => {
  it("produces triangles for a sphere SDF", () => {
    const sdf = (x, y, z) => Math.sqrt(x * x + y * y + z * z) - 0.7;
    const verts = marchingCubes(sdf, 16, 1.2);
    expect(verts.length).toBeGreaterThan(0);
    expect(verts.length % 9).toBe(0);
  });
});

