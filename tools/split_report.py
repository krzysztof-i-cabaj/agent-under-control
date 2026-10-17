# ==============================================================================
# Tytul:        split_report.py
# Opis:         Raport z events_log: kto rozstrzygnal wywolania narzedzi (czlowiek / tryb auto /
#               hook / regula) oraz "puls" - wykonane narzedzia, przy ktorych path_guard milczal
# Description [EN]: Report from events_log: who resolved tool calls (human / auto mode / hook /
#               rule) and a heartbeat check - executed tools that path_guard never saw
#
# Autor:        KCB Kris
# Data:         2026-10-17
# Wersja:       1.0
# Konwencje:    README.md (sekcja "Kto zatwierdza?")
#
# Wymagania [PL]:    - Python 3.10+, tylko biblioteka standardowa; log z path_guard 2.1+ i decision_log.py
# Requirements [EN]: - Python 3.10+, standard library only; log from path_guard 2.1+ and decision_log.py
#
# Uzycie [PL]:       python tools/split_report.py [--log PLIK] [--since RRRR-MM-DD] [--gap N]
# Usage [EN]:        python tools/split_report.py [--log FILE] [--since YYYY-MM-DD] [--gap N]
# ==============================================================================
"""
Klasyfikacja kazdego PreToolUse z path_guard / classification of each path_guard PreToolUse:
  hook_deny            path_guard zwrocil deny
  auto_denied          PermissionDenied: odmowil klasyfikator trybu auto
  human_approved       bylo okienko (PermissionRequest) i narzedzie sie wykonalo
  human_rejected       bylo okienko, narzedzie sie nie wykonalo
  ask_no_prompt        path_guard: ask, okienka nie bylo, narzedzie sie wykonalo (sprzeczne z dokumentacja)
  no_prompt            pass, bez okienka, wykonane: regula allow ALBO klasyfikator (nie do rozroznienia)
  not_executed         brak wykonania i brak okienka (przerwane, blad walidacji, koniec sesji)
  pending              ostatnie 5 min logu bez wyniku: prawdopodobnie jeszcze trwa (nie liczone jako odrzucenie)
Puls / heartbeat: PostToolUse(Failure) dla narzedzia pilnowanego przez path_guard bez jego PreToolUse.
Ograniczenie: PermissionRequest nie ma tool_use_id - laczony po sesji + narzedziu + input_sha + czasie.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

GUARDED = {'Read', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'Grep', 'Glob', 'Bash', 'PowerShell'}
DEFAULT_LOG = os.path.join(os.path.expanduser('~'), '.claude', 'logs', 'path_guard_events.jsonl')
LABELS = {
    'human_approved': 'czlowiek zatwierdzil / human approved',
    'human_rejected': 'czlowiek odrzucil / human rejected',
    'auto_denied': 'tryb auto odmowil / auto mode denied',
    'ask_no_prompt': 'ask bez okienka, wykonane / ask, no prompt, ran',
    'no_prompt': 'bez okienka: allow albo auto / no prompt: allow or auto',
    'hook_deny': 'path_guard deny',
    'not_executed': 'niewykonane, bez okienka / not run, no prompt',
    'pending': 'w toku (ostatnie 5 min) / still running (last 5 min)',
}


def ts(e):
    return datetime.fromisoformat(e['ts'])


def load(path, since):
    events = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                e = json.loads(line)
                if since and e.get('ts', '') < since:
                    continue
                events.append(e)
            except ValueError:
                continue
    return events


def classify(events):
    pre, post, denied = {}, set(), set()
    prompts = defaultdict(list)        # (session, tool, sha) -> [czas okienka / prompt time]
    executed = []
    for e in events:
        ev, tid = e.get('event'), e.get('tool_use_id')
        if ev == 'PreToolUse' and tid and 'decision' in e:
            pre[tid] = e
        elif ev in ('PostToolUse', 'PostToolUseFailure') and tid:
            post.add(tid)
            executed.append(e)
        elif ev == 'PermissionDenied' and tid:
            denied.add(tid)
        elif ev == 'PermissionRequest':
            prompts[(e.get('session'), e.get('tool'), e.get('input_sha'))].append(ts(e))

    result = Counter()
    by_mode = defaultdict(Counter)
    log_end = max((ts(e) for e in events), default=None)
    for tid, e in sorted(pre.items(), key=lambda kv: kv[1]['ts']):
        key = (e.get('session'), e.get('tool'), e.get('input_sha'))
        t0 = ts(e)
        hit = next((p for p in prompts.get(key, []) if t0 <= p <= t0 + timedelta(minutes=10)), None)
        if hit is not None:
            prompts[key].remove(hit)   # jedno okienko = jedno wywolanie / one prompt per call
        if e['decision'] == 'deny':
            cls = 'hook_deny'
        elif tid not in post and tid not in denied and log_end and t0 > log_end - timedelta(minutes=5):
            cls = 'pending'
        elif tid in denied:
            cls = 'auto_denied'
        elif hit is not None:
            cls = 'human_approved' if tid in post else 'human_rejected'
        elif tid in post:
            cls = 'ask_no_prompt' if e['decision'] == 'ask' else 'no_prompt'
        else:
            cls = 'not_executed'
        result[cls] += 1
        by_mode[e.get('mode') or '?'][cls] += 1
    unmatched_prompts = sum(len(v) for v in prompts.values())
    return pre, executed, result, by_mode, unmatched_prompts


def heartbeat(pre, executed, gap):
    """Serie wykonanych narzedzi bez PreToolUse z path_guard / runs of executed calls the guard never saw."""
    runs, current = [], []
    for e in sorted(executed, key=lambda x: x['ts']):
        if e.get('tool') not in GUARDED:
            continue
        if e.get('tool_use_id') in pre:
            if len(current) >= gap:
                runs.append(current)
            current = []
        else:
            current.append(e)
    if len(current) >= gap:
        runs.append(current)
    return runs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--log', default=os.environ.get('PATH_GUARD_EVENTS_LOG', DEFAULT_LOG))
    ap.add_argument('--since', help='RRRR-MM-DD')
    ap.add_argument('--gap', type=int, default=3, help='alarm od N wywolan bez path_guard (domyslnie 3)')
    args = ap.parse_args()
    if not os.path.isfile(args.log):
        print(f'Brak logu / no log: {args.log}')
        return 2
    events = load(args.log, args.since)
    pre, executed, result, by_mode, unmatched = classify(events)
    total = sum(result.values())
    print(f'Log: {args.log}  zdarzen / events: {len(events)}  PreToolUse (path_guard): {total}\n')
    for cls, label in LABELS.items():
        n = result.get(cls, 0)
        pct = f'{100 * n / total:5.1f}%' if total else '   - '
        print(f'  {label:<56} {n:>7}  {pct}')
    print('\nWg trybu / by permission_mode:')
    for mode, c in sorted(by_mode.items()):
        print(f'  {mode:<18} ' + ', '.join(f'{k}={v}' for k, v in sorted(c.items())))
    print(f'\nOkienka bez PreToolUse path_guard (np. MCP) / prompts for unguarded tools: {unmatched}')
    runs = heartbeat(pre, executed, args.gap)
    silent = sum(len(r) for r in runs)
    print(f'\nPuls / heartbeat: serie >= {args.gap} wykonanych narzedzi bez path_guard: {len(runs)} ({silent} wywolan)')
    for r in runs[:10]:
        print(f'  ALARM {r[0]["ts"]} .. {r[-1]["ts"]}  {len(r)} x  sesja {str(r[0].get("session"))[:8]}')
    return 1 if runs else 0


if __name__ == '__main__':
    sys.exit(main())
