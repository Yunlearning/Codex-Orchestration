# Orchestration Protocol

Use this protocol after configuring the team. Keep the orchestrator responsible for intent, decomposition, synthesis, and the verified end state. Keep executors focused on bounded work.

## Contents

- Role contract
- Fit gate
- Plan the work graph
- Scale effort
- Write executor contracts
- Dispatch and coordinate
- Synthesize results
- Verify the end state
- Recover from failures
- Avoid common failure modes

## Role contract

### Orchestrator

Own the user relationship and the final outcome.

- Clarify the objective, constraints, success criteria, risk, and budget.
- Inspect enough of the environment to create a real dependency graph.
- Decide whether delegation is useful.
- Partition work into independent scopes with explicit ownership.
- Choose worker count and dispatch order.
- Keep high-value context in the main thread and move noisy exploration away.
- Monitor drift, duplication, blockers, and conflicting edits.
- Integrate worker artifacts and resolve disagreements.
- Run end-to-end verification.
- Produce the final user-facing response.

Do not spend the strongest model on mechanical repetition that a bounded executor can handle. Do not delegate away judgment that depends on the entire user conversation.

### Executor

Own one bounded deliverable.

- Follow the assigned objective and stop conditions.
- Read only the context needed for the slice.
- Stay inside exclusive file or investigation ownership.
- Use the most direct relevant tools.
- Verify the assigned output.
- Report evidence, uncertainty, and blockers precisely.
- Return a structured handoff to the orchestrator.

Do not expand scope, re-plan the entire project, create more agents, overwrite unrelated work, or present the final user answer.

## Fit gate

Use no subagents when the task is small, sequential, highly coupled, dominated by one edit path, or cheaper to complete directly.

Use subagents when at least two lanes can proceed independently and one or more of these conditions hold:

- The task requires broad codebase or document exploration.
- Several authoritative sources or systems must be checked.
- Tests, analysis, or reviews can run independently.
- Implementation can be divided into disjoint file ownership.
- Multiple independent perspectives materially improve confidence.
- Intermediate output would pollute the main context.

Prefer read-heavy delegation first. Parallel write-heavy work only when file ownership is disjoint and interfaces are already stable.

## Plan the work graph

Write a concise, inspectable plan. Do not expose private chain-of-thought. Include:

1. The target end state.
2. Known constraints and non-goals.
3. Independent work nodes.
4. Dependencies between nodes.
5. Exclusive file or artifact owners.
6. Verification nodes.
7. Stop or escalation conditions.

Keep orchestration work local when it touches shared interfaces, global configuration, final merging, or user decisions. Delegate leaves of the dependency graph, not the central coordination spine.

## Scale effort

Use the smallest effective team:

| Task shape | Executors | Pattern |
| --- | ---: | --- |
| Simple fact or edit | 0 | Orchestrator completes directly |
| Moderate comparison or two independent checks | 2 | Parallel lanes |
| Broad research, review, or disjoint feature slices | 3-5 | Parallel lanes plus synthesis |
| Repeated row-shaped batch | Runtime batch tool | Bounded concurrency and structured output |
| Tightly coupled multi-file change | 0-2 | Serialize shared interfaces |

Cap concurrency by the user's requested count and the runtime's available slots. Account for other active agents. Keep nesting depth at one.

Use the capable orchestrator for ambiguous decomposition, cross-cutting design, conflict resolution, and final verification. Use faster or cheaper executors for well-specified searches, local edits, tests, transformations, and checks. Upgrade a worker or reduce fan-out when a slice itself requires frontier-level reasoning.

## Write executor contracts

Send a self-contained contract to each executor:

```text
Objective:
<one measurable outcome>

Context:
<relevant facts, paths, decisions, and dependencies>

Ownership:
<exclusive files/artifacts, or read-only investigation boundary>

Constraints:
<must preserve, must avoid, tools/sources, budget>

Deliverable:
<specific artifact or finding format>

Verification:
<checks the executor must run>

Stop conditions:
<when to return blocked or partial instead of guessing>
```

Make contracts mutually exclusive and collectively sufficient. Give each worker a distinct question or output. Avoid vague prompts such as “research this” or “help with the feature.”

Require this handoff shape:

```text
Status: complete | partial | blocked
Scope: <what was handled>
Files/artifacts: <changed or inspected>
Result: <concise outcome>
Verification: <commands, checks, evidence>
Risks: <remaining uncertainty or none>
Follow-up: <exact orchestrator action or none>
```

## Dispatch and coordinate

Dispatch every currently independent worker in one batch when the runtime supports it. Do not insert narration, file edits, or waits between launches that should start together.

Continue only non-conflicting orchestrator work while executors run. Useful local work includes preparing integration checks, inspecting shared interfaces, or resolving user-level decisions. Do not modify files owned by active executors.

Track for each executor:

- Role and objective.
- Owned scope.
- Status.
- Expected artifacts.
- Dependencies.
- Retry count.

Steer a running executor when new information invalidates its contract. Interrupt it when it duplicates another lane, crosses ownership, or can no longer produce useful output.

## Synthesize results

Wait for every required dependency, not necessarily every optional lane. Inspect shared-filesystem artifacts directly instead of relying only on summaries.

For each handoff:

1. Check that the worker stayed inside scope.
2. Confirm the claimed files or evidence exist.
3. Compare findings against other workers and source-of-truth constraints.
4. Resolve conflicts using evidence, not majority vote alone.
5. Integrate the smallest coherent result.

Do not concatenate worker answers. Rebuild a single answer or implementation around the original objective.

## Verify the end state

Run final checks from the orchestrator after integration. Workers verify their slices; the orchestrator verifies the system.

Use the strongest available end-state evidence:

- Tests, type checks, linters, builds, and targeted reproductions for code.
- Source traceability and claim coverage for research.
- Schema validation and sample parsing for structured data.
- Rendered output and visual inspection for documents or UI.
- Diff review for scope control and unintended changes.

Report what passed, what was not run, and residual risk. Human review remains appropriate for high-impact changes even when tests pass.

## Recover from failures

Classify the failure before acting:

- Bad contract: add missing context, narrow scope, or clarify output, then retry once.
- Tool or transient failure: retry once if state is safe.
- Model capability mismatch: assign a stronger model or finish locally.
- Overlapping writes: stop affected workers, inspect the worktree, and serialize recovery.
- Partial artifact: inspect it before deciding whether the missing work is trivial.
- Unavailable model or role: disclose the runtime limitation and use an explicitly approved fallback.

Never loop identical retries. Never hide a failed executor behind a confident synthesis.

## Avoid common failure modes

- Do not spawn agents merely because capacity exists.
- Do not assign every worker the same broad prompt.
- Do not let workers edit the same files concurrently.
- Do not pass the entire main-thread history when a focused contract is enough.
- Do not accept worker claims without inspecting evidence.
- Do not let the orchestrator become a passive message router.
- Do not raise recursive depth casually.
- Do not guarantee cost savings; measure quality, latency, and token use on real tasks.
- Do not optimize only the workers. Evaluate the whole interaction pattern and final state.

## Research basis

Anthropic describes orchestrator-workers as a central model dynamically decomposing tasks, delegating them, and synthesizing the results. Its production research guidance emphasizes detailed worker objectives, boundaries, output formats, complexity-scaled fan-out, parallel dispatch, observability, and end-state evaluation. OpenAI's Codex guidance similarly recommends parallel agents for read-heavy independent work, cautions against write conflicts, and assigns orchestration and consolidated verification to the main thread.

- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [OpenAI: Codex subagents](https://developers.openai.com/codex/subagents)
