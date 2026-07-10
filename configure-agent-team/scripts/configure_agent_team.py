#!/usr/bin/env python3
"""Preview or apply a Codex orchestrator/executor configuration."""

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


MANAGED_MARKER = "# Managed by configure-agent-team."
ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
PROVIDER_RE = re.compile(r"^[A-Za-z0-9_-]+$")
HEADER_RE = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*(?:#.*)?$")
ASSIGNMENT_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)\s*=")
DOTTED_AGENTS_RE = re.compile(r"^(\s*)agents\.([A-Za-z0-9_-]+)\s*=")
EFFORTS = ("auto", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
BUILTIN_PROVIDERS = {"openai", "ollama", "lmstudio", "amazon-bedrock"}


class ConfigurationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure a Codex orchestrator model and custom executor agent."
    )
    parser.add_argument("--scope", choices=("project", "personal"), default="project")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root.")
    parser.add_argument("--codex-home", type=Path, help="Override CODEX_HOME for personal scope.")
    parser.add_argument("--orchestrator-model", required=True)
    parser.add_argument("--orchestrator-effort", choices=EFFORTS, default="auto")
    parser.add_argument("--orchestrator-provider")
    parser.add_argument("--executor-model", required=True)
    parser.add_argument("--executor-effort", choices=EFFORTS, default="auto")
    parser.add_argument("--executor-provider")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--executor-role", default="orchestrated_executor")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument(
        "--confirm-unlisted-models",
        action="store_true",
        help="Accept exact IDs confirmed by another active-host capability source.",
    )
    parser.add_argument(
        "--force-agent-file",
        action="store_true",
        help="Replace an existing executor file not managed by this skill.",
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


def insert_top_level(lines: list[str], assignments: list[str]) -> list[str]:
    if not assignments:
        return lines
    first_header = next((i for i, line in enumerate(lines) if HEADER_RE.match(line)), len(lines))
    marker = [] if any(line.strip() == MANAGED_MARKER for line in lines) else [f"{MANAGED_MARKER}\n"]
    block = [*marker, *(f"{line}\n" for line in assignments), "\n"]
    return [*lines[:first_header], *block, *lines[first_header:]]


def ensure_agents_table(lines: list[str], workers: int) -> list[str]:
    sections = section_for_lines(lines)
    dotted_agent_keys = {
        match.group(2)
        for index, line in enumerate(lines)
        if sections[index] is None and (match := DOTTED_AGENTS_RE.match(line))
    }
    if dotted_agent_keys:
        seen: set[str] = set()
        updated: list[str] = []
        replacements = {"max_threads": str(workers), "max_depth": "1"}
        for index, line in enumerate(lines):
            match = DOTTED_AGENTS_RE.match(line) if sections[index] is None else None
            key = match.group(2) if match else None
            if key not in replacements:
                updated.append(line)
                continue
            if key in seen:
                continue
            seen.add(key)
            indent = match.group(1) if match else ""
            updated.append(f"{indent}agents.{key} = {replacements[key]}\n")
        missing = [
            f"agents.{key} = {value}"
            for key, value in replacements.items()
            if key not in seen
        ]
        return insert_top_level(updated, missing)

    if "agents" in sections:
        updated, seen = update_assignments(
            lines,
            "agents",
            {"max_threads": str(workers), "max_depth": "1"},
        )
        missing = []
        if "max_threads" not in seen:
            missing.append(f"max_threads = {workers}\n")
        if "max_depth" not in seen:
            missing.append("max_depth = 1\n")
        if not missing:
            return updated
        updated_sections = section_for_lines(updated)
        last_agent_index = max(i for i, value in enumerate(updated_sections) if value == "agents")
        insert_at = last_agent_index + 1
        while insert_at > 0 and not updated[insert_at - 1].strip():
            insert_at -= 1
        return [*updated[:insert_at], *missing, *updated[insert_at:]]

    insert_at = next(
        (
            i
            for i, line in enumerate(lines)
            if (match := HEADER_RE.match(line)) and match.group(1).strip().startswith("agents.")
        ),
        len(lines),
    )
    prefix = [] if insert_at == 0 or (insert_at > 0 and not lines[insert_at - 1].strip()) else ["\n"]
    block = [*prefix, "[agents]\n", f"max_threads = {workers}\n", "max_depth = 1\n", "\n"]
    return [*lines[:insert_at], *block, *lines[insert_at:]]


def update_main_config(
    original: str,
    orchestrator_model: str,
    orchestrator_effort: str,
    orchestrator_provider: str | None,
    workers: int,
) -> str:
    parse_toml(original, "Existing Codex config")
    lines = original.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
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
    lines = ensure_agents_table(lines, workers)
    result = "".join(lines)
    if result and not result.endswith("\n"):
        result += "\n"
    parse_toml(result, "Generated Codex config")
    return result


def executor_instructions() -> str:
    return (
        "Act as a bounded execution worker for a parent orchestrator.\n\n"
        "Stay inside the assigned objective, file ownership, constraints, and stop "
        "conditions. Do not broaden scope or delegate to more agents. Inspect before "
        "editing, preserve unrelated work, and avoid overlapping writes. Use tools "
        "directly, verify the assigned result, and report blockers instead of guessing.\n\n"
        "Return a concise handoff containing status, files changed or evidence inspected, "
        "result, verification performed, residual risks, and any exact follow-up the "
        "orchestrator must handle. Do not present the final user-facing answer; the "
        "orchestrator owns synthesis and final verification."
    )


def build_agent_file(
    role: str,
    model: str,
    effort: str,
    provider: str | None,
) -> str:
    fields = [
        MANAGED_MARKER,
        f"name = {toml_string(role)}",
        "description = \"Bounded execution worker for implementation, tests, research, and verification.\"",
        'nickname_candidates = ["Forge", "Relay", "Vector", "Scout", "Delta"]',
        f"model = {toml_string(model)}",
    ]
    if effort != "auto":
        fields.append(f"model_reasoning_effort = {toml_string(effort)}")
    if provider:
        fields.append(f"model_provider = {toml_string(provider)}")
    fields.extend(
        [
            f"developer_instructions = {toml_string(executor_instructions())}",
            "",
        ]
    )
    result = "\n".join(fields)
    parse_toml(result, "Generated executor agent")
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
            raise ConfigurationError(
                f"{label} effort {effort!r} is not listed for {model_id!r}; "
                f"catalog efforts: {', '.join(sorted(value for value in supported if value)) or 'none'}."
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
        "Choose an explicit executor effort so it does not inherit the orchestrator's override."
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
    os.replace(temp_name, path)


def main() -> int:
    args = parse_args()
    try:
        if not 1 <= args.workers <= 5:
            raise ConfigurationError("--workers must be between 1 and 5")
        if not ROLE_RE.fullmatch(args.executor_role):
            raise ConfigurationError(
                "--executor-role must start with a lowercase letter and contain only "
                "lowercase letters, digits, and underscores"
            )
        if args.scope == "project" and (args.orchestrator_provider or args.executor_provider):
            raise ConfigurationError(
                "Project-scoped Codex config cannot select machine-local model providers. "
                "Omit provider flags when the active provider already exposes both models, "
                "or use explicitly approved personal scope."
            )

        if args.scope == "project":
            base = args.root.expanduser().resolve()
            config_path = base / ".codex" / "config.toml"
            agent_path = base / ".codex" / "agents" / f"{args.executor_role}.toml"
        else:
            base = (
                args.codex_home
                or (Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else None)
                or Path.home() / ".codex"
            ).expanduser().resolve()
            config_path = base / "config.toml"
            agent_path = base / "agents" / f"{args.executor_role}.toml"

        old_config = read_text(config_path)
        parsed_config = parse_toml(old_config, "Existing Codex config")
        if args.scope == "personal":
            validate_provider(args.orchestrator_provider, parsed_config)
            validate_provider(args.executor_provider, parsed_config)

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
            args.orchestrator_model,
            args.orchestrator_effort,
            args.orchestrator_provider,
            args.workers,
        )
        old_agent = read_text(agent_path)
        managed_agent = bool(
            old_agent and old_agent.splitlines()[0].strip() == MANAGED_MARKER
        )
        if old_agent and not managed_agent and not args.force_agent_file:
            raise ConfigurationError(
                f"Refusing to replace unmanaged agent file {agent_path}. "
                "Review it and rerun with --force-agent-file only with explicit approval."
            )
        new_agent = build_agent_file(
            args.executor_role,
            args.executor_model,
            resolved_executor_effort,
            args.executor_provider,
        )

        changes = [
            (config_path, old_config, new_config),
            (agent_path, old_agent, new_agent),
        ]
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
        if old_agent and not managed_agent and old_agent != new_agent:
            backup = agent_path.with_name(agent_path.name + ".bak.configure-agent-team")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(agent_path, backup)
            print(f"Backed up unmanaged agent file to {backup}")
        for path, old, new in changes:
            if old != new:
                atomic_write(path, new)
                print(f"Updated {path}")
        parse_toml(read_text(config_path), "Written Codex config")
        parse_toml(read_text(agent_path), "Written executor agent")
        print("Configuration is valid TOML. Start a new Codex task or session to load it.")
        return 0
    except (ConfigurationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
