from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "configure-agent-team" / "scripts" / "configure_agent_team.py"
SPEC = importlib.util.spec_from_file_location("configure_agent_team", SCRIPT_PATH)
assert SPEC and SPEC.loader
CONFIGURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIGURE)

CATALOG = {
    "orchestrator-test": {
        "slug": "orchestrator-test",
        "default_reasoning_level": "high",
        "supported_reasoning_levels": [
            {"effort": "medium"},
            {"effort": "high"},
            {"effort": "xhigh"},
        ],
    },
    "executor-test": {
        "slug": "executor-test",
        "default_reasoning_level": "medium",
        "supported_reasoning_levels": [
            {"effort": "low"},
            {"effort": "medium"},
            {"effort": "high"},
        ],
    },
}


class ConfigureAgentTeamTests(unittest.TestCase):
    def run_main(self, root: Path, *extra: str) -> tuple[int, str, str]:
        argv = [
            str(SCRIPT_PATH),
            "--root",
            str(root),
            "--orchestrator-model",
            "orchestrator-test",
            "--orchestrator-effort",
            "high",
            "--executor-model",
            "executor-test",
            "--executor-effort",
            "auto",
            *extra,
        ]
        stdout = StringIO()
        stderr = StringIO()
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(CONFIGURE, "load_catalog", return_value=CATALOG),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = CONFIGURE.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def update(self, original: str = "", *, managed: bool = False) -> str:
        config_path = Path("/tmp/project/.codex/config.toml")
        layer_path = Path("/tmp/project/.codex/agents/executor-model.toml")
        return CONFIGURE.update_main_config(
            original,
            config_path,
            layer_path,
            "orchestrator-test",
            "high",
            None,
            managed,
        )

    def test_empty_config_adds_only_root_and_additive_executor_role(self) -> None:
        generated = self.update()
        parsed = tomllib.loads(generated)

        self.assertEqual(parsed["model"], "orchestrator-test")
        self.assertEqual(parsed["model_reasoning_effort"], "high")
        self.assertEqual(set(parsed["agents"]), {"executor"})
        self.assertEqual(
            parsed["agents"]["executor"]["config_file"],
            "agents/executor-model.toml",
        )
        self.assertNotIn("max_threads", generated)
        self.assertNotIn("max_depth", generated)
        self.assertNotIn("agents.default", generated)
        self.assertNotIn("agents.worker", generated)

    def test_executor_layer_has_only_model_configuration(self) -> None:
        generated = CONFIGURE.build_role_layer("executor-test", "medium", None)
        parsed = tomllib.loads(generated)

        self.assertEqual(
            parsed,
            {
                "model": "executor-test",
                "model_reasoning_effort": "medium",
            },
        )
        for forbidden in (
            "developer_instructions",
            "name",
            "nickname_candidates",
            "max_threads",
            "max_depth",
        ):
            self.assertNotIn(forbidden, generated)

    def test_preserves_builtin_overrides_limits_comments_and_other_tables(self) -> None:
        original = """# user's config
model = "old-root"

[features]
multi_agent = true

[agents]
max_threads = 7
max_depth = 3

[agents.default]
description = "User-owned default"

[agents.worker]
description = "User-owned worker"

[agents.explorer]
description = "User-owned explorer"
"""
        generated = self.update(original)
        parsed = tomllib.loads(generated)

        self.assertIn("# user's config", generated)
        self.assertTrue(parsed["features"]["multi_agent"])
        self.assertEqual(parsed["agents"]["max_threads"], 7)
        self.assertEqual(parsed["agents"]["max_depth"], 3)
        self.assertEqual(parsed["agents"]["default"]["description"], "User-owned default")
        self.assertEqual(parsed["agents"]["worker"]["description"], "User-owned worker")
        self.assertEqual(parsed["agents"]["explorer"]["description"], "User-owned explorer")

    def test_preserves_dotted_agent_limits(self) -> None:
        original = """agents.max_threads = 9
agents.max_depth = 2
model = "old-root"
"""
        generated = self.update(original)

        self.assertIn("agents.max_threads = 9", generated)
        self.assertIn("agents.max_depth = 2", generated)

    def test_update_is_idempotent(self) -> None:
        first = self.update()
        second = self.update(first, managed=True)

        self.assertEqual(first, second)
        self.assertEqual(first.count(CONFIGURE.MANAGED_MARKER), 1)
        self.assertEqual(first.count("[agents.executor]"), 1)

    def test_existing_executor_role_conflict_is_refused(self) -> None:
        original = """[agents.executor]
description = "Mine"
config_file = "agents/mine.toml"
"""
        with self.assertRaises(CONFIGURE.ConfigurationError):
            self.update(original)

    def test_same_path_executor_role_without_provenance_is_refused(self) -> None:
        original = """[agents.executor]
description = "User-owned"
config_file = "agents/executor-model.toml"
"""
        with self.assertRaises(CONFIGURE.ConfigurationError):
            self.update(original)

    def test_auto_executor_effort_resolves_to_executor_default(self) -> None:
        resolved = CONFIGURE.resolve_executor_effort(
            "auto", "xhigh", "executor-test", CATALOG
        )
        self.assertEqual(resolved, "medium")

    def test_dry_run_has_no_filesystem_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, stdout, _ = self.run_main(root)

            self.assertEqual(result, 0)
            self.assertIn("Dry run only", stdout)
            self.assertFalse((root / ".codex").exists())

    def test_apply_writes_valid_model_only_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, stdout, _ = self.run_main(root, "--apply")
            config_path = root / ".codex" / "config.toml"
            layer_path = root / ".codex" / "agents" / "executor-model.toml"

            self.assertEqual(result, 0)
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            layer = tomllib.loads(layer_path.read_text(encoding="utf-8"))
            self.assertEqual(set(config["agents"]), {"executor"})
            self.assertEqual(layer["model"], "executor-test")
            self.assertEqual(layer["model_reasoning_effort"], "medium")
            self.assertIn("full-history", stdout)

    def test_unmanaged_executor_layer_is_refused_without_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layer_path = root / ".codex" / "agents" / "executor-model.toml"
            layer_path.parent.mkdir(parents=True)
            layer_path.write_text('model = "user-owned"\n', encoding="utf-8")

            result, _, stderr = self.run_main(root, "--apply")

            self.assertEqual(result, 2)
            self.assertIn("Refusing to replace unmanaged", stderr)
            self.assertFalse((root / ".codex" / "config.toml").exists())
            self.assertEqual(layer_path.read_text(encoding="utf-8"), 'model = "user-owned"\n')

    def test_legacy_migration_removes_only_managed_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_dir = root / ".codex"
            legacy_path = codex_dir / "agents" / CONFIGURE.LEGACY_AGENT_FILENAME
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text(
                f"{CONFIGURE.LEGACY_MARKER}\nname = \"Legacy\"\n",
                encoding="utf-8",
            )
            config_path = codex_dir / "config.toml"
            config_path.write_text(
                "[agents]\nmax_threads = 3\nmax_depth = 1\n",
                encoding="utf-8",
            )

            result, _, _ = self.run_main(root, "--migrate-legacy", "--apply")
            parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(result, 0)
            self.assertFalse(legacy_path.exists())
            self.assertTrue(
                legacy_path.with_name(
                    legacy_path.name + ".bak.configure-agent-team"
                ).exists()
            )
            self.assertEqual(parsed["agents"]["max_threads"], 3)
            self.assertEqual(parsed["agents"]["max_depth"], 1)

    def test_legacy_file_requires_explicit_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = (
                root
                / ".codex"
                / "agents"
                / CONFIGURE.LEGACY_AGENT_FILENAME
            )
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text(
                f"{CONFIGURE.LEGACY_MARKER}\nname = \"Legacy\"\n",
                encoding="utf-8",
            )

            result, _, stderr = self.run_main(root, "--apply")

            self.assertEqual(result, 2)
            self.assertIn("--migrate-legacy", stderr)
            self.assertTrue(legacy_path.exists())
            self.assertFalse((root / ".codex" / "config.toml").exists())

    def test_legacy_migration_dry_run_does_not_remove_or_back_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = (
                root
                / ".codex"
                / "agents"
                / CONFIGURE.LEGACY_AGENT_FILENAME
            )
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text(
                f"{CONFIGURE.LEGACY_MARKER}\nname = \"Legacy\"\n",
                encoding="utf-8",
            )

            result, stdout, _ = self.run_main(root, "--migrate-legacy")

            self.assertEqual(result, 0)
            self.assertIn("Dry run only", stdout)
            self.assertTrue(legacy_path.exists())
            self.assertFalse(
                legacy_path.with_name(
                    legacy_path.name + ".bak.configure-agent-team"
                ).exists()
            )
            self.assertFalse((root / ".codex" / "config.toml").exists())

    def test_unmanaged_legacy_named_file_is_never_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = (
                root
                / ".codex"
                / "agents"
                / CONFIGURE.LEGACY_AGENT_FILENAME
            )
            legacy_path.parent.mkdir(parents=True)
            original = 'name = "User-owned"\n'
            legacy_path.write_text(original, encoding="utf-8")

            result, _, _ = self.run_main(root, "--migrate-legacy", "--apply")

            self.assertEqual(result, 0)
            self.assertEqual(legacy_path.read_text(encoding="utf-8"), original)
            self.assertFalse(
                legacy_path.with_name(
                    legacy_path.name + ".bak.configure-agent-team"
                ).exists()
            )

    def test_malformed_existing_config_fails_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / ".codex" / "config.toml"
            config_path.parent.mkdir(parents=True)
            original = 'model = "unterminated\n'
            config_path.write_text(original, encoding="utf-8")

            result, _, stderr = self.run_main(root, "--apply")

            self.assertEqual(result, 2)
            self.assertIn("not valid TOML", stderr)
            self.assertEqual(config_path.read_text(encoding="utf-8"), original)
            self.assertFalse(
                (root / ".codex" / "agents" / "executor-model.toml").exists()
            )


if __name__ == "__main__":
    unittest.main()
