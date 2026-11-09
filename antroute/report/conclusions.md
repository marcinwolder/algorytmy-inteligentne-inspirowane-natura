Wnioski napisane ręcznie po analizie wyników. Plik czyta `antroute/report/summary.py`.
Sekcja `decyzje` trafia na początek SUMMARY.md, sekcje `E*` pod tabele eksperymentów.

## decyzje

### Decyzje implementacyjne (docs/11, punkt 11.4)

| Id | Decyzja w PoC | Podstawa |
| --- | --- | --- |
| D1 | τ_0 = Profit_greedy / N (opcja `tau0_mode: doc` = wzór z dokumentacji) | E4: z przeszukiwaniem lokalnym i q_0 = 0,5 luka 0,00% wobec 0,46% dla wzoru z dokumentacji; bez przeszukiwania lokalnego różnica jest mała i niejednoznaczna |
| D2 | P_c(h) w punkcie h:30, interpolacja liniowa, cyklicznie | test `test_profile_value_*` |
| D3 | dokładne sprawdzenie „otwarte”: końce pobytu + węzły interpolacji w środku | test `test_is_open_detects_closed_node_inside_stay` |
| D4 | mnożnik według chwili wyjścia, krawędź „w obszarze”, gdy odcinek przecina koło | test `test_segment_hits_circle` |
| D5 | < 100 check-inów → profil z wszystkich dni → profil grupy Museum+Art Museum | Museum ma 95 check-inów na Manhattanie |
| D6 | losowanie warstwowe (min. 1 miejsce z kategorii, reszta proporcjonalnie), ziarno 0 | ta sama instancja dla wszystkich metod |
| D7 | pobyt w trakcie: użytkownik go kończy, nowy start = to miejsce po pobycie; przejście w trakcie: przejście jest przerwane, nowy start = poprzednie miejsce w chwili t_a | E13b pokazał błąd pierwszej wersji (zatwierdzenie przejścia do miejsca zamkniętego w trakcie przejścia); test `test_replanning_drops_walk_to_venue_closed_during_the_walk` |
| D8 | aktualizacja globalna na trasie najlepszej od początku | jak w ACS (Dorigo i Gambardella 1997) |
| D9 | przeszukiwanie lokalne (wstaw, zamień, przenieś, zamień miejscami) na najlepszej trasie iteracji | E1, E2, E4, K4 |
| D10 | CP-SAT: czas co 0,1 min, tabele zysku co 1 min, nadmiarowe ograniczenie budżetu, podpowiedź z ACS | bez ograniczenia budżetu CP-SAT nie dowodzi optimum w 60 s |
| D11 | Manhattan | - |

### Zmiany parametrów względem dokumentacji

- **Główna metoda to `acs_ls`**: ACS-A + przeszukiwanie lokalne (D9) + q_0 = 0,5. Z q_0 = 0,9 (dokumentacja) ACS-A trafia w optimum na małych instancjach tylko w ok. 63-70% uruchomień (K4 nie jest spełnione). ACS-LS trafia w 100%.
- **Liczba iteracji: 2000** zamiast 500. Jedno uruchomienie trwa < 1 s (Numba), a 500 iteracji czasem kończy się przed wyjściem z optimum lokalnego (kontrola na scenariuszu E10).
- Wariant `acs_a` zostaje z parametrami z dokumentacji (q_0 = 0,9, β = 2) jako punkt odniesienia.

## E1

- ACS-LS ma średnią lukę 0,19% do najlepszego znanego zysku. ACS-A ma 2,9%, metoda zachłanna 18,2%, trasa losowa 54,9%.
- ACS-LS jest lepszy od metody zachłannej na prawie każdej instancji i nigdy nie jest gorszy (start od trasy zachłannej). Kryterium K5 jest spełnione.
- Luka ACS-A rośnie z N i z budżetem. Luka ACS-LS jest prawie stała, bo przeszukiwanie lokalne poprawia kolejność wizyt.
- Wszystkie trasy wszystkich metod są dozwolone (0 naruszeń w 19 548 uruchomieniach).
- Koszt ACS-LS to ok. 1 s na uruchomienie (maks. ok. 17 s dla N = 100 i 12 h).
- K6: dla N = 25 średnia luka ACS-LS do best_known wynosi 0,09%. Na 24 instancjach, gdzie CP-SAT udowodnił optimum, luka wynosi 0,05%. Najlepsze ziarno ACS-LS osiąga best_known na 35 z 36 instancji. Górne ograniczenie CP-SAT jest słabe dla budżetu 12 h (średnia luka do niego 5,7%), więc dla tych instancji nie ma dowodu optymalności.

## E3

