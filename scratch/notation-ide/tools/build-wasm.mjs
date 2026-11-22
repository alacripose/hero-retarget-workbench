import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const crate = resolve(root, "core");
const built = resolve(crate, "target/wasm32-unknown-unknown/release/notation_core.wasm");
const publicCopy = resolve(root, "public/notation_core.wasm");
const receipt = resolve(root, "artifacts/wasm-build.json");

mkdirSync(dirname(receipt), { recursive: true });
const started = Date.now();
execFileSync(
  "cargo",
  ["build", "--release", "--target", "wasm32-unknown-unknown", "--manifest-path", resolve(crate, "Cargo.toml")],
  { stdio: "inherit", cwd: root },
);
mkdirSync(dirname(publicCopy), { recursive: true });
copyFileSync(built, publicCopy);
const bytes = readFileSync(publicCopy);
const sha256 = createHash("sha256").update(bytes).digest("hex");
const record = {
  ok: true,
  kind: "wasm-build",
  at: new Date().toISOString(),
  bytes: statSync(publicCopy).size,
  sha256,
  target: "wasm32-unknown-unknown",
  ms: Date.now() - started,
};
writeFileSync(receipt, JSON.stringify(record, null, 2) + "\n");
console.log(`WASM-BUILD ${record.bytes} bytes sha256 ${sha256}`);
