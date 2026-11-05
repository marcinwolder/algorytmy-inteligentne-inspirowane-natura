# 8. Plan eksperymentów

Eksperymenty sprawdzają cztery rzeczy: czy ACS daje większy zysk niż proste metody, czy trasa omija tłok, jak trasa reaguje na zdarzenia oraz czy trasa jest stabilna przy zmianie danych. ACS jest algorytmem losowym, więc każda konfiguracja ma 30 uruchomień z różnymi ziarnami losowania.

## 8.1. Siatka scenariuszy

Ten sam zbiór danych daje wiele różnych instancji, bo scenariusz ma 8 niezależnych wymiarów. Eksperymenty używają podzbiorów tej siatki.

| Wymiar | Wartości | Liczba |
| --- | --- | --- |
| Punkt startu | Times Square (40.7580, −73.9855); Union Square (40.7359, −73.9911); Wall Street (40.7074, −74.0104); Metropolitan Museum (40.7794, −73.9632) | 4 |
| Godzina startu T_0 | od 06:00 do 20:00 co 1 h | 15 |
| Budżet T_max | 4 h, 8 h, 12 h | 3 |
| Liczba miejsc N | 25, 50, 100 | 3 |
| Typ dnia | dzień roboczy, weekend | 2 |
| Profil preferencji u_c | 4 persony + 100 losowych profili u_c ~ U(0, 1) | 104 |
| Wersja danych | profil z całego okresu + 20 wersji bootstrap (losowanie dni ze zwracaniem) | 21 |
| Scenariusz zdarzeń | brak; skok tłoku znany rano; skok tłoku ogłoszony o 11:00; zamknięcie; utrudnienie; wszystkie razem | 6 |

Bootstrap symuluje zmienność dnia: każda wersja to profil P_c(h) policzony z innej losowej próby dni.

**Persony (wagi u_c, założenie projektu):**

| Persona | Breakfast Spot, Coffee Shop, Bakery | Museum, Art Museum, Movie Theater | Park | Clothing Store | American, Mexican Restaurant | Bar |
| --- | --- | --- | --- | --- | --- | --- |
| Zrównoważony | 1,0 | 1,0 | 1,0 | 1,0 | 1,0 | 1,0 |
| Turysta kulturalny | 0,6 | 1,0 | 0,8 | 0,2 | 0,6 | 0,2 |
| Smakosz | 1,0 | 0,3 | 0,4 | 0,2 | 1,0 | 0,6 |
| Nocny marek | 0,4 | 0,4 | 0,3 | 0,3 | 0,7 | 1,0 |

## 8.2. Metody porównawcze

| Metoda | Opis |
| --- | --- |
| Losowa | dodaje losowe dozwolone miejsca, aż budżet się skończy |
| Zachłanna | wybiera miejsce z największym η_ij(t) w każdym kroku |
| ACS-A | ACS z jedną macierzą feromonu i antyferomonem |
| ACS-B | ACS z feromonem zależnym od pory dnia |
| ACS-noφ | ACS-A bez antyferomonu (γ = 0) |
| ACS-static | ACS bez kary za tłok (λ = 0) |

Trasy wszystkich metod ocenia ta sama funkcja S_i(a_i) z karą za tłok.

## 8.3. Eksperymenty

| Id | Nazwa | Co sprawdza |
| --- | --- | --- |
| E1 | Jakość | średni zysk i odchylenie wszystkich metod; 4 punkty × 3 godziny × 3 budżety × 3 N, bez zdarzeń |
| E2 | Zbieżność | najlepszy zysk w funkcji iteracji dla ACS-A i ACS-B |
| E3 | Feromon zależny od czasu | ACS-A i ACS-B, test Wilcoxona (α = 0,05) |
| E4 | Wrażliwość parametrów | β ∈ {1, 2, 5}, q_0 ∈ {0,7; 0,9; 0,98}, m ∈ {5, 10, 20}, λ ∈ {0,4; 0,8; 1,0} |
| E5 | Godzina startu | mapa ciepła: kategoria × godzina startu (06:00–20:00), kolor = udział kategorii w trasie |
| E6 | Preferencje | 4 persony i 100 losowych profili; podobieństwo Jaccarda tras |
| E7 | Punkt startu | trasy z 4 punktów przy tej samej godzinie i personie |
| E8 | Stabilność danych | 20 wersji bootstrap; miejsca obecne w ≥ 80% tras to „stabilny rdzeń” |
| E9 | Omijanie tłoku | trasy ACS-A i ACS-static na mapie; czy ACS-A odwiedza miejsca poza szczytem |
| E10 | Zdarzenie znane rano | darmowe wejście do muzeum 10:00–13:00; T_d ∈ {30, 60, 180} min; oś czasu trasy |
| E11 | Zdarzenie w trakcie dnia | to samo zdarzenie ogłoszone o 11:00; zimny i ciepły start; krzywa powrotu |
| E12 | Zamknięcie i utrudnienie | zamknięte miejsce z porannej trasy + parada przy Times Square 12:00–15:00 |
| E13 | Rola antyferomonu | ACS-A i ACS-noφ w scenariuszach E10–E12; mapy φ i τ przed zdarzeniem i po nim |

## 8.4. Metryki

| Metryka | Definicja |
| --- | --- |
| Zysk | suma S_i(a_i) na trasie |
| Luka do najlepszego | (best_known − zysk) / best_known · 100% |
| Średni tłok | średnia C_i(a_i) dla miejsc na trasie |
| Wizyty w oknie zdarzenia | liczba miejsc odwiedzonych w czasie aktywnego zdarzenia „skok tłoku” |
| Koszt zdarzenia | zysk bez zdarzenia − zysk ze zdarzeniem |
| Czas powrotu | liczba iteracji po zdarzeniu do 95% najlepszego zysku |
| Wykorzystanie budżetu | czas trasy / T_max |
| Czas obliczeń | sekundy na jedno uruchomienie |

Dla N = 25 projekt liczy rozwiązanie dokładne solverem CP-SAT (OR-Tools) z czasem dyskretnym co 15 min. To daje wartość best_known.
