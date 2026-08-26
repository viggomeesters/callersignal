#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if test -f .go/tasks/open/foundation-visual-identity.json; then
  printf 'asset checks deferred until foundation-visual-identity is claimed\n'
  exit 0
fi

uv run python - <<'PY'
from pathlib import Path
import struct

root = Path.cwd()
assets = {
    "assets/hero.png": (1200, 630, 1.60, 2.10),
    "assets/social-preview.png": (1200, 630, 1.90, 2.10),
}

for relative, constraints in assets.items():
    minimum_width, minimum_height, minimum_ratio, maximum_ratio = constraints
    path = root / relative
    if not path.is_file() or path.stat().st_size < 10_000:
        raise SystemExit(f"missing or implausibly small raster asset: {relative}")
    with path.open("rb") as handle:
        signature = handle.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise SystemExit(f"asset is not a PNG: {relative}")
        length = struct.unpack(">I", handle.read(4))[0]
        chunk = handle.read(4)
        if chunk != b"IHDR" or length < 8:
            raise SystemExit(f"asset has no valid PNG header: {relative}")
        width, height = struct.unpack(">II", handle.read(8))
    if width < minimum_width or height < minimum_height:
        raise SystemExit(
            f"asset dimensions too small: {relative} is {width}x{height}, "
            f"minimum is {minimum_width}x{minimum_height}"
        )
    ratio = width / height
    if not minimum_ratio <= ratio <= maximum_ratio:
        raise SystemExit(f"asset ratio out of bounds: {relative} is {ratio:.3f}:1")

readme = (root / "README.md").read_text(encoding="utf-8")
if "![CallerSignal repository hero](assets/hero.png)" not in readme:
    raise SystemExit("README does not render the repository hero near the top")
if readme.index("assets/hero.png") > 600:
    raise SystemExit("README hero is not near the top of the document")

proof = root / "docs/visual-proof.md"
if not proof.is_file():
    raise SystemExit("visual inspection record is missing")
proof_text = proof.read_text(encoding="utf-8")
for check in ("Clipping", "Overlap", "Contrast", "Readability", "Private data", "Watermarks"):
    if check not in proof_text:
        raise SystemExit(f"visual inspection record omits: {check}")
PY

printf 'asset checks passed\n'