- Feromon zależny od pory dnia (ACS-B) nie poprawia wyniku. Na instancjach E1 różnica między ACS-B i ACS-A nie jest istotna (p = 0,25), a średnio ACS-B jest trochę gorszy. W E2 przy budżecie 12 h ACS-B jest wyraźnie gorszy.
- Powód: 8 macierzy feromonu dzieli tę samą liczbę depozytów na 8 części, więc każda macierz uczy się wolniej. Informacja o porze dnia jest już w heurystyce η, która zna godzinę przybycia.
- Rekomendacja: zostaw ACS-B jako wariant badawczy, nie jako metodę domyślną.

## E9

- Kara za tłok działa: bez kary (`acs_ls+static`) średni tłok na trasie rośnie z ok. 0,39 do ok. 0,58, a liczba wizyt w szczycie (C > 0,7) rośnie kilka razy.
- Trasa bez kary ma mniejszy prawdziwy zysk (oceniany z λ = 0,8), na poziomie metody zachłannej.
- Oś czasu pokazuje typowy efekt: trasa bez kary idzie do muzeum o 17:00, w szczycie; trasa z karą omija muzeum w tym czasie.

## E2

- ACS-LS zbiega najszybciej i najpewniej: 100% najlepszego zysku w każdym uruchomieniu na dwóch z trzech instancji i 99,7% średnio na trzeciej.
- ACS-A i ACS-B kończą na ok. 95-98% po 3000 iteracjach, z dużym rozrzutem między ziarnami.
- Wzór τ_0 z dokumentacji (`acs_a_tau0doc`) i wzór D1 dają prawie te same krzywe dla ACS-A. Skala τ_0 nie jest główną przyczyną słabej zbieżności ACS-A. Główna przyczyna to silna eksploatacja (q_0 = 0,9) i brak poprawy lokalnej kolejności wizyt.
- ACS-B jest wyraźnie najwolniejszy przy budżecie 12 h (86,6%).

## E4

- Mniejsze β i mniejsze q_0 dają lepsze trasy. Wartości z dokumentacji (β = 2, q_0 = 0,9) nie są najlepsze dla tego problemu. Najlepsze w siatce: β = 1, q_0 = 0,5.
- Więcej mrówek (m = 20) daje mały zysk jakości za dwa razy dłuższy czas.
- λ zmienia funkcję celu: λ = 0,4 daje większy zysk i większy tłok, λ = 1 daje mniejszy tłok (0,35 wobec 0,47).
- Tabela decyzji: przeszukiwanie lokalne + q_0 = 0,5 + τ_0 według D1 daje lukę 0,00% we wszystkich 120 uruchomieniach. To potwierdza wybór metody głównej.

## E5

- Wczesny start (06:00-08:00) i późny start (20:00) dają największy zysk i najmniejszy tłok (0,18-0,28). Start o 17:00-18:00 daje najmniejszy zysk i największy tłok (0,48).
- Mapa ciepła pokazuje, że trasa dobiera kategorie do pory dnia. Piekarnia i Breakfast Spot pojawiają się dopiero przy starcie od 14:00-15:00, a American Restaurant znika przy starcie od 17:00.
- **Ważne ograniczenie modelu.** Persona `balanced` odwiedza bar przy starcie 06:00-14:00. Bar ma wtedy P_c = 0,06-0,11: jest „otwarty” według progu 0,05 z dokumentacji i prawie pusty, więc daje prawie pełny zysk. Ten sam efekt daje muzeum o 08:24 (P_c ok. 0,2) w E10-E12. Model nagradza wizytę tuż nad progiem zamknięcia.
- Solver działa poprawnie w ramach modelu, ale te trasy nie są realistyczne. Zadanie na v2: godziny otwarcia dla kategorii (tabela założeń jak czasy pobytu) albo z OpenStreetMap, ewentualnie kara za bardzo mały ruch.

## E6

- Persony dają różne trasy: kategorie w trasie odpowiadają wagom u_c (na przykład `night_owl` i `foodie` mają bary i restauracje).
- Trasy są stabilne między ziarnami (Jaccard 0,8-1,0), więc różnice między personami to efekt preferencji, nie losowości.
- 100 losowych profili daje 67 różnych tras.

## E7

- Punkt startu zmienia trasę bardziej niż ziarno. Trasy z tego samego punktu mają Jaccard 0,78-1,0. Trasy z Times Square, Union Square i Wall Street dzielą część miejsc (0,37-0,65). Trasy z Metropolitan Museum są prawie rozłączne z innymi (0-0,12), bo start jest daleko na północy.
- Zysk zależy od punktu startu w małym stopniu (1,61-1,76). Budżet jest prawie w pełni wykorzystany we wszystkich punktach.

## E8

- Tylko 2 miejsca (dwie restauracje) są w ≥ 80% tras dla 20 wersji danych bootstrap. Reszta trasy zmienia się z wersją danych.
- Trasa z profilu bootstrap, oceniona na profilu z pełnych danych, traci średnio ok. 1% zysku (maks. ok. 10%). Model jest dość odporny na szum w danych, ale konkretne miejsca w trasie nie są stabilne.

## E10

