# AntRoute — dokumentacja produktu

AntRoute planuje jednodniową trasę po Manhattanie (Nowy Jork), która omija tłok. Trasa odwiedza wartościowe miejsca w godzinach, gdy jest w nich mało ludzi. Planer używa algorytmu mrówkowego (Ant Colony System) z dodatkową warstwą antyferomonu, który odstrasza mrówki od zatłoczonych miejsc.

> **Status:** propozycja projektu. Parametry, zestaw eksperymentów i wybór miasta mogą się zmienić w trakcie pracy.

## W skrócie

| Element | Opis |
| --- | --- |
| Problem | tłok w miejscach zmienia się w ciągu dnia i może nagle wzrosnąć przez zdarzenie |
| Model | Time-Dependent Orienteering Problem z karą za tłok |
| Algorytm | Ant Colony System + antyferomon + ponowne planowanie w trakcie dnia |
| Dane | Foursquare NYC check-ins (227 428 check-inów, 2012–2013) |
| Zdarzenia | symulowane: skok tłoku, zamknięcie miejsca, utrudnienie w ruchu |
| Wynik | trasa z godzinami, mapa trasy, mapa feromonu i antyferomonu |
| Technologia | Python (NumPy, pandas, matplotlib, folium) |

## Spis treści

1. [Problem i cel](01-problem-i-cel.md)
2. [Dane](02-dane.md)
3. [Model matematyczny](03-model.md)
4. [Algorytm mrówkowy](04-algorytm.md)
5. [Zdarzenia i scenariusze](05-zdarzenia-i-scenariusze.md)
6. [Architektura](06-architektura.md)
7. [Wizualizacja i symulacja](07-wizualizacja.md)
8. [Plan eksperymentów](08-eksperymenty.md)
9. [Ograniczenia i ryzyka](09-ograniczenia-i-ryzyka.md)
10. [Źródła](10-zrodla.md)

Dane pomocnicze: [`data/hourly_checkins_nyc.csv`](data/hourly_checkins_nyc.csv) — liczba check-inów w każdej godzinie dla 11 kategorii miejsc.
