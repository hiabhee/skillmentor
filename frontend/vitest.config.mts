import { defineConfig } from "vitest/config";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"] },
  resolve: { alias: { "@": projectDir } },
});
