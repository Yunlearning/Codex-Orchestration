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


MANAGED_MARKER = "# Managed by configure-agent-team. Model routing only."
LEGACY_MARKER = "# Managed by configure-agent-team."
ROLE_LAYER_RELATIVE_PATH = "agents/executor-model.toml"
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


class ConfigurationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Persist a root Codex model and add an optional model-only executor role. "
            "This does not change Codex orchestration policy."
        )
    )
    parser.add_argument("--scope", choices=("project", "personal"), default="project")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root.")
    parser.add_argument("--codex-home", type=Path, help="Override CODEX_HOME for personal scope.")
    parser.add_argument("--orchestrator-model", required=True)
    parser.add_argument(
        "--orchestrator-effort",
        default="auto",
        help="Exact host-supported effort, or auto (default).",
    )
    parser.add_argument("--orchestrator-provider")
    parser.add_argument("--executor-model", required=True)
    parser.add_argument(
        "--executor-effort",
        default="auto",
        help="Exact host-supported effort, or auto (default).",
    )
    parser.add_argument("--executor-provider")
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
            "Back up and remove the previous skill version's managed "
            "orchestrated_executor agent file. Existing max_threads/max_depth "
            "settings are deliberately left unchanged because prior ownership "
            "cannot be established safely."
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
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.strip() in {MANAGED_MARKER, LEGACY_MARKER}:
            if not replaced:
                output.append(f"{MANAGED_MARKER}\n")
                replaced = True
            continue
        output.append(line)
    if replaced:
        return output
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
    role_layer_path: Path,
    managed_role_provenance: bool,
) -> None:
    agents = parsed_config.get("agents") or {}
    if not isinstance(agents, dict):
        raise ConfigurationError("Existing agents configuration is not a TOML table")
    existing = agents.get(EXECUTOR_ROLE_NAME)
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
            f"Existing [agents.{EXECUTOR_ROLE_NAME}] configuration does not have this "
            "skill's complete config-and-layer provenance. Refusing to replace it; "
            "merge or rename it explicitly first."
        )


def update_main_config(
    original: str,
    config_path: Path,
    role_layer_path: Path,
    orchestrator_model: str,
    orchestrator_effort: str,
    orchestrator_provider: str | None,
    managed_role_provenance: bool = False,
) -> str:
    parsed = parse_toml(original, "Existing Codex config")
    validate_role_conflicts(
        parsed,
        config_path,
        role_layer_path,
        managed_role_provenance,
    )
    lines = original.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines = ensure_managed_marker(lines)

    top_updates = {
        "model": toml_string(orchestrator_model),
        "model_reasoning_effort": None
        if orchestrator_effort == "auto"
        else toml_string(orchestrator_effort),
    }
    if orchestrator_provider:
        top_updates["model_provider"] = toml_string(orchestrator_provider)
    lines, seen = update_assignments(lines, None, top_updates)
    missing = [
        f"{key} = {value}"
        for key, value in top_updates.items()
        if value is not None and key not in seen
    ]
    lines = insert_top_level(lines, missing)
    lines = ensure_role_section(
        lines,
        EXECUTOR_ROLE_NAME,
        EXECUTOR_ROLE_DESCRIPTION,
        ROLE_LAYER_RELATIVE_PATH,
    )
    result = "".join(lines)
    if result and not result.endswith("\n"):
        result += "\n"
    parse_toml(result, "Generated Codex config")
    return result


def build_role_layer(model: str, effort: str, provider: str | None) -> str:
    fields = [MANAGED_MARKER, f"model = {toml_string(model)}"]
    if effort != "auto":
        fields.append(f"model_reasoning_effort = {toml_string(effort)}")
    if provider:
        fields.append(f"model_provider = {toml_string(provider)}")
    fields.append("")
    result = "\n".join(fields)
    parse_toml(result, "Generated executor model layer")
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


