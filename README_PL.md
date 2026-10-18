# 🛡️ agent-under-control — hamulce dla Claude Code na Windows

[![Claude Code](https://img.shields.io/badge/Claude_Code-hooki_%2B_agent-D97757)]()
[![Platforma](https://img.shields.io/badge/Windows_11-testowane-0078D6)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)]()
[![Testy](https://img.shields.io/badge/Testy-47%2F47-success)](tests/cases.json)
[![Ścieżki](https://img.shields.io/badge/Instalacja-skryptem_%7C_r%C4%99cznie-blueviolet)]()
[![Licencja](https://img.shields.io/badge/Licencja-MIT-F1C40F)](LICENSE)

> 🎯 Dałeś agentowi AI dostęp do swojej pracy. Te hooki decydują, czego może dotknąć bez pytania, na co potrzebuje
> Twojego „tak”, a czego nie przeczyta nigdy — nawet przez shell. 🇬🇧 [English version](README.md)

![~/.claude — co jest w środku i kiedy działa](docs/claude-dir-map_pl.svg)

## 🤔 Po co

Claude Code ma dobry system uprawnień. W praktyce i tak przeciekają trzy rzeczy:

1. **W trybie auto `ask` nie zawsze trafia do Ciebie.** Zwykłe prośby o zgodę rozstrzyga klasyfikator trybu auto i oczywiste
   zatwierdza sam. Twardą blokadą jest tylko `deny`. `ask` zwrócone przez *hook* trafia do człowieka, także w trybie auto:
   tak mówi dokumentacja i tak wyszło w moim pomiarze `decision_log.py` (17–18.10.2026), gdzie żadne `ask` z hooka nie przeszło
   bez okienka. Czyli: `ask` z hooka to „zapytaj mnie”, a `deny` to „nigdy”.
2. **`deny Read(...)` to reguła dla narzędzia Read.** Dla polecenia w shellu, np. `cat ~/.ssh/id_ed25519`, nie można
   na niej polegać — dlatego hook sprawdza sam tekst polecenia.
3. **Hook, który się nie uruchomi, znika po cichu.** Hook wołany gołym `python` przestaje działać po zmianie PATH
   i nikt tego nie zauważa, bo błąd hooka nie blokuje narzędzia. Tu łatą jest pełna ścieżka Pythona, testy i puls —
   każde wywołanie zostawia linię w logu, więc cisza przy pracującym agencie daje alarm (`tools/split_report.py`).

To repozytorium zamyka te trzy luki: trzy małe hooki (dwa strażniki, jeden tylko loguje), raport, jeden agent tylko do odczytu i szkielet ustawień.
Powstało z audytu działającej konfiguracji (praca DBA Oracle/PostgreSQL i produkcja wideo z Claude Code).

## 📦 Zawartość

| Ścieżka | Co robi |
|---|---|
| [`hooks/path_guard.py`](hooks/path_guard.py) | hook `PreToolUse` dla wszystkich narzędzi plikowych i obu shelli: **deny** dla plików z sekretami, **ask** poza katalogami roboczymi i przed każdym usuwaniem |
| [`hooks/path_guard.config.example.json`](hooks/path_guard.config.example.json) | katalogi robocze, miejsce logu, dodatkowe wzorce deny |
| [`hooks/decision_log.py`](hooks/decision_log.py) | hook tylko do logowania: okienko zgody, odmowa trybu auto, wykonanie narzędzia — do podziału „auto vs człowiek” i pulsu |
| [`tools/split_report.py`](tools/split_report.py) | raport: kto rozstrzygnął wywołania i czy `path_guard` nie milczał |
| [`hooks/readonly_bash_guard.py`](hooks/readonly_bash_guard.py) | biała lista dla Bash: tylko polecenia do odczytu (`git log/show/diff`, `grep`, `cat`…) |
| [`agents/docs-auditor.md`](agents/docs-auditor.md) | subagent (po angielsku) sprawdzający, czy dokumentacja zgadza się z kodem; jego Bash pilnuje hook wyżej |
| [`settings/settings.example.json`](settings/settings.example.json) | reguły `deny` / `ask` i podpięcie hooków (z pełną ścieżką Pythona) |
| [`tests/`](tests) | 47 testów: wejście hooka → oczekiwana decyzja, logi i raport; działa bez Claude Code |
| [`install/install.ps1`](install/install.ps1) | instalator z `-DryRun`, kopią zapasową i scaleniem `settings.json` bez nadpisywania |
| [`docs/AUDIT_CHECKLIST_PL.md`](docs/AUDIT_CHECKLIST_PL.md) | jak przejrzeć własną konfigurację Claude Code |

## ⚖️ Jak decyduje `path_guard`

| # | Sytuacja | Decyzja |
|---|---|---|
| 0 | prywatny klucz SSH (nie `.pub`), dane logowania Claude/Gemini/Docker/DBeaver/pgAdmin, Twoje wzorce `extra_hard_deny` — w **dowolnym** narzędziu | **deny** |
| 1 | ścieżka poza katalogami roboczymi (Read, Edit, Grep, ścieżka w poleceniu shella, ścieżka w uruchamianym skrypcie) | **ask** |
| 2 | usuwanie plików (`rm`, `Remove-Item`, `del`, `git clean`, `git reset --hard`, `shutil.rmtree`…), także w katalogu roboczym | **ask** |
| 2a | pliki `.env` (szablony typu `.env.example` są w porządku) | **ask** |
| 2b | uruchamiany skrypt ze ścieżkami spoza katalogów roboczych albo wyliczający ścieżki profilu (`Path.home()`, `%APPDATA%`) | **ask** |
| 3 | wszystko inne | bez decyzji — działają zwykłe uprawnienia Claude Code |

Wyjątki: pamięć, plany i scratchpad samego Claude Code; **odczyt** `~/.claude/rules`. Każde `ask` i `deny` trafia do logu
JSONL. Błąd hooka nigdy nie blokuje pracy (fail-open) — zostaje zapisany w logu.

## 🧮 Kto zatwierdza? Podział „auto vs człowiek” i puls

`path_guard` działa **przed** decyzją, więc sam nie wie, kto potem odpowiedział na `ask`. Dlatego:

- `path_guard` zapisuje do `events_log` linię przy **każdym** wywołaniu (`pass` / `ask` / `deny`) z `tool_use_id`
  i `permission_mode`; `audit_log` jak dotąd ma tylko `ask` / `deny`;
- [`decision_log.py`](hooks/decision_log.py) (asynchronicznie, nigdy nie blokuje) dopisuje do `events_log` zdarzenia
  `PermissionRequest` (okienko dla człowieka), `PermissionDenied` (odmowa trybu auto), `PostToolUse` / `PostToolUseFailure`
  (narzędzie się wykonało);
- [`tools/split_report.py`](tools/split_report.py) łączy je i liczy: człowiek zatwierdził / odrzucił, tryb auto odmówił,
  bez okienka (reguła allow **albo** klasyfikator — tego nie da się rozróżnić), `ask` bez okienka;
- **puls:** narzędzie wykonane, a `path_guard` go nie widział (seria ≥ 3) → `ALARM`, kod wyjścia 1. Hook, który przestał się
  uruchamiać, przestaje być cichy.

```powershell
python tools/split_report.py --log "$HOME/.claude/logs/path_guard_events.jsonl" --since 2026-10-17
```

Ograniczenie: `PermissionRequest` nie ma `tool_use_id`; okienko jest łączone z wywołaniem po sesji, narzędziu, skrócie wejścia
i czasie. Pomysł na puls: Kyle Bartlett w komentarzu pod postem o tym repo.

## 🚀 Instalacja

### 🤖 Ścieżka skryptowa (automatycznie)

Wymagania: Windows 10/11, PowerShell 7+, Python 3.10+.

```powershell
git clone https://github.com/krzysztof-i-cabaj/agent-under-control
cd agent-under-control
pwsh install/install.ps1 -DryRun     # podgląd: co zostanie skopiowane, dodane, zostawione - nic nie zmienia
pwsh install/install.ps1             # instalacja (kopia zapasowa, kopiowanie, scalenie, testy)
```

Co robi instalator:

1. znajduje Pythona (odrzuca alias z Microsoft Store) albo bierze `-Python "C:/sciezka/python.exe"`;
2. kopiuje istniejące pliki do `~/.claude/backups/agent-under-control-<znacznik czasu>/`;
3. kopiuje trzy hooki do `~/.claude/hooks/` i zapisuje agenta z wpisanymi pełnymi ścieżkami;
4. tworzy `~/.claude/path_guard.config.json` z przykładu **tylko wtedy, gdy go nie ma**;
5. **scala** `settings.json`: dodaje brakujące reguły `deny`/`ask` i wpis hooka; resztę zostawia; niczego nie dubluje;
6. uruchamia testy.

Potem ustaw `workspaces` w `~/.claude/path_guard.config.json` i uruchom **nową** sesję Claude Code.
Inny katalog Claude: `-ClaudeDir D:\inny\.claude`.

### ✋ Ścieżka ręczna

1. Skopiuj `hooks/path_guard.py`, `hooks/decision_log.py` i `hooks/readonly_bash_guard.py` do `%USERPROFILE%\.claude\hooks\`.
2. Skopiuj `hooks/path_guard.config.example.json` jako `%USERPROFILE%\.claude\path_guard.config.json` i ustaw `workspaces`.
3. Skopiuj `agents/docs-auditor.md` do `%USERPROFILE%\.claude\agents\` i zamień `__PYTHON__` na pełną ścieżkę do
   `python.exe`, a `__HOOKS_DIR__` na `C:/Users/<ty>/.claude/hooks` (ukośniki do przodu).
4. Otwórz `%USERPROFILE%\.claude\settings.json` i dodaj z `settings/settings.example.json`: brakujące reguły `deny` i `ask`
   oraz wpisy `hooks` — `PreToolUse` (path_guard) i `PermissionRequest`, `PermissionDenied`, `PostToolUse`, `PostToolUseFailure`
   (decision_log) — w `command` te same dwie zamiany. Pozostałe ustawienia zostaw.
5. Sprawdź: `python tests/run_tests.py` → `47/47 passed`. Uruchom nową sesję Claude Code.

## ⚙️ Konfiguracja

`path_guard` czyta pierwszy znaleziony plik: zmienna środowiskowa `PATH_GUARD_CONFIG`, `path_guard.config.json`
obok hooka, katalog wyżej albo w `~/.claude/`.

```json
{
  "workspaces": ["D:/praca", "~/projekty"],
  "audit_log": "~/.claude/logs/path_guard_audit.jsonl",
  "events_log": "~/.claude/logs/path_guard_events.jsonl",
  "extra_hard_deny": ["\\.aws[/\\\\]credentials", "\\.kube[/\\\\]config"]
}
```

Bez konfiguracji jedynym katalogiem roboczym jest katalog projektu sesji, a log trafia do `~/.claude/logs/`.

## 🧪 Testy

```powershell
python tests/run_tests.py
```

Każdy przypadek w [`tests/cases.json`](tests/cases.json) podaje hookowi ten sam JSON, który podałby Claude Code, i sprawdza
decyzję. Dodając regułę, dodaj przypadek.

## ↩️ Wycofanie

Instalator zapisuje każdy zmieniany plik w `~/.claude/backups/agent-under-control-<znacznik czasu>/`. Aby cofnąć:
skopiuj te pliki z powrotem do `~/.claude/` (oraz `hooks/`, `agents/`), usuń hooki i agenta, jeśli były nowe,
i uruchom nową sesję Claude Code. Przy instalacji ręcznej: usuń wpisy `path_guard.py` i `decision_log.py` z `hooks` w `settings.json`.

## ⚠️ Ograniczenia — przeczytaj, zanim zaufasz

- **To nie jest sandbox.** To zabezpieczenie przed pomyłkami uczciwego agenta, a nie granica bezpieczeństwa przed wrogim.
  Ścieżka składana w locie, zakodowane polecenie albo nieznane narzędzie przejdą.
- **Windows-first.** Ścieżki są normalizowane po windowsowemu (`C:/…`, Git Bash `/c/…`). Linux i macOS nie były testowane.
- **Fail-open z założenia.** Gdy hook się wysypie, praca idzie dalej, a błąd trafia do logu. Zaglądaj do logu co jakiś czas.
- **Maskowania sekretów w wynikach narzędzi** tu nie ma — wymaga rozszerzenia Claude Code, pokazanego w serii.

## 🎬 Seria

Te zabezpieczenia krok po kroku pokazuje seria **„Agent pod kontrolą”** (po polsku, z napisami EN)
na kanale YouTube [KCB Consulting](https://www.youtube.com/@KCB_Consulting).

## 👤 Autor

Krzysztof Cabaj · KCB Consulting · Licencja: [MIT](LICENSE)
