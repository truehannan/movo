// Package the built Chromium extension into dist/chrome/extension.zip.
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = resolve(root, "extension/dist/chromium");
const outDir = resolve(root, "dist/chrome");
mkdirSync(outDir, { recursive: true });
const out = resolve(outDir, "extension.zip");
// Zip the contents (not the parent folder) so the manifest is at the root.
execSync(`cd "${src}" && zip -r -q "${out}" . -x '*.map'`, { stdio: "inherit" });
console.log(`>> packaged ${out}`);
