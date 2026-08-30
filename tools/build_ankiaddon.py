"""Package the add-on as dist/snip_occlusion.ankiaddon.

Per the Anki add-on docs, an .ankiaddon file is a zip of the add-on folder's
*contents* (no top-level folder, no meta.json, no caches).

Run from the repo root:  python3 tools/build_ankiaddon.py
"""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "snip_occlusion"
DIST = ROOT / "dist"

EXCLUDE = {"meta.json"}


def main() -> None:
    DIST.mkdir(exist_ok=True)
    out = DIST / "snip_occlusion.ankiaddon"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SRC.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            if path.name in EXCLUDE:
                continue
            zf.write(path, path.relative_to(SRC))
    print("wrote", out)


if __name__ == "__main__":
    main()
