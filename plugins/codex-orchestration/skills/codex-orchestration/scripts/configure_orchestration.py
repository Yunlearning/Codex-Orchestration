#!/usr/bin/env python3
"""Preview or apply optional persistent Codex model-seat configuration."""

from __future__ import annotations

import argparse
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - Python < 3.11
    raise SystemExit("Python 3.11 or newer is required (missing tomllib).") from exc


MANAGED_MARKER = "# Managed by codex-orchestration. Model routing only."
PREVIOUS_MANAGED_MARKER = "# Managed by configure-agent-team. Model routing only."
LEGACY_MARKER = "# Managed by configure-agent-team."
KNOWN_MANAGED_MARKERS = {MANAGED_MARKER, PREVIOUS_MANAGED_MARKER, LEGACY_MARKER}
ROLE_LAYER_MARKERS = {MANAGED_MARKER, PREVIOUS_MANAGED_MARKER}
ROLE_LAYER_KEYS = {"model", "model_reasoning_effort", "model_provider"}
EXECUTOR_LAYER_RELATIVE_PATH = "agents/executor-model.toml"
ADVISOR_LAYER_RELATIVE_PATH = "agents/advisor-model.toml"
# Compatibility for callers of the first codex-orchestration release.
ROLE_LAYER_RELATIVE_PATH = EXECUTOR_LAYER_RELATIVE_PATH
LEGACY_AGENT_FILENAME = "orchestrated_executor.toml"
PROVIDER_RE = re.compile(r"^[A-Za-z0-9_-]+$")
HEADER_RE = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*(?:#.*)?$")
ASSIGNMENT_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)\s*=")
BUILTIN_PROVIDERS = {"openai", "ollama", "lmstudio", "amazon-bedrock"}
EXECUTOR_ROLE_NAME = "executor"
EXECUTOR_ROLE_DESCRIPTION = (
    "Optional model-only route for delegated work after Codex has independently "
    "decided a compatible subagent is useful. Selecting this role does not "
    "authorize delegation."
)
ADVISOR_ROLE_NAME = "advisor"
ADVISOR_ROLE_DESCRIPTION = (
    "Optional model-only route for a read-only second opinion on the root "
    "orchestrator's plan and proposed executor tasks. It reports only to the "
    "root orchestrator and never directs or coordinates executors. Selecting "
    "this role does not force review or delegation."
)


class ConfigurationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Persist model-only executor and optional advisor routes. The selected "
            "session model remains the root orchestrator, and this tool does not "
            "change Codex orchestration policy."
        )
    )
    parser.add_argument("--scope", choices=("project", "personal"), default="project")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root.")
    parser.add_argument("--codex-home", type=Path, help="Override CODEX_HOME for personal scope.")
    parser.add_argument("--executor-model", required=True)
    parser.add_argument(
        "--executor-effort",
        default="auto",
        help="Exact host-supported effort, or auto (default).",
    )
    parser.add_argument("--executor-provider")
    advisor = parser.add_mutually_exclusive_group()
    advisor.add_argument(
        "--advisor-model",
        help="Optional exact advisor model ID.",
    )
    advisor.add_argument(
        "--remove-advisor",
        action="store_true",
        help="Remove only a previously managed advisor route and model layer.",
    )
    parser.add_argument(
        "--advisor-effort",
        help="Exact host-supported advisor effort, or auto (default when selected).",
    )
    parser.add_argument("--advisor-provider")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument(
        "--confirm-unlisted-models",
        action="store_true",
        help="Accept exact IDs confirmed by another active-host capability source.",
    )
    parser.add_argument(
        "--migrate-legacy",
        action="store_true",
        help=(
            "Back up and remove every exact-marker agent file managed by the "
            "previous skill version, including custom filenames. Existing "
            "max_threads/max_depth settings are deliberately left unchanged because "
            "prior ownership cannot be established safely."
        ),
    )
    parser.add_argument("--apply", action="store_true", help="Write files; default is dry-run.")
    return parser.parse_args()


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def parse_toml(text: str, label: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"{label} is not valid TOML: {exc}") from exc


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def has_exact_marker(text: str, markers: set[str]) -> bool:
    return any(line.strip() in markers for line in text.splitlines())


