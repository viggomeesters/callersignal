#!/usr/bin/env node

import { cp, mkdir, rm } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const outputRoot = join(repositoryRoot, "public");

if (dirname(outputRoot) !== repositoryRoot || basename(outputRoot) !== "public") {
  throw new Error("Refusing to stage outside the explicit public output directory.");
}

await rm(outputRoot, { recursive: true, force: true });
await mkdir(outputRoot, { recursive: true });
await cp(join(repositoryRoot, "web", "index.html"), join(outputRoot, "index.html"));
await cp(join(repositoryRoot, "web", "assets"), join(outputRoot, "assets"), {
  recursive: true,
});

process.stdout.write("staged web/index.html and web/assets in public/\n");
