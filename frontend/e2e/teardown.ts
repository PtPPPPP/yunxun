import { rm } from "node:fs/promises";
import type { FullConfig } from "playwright/test";

export default async function teardown(config: FullConfig) {
  const databasePath = String(config.metadata.databasePath);
  await Promise.all(
    [databasePath, `${databasePath}-wal`, `${databasePath}-shm`].map((path) => rm(path, { force: true })),
  );
}
