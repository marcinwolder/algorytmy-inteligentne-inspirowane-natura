# 4. Algorytm mrówkowy

AntRoute używa Ant Colony System (Dorigo i Gambardella, 1997) z adaptacją do Orienteering Problem (Montemanni i Gambardella, 2009). Projekt dodaje dwie zmiany:

- heurystyka η liczy zysk z karą za tłok dla aktualnej godziny mrówki,
- reguła wyboru używa antyferomonu φ, który odstrasza mrówki (Montgomery i Randall, 2002).

## 4.1. Budowa trasy przez jedną mrówkę

1. Ustaw mrówkę w wierzchołku 0. Ustaw zegar t = T_0.
2. Wyznacz zbiór dozwolonych miejsc F(i). Miejsce j jest dozwolone, gdy: nie było odwiedzone, jest otwarte przez cały pobyt, limit K_c nie jest przekroczony i mrówka zdąży wrócić do 0 w budżecie.
3. Jeżeli F(i) jest pusty, wróć do wierzchołka 0 i zakończ trasę.
4. Wybierz następne miejsce j regułą z punktu 4.2.
5. Zastosuj lokalną aktualizację feromonu na krawędzi (i, j). Jeżeli tłok w j przekracza próg θ, dodaj antyferomon (punkt 4.4).
6. Ustaw t = t + t_ij(t) + s_j. Przejdź do kroku 2.

## 4.2. Reguła wyboru

Heurystyka to zysk na minutę dla czasu przybycia:

$$
\eta_{ij}(t) = \frac{S_j\big(t + t_{ij}(t)\big)}{t_{ij}(t) + s_j}
$$

Niech b_j oznacza 30-minutowy przedział dnia, w którym mrówka przybędzie do j. Z prawdopodobieństwem q_0 mrówka wybiera miejsce z największą wartością τ_ij · η_ij(t)^β · (1 + φ_j(b_j))^−γ. W przeciwnym razie losuje miejsce z rozkładu:

$$
p_{ij} = \frac{\tau_{ij} \cdot \eta_{ij}(t)^{\beta} \cdot \big(1 + \varphi_j(b_j)\big)^{-\gamma}}{\sum_{l \in F(i)} \tau_{il} \cdot \eta_{il}(t)^{\beta} \cdot \big(1 + \varphi_l(b_l)\big)^{-\gamma}}
$$

## 4.3. Aktualizacja feromonu

Lokalna aktualizacja po każdym kroku mrówki:

$$
\tau_{ij} \leftarrow (1 - \psi)\,\tau_{ij} + \psi\,\tau_0
$$

Globalna aktualizacja po każdej iteracji, tylko na krawędziach najlepszej trasy:

$$
\tau_{ij} \leftarrow (1 - \rho)\,\tau_{ij} + \rho \cdot Profit_{best}
$$

Wartość początkowa: τ_0 = (N · Profit_greedy)^−1. To odpowiednik wzoru τ_0 = (n · L_nn)^−1 z ACS dla TSP.

## 4.4. Antyferomon φ

Feromon τ_ij jest na krawędziach i przyciąga mrówki. Antyferomon φ_j(b) jest na miejscach i odstrasza mrówki. Indeks b to 30-minutowy przedział dnia (48 przedziałów), więc to samo muzeum może mieć duży φ o 11:00 i mały o 17:00.

| Źródło | Kiedy | Wartość |
| --- | --- | --- |
| Zdarzenie „skok tłoku” | w każdej iteracji, dopóki zdarzenie trwa | φ_j^E(b) = φ_max · E_j(b) |
| Mrówki | gdy mrówka trafi do miejsca z tłokiem C_j(a_j) > θ | φ_j^A(b) ← φ_j^A(b) + Δφ · C_j(a_j) |

Razem: φ_j(b) = φ_j^E(b) + φ_j^A(b). Część od mrówek paruje po każdej iteracji: φ^A ← (1 − ρ_φ) · φ^A. Część od zdarzenia nie paruje, dopóki zdarzenie trwa, a po jego końcu maleje razem z E_j(t).