def section_for_lines(lines: list[str]) -> list[str | None]:
    current: str | None = None
    sections: list[str | None] = []
    for line in lines:
        match = HEADER_RE.match(line)
        if match:
            current = match.group(1).strip()
        sections.append(current)
    return sections


def update_assignments(
    lines: list[str], section: str | None, updates: dict[str, str | None]
) -> tuple[list[str], set[str]]:
    sections = section_for_lines(lines)
    seen: set[str] = set()
    output: list[str] = []
    for index, line in enumerate(lines):
        match = ASSIGNMENT_RE.match(line)
        key = match.group(2) if match and sections[index] == section else None
        if key not in updates:
            output.append(line)
            continue
        if key in seen:
            continue
        seen.add(key)
        replacement = updates[key]
        if replacement is not None:
            indent = match.group(1) if match else ""
            output.append(f"{indent}{key} = {replacement}\n")
    return output, seen


def ensure_managed_marker(lines: list[str]) -> list[str]:
    # Exact marker comments are ownership metadata, so normalize one to line 1.
    # A lookalike embedded in a value or a longer comment is deliberately ignored.
    output = [line for line in lines if line.strip() not in KNOWN_MANAGED_MARKERS]
    return [f"{MANAGED_MARKER}\n", *output]


def insert_top_level(lines: list[str], assignments: list[str]) -> list[str]:
    if not assignments:
        return lines
    first_header = next((i for i, line in enumerate(lines) if HEADER_RE.match(line)), len(lines))
    prefix = [] if first_header == 0 or not lines[first_header - 1].strip() else ["\n"]
    block = [*prefix, *(f"{line}\n" for line in assignments)]
    if first_header < len(lines):
        block.append("\n")
    return [*lines[:first_header], *block, *lines[first_header:]]


def ensure_role_section(
    lines: list[str], role_name: str, description: str, config_file: str
) -> list[str]:
    section = f"agents.{role_name}"
    sections = section_for_lines(lines)
    updates = {
        "description": toml_string(description),
        "config_file": toml_string(config_file),
    }
    if section in sections:
        updated, seen = update_assignments(lines, section, updates)
        missing = [
            f"{key} = {value}\n"
            for key, value in updates.items()
            if key not in seen
        ]
        if not missing:
            return updated
        updated_sections = section_for_lines(updated)
        last_index = max(i for i, value in enumerate(updated_sections) if value == section)
        insert_at = last_index + 1
        while insert_at > 0 and not updated[insert_at - 1].strip():
            insert_at -= 1
        return [*updated[:insert_at], *missing, *updated[insert_at:]]

    output = list(lines)
    if output and output[-1].strip():
        output.append("\n")
    output.extend(
        [
            f"[{section}]\n",
            f"description = {toml_string(description)}\n",
            f"config_file = {toml_string(config_file)}\n",
        ]
    )
    return output


def remove_role_section(lines: list[str], role_name: str) -> list[str]:
    """Remove one exact role table after its ownership has been established."""
    section = f"agents.{role_name}"
    start: int | None = None
    end: int | None = None
    for index, line in enumerate(lines):
        match = HEADER_RE.match(line)
        if not match:
            continue
        current = match.group(1).strip()
        if start is None and current == section:
            start = index
            continue
        if start is not None:
            end = index
            break
    if start is None:
        return lines
    if end is None:
        end = len(lines)
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    return [*lines[:start], *lines[end:]]


def ensure_safe_managed_path(path: Path, base: Path) -> None:
    """Refuse symlinks at the managed base or any component beneath it."""
    try:
        relative = path.relative_to(base)
    except ValueError as exc:
        raise ConfigurationError(
            f"Managed path {path} is outside the Codex configuration directory {base}."
        ) from exc
    current = base
    for component in (Path(), *relative.parents[::-1], relative):
        candidate = current if component == Path() else base / component
        if candidate.is_symlink():
            raise ConfigurationError(
                f"Refusing to read or replace symlinked managed path component {candidate}."
            )


