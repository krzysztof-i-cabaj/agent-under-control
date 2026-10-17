# ✅ Audyt konfiguracji Claude Code — checklista

[![Zakres](https://img.shields.io/badge/Zakres-ustawienia_%C2%B7_hooki_%C2%B7_skille_%C2%B7_pami%C4%99%C4%87-blue)]()
[![Tryb](https://img.shields.io/badge/Tryb-najpierw_tylko_odczyt-success)]()

> 🎯 Konfiguracja rośnie miesiącami: hooki, reguły, skille, pamięć, pluginy. Co jakiś czas sprawdź, czy nadal robi to,
> co myślisz. Zasada zero: **najpierw kopia, potem zmiana** — a w trakcie przeglądu nie zmieniaj niczego.
> 🇬🇧 [English version](AUDIT_CHECKLIST.md)

## 🔐 1. Uprawnienia i hooki

- [ ] `settings.json` to poprawny JSON; żadna reguła nie jest jednocześnie w `allow` i `deny`.
- [ ] Pliki z sekretami są w **`deny`**, nie w `ask` (w trybie auto zwykłe prośby o zgodę rozstrzyga klasyfikator, nie Ty).
- [ ] Sekrety są zablokowane także **w shellu**, nie tylko dla narzędzia Read (test: poproś agenta o `cat` testowego klucza).
- [ ] Log hooka **rośnie** razem z pracą agenta (cisza przy pracującym agencie = hook nie działa); `tools/split_report.py` bez `ALARM`.
- [ ] Każdy `command` hooka używa **pełnej ścieżki** do interpretera; każdy wołany skrypt istnieje.
- [ ] Każdy hook uruchomiony ręcznie z przykładowym JSON-em na stdin zwraca oczekiwaną decyzję.
- [ ] Hooki niepodpięte nigdzie (sieroty) są zarchiwizowane; stare `*.bak` nie leżą obok aktywnych plików.
- [ ] Agent „tylko do odczytu” naprawdę jest tylko do odczytu: sprawdź, co potrafią dozwolone komendy (`sed` umie zapisać
      plik i uruchomić program; `git grep -O` uruchamia program; `git -c` zmienia konfigurację).

## 🧩 2. Skille

- [ ] Każdy `SKILL.md` ma poprawny frontmatter YAML (ścisły parser) i `name` równe nazwie katalogu.
- [ ] Każdy `description` mówi, **kiedy** użyć skilla — i kiedy **nie** (nakładające się skille konkurują o tę samą prośbę).
- [ ] Brak duplikatów między skillami lokalnymi a zsynchronizowanymi z claude.ai.
- [ ] Kopie skilli z upstreamu są aktualne: porównaj ze źródłem **po** pullu.
- [ ] **Skille domenowe pisane z AI są zweryfikowane z oficjalną dokumentacją** — nazwy pakietów, widoków, kolumn,
      parametrów, wersje, licencje. Wygenerowany kod wygląda wiarygodnie, a może odwoływać się do obiektów, których nie ma.

## 🧠 3. Instrukcje i pamięć

- [ ] Pliki `CLAUDE.md` nie przeczą sobie nawzajem ani regułom; linki prowadzą do istniejących plików.
- [ ] Fakty w instrukcjach są aktualne (wersje, listy katalogów).
- [ ] Indeks pamięci bez sierot i martwych wpisów; wpisy krótkie; nic nie „czeka” na coś dawno zrobionego.
- [ ] Pamięć nie dubluje reguł; stałe zasady są w `CLAUDE.md` / regułach, nie w pamięci.
- [ ] Brak sekretów w pamięci i instrukcjach (albo, jeśli akceptujesz hasła LAB, maskowanie naprawdę je łapie).
- [ ] Kontrola kodowania: bez mojibake i znaków sterujących w żadnym z tych plików.

## 🔌 4. Pluginy, MCP, rozszerzenia

- [ ] Każdy włączony plugin jest zainstalowany i uwierzytelniony; żadna usługa nie jest skonfigurowana dwa razy (plugin + konektor).
- [ ] Wypisz aktywne serwery MCP z nazwy — wszystko, czego nie rozpoznajesz, wylatuje.
- [ ] Pull publicznego repozytorium sam niczego nie zmienia — sprawdź, co w konfiguracji naprawdę go **używa**.

## 🧾 5. Po przeglądzie

- [ ] Ustalenia w raporcie: `plik:linia | problem | waga | poprawka`; waga = błąd / ryzyko / porządek.
- [ ] Poprawki w pakietach, każdy: kopia → zmiana → weryfikacja (JSON się parsuje, test hooka przechodzi, skill się ładuje).
- [ ] Przenoś, nie kasuj; trzymaj kopię do następnego przeglądu.
