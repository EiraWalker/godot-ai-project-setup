#!/usr/bin/env python3
"""Verify a signed release; optionally install into an absent project addon path."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path


def load_verifier(repo: Path):
    path = repo / "src/godot_ai/release_verify.py"
    spec = importlib.util.spec_from_file_location("godot_ai_setup_verifier", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load verifier: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, hashlib.sha256(path.read_bytes()).hexdigest()


def install(args) -> dict:
    project = args.project.expanduser().resolve(strict=True)
    if not (project / "project.godot").is_file():
        raise ValueError(f"Missing project.godot: {project}")
    addons = project / "addons"
    if os.path.lexists(addons) and (
        addons.is_symlink() or addons.resolve() != addons or not addons.is_dir()
    ):
        raise ValueError(f"addons must be a regular project directory: {addons}")
    live = addons / "godot_ai"
    if os.path.lexists(live):
        raise ValueError(f"Addon already exists; inspect or use the update workflow: {live}")
    if os.path.lexists(addons / ".godot_ai_update"):
        raise ValueError(
            "Existing .godot_ai_update state requires inspection before a fresh install"
        )
    verifier, verifier_hash = load_verifier(args.repo.expanduser().resolve(strict=True))
    expected = ("hi-godot/godot-ai", "stable", args.tag, args.version, args.source)
    archive = args.assets / verifier.ASSET_NAME
    manifest_file = args.assets / verifier.MANIFEST_NAME
    signature = args.assets / verifier.SIGNATURE_NAME
    manifest = verifier.verify_release(archive, manifest_file, signature, expected)
    expected_tree = verifier.inventory_tree_hash(manifest)
    report = {
        "status": "verified_preview",
        "project": str(project),
        "destination": str(live),
        "tag": args.tag,
        "version": args.version,
        "source_commit": args.source,
        "verifier_sha256": verifier_hash,
        "key_spki_sha256": verifier.PUBLIC_KEY_SPKI_SHA256,
        "tree_sha256": expected_tree,
        "file_count": len(manifest["inventory"]),
    }
    if not args.apply:
        return report
    addons.mkdir(exist_ok=True)
    # Same-volume staging; upstream verifies frozen bytes before extracting them.
    with tempfile.TemporaryDirectory(prefix=".godot-ai-setup-", dir=addons) as temp:
        stage, _, staged_manifest = verifier.stage_verified_release(
            archive, manifest_file, signature, expected, Path(temp) / "verified"
        )
        if verifier.inventory_tree_hash(staged_manifest) != expected_tree:
            raise RuntimeError("Release changed between preview verification and staging")
        if os.path.lexists(live):
            raise ValueError(f"Destination appeared while staging: {live}")
        stage.rename(live)
    if verifier.hash_tree(live)["tree_sha256"] != expected_tree:
        raise RuntimeError(f"Installed tree verification failed; retain for inspection: {live}")
    report["status"] = "installed_files_only"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True, help="Trusted local Godot AI checkout")
    parser.add_argument(
        "--assets", type=Path, required=True, help="Directory with signed asset triple"
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source", required=True, help="Independently confirmed release commit")
    parser.add_argument(
        "--apply", action="store_true", help="Install verified files; otherwise preview only"
    )
    try:
        report = install(parser.parse_args())
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
