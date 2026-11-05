# 7. Wizualizacja i symulacja

AntRoute pokazuje stan kolonii na mapie. Są dwie osie czasu i dwa tryby wizualizacji.

| Oś czasu | Co się zmienia | Ile trwa | Tryb |
| --- | --- | --- | --- |
| Iteracje algorytmu | feromon, trasy mrówek, najlepsza trasa | sekundy obliczeń | „Jak myśli kolonia” |
| Godziny symulowanego dnia | pozycja użytkownika, tłok, zdarzenia | np. 08:00–20:00 | „Jak mija dzień” |

Jedno uruchomienie ACS planuje cały dzień naraz. Feromon zmienia się wtedy z iteracji na iterację, a nie z godziny na godzinę. Widok „co godzinę” wymaga pętli symulacji dnia (punkt 7.3).

## 7.1. Elementy mapy

| Element | Znaczenie |
| --- | --- |
| Grubość i kolor krawędzi | feromon τ_ij (znormalizowany do maksimum w danej klatce) |
| Kolor miejsca | antyferomon φ_j w aktualnym przedziale czasu |
| Cienkie linie | trasy mrówek z tej iteracji (m = 10) |
| Gruba linia | najlepsza trasa do tej pory |
| Licznik | numer iteracji lub godzina dnia, zysk najlepszej trasy |

## 7.2. Tryb „Jak myśli kolonia” — migawka co iterację

1. Przekaż do `acs()` funkcję `on_iteration`.
2. Po każdej iteracji funkcja zapisuje kopię τ, φ, tras mrówek i najlepszej trasy.
3. Z zapisanych stanów `report/plots.py` tworzy klatki animacji.

Wskazówki:

- Rysuj tylko najsilniejsze krawędzie, np. 5% krawędzi z największym τ. Dla N = 100 jest 10 000 krawędzi.
- Normalizuj τ w każdej klatce. Wartości τ są bardzo małe (rzędu τ_0).
- Zapisuj każdą iterację na początku, a potem np. co 10. ACS z q_0 = 0,9 zbiega szybko i największe zmiany są w pierwszych ok. 50 iteracjach.
- Spodziewaj się koncentracji feromonu, nie rozlewania. W ACS tylko najlepsza trasa dostaje feromon globalnie.

## 7.3. Tryb „Jak mija dzień” — migawka co godzinę

Pętla symulacji dnia owija solver. Zegar idzie co `step_min` minut. W każdym kroku:

1. Dodaj zdarzenia, które mają ogłoszenie w tej godzinie.
2. Uruchom ACS na resztę dnia (ciepły start, np. 50 iteracji).
3. Zapisz migawkę stanu.
4. Przesuń użytkownika po planie do następnego kroku.

```python
def simulate_day(instance, scenario, params, step_min=60):
    clock, position, done = params.T0, 0, []
    tau = phi = None
    snapshots = []
    while clock < params.T0 + params.Tmax:
        scenario.activate_announced(clock)
        sub = instance.remaining(position, clock, done)
        best, tau, phi = acs(sub, scenario, params, tau=tau, phi_ants=phi)
        snapshots.append(Snapshot(clock, tau.copy(), phi.copy(), best, position))
        position, done = walk(best, clock, clock + step_min, done)
        clock += step_min
    return snapshots
```

Migawki są zapisywane do plików: JSON dla tras, `.npz` dla τ i φ. Dla N = 100 macierz τ ma 10 000 liczb, więc pliki są małe.

## 7.4. Formy prezentacji

- Mapa HTML z suwakiem godziny lub iteracji (folium).
- Animacja (matplotlib `FuncAnimation`), np. GIF lub MP4.
- Oś czasu trasy (wykres Gantta): trasa bez zdarzenia i trasa ze zdarzeniem, jedna pod drugą.
- Opcjonalnie: interfejs Streamlit z suwakiem godziny.
