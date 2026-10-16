# ==============================================================================
# Tytul:        path_guard.py
# Opis:         Hook PreToolUse Claude Code: pytanie o zgode (ASK) przy dostepie poza
#               katalogami roboczymi i przy usuwaniu plikow; twarda blokada (DENY)
#               plikow z sekretami w kazdym narzedziu, takze w shellu
# Description [EN]: Claude Code PreToolUse hook: permission prompt (ASK) for access
#               outside your workspaces and for file deletion; hard DENY for secret
#               files in every tool, including shells
#
# Autor:        KCB Kris
# Data:         2026-10-16
# Wersja:       2.0 (konfiguracja z pliku JSON zamiast sciezek w kodzie / JSON config)
# Konwencje:    README.md (sekcja Configuration)
#
# Wymagania [PL]:    - Python 3.10+; Windows 10/11 (testowane na Windows 11)
#                    - wpis hooks.PreToolUse w ~/.claude/settings.json (settings/settings.example.json)
# Requirements [EN]: - Python 3.10+; Windows 10/11 (tested on Windows 11)
#                    - hooks.PreToolUse entry in ~/.claude/settings.json (settings/settings.example.json)
#
# Uzycie [PL]:       Uruchamia go Claude Code (JSON na stdin). Testy: python tests/run_tests.py
# Usage [EN]:        Run by Claude Code (JSON on stdin). Tests: python tests/run_tests.py
# ==============================================================================
"""
Zasady / Rules:
  0. Plik z sekretami (klucz SSH bez .pub, dane logowania Claude/Gemini/Docker/DBeaver/pgAdmin,
     + wzorce z extra_hard_deny) w DOWOLNYM narzedziu -> DENY.
     Secret file in ANY tool -> DENY. (Auto mode can approve ASK on its own; only DENY is a hard stop.)
  1. Sciezka poza katalogami roboczymi (workspaces, z podkatalogami) -> ASK.
     Path outside your workspaces (including subdirectories) -> ASK.
  2. Usuwanie plikow (rm, Remove-Item, del, git clean, ...) -> ASK, takze w katalogu roboczym.
     File deletion -> ASK, also inside a workspace.
  2a. Pliki .env (bez .env.example/.sample/.template/.dist) -> ASK, takze w katalogu roboczym.
  2b. Uruchamiany skrypt (python x.py, node x.js, pwsh -File x.ps1, ./x.sh): hook czyta plik i pyta,
      gdy zawiera sciezki spoza katalogow roboczych lub sciezki wyliczane do profilu (Path.home(), %APPDATA%).
      Heurystyka: nie wykryje sciezki skladanej w locie.
      A script being run is read; ASK if it contains outside paths or computed profile paths (heuristic).
  3. Wszystko inne -> brak decyzji (dziala zwykly mechanizm uprawnien Claude Code).
     Anything else -> no decision (Claude Code's normal permission flow applies).
  Wyjatki: pamiec, plany i scratchpad samego Claude Code; Read z ~/.claude/rules.
  Blad hooka -> brak decyzji (fail-open), blad zapisany w logu. Hook error -> fail-open, logged.

Konfiguracja / Configuration (JSON, pierwszy znaleziony plik / first file found):
  1. zmienna srodowiskowa / env var PATH_GUARD_CONFIG
  2. path_guard.config.json obok tego pliku / next to this file
  3. path_guard.config.json katalog wyzej (tam kladzie go install.ps1) / one level up (install.ps1 puts it there)
  4. ~/.claude/path_guard.config.json
  Pola / fields: workspaces (lista katalogow), audit_log (plik .jsonl), extra_hard_deny (lista regex).
  Bez konfiguracji: katalogiem roboczym jest katalog projektu sesji (CLAUDE_PROJECT_DIR albo cwd),
  log w ~/.claude/logs/path_guard_audit.jsonl.
  Without config: the session's project directory is the only workspace.
"""
import json
import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import PurePosixPath

HOME = os.path.expanduser('~').replace('\\', '/').lower()
TEMP = os.environ.get('TEMP', HOME + '/appdata/local/temp').replace('\\', '/').lower()
HERE = os.path.dirname(os.path.abspath(__file__))


