# 3. Model matematyczny

AntRoute rozwiązuje Orienteering Problem, w którym zysk z miejsca zależy od tłoku w chwili przybycia. Trasa zaczyna się i kończy w punkcie użytkownika. Każde miejsce można odwiedzić najwyżej raz.

## 3.1. Oznaczenia

| Symbol | Znaczenie | Jednostka |
| --- | --- | --- |
| V = {0, 1, …, N} | wierzchołki; 0 = punkt startu i końca | — |
| t_ij(t) | czas przejścia pieszo z i do j (zależy od utrudnień) | min |
| s_i | czas pobytu w miejscu i | min |
| c(i) | kategoria miejsca i | — |
| w_i | wartość miejsca i, w zakresie [0, 1] | — |
| P_c(h) | profil tłoku kategorii c, w zakresie [0, 1] | — |
| E_i(t) | dodatkowy tłok ze zdarzenia | — |
| C_i(t) | łączny tłok w miejscu i | — |
| u_c | preferencja użytkownika dla kategorii c, w zakresie [0, 1] | — |
| λ | siła kary za tłok, w zakresie [0, 1] | — |
| T_0, T_max | godzina startu, budżet czasu | min |
| K_c | maksymalna liczba miejsc kategorii c w trasie | — |
| a_i | czas przybycia do miejsca i | min |

## 3.2. Zysk z karą za tłok

Tłok ma dwie części: tło z danych i zdarzenia scenariusza.

$$
C_i(t) = P_{c(i)}\big(h(t)\big) + E_i(t)
$$

Zysk z miejsca maleje, gdy tłok rośnie:

$$
S_i(a_i) = u_{c(i)} \cdot w_i \cdot \Big(1 - \lambda \cdot \min\big(1,\, C_i(a_i)\big)\Big)
$$

Model używa interpolacji liniowej między pełnymi godzinami, więc zysk nie skacze o pełnej godzinie.

| Składnik | Co opisuje | Skąd pochodzi | Co zmienia w trasie |
| --- | --- | --- | --- |
| P_c(h) | kiedy kategoria jest zatłoczona | dane | przesuwa wizyty na godziny poza szczytem |
| E_i(t) | dodatkowy tłok ze zdarzenia | scenariusz (symulacja) | omija miejsce w oknie zdarzenia |
| w_i | popularność miejsca w całym okresie | dane | wybór między miejscami |
| u_c | co lubi użytkownik | użytkownik | jakie kategorie są w trasie |

Domyślnie λ = 0,8. Gdy λ = 0, model ignoruje tłok. Gdy λ = 1, miejsce w szczycie nie daje zysku. Gdy u_c = 0, model nie dodaje kategorii c do trasy.

## 3.3. Funkcja celu i ograniczenia

Trasa to ciąg r = (0, v_1, …, v_k, 0). Czas przybycia:

$$
a_{v_1} = T_0 + t_{0 v_1}, \qquad a_{v_{j+1}} = a_{v_j} + s_{v_j} + t_{v_j v_{j+1}}\big(a_{v_j} + s_{v_j}\big)
$$

Cel:

$$
\max_{r} \; \sum_{j=1}^{k} S_{v_j}\big(a_{v_j}\big)
$$

Ograniczenia:

1. Budżet czasu: powrót do 0 najpóźniej o T_0 + T_max.
2. Każde miejsce jest w trasie najwyżej raz.
3. Miejsce jest otwarte przez cały pobyt: P_c(h) ≥ 0,05 i brak zdarzenia „zamknięcie” w czasie [a_i, a_i + s_i].
4. Różnorodność: najwyżej K_c miejsc kategorii c (domyślnie K_c = 1, dla restauracji K_c = 2).

Model nie pozwala na czekanie przed miejscem.

## 3.4. Dlaczego algorytm mrówkowy

- Orienteering Problem jest NP-trudny, więc dokładne metody działają tylko dla małych N.
- Zysk zależy od godziny przybycia, więc wartość miejsca zależy od całej wcześniejszej części trasy. ACS buduje trasę krok po kroku i w każdym kroku zna aktualną godzinę.
- Feromon i antyferomon to pamięć kolonii o dobrych i złych wyborach. Gdy zdarzenie zmienia problem w trakcie dnia, kolonia nie zaczyna od zera, tylko dostosowuje tę pamięć. To podejście jest znane z ACO dla dynamicznego TSP (Guntsch i Middendorf, 2001).
- Algorytm nie wymaga treningu. Każde uruchomienie dostaje dane i reguły, a feromon „uczy się” tylko w trakcie tego uruchomienia.
