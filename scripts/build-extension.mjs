// Build a browser extension for a target (chrome|firefox), version-synced.
// Usage: node scripts/build-extension.mjs chrome
import { execSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

const arg = process.argv[2] || "chrome";
const target = arg === "firefox" ? "firefox" : "chromium";
const manifestName = target === "firefox" ? "firefox.json" : "chromium.json";

// Single source of truth for version (from package.json).
const pkg = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));

console.log(`>> vite build (${target})`);
execSync(`TARGET=${target} npx vite build`, { cwd: root, stdio: "inherit" });

const outDir = resolve(root, `extension/dist/${target}`);
mkdirSync(outDir, { recursive: true });

// Manifest: inject the synchronized version.
const manifest = JSON.parse(readFileSync(resolve(root, "extension/manifest", manifestName), "utf8"));
manifest.version = pkg.version;
writeFileSync(resolve(outDir, "manifest.json"), JSON.stringify(manifest, null, 2));

// Icon (optional; generated placeholder if missing so builds never fail).
const iconSrc = resolve(root, "extension/public/icon128.png");
const iconDst = resolve(outDir, "icon128.png");
if (existsSync(iconSrc)) {
  copyFileSync(iconSrc, iconDst);
} else {
  // 1x1 transparent PNG so the manifest icon reference resolves.
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "base64",
  );
  writeFileSync(iconDst, png);
}

console.log(`>> built extension/dist/${target} (v${manifest.version})`);
