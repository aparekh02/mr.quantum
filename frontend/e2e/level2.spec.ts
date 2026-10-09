import { expect, test } from "./fixtures";

const COMPENSATION = {
  peak_spacing: 0.02,
  control_group_name: "side_A",
  measure_electrode: "OUT_B",
  bias_gate: "IN_B",
  bias_voltage: 0.001,
  settling_time_s: 0,
  num_samples_for_averaging: 2,
  gates_to_compensate: ["PA1"],
  seed: 3,
};

test("level 2: measure the gradient, step PA1, compensate with PB, submit", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Level", { exact: true }).selectOption("compensate-sensor");
  await page.getByRole("button", { name: "Start level" }).click();
  await expect(page.getByTestId("measurements")).toBeVisible({ timeout: 60_000 });

  const startPB = Number(await page.getByLabel("PB").inputValue());
  const startPA1 = Number(await page.getByLabel("PA1").inputValue());

  await page.getByLabel("Routine").selectOption("run_compensation");
  await page.getByLabel("Parameters (JSON)").fill(JSON.stringify(COMPENSATION));
  await page.getByRole("button", { name: "Run routine" }).click();
  await expect(page.locator(".last-run")).toHaveText("run_compensation succeeded", { timeout: 90_000 });
  const result = JSON.parse((await page.getByTestId("last-result").textContent()) ?? "{}");
  const gradient: number = result.compensation_gradients.PA1;
  expect(gradient).toBeLessThan(0);

  const step = 0.03;
  await page.getByLabel("PA1").fill(String(startPA1 + step));
  await expect(page.getByTestId("value-PA1")).toContainText((startPA1 + step).toFixed(3));
  await page.getByLabel("PB").fill((startPB + gradient * step).toFixed(4));
  await expect(page.getByTestId("value-PB")).toContainText((startPB + gradient * step).toFixed(3));

  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByTestId("result")).toContainText("Level complete");
});
