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

## Ideas for later

## Publishing plan

Work happens on local branch `dev`. One milestone slice goes to GitHub `main` per day, each with
a README updated that day. Never change commit dates. Per day: cherry-pick that slice's dev
commits onto `publish` (tracks main), update README.md, run tests and employer-terms checks,
ask the user, then `git push origin publish:main`. The GitHub repo does not exist yet: ask the
user before creating it.

## Next step

Milestone 1, step 10 (last of M1): app catalog + CLI. `src/flow_forge/catalog.py` renders
Markdown docs of the task's apps from ActionSpec/TriggerSpec (triggers + data shape, actions
+ inputs/types/enums/required + output, recipe format and expression cheat sheet) - the only
app info agents get; CLI `flow-forge eval --set dev|heldout [--task X] [--recipe-dir DIR]
[--out f.json]` scoring a directory of recipes against the references. Then employer-terms
checks; mark milestone 1 done.
