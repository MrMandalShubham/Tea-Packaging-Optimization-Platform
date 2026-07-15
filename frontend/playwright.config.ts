import { defineConfig, devices } from "@playwright/test";

/**
 * Requires the app running: backend on :8000, frontend on :3000, DB migrated.
 *
 * Gotcha worth knowing: `next build` and `next dev` share the `.next/` directory.
 * Running a production build while the dev server is up replaces its chunks, and
 * every page then serves a JS-less shell — pages return 200, but nothing renders
 * and every test fails with "element not found". If that happens, stop the dev
 * server, delete `.next/`, and restart it.
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 60_000, // the optimiser evaluates ~15k configurations per run
  retries: 1,
  // The journey tests each create a simulation; running them in parallel makes a
  // CPU-bound backend the bottleneck and produces flaky timeouts.
  workers: 1,
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
