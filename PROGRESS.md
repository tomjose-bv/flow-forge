# Progress

## Done

- Plan written (PLAN.md). Local repo created with personal git identity.
- M1.1 Project skeleton: pyproject, src layout, scripts/setup.py (.venv), MIT license,
  README stub, smoke tests. 2 tests passing.

## Ideas for later

## Publishing plan

Work happens on local branch `dev`. One milestone slice goes to GitHub `main` per day, each with
a README updated that day. Never change commit dates. Per day: cherry-pick that slice's dev
commits onto `publish` (tracks main), update README.md, run tests and employer-terms checks,
ask the user, then `git push origin publish:main`. The GitHub repo does not exist yet: ask the
user before creating it.

## Next step

Milestone 1, step 2: mock apps. `src/flow_forge/apps.py`: an in-memory App base (objects per
collection, append-only events list with ids, action handlers, idempotency-key cache) and 4
apps: crm (deals, contacts; events deal.created/deal.updated/deal.won), billing (customers,
invoices; create_invoice, find_customer), chat (channels, post_message), tickets
(create_ticket, find_ticket). One stdlib HTTP server exposing POST /<app>/actions/<name>,
GET /<app>/events?after=<id>, API-key auth per app, request log. Tests with urllib.
