# Contributing

No CONTRIBUTING.md or governance docs exist in-repo. The following is **only** what the repository already encodes.

## Workflow encoded in this repo

- Changes are expected to land via GitHub PRs (`.github/workflows/ci.yml` runs on push and pull_request).
- Cursor rules under `.cursor/rules/` describe an internal lifecycle (branch → PR → merge → deploy). That is operator process, not published OSS governance.

## Before a PR

1. Prefer a feature branch (do not commit directly to `main` if following project rules).
2. Use terms from [`ubiquitous-language.md`](../../ubiquitous-language.md).
3. Run backend pytest and frontend `npm test` + `npm run build` when behaviour changes.
4. Do not add secrets to git. Root `.gitignore` excludes `.env` / `.env.*` (except `*.example`), private keys, credential JSON, Compose override/debug files, and runtime `data/*` blobs. Commit product docs under `docs/` and `ubiquitous-language.md`; do not commit `notes.md` or `*.plan.md`.

## Scope

Do not treat issues/plans (`notes.md`, `*.plan.md`) as specifications without checking current code.

Contributions are under the same [GNU AGPL v3.0](../../LICENSE) as the rest of lesspaper-ngl.

There is **no** documented CLA, code of conduct, or security disclosure process in the repository (**Confirmed** absence).
