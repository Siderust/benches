#!/usr/bin/env node
/**
 * copy-data.mjs — Post-build step for `npm run build:standalone`.
 *
 * Copies the local static lab export from ../../static_export into
 * dist/data/lab so the standalone bundle is fully self-contained and can be
 * served by any static host (e.g. `npx serve dist`).
 *
 * If the source directory does not exist (no static export yet), the script
 * prints a warning and exits 0 — the bundle is still useful for inspecting
 * the UI, just empty of data.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(here, "..");
const REPO_ROOT = path.resolve(FRONTEND_ROOT, "../../");
const SRC = path.resolve(REPO_ROOT, "static_export");
const DST = path.resolve(FRONTEND_ROOT, "dist/data/lab");

async function copyDir(src, dst) {
  await fs.mkdir(dst, { recursive: true });
  const entries = await fs.readdir(src, { withFileTypes: true });
  for (const entry of entries) {
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) await copyDir(s, d);
    else await fs.copyFile(s, d);
  }
}

try {
  await fs.access(SRC);
} catch {
  console.warn(
    `[copy-data] Source data not found at ${SRC}. ` +
      `Run 'python3 -m pipeline.export_static' first to populate it. ` +
      `Standalone bundle will have no run data.`,
  );
  process.exit(0);
}

await copyDir(SRC, DST);
console.log(`[copy-data] Copied ${SRC} -> ${DST}`);
