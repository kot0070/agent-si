const fs = require("fs");
function deepMerge(base, over) {
  const out = Array.isArray(base) ? base.slice() : { ...base };
  for (const k of Object.keys(over)) {
    const bv = base[k];
    const ov = over[k];
    if (
      bv !== null && ov !== null &&
      typeof bv === "object" && typeof ov === "object" &&
      !Array.isArray(bv) && !Array.isArray(ov)
    ) {
      out[k] = deepMerge(bv, ov);
    } else {
      out[k] = ov;
    }
  }
  return out;
}
for (const p of [
  "D:/AI_PROJECTS/AGENT_SI_BUILD/WT/R02/frontend/src/locale/en.json",
  "D:/AI_PROJECTS/AGENT_SI_BUILD/WT/R02/frontend/src/locale/uk.json",
]) {
  const lines = fs.readFileSync(p, "utf8").split("\n");
  if (lines[0] !== "<<<<<<< HEAD" || lines[2] !== "=======" || lines[4] !== ">>>>>>> int") {
    console.log("SKIP (no markers): " + p);
    continue;
  }
  const mine = JSON.parse(lines[1]);
  const theirs = JSON.parse(lines[3]);
  // Theirs is the base (latest int); my lane keys win on conflict.
  const merged = deepMerge(theirs, mine);
  fs.writeFileSync(p, JSON.stringify(merged) + "\n", "utf8");
  console.log("MERGED " + p);
}
