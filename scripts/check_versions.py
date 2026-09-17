#!/usr/bin/env python3
"""Validate project and per-skill release versions before tagging or publishing."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def load_manifest(root: Path = ROOT) -> dict:
    project_version = (root / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads((root / "skill-versions.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    if not SEMVER.fullmatch(project_version):
        errors.append(f"VERSION 不是 SemVer：{project_version}")
    if manifest.get("project", {}).get("version") != project_version:
        errors.append("VERSION 与 skill-versions.json 的 project.version 不一致")
    if manifest.get("project", {}).get("tag") != f"v{project_version}":
        errors.append("project.tag 必须等于 v + project.version")

    skills = manifest.get("skills", {})
    expected = {
        path.name for path in root.iterdir()
        if path.is_dir() and (path / "SKILL.md").exists() and path.name != "trading-sop-workspace"
    }
    if set(skills) != expected:
        errors.append(f"Skill 清单不完整：manifest={sorted(skills)}, workspace={sorted(expected)}")
    for name, item in skills.items():
        version = item.get("version", "")
        if not SEMVER.fullmatch(version):
            errors.append(f"{name} 版本不是 SemVer：{version}")
        if item.get("slug") != f"@fize/{name}":
            errors.append(f"{name} 的 ClawHub slug 不符合目录名")
    if errors:
        raise ValueError("；".join(errors))
    return {"project": project_version, "skills": skills}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="可选：校验发布 tag 是否等于 manifest 的 project.tag")
    args = parser.parse_args()
    result = load_manifest()
    if args.tag and args.tag != f"v{result['project']}":
        raise SystemExit(f"发布 tag {args.tag} 与项目版本 v{result['project']} 不一致")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
