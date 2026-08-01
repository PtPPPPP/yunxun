import { defineConfig } from "playwright/test";
import { join } from "node:path";
import { tmpdir } from "node:os";

const databasePath = join(tmpdir(), `yunxun-e2e-${process.pid}.db`);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:5174",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "python ../backend/main.py",
      cwd: ".",
      port: 8011,
      env: {
        YUNXUN_PORT: "8011",
        YUNXUN_HOST: "127.0.0.1",
        YUNXUN_DB_PATH: databasePath,
        YUNXUN_ALLOWED_ORIGINS: "http://127.0.0.1:5174",
        YUNXUN_REQUESTS_PER_MINUTE: "600",
        DOUBAO_API_KEY: "",
        BYOK_ENABLED: "true",
        BYOK_ALLOW_PERSISTENCE: "true",
        BYOK_ALLOWED_PROVIDERS: "openai",
        YUNXUN_CREDENTIAL_ENCRYPTION_KEY: "ZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWU=",
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5174",
      cwd: ".",
      port: 5174,
      env: { VITE_YUNXUN_API_BASE_URL: "http://127.0.0.1:8011" },
    },
  ],
  globalTeardown: "./e2e/teardown.ts",
  metadata: { databasePath },
});