def load_config():
    """Pierwszy istniejacy plik konfiguracji / first existing config file."""
    for p in (os.environ.get('PATH_GUARD_CONFIG'),
              os.path.join(HERE, 'path_guard.config.json'),
              os.path.join(os.path.dirname(HERE), 'path_guard.config.json'),   # <claude dir>/ (install.ps1)
              os.path.join(os.path.expanduser('~'), '.claude', 'path_guard.config.json')):
        if p and os.path.isfile(p):
            with open(p, encoding='utf-8') as f:
                return json.load(f)
    return {}


CONFIG = load_config()
AUDIT_LOG = os.path.expanduser(CONFIG.get('audit_log')
                               or os.path.join('~', '.claude', 'logs', 'path_guard_audit.jsonl'))

# Wyjatki: katalogi robocze Claude Code / Claude Code's own working dirs
EXCEPTIONS = [
    re.compile('^' + re.escape(HOME) + r'/\.claude/projects/[^/]+/memory(/|$)'),
    re.compile('^' + re.escape(HOME) + r'/\.claude/plans(/|$)'),
    re.compile('^' + re.escape(TEMP) + r'/claude(/|$)'),
]
# Wyjatki TYLKO dla narzedzia Read: reguly Claude Code; zapis/edycja nadal ASK
# Read-only exceptions: Claude Code rules; write/edit still ASK
READ_EXCEPTIONS = [
    re.compile('^' + re.escape(HOME) + r'/\.claude/rules(/|$)'),
]

# Twardy DENY: pliki z sekretami - kazde narzedzie / hard DENY: secret files - any tool
HARD_DENY = [re.compile(r, re.I) for r in (
    r'(^|[\s"\'=/\\])(~|\$home|\$env:userprofile|c:[/\\]users[/\\][^/\\]+)[/\\]\.ssh[/\\]id_[^\s"\';|&]*(?<!\.pub)(?=$|[\s"\';|&])',
    r'\.claude[/\\]\.credentials\.json',
    r'\.gemini[/\\]oauth_creds\.json',
    r'\.config[/\\]gws[/\\]',
    r'dbeaverdata[/\\].*credentials-config\.json',
    r'\.docker[/\\]config\.json',
    r'appdata[/\\]roaming[/\\]pgadmin(?=$|[/\\\s"\'])',
    *CONFIG.get('extra_hard_deny', []),
)]


def hard_deny(data):
    """Zwraca opis trafienia albo None / returns the hit or None."""
    ti = data.get('tool_input') or {}
    text = ' '.join(str(ti.get(k) or '') for k in ('file_path', 'notebook_path', 'path', 'pattern', 'glob', 'command'))
    text = text.replace(HOME, '~')
    for r in HARD_DENY:
        m = r.search(text)
        if m:
            return m.group(0).strip()
    return None


# Programy uruchamiane z pelnej sciezki (pozycja komendy) nie sa "dostepem do plikow"
# Executables invoked by full path (command position) are not treated as file access
EXEC_PREFIXES = ('c:/program files/', 'c:/program files (x86)/', 'c:/windows/')

DELETE_PATTERNS = [
    r'(?<![\w.-])(rm|rmdir|unlink|shred)\s',
    r'(?<![\w.-])(del|erase|rd)\s+[/"\'\w.$%~\\]',
    r'\bRemove-Item\b', r'(?<![\w.-])ri\s', r'\bClear-RecycleBin\b',
    r'\bgit\s+(rm|clean)\b', r'\bgit\s+reset\s+--hard\b', r'\bgit\s+checkout\s+--\s',
    r'\bfind\b.*\s-delete\b',
    r'\bshutil\.rmtree\b', r'\bos\.(remove|unlink|rmdir|removedirs)\b', r'\.unlink\(', r'\.rmdir\(',
    r'\[System\.IO\.(File|Directory)\]::Delete\b',
]
DELETE_RE = re.compile('|'.join(DELETE_PATTERNS), re.I)

# Pliki .env: zawsze ASK, takze w katalogu roboczym; bez szablonow (.env.example/.sample/.template/.dist)
SECRET_RE = re.compile(
    r'(?<![\w-])\.env(?:\.(?!example\b|sample\b|template\b|dist\b)[\w-]+)?(?![\w.-])', re.I)

