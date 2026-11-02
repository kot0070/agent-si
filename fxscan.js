const fs = require("fs");
function load(p) {
  const lines = fs.readFileSync(p, "utf8").split("\n");
  const mine = JSON.parse(lines[1]);
  const theirs = JSON.parse(lines[3]);
  return { mine, theirs };
}
function leaves(o, p, out) {
  for (const k of Object.keys(o)) {
    const v = o[k];
    if (v !== null && typeof v === "object") leaves(v, p + k + ".", out);
    else out[p + k] = v;
  }
  return out;
}
for (const p of [
  "D:/AI_PROJECTS/AGENT_SI_BUILD/WT/R02/frontend/src/locale/en.json",
  "D:/AI_PROJECTS/AGENT_SI_BUILD/WT/R02/frontend/src/locale/uk.json",
]) {
  const { mine, theirs } = load(p);
  const m = leaves(mine, "", {});
  const t = leaves(theirs, "", {});
  console.log("=== " + p.split("/").pop() + " mine=" + Object.keys(m).length + " theirs=" + Object.keys(t).length);
  for (const k of Object.keys(t).sort()) {
    if (!(k in m)) console.log("NEW-T " + k + " = " + JSON.stringify(t[k]).slice(0, 160));
  }
  for (const k of Object.keys(m).sort()) {
    if (!(k in t)) console.log("NEW-M " + k + " = " + JSON.stringify(m[k]).slice(0, 160));
  }
  for (const k of Object.keys(t).sort()) {
    if (k in m && JSON.stringify(m[k]) !== JSON.stringify(t[k])) {
      console.log("CHG " + k + " mine=" + JSON.stringify(m[k]).slice(0, 100) + " theirs=" + JSON.stringify(t[k]).slice(0, 100));
    }
  }
}
