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

test("a named player unlocks level 2 by winning level 1, and keeps it after a reload", async ({ page }) => {
  const name = `e2e_${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Your name").fill(name);
  await page.getByRole("button", { name: "Save my progress" }).click();
  await expect(page.getByText(/Playing as/)).toContainText(name);

  const picker = page.getByLabel("Level", { exact: true });
  await expect(picker.locator("option").nth(1)).toHaveAttribute("disabled", "");
  await expect(picker.locator("option").nth(2)).toHaveAttribute("disabled", "");

  await page.getByRole("button", { name: "Start level" }).click();
  await expect(page.getByTestId("measurements")).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Routine").selectOption("find_sensor_peak");
  await page.getByLabel("Parameters (JSON)").fill(JSON.stringify(SENSOR));
  await page.getByRole("button", { name: "Run routine" }).click();
  await expect(page.locator(".last-run")).toHaveText("find_sensor_peak succeeded", { timeout: 60_000 });
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByTestId("result")).toContainText("Level complete");
  await expect(page.getByTestId("explanation")).toContainText("Why it works");
  await expect(page.getByTestId("explanation")).toContainText("charging energy");

  await page.getByRole("button", { name: "Choose another level" }).click();
  await expect(picker.locator("option").nth(0)).toContainText("✓ Level 1");
  await expect(picker.locator("option").nth(1)).not.toHaveAttribute("disabled", "");
  await expect(picker.locator("option").nth(2)).toHaveAttribute("disabled", "");

  await page.reload();
  await expect(page.getByText(/Playing as/)).toContainText(name);
  await expect(page.getByLabel("Level", { exact: true }).locator("option").nth(1)).not.toHaveAttribute("disabled", "");
  await expect(page.getByText("2. Compensate the sensor")).toBeVisible();
});
