import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

async function runRoutine(page: Page, routine: string, parameters: Record<string, unknown>) {
  await page.getByLabel("Routine").selectOption(routine);
  await page.getByLabel("Parameters (JSON)").fill(JSON.stringify(parameters));
  await page.getByRole("button", { name: "Run routine" }).click();
  await expect(page.locator(".last-run")).toHaveText(`${routine} succeeded`, { timeout: 60_000 });
}

test("driving a sweep from the browser renders every measured point", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("stream-status")).toHaveText("stream: open");
  await expect(page.getByLabel("PB")).toBeVisible();

  await runRoutine(page, "noise_floor_measurement", { measure_electrode: "OUT_B", group: "side_B" });
  await runRoutine(page, "leakage_test", { leakage_threshold_resistance: 50_000_000, group: "side_B" });
  await runRoutine(page, "global_accumulation", {
    measure_electrode: "OUT_B",
    bias_gate: "IN_B",
    bias_voltage: 0.001,
    charge_carrier_type: "hole",
    step_size: 0.01,
    group: "side_B",
  });

  // global_accumulation sweeps 0 V -> -2.0 V in 10 mV steps: 200 points.
  const trace = page.getByTestId("trace");
  await expect(trace).toHaveAttribute("data-points", "200");
  const coords = (await trace.locator("polyline").getAttribute("points"))?.split(" ") ?? [];
  expect(coords).toHaveLength(200);
  await expect(page.getByText("global_accumulation: n gates sweep")).toBeVisible();

  // The routine parked the gates at the turn-on voltage; the sliders show it.
  const pb = Number(await page.getByLabel("PB").inputValue());
  expect(pb).toBeLessThan(-0.5);
});

test("a manual slider change reaches the device", async ({ page }) => {
  await page.goto("/");
  const slider = page.getByLabel("PB");
  await expect(slider).toBeVisible();
  const applied = page.waitForResponse(
    (r) => r.url().endsWith("/voltages") && r.request().method() === "PUT",
  );
  await slider.fill("-0.75");
  const response = await applied;
  expect(response.status()).toBe(200);
  expect((await response.json()).PB).toBeCloseTo(-0.75, 6);
  await expect(page.getByTestId("value-PB")).toHaveText("-0.750 V");
});
