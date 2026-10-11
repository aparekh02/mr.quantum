// Records the demo video in one continuous take of one browser tab.
//
// Needs the trainer API on :8765, the frontend on :5173 (make demo-04) and
// scripts/demo/console_server.py on :8777. Writes <out>/frames/*.jpg, <out>/frames.txt
// (an ffmpeg concat list) and <out>/timeline.json (when each beat starts).
//
//   node scripts/demo/record.mjs <out-dir>
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(join(here, "../../frontend/node_modules/playwright/index.mjs"));
const out = process.argv[2] ?? join(here, "out");
mkdirSync(join(out, "frames"), { recursive: true });

const TRAINER = "http://127.0.0.1:5173/";
const CONSOLE = "http://127.0.0.1:8777/";
const REPO = "github.com/aparekh02/mr.quantum";

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 4 / 3 });
await context.addInitScript({ content: readFileSync(join(here, "overlay.js"), "utf8") });
const page = await context.newPage();

// --- screencast: every repaint as a JPEG with its timestamp ------------------------
const cdp = await context.newCDPSession(page);
const frames = [];
cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
  const file = `f${String(frames.length).padStart(6, "0")}.jpg`;
  writeFileSync(join(out, "frames", file), Buffer.from(data, "base64"));
  frames.push({ file, t: Date.now() / 1000 });
  await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
});

const timeline = [];
let t0 = 0;
const beat = (name) => timeline.push({ name, t: Date.now() / 1000 - t0 });
const hold = (s) => page.waitForTimeout(s * 1000);
const demo = (fn, ...args) => page.evaluate(([f, a]) => window.__demo[f](...a), [fn, args]);
const caption = (text, tag) => demo("caption", text, tag ?? "");
const point = (selector, text) => demo("point", selector, text ?? "");
const unpoint = () => demo("unpoint");

let mouse = { x: 720, y: 405 };
async function moveTo(locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  const to = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(to.x, to.y, { steps: 25 });
  mouse = to;
}
async function click(locator) {
  await moveTo(locator);
  await hold(0.25);
  await page.mouse.down();
  await page.mouse.up();
}
async function type(locator, text) {
  await click(locator);
  await locator.press("ControlOrMeta+a");
  await locator.pressSequentially(text, { delay: 80 });
}
async function choose(locator, value) {
  await moveTo(locator);
  await hold(0.3);
  await locator.selectOption(value);
}
async function scrollTo(selector, block = "center") {
  await page.evaluate(
    ([s, b]) => document.querySelector(s).scrollIntoView({ behavior: "smooth", block: b }),
    [selector, block],
  );
  await hold(1.0);
}
async function runRoutine(name, params) {
  await choose(page.getByLabel("Routine"), name);
  await page.getByLabel("Parameters (JSON)").fill(JSON.stringify(params));
  await hold(0.6);
  await click(page.getByRole("button", { name: "Run routine" }));
  await page.locator(".last-run").filter({ hasText: `${name} succeeded` }).waitFor({ timeout: 120_000 });
}
async function runConsole() {
  const before = Number((await page.locator("body").getAttribute("data-runs")) ?? 0);
  await click(page.getByRole("button", { name: "Run" }));
  await page.waitForFunction((n) => Number(document.body.dataset.runs || 0) > n, before, { timeout: 120_000 });
  await hold(0.4);
}
async function consoleScroll(text) {
  await page.evaluate((t) => {
    const ln = [...document.querySelectorAll("#console .ln")].find((n) => n.textContent.includes(t));
    const box = document.getElementById("console");
    box.scrollTop = ln.offsetTop - box.offsetTop - 12;
  }, text);
  await hold(0.9);
}

async function grab(selector, re) {
  const text = await page.locator(selector).innerText();
  const m = text.match(re);
  if (!m) throw new Error(`no ${re} in ${selector}`);
  return m;
}

const SENSOR = {
  peak_spacing: 0.02, sensor_group_name: "side_B", sensor_plunger_gate: "PB",
  measure_electrode: "OUT_B", bias_gate: "IN_B", bias_voltage: 0.001, settling_time_s: 0,
};
const DQD = {
  gates: ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"], measure_electrode: "OUT_A",
  min_search_scale: 0.0005, max_search_scale: 0.001, current_trace_points: 128,
  outer_barrier_points: 3, inner_barrier_points: 3, num_dqds_for_exit: 1,
};

