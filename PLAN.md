# flow-forge: plan

A local AI agent that turns a plain-English description of an integration workflow into a
tested recipe, plus a benchmark that measures whether the recipes are actually correct: the
right side effects, exactly once, nothing for events that should be ignored, and correct
behaviour when apps fail or events are replayed. Everything runs on one machine: Ollama for
the model, standard-library mock apps on localhost.

Most workflow tools show that a recipe ran. This project measures whether it did the right
thing.

## Architecture

```
task YAML ──► mock apps (CRM, billing, chat, tickets, mail) on localhost
    │              ▲            │ events feed (triggers)
    ▼              │ actions    ▼
 description ──► agent (Ollama) ── tools ──► guard ──► recipe ──► engine
 + app catalog                                                      │
                     harness: replay events → engine → app state → compare with expected effects
```

- **Mock apps:** Python standard library HTTP servers with seeded synthetic data. Each app has
  an events feed (for triggers), read/search actions and write actions, API-key auth, rate
  limits, and optional failure injection (5xx, timeouts) for retry tests.
- **App catalog:** generated docs listing each app's triggers, actions, inputs and outputs. It
  is all the agent gets about the apps.
- **Recipe format:** declarative YAML: one trigger (app + event + optional filter), then steps:
  `action` (app + action + input mappings), `lookup` (search another app), `if` (condition),
  `for_each` (over a list). Mappings use a small, safe expression language
  (`{{trigger.deal.amount}}`, `{{steps.find_customer.id}}`, a few functions). No arbitrary code.
- **Engine:** validates and runs a recipe against the apps: polls triggers, evaluates
  conditions and mappings, retries transient failures with backoff, passes an idempotency key
  per (event, step) so replays do not create duplicates. Every call is logged.
- **Harness:** for each task, generate an event stream from a seed, run the recipe, then
  compare the apps' final state and the action log with the expected effects (computed by a
  hand-written reference recipe).

## Agent variants

1. `reference`: hand-written recipes, no AI. Proves the harness; target 100%.
2. `prompt`: one attempt from the description and the catalog.
3. `probe`: may read sample events and call read-only actions first.
4. `graph`: fixed plan: probe → write → validate → dry run on sample events → fix, up to N rounds.
5. `graph+clarify`: for ambiguous tasks, may ask a scripted user up to K questions first.

## Tasks and metrics

- About 16 development tasks plus 5 held-out ones, from simple (one trigger, one action) to
  multi-step (lookups, conditions, loops, several apps). Held-out tasks are fixed in their own
  commit before any agent is written. Some tasks are deliberately ambiguous.
- Metrics:
  - task success (all expected effects, nothing else)
  - effect precision and recall, matched by app, object and fields
  - duplicates after replaying the event stream
  - correctness under injected failures (retries, no partial duplicates)
  - filtered events correctly ignored
  - recipe validity rate, rounds, clarifying questions asked, tokens and time
  - calls blocked by the guard

## Milestones (each split into small committed steps)

1. Mock apps, catalog docs, recipe format, expression language, engine, task format, harness
   and the `reference` recipes.
2. Guard, agent tools, LLM client, and the `prompt` and `probe` agents.
3. The `graph` agent with validate → dry run → fix.
4. Failure injection, replay/idempotency checks, ambiguous tasks and `graph+clarify`.
5. Real runs over three seeds, README with results, CI, v0.1.0 release (ask before pushing).

## Stack

Python 3.12, pyyaml, pytest. Ollama with `qwen2.5-coder:3b` (optional `qwen2.5-coder:7b`).
No web framework.
