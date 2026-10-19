# flow-forge

A local AI agent that turns a plain-English description of an integration workflow ("when a deal
is won in the CRM, create an invoice and post a message to chat") into a tested recipe, plus a
benchmark that measures whether the recipes are actually correct. Everything runs on one
machine: Ollama for the model, standard-library mock apps on localhost.

Status: early development.

## Setup

```
python scripts/setup.py
.venv\Scripts\python -m pytest -q      # Windows
.venv/bin/python -m pytest -q          # macOS/Linux
```
