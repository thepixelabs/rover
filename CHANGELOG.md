# CHANGELOG


## v0.4.0 (2026-05-23)

### Bug Fixes

- **ci**: Use github.token — no GH_TOKEN secret needed
  ([#3](https://github.com/thepixelabs/rover/pull/3),
  [`f5a113e`](https://github.com/thepixelabs/rover/commit/f5a113edf09c83dbcbc7a94546e1d8352938f965))

## Summary

- Replaces `secrets.GH_TOKEN` with the built-in `github.token` in both the checkout step and the
  semantic-release `env` block - Fixes a stale cache key that still referenced the old `release.yml`
  filename - Removes stale comment that explained why a PAT was needed (no longer applicable)

The job already declares `contents: write`, `pull-requests: write`, and `issues: write` permissions,
  so `github.token` has everything `semantic-release version --push` needs.

## Test plan

- [ ] CI passes on this PR - [ ] After merge, the Release workflow on main completes without `Input
  required and not supplied: token` error

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-authored-by: thepixelabs <pixelicous@users.noreply.github.com>

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>

### Features

- Semantic release, CI/CD, test expansion, landing polish
  ([#1](https://github.com/thepixelabs/rover/pull/1),
  [`f53aa88`](https://github.com/thepixelabs/rover/commit/f53aa886d13aa60f131baab79b72a8399550642a))

## Summary

- **Semantic release** — replaces manual `pypi-publish.yml` with `release.yml` driven by
  `python-semantic-release==9.*`. Merging a `feat:` commit to main publishes to PyPI and bumps the
  Homebrew tap automatically. No more manual tags. - **pytest config** — adds `pythonpath = ["src"]`
  so tests run without `pip install -e .` in local dev - **3 new test files** —
  `test_menu_action_enum`, `test_fetch_menu_stats`, `test_config` — suite grows from 10 to 13 files
  (233 → 236 tests passing) - **Dispatch decoupling** — removes `D`/`B` menu keybinds and
  server-toggle logic from `menu.py` - **README** — slimmed to 168 lines; SSH connectivity detail
  moved to `docs/ssh-setup.md` - **Landing page** — favicon, `#get-home` section rewrite, dictate
  section SSH copy, mascot background visibility fix - **`__version__` fallback** — stale `0.3.4`
  updated to `0.3.8`

## Before merging

- [ ] Update PyPI Trusted Publisher config on pypi.org: change workflow filename from
  `pypi-publish.yml` → `release.yml` (same environment `pypi`, same owner/repo) — otherwise the
  first OIDC exchange will be rejected - [ ] Confirm `GH_TOKEN` secret exists on the repo with
  `contents:write` + `pull-requests:write` scopes

## Test plan

- [ ] CI passes on this PR (lint + pytest on 3.11/3.12/3.13) - [ ] After merge: verify `release.yml`
  runs on main push, no release triggered (no releasable commits yet) - [ ] Merge a `feat:` commit
  and confirm version bump + PyPI publish + Homebrew dispatch fire

🤖 Generated with [Claude Code](https://claude.com/claude-code)

---------

Co-authored-by: thepixelabs <pixelicous@users.noreply.github.com>

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.8 (2026-05-12)

### Bug Fixes

- **ci**: Resolve ruff lint failures (37 errors → 0)
  ([`06c2e6b`](https://github.com/thepixelabs/rover/commit/06c2e6b115b57f0f5c97fd614345624c3493d610))

- ruff --fix auto-resolved 35 unused-import warnings in tests - Manually removed dead
  `session_filter` assignment in screens/activity.py - Renamed ambiguous loop variable `l` → `line`
  in test_telemetry.py

Unblocks Lint job in CI and clears the gate for the next v* release.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

- **ci**: Rover-pypi-publish — strip rover-v prefix, switch tap dispatch to repository_dispatch
  ([`b6fdf5b`](https://github.com/thepixelabs/rover/commit/b6fdf5b74bd0309b243d56bf45935b2ffb1702a1))

Two bugs in the rover-v0.3.4 publish run:

1. Version derivation stripped only "rover-" leaving "v0.3.4", so the sha256 step looked for
  dist/rover_tui-v0.3.4.tar.gz which doesn't exist (hatchling produces rover_tui-0.3.4.tar.gz).
  sha256sum failed silently, output was empty. Now strips "rover-v" and the step fails loudly if
  sdist is missing.

2. Cross-repo trigger to homebrew-tap used `gh workflow run` (workflow_dispatch API), which requires
  actions:write — the tap-scoped GitHub App only has contents:write. Switched to `gh api
  .../dispatches` (repository_dispatch), which only needs contents:write, matching what
  dmg-release.yml already proves works for this App.

Companion change in homebrew-tap adds the matching `repository_dispatch: [rover-bump]` trigger.

- **docs**: Track illustration pack PNGs so Pages deploy doesn't fail
  ([`96e550d`](https://github.com/thepixelabs/rover/commit/96e550d1574174c72a9624a7b0a19c52902be803))

docs.yml copies src/assets/rover/packs/ into the _site artifact (commit a6f18f7), but the pack PNGs
  were never added to git — so the `cp -r` silently found nothing in CI checkout and exited 1,
  failing the Deploy Docs job after every push to main.

Add all three packs' processed PNGs (pack-a-relay-noir, pack-b-field-manual, pack-c-benchtop) as
  tracked assets, and extend .gitignore to exclude *.raw.png source files and scratch generative
  outputs (gemini_*.png, imagen-*.png) so those never land in the tree.

- **nav**: Group brand + breadcrumb so /rover sits tight against DISPATCH
  ([`3dbdc72`](https://github.com/thepixelabs/rover/commit/3dbdc7296c13f7757abf60e81ce49e43e82b196a))

Wrapping both in .nav-brand-wrap (flex, gap: 6px) means space-between treats them as one unit — no
  more breadcrumb floating in the middle of the nav bar.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **nav**: Remove pill/box styling from top bar buttons, hide CTA on mobile
  ([`c082cb3`](https://github.com/thepixelabs/rover/commit/c082cb3d1e7738b44d07661eb82ca2223b0b18e1))

- theme-toggle: remove border + card background → bare icon (36px) - nav-hamburger: same cleanup →
  bare icon (36px) - nav-cta: remove pill (border-radius: 999px), indigo fill, and border → flat
  transparent link matching muted text style - mobile ≤640px: hide nav-cta entirely so DISPATCH
  stays visually left with only hamburger + theme icons on the right

Applies to both landing.html and rover.html.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **nav**: Restore GitHub CTA on mobile — only remove pill/box styling
  ([`e1fde9b`](https://github.com/thepixelabs/rover/commit/e1fde9bed9187397999d777dcfbb5f27d3750fb7))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **nav**: Shrink top bar elements on mobile to prevent overflow
  ([`b92b271`](https://github.com/thepixelabs/rover/commit/b92b2714c81ce5f4de5602856231b9620898cfed))

@media ≤640px for both pages: - nav height: 48px → 44px, padding: 14px → 10px - brand: 1.1rem →
  0.875rem, letter-spacing 2px → 1px, dot 8px → 6px - icon buttons (theme-toggle, hamburger): 36px →
  30px - nav-cta: tighter padding, 0.75rem font, hide star count - dropdown top offset updated to
  44px rover.html @media ≤380px: hide breadcrumb if it won't fit

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **nav**: Tighten breadcrumb spacing, split / and rover colors
  ([`6381063`](https://github.com/thepixelabs/rover/commit/6381063218487bcf60ae9408c43d55bc6dceee1a))

- margin-left: 2px → -4px to close gap between DISPATCH and breadcrumb - / separator gets muted dim
  color (var(--text-muted) at 0.5 opacity) - rover text keeps neon-cyan at 0.7 opacity

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **nav**: Tighten top bar spacing + add /rover breadcrumb
  ([`dd22c75`](https://github.com/thepixelabs/rover/commit/dd22c7513d501e5d4230697e8d78334412c89f52))

- nav height: 60px → 48px - side padding: 20px → 14px - nav-links gap: 8px → 2px, link padding: 6px
  14px → 4px 10px - nav-right gap: 10px → 4px - mobile dropdown top offset updated to match 48px
  height - rover.html: add "/ rover" breadcrumb next to DISPATCH brand in muted cyan

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **rover**: Add LICENSE file to rover/ subdirectory for hatchling build
  ([`fb7b44e`](https://github.com/thepixelabs/rover/commit/fb7b44e73a4b58bd0d5633e62c3af1f450cab9e2))

hatchling builds rover from rover/ as working-directory with ignore-vcs=true, so it cannot resolve
  the repo-root LICENSE. The pyproject.toml license field references { file = "LICENSE" } which
  caused OSError on sdist build. Copy the PolyForm Shield LICENSE into rover/ to fix the PyPI
  publish workflow.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **rover**: Split docsRow copy — distinct label and buttonLabel for docs row
  ([`f130d31`](https://github.com/thepixelabs/rover/commit/f130d31914ce35fc498d615e5be62b8a275c61b7))

## Summary

- `src/copy/rover.ts` — splits `docsRow: { label: 'Open README' }` into `label: 'README and docs'` +
  `buttonLabel: 'Open README'` - `src/components/rover/RoverSettingsPanel.tsx` — button now uses
  `docsRow.buttonLabel` instead of `docsRow.label`

**Before:** the row description span and the button both rendered `"Open README"` → visually `"Open
  README [Open README]"` **After:** span shows `"README and docs"`, button shows `"Open README"`

Caught during post-merge code review of #54.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

- **rover**: Strip SSH-token bridge; altergo owns per-account auth now
  ([#8](https://github.com/thepixelabs/rover/pull/8),
  [`5401e2b`](https://github.com/thepixelabs/rover/commit/5401e2b7573dfe103a135d9a44cd542592a3e5cf))

## Summary

Removes ~170 lines of token/keychain logic that was rover's territorial overreach. With altergo
  1.2.x owning per-account OAuth tokens (via \`altergo --setup-token <account>\` writing to
  \`<home>/.claude/.oauth-token\`) and \`_build_alt_env\` exporting per-subprocess
  \`CLAUDE_CODE_OAUTH_TOKEN\`, rover doesn't need to do anything beyond build an altergo argv and
  run it.

## The bug being fixed

Rover unconditionally exported \`CLAUDE_CODE_OAUTH_TOKEN\` (read from
  \`~/.claude/rover-native-token\`) into its own process env on every launch. That env var inherited
  into every altergo subprocess — including non-native accounts (hocus, pocus, gemini accounts,
  etc.). Claude under those accounts then auth'd as the **native** identity, silently
  cross-contaminating per-account credential state and triggering altergo's destructive keychain
  rebuild path on subsequent launches.

## What's removed

- \`--setup-native-ssh\` CLI flag - \`run_native_ssh_setup\` helper - \`_native_ssh_token_path\`,
  \`_check_native_ssh_token\` - The \`os.environ[\"CLAUDE_CODE_OAUTH_TOKEN\"] = …\` mutation in
  \`__main__.main()\` - The \`if chosen_account == \"native\" and not _check_native_ssh_token\` gate
  in \`_exec_altergo\`

## What's kept

- \`_real_home()\` (still needed for path resolution under altergo's HOME swap) - Everything else:
  menu, altergo launcher pickers, session manager, test infra

## Plus, in this PR

- **Menu banner fix**: removed the redundant second \`rover\` figlet rendered under a user's
  nickname figlet; the version label inside the menu box now reads \`rover v0.3.8\` instead of just
  \`v0.3.8\`. Single figlet, cleaner. - **Fix pre-existing broken test** in
  \`test_sessions_index.py\` — the hardcoded assertion expected \`/home/user/...\` but the function
  returns whatever the dash-decoded path is. Changed to \`-home-alice-projects-foo\` for stable,
  environment-independent testing. - **Bump rover-tui to 0.3.8.**

## Test plan

- [x] All 208 rover tests pass locally (was 207 passing + 1 pre-existing failing → now 208 pass) -
  [x] Manual: \`rover\` → Y → y → hocus through tmux works without crash, with altergo 1.2.2's
  per-account OAuth bridge in place - [x] Manual: rover banner shows single figlet + \`rover
  v0.3.8\` version label

## Release path

Once merged, tag \`rover-v0.3.8\` to trigger \`.github/workflows/rover-pypi-publish.yml\` (OIDC
  trusted publish to PyPI).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

- **rover.html**: Correct PyPI package name and install script URL
  ([`b26e128`](https://github.com/thepixelabs/rover/commit/b26e12891a019d23bc6ed7910c1b4a11462e68f6))

- pipx/uv tabs: rover → rover-tui (PyPI package name) - Script tab: fake rover.thepixelabs.dev
  domain → real GitHub raw URL - JS COMMANDS object updated to match

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **rover/recall**: Delegate R key to altergo --recall, delete custom RecallScreen
  ([`4c6caa1`](https://github.com/thepixelabs/rover/commit/4c6caa194cd204611caf7229628133309275199e))

We were reimplementing altergo's session picker from scratch via a filesystem scan. altergo --recall
  already does this correctly and is maintained there. Now pressing R (or Yolo → Resume) exits rover
  and execs altergo --recall directly.

Removes rover/rover/screens/recall.py entirely.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Documentation

- Readme/changelog/workflow consistency cleanup
  ([`637be56`](https://github.com/thepixelabs/rover/commit/637be56a07293bce872c7c24c5c359438b8fd614))

Surgical post-extraction cleanup of the docs surface:

- README: subtitle rewritten away from "The Dispatch TUI" (post-extraction, rover is standalone).
  Keymap table gains R / N / C rows that the app already binds. Adds optional "Auto-launch on SSH"
  snippet for users SSH'ing in from phone/tablet. - CHANGELOG: [Unreleased] → [0.3.8] - 2026-05-09;
  adds a [0.3.7] stub for the pre-extraction release. - pyproject.toml: description capitalization
  "dispatch" → "Dispatch". - pypi-publish.yml: stale v0.3.4 comment refs bumped to v0.3.8; removed
  one-time migration NOTE about the trusted-publisher configuration.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

- V1.39.0 multi-provider MCP — README, provider guides, landing section
  ([#52](https://github.com/thepixelabs/rover/pull/52),
  [`c70e2f0`](https://github.com/thepixelabs/rover/commit/c70e2f0b4626290398bbd796b4f092facb39ba9c))

## Summary

Follows v1.39.0 (PR #51). Updates public + landing docs to accurately describe the new
  multi-provider MCP install story. Backed by three prep briefs (system-architect change brief,
  product-service-architect positioning, brand-strategist voice).

### Public repo — this PR - **README.md**: new "Works with Claude · Gemini · Copilot · Codex" badge
  chip; MCP bullet corrected (11 tools, all 4 providers); new MCP Integration subsection; Getting
  Started step 5 for one-command install. - **docs/ARCHITECTURE.md, docs/AGENTS.md**: confirmed
  accurate from phase 12, cross-references added. - **docs/providers/{gemini,copilot,codex}.md**:
  applies_to bumped to v1.39.0+; spawn limitations and token-rotation caveats surfaced in intros. -
  **docs/MCP_TOOLS.md**: 11 tools; accurate advisory-mode description of
  `dispatch_update_phase_status` when `REACTOR_SOLE_AUTHORITY=1`; example corrected. -
  **docs/HOW_IT_WORKS.md**: 10→11 tools; provider list updated. - **rover.html (landing)**: new
  section "One Dispatch. Every agent, on the same page." with provider matrix, three outcome-first
  features, single "Install MCP tools" CTA, honest limitations microline. Hero badge `Claude ·
  Gemini · Copilot · Codex`.

### Internal docs (separate trees, not in this PR) Also updated in companion repos (RELEASES.md, README.md, provider-parity-execution-log.md, docs/HOW_IT_WORKS.md, docs/MCP_TOOLS.md, docs/FEATURES.md).

## Voice notes Per brand-strategist: peer-level, dry-with-a-pulse, third-person "Dispatch", no
  "seamless/unified/ecosystem" language. Tagline **"Four agents. One surface."** integrated as
  section eyebrow.

## Test plan - [x] `grep "10 tools|Claude Code only"` returns 0 across README and docs/ - [x]
  Provider matrix colors render via existing `:root` tokens (no new palette) - [x] All CTA links
  resolve to existing files (`docs/providers/README.md`) - [ ] Landing page visually inspected (left
  to reviewer / post-merge deploy)

- **landing**: Refresh rover-menu screenshot with current main menu
  ([`ce527f3`](https://github.com/thepixelabs/rover/commit/ce527f3f721f4f0f64bc2db61fdb2d6b8b34fec5))

Captures the v0.3.8 menu layout (Dispatch Dashboard / altergo session / Yolo / Recall conversation /
  Start dispatch server / Keep mac awake / Settings / Quit). Same convention as the other landing
  screenshots: 720px wide webp, ~28 KB.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

- **rover**: Convert landing page images to WebP (~95% smaller)
  ([`0b7ee2b`](https://github.com/thepixelabs/rover/commit/0b7ee2b1f3bd52f829a44c666c5bd94a0ef2615b))

Page payload drops from ~13MB to ~664KB. Tiny 14x14 icons that were shipped as 1024x1024 PNGs are
  now 28x28 WebP (~3.6MB → ~3KB total). Large illustrations re-encoded as WebP q=82. Hero gets
  fetchpriority, below-the-fold images get loading=lazy. Original PNGs kept outside the repo at
  ../dispatch-rover-image-originals/ for re-encoding source.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

### Features

- Orchestrator-spawn-shift — multi-turn chat, tunnel providers, rover overhaul, notifications
  ([#82](https://github.com/thepixelabs/rover/pull/82),
  [`68a8930`](https://github.com/thepixelabs/rover/commit/68a8930e3b528851ba610a5524d6c20af943542a))

## Summary

This branch closes the **chat-surface epic** (multi-turn agent conversations in the run drawer via
  per-turn \`--resume\`), stacks the **tunnel provider abstraction** (cloudflared + ngrok,
  hot-swap), a **Rover Ground Station UI overhaul**, and **Telegram notifications + signals
  console**.

- **Multi-turn chat loop** — per-turn \`--resume\` spawn model; \`awaiting-input\` run state;
  chatbox visible from all entry points; SSE race fixed; "Connecting forever" fixed; "Agents
  disappeared" fixed (buildState watermark) - **Tunnel providers** — fat \`tunnel-manager.ts\` →
  thin facade + pluggable cloudflared/ngrok providers; hot-swap via \`POST /api/tunnel/provider\`;
  extended retry chain (~38 min); orphan reaping; URL spoofing validation - **Rover Ground Station**
  — Mission Status hero + 2×2 wayfinding cards; two-tier detection (Electron bridge → HTTP
  fallback); new \`PortalPopover\` primitive - **Notifications** — Telegram pushes via
  \`NotificationDispatcher\`; persistent signals console; \`connector:updated\` SSE for instant Chat
  ID refresh - **SplashScreen** — synthwave rewrite; theme-token reactive across all 25 themes

## Verification

- \`tsc --noEmit\` — clean (0 errors) - Server suite — ~7300 tests passing (2 pre-existing unrelated
  flakes: \`lan-guard\`, \`rate-limit\`) - Frontend suite — 2243 passing - Live tier — 12/12
  \`@live\` probes pass (serialized with \`--no-file-parallelism\`)

## Critical discoveries

- \`child.stdin.end()\` is load-bearing for ADR-026 — \`claude -p --input-format stream-json\` reads
  stdin until EOF; unit tests passed silently; live probe caught the hang in minutes -
  \`--session-id\` + \`--resume\` in the same argv crashes the CLI unless \`--fork-session\` is also
  set (Probe 13 catch — also fixed the existing \`/resume\` route)

## Deferred (explicit out-of-scope)

- Launch button vs +New Run UX deduplication (CEO strategic call) - Multi-vendor multi-turn live
  probes (codex/gemini/copilot) - Token-by-token streaming (ADR-023) - Test stability epic for
  pre-existing flakes

See \`.tasks/orchestrator-spawn-shift-chat-surface/branch-overview.md\` for full architecture
  details.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

---------

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

- **e2e**: Phase 30 cross-platform smoke test infrastructure
  ([#49](https://github.com/thepixelabs/rover/pull/49),
  [`7a596e7`](https://github.com/thepixelabs/rover/commit/7a596e799c4d5586b1b6c3eb7d3a976879b582b5))

## Summary

Closes Phase 30 (final phase) of `.tasks/unified-spawn-architecture/plan.md`. Adds hermetic
  end-to-end smoke tests across darwin/linux/win32 × 4 CLIs with **zero API keys, zero network, zero
  per-run cost**.

- **Stub CLIs** (`tests/e2e/stubs/`) speak the real wire protocols — stream-json for claude, ACP for
  gemini+copilot, codex app-server JSON-RPC for codex. Nine baked scenarios cover happy-path,
  permission-deny, stale-session, hang-forever, crash, utf8-split, permission-method-scopes,
  malformed-frame, slow-ack. - **Override mechanism**: single `DISPATCH_E2E_STUB_DIR` env var, read
  once at boot, frozen. Hard-guarded against packaged/production builds. `resolveCliBinary()`
  replaces all 9 call sites in the 4 adapters. - **Frontend**: 10 `data-testid` anchors +
  `/api/onboarding` e2e flag so Playwright can drive the app without fighting CSS and without
  hitting onboarding. - **Playwright suite**: 5 spec files (spawn / approval / resume / timeout /
  reconcile), matrix via grep tags. - **CI workflow** `.github/workflows/e2e-smoke.yml`: flat 3×4
  matrix = 12 jobs, xvfb on Linux, Electron bundled binary (no Playwright Chromium install).

Design produced by 7 parallel analysts → integration contract
  (`docs/phase-30/integration-contract.md`) → 7 parallel implementers → reconciliation pass.
  Contract is the source of truth.

## Test plan

- [x] `npx vitest run server/` — 4227 passing / 17 skipped - [x] `npx vitest run tests/e2e/stubs/` —
  10 stub-protocol smoke tests passing - [x]
  `server/adapters/__tests__/stub-override-prod-safety.test.ts` — 8 tests enforcing prod guard - [x]
  Each stub verified standalone (manual) - [ ] CI `e2e-smoke.yml` passes on the 12-cell matrix (this
  PR) - [ ] Follow-up: real CLI install on a single OS, deferred to release-time manual smoke

- **landing**: Add Source install tab — clone + editable install + run
  ([`a3432ef`](https://github.com/thepixelabs/rover/commit/a3432ef761199c433c6688890c19d6c27ec9bbb5))

Third tab labeled "Source" with three stacked, copyable commands:

git clone https://github.com/thepixelabs/rover.git cd rover && pip install -e ".[dev]" rover

This is the Python equivalent of "git clone && npm run dev" — for contributors who want to hack on
  the TUI directly. The .[dev] extra pulls pytest + pytest-timeout so the test suite can be run
  locally.

Updated section description and install note to acknowledge the third path. Tab icon is an inline
  git-branch SVG (matches the "this isn't a package manager" framing — no package icon).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

- **landing**: Terminal-viewer screenshot block + restore pipx install option
  ([`d3dc61c`](https://github.com/thepixelabs/rover/commit/d3dc61cf9825f98f8cb4848f0311b39c7f40e7e4))

Adds a tabbed mock-terminal viewer (macOS-style traffic-light dots, mono ─[ tab ]─ chrome, status
  bar, faint scan-line) showing three Rover TUI screenshots — main menu, yolo session, settings.
  Replaces the earlier flat-image grid concept. Right-click / tap-and-hold defenses preserved via
  transparent ::after overlay over each panel.

Also restores pipx as a visible install option: tab renamed pip → pipx in the install section, hero
  gains a secondary pipx snippet beside the brew button. Aligns landing with README, which has
  always used pipx for the PyPI install path.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

- **rover**: Add 4-ghost teleport trail to benefits section (surgical)
  ([`57f2369`](https://github.com/thepixelabs/rover/commit/57f2369b4fd6f441446d208d7e28e07fdab09b29))

Reintroduces only the piece of the 3512-line backup the user actually wanted: the four opacity-faded
  mascot residuals on the right edge of the "Four chords, one phone, no laptop." benefits section.
  Everything else from the big backup (different hero copy, different chord-section layout, extra
  illustration PNGs, pack b/pack c) stays out.

Changes: - rover.html: add .rv-benefits-trail-mascot CSS (base + 4 variants with desktop staggered
  right-edge positions at opacity 0.42/0.22/0.17/0.12, light-theme overrides, and mobile layout that
  moves the trail to the left edge) inside the existing <style> block. Insert four aria-hidden <div
  class="rv-benefits-trail-mascot--N"> wrappers at the top of <section id="benefits">, each
  rendering b7-fleet-running.png. Section is already position:relative via .section so no extra
  scaffold needed. - .gitignore: keep src/assets/rover/packs/ broadly ignored (Gemini scratch) but
  explicitly un-ignore only b7-fleet-running.png — the single PNG the trail renders. - docs.yml: add
  one explicit cp for b7-fleet-running.png into the Pages artifact under
  _site/src/assets/rover/packs/pack-a-relay-noir/. -
  src/assets/rover/packs/pack-a-relay-noir/b7-fleet-running.png: restored from reverted commit
  b118e1c's blob (~1.6 MB).

"Your fleet, one SSH away." CTA card was already identical in both versions, so no port needed for
  that.

- **rover**: Add RecallScreen — session picker replacing force-refresh on R
  ([`f99783e`](https://github.com/thepixelabs/rover/commit/f99783e7613e70d040c33ff157d34287c737a1a8))

- R key now opens RecallScreen (full-screen session picker) instead of force-refreshing the main
  menu - RecallScreen lists all altergo sessions with search, provider filter, and sort (time /
  project / provider); Enter resumes selected session - YoloSubmenu "resume last" also routes
  through RecallScreen to avoid the unreliable "guess last session" path

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **rover**: Dashboard redesign + activity screen + package-metadata version
  ([`02dfca5`](https://github.com/thepixelabs/rover/commit/02dfca5d3a7a91cc9ca99ebda3823fe600f85a47))

- __init__.py reads version from importlib.metadata (package name 'rover-tui') with a 0.3.4 fallback
  when running uninstalled from source. - api.py adds a new module (101 lines) — presumably
  dispatch-API helpers for the dashboard screens. - app.py drops the Help screen binding ('?') and
  the manual 'r' refresh binding, removes the in-panel chrome CSS (#status-bar, #session-panel,
  Label.panel-title) and the DataTable border. - screens/dashboard.py and screens/detail.py: 400+
  line reworks each — visual redesign matching the tighter dashboard look. - screens/activity.py:
  new screen (untracked until now).

Grouped as one commit because these files form a single 'dashboard redesign' change. No tests
  touched.

- **rover**: Landing page visual campaign + Settings panel expansion
  ([`b0d2f5b`](https://github.com/thepixelabs/rover/commit/b0d2f5b903f69babf204cc2a26ecdd6c365937ee))

rover.html: - PCB-trace hero background (teal-green animated SVG) - Mobile mascot trail: 2× size,
  higher opacity - Block 2 "One stack. Three surfaces." — new mascot-hero image, translateX overlap
  - Block 3b retitled: "// voice input" / "Dictate. Agent moves." - Block 3 icons removed (icon-free
  card layout) - Block 4 mascot dissolved to absolute background layer - Block 5 keycap-cluster
  image (despilled, clean transparency) - Block 6 rebuilt as terminal SYNOPSIS requirements block
  (host / phone / agent stack) - Block 6 altergo link (Rover drives altergo, not raw provider CLIs)
  - Block 6 background illustration (mascot + clipboard, despilled) - Section label / title font
  sizes bumped ~40%/25% - All image URLs fixed: dispatch-tui/ → rover/

Settings → Rover panel: - RoverPhoneSetupChecklist: 9-item SSH app checklist (details accordion) -
  RoverNativeSshCard: macOS Keychain / Claude SSH token setup - Analytics: phone_checklist_view,
  ssh_token_copy, readme_open events

Assets: - pack-a-relay-noir: b1–b6 processed PNGs committed; *.raw.png, gemini_* ignored - pack-b /
  pack-c ignored (not wired into rover.html) - .gitignore: restore *.raw.png, gemini_*, imagen-*
  rules

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **rover**: Phone-companion TUI + Electron/landing integration
  ([#45](https://github.com/thepixelabs/rover/pull/45),
  [`1c4cb6e`](https://github.com/thepixelabs/rover/commit/1c4cb6e530a9eb5e3ad3cf887ff16ff60da3a854))

## Summary - Adds **Rover**, the Dispatch SSH TUI companion: SSH into your Mac from your phone to
  check/launch/kill any agent. - **Python package** at `rover/` (`dispatch_tui` module,
  `install.sh`, `pyproject.toml`, full test suite). - **Electron integration** — `electron/rover.ts`
  main-process handlers (`rover:detect`, `rover:brewPresent`, `rover:openTerminal`) exposed via
  `preload.ts`; `App.tsx` gains a top-bar launcher plus mobile-overflow entry; `SettingsModal` gains
  a `rover` tab rendering `RoverSettingsPanel`. - **Landing page** — new Rover section in
  `landing.html` (themed SVGs, 25-theme token bridge) and a standalone `rover.html` route. -
  **Assets** — six themed SVGs under `src/assets/rover/`, analytics events, copy strings, IPC shim.
  - **Hygiene** — `.gitignore` now excludes `__pycache__/`, `*.pyc`, `*.pyo`, `.pytest_cache/`.

## Test plan - [ ] `npm run build` — renderer + main compile clean - [ ] Launch Electron app →
  top-bar Rover button opens Settings → Rover tab - [ ] Rover tab: detect/install/update flows
  behave correctly whether Rover is installed or not - [ ] `open rover.html` via `landing.html` nav
  link → Rover section renders across themes - [ ] `cd rover && pytest` — Python test suite green -
  [ ] `cd rover && ./tests/test_install.sh` — install script smoke passes - [ ] Mobile overflow menu
  exposes Rover entry; clicking opens the tab


- **rover**: Standalone distribution — PyPI publish pipeline + install.sh update
  ([`32fc6d2`](https://github.com/thepixelabs/rover/commit/32fc6d2aaee1047a64e41331cdbdbb5cc51a9e42))

- Rename package to rover-tui (PyPI name 'rover' is taken) - Add classifiers, license, URLs,
  keywords to pyproject.toml - install.sh: default to pip install rover-tui; ROVER_LOCAL=1 for
  bundled installs - Add .github/workflows/rover-pypi-publish.yml: OIDC trusted publisher, two-job
  design (build-and-publish + trigger-homebrew-bump), uses existing HOMEBREW_TAP_APP GitHub App for
  cross-repo dispatch to homebrew-tap

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **rover**: Textualize all built-in screens ([#50](https://github.com/thepixelabs/rover/pull/50),
  [`bdd1e57`](https://github.com/thepixelabs/rover/commit/bdd1e5740df68060ccf506a67f70ca7da737be36))

## Summary - Convert remaining raw-terminal / Rich `input()` surfaces to Textual so every built-in
  rover screen uses the same UI layer. - Fix yolo-submenu double-press bug (`Y` → `y` for yolo-new
  previously required Enter or a second keystroke).

## Changes - `YoloSubmenuScreen`: `Screen` → `ModalScreen` — modal screens route keys exclusively,
  eliminating the push-screen race. - New modal screens replace the old `_blocking` helpers: -
  `KillConfirmModalScreen` (y/n) - `NewSessionInputModalScreen` (text input) -
  `ServerToggleModalScreen` (confirm → worker-thread start/stop → result, with `LoadingIndicator`
  for the in-flight phase) - `altergo_launcher._prompt_attach_or_new` → short Textual mini-app (same
  `(console, session_name) -> str` signature kept for test-compat). - Remaining `console.input()`
  fallbacks (native-ssh token missing, no-git-repos-found) reuse the existing `_run_error_screen`. -
  `run_menu`: drop `"kill"`, `"new_tmux_session"`, `"server_toggle"` dispatch arms — now handled
  inline by modals. - Tests: update two pre-existing tests that patched stale module attrs
  (`select`/`tty`/`termios`) that were removed when altergo_launcher was ported to Textual earlier.

## Test plan - [x] `pytest rover/tests/` → 129/129 passing - [ ] Manual: yolo submenu single-press
  (y/r/p) without needing Enter - [ ] Manual: kill confirm, new tmux session, server toggle modals
  render + work over SSH

- **rover**: Wire up 4-ghost trail CSS + HTML + bundling (follow-up to 57f2369)
  ([`d7262b8`](https://github.com/thepixelabs/rover/commit/d7262b8e3345b75ac6b39b34c260b04f573069a6))

Previous commit only included the b7-fleet-running.png blob restore due to a staging error. This
  adds the actual code changes that reference it:

- rover.html: .rv-benefits-trail-mascot CSS (base + 4 variants at opacity 0.42/0.22/0.17/0.12 on
  desktop, mobile layout that stacks on the left edge, light-theme opacity overrides) + 4
  aria-hidden <div> wrappers rendering b7-fleet-running.png at the top of <section id="benefits">.
  Section is already position:relative via .section so anchors work. - .gitignore: broadly ignore
  src/assets/rover/packs/ (Gemini scratch) but un-ignore just b7-fleet-running.png. - docs.yml:
  single explicit cp of that PNG into the Pages artifact under
  _site/src/assets/rover/packs/pack-a-relay-noir/.

"Your fleet, one SSH away." CTA card is already identical in the committed 2787-line version — no
  port needed for that.

- **rover-landing**: Tron-style b2 mascot + trimmed MCP section + mobile glow
  ([`1520d4d`](https://github.com/thepixelabs/rover/commit/1520d4ddf4a86274948667597cef6101b4c53c9f))

- Regenerate b2-mascot-hero in the pack's cyan-rim tron aesthetic so it matches b1/b3b, with the
  figure operating a stack of three cyan-lit surfaces that literalize "One stack. Three surfaces." -
  Re-layout the three-together section: mascot pinned to the section floor, scaled up (820px desktop
  / 1100px 4K / 520px tablet / 300px mobile), 0.88 opacity, combo drop-shadow + ::before radial for
  a top-left light source. - On mobile/tablet the mascot becomes an absolute background layer
  (opacity 0.28/0.22) behind the text; align-self:center so it actually centers inside the wrap and
  the glow tracks the figure instead of floating in empty space. - Replace the mcp-providers section
  copy: new label, headline, benefit-led feature cards, drop the 4x5 capability matrix, shorter
  caveat, and a "Read the provider guide" CTA in place of "Install MCP tools". - prompts.md records
  the generation parameters and prompt for the new asset.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

- **rover/recall**: Polish RecallScreen UX — better columns and copy
  ([`06a5ad8`](https://github.com/thepixelabs/rover/commit/06a5ad88e3cc82e14fdb4eeabef70933144d1c94))

- Merge provider + project into single SOURCE column (saves horizontal space) - Full provider names
  in badges (claude/gemini/codex/copilot) instead of 3-char codes - Wider TOPIC column (40 → 80
  chars) fills terminal width better - "session" → "conversation" throughout (matches altergo
  terminology) - Filter placeholder simplified (/ prefix hint removed)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **settings**: Tool Manager panel with Matrix view + Add Tool wizard
  ([#48](https://github.com/thepixelabs/rover/pull/48),
  [`633101f`](https://github.com/thepixelabs/rover/commit/633101fdc7eee799a7e953687f9836a9c53fdcbf))

## Summary - Replaces \`MCPSourcesPanel\` mount in Settings with a new \`ToolManagerPanel\` two-tab
  wrapper - Tab 1 (\"Sources & Discovered\") keeps the existing experience — default tab preserves
  landing behavior - Tab 2 (\"Matrix\") adds a per-source table with enable toggle, health check,
  remove, plus a guided \`AddToolWizard\` modal

## Why Operators wanted a denser, table-style view of all configured MCP tools alongside the
  existing source-oriented view, and a guided add-tool flow instead of raw JSON.

## Test plan - [ ] Open Settings → MCP → default tab shows existing Sources & Discovered UI
  untouched - [ ] Switch to Matrix tab → table renders with per-source rows - [ ] Toggle enable →
  useTools mutation fires, row updates - [ ] Click health check → status refreshes - [ ] Remove →
  confirms, removes, table refreshes - [ ] Click Add → wizard modal opens, save creates new tool,
  modal closes

### Refactoring

- Restructure repo layout for standalone extraction
  ([`f07623d`](https://github.com/thepixelabs/rover/commit/f07623dac1573843cfb02be7379d259b8ba23f77))

- rover/rover/ → src/rover/ (Python source under src/) - rover/pyproject.toml, README.md, LICENSE →
  repo root - rover/tests/ → tests/ - rover.html → landing/index.html - src/assets/rover/ →
  landing/assets/ - .github/workflows/rover-pypi-publish.yml → .github/workflows/pypi-publish.yml

Decision on src/assets/rover/generated/: excluded from history via --invert-paths in filter-repo.
  Those files are raw concept PNGs with timestamp-based names (gemini_2026*.png, *.raw.png) —
  dev-only generation artifacts never referenced by rover.html or any pack. They add ~30 MB to the
  repo with no runtime value. The finalized assets in packs/ are preserved.
