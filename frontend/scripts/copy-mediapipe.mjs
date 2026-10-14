// Serve MediaPipe's WASM runtime from our own origin so face tracking needs no CDN at runtime.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules", "@mediapipe", "tasks-vision", "wasm");
const target = join(root, "public", "mediapipe", "wasm");
if (existsSync(source)) {
  mkdirSync(target, { recursive: true });
  cpSync(source, target, { recursive: true });
}