def validate_managed_role_layer(text: str, path: Path) -> bool:
    """Return ownership and reject managed layers containing non-routing settings."""
    if not text:
        return False
    if not has_exact_marker(text, ROLE_LAYER_MARKERS):
        return False
    parsed = parse_toml(text, f"Existing model layer {path}")
    extra = set(parsed) - ROLE_LAYER_KEYS
    if extra:
        listed = ", ".join(sorted(extra))
        raise ConfigurationError(
            f"Managed model layer {path} contains settings beyond model routing: "
            f"{listed}. Refusing to replace or remove it; review those settings explicitly."
        )
    if "model" not in parsed:
        raise ConfigurationError(
            f"Managed model layer {path} is missing its model setting. Refusing to "
            "replace or remove incomplete managed output."
        )
    non_strings = sorted(
        key for key, value in parsed.items() if not isinstance(value, str)
    )
    if non_strings:
        listed = ", ".join(non_strings)
        raise ConfigurationError(
            f"Managed model layer {path} has non-string routing values: {listed}. "
            "Refusing to replace or remove it."
        )
    return True


def discover_legacy_agent_files(
    agents_dir: Path, excluded: set[Path]
) -> list[tuple[Path, str]]:
    """Find every regular TOML file carrying the old skill's exact marker."""
    if not agents_dir.exists():
        return []
    if agents_dir.is_symlink():
        raise ConfigurationError(
            f"Refusing to inspect symlinked Codex agents directory {agents_dir}."
        )
    found: list[tuple[Path, str]] = []
    for candidate in sorted(agents_dir.glob("*.toml")):
        if candidate in excluded or candidate.is_symlink() or not candidate.is_file():
            continue
        content = read_text(candidate)
        if has_exact_marker(content, {LEGACY_MARKER}):
            found.append((candidate, content))
    return found


