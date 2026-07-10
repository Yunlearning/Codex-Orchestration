# Codex-Orchestration

Let your best model lead. Let a second model challenge the plan. Let a faster model handle the bulk of the coding.

**In an executor-heavy task, this setup can preserve about 65% of your top-tier model's included allowance.** It is an estimate, not a promise of 65% fewer raw tokens or a 65% lower bill.

## What This Skill Does

Codex already has an orchestrator: the model you selected for the current task. You do not need to configure another one.

Codex-Orchestration adds two model roles around it:

- **Executor:** the model that handles clear, well-scoped work.
- **Advisor:** an optional second opinion that checks the plan before execution.

Codex still decides how much planning the task needs and whether delegating work would help. The skill adds model choice without replacing the way Codex works.

## Install Once

```bash
codex plugin marketplace add Cjbuilds/Codex-Orchestration
codex plugin add codex-orchestration@codex-orchestration
```

Start a new Codex task after installation.

## Use It

In the Codex app, choose your main model as usual. Then call the skill:

```text
/codex-orchestration executor: GPT-5.6 Luna extra high, advisor: Anthropic Fable 5 extra high
```

Do not want a second opinion? Say so:

```text
/codex-orchestration executor: GPT-5.6 Luna extra high, advisor: none
```

You can also call it with no settings:

```text
/codex-orchestration
```

Codex asks one short question:

```text
executor=<model>@<effort-or-auto>, advisor=<model>@<effort-or-auto>|none
```

If you already supplied the executor, Codex asks only about the advisor. “Extra High” becomes `xhigh`. Codex checks model names against the active host instead of guessing.

In CLI or IDE, open `/skills` and select **Codex Orchestration**. The full plugin skill name is:

```text
$codex-orchestration:codex-orchestration executor: GPT-5.6 Luna extra high, advisor: Anthropic Fable 5 extra high
```

A standalone copy uses `$codex-orchestration` without the plugin prefix.

> Updating from an older release? Stop passing `orchestrator:`. The model you selected for the task already fills that role.

## The Whole Flow

```text
        Start a Codex task with the model you trust most
                              |
                              v
             That model leads the task (ORCHESTRATOR)
                  understands | plans | decides
                              |
                    Is this task complex?
                         /          \
                       no            yes
                       |              |
                Codex handles it   Did you add an advisor?
                                      /       \
                                    no         yes
                                    |           |
                                    |    ADVISOR checks plan
                                    |       /          \
                                    |  needs work    looks solid
                                    |      |              |
                                    |  Orchestrator       |
                                    |  fixes the gaps     |
                                    |  and may recheck    |
                                    +---------+-----------+
                                              |
                                  Would delegating help?
                                      /             \
                                    no               yes
                                    |                 |
                         Orchestrator works     EXECUTOR handles
                                                assigned work
                                                      |
                                                      v
                                  Orchestrator reviews and verifies
```

No second planner. No forced swarm. No new Goal system. Codex keeps making the same decisions it normally makes.

## The Three Roles

### Orchestrator: the lead

This is the model you already chose for the task. Think of it as the tech lead: it understands the goal, makes the plan, decides whether help is useful, and reviews the finished work.

You never choose a second orchestrator inside this skill.

### Advisor: the second pair of eyes

The advisor is optional. It reads the plan and proposed executor tasks before coding starts. Its job is to spot missing requirements, shallow tasks, risky assumptions, weak checks, or work that should not run in parallel.

The advisor speaks only to the orchestrator. It never edits code, assigns work, talks to executors, or accepts their output.

A model from another family or provider can be useful here because it may notice different problems. Use the advisor for meaningful or risky plans, not every tiny task.

The advisor starts its answer with one clear signal:

```text
PLAN_APPROVED   The plan is ready to execute.
PLAN_REVISE    The orchestrator should fix material gaps first.
ADVISOR_BLOCKED The advisor is missing context or cannot run.
```

If the plan needs work, the orchestrator fixes it and may ask for one more check. The advisor cannot create an endless review loop or overrule the orchestrator.

### Executor: the builder

The executor receives a clear piece of work with the right context, constraints, files, success criteria, and test command. It builds that piece and returns the result to the orchestrator.

The executor does not control the whole project. Codex decides whether an executor is useful and how many executors the task needs. The orchestrator reviews every result before accepting it.

## Why This Can Save Your Limits

Your strongest model is most valuable when judgment matters: understanding the request, making the plan, handling tradeoffs, and reviewing the result.

