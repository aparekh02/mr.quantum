import { expect, test } from "./fixtures";

const SENSOR = {
  peak_spacing: 0.02,
  sensor_group_name: "side_B",
  sensor_plunger_gate: "PB",
  measure_electrode: "OUT_B",
  bias_gate: "IN_B",
  bias_voltage: 0.001,
  settling_time_s: 0,
};

test("level 1 can be played start to finish in the browser", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("1. Find the Coulomb peak")).toBeVisible();
  await page.getByRole("button", { name: "Start level" }).click();
  await expect(page.getByText(/Park|Find a Coulomb peak/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("measurements")).toHaveText("0 / 2500 measurements");

  await page.getByRole("button", { name: "Show a hint" }).click();
  await page.getByRole("button", { name: "Show a hint" }).click();
  await expect(page.locator(".hints li")).toHaveCount(2);
  await expect(page.locator(".hints li").nth(1)).toContainText("find_sensor_peak");

  await page.getByLabel("Routine").selectOption("find_sensor_peak");
  await page.getByLabel("Parameters (JSON)").fill(JSON.stringify(SENSOR));
  await page.getByRole("button", { name: "Run routine" }).click();
  await expect(page.locator(".last-run")).toHaveText("find_sensor_peak succeeded", { timeout: 60_000 });
  await expect(page.getByTestId("measurements")).not.toHaveText("0 / 2500 measurements");

  await page.getByRole("button", { name: "Submit" }).click();
  const result = page.getByTestId("result");
  await expect(result).toContainText("Level complete");
  await expect(result).toContainText("points");
});

test("submitting without playing does not complete the level", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start level" }).click();
  await expect(page.getByTestId("measurements")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByTestId("result")).toContainText("Not yet");
});
