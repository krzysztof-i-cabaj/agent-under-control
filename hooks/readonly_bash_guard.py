# ==============================================================================
# Tytul:        readonly_bash_guard.py
# Opis:         Hook PreToolUse dla agenta docs-auditor: przepuszcza tylko komendy Bash
#               do odczytu (git log/show/blame/diff..., grep, ls, cat...), reszte blokuje (deny)
# Description [EN]: PreToolUse hook for the docs-auditor agent: allows read-only Bash
#               commands only (git log/show/blame/diff..., grep, ls, cat...), denies the rest
#
# Autor:        KCB Kris
# Data:         2026-10-16
# Wersja:       1.2 (bez sed: skrypt sed potrafi zapisac (w) i wykonac (e); blokada git -O / --open-files-in-pager)
# Konwencje:    README.md (sekcja Read-only agent)
#
# Wymagania [PL]:    - Python 3.10+; podpiety w frontmatter agents/docs-auditor.md
# Requirements [EN]: - Python 3.10+; wired in agents/docs-auditor.md frontmatter
#
# Uzycie [PL]:       hooks.PreToolUse (matcher Bash) w frontmatter agenta; JSON na stdin
# Usage [EN]:        hooks.PreToolUse (matcher Bash) in the agent frontmatter; JSON on stdin
# ==============================================================================
import json
import re
import shlex
import sys

# Komendy dozwolone (pierwsze slowo segmentu) / allowed commands (first word of a segment)
ALLOWED = {'grep', 'rg', 'ls', 'cat', 'head', 'tail', 'wc', 'find', 'sort', 'uniq',
           'cut', 'tr', 'awk', 'diff', 'file', 'stat', 'pwd', 'echo', 'basename',
           'dirname', 'realpath', 'test', 'true', 'git', 'cd'}
GIT_ALLOWED = {'log', 'show', 'blame', 'diff', 'grep', 'rev-parse', 'status',
               'ls-files', 'shortlog', 'describe', 'branch', 'tag', 'rev-list', 'cat-file'}
# Konstrukcje zabronione wszedzie / forbidden anywhere
FORBIDDEN = [
    (r'`|\$\(', 'podstawianie komend'),
    (r'(?<![0-9&])>|>>|[0-9]>(?!&|\s*/dev/null)', 'przekierowanie do pliku'),
    (r'\btee\b', 'tee'),
    (r'\bawk\b[^|;&]*(system\s*\(|>\s*")', 'awk z zapisem lub system()'),
    (r'\bfind\b[^|;&]*\s-(delete|exec|execdir|ok|okdir|fprint\w*|fls)\b', 'find z akcja'),
    (r'\bsort\b[^|;&]*\s-o\b', 'sort -o'),
    (r'\bgit\b[^|;&]*\s--output\b', 'git --output'),
    # git grep -O<prog> / --open-files-in-pager uruchamia program / runs a program
    (r'\bgit\b[^|;&]*\s(-O|--open-files-in-pager)', 'git grep -O (uruchamia program)'),
    # -c ustawia konfiguracje (np. core.pager) = mozliwe uruchomienie dowolnej komendy
    # -c sets config (e.g. core.pager) = can run an arbitrary command
    (r'\bgit\b[^|;&]*\s-c\s', 'git -c (zmiana konfiguracji)'),
]
# Opcje globalne gita, ktore biora nastepny argument / git global options taking the next word
GIT_OPTS_WITH_ARG = {'-C', '--git-dir', '--work-tree', '--namespace'}


def git_sub(words: list[str]) -> tuple[str, list[str]]:
    """Zwraca (podkomenda, reszta argumentow), pomijajac opcje globalne gita."""
    i = 1
    while i < len(words):
        w = words[i]
        if w in GIT_OPTS_WITH_ARG:
            i += 2
            continue
        if w.startswith('-'):
            i += 1
            continue
        return w, words[i + 1:]
    return '', []


def split_words(seg: str) -> list[str]:
    try:
        return shlex.split(seg, posix=True)
    except ValueError:
        return seg.split()


def check(cmd: str):
    # 2>/dev/null i 2>&1 sa nieszkodliwe / harmless stderr redirections
    clean = re.sub(r'\s[12]?>\s*/dev/null|\s2>&1', ' ', cmd)
    for pat, why in FORBIDDEN:
        if re.search(pat, clean):
            return why
    for seg in re.split(r'\|\||&&|[|;\n]', clean):
        words = split_words(seg.strip())
        if not words:
            continue
        head = words[0]
        if head not in ALLOWED:
            return f'komenda spoza bialej listy: {head}'
        if head == 'git':
            sub, rest = git_sub(words)
            if sub not in GIT_ALLOWED:
                return f'git {sub or "?"} spoza bialej listy'
            flags = ''.join(w[1:] for w in rest if w.startswith('-') and not w.startswith('--'))
            longs = {w.split('=')[0] for w in rest if w.startswith('--')}
            if sub == 'branch' and (set(flags) & set('dDmMcC') or longs & {'--delete', '--move', '--copy', '--set-upstream-to', '--unset-upstream', '--edit-description'}):
                return 'git branch ze zmiana'
            if sub == 'tag' and (set(flags) & set('dasf') or longs & {'--delete', '--annotate', '--sign', '--force'}):
                return 'git tag ze zmiana'
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # brak danych -> bez decyzji / no data -> no decision
    if data.get('tool_name') != 'Bash':
        return
    why = check(data.get('tool_input', {}).get('command', ''))
    if why:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': f'readonly_bash_guard: {why}. Agent docs-auditor ma Bash tylko do odczytu.'}},
            ensure_ascii=False))


if __name__ == '__main__':
    main()