Most of the volume often comes later, while writing code, tests, docs, and repetitive changes. A capable executor can handle that work once the plan is clear.

OpenAI's published Plus limits, checked July 9, 2026, show why this split can help:

| Model | Local messages / 5h | Best fit |
| --- | ---: | --- |
| GPT-5.6 Sol | 15–90 | Deep judgment and planning |
| GPT-5.6 Luna | 50–280 | Fast, high-volume execution |

Luna provides roughly **3.1–3.3× more message capacity** in that window.

<details>
<summary>Where the “about 65%” example comes from</summary>

Using a conservative Luna-to-Sol allowance ratio of `0.32`, imagine 5% of the work stays with the top-tier model and 95% is eligible for Luna:

```text
relative allowance use = 0.05 + (0.95 × 0.32) = 0.354
illustrative saving     = 1 - 0.354            = 64.6%
```

If planning and advising rise to 10%, the same example becomes about 61.2%:

```text
relative allowance use = 0.10 + (0.90 × 0.32) = 0.388
illustrative saving     = 1 - 0.388            = 61.2%
```

This may preserve included five-hour and applicable weekly allowance. Task complexity, context, reasoning, tools, retrieval, caching, and extra weekly limits all affect real usage.

</details>

Keep the claim honest:

- It is not a guarantee of 65% fewer raw tokens. Extra agents may increase total tokens.
- It is not a guarantee of 65% lower API cost or credits.
- It is not a fixed 5× increase in limits.
- An advisor adds overhead and may use a different provider's allowance.
- Codex never creates agents just to hit a savings target.

## Will It Work on Every Codex Surface?

Not yet. Codex must expose child-model controls before a skill can send an advisor or executor to a different model.

Some Codex surfaces expose those controls; some Desktop hosts currently hide them. The skill checks the surface in front of it and tells you the truth.

If routing is unavailable, it will not pretend Luna or Fable ran. It tells you which role is unavailable and what kind of task or role support is missing.

| What Codex exposes | What happens |
| --- | --- |
| Child `model` and `reasoning_effort` | The skill can request a task-local model. |
| A loaded custom role plus `agent_type` | The skill can request a saved advisor or executor role. |
| Fresh or partial child context | A different child model can run. |
| Full task history only | The child inherits the orchestrator model. |
| No model or role controls | Exact routing is unavailable on that surface. |

Full-history children inherit the orchestrator model. The skill uses a self-contained handoff only when the work can safely run with the relevant context instead of the entire chat.

## Models and Providers

Sol, Luna, Fable, and Opus are examples, not a fixed list. Use any executor or advisor model available to your Codex host.

An Anthropic or other-provider model needs an existing, authenticated Codex-compatible provider. OpenAI access does not automatically include Anthropic access.

The plugin never asks you to paste an API key into chat and never writes credentials.

## Optional Saved Roles

Normal use is task-local. You do not need to edit a config file.

If you want Codex to load executor and advisor roles in future tasks, preview the included configurator:

```bash
python3 plugins/codex-orchestration/skills/codex-orchestration/scripts/configure_orchestration.py \
  --scope project \
  --root /path/to/workspace \
  --executor-model <exact-model-id> \
  --executor-effort <effort-or-auto> \
  --advisor-model <exact-model-id> \
  --advisor-effort <effort-or-auto>
```

Review the preview, then run the same command with `--apply`.

Leave out the advisor flags for executor-only setup. Use `--remove-advisor` to remove a role previously managed by this plugin.

The configurator never changes the root model. It adds only model-routing layers for `executor` and optional `advisor`, leaves built-in Codex roles alone, and refuses to overwrite user-owned role files.

Saved roles load in a new task. They still need Codex to expose role selection and use fresh or partial child context.

## Update

```bash
codex plugin marketplace upgrade codex-orchestration
codex plugin add codex-orchestration@codex-orchestration
```

Start a new task after updating.

## Validate

```bash
python3 -m unittest discover -s tests -v
```

The release checks also run Codex's skill and plugin validators plus an isolated marketplace install.

## Design Sources

- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills)
- [OpenAI: Build plugins](https://learn.chatgpt.com/docs/build-plugins)
- [OpenAI Codex pricing and usage limits](https://developers.openai.com/codex/pricing)
- [OpenAI Codex subagents and custom agents](https://developers.openai.com/codex/subagents)
- [OpenAI Codex role-layer implementation](https://github.com/openai/codex/blob/main/codex-rs/core/src/agent/role.rs)
- [OpenAI Codex MultiAgentV2 spawn implementation](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)
- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

## License

MIT
