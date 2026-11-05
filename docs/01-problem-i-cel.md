# 1. Problem i cel

## Problem

Osoba, która zwiedza miasto, chce w ciągu jednego dnia odwiedzić wartościowe miejsca: muzea, kawiarnie, parki, restauracje. Chce też uniknąć tłoku. Tłok w miejscu zmienia się w ciągu dnia. Może też nagle wzrosnąć przez zdarzenie, na przykład darmowe wejście do muzeum. Miejsce może być nieoczekiwanie zamknięte, a ulica zablokowana przez paradę.

Przykład: popularne muzeum warto odwiedzić o 10:00, a nie o 15:00, gdy ma szczyt. Gdy muzeum ma darmowe wejście od 10:00 do 13:00, lepiej odwiedzić je wieczorem albo wcale.

## Rozwiązanie

AntRoute układa trasę, która:

- odwiedza miejsca poza ich godzinami szczytu,
- uwzględnia preferencje użytkownika (np. więcej kultury, mniej zakupów),
- reaguje na zdarzenia znane rano i na zdarzenia, które pojawiają się w trakcie dnia,
- mieści się w budżecie czasu i wraca do punktu startu.

Problem to klasyczny **Time-Dependent Orienteering Problem (TDOP)** z karą za tłok. Projekt nie wymaga nowej metody. Nowe elementy to kara za tłok, antyferomon i symulowane zdarzenia.

## Cele projektu

1. Zbuduj godzinowe profile tłoku miejsc z prawdziwych danych check-in.
2. Zaimplementuj ACS dla TDOP z karą za tłok i antyferomonem.
3. Dodaj symulowane zdarzenia: skok tłoku, zamknięcie miejsca, utrudnienie w ruchu.
4. Pokaż, jak zdarzenie zmienia trasę i feromon: przed zdarzeniem, w trakcie i po nim.
5. Porównaj ACS z prostymi metodami: algorytmem zachłannym i trasą losową.

## Dane wejściowe

| Wejście | Przykład |
| --- | --- |
| Punkt startu | Times Square (40.7580, −73.9855) |
| Godzina startu T_0 | 08:00 |
| Budżet czasu T_max | 8 h |
| Profil preferencji u_c | persona „Turysta kulturalny” albo własne wagi kategorii |
| Typ dnia | dzień roboczy lub weekend |
| Scenariusz zdarzeń | plik YAML ([rozdział 5](05-zdarzenia-i-scenariusze.md)) |

## Wynik

- Uporządkowana lista miejsc: Venue ID, kategoria, godzina przybycia, czas pobytu, tłok, zysk.
- Mapa trasy (HTML).
- Mapa feromonu τ i antyferomonu φ.
- Dla scenariusza ze zdarzeniem: trasa bez zdarzenia do porównania.

## Poza zakresem

- Prawdziwe dane o tłoku w czasie rzeczywistym.
- Aplikacja mobilna i nawigacja krok po kroku.
- Transport publiczny (model zakłada ruch pieszo).
