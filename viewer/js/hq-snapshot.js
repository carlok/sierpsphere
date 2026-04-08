import { smoothIntersect, smoothSub, smoothUnion } from "./sdf.js";

function primCall(prim, cx, cy, cz, r) {
  const c = `${cx.toFixed(6)},${cy.toFixed(6)},${cz.toFixed(6)}`;
  if (prim === "cube") return `sdBox(p, vec3(${c}), vec3(${r.toFixed(6)}))`;
  if (prim === "octahedron") return `sdOct(p, vec3(${c}), ${r.toFixed(6)})`;
  return `sdSphere(p, vec3(${c}), ${r.toFixed(6)})`;
}

export function renderHQSnapshot({ currentOps, activeGrammar, currentSeedC, currentSeedR, camera, setStatus }) {
  if (currentOps.length === 0) {
    setStatus("Nothing to render");
    return;
  }

  setStatus("Rendering HQ snapshot...");
  requestAnimationFrame(() => {
    const W = window.innerWidth * 2;
    const H = window.innerHeight * 2;
    const offscreen = document.createElement("canvas");
    offscreen.width = W;
    offscreen.height = H;
    const gl = offscreen.getContext("webgl", { preserveDrawingBuffer: true });
    if (!gl) {
      setStatus("WebGL not available for snapshot");
      return;
    }

    const seedPrim = activeGrammar?.seed?.type || "sphere";
    let sdfBody = `  float d = ${primCall(seedPrim, currentSeedC[0], currentSeedC[1], currentSeedC[2], currentSeedR)};\n`;
    for (const o of currentOps) {
      const opName = o.boolFn === smoothSub ? "smoothSub" : o.boolFn === smoothUnion ? "smoothUni" : "smoothInt";
      sdfBody += `  d = ${opName}(${primCall(o.prim, o.cx, o.cy, o.cz, o.r)}, d, ${o.k.toFixed(6)});\n`;
    }

    const fSrc = `
precision highp float;
uniform vec2 uRes;
uniform mat4 uInvProj, uInvView;

float smoothSub(float a, float b, float k) {
  if(k<=0.) return max(-a,b);
  float h=clamp(.5-.5*(b+a)/k,0.,1.);
  return mix(b,-a,h)+k*h*(1.-h);
}
float smoothUni(float a, float b, float k) {
  if(k<=0.) return min(a,b);
  float h=clamp(.5+.5*(b-a)/k,0.,1.);
  return mix(b,a,h)-k*h*(1.-h);
}
float smoothInt(float a, float b, float k) {
  if(k<=0.) return max(a,b);
  float h=clamp(.5-.5*(b-a)/k,0.,1.);
  return mix(b,a,h)+k*h*(1.-h);
}
float sdSphere(vec3 p, vec3 c, float r) { return length(p - c) - r; }
float sdBox(vec3 p, vec3 c, vec3 b) {
  vec3 q = abs(p - c) - b;
  return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0);
}
float sdOct(vec3 p, vec3 c, float r) {
  vec3 q = abs(p - c);
  return (q.x + q.y + q.z - r) * 0.57735026919;
}
float map(vec3 p) {
${sdfBody}  return d;
}
vec3 calcN(vec3 p) {
  vec2 e=vec2(.0005,0);
  return normalize(vec3(map(p+e.xyy)-map(p-e.xyy),map(p+e.yxy)-map(p-e.yxy),map(p+e.yyx)-map(p-e.yyx)));
}
float ao(vec3 p, vec3 n) {
  float o=0.,s=1.;
  for(int i=0;i<6;i++){float h=.01+.15*float(i)/5.;o+=(h-map(p+h*n))*s;s*=.9;}
  return clamp(1.-2.5*o,0.,1.);
}
float shadow(vec3 ro, vec3 rd, float tmax) {
  float res=1., t=.02;
  for(int i=0;i<48;i++){
    float d=map(ro+rd*t);
    if(d<.001) return 0.;
    res=min(res, 12.*d/t);
    t+=d;
    if(t>tmax) break;
  }
  return clamp(res,0.,1.);
}
vec3 fresnelSchlick(float cosT, vec3 F0) {
  return F0 + (1.0 - F0) * pow(clamp(1.0 - cosT, 0.0, 1.0), 5.0);
}
float ggxD(float NdH, float rough) {
  float a = rough * rough;
  float a2 = a * a;
  float d = NdH * NdH * (a2 - 1.0) + 1.0;
  return a2 / (3.14159 * d * d);
}
float ggxG(float NdV, float NdL, float rough) {
  float k = (rough + 1.0); k = k * k / 8.0;
  float g1 = NdV / (NdV * (1.0 - k) + k);
  float g2 = NdL / (NdL * (1.0 - k) + k);
  return g1 * g2;
}
void main(){
  vec2 uv=gl_FragCoord.xy/uRes*2.-1.;
  vec4 cd=uInvProj*vec4(uv,-1,1); cd=vec4(cd.xyz/cd.w,0.);
  vec3 rd=normalize((uInvView*cd).xyz), ro=(uInvView*vec4(0,0,0,1)).xyz;
  float t=0.;
  for(int i=0;i<256;i++){ float d=map(ro+rd*t); if(d<.0003) break; t+=d; if(t>20.) break; }
  vec3 col=vec3(.02,.02,.04);
  if(t<20.){
    vec3 p=ro+rd*t, n=calcN(p), V=-rd;
    float occ=ao(p,n);
    vec3 albedo = vec3(0.78, 0.50, 0.22);
    float metallic = 0.9, roughness = 0.35;
    vec3 F0 = mix(vec3(0.04), albedo, metallic);
    vec3 L1=normalize(vec3(1.0, 1.5, 2.0));
    float sh1=shadow(p+n*.002, L1, 8.0);
    vec3 lc1=vec3(1.0, 0.95, 0.85) * 1.4;
    vec3 L2=normalize(vec3(-1.0, 0.3, -0.5));
    vec3 lc2=vec3(0.3, 0.4, 0.6) * 0.5;
    vec3 Lo = vec3(0.0);
    for(int li=0; li<2; li++){
      vec3 L = li==0 ? L1 : L2;
      vec3 lc = li==0 ? lc1 * sh1 : lc2;
      vec3 H = normalize(V + L);
      float NdL = max(dot(n, L), 0.0), NdV = max(dot(n, V), 0.001), NdH = max(dot(n, H), 0.0), VdH = max(dot(V, H), 0.0);
      vec3 F = fresnelSchlick(VdH, F0);
      float D = ggxD(NdH, roughness), G = ggxG(NdV, NdL, roughness);
      vec3 spec = (D * G * F) / max(4.0 * NdV * NdL, 0.001);
      vec3 kD = (1.0 - F) * (1.0 - metallic);
      Lo += (kD * albedo / 3.14159 + spec) * lc * NdL;
    }
    vec3 ambient = vec3(0.08, 0.05, 0.03) * albedo * occ;
    float rim = pow(1.0 - max(dot(n, V), 0.0), 4.0);
    vec3 rimCol = vec3(0.25, 0.35, 0.5) * rim * 0.3 * occ;
    col = ambient + Lo * occ + rimCol;
  }
  col = col * (2.51 * col + 0.03) / (col * (2.43 * col + 0.59) + 0.14);
  col = pow(clamp(col, 0.0, 1.0), vec3(1.0/2.2));
  gl_FragColor=vec4(col,1);
}`;

    const vSrc = "attribute vec2 a;void main(){gl_Position=vec4(a,0,1);}";
    const mkShader = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) return null;
      return s;
    };
    const vs = mkShader(gl.VERTEX_SHADER, vSrc);
    const fs = mkShader(gl.FRAGMENT_SHADER, fSrc);
    if (!vs || !fs) {
      setStatus("Shader error");
      return;
    }

    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const aLoc = gl.getAttribLocation(prog, "a");
    gl.enableVertexAttribArray(aLoc);
    gl.vertexAttribPointer(aLoc, 2, gl.FLOAT, false, 0, 0);

    const savedAspect = camera.aspect;
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    const invP = camera.projectionMatrixInverse.elements;
    const invV = camera.matrixWorld.elements;
    camera.aspect = savedAspect;
    camera.updateProjectionMatrix();

    gl.uniform2f(gl.getUniformLocation(prog, "uRes"), W, H);
    gl.uniformMatrix4fv(gl.getUniformLocation(prog, "uInvProj"), false, invP);
    gl.uniformMatrix4fv(gl.getUniformLocation(prog, "uInvView"), false, invV);
    gl.viewport(0, 0, W, H);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.finish();

    offscreen.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "sierpsphere_hq.png";
      a.click();
      URL.revokeObjectURL(url);
      setStatus("Snapshot saved.");
      setTimeout(() => setStatus(""), 3000);
    }, "image/png");
  });
}