- Plan bez zdarzeń nie odwiedza muzeum w oknie 10:00-13:00 (odwiedza je o 08:24 albo wcale). Dlatego miejsce zdarzenia to sklep z ubraniami (start 08:00) i meksykańska restauracja (start 10:00), które ten plan odwiedza o 10:04.
- Gdy zdarzenie jest znane rano, ACS-LS nigdy nie odwiedza miejsca w oknie zdarzenia. Przy krótkim spadku tłoku (T_d = 30 min) przesuwa wizytę na popołudnie (14:40 albo 16:53). Przy długim spadku (T_d = 180 min) częściej usuwa miejsce z trasy.
- Koszt zdarzenia dla ACS-LS to 0,004-0,010 przy starcie 08:00 i ok. 0,10 przy starcie 10:00. Plan bez zmian (`fixed`) traci 0,047 i 0,19, czyli 2-10 razy więcej.
- Większe T_d daje większy koszt, zgodnie z docs 5.1.

## E11

- Ponowne planowanie o 11:00 odzyskuje prawie cały zysk: strata wobec wiedzy od rana to ok. 0,007, a plan bez zmian (`fixed`) traci ok. 0,136.
- Ciepły start nie jest lepszy od zimnego w tym scenariuszu. Oba warianty ACS-LS osiągają najlepszy zysk podproblemu w każdym uruchomieniu, średnio w ok. 3 iteracje. Podproblem po 11:00 jest mały (3-4 wizyty), a trasa zachłanna już jest blisko optimum.
- Dla ACS-A ciepły start jest nawet trochę gorszy (73% wobec 87% uruchomień z najlepszym zyskiem): stary feromon kieruje mrówki na stare krawędzie.
- Wniosek: korzyść z ciepłego startu (Guntsch i Middendorf 2001) nie pojawia się przy małych podproblemach. Przy większym podproblemie i małej liczbie iteracji ciepły start wyraźnie pomaga (E13b).

## E12

- Zamknięcie i parada mają mały koszt dla ACS-LS (0,02-0,06). ACS-LS odwiedza zamknięte muzeum po 12:00, gdy jest już otwarte.
- Plan bez zdarzeń (`fixed`) jest niewykonalny we wszystkich trzech scenariuszach: wizyta w zamkniętym miejscu albo powrót po czasie przez paradę.
- Metoda zachłanna traci 0,21-0,27 zysku.

## E13

- Antyferomon nie zmienia wyniku ACS-LS w E11 i E12 (prawie wszystkie pary to remisy) ani średnio w E1 (różnica w granicach szumu).
- Powód: heurystyka η już karze tłok w chwili przybycia, a przeszukiwanie lokalne poprawia trasę niezależnie od feromonu. Antyferomon powtarza tę samą informację.
- Antyferomon jest przydatny jako wizualizacja pamięci kolonii: mapa φ pokazuje miejsce zdarzenia w oknie zdarzenia.
- Rekomendacja: zostaw antyferomon (γ = 1) jako opcję. Nie ma dowodu, że pomaga albo szkodzi. Test w trudniejszych warunkach jest w E13b.

## E13b

- Scenariusz z rozmowy z zespołem: start 09:00, wypadek, zamknięcie albo skok tłoku ogłoszony o 10:23. Każdy wariant reaguje poprawnie: 0 tras niewykonalnych w 2160 uruchomieniach, a nowy plan omija zdarzenie.
- **Antyferomon ze zdarzenia dla wypadku i zamknięcia nie zmienia żadnej trasy** (`acs_a_g1` = `acs_a_g1_phidoc` w 30/30 parach, w każdym ustawieniu). To wynika z konstrukcji modelu: zamknięte miejsce nie jest kandydatem, a każde przejście do miejsca w obszarze wypadku (×50) przekracza budżet. Mrówka nigdy nie czyta tego φ, bo model już zabrania tych wyborów.
- **γ nie daje stałego efektu.** γ = 1 wobec γ = 0 jest istotnie lepsze tylko w 1 z 12 ustawień (wypadek, 50 iteracji, zimny start); w innych różnice idą w obie strony. γ = 3 też nie pomaga.
- **Ciepły start daje wyraźny efekt** przy szybkim ponownym planowaniu: dla ACS-A i 10 iteracji ok. 1,55-1,56 wobec 1,43-1,46 przy zimnym starcie; po 50 iteracjach różnica maleje. Pamięć kolonii pomaga, ale przez feromon τ z planu porannego.
- Pierwsze uruchomienie E13b znalazło błąd w D7 (przejście do miejsca zamkniętego w trakcie przejścia było zatwierdzane). Po poprawce wcześniejsza pozorna korzyść z γ = 1 zniknęła.
- Wniosek: w tym modelu planista zna skutek zdarzenia dokładnie (zakaz, czas przejścia, tłok), więc antyferomon nie dodaje informacji. Antyferomon ma sens, gdy planista zna zdarzenie tylko w przybliżeniu, na przykład „coś się stało w okolicy”, bez dokładnego czasu przejścia. Taki tryb to propozycja na v2.
