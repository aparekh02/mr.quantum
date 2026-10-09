import { defineConfig } from "@playwright/test";

const API_PORT = 8766;
const WEB_PORT = 5174;
const repo = new URL("..", import.meta.url).pathname;

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  // The API runs one routine at a time per process (DECISIONS.md D-037): run serially.
  workers: 1,
  fullyParallel: false,
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: "retain-on-failure" },
  webServer: [
    {
      command: `${repo}.venv/bin/python -m trainer.api --port ${API_PORT}`,
      cwd: repo,
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npx vite",
      env: { TRAINER_API: `http://127.0.0.1:${API_PORT}`, FRONTEND_PORT: String(WEB_PORT) },
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