Heurystyka η już karze tłok. Antyferomon dodaje pamięć kolonii o złych parach (miejsce, godzina). Ta pamięć jest widoczna na mapie jako kolor miejsca.

## 4.5. Ponowne planowanie w trakcie dnia

Gdy zdarzenie ma ogłoszenie w chwili t_a > T_0:

1. Zatrzymaj wykonaną część trasy. Miejsca odwiedzone przed t_a zostają w trasie.
2. Ustaw nowy start: aktualne miejsce użytkownika, godzina t_a, pozostały budżet.
3. Dodaj antyferomon i zmiany z nowego zdarzenia.
4. Uruchom ACS na nowej instancji przez 50 iteracji.

| Wariant | Feromon τ na starcie | Antyferomon φ na starcie |
| --- | --- | --- |
| Zimny start | τ_0 na wszystkich krawędziach | tylko od zdarzenia |
| Ciepły start | τ z planu porannego, wyrównany: τ ← (1 − κ) · τ + κ · τ_0 | od zdarzenia + od mrówek z planu porannego |

Wyrównanie κ to strategia „restart” z pracy Guntscha i Middendorfa (2001).

## 4.6. Wariant B: feromon zależny od pory dnia (opcjonalny)

W wariancie B feromon ma 8 przedziałów 3-godzinnych: τ_ij^(b). Mrówka czyta i aktualizuje feromon z przedziału swojej aktualnej godziny. Ten wariant pamięta, że przejście „park → bar” jest dobre wieczorem, ale złe rano.

## 4.7. Parametry

| Parametr | Wartość domyślna | Źródło |
| --- | --- | --- |
| m (liczba mrówek) | 10 | Dorigo i Gambardella 1997 |
| β | 2 | Dorigo i Gambardella 1997 |
| q_0 | 0,9 | Dorigo i Gambardella 1997 |
| ρ (globalne parowanie) | 0,1 | Dorigo i Gambardella 1997; Montemanni i Gambardella 2009 |
| ψ (lokalne parowanie) | 0,1 | Dorigo i Gambardella 1997; Montemanni i Gambardella 2009 |
| τ_0 | (N · Profit_greedy)^−1 | adaptacja wzoru (n · L_nn)^−1 |
| λ (siła kary za tłok) | 0,8 | założenie projektu |
| γ (siła antyferomonu) | 1 | założenie projektu; zbyt duża siła pogarsza wyniki (Montgomery i Randall 2002) |
| φ_max | 5 | założenie projektu |
| Δφ, ρ_φ, θ | 0,5; 0,1; 0,7 | założenie projektu |
| T_d (spadek tłoku po zdarzeniu) | 60 min | założenie projektu |
| κ (wyrównanie po zdarzeniu) | 0,3 | założenie projektu |
| Liczba iteracji | 500 lub 60 s; 50 po zdarzeniu | założenie projektu |

## 4.8. Pseudokod

```python
def acs(instance, scenario, params, tau=None, phi_ants=None, on_iteration=None):
    tau = tau if tau is not None else full_matrix(tau0(instance))
    phi_ants = phi_ants if phi_ants is not None else zeros(instance.n, 48)
    phi_event = event_antipheromone(scenario, params)
    best = greedy(instance, scenario)
    for it in range(params.iterations):
        routes = []
        for ant in range(params.m):
            route = build_route(instance, scenario, tau, phi_event + phi_ants, params)
            routes.append(route)
            if profit(route) > profit(best):
                best = route
        global_update(tau, best, params.rho)
        phi_ants *= (1 - params.rho_phi)
        if on_iteration:
            on_iteration(Snapshot(it, tau, phi_event + phi_ants, routes, best))
    return best, tau, phi_ants
```

Funkcja `on_iteration` służy do wizualizacji ([rozdział 7](07-wizualizacja.md)).