PATH_TOKEN_RE = re.compile(
    r'''(?ix)
    (?<![\w/:.$%~-])(?:
        [a-z]:[\\/](?:\\\ |[^\s'"|;&<>()])*      # C:\x  C:/x
      | //?[a-z]/(?:\\\ |[^\s'"|;&<>()])*        # /c/x  //c/x (Git Bash), "Program\ Files"
      | ~(?:[\\/](?:\\\ |[^\s'"|;&<>()])*)?(?![\w])  # ~ ~/x
      | \$HOME(?:\\\ |[^\s'"|;&<>()])*
      | \$env:USERPROFILE(?:\\\ |[^\s'"|;&<>()])*
      | %USERPROFILE%(?:\\\ |[^\s'"|;&<>()])*
      | \.\.(?:[\\/](?:\\\ |[^\s'"|;&<>()])*)?(?![\w.])   # .. ../x
      | /tmp\b(?:\\\ |[^\s'"|;&<>()])*
    )''')


def normalize(p, cwd):
    """Zamiana na postac 'd:/x/y' (male litery) / normalize to 'd:/x/y' lowercase."""
    p = p.strip().strip('"\'').replace('\\ ', ' ').replace('\\', '/')
    low = p.lower()
    for var in ('$home', '$env:userprofile', '%userprofile%'):
        if low.startswith(var):
            p = HOME + p[len(var):]
            low = p.lower()
    if low.startswith('~'):
        p = HOME + p[1:]
    elif low.startswith('/tmp'):
        p = TEMP + p[4:]
    m = re.match(r'^//?([a-zA-Z])/(.*)$', p)
    if m:
        p = m.group(1) + ':/' + m.group(2)
    if not re.match(r'^[a-zA-Z]:/', p):
        p = cwd.rstrip('/') + '/' + p
    drive, rest = p[:2], p[2:]
    parts = []
    for seg in PurePosixPath(rest).parts:
        if seg == '..':
            if len(parts) > 1:
                parts.pop()
        elif seg not in ('.', ''):
            parts.append(seg)
    norm = drive + '/' + '/'.join(x for x in parts if x != '/')
    return norm.lower().rstrip('/')


def workspaces(cwd):
    """Katalogi robocze z konfiguracji albo katalog projektu sesji / configured workspaces or the project dir."""
    ws = CONFIG.get('workspaces') or [os.environ.get('CLAUDE_PROJECT_DIR') or cwd]
    return tuple(normalize(os.path.expanduser(w), cwd) for w in ws)


def is_inside(norm, ws):
    return any(norm == w or norm.startswith(w + '/') for w in ws)


def is_exception(norm):
    return any(r.match(norm) for r in EXCEPTIONS)


def split_segments(cmd, posix=True):
    """Podzial na segmenty po &&, ||, ;, |, nowej linii - poza cudzyslowami.
    Split on &&, ||, ;, |, newline outside quotes only."""
    segs, buf, quote, i = [], [], None, 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            buf.append(c)
            if posix and c == '\\' and quote == '"' and i + 1 < len(cmd):
                buf.append(cmd[i + 1])
                i += 1
            elif c == quote:
                quote = None
        elif c in ('"', "'"):
            quote = c
            buf.append(c)
        elif posix and c == '\\' and i + 1 < len(cmd):
            buf.append(c + cmd[i + 1])
            i += 1
        elif cmd.startswith(('&&', '||'), i):
            segs.append(''.join(buf)); buf = []
            i += 1
        elif c in ';|\n':
            segs.append(''.join(buf)); buf = []
        else:
            buf.append(c)
        i += 1
    segs.append(''.join(buf))
    return [s for s in segs if s.strip()]


def command_positions(cmd, posix=True):
    """Zbior tokenow bedacych nazwa programu / set of tokens in command position."""
    progs = set()
    for seg in split_segments(cmd, posix):
        try:
            toks = shlex.split(seg, posix=posix)
        except ValueError:
            toks = seg.split()
        while toks and toks[0] in ('&', 'sudo', 'time', 'xargs', 'exec'):
            toks = toks[1:]
        if toks:
            progs.add(toks[0])
    return progs


