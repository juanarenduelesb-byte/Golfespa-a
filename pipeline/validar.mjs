// Comprueba antes de guardar: auto.js se carga y tiene la forma correcta, y todos los <script> de index.html compilan.
import { readFileSync } from "node:fs";
const fail = m => { console.error("::error::" + m); process.exit(1); };
const w = {}; new Function("window", readFileSync("site/auto.js", "utf8"))(w);
const A = w.AUTO;
if (!A || typeof A.upd !== "string" || !A.res || !A.res.ncaa || !A.res.nac) fail("auto.js no tiene la forma esperada");
for (const m of ["ncaa", "nac"]) for (const [pid, evs] of Object.entries(A.res[m]))
  for (const [eid, r] of Object.entries(evs)) {
    if (typeof r.pos !== "string" || !Array.isArray(r.rounds)) fail(`resultado mal formado: ${m}/${pid}/${eid}`);
    if (!/^https:\/\//.test(r.src || "")) fail(`sin fuente: ${m}/${pid}/${eid}`);
  }
for (const [u, list] of Object.entries((A.ev && A.ev.ncaa) || {})) for (const e of list) {
  if (!e.id || !e.n || !/^\d{4}-\d\d-\d\d$/.test(e.a || "") || !/^\d{4}-\d\d-\d\d$/.test(e.b || "")) fail(`torneo mal formado en ${u}: ${JSON.stringify(e)}`);
}
for (const [pid, w] of Object.entries(A.wagr || {})) if (!(Number.isInteger(w) && w > 0)) fail(`ranking WAGR raro para ${pid}: ${w}`);
const html = readFileSync("site/index.html", "utf8");
const scripts = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
scripts.forEach((s, i) => { try { new Function(s); } catch (e) { fail(`index.html, script ${i + 1}: ${e.message}`); } });
if (A.errores && A.errores.length) console.log("::warning::Fuentes con fallos: " + A.errores.join(" | "));
console.log(`OK · actualizado ${A.upd} · ${scripts.length} scripts · ${Object.keys(A.res.nac).length + Object.keys(A.res.ncaa).length} jugadoras con resultados automáticos`);
