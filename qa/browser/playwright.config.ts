import { defineConfig, devices } from "@playwright/test";

const qaHttpCredentials =
  process.env.QA_GATE_USERNAME && process.env.QA_GATE_PASSWORD
    ? { username: process.env.QA_GATE_USERNAME, password: process.env.QA_GATE_PASSWORD }
    : undefined;

export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 25_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    httpCredentials: qaHttpCredentials,
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
