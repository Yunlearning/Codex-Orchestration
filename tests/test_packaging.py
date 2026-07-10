from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-orchestration"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "codex-orchestration"


class PackagingTests(unittest.TestCase):
    def test_plugin_marketplace_and_skill_names_are_aligned(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        marketplace = json.loads(
            (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertEqual(manifest["name"], "codex-orchestration")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(marketplace["name"], "codex-orchestration")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "codex-orchestration")
        self.assertEqual(entry["source"]["path"], "./plugins/codex-orchestration")
        self.assertRegex(skill, r"(?m)^name: codex-orchestration$")

    def test_explicit_invocation_metadata_is_consistent(self) -> None:
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("$codex-orchestration", metadata)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("/codex-orchestration executor:", readme)
        self.assertIn("$codex-orchestration:codex-orchestration executor:", readme)
        self.assertIn("advisor: none", readme)
        self.assertIn(
            "codex plugin add codex-orchestration@codex-orchestration",
            readme,
        )

    def test_current_session_model_is_the_only_orchestrator(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("current Codex task as the only orchestrator", skill)
        self.assertIn(
            "Codex already has an orchestrator: the model you selected",
            readme,
        )
        self.assertNotIn("--orchestrator-model", skill)
        self.assertNotIn("--orchestrator-model", readme)

    def test_advisor_protocol_is_bounded_and_root_only(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("PLAN_APPROVED", skill)
        self.assertIn("PLAN_REVISE", skill)
        self.assertIn("ADVISOR_BLOCKED", skill)
        self.assertIn("reports only to the root", skill)
        self.assertIn("one confirmation review", skill)

    def test_readme_uses_plain_codex_language_and_simple_flow(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("That model leads the task (ORCHESTRATOR)", readme)
        self.assertIn("ADVISOR checks plan", readme)
        self.assertIn("EXECUTOR handles", readme)
        self.assertNotIn("Native Codex", readme)
        self.assertNotIn("CURRENT SESSION MODEL", readme)

    def test_savings_copy_distinguishes_allowance_from_raw_tokens(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("64.6%", readme)
        self.assertIn("61.2%", readme)
        self.assertRegex(readme, re.compile(r"estimate, not a promise", re.I))
        self.assertRegex(readme, re.compile(r"not.*65% fewer raw tokens", re.I))
        self.assertIn("may increase total tokens", readme)


if __name__ == "__main__":
    unittest.main()
