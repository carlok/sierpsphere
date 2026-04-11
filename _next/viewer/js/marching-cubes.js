// Local polygonization via marching tetrahedra (cube split into 6 tetrahedra).

const CORNER = [
  [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
];

const TETS = [
  [0, 5, 1, 6],
  [0, 1, 2, 6],
  [0, 2, 3, 6],
  [0, 3, 7, 6],
  [0, 7, 4, 6],
  [0, 4, 5, 6],
];

const TET_EDGES = [
  [0, 1], [1, 2], [2, 0],
  [0, 3], [1, 3], [2, 3],
];

function interp(p1, p2, v1, v2) {
  if (Math.abs(v1) < 1e-6) return p1;
  if (Math.abs(v2) < 1e-6) return p2;
  const t = -v1 / (v2 - v1);
  return [
    p1[0] + t * (p2[0] - p1[0]),
    p1[1] + t * (p2[1] - p1[1]),
    p1[2] + t * (p2[2] - p1[2]),
  ];
}

function polygonizeTetra(positions, tetPoints, tetVals) {
  const inter = [];
  for (const [a, b] of TET_EDGES) {
    const va = tetVals[a];
    const vb = tetVals[b];
    if ((va < 0) !== (vb < 0)) inter.push(interp(tetPoints[a], tetPoints[b], va, vb));
  }

  if (inter.length === 3) {
    positions.push(
      inter[0][0], inter[0][1], inter[0][2],
      inter[1][0], inter[1][1], inter[1][2],
      inter[2][0], inter[2][1], inter[2][2],
    );
  } else if (inter.length === 4) {
    positions.push(
      inter[0][0], inter[0][1], inter[0][2],
      inter[1][0], inter[1][1], inter[1][2],
      inter[2][0], inter[2][1], inter[2][2],
      inter[0][0], inter[0][1], inter[0][2],
      inter[2][0], inter[2][1], inter[2][2],
      inter[3][0], inter[3][1], inter[3][2],
    );
  }
}

export function marchingCubes(sdfFn, res, bounds) {
  const step = (2 * bounds) / res;
  const s1 = res + 1;
  const grid = new Float32Array(s1 * s1 * s1);
  const idx = (ix, iy, iz) => iz * s1 * s1 + iy * s1 + ix;

  for (let iz = 0; iz <= res; iz++) {
    const pz = -bounds + iz * step;
    for (let iy = 0; iy <= res; iy++) {
      const py = -bounds + iy * step;
      for (let ix = 0; ix <= res; ix++) {
        const px = -bounds + ix * step;
        grid[idx(ix, iy, iz)] = sdfFn(px, py, pz);
      }
    }
  }

  const positions = [];
  for (let iz = 0; iz < res; iz++) {
    for (let iy = 0; iy < res; iy++) {
      for (let ix = 0; ix < res; ix++) {
        const cubePoints = new Array(8);
        const cubeVals = new Array(8);
        for (let c = 0; c < 8; c++) {
          const cx = ix + CORNER[c][0];
          const cy = iy + CORNER[c][1];
          const cz = iz + CORNER[c][2];
          cubePoints[c] = [-bounds + cx * step, -bounds + cy * step, -bounds + cz * step];
          cubeVals[c] = grid[idx(cx, cy, cz)];
        }

        for (const t of TETS) {
          const tetPoints = [cubePoints[t[0]], cubePoints[t[1]], cubePoints[t[2]], cubePoints[t[3]]];
          const tetVals = [cubeVals[t[0]], cubeVals[t[1]], cubeVals[t[2]], cubeVals[t[3]]];
          polygonizeTetra(positions, tetPoints, tetVals);
        }
      }
    }
  }

  return new Float32Array(positions);
}

export function filterLargestComponent(flat) {
  const nTri = flat.length / 9;
  if (nTri === 0) return flat;

  const vertMap = new Map();
  const triVerts = new Int32Array(nTri * 3);
  let nextId = 0;
  for (let t = 0; t < nTri; t++) {
    for (let v = 0; v < 3; v++) {
      const b = t * 9 + v * 3;
      const key = `${(flat[b] * 2e4 + 0.5) | 0},${(flat[b + 1] * 2e4 + 0.5) | 0},${(flat[b + 2] * 2e4 + 0.5) | 0}`;
      let id = vertMap.get(key);
      if (id === undefined) {
        id = nextId++;
        vertMap.set(key, id);
      }
      triVerts[t * 3 + v] = id;
    }
  }

  const vertTris = Array.from({ length: nextId }, () => []);
  for (let t = 0; t < nTri; t++) {
    for (let v = 0; v < 3; v++) vertTris[triVerts[t * 3 + v]].push(t);
  }

  const comp = new Int32Array(nTri).fill(-1);
  const compSizes = [];
  for (let start = 0; start < nTri; start++) {
    if (comp[start] !== -1) continue;
    const c = compSizes.length;
    const queue = [start];
    comp[start] = c;
    let size = 0;
    while (queue.length) {
      const t = queue.pop();
      size++;
      for (let v = 0; v < 3; v++) {
        for (const nb of vertTris[triVerts[t * 3 + v]]) {
          if (comp[nb] === -1) {
            comp[nb] = c;
            queue.push(nb);
          }
        }
      }
    }
    compSizes.push(size);
  }

  const largest = compSizes.indexOf(Math.max(...compSizes));
  const out = [];
  for (let t = 0; t < nTri; t++) {
    if (comp[t] !== largest) continue;
    for (let i = 0; i < 9; i++) out.push(flat[t * 9 + i]);
  }
  return new Float32Array(out);
}

