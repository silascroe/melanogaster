"""Verify downloaded and working MaleCNS files against the source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _hash_file(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def verify_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent.parent.parent
    results = []
    for item in manifest["files"]:
        original = root / item["original_path"]
        working = root / item["working_path"]
        row: dict[str, Any] = {"name": item["name"], "original": {}, "working": {}}
        for label, path in (("original", original), ("working", working)):
            if not path.is_file():
                row[label] = {"path": str(path), "exists": False, "ok": False}
                continue
            md5, sha256 = _hash_file(path)
            row[label] = {
                "path": str(path),
                "exists": True,
                "bytes": path.stat().st_size,
                "md5": md5,
                "sha256": sha256,
                "ok": path.stat().st_size == item["bytes"]
                and md5 == item["provider_md5"]
                and sha256 == (item["sha256"] if label == "original" else item["working_sha256"]),
            }
        row["copies_match"] = row["original"].get("sha256") == row["working"].get("sha256")
        row["ok"] = row["original"].get("ok", False) and row["working"].get("ok", False) and row["copies_match"]
        results.append(row)
    return {"manifest": str(manifest_path), "ok": all(row["ok"] for row in results), "files": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify MaleCNS release files")
    parser.add_argument("--manifest", type=Path, default=Path("data/metadata/source_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/verification.json"))
    args = parser.parse_args()
    result = verify_manifest(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
