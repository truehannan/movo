// Package the built Firefox extension into dist/firefox/extension.xpi.
// An .xpi is a zip with the manifest at the root.
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = resolve(root, "extension/dist/firefox");
const outDir = resolve(root, "dist/firefox");
mkdirSync(outDir, { recursive: true });
const out = resolve(outDir, "extension.xpi");
execSync(`cd "${src}" && zip -r -q "${out}" . -x '*.map'`, { stdio: "inherit" });
console.log(`>> packaged ${out}`);