def resolve_executor_effort(
    requested_effort: str,
    orchestrator_effort: str,
    model_id: str,
    catalog: dict[str, dict[str, Any]],
) -> str:
    if requested_effort != "auto":
        return requested_effort
    model = catalog.get(model_id) or {}
    default = model.get("default_reasoning_level")
    if isinstance(default, str) and default:
        return default
    if orchestrator_effort == "auto":
        return "auto"
    raise ConfigurationError(
        f"Cannot determine the default reasoning effort for executor model {model_id!r}. "
        "Choose an explicit executor effort so it does not inherit the root override."
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


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temp_name = handle.name
    try:
        os.replace(temp_name, path)
    except OSError:
        Path(temp_name).unlink(missing_ok=True)
        raise


def main() -> int:
    args = parse_args()
    try:
        if args.scope == "project" and (args.orchestrator_provider or args.executor_provider):
            raise ConfigurationError(
                "Project-scoped Codex config cannot select machine-local model providers. "
                "Omit provider flags when the active provider exposes both models, or use "
                "explicitly approved personal scope."
            )

        if args.scope == "project":
            base = args.root.expanduser().resolve() / ".codex"
        else:
            base = (
                args.codex_home
                or (Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else None)
                or Path.home() / ".codex"
            ).expanduser().resolve()
        config_path = base / "config.toml"
        role_layer_path = base / ROLE_LAYER_RELATIVE_PATH
        legacy_agent_path = base / "agents" / LEGACY_AGENT_FILENAME

        old_config = read_text(config_path)
        parsed_config = parse_toml(old_config, "Existing Codex config")
        if args.scope == "personal":
            validate_provider(args.orchestrator_provider, parsed_config)
            validate_provider(args.executor_provider, parsed_config)

        old_role_layer = read_text(role_layer_path)
        managed_role_layer = bool(
            old_role_layer
            and old_role_layer.splitlines()[0].strip() == MANAGED_MARKER
        )
        config_has_managed_provenance = bool(
            old_config and old_config.splitlines()[0].strip() == MANAGED_MARKER
        )
        managed_role_provenance = (
            managed_role_layer and config_has_managed_provenance
        )
        if old_role_layer and not managed_role_layer:
            raise ConfigurationError(
                f"Refusing to replace unmanaged model layer {role_layer_path}. "
                "Move it or merge the model settings explicitly first."
            )

        old_legacy_agent = read_text(legacy_agent_path)
        managed_legacy = bool(
            old_legacy_agent
            and old_legacy_agent.splitlines()[0].strip() == LEGACY_MARKER
        )
        if managed_legacy and not args.migrate_legacy:
            raise ConfigurationError(
                "Legacy configure-agent-team output was detected. Preview again with "
                "--migrate-legacy to back up and remove orchestrated_executor.toml. "
                "Review any agents.max_threads/max_depth values separately; this tool "
                "cannot prove whether they predated the old skill."
            )

        catalogs: dict[str | None, dict[str, dict[str, Any]]] = {}
        warnings: list[str] = []
        for label, model_id, effort, provider in (
            (
                "Orchestrator",
                args.orchestrator_model,
                args.orchestrator_effort,
                args.orchestrator_provider,
            ),
            ("Executor", args.executor_model, args.executor_effort, args.executor_provider),
        ):
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

        resolved_executor_effort = resolve_executor_effort(
            args.executor_effort,
            args.orchestrator_effort,
            args.executor_model,
            catalogs[args.executor_provider],
        )
        if args.executor_effort == "auto" and resolved_executor_effort != "auto":
            warnings.append(
                f"Executor effort 'auto' resolved to catalog default {resolved_executor_effort!r}."
            )

        new_config = update_main_config(
            old_config,
            config_path,
            role_layer_path,
            args.orchestrator_model,
            args.orchestrator_effort,
            args.orchestrator_provider,
            managed_role_provenance,
        )
        new_role_layer = build_role_layer(
            args.executor_model,
            resolved_executor_effort,
            args.executor_provider,
        )

        changes = [
            (role_layer_path, old_role_layer, new_role_layer),
            (config_path, old_config, new_config),
        ]
        if managed_legacy and args.migrate_legacy:
            changes.append((legacy_agent_path, old_legacy_agent, ""))
            warnings.append(
                "The legacy custom executor will be backed up and removed. Existing "
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

        if args.scope == "personal" and config_path.exists() and old_config != new_config:
            backup = config_path.with_name(config_path.name + ".bak.configure-agent-team")
            shutil.copy2(config_path, backup)
            print(f"Backed up personal config to {backup}")
        if managed_legacy and args.migrate_legacy and legacy_agent_path.exists():
            backup = legacy_agent_path.with_name(
                legacy_agent_path.name + ".bak.configure-agent-team"
            )
            shutil.copy2(legacy_agent_path, backup)
            print(f"Backed up legacy agent file to {backup}")

        for path, old, new in changes:
            if old == new:
                continue
            if new:
                atomic_write(path, new)
                print(f"Updated {path}")
            elif path.exists():
                path.unlink()
                print(f"Removed {path}")

        parse_toml(read_text(config_path), "Written Codex config")
        parse_toml(read_text(role_layer_path), "Written executor model layer")
        print(
            "Configuration is valid TOML. Start a new Codex task or session to load "
            "the persistent settings. The executor role works only when the native "
            "spawn surface exposes role selection and uses a non-full-history fork; "
            "native Codex planning, Goals, and delegation remain unchanged."
        )
        return 0
    except (ConfigurationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
