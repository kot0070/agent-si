const fs = require("fs");
const en = JSON.parse(fs.readFileSync("D:/AI_PROJECTS/AGENT_SI_BUILD/WT/R02/frontend/src/locale/en.json", "utf8"));
const dts = fs.readFileSync("D:/AI_PROJECTS/AGENT_SI_BUILD/WT/R02/frontend/src/settings/k07b-iface.d.ts", "utf8");
const block = dts.split("export type LocaleKey")[1].split(";")[0];
const union = [...new Set([...block.matchAll(/'([^']+)'/g)].map((m) => m[1]))].sort();
function leaves(o, p, out) {
  for (const k of Object.keys(o)) {
    const v = o[k];
    if (v !== null && typeof v === "object") leaves(v, p + k + ".", out);
    else out.push(p + k);
  }
  return out.sort();
}
const ek = leaves(en, "", []);
console.log("json=" + ek.length + " union=" + union.length);
console.log("IN UNION NOT JSON:");
for (const k of union) if (!ek.includes(k)) console.log("  " + k);
console.log("IN JSON NOT UNION:");
for (const k of ek) if (!union.includes(k)) console.log("  " + k);