// --- the take -----------------------------------------------------------------------
await page.goto(TRAINER);
await page.getByTestId("stream-status").filter({ hasText: "stream: open" }).waitFor();
await demo("card", `<h1>mr.quantum</h1><h2>From Tune-Up to Qubit</h2>
  <p>A semiconductor double quantum dot, tuned like a real lab does it, then run as a charge qubit in Qiskit.</p>
  <p>Qollab × IonQ hackathon · theme: Quantum Unlocked</p>`);
await hold(0.6);
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, everyNthFrame: 1 });
t0 = Date.now() / 1000;
beat("title");
await hold(7);
await demo("hideCard");
await hold(0.8);

// Part 1: the trainer (prior work).
beat("trainer");
await caption("A simulated quantum-dot chip, driven by the real Stanza tune-up routines researchers run on hardware.", "Part 1 · prior work, disclosed");
await hold(6.5);
await point(".levels");
await caption("Each level teaches one physical concept. Level 1: Coulomb blockade.", "Part 1 · prior work, disclosed");
await hold(4.5);
await unpoint();
beat("level1");
await click(page.getByRole("button", { name: "Start level" }));
await page.getByTestId("measurements").waitFor({ timeout: 60_000 });
await caption("Goal: park the charge sensor on the steep flank of a Coulomb peak.");
await hold(3.5);
await runRoutine("find_sensor_peak", SENSOR);
await scrollTo("[data-testid=trace]");
await point("[data-testid=trace]");
await caption("The routine sweeps the sensor's plunger gate: sharp current peaks with blockaded valleys between them.");
await hold(5.5);
await unpoint();
await scrollTo(".levels", "start");
await click(page.getByRole("button", { name: "Submit" }));
await page.getByTestId("result").waitFor();
await hold(0.6);
await point("[data-testid=result] strong");
const [, flank] = await grab("[data-testid=result]", /at (\d+)% of the best/);
await caption(`Scored on the physics: the sensor sits at ${flank}% of the best sensitivity nearby.`);
await hold(5);
await unpoint();

beat("level3");
await click(page.getByRole("button", { name: "Choose another level" }));
await choose(page.locator("select").nth(1), "double-dot");
await caption("Level 3: find a double quantum dot, the device that becomes a qubit.");
await click(page.getByRole("button", { name: "Start level" }));
await page.getByTestId("measurements").waitFor({ timeout: 60_000 });
await hold(2.5);
await runRoutine("run_dqd_search", DQD);
await scrollTo("[data-testid=heatmap]");
await point("[data-testid=heatmap]");
await caption("Its charge-stability map is a honeycomb. Current flows only at the bright triple points.");
await hold(6);
await unpoint();
const target = await page.getByTestId("heatmap").evaluate((el) => {
  const ctx = el.getContext("2d");
  const { data, width, height } = ctx.getImageData(0, 0, el.width, el.height);
  const lum = (k) => data[4 * k] + data[4 * k + 1] - 0.5 * data[4 * k + 2];
  const step = Math.max(1, Math.round(width / 48));
  let best = -Infinity, at = 0;
  for (let y = step; y < height - step; y++) for (let x = step; x < width - step; x++) {
    let sum = 0;
    for (let dy = -step; dy <= step; dy += step) for (let dx = -step; dx <= step; dx += step) sum += lum((y + dy) * width + x + dx);
    if (sum > best) { best = sum; at = y * width + x; }
  }
  const r = el.getBoundingClientRect();
  return { x: r.left + ((at % width) + 0.5) * (r.width / width), y: r.top + (Math.floor(at / width) + 0.5) * (r.height / height) };
});
await caption("Click a triple point to set both plunger gates there.");
await page.mouse.move(target.x, target.y, { steps: 30 });
await hold(0.4);
await page.mouse.down();
await page.mouse.up();
await hold(1.5);
await scrollTo(".levels", "start");
await click(page.getByRole("button", { name: "Submit" }));
await page.getByTestId("result").waitFor();
await hold(0.6);
await point("[data-testid=result] strong");
await caption("Double dot found. Now the hackathon question: what does this tuned device do as a qubit?");
await hold(5.5);
await unpoint();
await demo("hideCaption");

// Part 2: the Qollab project (built during the hackathon).
beat("qollab");
await page.goto(CONSOLE);
await hold(0.3);
await caption("Built during the hackathon: qollab/main.py, a Qiskit project that runs on Qollab's simulators, including IonQ's.", "Part 2 · new for the hackathon");
await hold(6);
await point("#settings");
await caption("Qollab turns main()'s parameters into Run settings: the same knobs a student set while tuning.", "Part 2 · new for the hackathon");
await hold(5.5);
await unpoint();

