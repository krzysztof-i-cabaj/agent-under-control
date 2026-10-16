# ==============================================================================
# Tytul:        run_tests.py
# Opis:         Testy hookow bez Claude Code: podaje wejscie z cases.json na stdin
#               i porownuje decyzje (allow/ask/deny) z oczekiwana
# Description [EN]: Tests the hooks without Claude Code: feeds inputs from cases.json
#               on stdin and compares the decision (allow/ask/deny) with the expected one
#
# Autor:        KCB Kris
# Data:         2026-10-16
# Wersja:       1.0
# Konwencje:    README.md (sekcja Tests)
#
# Wymagania [PL]:    - Python 3.10+, tylko biblioteka standardowa
# Requirements [EN]: - Python 3.10+, standard library only
#
# Uzycie [PL]:       python tests/run_tests.py   (kod wyjscia 0 = wszystko OK)
# Usage [EN]:        python tests/run_tests.py   (exit code 0 = all passed)
# ==============================================================================
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / 'hooks'
CASES = json.loads((ROOT / 'tests' / 'cases.json').read_text(encoding='utf-8'))
CWD = 'C:/auc-test-ws'


def decision(script, payload, env):
    out = subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(payload).encode('utf-8'),
                         capture_output=True, env=env, timeout=30).stdout.decode('utf-8', errors='replace')
    if not out.strip():
        return 'allow'
    return json.loads(out)['hookSpecificOutput']['permissionDecision']


def main():
    env = dict(os.environ, PATH_GUARD_CONFIG=str(ROOT / 'tests' / 'test.config.json'))
    env.pop('CLAUDE_PROJECT_DIR', None)
    failed = 0
    rows = [('path_guard.py', c['name'], c['expect'],
             decision('path_guard.py', {'tool_name': c['tool'], 'tool_input': c['input'], 'cwd': CWD}, env))
            for c in CASES['path_guard']]
    rows += [('readonly_bash_guard.py', c['name'], c['expect'],
              decision('readonly_bash_guard.py', {'tool_name': 'Bash', 'tool_input': {'command': c['command']}}, env))
             for c in CASES['readonly_bash_guard']]
    for hook, name, expect, got in rows:
        ok = expect == got
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'}  {hook:<24} {name:<42} expected={expect:<5} got={got}")
    print(f'\n{len(rows) - failed}/{len(rows)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
