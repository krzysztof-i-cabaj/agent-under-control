# 🛡️ agent-under-control — guardrails for Claude Code on Windows

[![Claude Code](https://img.shields.io/badge/Claude_Code-hooks_%2B_agent-D97757)]()
[![Platform](https://img.shields.io/badge/Windows_11-tested-0078D6)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)]()
[![Tests](https://img.shields.io/badge/Tests-38%2F38-success)](tests/cases.json)
[![Paths](https://img.shields.io/badge/Install-scripted_%7C_manual-blueviolet)]()
[![License](https://img.shields.io/badge/License-MIT-F1C40F)](LICENSE)

> 🎯 You gave an AI agent access to your work. These hooks decide what it may touch without asking, what needs your
> explicit "yes", and what it can never read — not even through a shell. 🇵🇱 [Wersja polska](README_PL.md)

![~/.claude — what is inside and when it acts](docs/claude-dir-map.svg)

## 🤔 Why

Claude Code has a good permission system. Three things in practice still slip through:

1. **In auto mode, `ask` does not always reach you.** Ordinary permission prompts are resolved by the auto-mode classifier,
   which approves obvious ones itself. Only `deny` is a hard stop. (Per the docs, an `ask` returned by a *hook* still goes
   to a human; `decision_log.py` lets you measure who really answered.)
2. **`deny Read(...)` is a rule for the Read tool.** For a shell command such as `cat ~/.ssh/id_ed25519` it is not
   something you can count on — so the hook checks the command text itself.
3. **A hook that cannot start disappears silently.** A hook called as plain `python` stops working after a PATH change
   and nobody notices, because hook errors do not block the tool. The fix here: a full Python path, tests, and a heartbeat —
   every call leaves a log line, so silence while the agent works raises an alarm (`tools/split_report.py`).

This repository closes those three gaps with three small hooks (two guards, one log-only), a report, one read-only agent and a settings skeleton.
It comes from a real audit of a working setup (Oracle/PostgreSQL DBA work and video production with Claude Code).

## 📦 What's inside

| Path | What it does |
|---|---|
| [`hooks/path_guard.py`](hooks/path_guard.py) | `PreToolUse` hook for every file tool and both shells: **deny** secret files, **ask** outside your workspaces and before any deletion |
| [`hooks/path_guard.config.example.json`](hooks/path_guard.config.example.json) | your workspaces, audit log location, extra deny patterns |
| [`hooks/decision_log.py`](hooks/decision_log.py) | log-only hook: permission prompt, auto-mode denial, tool executed — for the auto-vs-human split and the heartbeat |
| [`tools/split_report.py`](tools/split_report.py) | report: who resolved tool calls, and whether `path_guard` went silent |
| [`hooks/readonly_bash_guard.py`](hooks/readonly_bash_guard.py) | allow-list for Bash: only read-only commands (`git log/show/diff`, `grep`, `cat`…) |
| [`agents/docs-auditor.md`](agents/docs-auditor.md) | sub-agent that checks whether docs still match the code; its Bash is locked by the guard above |
| [`settings/settings.example.json`](settings/settings.example.json) | `deny` / `ask` rules and the hooks wiring (with a full Python path) |
| [`tests/`](tests) | 38 tests: hook input → expected decision, logs and report; runs without Claude Code |
| [`install/install.ps1`](install/install.ps1) | installer with `-DryRun`, backup and a non-destructive `settings.json` merge |
| [`docs/AUDIT_CHECKLIST.md`](docs/AUDIT_CHECKLIST.md) | how to review your own Claude Code setup |

## ⚖️ How `path_guard` decides

| # | Situation | Decision |
|---|---|---|
| 0 | SSH private key (not `.pub`), Claude/Gemini/Docker/DBeaver/pgAdmin credentials, your `extra_hard_deny` patterns — in **any** tool | **deny** |
| 1 | a path outside your workspaces (Read, Edit, Grep, a path inside a shell command, a path inside a script being run) | **ask** |
| 2 | file deletion (`rm`, `Remove-Item`, `del`, `git clean`, `git reset --hard`, `shutil.rmtree`…), also inside a workspace | **ask** |
| 2a | `.env` files (templates such as `.env.example` are fine) | **ask** |
| 2b | a script being run that contains outside paths or computes profile paths (`Path.home()`, `%APPDATA%`) | **ask** |
| 3 | anything else | no decision — Claude Code's normal permissions apply |

Exceptions: Claude Code's own memory, plans and scratchpad; **reading** `~/.claude/rules`. Every `ask` and `deny` is written
to a JSONL audit log. A hook error never blocks your work (fail-open) — it is logged instead.

## 🧮 Who approves? Auto-vs-human split and heartbeat

`path_guard` runs **before** the decision, so on its own it never learns who answered an `ask`. Therefore:

- `path_guard` writes a line to `events_log` on **every** call (`pass` / `ask` / `deny`) with `tool_use_id` and
  `permission_mode`; `audit_log` still holds only `ask` / `deny`;
- [`decision_log.py`](hooks/decision_log.py) (async, never blocks) appends `PermissionRequest` (a prompt shown to a human),
  `PermissionDenied` (auto mode refused), `PostToolUse` / `PostToolUseFailure` (the tool ran) to `events_log`;
- [`tools/split_report.py`](tools/split_report.py) joins them: human approved / rejected, auto mode denied,
  no prompt (an allow rule **or** the classifier — indistinguishable), `ask` without a prompt;
- **heartbeat:** a tool ran but `path_guard` never saw it (a run of ≥ 3) → `ALARM`, exit code 1. A hook that stopped
  starting is no longer silent.

```powershell
python tools/split_report.py --log "$HOME/.claude/logs/path_guard_events.jsonl" --since 2026-10-17
```

Limit: `PermissionRequest` carries no `tool_use_id`; a prompt is matched to its call by session, tool, input hash and time.
Heartbeat idea: Kyle Bartlett, in a comment on the post about this repo.

## 🚀 Install

### 🤖 Scripted path (automatic)

Requirements: Windows 10/11, PowerShell 7+, Python 3.10+.

```powershell
git clone https://github.com/krzysztof-i-cabaj/agent-under-control
cd agent-under-control
pwsh install/install.ps1 -DryRun     # preview: what would be copied, added, kept - changes nothing
pwsh install/install.ps1             # install (backup first, then copy, merge, run the tests)
```

What the installer does:

1. finds Python (refuses the Microsoft Store alias) or takes `-Python "C:/path/to/python.exe"`;
2. backs up existing files to `~/.claude/backups/agent-under-control-<timestamp>/`;
3. copies the three hooks to `~/.claude/hooks/` and writes the agent with full paths filled in;
4. creates `~/.claude/path_guard.config.json` from the example **only if it does not exist**;
5. **merges** `settings.json`: adds missing `deny`/`ask` rules and the hook entry; keeps everything else; never duplicates;
6. runs the tests.

Then edit `workspaces` in `~/.claude/path_guard.config.json` and start a **new** Claude Code session.
Another Claude directory: `-ClaudeDir D:\other\.claude`.

### ✋ Manual path

1. Copy `hooks/path_guard.py`, `hooks/decision_log.py` and `hooks/readonly_bash_guard.py` to `%USERPROFILE%\.claude\hooks\`.
2. Copy `hooks/path_guard.config.example.json` to `%USERPROFILE%\.claude\path_guard.config.json` and set your `workspaces`.
3. Copy `agents/docs-auditor.md` to `%USERPROFILE%\.claude\agents\` and replace `__PYTHON__` with the full path to
   `python.exe` and `__HOOKS_DIR__` with `C:/Users/<you>/.claude/hooks` (forward slashes).
4. Open `%USERPROFILE%\.claude\settings.json` and add from `settings/settings.example.json`: the `deny` and `ask` rules
   you do not have yet, and the `hooks` entries — `PreToolUse` (path_guard) plus `PermissionRequest`, `PermissionDenied`,
   `PostToolUse`, `PostToolUseFailure` (decision_log) — with the same two replacements in `command`. Keep your other settings.
5. Check: `python tests/run_tests.py` → `38/38 passed`. Start a new Claude Code session.

## ⚙️ Configuration

`path_guard` reads the first file it finds: `PATH_GUARD_CONFIG` (environment variable), `path_guard.config.json`
next to the hook, one level up, or in `~/.claude/`.

```json
{
  "workspaces": ["D:/work", "~/projects"],
  "audit_log": "~/.claude/logs/path_guard_audit.jsonl",
  "events_log": "~/.claude/logs/path_guard_events.jsonl",
  "extra_hard_deny": ["\\.aws[/\\\\]credentials", "\\.kube[/\\\\]config"]
}
```

No config at all: the session's project directory is the only workspace, and the log goes to `~/.claude/logs/`.

## 🧪 Tests

```powershell
python tests/run_tests.py
```

Each case in [`tests/cases.json`](tests/cases.json) feeds a hook the same JSON that Claude Code would, and checks the decision.
Add a case whenever you add a rule.

## ↩️ Rollback

The installer saves every file it touches to `~/.claude/backups/agent-under-control-<timestamp>/`. To undo: copy those
files back to `~/.claude/` (and `hooks/`, `agents/`), delete the hook files and the agent if they were new,
then start a new Claude Code session. Manual install: remove the `path_guard.py` and `decision_log.py` entries from `hooks` in `settings.json`.

## ⚠️ Limits — read before you rely on it

- **Not a sandbox.** It is a guard for an honest agent making mistakes, not a security boundary against a hostile one.
  A path assembled at runtime, an encoded command or a tool it does not know about will pass.
- **Windows-first.** Paths are normalized the Windows way (`C:/…`, Git Bash `/c/…`). Linux and macOS are untested.
- **Fail-open by design.** If the hook crashes, your work continues and the error is logged. Check the log now and then.
- **Masking secrets in tool output** is not part of this repository — it needs a Claude Code extension, shown in the series.

## 🎬 Series

These guardrails are shown step by step in the video series **„Agent pod kontrolą”** (Polish, English subtitles)
on the [KCB Consulting](https://www.youtube.com/@KCB_Consulting) YouTube channel.

## 👤 Author

Krzysztof Cabaj · KCB Consulting · License: [MIT](LICENSE)