beat("detuning");
await runConsole();
await point("#console .ln", "Inner barrier BA1");
await caption("The inner-barrier voltage sets the tunnel coupling, so it sets the qubit's splitting Δ and its frequency.");
await hold(6);
await point("#console .ln", "== Charge map");
await caption("The device's charge map: your operating point (*) on the line where the charge moves between the dots.");
await hold(6);
await consoleScroll("== Experiment");
await point("#console .ln", "== Experiment");
await caption("16 detunings, 16 qubits, one circuit, one job. Each row is read out as charge-sensor current.");
await hold(6.5);
await consoleScroll("== Analysis");
await point("#console .ln", "fitted Δ");
const [, fit1, true1] = await grab("#console", /fitted Δ = ([0-9.]+) µeV \(true Δ = ([0-9.]+)/);
await caption(`Fit the physics back out of the counts: Δ ≈ ${fit1} µeV, against the true ${true1} µeV.`);
await hold(6);
await unpoint();

beat("barrier");
await caption("Open the inner barrier a little more…");
await type(page.locator("#inner_barrier_V"), "-0.95");
await hold(0.5);
await runConsole();
await consoleScroll("== Analysis");
await point("#console .ln", "fitted Δ");
const [, fit2] = await grab("#console", /fitted Δ = ([0-9.]+) µeV/);
await caption(`…and the resonance widens to Δ ≈ ${fit2} µeV: the coupling you tuned in the trainer is the qubit's Δ.`);
await hold(6);
await unpoint();

beat("time");
await choose(page.locator("#experiment"), "time_sweep");
await type(page.locator("#inner_barrier_V"), "-0.88");
await type(page.locator("#pulse_ps"), "300");
await caption("time_sweep: longer and longer pulses at fixed detuning.");
await runConsole();
await consoleScroll("== Experiment");
await point("#console .ln", "== Experiment");
await caption("The charge oscillates between the dots: a charge qubit.");
await hold(5);
await consoleScroll("== Analysis");
await point("#console .ln", "From the oscillation");
const [, f, ftrue] = await grab("#console", /f = ([0-9.]+) GHz \(true ([0-9.]+) GHz/);
await caption(`Measured frequency ${f} GHz; theory √(ε² + Δ²)/h gives ${ftrue} GHz.`);
await hold(5.5);
await unpoint();

beat("sweet");
await choose(page.locator("#experiment"), "sweet_spot");
await type(page.locator("#charge_noise_ueV"), "15");
await caption("sweet_spot: add frozen charge noise to every qubit, half of them at ε = 0 and half off it.");
await runConsole();
await consoleScroll("== Analysis");
await point("#console .ln", "     sweet spot:");
const [, at] = await grab("#console", / sweet spot: typical frequency shift ([0-9.]+) GHz/);
const [, off] = await grab("#console", /off sweet spot: typical frequency shift ([0-9.]+) GHz/);
await caption(`At the sweet spot the noise barely moves the frequency (${Number(at).toFixed(2)} GHz)…`);
await hold(5);
await point("#console .ln", "off sweet spot:");
await caption(`…off it, the frequency shifts ${Math.round(off / at)}× more (${Number(off).toFixed(2)} GHz) and the data scatter. That is why qubits are parked at sweet spots.`);
await hold(7);
await unpoint();
await demo("hideCaption");

beat("end");
await demo("card", `<h1>mr.quantum</h1><h2>From Tune-Up to Qubit</h2>
  <p>One file on Qollab · every sweep in one circuit and one job, so it runs on IonQ's simulator too · MIT licensed</p>
  <p>${REPO}</p>
  <p class="att">This effort is supported by Qollab &amp; IonQ</p>`);
await hold(8);
beat("stop");

await cdp.send("Page.stopScreencast");
await browser.close();

// ffmpeg concat list: each frame lasts until the next one.
const start = frames[0].t;
const lines = [];
for (let i = 0; i < frames.length; i++) {
  const next = i + 1 < frames.length ? frames[i + 1].t : timeline.at(-1).t + t0;
  lines.push(`file 'frames/${frames[i].file}'`, `duration ${Math.max(0.001, next - frames[i].t).toFixed(4)}`);
}
lines.push(`file 'frames/${frames.at(-1).file}'`);
writeFileSync(join(out, "frames.txt"), lines.join("\n") + "\n");
writeFileSync(
  join(out, "timeline.json"),
  JSON.stringify(timeline.map((b) => ({ ...b, t: +(b.t - (start - t0)).toFixed(2) })), null, 2),
);
console.log(`${frames.length} frames, ${(timeline.at(-1).t).toFixed(1)} s`);
