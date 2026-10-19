# Progress

## Done

- Plan written (PLAN.md). Local repo created with personal git identity.
- M1.1 Project skeleton: pyproject, src layout, scripts/setup.py (.venv), MIT license,
  README stub, smoke tests. 2 tests passing.
- M1.2 Mock apps: `apps.py` (App base with collections, events feed, declarative
  ActionSpec/TriggerSpec, input validation with clear 400/404/409 errors, idempotency keys,
  action log) + crm, billing, chat, tickets; `server.py` AppServer (POST
  /<app>/actions/<name>, GET /<app>/events?after=, X-Api-Key, Idempotency-Key, request log).
  6 tests passing.
- M1.3 `expr.py`: own tokenizer/parser (no eval): dotted paths and [i], literals, lists,
  comparisons, and/or/not with short-circuit, in / not in, is [not] null, filters (upper,
  lower, trim, default, round, number, integer, string, length); render() for templates
  (whole-value refs keep type) and condition(). Unknown paths fail loudly unless defaulted
  or null-tested. 33 tests passing.
- M1.4 `recipe.py`: YAML recipe (trigger app/event/filter; steps with action+inputs,
  optional if, for_each with nested steps) and validate() against app specs: unknown
  app/event/action/input, missing required inputs, literal types and enums, duplicate ids,
  references to undefined/later steps, item/index outside loops, expression syntax
  (expr.check). 51 tests passing.
- M1.5 `engine.py`: HTTP Client (X-Api-Key, Idempotency-Key, retries 429/5xx/connection
  errors with backoff or Retry-After) and run(): polls the trigger app from a cursor,
  ignores other event types, filter, if/skip (null output), for_each with item/index and
  per-iteration keys, key = <recipe>:<event>:<step path>; failures recorded per event and
  the run continues. Fixed app id collisions with hand-inserted ids (found by the replay
  test). 58 tests passing.
- M1.6 `task.py`: task YAML (description, apps, seed, world sizes, event stream specs with
  stage/priority/currency mixes, ambiguous flag, scripted clarifications) and build_world():
  deterministic contacts, billing customers (some with differently-cased emails), channels,
  tickets, and deal/contact/ticket/invoice event streams with increasing timestamps. 66
  tests passing.
- M1.7 `harness.py`: canonical effects (ids replaced by natural keys; text case/space-
  insensitive; amounts to the cent) as a multiset; evaluate(task, recipe, reference) ->
  Report (valid + validation errors, success, precision, recall, duplicates on full replay,
  events ok/filtered/failed, examples of missing/unexpected effects, event errors, API
  calls). 72 tests passing.
- M1.8 16 dev tasks in tasks/dev/ (chat alerts, filters on
  stage/amount/currency/tags/previous stage/title, lookups with create-if-missing, invoices,
  deal notes, tickets, for_each, if-routing, multi-app chains) with reference recipes in
  recipes/reference/. Every reference is valid, succeeds, has no failed events or replay
  duplicates; for filtered tasks, dropping the filter makes the recipe fail. 89 tests
  passing.
- M1.9 5 held-out tasks in tasks/heldout/ with reference recipes in
  recipes/reference/heldout/ (never shown to agents), committed before any agent code. All
  references perfect; filters discriminate. 94 tests passing.
- M1.10 `catalog.py` (Markdown catalog from app specs: triggers, actions with
  inputs/types/enums, object shapes, recipe format + expression cheat sheet; no reference
  recipes) and CLI `flow-forge eval` / `flow-forge catalog`. Employer-terms checks clean
  (tree + history). 99 tests passing. **Milestone 1 done.**
- M2.1 `llm.py` (OllamaClient with reply cap, FakeLLM, extract_recipe) and `tools.py`
  ToolBox: practice world = task seed + 1000 (agents never see test events); read_task,
  read_catalog, sample_events, call_readonly (write actions blocked by the guard),
  write_recipe (versions + validation errors), dry_run (practice-run summary:
  ok/filtered/failed, errors, produced effects, replay duplicates; never the expected
  effects), submit; per-tool limits, call log. 107 tests passing.
- M2.2 `agents.py`: contract prompt + catalog + task (reference never in prompts); `prompt`
  (one call) and `probe` (SAMPLE/CALL lines, up to 3 inspection turns; write actions
  blocked); AgentResult with test-world report, usage, tool log; CLI `flow-forge agent
  --variant prompt|probe` with per-task crash isolation, result.json and summary.json
  (machine/date/model/seed). 114 tests passing. **Milestone 2 done** (real-model smoke run
  pending while connector-forge benchmarks use Ollama).

## Ideas for later

## Publishing plan

Work happens on local branch `dev`. One milestone slice goes to GitHub `main` per day, each with
a README updated that day. Never change commit dates. Per day: cherry-pick that slice's dev
commits onto `publish` (tracks main), update README.md, run tests and employer-terms checks,
ask the user, then `git push origin publish:main`. The GitHub repo does not exist yet: ask the
user before creating it.

## Next step

Milestone 3, step 1: graph agent in agents.py: inspect turn (probe_turns) -> write ->
[validation errors -> fix] -> dry_run -> self-check against the description -> fix, up to 4
rounds; context kept small (contract + catalog + task + current recipe + last tool output);
final = last valid recipe whose dry run had no failed events (else last valid). Tests with
FakeLLM.
