# ✅ Claude Code setup audit — checklist

[![Scope](https://img.shields.io/badge/Scope-settings_%C2%B7_hooks_%C2%B7_skills_%C2%B7_memory-blue)]()
[![Mode](https://img.shields.io/badge/Mode-read--only_first-success)]()

> 🎯 A setup grows for months: hooks, rules, skills, memory, plugins. Once in a while check that it still does what you
> think it does. Rule zero: **back up first, change after** — and change nothing during the review itself.
> 🇵🇱 [Wersja polska](AUDIT_CHECKLIST_PL.md)

## 🔐 1. Permissions and hooks

- [ ] `settings.json` is valid JSON; no rule is both in `allow` and `deny`.
- [ ] Secret files are in **`deny`**, not `ask` (auto mode can approve `ask` by itself).
- [ ] Secrets are also blocked **in shells**, not only for the Read tool (test: ask the agent to `cat` a test key).
- [ ] Every hook `command` uses a **full path** to the interpreter; every script it calls exists.
- [ ] Each hook has been run by hand with sample JSON on stdin — it returns the decision you expect.
- [ ] Hooks that are not wired anywhere (orphans) are archived; old `*.bak` files do not sit next to live ones.
- [ ] A "read-only" agent really is read-only: check what its allowed commands can do (`sed` can write files and run
      programs; `git grep -O` runs a program; `git -c` changes configuration).

## 🧩 2. Skills

- [ ] Every `SKILL.md` has valid YAML front matter (strict parser) and a `name` equal to its folder.
- [ ] Each `description` says **when** to use the skill — and when **not** (overlapping skills compete for the same request).
- [ ] No duplicates between local skills and skills synced from claude.ai.
- [ ] Copies of upstream skills are current: compare with the source repository **after** pulling it.
- [ ] **Domain skills written with AI are verified against official documentation** — package, view, column and
      parameter names, versions, licensing. Generated code looks plausible and can still reference objects that do not exist.

## 🧠 3. Instructions and memory

- [ ] `CLAUDE.md` files do not contradict each other or your rules files; links point to existing files.
- [ ] Facts in instructions are current (versions, directory lists).
- [ ] Memory index has no orphans or dead entries; entries are short; nothing says "waiting" for something long done.
- [ ] Memory does not duplicate rules; permanent rules live in `CLAUDE.md` / rules, not in memory.
- [ ] No secrets in memory or instructions (or, if you accept lab passwords, the masking really catches them).
- [ ] Encoding check: no mojibake, no control characters in any of these files.

## 🔌 4. Plugins, MCP, extensions

- [ ] Every enabled plugin is installed and authenticated; no service is configured twice (plugin + connector).
- [ ] List active MCP servers by name — anything you do not recognize goes.
- [ ] Pulling a public repository changes nothing by itself — check what in your setup actually **uses** it.

## 🧾 5. After the review

- [ ] Findings in a report: `file:line | problem | severity | fix`; severity = bug / risk / housekeeping.
- [ ] Fix in packages, each one: backup → change → verify (JSON parses, hook test passes, skill still loads).
- [ ] Move, do not delete; keep the backup until the next review.
