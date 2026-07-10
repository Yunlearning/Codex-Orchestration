# Codex-Orchestration

Configure a high-capability Codex model as the orchestrator and a faster or lower-cost model as the executor for bounded parallel subagent work.

The included `configure-agent-team` skill asks for both model IDs, reasoning effort, worker count, configuration scope, and whether to run work after setup. It validates the active runtime, previews every configuration change, and applies a guarded plan-delegate-synthesize-verify workflow.

## Install

```bash
git clone https://github.com/Cjbuilds/Codex-Orchestration.git
cp -R Codex-Orchestration/configure-agent-team "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Start a new Codex task after installation so the skill is discovered.

## Use

Invoke the skill in Codex:

```text
Use $configure-agent-team to configure my orchestrator and executor models.
```

Codex will ask for any missing values using this compact format:

```text
orchestrator=<model-id>@<effort>, executor=<model-id>@<effort>, workers=<1-5>, scope=<project|personal>, run_now=<yes|no>
```

Example:

```text
orchestrator=gpt-5.6-sol@xhigh, executor=gpt-5.6-luna@xhigh, workers=4, scope=project, run_now=no
```

Project scope creates or updates:

```text
.codex/config.toml
.codex/agents/orchestrated_executor.toml
```

New model settings take effect in a new Codex task or session.

## Roles

The orchestrator owns user intent, the work graph, delegation, integration, conflict resolution, end-state verification, and the final response.

Executors receive bounded contracts with explicit ownership, constraints, deliverables, verification, and stop conditions. They complete their slice and return evidence to the orchestrator instead of expanding scope.

The configured worker count is a maximum, not a quota. Simple or tightly coupled work stays with one agent; moderate independent work can use two executors; broad research, review, testing, or disjoint implementation can use three to five.

## Guardrails

- Discover and validate exact model IDs instead of guessing slugs.
- Keep provider credentials and machine-local provider definitions out of project files.
- Preview changes before applying them.
- Preserve existing TOML and refuse silent overwrites of unmanaged agent files.
- Keep parallel writes disjoint and delegation depth at one by default.
- Verify the integrated end state rather than trusting worker summaries.
- Treat cost, speed, and usage-limit improvements as workload-dependent, not guaranteed multipliers.

## Requirements

- A current Codex release with custom-agent and subagent support.
- Python 3.11 or newer for the configuration scripts.
- Provider access for every selected model. OpenAI authentication does not automatically provide access to Anthropic models.

## Design Sources

- [OpenAI Codex subagents and custom agents](https://developers.openai.com/codex/subagents)
- [OpenAI Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

## License

MIT
