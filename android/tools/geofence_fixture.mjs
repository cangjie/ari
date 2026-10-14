// Offline fixture from the production app.js functions, without duplicating the decision algorithm.
// Browser fixture remains the stronger end-to-end check when Chrome can run.
import { readFile, readdir, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = new URL("../../", import.meta.url);
const source = await readFile(new URL("web_api/tour/app.js", root), "utf8");
const files = (await readdir(new URL("web_api/tour/data/", root))).filter((name) => name.endsWith(".json")).sort();
const file = process.argv[2] ? `${process.argv[2]}.json` : files[0];
if (!files.includes(file)) throw new Error("Unknown tour data");
const museum = JSON.parse(await readFile(new URL("web_api/tour/data/" + file, root), "utf8"));
function extract(name) {
  const match = new RegExp(`  function ${name}\\([^)]*\\) \\{`).exec(source);
  if (!match) throw new Error(`Function missing: ${name}`);
  let depth = 0, quote = null, escaped = false, lineComment = false;
  const start = match.index, firstBrace = source.indexOf("{", start);
  for (let i = firstBrace; i < source.length; i++) {
    const c = source[i];
    if (lineComment) { if (c === "\n") lineComment = false; continue; }
    if (quote) { if (escaped) escaped = false; else if (c === "\\") escaped = true; else if (c === quote) quote = null; continue; }
    if (c === "/" && source[i + 1] === "/") { lineComment = true; i++; continue; }
    if (c === '"' || c === "'") { quote = c; continue; }
    if (c === "{") depth++;
    if (c === "}" && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`Unbalanced function: ${name}`);
}
const context = vm.createContext({ M: museum, st: { geo: "waiting", inside: null, pos: [museum.entrance.x, museum.entrance.y], follow: false, raw: null },
  OPT: { gcj: false }, ACC_TRIGGER_M: Number(source.match(/var ACC_TRIGGER_M = ([\d.]+)/)[1]),
  STAY_FACTOR: Number(source.match(/var STAY_FACTOR = ([\d.]+)/)[1]),
  updateSpots() {}, updateMe() {}, centerOn() {}, notify() {} });
vm.runInContext(["clamp", "project", "haversine", "inPoly", "distPoly", "inArea", "placeById", "hitPlace", "setPos", "onFix", "onGeoError"].map(extract).join("\n"), context);
const p = museum.proj;
function inverse(x, y) {
  const dx = x - p.tx, dy = y - p.ty, det = p.a * p.d - p.b * p.c;
  return [p.lat0 + (-p.c * dx + p.a * dy) / det / p.mlat, p.lon0 + (p.d * dx - p.b * dy) / det / p.mlon];
}
const samples = [{ lat: 0, lon: 0, acc: 5 }];
for (const place of museum.places) {
  for (const offset of [2, 0, 1.05, 1.19, 1.21, 2.5, 0]) {
    const [lat, lon] = inverse(place.x + place.r * offset, place.y);
    samples.push({ lat, lon, acc: offset === 2.5 ? 40 : 5 });
  }
  const [lat, lon] = inverse(place.x, place.y);
  samples.push({ lat, lon, acc: 31 }, { error: "timeout" }, { lat, lon, acc: 5 });
}
samples.push({ lat: 0, lon: 0, acc: 5 });
const cases = samples.map((sample) => {
  if (sample.error) context.onGeoError({ code: 3, TIMEOUT: 3, PERMISSION_DENIED: 1 });
  else context.onFix({ coords: { latitude: sample.lat, longitude: sample.lon, accuracy: sample.acc } });
  return { ...sample, expected: { status: context.st.geo, inside: context.st.inside, x: context.st.pos[0], y: context.st.pos[1] } };
});
await mkdir(new URL("android/testdata/", root), { recursive: true });
const output = new URL("android/testdata/geofence_cases.json", root);
await writeFile(output, JSON.stringify({ museum: museum.key, generated_by: "Production app.js functions in Node vm; browser delivery not exercised", cases }, null, 2) + "\n");
console.log(`${cases.length} cases from actual app.js -> ${fileURLToPath(output)}`);
