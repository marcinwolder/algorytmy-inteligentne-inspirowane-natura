# 2. Dane

Projekt używa publicznego zbioru [Foursquare NYC and Tokyo Check-in Dataset](https://sites.google.com/site/yangdingqi/home/foursquare-dataset), plik `dataset_TSMC2014_NYC.txt`. Zbiór ma 227 428 check-inów z Nowego Jorku, 1 083 użytkowników, 38 333 miejsc i 251 kategorii.

## 2.1. Format pliku

Plik to TSV bez nagłówka, kodowanie ISO-8859-1, 8 kolumn:

| Nr | Kolumna | Przykład | Użycie w projekcie |
| --- | --- | --- | --- |
| 1 | User ID (zanonimizowany) | `470` | nieużywana |
| 2 | Venue ID (Foursquare) | `49bbd6c0f964a520f4531fe3` | identyfikator wierzchołka |
| 3 | Venue category ID | `4bf58dd8d48988d127951735` | nieużywana |
| 4 | Venue category name | `Coffee Shop` | grupowanie profili |
| 5 | Latitude | `40.7198` | odległości, filtr Manhattanu |
| 6 | Longitude | `-74.0026` | odległości, filtr Manhattanu |
| 7 | Timezone offset [min] | `-240` | konwersja na czas lokalny |
| 8 | UTC time | `Tue Apr 03 18:00:09 +0000 2012` | godzina check-inu |

> **Uwaga:** readme zbioru podaje okres od 12.04.2012 do 16.02.2013. W pliku pierwszy check-in (czas lokalny) ma datę 3.04.2012, a ostatni 15.02.2013.

**Licencja:** strona zbioru nie podaje licencji. Autorzy proszą o cytowanie pracy Yang i in. (2015), [rozdział 10](10-zrodla.md). Projekt używa zbioru tylko do celów akademickich. Plik źródłowy nie jest w repozytorium.

## 2.2. Wybrane kategorie miejsc

Projekt używa kategorii z wyraźnie różnymi godzinami szczytu. „Szczyt” to godzina lokalna z największą liczbą check-inów (cały Nowy Jork, wszystkie dni). Pełne liczby godzinowe są w pliku [`data/hourly_checkins_nyc.csv`](data/hourly_checkins_nyc.csv).

| Kategoria | Check-iny | Miejsca | Szczyt [h] | Czas pobytu [min] (założenie) |
| --- | --- | --- | --- | --- |
| Breakfast Spot | 504 | 115 | 8 | 45 |
| Coffee Shop | 7 510 | 853 | 9 | 20 |
| Bakery | 1 586 | 372 | 13 | 15 |
| Museum | 175 | 45 | 14 | 90 |
| Art Museum | 326 | 34 | 15 | 120 |
| Park | 4 804 | 536 | 17 | 45 |
| Clothing Store | 2 976 | 996 | 18 | 30 |
| American Restaurant | 3 701 | 716 | 19 | 75 |
| Movie Theater | 2 158 | 139 | 19 | 150 |
| Mexican Restaurant | 2 043 | 374 | 20 | 60 |
| Bar | 15 978 | 2 488 | 22 | 60 |

Kategoria `Nightlife Spot` ma tylko 20 check-inów, więc projekt używa kategorii `Bar` jako miejsca nocnego. Piekarnia w Nowym Jorku ma szczyt o 13:00, a nie rano. Model używa danych, nie intuicji.

## 2.3. Przygotowanie danych

1. Przelicz czas UTC na czas lokalny: `local = utc + offset` (kolumna 7).
2. Odrzuć check-iny poza Manhattanem. Użyj wielokąta dzielnicy z [NYC Borough Boundaries](https://data.cityofnewyork.us/City-Government/Borough-Boundaries/tqmj-j8zm).
3. Zostaw tylko kategorie z tabeli 2.2.
4. Policz histogram 24 godzin dla każdej kategorii. Policz osobno dni robocze i weekend.
5. Wygładź histogram średnią kroczącą z oknem 3 h (cyklicznie, 23:00 łączy się z 0:00).
6. Znormalizuj profil do zakresu [0, 1]: `P_c(h) = n_c(h) / max_h n_c(h)`.
7. Wybierz miejsca z co najmniej 10 check-inami. Ogranicz instancję do N miejsc (N = 25, 50, 100).
8. Policz wagę wartości miejsca: `w_i = log(1 + n_i) / max_j log(1 + n_j)`.
9. Policz macierz czasów przejścia pieszo: odległość haversine × 1,3 (współczynnik siatki ulic), prędkość 5 km/h.

Zbiór nie ma godzin otwarcia. Model przyjmuje, że miejsce jest zamknięte, gdy `P_c(h) < 0,05`.

## 2.4. Dlaczego profil dla kategorii, a nie dla miejsca

Dane są za rzadkie na profil dla każdego miejsca:

- mediana to 2 check-iny na miejsce,
- tylko 141 z 38 333 miejsc ma co najmniej 100 check-inów,
- w wybranych kategoriach takich miejsc jest tylko 17.

Dlatego wszystkie miejsca jednej kategorii mają ten sam kształt profilu. Różnicę między miejscami dają waga `w_i` oraz zdarzenia dla konkretnych miejsc ([rozdział 5](05-zdarzenia-i-scenariusze.md)).
