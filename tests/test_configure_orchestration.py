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
SCRIPT_PATH = (
    REPO_ROOT
    / "plugins"
    / "codex-orchestration"
    / "skills"
    / "codex-orchestration"
    / "scripts"
    / "configure_orchestration.py"
)
SPEC = importlib.util.spec_from_file_location("configure_orchestration", SCRIPT_PATH)
assert SPEC and SPEC.loader
CONFIGURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIGURE)

CATALOG = {
    "executor-test": {
        "slug": "executor-test",
        "default_reasoning_level": "medium",
        "supported_reasoning_levels": [
            {"effort": "low"},
            {"effort": "medium"},
            {"effort": "high"},
        ],
    },
    "advisor-test": {
        "slug": "advisor-test",
        "default_reasoning_level": "high",
        "supported_reasoning_levels": [
            {"effort": "medium"},
            {"effort": "high"},
            {"effort": "xhigh"},
        ],
    },
}


class ConfigureOrchestrationTests(unittest.TestCase):
    def run_main(self, root: Path, *extra: str) -> tuple[int, str, str]:
        argv = [
            str(SCRIPT_PATH),
            "--root",
            str(root),
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

    def update(
        self,
        original: str = "",
        *,
        executor_managed: bool = False,
        advisor_action: str = "preserve",
        advisor_managed: bool = False,
    ) -> str:
        config_path = Path("/tmp/project/.codex/config.toml")
        executor_path = Path("/tmp/project/.codex/agents/executor-model.toml")
        advisor_path = Path("/tmp/project/.codex/agents/advisor-model.toml")
        return CONFIGURE.update_main_config(
            original,
            config_path,
            executor_path,
            executor_managed,
            advisor_layer_path=advisor_path,
            advisor_action=advisor_action,
            advisor_managed_provenance=advisor_managed,
        )

    def test_empty_config_adds_executor_role_but_never_root_model(self) -> None:
        generated = self.update()
        parsed = tomllib.loads(generated)

        self.assertNotIn("model", parsed)
        self.assertNotIn("model_reasoning_effort", parsed)
        self.assertNotIn("model_provider", parsed)
        self.assertEqual(set(parsed["agents"]), {"executor"})
        self.assertEqual(
            parsed["agents"]["executor"]["config_file"],
            "agents/executor-model.toml",
        )
        self.assertNotIn("max_threads", generated)
        self.assertNotIn("max_depth", generated)
        self.assertNotIn("agents.default", generated)
        self.assertNotIn("agents.worker", generated)

    def test_role_layers_contain_only_model_configuration(self) -> None:
        cases = (
            (
                "executor",
                "executor-test",
                "medium",
                None,
                {"model": "executor-test", "model_reasoning_effort": "medium"},
            ),
            (
                "advisor",
                "advisor-test",
                "high",
                "anthropic",
                {
                    "model": "advisor-test",
                    "model_reasoning_effort": "high",
                    "model_provider": "anthropic",
                },
            ),
        )
        for label, model, effort, provider, expected in cases:
            generated = CONFIGURE.build_role_layer(
                model, effort, provider, label=label
            )
            self.assertEqual(tomllib.loads(generated), expected)
            for forbidden in (
                "developer_instructions",
                "name",
                "nickname_candidates",
                "max_threads",
                "max_depth",
            ):
                self.assertNotIn(forbidden, generated)

    def test_preserves_root_builtin_roles_limits_comments_and_tables(self) -> None:
        original = """# user's config
model = "user-selected-default"
model_reasoning_effort = "xhigh"

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
        self.assertEqual(parsed["model"], "user-selected-default")
        self.assertEqual(parsed["model_reasoning_effort"], "xhigh")
        self.assertTrue(parsed["features"]["multi_agent"])
        self.assertEqual(parsed["agents"]["max_threads"], 7)
        self.assertEqual(parsed["agents"]["max_depth"], 3)
        self.assertEqual(parsed["agents"]["default"]["description"], "User-owned default")
        self.assertEqual(parsed["agents"]["worker"]["description"], "User-owned worker")
        self.assertEqual(parsed["agents"]["explorer"]["description"], "User-owned explorer")

    def test_preserves_dotted_agent_limits_and_root(self) -> None:
        original = """agents.max_threads = 9
agents.max_depth = 2
model = "old-root"
"""
        generated = self.update(original)
        self.assertIn("agents.max_threads = 9", generated)
        self.assertIn("agents.max_depth = 2", generated)
        self.assertIn('model = "old-root"', generated)

    def test_update_is_idempotent(self) -> None:
        first = self.update()
        second = self.update(first, executor_managed=True)

        self.assertEqual(first, second)
        self.assertEqual(first.count(CONFIGURE.MANAGED_MARKER), 1)
        self.assertEqual(first.count("[agents.executor]"), 1)

    def test_advisor_is_optional_and_added_without_changing_root(self) -> None:
        original = 'model = "root-stays"\n'
        generated = self.update(original, advisor_action="configure")
        parsed = tomllib.loads(generated)

        self.assertEqual(parsed["model"], "root-stays")
        self.assertEqual(set(parsed["agents"]), {"executor", "advisor"})
        self.assertEqual(
            parsed["agents"]["advisor"]["config_file"],
            "agents/advisor-model.toml",
        )
        self.assertIn("reports only to the root orchestrator", generated)
        self.assertIn("never directs or coordinates executors", generated)

    def test_previous_release_markers_upgrade_and_preserve_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / ".codex" / "config.toml"
            layer_path = root / ".codex" / "agents" / "executor-model.toml"
            layer_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        CONFIGURE.PREVIOUS_MANAGED_MARKER,
                        'model = "old-root"',
                        'model_reasoning_effort = "xhigh"',
                        "",
                        "[agents.executor]",
                        'description = "Old description"',
                        'config_file = "agents/executor-model.toml"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            layer_path.write_text(
                f'{CONFIGURE.PREVIOUS_MANAGED_MARKER}\nmodel = "old-worker"\n',
                encoding="utf-8",
            )

            result, _, stderr = self.run_main(root, "--apply")
            parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(result, 0)
            self.assertEqual(parsed["model"], "old-root")
            self.assertEqual(parsed["model_reasoning_effort"], "xhigh")
            self.assertIn("never configures the root", stderr)
            self.assertTrue(
                config_path.read_text(encoding="utf-8").startswith(
                    CONFIGURE.MANAGED_MARKER
                )
            )
            self.assertTrue(
                layer_path.read_text(encoding="utf-8").startswith(
                    CONFIGURE.MANAGED_MARKER
                )
            )

    def test_managed_markers_below_comments_are_recognized_and_moved_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / ".codex" / "config.toml"
            layer_path = root / ".codex" / "agents" / "executor-model.toml"
            layer_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        "# keep this user comment",
                        CONFIGURE.PREVIOUS_MANAGED_MARKER,
                        'model = "root-stays"',
                        "",
                        "[agents.executor]",
                        'description = "Old"',
                        'config_file = "agents/executor-model.toml"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            layer_path.write_text(
                "# keep layer comment\n"
                f"{CONFIGURE.PREVIOUS_MANAGED_MARKER}\n"
                'model = "old-executor"\n',
                encoding="utf-8",
            )

            result, _, _ = self.run_main(root, "--apply")

            self.assertEqual(result, 0)
            updated_config = config_path.read_text(encoding="utf-8")
            updated_layer = layer_path.read_text(encoding="utf-8")
            self.assertEqual(updated_config.splitlines()[0], CONFIGURE.MANAGED_MARKER)
            self.assertEqual(updated_layer.splitlines()[0], CONFIGURE.MANAGED_MARKER)
            self.assertIn("# keep this user comment", updated_config)
            self.assertIn("# keep layer comment", updated_layer)
            self.assertEqual(tomllib.loads(updated_config)["model"], "root-stays")

    def test_existing_executor_role_conflicts_are_refused(self) -> None:
        cases = (
            """[agents.executor]
description = "Mine"
config_file = "agents/mine.toml"
""",
            """[agents.executor]
description = "User-owned"
config_file = "agents/executor-model.toml"
""",
        )
        for original in cases:
            with self.subTest(original=original):
                with self.assertRaises(CONFIGURE.ConfigurationError):
                    self.update(original)

    def test_existing_advisor_conflict_is_refused_only_when_touched(self) -> None:
        original = """[agents.advisor]
description = "Mine"
config_file = "agents/mine.toml"
"""
        preserved = self.update(original)
        self.assertIn('config_file = "agents/mine.toml"', preserved)

        with self.assertRaises(CONFIGURE.ConfigurationError):
            self.update(original, advisor_action="configure")

    def test_remove_advisor_refuses_extra_settings_with_provenance(self) -> None:
        original = f"""{CONFIGURE.MANAGED_MARKER}
[agents.advisor]
description = "Managed"
config_file = "agents/advisor-model.toml"
extra = true
"""
        with self.assertRaises(CONFIGURE.ConfigurationError):
            self.update(
                original,
                advisor_action="remove",
                advisor_managed=True,
            )

    def test_auto_efforts_resolve_to_each_seats_own_default(self) -> None:
        self.assertEqual(
            CONFIGURE.resolve_role_effort(
                "auto", "Executor", "executor-test", CATALOG
            ),
            "medium",
        )
        self.assertEqual(
            CONFIGURE.resolve_role_effort(
                "auto", "Advisor", "advisor-test", CATALOG
            ),
            "high",
        )
        with self.assertRaises(CONFIGURE.ConfigurationError):
            CONFIGURE.resolve_role_effort("auto", "Advisor", "missing", {})

    def test_dry_run_has_no_filesystem_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, stdout, _ = self.run_main(root)

            self.assertEqual(result, 0)
            self.assertIn("Dry run only", stdout)
            self.assertFalse((root / ".codex").exists())

    def test_apply_writes_executor_without_root_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, stdout, _ = self.run_main(root, "--apply")
            config_path = root / ".codex" / "config.toml"
            layer_path = root / ".codex" / "agents" / "executor-model.toml"

            self.assertEqual(result, 0)
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            layer = tomllib.loads(layer_path.read_text(encoding="utf-8"))
            self.assertEqual(set(config["agents"]), {"executor"})
            self.assertNotIn("model", config)
            self.assertEqual(layer["model"], "executor-test")
            self.assertEqual(layer["model_reasoning_effort"], "medium")
            self.assertIn("current session model remains", stdout)

    def test_apply_writes_and_explicitly_removes_managed_advisor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, _, _ = self.run_main(
                root,
                "--advisor-model",
                "advisor-test",
                "--advisor-effort",
                "auto",
                "--apply",
            )
            config_path = root / ".codex" / "config.toml"
            advisor_path = root / ".codex" / "agents" / "advisor-model.toml"

            self.assertEqual(result, 0)
            self.assertEqual(
                tomllib.loads(advisor_path.read_text(encoding="utf-8")),
                {"model": "advisor-test", "model_reasoning_effort": "high"},
            )
            self.assertIn(
                "advisor",
                tomllib.loads(config_path.read_text(encoding="utf-8"))["agents"],
            )

            result, _, _ = self.run_main(root, "--remove-advisor", "--apply")
            self.assertEqual(result, 0)
            self.assertFalse(advisor_path.exists())
            self.assertEqual(
                set(tomllib.loads(config_path.read_text(encoding="utf-8"))["agents"]),
                {"executor"},
            )

    def test_apply_rolls_back_every_file_when_a_commit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.run_main(root, "--advisor-model", "advisor-test", "--apply")
            config_path = root / ".codex" / "config.toml"
            executor_path = root / ".codex" / "agents" / "executor-model.toml"
            advisor_path = root / ".codex" / "agents" / "advisor-model.toml"
            paths = (config_path, executor_path, advisor_path)
            before = {path: path.read_text(encoding="utf-8") for path in paths}
            real_replace = CONFIGURE.os.replace
            injected = False

            def fail_second_layer_once(source: object, destination: object) -> None:
                nonlocal injected
                if Path(destination) == advisor_path and not injected:
                    injected = True
                    raise OSError("injected commit failure")
                real_replace(source, destination)

            with mock.patch.object(
                CONFIGURE.os, "replace", side_effect=fail_second_layer_once
            ):
                result, _, stderr = self.run_main(
                    root,
                    "--executor-effort",
                    "high",
                    "--advisor-model",
                    "advisor-test",
                    "--advisor-effort",
                    "xhigh",
                    "--apply",
                )

            self.assertTrue(injected)
            self.assertEqual(result, 2)
            self.assertIn("committed files were restored", stderr)
            self.assertEqual(
                {path: path.read_text(encoding="utf-8") for path in paths},
                before,
            )
            temporary_files = [
                path
                for path in (root / ".codex").rglob("*")
                if path.is_file() and path not in paths
            ]
            self.assertEqual(temporary_files, [])

    def test_omitting_advisor_preserves_existing_managed_advisor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.run_main(root, "--advisor-model", "advisor-test", "--apply")
            advisor_path = root / ".codex" / "agents" / "advisor-model.toml"
            before = advisor_path.read_text(encoding="utf-8")

            result, _, stderr = self.run_main(root, "--apply")

            self.assertEqual(result, 0)
            self.assertEqual(advisor_path.read_text(encoding="utf-8"), before)
            self.assertIn("advisor route was left unchanged", stderr)

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
            self.assertEqual(
                layer_path.read_text(encoding="utf-8"),
                'model = "user-owned"\n',
            )

    def test_unmanaged_advisor_layer_is_refused_without_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            advisor_path = root / ".codex" / "agents" / "advisor-model.toml"
            advisor_path.parent.mkdir(parents=True)
            advisor_path.write_text('model = "user-owned"\n', encoding="utf-8")

            result, _, stderr = self.run_main(root, "--remove-advisor", "--apply")

            self.assertEqual(result, 2)
            self.assertIn("Refusing to remove unmanaged", stderr)
            self.assertFalse((root / ".codex" / "config.toml").exists())
            self.assertTrue(advisor_path.exists())

    def test_managed_executor_layer_with_extra_keys_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layer_path = root / ".codex" / "agents" / "executor-model.toml"
            layer_path.parent.mkdir(parents=True)
            original = (
                f"{CONFIGURE.MANAGED_MARKER}\n"
                'model = "executor-test"\n'
                'sandbox_mode = "read-only"\n'
            )
            layer_path.write_text(original, encoding="utf-8")

            result, _, stderr = self.run_main(root, "--apply")

            self.assertEqual(result, 2)
            self.assertIn("beyond model routing: sandbox_mode", stderr)
            self.assertEqual(layer_path.read_text(encoding="utf-8"), original)
            self.assertFalse((root / ".codex" / "config.toml").exists())

    def test_managed_advisor_layer_with_extra_keys_refuses_update_and_removal(self) -> None:
        for action in ("configure", "remove"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.run_main(root, "--advisor-model", "advisor-test", "--apply")
                advisor_path = root / ".codex" / "agents" / "advisor-model.toml"
                with advisor_path.open("a", encoding="utf-8") as handle:
                    handle.write('developer_instructions = "user-added"\n')
                original = advisor_path.read_text(encoding="utf-8")
                extra = (
                    ("--advisor-model", "advisor-test")
                    if action == "configure"
                    else ("--remove-advisor",)
                )

                result, _, stderr = self.run_main(root, *extra, "--apply")

                self.assertEqual(result, 2)
                self.assertIn("beyond model routing: developer_instructions", stderr)
                self.assertEqual(advisor_path.read_text(encoding="utf-8"), original)

    def test_advisor_flags_require_model_and_project_provider_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, _, stderr = self.run_main(root, "--advisor-effort", "high")
            self.assertEqual(result, 2)
            self.assertIn("require --advisor-model", stderr)

            result, _, stderr = self.run_main(
                root, "--executor-provider", "custom"
            )
            self.assertEqual(result, 2)
            self.assertIn("Project-scoped", stderr)

    def test_symlinked_config_and_role_layers_are_refused(self) -> None:
        for target_name in ("config.toml", "agents/executor-model.toml"):
            with self.subTest(target_name=target_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                outside = root / "outside.toml"
                original = 'model = "outside-must-not-change"\n'
                outside.write_text(original, encoding="utf-8")
                managed_path = root / ".codex" / target_name
                managed_path.parent.mkdir(parents=True)
                managed_path.symlink_to(outside)

                result, _, stderr = self.run_main(root, "--apply")

                self.assertEqual(result, 2)
                self.assertIn("symlinked managed path", stderr)
                self.assertEqual(outside.read_text(encoding="utf-8"), original)
                self.assertTrue(managed_path.is_symlink())

    def test_retired_orchestrator_flags_are_not_accepted(self) -> None:
        stderr = StringIO()
        argv = [
            str(SCRIPT_PATH),
            "--executor-model",
            "executor-test",
            "--orchestrator-model",
            "root-must-not-be-configured",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            CONFIGURE.parse_args()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments: --orchestrator-model", stderr.getvalue())

    def test_legacy_migration_removes_only_managed_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_dir = root / ".codex"
            legacy_path = codex_dir / "agents" / CONFIGURE.LEGACY_AGENT_FILENAME
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text(
                f'{CONFIGURE.LEGACY_MARKER}\nname = "Legacy"\n',
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
                    legacy_path.name + ".bak.codex-orchestration"
                ).exists()
            )
            self.assertEqual(parsed["agents"]["max_threads"], 3)
            self.assertEqual(parsed["agents"]["max_depth"], 1)

    def test_custom_named_exact_marker_legacy_agent_is_detected_and_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            custom = root / ".codex" / "agents" / "my_custom_worker.toml"
            custom.parent.mkdir(parents=True)
            original = (
                "# preceding comment is allowed\n"
                f"{CONFIGURE.LEGACY_MARKER}\n"
                'name = "Custom legacy worker"\n'
            )
            custom.write_text(original, encoding="utf-8")

            result, _, stderr = self.run_main(root, "--apply")
            self.assertEqual(result, 2)
            self.assertIn("my_custom_worker.toml", stderr)
            self.assertTrue(custom.exists())

            result, stdout, _ = self.run_main(root, "--migrate-legacy")
            self.assertEqual(result, 0)
            self.assertIn("my_custom_worker.toml", stdout)
            self.assertTrue(custom.exists())

            result, _, _ = self.run_main(root, "--migrate-legacy", "--apply")
            backup = custom.with_name(custom.name + ".bak.codex-orchestration")
            self.assertEqual(result, 0)
            self.assertFalse(custom.exists())
            self.assertEqual(backup.read_text(encoding="utf-8"), original)

    def test_legacy_file_requires_explicit_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = root / ".codex" / "agents" / CONFIGURE.LEGACY_AGENT_FILENAME
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text(
                f'{CONFIGURE.LEGACY_MARKER}\nname = "Legacy"\n',
                encoding="utf-8",
            )

            result, _, stderr = self.run_main(root, "--apply")

            self.assertEqual(result, 2)
            self.assertIn("--migrate-legacy", stderr)
            self.assertTrue(legacy_path.exists())
            self.assertFalse((root / ".codex" / "config.toml").exists())

    def test_legacy_migration_dry_run_has_no_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = root / ".codex" / "agents" / CONFIGURE.LEGACY_AGENT_FILENAME
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text(
                f'{CONFIGURE.LEGACY_MARKER}\nname = "Legacy"\n',
                encoding="utf-8",
            )

            result, stdout, _ = self.run_main(root, "--migrate-legacy")

            self.assertEqual(result, 0)
            self.assertIn("Dry run only", stdout)
            self.assertTrue(legacy_path.exists())
            self.assertFalse(
                legacy_path.with_name(
                    legacy_path.name + ".bak.codex-orchestration"
                ).exists()
            )
            self.assertFalse((root / ".codex" / "config.toml").exists())

    def test_unmanaged_legacy_named_file_is_never_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = root / ".codex" / "agents" / CONFIGURE.LEGACY_AGENT_FILENAME
            legacy_path.parent.mkdir(parents=True)
            original = 'name = "User-owned"\n'
            legacy_path.write_text(original, encoding="utf-8")

            result, _, _ = self.run_main(root, "--migrate-legacy", "--apply")

            self.assertEqual(result, 0)
            self.assertEqual(legacy_path.read_text(encoding="utf-8"), original)
            self.assertFalse(
                legacy_path.with_name(
                    legacy_path.name + ".bak.codex-orchestration"
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
