# Codex-Orchestration

Choose a high-capability model for the root Codex task and a faster or lower-cost model for compatible execution subagents—without replacing Codex's own orchestration.

Codex still owns the plan, Goals, the decision to delegate, agent count, role selection, coordination, integration, and verification. This skill adds only a model preference at the native model-selection seam.

> Exact two-model routing depends on the current Codex surface. Live routing requires native model controls; optional persistent routing requires native role controls. Both require a non-full-history fork. When the required controls are unavailable, this skill fails closed instead of claiming the executor model ran.

## How It Works

```text
                    Tag $configure-agent-team
                               |
                               v
              Choose ORCHESTRATOR + EXECUTOR models
                               |
                               v
             Select root model with Codex's native picker
                               |
                               v
                     User prompt or Goal
                               |
                               v
             +----------------------------------+
             | Root Codex                       |
             | ORCHESTRATOR MODEL               |
             | plans / owns Goal / integrates   |
             +----------------------------------+
                               |
                    Native Codex decides:
                     "Delegate this work?"
                               |
                    +----------+----------+
                    |                     |
                   NO                    YES
                    |                     |
             Work directly       Native spawn + role +
                                 context/fork decision
                                           |
                                +----------+----------+
                                |                     |
                    Model override exposed?       Hidden controls or
                    Non-full-history fork?        full-history fork?
                                |                     |
                               YES                   YES
                                |                     |
                         EXECUTOR MODEL        Root model inherited;
                         runs the slice        limitation disclosed
                                |                     |
                                +----------+----------+
                                           |
                                           v
                          Orchestrator integrates and verifies
                                           |
                                           v
                                      Final result
```

There is no second planner, supervisor loop, custom Goal system, forced fan-out, worker-count setting, or replacement orchestration protocol.

## The Two Roles

The orchestrator is the root Codex model. It preserves the user's intent, uses Codex's native planning and Goal behavior, decides whether delegation is worthwhile, synthesizes results, resolves conflicts, and owns the final verification.

The executor is a model preference applied only to a subagent Codex already decided to spawn. It performs the assigned slice and returns its work through Codex's existing subagent channel; this skill adds no new handoff format. It does not gain authority to plan the whole task, create more workers, or change the orchestration policy merely because a cheaper model was selected.

This follows the useful part of the orchestrator-workers pattern without rebuilding it. Anthropic describes a central model dynamically decomposing work, delegating it, and synthesizing results; it also recommends simple, composable designs and warns that multi-agent systems add cost and work poorly when tasks share lots of context or dependencies. Codex already supplies the orchestration machinery, so this project leaves it alone.

## Install

```bash
git clone https://github.com/Cjbuilds/Codex-Orchestration.git
cp -R Codex-Orchestration/configure-agent-team "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Start a new Codex task once so the installed skill is discovered.

## Use in the Current Task

Invoke the skill:

```text
Use $configure-agent-team to set my orchestrator and executor models.
```

Codex asks only for missing model settings:

```text
orchestrator=<model-id>@<effort-or-auto>, executor=<model-id>@<effort-or-auto>
```

Example using IDs that must still be validated on your own host:

```text
orchestrator=gpt-5.5@high, executor=gpt-5.4-mini@medium
```

Then:

1. Select the orchestrator through Codex's native model picker or `/model` command if it is not already active.
2. Continue working normally or start a Goal in that same task.
3. Codex decides whether subagents are useful. The skill never asks for a worker count and never forces a spawn.
4. When the native spawn surface supports it, Codex adds the executor model to a compatible spawn call.

No project file is required for this live, task-local mode.

## Native Capability Matrix

| Native Codex capability | Result |
| --- | --- |
| `spawn_agent` exposes `model` and uses a non-full-history fork | The selected executor model can run that child. |
| `spawn_agent` exposes `agent_type` and uses a non-full-history fork | The optional persistent `executor` role can be selected. |
| `fork_turns="all"` | The child inherits the orchestrator model; role/model overrides do not apply. |
| Model and role fields are hidden | Exact executor routing is unavailable on that surface. |

The skill checks the schema exposed in the active task. It does not assume that Desktop, CLI, cloud, and embedded Codex surfaces have identical controls.

## Optional Persistence

Use persistence only when you want startup defaults for future tasks. The included script previews its diff before writing:

```bash
python3 configure-agent-team/scripts/configure_agent_team.py \
  --scope project \
  --root /path/to/workspace \
  --orchestrator-model <model-id> \
  --orchestrator-effort <effort-or-auto> \
  --executor-model <model-id> \
  --executor-effort <effort-or-auto>
```

After reviewing the preview, repeat the command with `--apply`.

Project scope creates or updates:

```text
.codex/config.toml
.codex/agents/executor-model.toml
```

The root config sets the startup model and registers one additive `[agents.executor]` role. It does not override Codex's built-in `default`, `worker`, or `explorer` roles. The executor layer contains only model, reasoning-effort, and optional provider settings.

Persistent settings require a new task to load. The custom role still requires native `agent_type` visibility and a non-full-history fork, so persistence is not a bypass for a surface that hides those controls. An existing task-scoped Goal does not move to the new task.

## What This Never Changes

- Plan mode or Codex's planning behavior.
- Goal creation, continuation, lifecycle, or budget.
- Whether Codex delegates or how many agents it spawns.
- Built-in role descriptions or role-selection guidance.
- Concurrency, nesting depth, steering, waiting, retries, or synthesis.
- Sandbox, approvals, tools, hooks, skills, or verification policy.

## Models and Providers

Model names are discovered at runtime; the repository does not hard-code an allowlist. A display name such as “Extra High” is normalized to `xhigh`, but the exact model ID and supported effort must come from the execution host or official provider documentation.

Direct live spawn overrides use the task's active provider. OpenAI authentication does not automatically provide Anthropic access. Cross-provider persistent roles require an already configured and authenticated compatible provider, plus visible native role selection. Credentials and provider definitions are never written into project files.

Do not treat “5x limits” or “3x cheaper” as a guarantee. A lower-cost executor can reduce the price of suitable delegated work, while extra agents can also increase total token use.

## Legacy Migration

The first release wrote an opinionated `orchestrated_executor.toml` and changed `agents.max_threads`/`agents.max_depth`. The revised script detects its managed legacy file. `--migrate-legacy` backs up and removes only that file.

It deliberately does not remove `max_threads` or `max_depth`: the old release did not store their previous values, so automatic restoration would risk deleting user-owned settings. Review those keys manually.

## Validate

```bash
python3 -m unittest discover -s tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py configure-agent-team
```

## Design Sources

- [OpenAI Codex subagents and custom agents](https://developers.openai.com/codex/subagents)
- [OpenAI Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [OpenAI Codex native role-layer implementation](https://github.com/openai/codex/blob/main/codex-rs/core/src/agent/role.rs)
- [OpenAI Codex MultiAgentV2 spawn implementation](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)
- [OpenAI: Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)
- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

## License

MIT
