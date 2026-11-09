# AntRoute - PoC

AntRoute planuje jednodniową trasę pieszą po Manhattanie, która omija tłok. Model to Time-Dependent Orienteering Problem z karą za tłok. Solver to Ant Colony System z antyferomonem i ponownym planowaniem po zdarzeniu.

- Dokumentacja produktu: [`docs/`](docs/README.md).
- Zakres prac PoC: [`docs/11-zakres-prac-v1.md`](docs/11-zakres-prac-v1.md).
- Wyniki eksperymentów: [`results/SUMMARY.md`](results/SUMMARY.md).

## Instalacja

Projekt używa Python 3.12 i [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Dane

Pliki surowe nie są w repozytorium (brak licencji zbioru, docs/02-dane.md).

1. Pobierz `dataset_tsmc2014.zip` ze strony zbioru [Foursquare Dataset](https://sites.google.com/site/yangdingqi/home/foursquare-dataset). Rozpakuj `dataset_TSMC2014_NYC.txt` do `data/raw/`.
2. Pobierz wielokąt Manhattanu z NYC Open Data do `data/raw/manhattan.geojson`:

```bash
curl -L -o data/raw/manhattan.geojson \
  "https://data.cityofnewyork.us/resource/gthc-hcne.geojson?boroname=Manhattan"
```

## Uruchomienie

Cały potok (dane → profile → eksperymenty → raport) jednym poleceniem:

```bash
uv run python run_all.py                                   # pełne wyniki w results/
uv run python run_all.py --seeds 3 --out runs/quick --no-cpsat   # szybkie sprawdzenie
```

Kroki osobno:

```bash
uv run python -m antroute.data.prepare                      # WP1: czas lokalny, Manhattan, kategorie
uv run python -m antroute.model.profiles --bootstrap 20     # WP2: profile P_c(h), wagi w_i
uv run python -m antroute.model.instance --n 50             # WP3: zapis instancji
uv run python -m antroute.solvers.aco --n 50 --start 08:00 --budget 480 --seed 1 \
    --scenario antroute/scenario/examples/all_events.yaml --warm   # jedna trasa
uv run python -m antroute.experiments.run E1 E2 E4          # WP9: eksperymenty
uv run python -m antroute.report.summary                    # WP10: results/SUMMARY.md
```

Testy i lint:

```bash
uv run pytest
uv run ruff check antroute tests
NUMBA_DISABLE_JIT=1 uv run pytest tests/test_evaluate.py --cov=antroute.model.evaluate
```

## Struktura

```text
antroute/
├── data/
│   └── prepare.py          # wczytanie TSV, czas lokalny, filtr Manhattanu
├── model/
│   ├── profiles.py         # profile tłoku P_c(h), wygładzanie, wagi w_i, bootstrap
│   ├── instance.py         # wybór N miejsc (losowanie warstwowe), macierz czasów przejścia
│   ├── evaluate.py         # jedyna funkcja oceny: C_i(t), S_i(a_i), t_ij(t), ograniczenia
│   └── problem.py          # instancja + persona + budżet + zdarzenia znane planiście
├── scenario/
│   └── events.py           # zdarzenia YAML: crowd_surge, closure, traffic
├── solvers/
│   ├── aco.py              # ACS-A, ACS-B, antyferomon, warianty, przeszukiwanie lokalne
│   ├── replan.py           # ponowne planowanie po ogłoszeniu zdarzenia (zimny i ciepły start)
│   ├── greedy.py           # metoda porównawcza
│   ├── random_route.py     # metoda porównawcza
│   ├── brute.py            # pełny przegląd (N <= 8)
│   └── exact.py            # CP-SAT (best_known)
├── experiments/            # konfiguracje YAML E1-E12, runner równoległy
└── report/                 # wykresy matplotlib i results/SUMMARY.md
```

Wszystkie parametry są w `config/default.yaml`.
