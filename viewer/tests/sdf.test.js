import { describe, expect, it } from "vitest";
import { buildOps, evalSDF, PRIMS } from "../js/sdf.js";

describe("sdf module", () => {
  it("builds cube operations from cube grammar", () => {
    const grammar = {
      seed: { type: "cube", radius: 1, center: [0, 0, 0] },
      symmetry_group: "tetrahedral",
      iterations: [
        { operation: "subtract", primitive: "cube", scale_factor: 0.5, distance_factor: 1, smooth_radius: 0.02, apply_to: "new" },
      ],
    };
    const ops = buildOps(grammar);
    expect(ops.length).toBeGreaterThan(0);
    expect(ops[0].prim).toBe("cube");
  });

  it("evaluates seed as cube when cube selected", () => {
    const ops = [];
    const seedR = 1;
    const seedC = [0, 0, 0];
    const dInside = evalSDF(ops, PRIMS.cube, seedR, seedC, 0, 0, 0);
    const dOutside = evalSDF(ops, PRIMS.cube, seedR, seedC, 2, 0, 0);
    expect(dInside).toBeLessThan(0);
    expect(dOutside).toBeGreaterThan(0);
  });
});