def paths_from_command(cmd, cwd, posix):
    # Bash: posix (rozwiazuje "Program\ Files"); PowerShell: non-posix (zachowuje C:\)
    try:
        tokens = shlex.split(cmd, posix=posix)
    except ValueError:
        tokens = cmd.split()
    raw = set(PATH_TOKEN_RE.findall(cmd))
    for tok in tokens:
        t = tok.strip('"\'')
        if PATH_TOKEN_RE.match(t):
            raw.add(t)  # caly argument = sciezka (moze zawierac spacje) / whole argument is a path
        raw.update(PATH_TOKEN_RE.findall(t))  # sciezki w napisach, np. python -c "open('C:/x')"
    norms = {normalize(t, cwd) for t in raw}
    # fragment ucietej na spacji sciezki ("c:/program" z "c:/program files/x") -> pomin
    norms = {n for n in norms if not any(o.startswith(n + ' ') for o in norms)}
    progs = {normalize(p, cwd) for p in command_positions(cmd, posix)
             if PATH_TOKEN_RE.match(p.strip('"\''))}
    return [n for n in norms if not (n in progs and n.startswith(EXEC_PREFIXES))]


# Zagladanie do uruchamianych skryptow / inspecting scripts being run
INTERPRETERS = {'python', 'python3', 'py', 'pythonw', 'node', 'deno', 'bun', 'tsx', 'ts-node',
                'pwsh', 'powershell', 'bash', 'sh', 'zsh', 'ruby', 'perl', 'cmd', 'uv'}
SCRIPT_EXT_RE = re.compile(r'\.(py|pyw|js|mjs|cjs|ts|ps1|psm1|sh|bash|rb|pl|bat|cmd)$', re.I)
SCRIPT_MAX_BYTES = 1_000_000
# Sciezki wyliczane w kodzie (nie widac ich jako tekst) -> profil uzytkownika / computed profile paths
DYNAMIC_RE = re.compile(
    r'Path\.home\(\)|expanduser\(|os\.environ(?:\.get)?\s*[\[(]\s*[\'"](?:USERPROFILE|APPDATA|LOCALAPPDATA|HOME)'
    r'|os\.getenv\(\s*[\'"](?:USERPROFILE|APPDATA|LOCALAPPDATA|HOME)'
    r'|%(?:APPDATA|LOCALAPPDATA)%|\$env:(?:APPDATA|LOCALAPPDATA)\b'
    r'|os\.homedir\(\)|homedir\(\)|process\.env\.(?:HOME|USERPROFILE|APPDATA|LOCALAPPDATA)\b'
    r'|GetFolderPath\(|\[Environment\]::GetEnvironmentVariable\(\s*[\'"](?:USERPROFILE|APPDATA)',
    re.I)


def to_os_path(norm):
    return norm.replace('/', os.sep)


def scripts_from_command(cmd, cwd, posix):
    """Pliki skryptow uruchamiane przez komende / script files the command executes."""
    found = []
    for seg in split_segments(cmd, posix):
        try:
            toks = shlex.split(seg, posix=posix)
        except ValueError:
            toks = seg.split()
        toks = [t.strip('"\'') for t in toks]
        while toks and (re.match(r'^\w+=', toks[0]) or toks[0] in ('&', 'sudo', 'time', 'exec', '.')):
            toks = toks[1:]
        if toks and toks[0] == 'timeout' and len(toks) > 2:
            toks = toks[2:]
        if not toks:
            continue
        prog = re.sub(r'\.exe$', '', toks[0].replace('\\', '/').rsplit('/', 1)[-1], flags=re.I).lower()
        cands = []
        if SCRIPT_EXT_RE.search(toks[0]):
            cands.append(toks[0])                          # ./x.sh, .\x.ps1
        elif prog in INTERPRETERS:
            rest = toks[1:]
            if prog == 'uv' and rest[:1] == ['run']:
                rest = rest[1:]
            if any(r in ('-c', '-e', '-Command', '-command', '--eval', '-m') for r in rest[:3]):
                rest = []                                  # kod inline/modul: sprawdza go analiza komendy
            for r in rest:
                if r.lower() in ('-file', '-f'):
                    continue
                if SCRIPT_EXT_RE.search(r):
                    cands.append(r)
                    break
        for c in cands:
            p = to_os_path(normalize(c, cwd))
            if os.path.isfile(p):
                found.append((c, p))
    return found


