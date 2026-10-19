# Progress

## Done

- Plan written (PLAN.md). Local repo created with personal git identity.

## Publishing plan

Work happens on local branch `dev`. One milestone slice goes to GitHub `main` per day, each with
a README updated that day. Never change commit dates. Per day: cherry-pick that slice's dev
commits onto `publish` (tracks main), update README.md, run tests and employer-terms checks,
ask the user, then `git push origin publish:main`. The GitHub repo does not exist yet: ask the
user before creating it.

## Ideas for later

## Next step

Milestone 1, step 1: project skeleton (`pyproject.toml`, `src/flow_forge/`, `tests/`,
`.gitignore`, `.gitattributes`, MIT LICENSE, README stub, `scripts/setup.py` creating `.venv`
with pyyaml + pytest), one passing smoke test, commit on `dev`.
