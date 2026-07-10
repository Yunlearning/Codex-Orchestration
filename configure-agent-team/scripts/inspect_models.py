#!/usr/bin/env python3
"""Print a compact view of the model catalog exposed by Codex."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from typing import Any


PROVIDER_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the model catalog exposed by the installed Codex CLI."
    )
    parser.add_argument("--provider", help="Optional configured Codex provider ID.")
    parser.add_argument("--bundled", action="store_true", help="Skip catalog refresh.")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--codex-bin", default="codex", help="Codex executable name or path.")
    return parser.parse_args()


def load_catalog(codex_bin: str, provider: str | None, bundled: bool) -> dict[str, Any]:
    executable = shutil.which(codex_bin) if "/" not in codex_bin else codex_bin
    if not executable:
        raise RuntimeError(f"Codex executable not found: {codex_bin}")

    command = [executable, "debug", "models"]
    if bundled:
        command.append("--bundled")
    if provider:
        if not PROVIDER_RE.fullmatch(provider):
            raise RuntimeError(f"Invalid provider ID: {provider!r}")
        command.extend(["-c", f'model_provider="{provider}"'])

    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise RuntimeError(f"Could not run Codex model inspection: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RuntimeError(f"Codex model inspection failed: {detail}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Codex returned invalid model JSON: {exc}") from exc
    if not isinstance(payload.get("models"), list):
        raise RuntimeError("Codex model response does not contain a models array")
    return payload


def compact_model(model: dict[str, Any]) -> dict[str, Any]:
    levels = model.get("supported_reasoning_levels") or []
    efforts = [item.get("effort") for item in levels if isinstance(item, dict)]
    return {
        "id": model.get("slug"),
        "display_name": model.get("display_name"),
        "description": model.get("description"),
        "default_effort": model.get("default_reasoning_level"),
        "supported_efforts": [effort for effort in efforts if effort],
        "visibility": model.get("visibility"),
    }


def print_table(models: list[dict[str, Any]]) -> None:
    rows = []
    for model in models:
        rows.append(
            (
                str(model.get("id") or ""),
                ",".join(model.get("supported_efforts") or []) or "default only",
                str(model.get("description") or ""),
            )
        )
    id_width = max([len("MODEL ID"), *(len(row[0]) for row in rows)])
    effort_width = max([len("EFFORTS"), *(len(row[1]) for row in rows)])
    print(f"{'MODEL ID':<{id_width}}  {'EFFORTS':<{effort_width}}  DESCRIPTION")
    for model_id, efforts, description in rows:
        print(f"{model_id:<{id_width}}  {efforts:<{effort_width}}  {description}")


def main() -> int:
    args = parse_args()
    try:
        payload = load_catalog(args.codex_bin, args.provider, args.bundled)
        models = [compact_model(model) for model in payload["models"]]
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"provider": args.provider, "models": models}, indent=2))
    else:
        print_table(models)
        print(
            "\nNote: the active desktop or remote host may expose newer models than this CLI catalog.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
