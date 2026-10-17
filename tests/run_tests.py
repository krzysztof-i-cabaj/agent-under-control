# ==============================================================================
# Tytul:        run_tests.py
# Opis:         Testy hookow bez Claude Code: podaje wejscie z cases.json na stdin
#               i porownuje decyzje (allow/ask/deny) z oczekiwana
# Description [EN]: Tests the hooks without Claude Code: feeds inputs from cases.json
#               on stdin and compares the decision (allow/ask/deny) with the expected one
#
# Autor:        KCB Kris
# Data:         2026-10-17
# Wersja:       1.1 (testy logow, decision_log.py i split_report.py / log, decision_log and report tests)
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
import tempfile
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


def run(args, payload, env):
    p = subprocess.run([sys.executable, *args], input=json.dumps(payload).encode('utf-8') if payload is not None else b'',
                       capture_output=True, env=env, timeout=30)
    return p.returncode, p.stdout.decode('utf-8', errors='replace')


def read_jsonl(path):
    if not os.path.isfile(path):
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def log_checks(base_env):
    """Logi path_guard 2.1, decision_log.py i split_report.py na tymczasowym katalogu / temp dir."""
    tmp = tempfile.mkdtemp(prefix='auc-test-')
    audit, events = os.path.join(tmp, 'audit.jsonl'), os.path.join(tmp, 'events.jsonl')
    cfg = os.path.join(tmp, 'config.json')
    Path(cfg).write_text(json.dumps({'workspaces': [CWD], 'audit_log': audit, 'events_log': events}), encoding='utf-8')
    env = dict(base_env, PATH_GUARD_CONFIG=cfg)
    pg, dl = [str(HOOKS / 'path_guard.py')], [str(HOOKS / 'decision_log.py')]
    report = [str(ROOT / 'tools' / 'split_report.py'), '--log', events]
    s = {'session_id': 's1', 'permission_mode': 'auto', 'cwd': CWD}
    inside, outside = {'file_path': CWD + '/a.txt'}, {'file_path': 'C:/Windows/win.ini'}
    rows = []

    run(pg, dict(s, tool_name='Read', tool_input=inside, tool_use_id='t1'), env)          # pass
    run(pg, dict(s, tool_name='Read', tool_input=outside, tool_use_id='t2'), env)         # ask
    ev, au = read_jsonl(events), read_jsonl(audit)
    rows.append(('log', 'pass -> events_log, not audit_log', 'yes',
                 'yes' if [e['decision'] for e in ev] == ['pass', 'ask'] and [e['decision'] for e in au] == ['ask']
                 else 'no'))
    rows.append(('log', 'tool_use_id + permission_mode logged', 'yes',
                 'yes' if ev and ev[0].get('tool_use_id') == 't1' and ev[0].get('mode') == 'auto' else 'no'))

    run(dl, dict(s, hook_event_name='PostToolUse', tool_name='Read', tool_input=inside, tool_use_id='t1'), env)
    run(dl, dict(s, hook_event_name='PermissionRequest', tool_name='Read', tool_input=outside), env)
    run(dl, dict(s, hook_event_name='PostToolUse', tool_name='Read', tool_input=outside, tool_use_id='t2'), env)
    run(pg, dict(s, tool_name='Bash', tool_input={'command': 'cat C:/x/y'}, tool_use_id='t3'), env)   # ask
    run(dl, dict(s, hook_event_name='PermissionDenied', tool_name='Bash', tool_input={'command': 'cat C:/x/y'},
                 tool_use_id='t3', reason='[Data Exfiltration]'), env)
    code, out = run(dl, None, env)                                                          # smieci / garbage
    rows.append(('decision_log.py', 'garbage stdin: exit 0, no output', 'yes',
                 'yes' if code == 0 and not out.strip() else 'no'))
    code, out = run(report, None, env)
    want = {'czlowiek zatwierdzil': 1, 'bez okienka: allow albo auto': 1, 'tryb auto odmowil': 1}
    got_ok = all(any(line.strip().startswith(k) and line.split()[-2] == str(v) for line in out.splitlines())
                 for k, v in want.items())
    rows.append(('split_report.py', 'human / no_prompt / auto_denied = 1/1/1', 'yes', 'yes' if got_ok else 'no'))
    rows.append(('split_report.py', 'no heartbeat alarm (exit 0)', 'yes', 'yes' if code == 0 else 'no'))

    for i in range(3):   # 3 wykonania Bash bez path_guard = cisza / 3 runs the guard never saw
        run(dl, dict(s, hook_event_name='PostToolUse', tool_name='Bash', tool_input={'command': f'echo {i}'},
                     tool_use_id=f'x{i}'), env)
    code, out = run(report, None, env)
    rows.append(('split_report.py', 'heartbeat alarm after 3 silent calls', 'yes',
                 'yes' if code == 1 and 'ALARM' in out else 'no'))
    return rows


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
    rows += log_checks(env)
    for hook, name, expect, got in rows:
        ok = expect == got
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'}  {hook:<24} {name:<42} expected={expect:<5} got={got}")
    print(f'\n{len(rows) - failed}/{len(rows)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
