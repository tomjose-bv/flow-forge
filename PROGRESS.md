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

## Ideas for later

## Publishing plan

Work happens on local branch `dev`. One milestone slice goes to GitHub `main` per day, each with
a README updated that day. Never change commit dates. Per day: cherry-pick that slice's dev
commits onto `publish` (tracks main), update README.md, run tests and employer-terms checks,
ask the user, then `git push origin publish:main`. The GitHub repo does not exist yet: ask the
user before creating it.

## Next step

Milestone 1, step 7: harness. `src/flow_forge/harness.py`: effects(apps, initial) =
canonical created/changed objects per app (ids replaced by natural keys: customers by email,
invoices by (customer email, external_ref, amount, currency, memo), messages by (channel,
text), tickets by (title, priority, requester), deal changes by (deal id, stage, note));
evaluate(task, recipe_text): build world twice, run reference and candidate recipes via
AppServer+engine, compare effects -> precision, recall, success, duplicates after a replay,
failed/filtered event counts, validation errors. Tests with an inline reference recipe.
