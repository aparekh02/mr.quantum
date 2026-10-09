import { expect, test as base } from "@playwright/test";

// Every e2e test fails if the page logs an error or throws: a render loop or a
// crash must not hide behind passing assertions.
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(m.text());
      });
      page.on("pageerror", (e) => errors.push(e.message));
      await use(errors);
      expect(errors, "browser console errors").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