def config_file_resolves_to(config_path: Path, value: Any, target: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = config_path.parent / candidate
    return candidate.resolve() == target.resolve()


def validate_role_conflicts(
    parsed_config: dict[str, Any],
    config_path: Path,
    role_name: str,
    role_layer_path: Path,
    managed_role_provenance: bool,
    *,
    removing: bool = False,
) -> None:
    agents = parsed_config.get("agents") or {}
    if not isinstance(agents, dict):
        raise ConfigurationError("Existing agents configuration is not a TOML table")
    existing = agents.get(role_name)
    if existing is None:
        return
    if (
        not managed_role_provenance
        or not isinstance(existing, dict)
        or not config_file_resolves_to(
            config_path, existing.get("config_file"), role_layer_path
        )
    ):
        raise ConfigurationError(
            f"Existing [agents.{role_name}] configuration does not have this "
            "skill's complete config-and-layer provenance. Refusing to replace it; "
            "merge or rename it explicitly first."
        )
    if removing and set(existing) != {"description", "config_file"}:
        raise ConfigurationError(
            f"Existing [agents.{role_name}] contains settings beyond this skill's "
            "managed description and config_file. Refusing to remove it; review and "
            "merge those settings explicitly first."
        )


def update_main_config(
    original: str,
    config_path: Path,
    executor_layer_path: Path,
    executor_managed_provenance: bool = False,
    *,
    advisor_layer_path: Path | None = None,
    advisor_action: str = "preserve",
    advisor_managed_provenance: bool = False,
) -> str:
    if advisor_action not in {"preserve", "configure", "remove"}:
        raise ConfigurationError(f"Unknown advisor action: {advisor_action!r}")
    if advisor_action != "preserve" and advisor_layer_path is None:
        raise ConfigurationError("Advisor layer path is required for this advisor action")
    parsed = parse_toml(original, "Existing Codex config")
    validate_role_conflicts(
        parsed,
        config_path,
        EXECUTOR_ROLE_NAME,
        executor_layer_path,
        executor_managed_provenance,
    )
    if advisor_action != "preserve":
        validate_role_conflicts(
            parsed,
            config_path,
            ADVISOR_ROLE_NAME,
            advisor_layer_path,
            advisor_managed_provenance,
            removing=advisor_action == "remove",
        )
    lines = original.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines = ensure_managed_marker(lines)

    if advisor_action == "remove":
        lines = remove_role_section(lines, ADVISOR_ROLE_NAME)
    lines = ensure_role_section(
        lines,
        EXECUTOR_ROLE_NAME,
        EXECUTOR_ROLE_DESCRIPTION,
        EXECUTOR_LAYER_RELATIVE_PATH,
    )
    if advisor_action == "configure":
        lines = ensure_role_section(
            lines,
            ADVISOR_ROLE_NAME,
            ADVISOR_ROLE_DESCRIPTION,
            ADVISOR_LAYER_RELATIVE_PATH,
        )
    result = "".join(lines)
    if result and not result.endswith("\n"):
        result += "\n"
    parse_toml(result, "Generated Codex config")
    return result


def build_role_layer(
    model: str,
    effort: str,
    provider: str | None,
    *,
    label: str = "role",
    original: str = "",
) -> str:
    comments = [
        line
        for line in original.splitlines()
        if line.strip().startswith("#")
        and line.strip() not in KNOWN_MANAGED_MARKERS
    ]
    fields = [MANAGED_MARKER, *comments, f"model = {toml_string(model)}"]
    if effort != "auto":
        fields.append(f"model_reasoning_effort = {toml_string(effort)}")
    if provider:
        fields.append(f"model_provider = {toml_string(provider)}")
    fields.append("")
    result = "\n".join(fields)
    parse_toml(result, f"Generated {label} model layer")
    return result


def load_catalog(codex_bin: str, provider: str | None) -> dict[str, dict[str, Any]]:
    executable = shutil.which(codex_bin) if "/" not in codex_bin else codex_bin
    if not executable:
        raise ConfigurationError(f"Codex executable not found: {codex_bin}")
    command = [executable, "debug", "models"]
    if provider:
        command.extend(["-c", f'model_provider="{provider}"'])
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ConfigurationError(f"Could not run Codex model inspection: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise ConfigurationError(f"Could not inspect models for provider {provider or 'active'}: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Codex returned invalid model JSON: {exc}") from exc
    return {
        model["slug"]: model
        for model in payload.get("models", [])
        if isinstance(model, dict) and isinstance(model.get("slug"), str)
    }


def validate_model(
    label: str,
    model_id: str,
    effort: str,
    catalog: dict[str, dict[str, Any]],
    confirm_unlisted: bool,
) -> str | None:
    if not model_id.strip() or model_id != model_id.strip():
        raise ConfigurationError(f"{label} model ID must be a non-empty exact ID")
    if not effort.strip() or effort != effort.strip():
        raise ConfigurationError(f"{label} effort must be a non-empty exact value")
    if model_id not in catalog:
        if not confirm_unlisted:
            raise ConfigurationError(
                f"{label} model {model_id!r} is not in the inspected CLI catalog. "
                "Confirm it through the active host or provider, then rerun with "
                "--confirm-unlisted-models."
            )
        return f"{label} model {model_id!r} was accepted from an external capability check."
    if effort == "auto":
        return None
    supported = {
        item.get("effort")
        for item in catalog[model_id].get("supported_reasoning_levels", [])
        if isinstance(item, dict)
    }
    if effort not in supported:
        if not confirm_unlisted:
            listed = ", ".join(sorted(value for value in supported if value)) or "none"
            raise ConfigurationError(
                f"{label} effort {effort!r} is not listed for {model_id!r}; "
                f"catalog efforts: {listed}."
            )
        return f"{label} effort {effort!r} was accepted from an external capability check."
    return None


def resolve_role_effort(
    requested_effort: str,
    label: str,
    model_id: str,
    catalog: dict[str, dict[str, Any]],
) -> str:
    if requested_effort != "auto":
        return requested_effort
    model = catalog.get(model_id) or {}
    default = model.get("default_reasoning_level")
    if isinstance(default, str) and default:
        return default
    raise ConfigurationError(
        f"Cannot determine the default reasoning effort for {label.lower()} model "
        f"{model_id!r}. Choose an explicit {label.lower()} effort so it cannot "
        "silently inherit an incompatible root override."
    )


def validate_provider(provider: str | None, config: dict[str, Any]) -> None:
    if not provider:
        return
    if not PROVIDER_RE.fullmatch(provider):
        raise ConfigurationError(f"Invalid provider ID: {provider!r}")
    configured = config.get("model_providers") or {}
    if provider not in BUILTIN_PROVIDERS and provider not in configured:
        raise ConfigurationError(
            f"Provider {provider!r} is neither built in nor defined in the personal Codex config. "
            "Configure and authenticate it separately before assigning models to it."
        )


def unified_diff(path: Path, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )


def stage_text(path: Path, content: str, mode: int = 0o600) -> Path:
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            staged = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(staged, mode)
        return staged
    except OSError:
        if staged is not None:
            staged.unlink(missing_ok=True)
        raise


def apply_changes_transactionally(changes: list[tuple[Path, str, str]]) -> None:
    """Stage every change, commit atomically per file, and roll back on failure.

    An empty new value represents deletion. Multi-file atomicity is emulated with
    same-directory staged replacements plus pre-staged rollback copies.
    """
    active = [change for change in changes if change[1] != change[2]]
    if not active:
        return
    paths = [path for path, _, _ in active]
    if len(paths) != len(set(paths)):
        raise ConfigurationError("Transactional change set contains a duplicate path")

    prepared: list[dict[str, Any]] = []
    staged_paths: set[Path] = set()
    created_dirs: set[Path] = set()
    attempted: list[dict[str, Any]] = []
    try:
        # Complete every safety/concurrency check before creating staging files.
        for path, expected, new in active:
            if path.is_symlink():
                raise ConfigurationError(
                    f"Refusing to transactionally replace symlinked path {path}."
                )
            existed = path.exists()
            current = read_text(path)
            if current != expected:
                raise ConfigurationError(
                    f"Configuration changed while preparing the update: {path}. "
                    "No files were modified; preview again."
                )
            prepared.append(
                {
                    "path": path,
                    "old": expected,
                    "new": new,
                    "existed": existed,
                    "mode": (path.stat().st_mode & 0o777) if existed else 0o600,
                    "staged_new": None,
                    "staged_old": None,
                }
            )

        for item in prepared:
            parent = item["path"].parent
            missing: list[Path] = []
            cursor = parent
            while not cursor.exists():
                missing.append(cursor)
                cursor = cursor.parent
            parent.mkdir(parents=True, exist_ok=True)
            created_dirs.update(missing)
            if item["new"]:
                item["staged_new"] = stage_text(
                    item["path"], item["new"], item["mode"]
                )
                staged_paths.add(item["staged_new"])
            if item["existed"]:
                item["staged_old"] = stage_text(
                    item["path"], item["old"], item["mode"]
                )
                staged_paths.add(item["staged_old"])

        for item in prepared:
            attempted.append(item)
            if item["new"]:
                os.replace(item["staged_new"], item["path"])
                staged_paths.discard(item["staged_new"])
                item["staged_new"] = None
            else:
                item["path"].unlink()
    except (ConfigurationError, OSError) as exc:
        rollback_errors: list[str] = []
        for item in reversed(attempted):
            try:
                if item["existed"]:
                    os.replace(item["staged_old"], item["path"])
                    staged_paths.discard(item["staged_old"])
                    item["staged_old"] = None
                elif item["path"].exists() or item["path"].is_symlink():
                    item["path"].unlink()
            except OSError as rollback_exc:
                rollback_errors.append(f"{item['path']}: {rollback_exc}")
        for staged in list(staged_paths):
            staged.unlink(missing_ok=True)
        for directory in sorted(created_dirs, key=lambda value: len(value.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        if rollback_errors:
            detail = "; ".join(rollback_errors)
            raise ConfigurationError(
                f"Transactional apply failed ({exc}) and rollback was incomplete: {detail}"
            ) from exc
        raise ConfigurationError(
            f"Transactional apply failed; committed files were restored: {exc}"
        ) from exc
    finally:
        for staged in list(staged_paths):
            staged.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    try:
        if args.remove_advisor and (args.advisor_effort or args.advisor_provider):
            raise ConfigurationError(
                "--remove-advisor cannot be combined with advisor effort or provider flags."
            )
        if not args.advisor_model and (args.advisor_effort or args.advisor_provider):
            raise ConfigurationError(
                "--advisor-effort and --advisor-provider require --advisor-model."
            )
        advisor_action = (
            "configure"
            if args.advisor_model
            else "remove"
            if args.remove_advisor
            else "preserve"
        )
        advisor_effort = args.advisor_effort or "auto"

        if args.scope == "project" and (
            args.executor_provider or args.advisor_provider
        ):
            raise ConfigurationError(
                "Project-scoped Codex config cannot select machine-local model providers. "
                "Omit provider flags when the active provider exposes the selected models, or use "
                "explicitly approved personal scope."
            )

        if args.scope == "project":
            base = args.root.expanduser().resolve() / ".codex"
        else:
            base = (
                args.codex_home
                or (Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else None)
                or Path.home() / ".codex"
            ).expanduser().absolute()
        config_path = base / "config.toml"
        executor_layer_path = base / EXECUTOR_LAYER_RELATIVE_PATH
        advisor_layer_path = base / ADVISOR_LAYER_RELATIVE_PATH
        agents_dir = base / "agents"

        for managed_path in (
            config_path,
            executor_layer_path,
            advisor_layer_path,
        ):
            ensure_safe_managed_path(managed_path, base)

        old_config = read_text(config_path)
        parsed_config = parse_toml(old_config, "Existing Codex config")
        if args.scope == "personal":
            validate_provider(args.executor_provider, parsed_config)
            validate_provider(args.advisor_provider, parsed_config)

        old_executor_layer = read_text(executor_layer_path)
        managed_executor_layer = validate_managed_role_layer(
            old_executor_layer, executor_layer_path
        )
        if old_executor_layer and not managed_executor_layer:
            raise ConfigurationError(
                f"Refusing to replace unmanaged model layer {executor_layer_path}. "
                "Move it or merge the model settings explicitly first."
            )

        old_advisor_layer = read_text(advisor_layer_path)
        managed_advisor_layer = False
        if advisor_action in {"configure", "remove"}:
            managed_advisor_layer = validate_managed_role_layer(
                old_advisor_layer, advisor_layer_path
            )
        if (
            advisor_action in {"configure", "remove"}
            and old_advisor_layer
            and not managed_advisor_layer
        ):
            verb = "replace" if advisor_action == "configure" else "remove"
            raise ConfigurationError(
                f"Refusing to {verb} unmanaged model layer {advisor_layer_path}. "
                "Move it or merge the model settings explicitly first."
            )

        config_has_managed_provenance = bool(
            old_config and has_exact_marker(old_config, KNOWN_MANAGED_MARKERS)
        )
        executor_managed_provenance = (
            managed_executor_layer and config_has_managed_provenance
        )
        advisor_managed_provenance = (
            managed_advisor_layer and config_has_managed_provenance
        )

        legacy_agents = discover_legacy_agent_files(
            agents_dir,
            {executor_layer_path, advisor_layer_path},
        )
        if legacy_agents and not args.migrate_legacy:
            names = ", ".join(path.name for path, _ in legacy_agents)
            raise ConfigurationError(
                "Legacy configure-agent-team output was detected in: "
                f"{names}. Preview again with --migrate-legacy to back up and remove "
                "every exact-marker legacy agent file. "
                "Review any agents.max_threads/max_depth values separately; this tool "
                "cannot prove whether they predated the old skill."
            )

        catalogs: dict[str | None, dict[str, dict[str, Any]]] = {}
        warnings: list[str] = []
        model_seats = [
            ("Executor", args.executor_model, args.executor_effort, args.executor_provider)
        ]
        if args.advisor_model:
            model_seats.append(
                ("Advisor", args.advisor_model, advisor_effort, args.advisor_provider)
            )
        for label, model_id, effort, provider in model_seats:
            if provider not in catalogs:
                try:
                    catalogs[provider] = load_catalog(args.codex_bin, provider)
                except ConfigurationError:
                    if not args.confirm_unlisted_models:
                        raise
                    catalogs[provider] = {}
                    warnings.append(
                        f"Could not inspect provider {provider or 'active'}; "
                        "exact IDs require external confirmation."
                    )
            warning = validate_model(
                label,
                model_id,
                effort,
                catalogs[provider],
                args.confirm_unlisted_models,
            )
            if warning:
                warnings.append(warning)

        resolved_executor_effort = resolve_role_effort(
            args.executor_effort,
            "Executor",
            args.executor_model,
            catalogs[args.executor_provider],
        )
        if args.executor_effort == "auto":
            warnings.append(
                f"Executor effort 'auto' resolved to catalog default {resolved_executor_effort!r}."
            )
        resolved_advisor_effort: str | None = None
        if args.advisor_model:
            resolved_advisor_effort = resolve_role_effort(
                advisor_effort,
                "Advisor",
                args.advisor_model,
                catalogs[args.advisor_provider],
            )
            if advisor_effort == "auto":
                warnings.append(
                    "Advisor effort 'auto' resolved to catalog default "
                    f"{resolved_advisor_effort!r}."
                )

        if any(
            key in parsed_config
            for key in ("model", "model_reasoning_effort", "model_provider")
        ):
            warnings.append(
                "Existing root model settings were preserved unchanged. This version never "
                "configures the root; the model selected for the Codex session is the orchestrator."
            )

        new_config = update_main_config(
            old_config,
            config_path,
            executor_layer_path,
            executor_managed_provenance,
            advisor_layer_path=advisor_layer_path,
            advisor_action=advisor_action,
            advisor_managed_provenance=advisor_managed_provenance,
        )
        new_executor_layer = build_role_layer(
            args.executor_model,
            resolved_executor_effort,
            args.executor_provider,
            label="executor",
            original=old_executor_layer,
        )

        changes = [
            (executor_layer_path, old_executor_layer, new_executor_layer),
        ]
        if advisor_action == "configure":
            new_advisor_layer = build_role_layer(
                args.advisor_model,
                resolved_advisor_effort,
                args.advisor_provider,
                label="advisor",
                original=old_advisor_layer,
            )
            changes.append((advisor_layer_path, old_advisor_layer, new_advisor_layer))
        changes.append((config_path, old_config, new_config))
        if advisor_action == "remove":
            changes.append((advisor_layer_path, old_advisor_layer, ""))
        elif advisor_action == "preserve" and (
            (parsed_config.get("agents") or {}).get(ADVISOR_ROLE_NAME) is not None
        ):
            warnings.append(
                "Existing advisor route was left unchanged; use --remove-advisor to remove "
                "a route previously managed by this skill."
            )
        if legacy_agents and args.migrate_legacy:
            changes.extend((path, content, "") for path, content in legacy_agents)
            names = ", ".join(path.name for path, _ in legacy_agents)
            warnings.append(
                f"Legacy agent files will be backed up and removed: {names}. Existing "
                "agents.max_threads/max_depth values were not changed; review them manually."
            )

        for path, old, new in changes:
            diff = unified_diff(path, old, new)
            if diff:
                print(diff, end="" if diff.endswith("\n") else "\n")
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)

        if not args.apply:
            print("Dry run only. Re-run with --apply after reviewing the diff.")
            return 0

        backup_sources: dict[Path, str] = {}
        if args.scope == "personal":
            for path, old, new in changes:
                if old != new and path.exists():
                    backup_sources[path] = old
        for path, content in legacy_agents:
            if args.migrate_legacy:
                backup_sources[path] = content

        backup_changes: list[tuple[Path, str, str]] = []
        backup_destinations: list[Path] = []
        for source, content in backup_sources.items():
            backup = source.with_name(source.name + ".bak.codex-orchestration")
            ensure_safe_managed_path(backup, base)
            backup_changes.append((backup, read_text(backup), content))
            backup_destinations.append(backup)

        apply_changes_transactionally([*backup_changes, *changes])

        for backup in backup_destinations:
            print(f"Backed up configuration file to {backup}")
        for path, old, new in changes:
            if old != new:
                print(f"Updated {path}" if new else f"Removed {path}")

        parse_toml(read_text(config_path), "Written Codex config")
        parse_toml(read_text(executor_layer_path), "Written executor model layer")
        if advisor_action == "configure":
            parse_toml(read_text(advisor_layer_path), "Written advisor model layer")
        print(
            "Configuration is valid TOML. Start a new Codex task or session to load "
            "the persistent settings. The current session model remains the root "
            "orchestrator. Executor and advisor routes work only when the native spawn "
            "surface exposes role selection and uses a non-full-history fork; native "
            "Codex planning, Goals, and delegation remain unchanged."
        )
        return 0
    except (ConfigurationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
