import { expect, test } from "@playwright/test";

test("a 100x100 charge stability diagram renders, reads out and sets gates", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("stream-status")).toHaveText("stream: open");
  const sid = await page.locator("main").getAttribute("data-session-id");
  expect(sid).toBeTruthy();

  // Put side A into the double-dot regime (outer barriers open, inner barrier pinched).
  const setup = await page.request.put(`/api/sessions/${sid}/voltages`, {
    data: { voltages: { RA1: -1.7, RA2: -1.7, BA0: -0.9, BA1: -0.75, BA2: -0.9, IN_A: 0.001 } },
  });
  expect(setup.ok()).toBe(true);

  await page.getByLabel("X gate").selectOption("PA1");
  await page.getByLabel("Y gate").selectOption("PA2");
  await page.getByLabel("X from (V)").fill("-0.66");
  await page.getByLabel("X to (V)").fill("-0.58");
  await page.getByLabel("Y from (V)").fill("-0.66");
  await page.getByLabel("Y to (V)").fill("-0.58");
  await page.getByLabel("Points per axis").fill("100");
  await page.getByRole("button", { name: "Measure map" }).click();
  await expect(page.locator(".last-run")).toHaveText("charge_stability_diagram succeeded", {
    timeout: 90_000,
  });

  const heatmap = page.getByTestId("heatmap");
  await expect(heatmap).toHaveAttribute("data-cells", "10000");
  const renderMs = Number(await heatmap.getAttribute("data-render-ms"));
  expect(renderMs).toBeGreaterThan(0);
  expect(renderMs).toBeLessThan(50); // render budget for a 100 x 100 map

  await heatmap.scrollIntoViewIfNeeded();
  const box = await heatmap.boundingBox();
  if (!box) throw new Error("no heatmap box");
  // Crosshair readout at the centre of the map.
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.getByTestId("crosshair")).toContainText("PA1 = -0.6200 V");
  await expect(page.getByTestId("crosshair")).toContainText("PA2 = -0.6200 V");

  // Click a quarter of the way in from the bottom-left: sets both gates.
  const put = page.waitForResponse((r) => r.url().endsWith("/voltages") && r.request().method() === "PUT");
  await page.mouse.click(box.x + box.width / 4, box.y + (3 * box.height) / 4);
  const applied = await (await put).json();
  expect(applied.PA1).toBeCloseTo(-0.64, 3);
  expect(applied.PA2).toBeCloseTo(-0.64, 3);
  await expect(page.getByTestId("value-PA1")).toHaveText("-0.640 V");
});
