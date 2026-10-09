import { expect, test } from "./fixtures";

const DQD_SEARCH = {
  gates: ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"],
  measure_electrode: "OUT_A",
  min_search_scale: 0.0005,
  max_search_scale: 0.001,
  current_trace_points: 128,
  outer_barrier_points: 3,
  inner_barrier_points: 3,
  num_dqds_for_exit: 1,
};

test("level 3: search for the double dot, click a triple point on its map, submit", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Level", { exact: true }).selectOption("double-dot");
  await page.getByRole("button", { name: "Start level" }).click();
  await expect(page.getByTestId("measurements")).toBeVisible({ timeout: 60_000 });

  await page.getByLabel("Routine").selectOption("run_dqd_search");
  await page.getByLabel("Parameters (JSON)").fill(JSON.stringify(DQD_SEARCH));
  await page.getByRole("button", { name: "Run routine" }).click();
  await expect(page.locator(".last-run")).toHaveText("run_dqd_search succeeded", { timeout: 90_000 });

  const heatmap = page.getByTestId("heatmap");
  await expect(page.getByText("run_dqd_search: dqd_search_high_res_csd")).toBeVisible();
  await expect(heatmap).toHaveAttribute("data-cells", "2304");

  // Click the brightest pixel of the measured map: a triple point.
  await heatmap.scrollIntoViewIfNeeded();
  const target = await heatmap.evaluate((el) => {
    const canvas = el as HTMLCanvasElement;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("no 2d context");
    const { data, width, height } = ctx.getImageData(0, 0, canvas.width, canvas.height);
    // Like a person: aim at the middle of the brightest blob, not its edge.
    const lum = (k: number) => (data[4 * k] ?? 0) + (data[4 * k + 1] ?? 0) - 0.5 * (data[4 * k + 2] ?? 0);
    const step = Math.max(1, Math.round(width / 48));
    let best = -Infinity;
    let at = 0;
    for (let y = step; y < height - step; y += 1) {
      for (let x = step; x < width - step; x += 1) {
        let sum = 0;
        for (let dy = -step; dy <= step; dy += step) {
          for (let dx = -step; dx <= step; dx += step) sum += lum((y + dy) * width + (x + dx));
        }
        if (sum > best) {
          best = sum;
          at = y * width + x;
        }
      }
    }
    const rect = canvas.getBoundingClientRect();
    return {
      x: rect.left + ((at % width) + 0.5) * (rect.width / width),
      y: rect.top + (Math.floor(at / width) + 0.5) * (rect.height / height),
    };
  });
  const applied = page.waitForResponse((r) => r.url().endsWith("/voltages") && r.request().method() === "PUT");
  await page.mouse.click(target.x, target.y);
  expect((await applied).status()).toBe(200);

  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByTestId("result")).toContainText("Level complete");
});
