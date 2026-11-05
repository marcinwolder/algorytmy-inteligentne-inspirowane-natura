# 5. Zdarzenia i scenariusze

Zdarzenie to symulowana zmiana warunków w mieście. Zdarzenia nie pochodzą z danych: użytkownik albo eksperyment dodaje je do scenariusza. Prawdziwe dane opisują tylko tłok w zwykły dzień.

## 5.1. Typy zdarzeń

Każde zdarzenie ma typ, miejsce lub obszar, okno czasu [t_s, t_e] i siłę s ∈ [0, 1].

| Typ | Przykład | Wpływ na model |
| --- | --- | --- |
| Skok tłoku (`crowd_surge`) | darmowe wejście do muzeum 10:00–13:00 | E_i(t) = s w oknie; po t_e tłok maleje: E_i(t) = s · exp(−(t − t_e) / T_d); ACS dodaje antyferomon |
| Zamknięcie (`closure`) | remont, zamknięty lokal | miejsce jest poza zbiorem dozwolonych miejsc w oknie |
| Utrudnienie w ruchu (`traffic`) | parada, zamknięta ulica | t_ij(t) = m · t_ij dla krawędzi w obszarze (koło o promieniu r), gdy przejście zaczyna się w oknie; m > 1 |

Spadek tłoku po t_e decyduje o wyniku. Gdy T_d jest krótki, trasa może wrócić do muzeum wieczorem. Gdy T_d jest długi, trasa omija muzeum cały dzień.

## 5.2. Zdarzenie znane rano i zdarzenie w trakcie dnia

Zdarzenie ma chwilę ogłoszenia t_a:

- **t_a ≤ T_0** — zdarzenie jest znane rano i plan od początku je uwzględnia.
- **t_a > T_0** — zdarzenie pojawia się w trakcie trasy. ACS planuje resztę trasy od nowa ([punkt 4.5](04-algorytm.md#45-ponowne-planowanie-w-trakcie-dnia)).

## 5.3. Plik scenariusza

Użytkownik opisuje zdarzenia w pliku YAML. Aby sprawdzić nowy przypadek, dodaj zdarzenie do pliku i uruchom solver ponownie.

```yaml
name: free_museum
day_type: weekend
events:
  - type: crowd_surge          # skok tłoku
    venue: <venue_id muzeum>
    window: ["10:00", "13:00"]
    strength: 1.0
    decay_min: 60              # T_d
    announced: "11:00"         # t_a > T_0, więc ponowne planowanie
  - type: closure              # zamknięcie
    venue: <venue_id kawiarni>
    window: ["08:00", "12:00"]
  - type: traffic              # utrudnienie w ruchu
    center: [40.7536, -73.9832]
    radius_m: 400
    window: ["12:00", "15:00"]
    factor: 2.0                # m
```

| Pole | Typ zdarzenia | Opis |
| --- | --- | --- |
| `venue` | `crowd_surge`, `closure` | Venue ID ze zbioru Foursquare |
| `window` | wszystkie | okno czasu [t_s, t_e], czas lokalny |
| `strength` | `crowd_surge` | siła s ∈ [0, 1] |
| `decay_min` | `crowd_surge` | T_d w minutach (domyślnie 60) |
| `center`, `radius_m` | `traffic` | środek i promień obszaru utrudnienia |
| `factor` | `traffic` | mnożnik czasu przejścia m > 1 |
| `announced` | wszystkie | chwila ogłoszenia t_a; brak pola = zdarzenie znane od początku dnia |

## 5.4. Przykładowe pytania, na które odpowiada scenariusz

- Czy trasa omija muzeum w czasie darmowego wejścia, przesuwa je na wieczór, czy odwiedza je przed 10:00?
- Jak zmienia się kolejność miejsc, gdy kawiarnia z porannego planu jest zamknięta?
- Ile zysku kosztuje parada w okolicy Times Square?
- Czy kolonia z ciepłym startem szybciej znajduje dobrą trasę po zdarzeniu niż kolonia z zimnym startem?
