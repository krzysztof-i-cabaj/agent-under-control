# ==============================================================================
# Tytul:        decision_log.py
# Opis:         Hook Claude Code tylko do logowania: co stalo sie po PreToolUse - okienko zgody
#               (PermissionRequest), odmowa trybu auto (PermissionDenied), wykonanie narzedzia
#               (PostToolUse / PostToolUseFailure). Nigdy nie zwraca decyzji.
# Description [EN]: Log-only Claude Code hook: what happened after PreToolUse - permission
#               prompt, auto-mode denial, tool executed or failed. Never returns a decision.
#
# Autor:        KCB Kris
# Data:         2026-10-17
# Wersja:       1.0
# Konwencje:    README.md (sekcja "Kto zatwierdza?"); ten sam plik konfiguracji co path_guard
#
# Wymagania [PL]:    - Python 3.10+; wpisy hooks.PermissionRequest / PermissionDenied / PostToolUse /
#                      PostToolUseFailure w ~/.claude/settings.json (settings/settings.example.json)
# Requirements [EN]: - Python 3.10+; hook entries listed above in ~/.claude/settings.json
#
# Uzycie [PL]:       Uruchamia go Claude Code (JSON na stdin). Raport: python tools/split_report.py
# Usage [EN]:        Run by Claude Code (JSON on stdin). Report: python tools/split_report.py
# ==============================================================================
"""
Kazde zdarzenie -> jedna linia w events_log (ten sam plik co path_guard).
Every event -> one line in events_log (the same file path_guard writes to).

Laczenie z PreToolUse / correlation: tool_use_id (PostToolUse, PostToolUseFailure, PermissionDenied);
PermissionRequest nie ma tool_use_id -> session + tool + input_sha (skrot tool_input, jak w path_guard).
Bledy sa polykane: hook nie moze przeszkadzac w pracy. Errors are swallowed: never disturbs work.
"""
import hashlib
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = 'decision_log 1.0'


def load_config():
    """Ta sama kolejnosc co path_guard / same lookup order as path_guard."""
    for p in (os.environ.get('PATH_GUARD_CONFIG'),
              os.path.join(HERE, 'path_guard.config.json'),
              os.path.join(os.path.dirname(HERE), 'path_guard.config.json'),
              os.path.join(os.path.expanduser('~'), '.claude', 'path_guard.config.json')):
        if p and os.path.isfile(p):
            with open(p, encoding='utf-8') as f:
                return json.load(f)
    return {}


def main():
    try:
        config = load_config()
        events_log = os.path.expanduser(config.get('events_log')
                                        or os.path.join('~', '.claude', 'logs', 'path_guard_events.jsonl'))
        data = json.loads(sys.stdin.buffer.read().decode('utf-8', errors='replace'))
        ti = data.get('tool_input') or {}
        target = ti.get('command') or ti.get('file_path') or ti.get('path') or ti.get('pattern') or ''
        entry = {
            'ts': datetime.now().isoformat(timespec='milliseconds'),
            'event': data.get('hook_event_name'),
            'hook': VERSION,
            'session': data.get('session_id'),
            'tool_use_id': data.get('tool_use_id'),
            'mode': data.get('permission_mode'),
            'tool': data.get('tool_name'),
            'input_sha': hashlib.sha1(json.dumps(ti, sort_keys=True, ensure_ascii=False)
                                      .encode('utf-8')).hexdigest()[:12],
            'target': str(target)[:int(config.get('pass_target_chars', 120))],
        }
        for key in ('reason', 'is_interrupt', 'duration_ms'):     # PermissionDenied / PostToolUse(Failure)
            if key in data:
                entry[key] = data[key]
        if 'error' in data:
            entry['error'] = str(data['error'])[:200]
        os.makedirs(os.path.dirname(events_log), exist_ok=True)
        with open(events_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:   # tylko log; nigdy nie blokuj / log only; never block
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
