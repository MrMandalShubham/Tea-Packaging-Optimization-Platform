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
  retries: process.env.CI ? 1 : 0,
  // The journey tests each create a simulation; running them in parallel makes a
  // CPU-bound backend the bottleneck and produces flaky timeouts.
  workers: 1,
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  // Start the frontend if it isn't already up.
  //
  // Without this the CI job started the backend, installed browsers, and ran the
  // suite against a port nobody was listening on — a workflow that had never been
  // executed and could not have passed. Locally it reuses whatever dev server is
  // already running, so nothing changes for day-to-day work.
  //
  // The backend is NOT started here: it needs a migrated Postgres, which belongs
  // to the CI job (and to `docker compose up` locally).
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
