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

## Ideas for later

## Publishing plan

Work happens on local branch `dev`. One milestone slice goes to GitHub `main` per day, each with
a README updated that day. Never change commit dates. Per day: cherry-pick that slice's dev
commits onto `publish` (tracks main), update README.md, run tests and employer-terms checks,
ask the user, then `git push origin publish:main`. The GitHub repo does not exist yet: ask the
user before creating it.

## Next step

Milestone 1, step 4: recipe format + validation. `src/flow_forge/recipe.py`: load YAML
recipe {name, trigger: {app, event, filter?}, steps: [{id, action: app.name, inputs, if?} |
{id, for_each: expr, steps: [...]} ] }; validate() against the apps' TriggerSpec/ActionSpec
(unknown app/action/event, unknown or missing required inputs, duplicate step ids,
references to later or unknown steps, expression syntax) returning a list of readable
errors. Tests.
