# Hermes mono-repo merge report

Reconstruction of the original **nousresearch/hermes-agent @ `5d33efd99`** mono-repo
by merging the two forks that were split from it:

- **AgentFlowX/agentflow-runtime** — Python agent + infra. Kept as the **base** of this
  merge (its full clone, including `.git`, so upstream + fork history is preserved).
  Merged working tree HEAD: `57f899faade5f1dbfce4ead31895809f1a664252`.
- **AgentFlowX/agentflow-app** — JS/desktop client. Its unique top-level dirs and root
  files were grafted onto the runtime base at the repo root (side-by-side, matching the
  original upstream layout).

The two forks are disjoint for all code: each deleted the other track's half. Only 5
top-level paths existed in both; of those, 3 are byte-identical, and 2 needed a merge.

---

## What came from the runtime base (unchanged)
Everything in the runtime clone was taken as-is, including its `.git` history. This
covers all Python trees (`agent/ gateway/ hermes_cli/ plugins/ providers/ tui_gateway/
skills/ tools/ cron/ native/ locales/ evals/ acp_adapter/ optional-mcps/ optional-skills/
scripts/ tests/ docs/ website/ contributors/ …`), the root Python modules (`cli.py`,
`batch_runner.py`, `hermes_*.py`, `hermes`), and all infra/root files: `Dockerfile`,
`docker-compose.yml`, `docker-compose.windows.yml`, `flake.nix`, `flake.lock`,
`pyproject.toml`, `setup.py`, `uv.lock`, `constraints-termux.txt`, `AGENTS.md`,
`CONTRIBUTING*.md`, README family, `LICENSE`, and all dotfiles
(`.env.example .envrc .npmrc .nvmrc .prettierrc .prettierignore .python-version
.dockerignore .gitattributes .hadolint.yaml .coderabbit.yaml .mailmap`).
Also `.github/workflows/trigger-agent-image.yml` (runtime-only; no collision).

## What was copied FROM app (new paths grafted at root)
All copied verbatim from the app working tree. No collisions — none of these existed in
the runtime base.

| Path | Type | Files |
|---|---|---|
| `apps/` | dir (`bootstrap-installer`, `desktop`, `shared`) | 1766 |
| `web/` | dir | 181 |
| `ui-tui/` | dir (incl. `ui-tui/.gitignore`) | 467 |
| `tests-js/` | dir | 10 |
| `package.json` | root file (npm workspaces: `apps/*`, `ui-tui`, `ui-tui/packages/*`, `web`, `tests-js`) | 1 |
| `package-lock.json` | root file (lockfile for the workspace set) | 1 |

Total new from app: **2426 files**.

## Shared files present in both — NOT re-copied (runtime copy kept; verified byte-identical)
These 15 files exist in both forks identically, so the runtime base copy is authoritative
and app's copies were skipped:
- `.gitignore` — identical (covers both Python and JS ignores; it is the upstream root file)
- `FORK.md` — identical
- `eslint.config.shared.mjs` — identical
- `.github/**` (11 files: issue/PR templates, 4 composite actions, `dependabot.yml`, and
  `workflows/*` except `ci.yml`) — all identical

## Reconciled files (differed between forks → merged by hand)

### 1. `CLAUDE.md` — MERGED (union of both tracks)
Each fork's `CLAUDE.md` documented only its own track and did not overlap. The merged file
keeps the shared header (`🔴 ПЕРВЫМ ДЕЛОМ прочитай ~/Agent/WORKSPACE.md`) once, then carries
both track sections under headings: **"Python runtime"** (from runtime, verbatim guidance)
and **"Desktop app"** (from app, verbatim guidance). Pure union — no content dropped, no
line-level conflict. A one-line mono-repo intro was added on top.

### 2. `.github/workflows/ci.yml` — MERGED (union of both jobs)
Both files were `name: ci` with identical `on:` triggers but a single, different job.
Merged file keeps the shared `name:`/`on:` and places BOTH jobs under `jobs:`:
- `lint-test:` (from runtime — setup-python 3.11 + ruff + pytest)
- `build:` (from app — setup-node 22 + npm ci + build `apps/desktop`)

Distinct top-level job keys, so the union is clean; both toolchains run in CI, as the
original upstream mono-repo would have.

---

## Result
Merged working tree: **6948** tracked (runtime base) + **2426** new (app) = **9374** files.
`git status` shows exactly: 2 modified tracked files (`CLAUDE.md`, `.github/workflows/ci.yml`)
and 6 new untracked top-level paths (`apps/ web/ ui-tui/ tests-js/ package.json
package-lock.json`). **No deletions.** Nothing committed or pushed.

## Could NOT cleanly reconcile / needs owner decision
**Nothing blocked.** Every path was either single-sided (grafted as-is), byte-identical
(one copy kept), or a clean union (`CLAUDE.md`, `ci.yml`). No true content conflict required
choosing one fork's changes over the other's — both forks only ever deleted the other
track's files, never edited the same lines.

Minor notes for the owner (informational, not blockers):
- The merged `.git` carries **runtime's** history only. App's independent fork commits are
  not in this history (they were a parallel branch off the same upstream). If app-side
  history must also be preserved, it would need a separate `git replace`/graft or a
  `subtree`-style import — out of scope for this file-level reconstruction.
- Root `package.json` came from app unchanged; its `postinstall` already references
  `python run_agent.py --help`, confirming it was authored as the combined-repo root and
  now sits correctly beside the Python side.
