import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_versions", ROOT / "scripts" / "check_versions.py")
check_versions = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(check_versions)


class VersionContractTests(unittest.TestCase):
    def test_project_and_skill_versions_are_consistent(self):
        result = check_versions.load_manifest(ROOT)
        self.assertEqual(result["project"], "1.1.0")
        self.assertEqual(result["skills"]["trading-sop"]["version"], "1.1.0")
        self.assertEqual(result["skills"]["sim-trade"]["version"], "1.0.0")

    def test_major_version_policy_is_explicit(self):
        manifest = (ROOT / "skill-versions.json").read_text(encoding="utf-8")
        self.assertIn("根本性重构", manifest)
        self.assertIn("向后兼容", manifest)


if __name__ == "__main__":
    unittest.main()
