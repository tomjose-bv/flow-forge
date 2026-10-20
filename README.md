# flow-forge

A local AI agent that turns a plain-English description of an integration workflow ("when a deal
is won in the CRM, create an invoice and post a message to chat") into a recipe, plus a benchmark
that measures whether the recipe actually does the right thing: the right side effects, exactly
once, nothing for events that should be ignored, and correct behaviour when events are replayed.
Everything runs on one machine: Ollama for the model, standard-library mock apps on localhost.

Most workflow tools show that a recipe ran. This project measures whether it did what was asked.

**Status:** milestone 1 of 5 done: mock apps, recipe format, expression language, engine, tasks,
evaluation harness and reference recipes. The AI agents come next (see [Roadmap](#roadmap)).

## How it works

```
task YAML ──► mock apps (crm, billing, chat, tickets) on localhost
    │              ▲            │ events feed (triggers)
    ▼              │ actions    ▼
 description     recipe ──► engine
                                │
          harness: events → engine → app state → compare with the reference recipe's effects
```

- **Mock apps** (`apps.py`, `server.py`): CRM (deals, contacts), billing (customers, invoices),
  chat (channels, messages) and tickets. Each has an events feed for triggers and typed actions
  with clear validation errors, API keys and idempotency keys.
- **Recipes** (`recipe.py`): declarative YAML: one trigger with an optional filter, then steps
  (`action`, optional `if`, `for_each`). Mappings and conditions use a small expression language
  (`expr.py`, its own parser, no `eval`): `{{trigger.deal.amount}}`, `steps.customer is null`,
  `'enterprise' in trigger.deal.tags`, `| default: ...`.
- **Engine** (`engine.py`): polls the trigger app, applies the filter, runs the steps, retries 429
  and 5xx responses, and sends an idempotency key per (event, step) so replays never duplicate
  side effects.
- **Tasks** (`tasks/`): a description, the apps, and a seeded world and event stream. 16
  development tasks and 5 held-out tasks, each with a hand-written reference recipe.
- **Harness** (`harness.py`): runs a candidate recipe and the reference on identical worlds and
  compares side effects in a canonical form (generated ids replaced by natural keys), then
  replays every event to count duplicates.
- **App catalog** (`catalog.py`): Markdown docs of the apps' triggers, actions and objects plus
  the recipe format. It will be all the agents get about the apps.

Every reference recipe scores perfectly, and for every task with a filter, dropping the filter
makes the recipe fail, so the tasks tell careless recipes from correct ones.

## Setup

Requires Python 3.12.

```
python scripts/setup.py
.venv\Scripts\python -m pytest -q          # Windows
.venv/bin/python -m pytest -q              # macOS/Linux
```

```
.venv\Scripts\flow-forge eval --set dev                              # score the reference recipes
.venv\Scripts\flow-forge catalog tasks/dev/won_deal_invoice.yaml     # what an agent will see
```

## Roadmap

1. ~~Mock apps, catalog, recipe format, expression language, engine, tasks, harness, reference recipes.~~
2. Guard, agent tools, LLM client, `prompt` and `probe` agents (Ollama, `qwen2.5-coder:3b`).
3. The `graph` agent with validate → dry run → fix.
4. Fault injection, ambiguous tasks and an agent that asks clarifying questions.
5. Runs over three seeds, results in this README, CI, v0.1.0 release.

## License

MIT
