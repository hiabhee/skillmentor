import { defineConfig, globalIgnores } from "eslint/config";
import nextPlugin from "@next/eslint-plugin-next";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextTypescript,
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    plugins: { "@next/next": nextPlugin },
    rules: nextPlugin.configs["core-web-vitals"].rules,
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "public/mediapipe/**"]),
]);
