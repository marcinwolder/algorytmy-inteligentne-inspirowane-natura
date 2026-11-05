# 9. Ograniczenia i ryzyka

| Ograniczenie | Skutek | Działanie |
| --- | --- | --- |
| Zdarzenia są symulowane | wyniki E10–E13 nie są pomiarem prawdziwego tłoku | dokumentacja nazywa je scenariuszami „co jeśli”; dane służą tylko jako tło zwykłego dnia |
| Dane z lat 2012–2013 | profile mogą nie pasować do dzisiejszego miasta | projekt jest demonstracją metody, nie usługą dla turystów |
| Check-in to nie liczba gości | profil mówi o aktywności użytkowników Foursquare, nie o ruchu w lokalu | traktuj P_c(h) jako względny wskaźnik tłoku |
| Brak godzin otwarcia | trasa może wskazać zamknięte miejsce | próg P_c(h) ≥ 0,05; opcjonalnie godziny z OpenStreetMap (`opening_hours`) |
| Profil per kategoria, nie per miejsce | dwa bary mają ten sam kształt profilu | różnicę daje waga w_i i zdarzenia dla konkretnych miejsc |
| Odległość haversine × 1,3 | czas przejścia jest przybliżony | opcjonalnie macierz z OSRM (profil `foot`) |
| Małe kategorie (np. Museum: 175 check-inów) | profil jest zaszumiony | wygładzanie 3 h, ewentualnie łączenie z Art Museum |
| Za duża siła antyferomonu | mrówki omijają za dużo miejsc, wynik spada | E4 i E13 sprawdzają γ; Montgomery i Randall opisują ten sam efekt |
| Brak licencji zbioru | niejasne prawa do publikacji danych | plik źródłowy poza repozytorium; tylko cele akademickie; cytowanie autorów |

## Otwarte decyzje

- Miasto: Manhattan (Nowy Jork) czy Tokio. Ten sam zbiór ma 573 703 check-iny z Tokio.
- Wartości parametrów projektu (λ, γ, φ_max, T_d, κ) — do strojenia w E4.
- Zakres eksperymentów — do ustalenia z prowadzącym.
