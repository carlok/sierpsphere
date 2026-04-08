export const SYM = {
  tetrahedral() {
    const s = 1 / Math.sqrt(3);
    return [[s, s, s], [s, -s, -s], [-s, s, -s], [-s, -s, s]];
  },
  octahedral() {
    return [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
  },
  icosahedral() {
    const phi = (1 + Math.sqrt(5)) / 2;
    const v = [];
    for (const s1 of [-1, 1]) {
      for (const s2 of [-1, 1]) {
        v.push([0, s1, s2 * phi], [s1, s2 * phi, 0], [s2 * phi, 0, s1]);
      }
    }
    const len = Math.sqrt(1 + phi * phi);
    return v.map((p) => p.map((c) => c / len));
  },
};

export function sdfSphere(px, py, pz, cx, cy, cz, r) {
  const dx = px - cx;
  const dy = py - cy;
  const dz = pz - cz;
  return Math.sqrt(dx * dx + dy * dy + dz * dz) - r;
}

export function sdfCube(px, py, pz, cx, cy, cz, halfExtent) {
  const qx = Math.abs(px - cx) - halfExtent;
  const qy = Math.abs(py - cy) - halfExtent;
  const qz = Math.abs(pz - cz) - halfExtent;
  const ox = Math.max(qx, 0);
  const oy = Math.max(qy, 0);
  const oz = Math.max(qz, 0);
  return Math.sqrt(ox * ox + oy * oy + oz * oz) + Math.min(Math.max(qx, Math.max(qy, qz)), 0);
}

export function sdfOctahedron(px, py, pz, cx, cy, cz, r) {
  return (Math.abs(px - cx) + Math.abs(py - cy) + Math.abs(pz - cz) - r) * (1 / Math.sqrt(3));
}

export function smoothUnion(d1, d2, k) {
  if (k <= 0) return Math.min(d1, d2);
  const h = Math.max(0, Math.min(1, 0.5 + 0.5 * (d2 - d1) / k));
  return d2 * (1 - h) + d1 * h - k * h * (1 - h);
}

export function smoothSub(d1, d2, k) {
  if (k <= 0) return Math.max(-d1, d2);
  const h = Math.max(0, Math.min(1, 0.5 - 0.5 * (d2 + d1) / k));
  return d2 * (1 - h) + (-d1) * h + k * h * (1 - h);
}

export function smoothIntersect(d1, d2, k) {
  if (k <= 0) return Math.max(d1, d2);
  const h = Math.max(0, Math.min(1, 0.5 - 0.5 * (d2 - d1) / k));
  return d2 * (1 - h) + d1 * h + k * h * (1 - h);
}

export const PRIMS = { sphere: sdfSphere, cube: sdfCube, octahedron: sdfOctahedron };
const BOOL_OPS = { subtract: smoothSub, add: smoothUnion, intersect: smoothIntersect };

export function buildOps(grammar) {
  const verts = SYM[grammar.symmetry_group || "tetrahedral"]();
  const iters = grammar.iterations || [];
  const ops = [];
  const seedType = grammar.seed?.type || "sphere";
  const seedFn = PRIMS[seedType] || sdfSphere;
  const seedC = grammar.seed.center || [0, 0, 0];
  const seedR = grammar.seed.radius;
  let allNodes = [{ cx: seedC[0], cy: seedC[1], cz: seedC[2], r: seedR }];
  let newNodes = [{ cx: seedC[0], cy: seedC[1], cz: seedC[2], r: seedR }];

  const evalAt = (x, y, z) => evalSDF(ops, seedFn, seedR, seedC, x, y, z);

  for (const it of iters) {
    const boolFn = BOOL_OPS[it.operation];
    const primName = it.primitive || "sphere";
    const sdfFn = PRIMS[primName] || sdfSphere;
    const sf = it.scale_factor;
    const df = it.distance_factor ?? 1.0;
    const sk = it.smooth_radius ?? 0.0;
    let sourceNodes;
    const applyTo = it.apply_to || "all";
    if (applyTo === "all") {
      sourceNodes = allNodes;
    } else if (applyTo === "surface") {
      sourceNodes = allNodes.filter((n) => Math.abs(evalAt(n.cx, n.cy, n.cz)) <= n.r * 0.25);
    } else {
      sourceNodes = newNodes;
    }
    const nextNodes = [];

    for (const p of sourceNodes) {
      const childR = p.r * sf;
      for (const v of verts) {
        const cx = p.cx + v[0] * p.r * df;
        const cy = p.cy + v[1] * p.r * df;
        const cz = p.cz + v[2] * p.r * df;

        if (it.operation === "add") {
          const d = evalSDF(ops, seedFn, seedR, seedC, cx, cy, cz);
          if (d > childR * 0.5) continue;
        }

        ops.push({ boolFn, sdfFn, prim: primName, cx, cy, cz, r: childR, k: sk });
        nextNodes.push({ cx, cy, cz, r: childR });
      }
    }

    allNodes = allNodes.concat(nextNodes);
    newNodes = nextNodes;
  }

  return ops;
}

export function evalSDF(ops, seedFn, seedR, seedC, px, py, pz) {
  let d = seedFn(px, py, pz, seedC[0], seedC[1], seedC[2], seedR);
  for (const o of ops) {
    const dc = o.sdfFn(px, py, pz, o.cx, o.cy, o.cz, o.r);
    d = o.boolFn(dc, d, o.k);
  }
  return d;
}