def inspect_script(path, cwd, ws):
    """Powody ASK wynikajace z zawartosci skryptu / ASK reasons from script contents."""
    reasons = []
    try:
        if os.path.getsize(path) > SCRIPT_MAX_BYTES:
            return ['skrypt za duzy do sprawdzenia / script too large to inspect: ' + path]
        with open(path, 'rb') as f:
            text = f.read().decode('utf-8', errors='replace')
    except OSError:
        return []
    name = os.path.basename(path)
    norms = {normalize(t, cwd) for t in set(PATH_TOKEN_RE.findall(text))}
    norms = {n for n in norms if not any(o.startswith(n + ' ') for o in norms)}
    outside = sorted(n for n in norms if not is_inside(n, ws) and not is_exception(n))
    if outside:
        reasons.append(f'skrypt {name}: sciezki poza katalogami roboczymi / script paths outside workspaces: '
                       + ', '.join(outside[:3]))
    if DYNAMIC_RE.search(text):
        reasons.append(f'skrypt {name}: dostep do profilu uzytkownika (sciezka wyliczana) / user profile access')
    # Celowo bez .env i usuwania w tresci skryptu: narzedzia projektow czytaja wlasny .env i sprzataja
    # pliki tymczasowe. Deliberately no .env/deletion checks inside scripts (too many false alarms).
    return reasons


def decide(data):
    tool = data.get('tool_name', '')
    ti = data.get('tool_input') or {}
    cwd = (data.get('cwd') or os.getcwd()).replace('\\', '/')
    ws = workspaces(cwd)
    reasons = []
    paths = []

    if tool in ('Read', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit'):
        p = ti.get('file_path') or ti.get('notebook_path')
        if p:
            paths.append(normalize(p, cwd))
            if SECRET_RE.search(p.replace('\\', '/').rsplit('/', 1)[-1]):
                reasons.append('plik z sekretami (.env) / secrets file')
    elif tool in ('Grep', 'Glob'):
        paths.append(normalize(ti.get('path') or cwd, cwd))
        target = ' '.join(str(ti.get(k) or '') for k in ('path', 'glob', 'pattern'))
        if tool == 'Glob' or ti.get('path') or ti.get('glob'):
            if SECRET_RE.search(target.replace('\\', '/')):
                reasons.append('plik z sekretami (.env) / secrets file')
    elif tool in ('Bash', 'PowerShell'):
        cmd = ti.get('command') or ''
        if DELETE_RE.search(cmd):
            reasons.append('usuwanie plikow / file deletion')
        if SECRET_RE.search(cmd):
            reasons.append('plik z sekretami (.env) / secrets file')
        paths.extend(paths_from_command(cmd, cwd, posix=(tool == 'Bash')))
        if DYNAMIC_RE.search(cmd):
            reasons.append('dostep do profilu uzytkownika (sciezka wyliczana) / user profile access')
        for _, spath in scripts_from_command(cmd, cwd, posix=(tool == 'Bash')):
            reasons.extend(inspect_script(spath, cwd, ws))
        if not is_inside(normalize(cwd, cwd), ws) and not is_exception(normalize(cwd, cwd)):
            paths.append(normalize(cwd, cwd))

    outside = sorted({p for p in paths if not is_inside(p, ws) and not is_exception(p)
                      and not (tool == 'Read' and any(r.match(p) for r in READ_EXCEPTIONS))})
    if outside:
        reasons.append('poza katalogami roboczymi / outside workspaces: ' + ', '.join(outside[:5]))
    return reasons, outside


def log(entry):
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
        with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except OSError:
        pass


def emit(decision, reason):
    sys.stdout.write(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': decision,
        'permissionDecisionReason': 'path_guard: ' + reason,
    }}, ensure_ascii=False))


def main():
    raw = sys.stdin.buffer.read().decode('utf-8', errors='replace')
    try:
        data = json.loads(raw)
        hit = hard_deny(data)
        reasons, _ = ([], []) if hit else decide(data)
    except Exception as e:  # fail-open, ale z logiem / fail-open, logged
        log({'ts': datetime.now().isoformat(timespec='seconds'), 'error': repr(e)})
        return 0
    if not hit and not reasons:
        return 0
    ti = data.get('tool_input') or {}
    decision = 'deny' if hit else 'ask'
    why = ['plik z sekretami / secret file: ' + hit] if hit else reasons
    log({'ts': datetime.now().isoformat(timespec='seconds'), 'session': data.get('session_id'),
         'tool': data.get('tool_name'),
         'target': (ti.get('command') or ti.get('file_path') or ti.get('path') or '')[:300],
         'decision': decision, 'reasons': why})
    emit(decision, '; '.join(why))
    return 0


if __name__ == '__main__':
    sys.exit(main())
