"""WP10: results/SUMMARY.md with tables and figures for every experiment, from the CSV files.

Usage: python -m antroute.report.summary [--results results]
Hand-written conclusions are read from antroute/report/conclusions.md (sections "## E1", ...).
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from antroute.config import ROOT, fmt_hhmm, parse_hhmm
from antroute.report import plots

CONCLUSIONS = Path(__file__).parent / "conclusions.md"
METHOD_ORDER = ["random", "greedy", "acs_a", "acs_b", "acs_ls", "acs_ls+nophi", "acs_ls+static",
                "cpsat"]


# ---------------------------------------------------------------- helpers

def md(df: pd.DataFrame, fmt: str = "{:.4f}", index: bool = True) -> str:
    d = df.reset_index() if index else df
    cols = [str(c) for c in d.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(" --- " for _ in cols) + "|"]
    for _, r in d.iterrows():
        cells = []
        for v in r:
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else fmt.format(v))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def paired(a: np.ndarray, b: np.ndarray) -> dict:
    """Wilcoxon signed-rank test for paired samples a vs b (two-sided)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    res = {"n": len(d), "mean_diff": float(d.mean()), "wins": int((d > 1e-9).sum()),
           "ties": int((np.abs(d) <= 1e-9).sum()), "losses": int((d < -1e-9).sum())}
    if np.all(np.abs(d) <= 1e-12):
        res["p"] = 1.0
    else:
        res["p"] = float(wilcoxon(a, b, zero_method="zsplit").pvalue)
    return res


def pstr(p: float) -> str:
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


def load(res: Path, e: str) -> pd.DataFrame | None:
    f = res / e / "results.csv"
    return pd.read_csv(f, low_memory=False) if f.exists() else None


def load_hist(res: Path, e: str) -> list[dict]:
    f = res / e / "histories.jsonl"
    if not f.exists():
        return []
    hs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return [h for h in hs if h["values"]]


def conclusions() -> dict[str, str]:
    if not CONCLUSIONS.exists():
        return {}
    text = CONCLUSIONS.read_text(encoding="utf-8")
    parts = re.split(r"^## (\S+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def rows_of(r: pd.Series) -> list[dict]:
    if pd.isna(r["route"]) or r["route"] == "":
        return []
    ids = str(r["route"]).split(";")
    cats = str(r["categories"]).split(";")
    arr = [float(x) for x in str(r["arrivals"]).split(";")]
    return [{"venue_id": v, "category": c, "arrival": a} for v, c, a in
            zip(ids, cats, arr, strict=True)]


def full_rows(job: dict, route_ids: list[str]) -> list[dict]:
    """Re-evaluate a route (for crowd and stay values in plots)."""
    from antroute.experiments.common import build_problem
    from antroute.model.evaluate import evaluate_route

    p = build_problem(job).with_events(None)
    return evaluate_route(p, [p.instance.node_of(v) for v in route_ids]).rows


# ---------------------------------------------------------------- sections

class Summary:
    def __init__(self, res: Path):
        self.res = res
        self.fig = res / "figures"
        self.fig.mkdir(parents=True, exist_ok=True)
        self.out: list[str] = []
        self.k: dict[str, str] = {}
        self.notes = conclusions()

    def h(self, text: str) -> None:
        self.out += ["", text, ""]

    def p(self, text: str) -> None:
        self.out += [text, ""]

    def img(self, name: str, alt: str) -> None:
        self.out += [f"![{alt}](figures/{name})", ""]

    def concl(self, e: str) -> None:
        if e in self.notes:
            self.out += ["**Wnioski.**", "", self.notes[e], ""]

    # ------------------------------------------------------------ E1, K5, K6, E3, E9
    def e1(self) -> None:
        df = load(self.res, "E1")
        if df is None:
            return
        inst = ["start_point", "t0", "budget", "n"]
        feas = df[df["feasible"]]
        best = feas.groupby(inst)["profit"].max().rename("best")
        df = df.join(best, on=inst)
        df["gap"] = (df["best"] - df["profit"]) / df["best"] * 100
        self.h("## E1. Jakość metod (bez zdarzeń)")
        self.p(f"{df.groupby(inst).ngroups} instancji (4 punkty startu × 3 godziny × 3 budżety × "
               f"3 wartości N), persona `culture`, dzień roboczy, 30 ziaren dla metod losowych. "
               f"Luka = (najlepszy znany zysk instancji − zysk) / najlepszy znany zysk. "
               f"Najlepszy znany zysk to maksimum ze wszystkich metod, razem z CP-SAT.")
        methods = [m for m in METHOD_ORDER if m in set(df["method"])]
        t = (df.groupby("method").agg(profit=("profit", "mean"), profit_std=("profit", "std"),
                                      gap_pct=("gap", "mean"), feasible=("feasible", "mean"),
                                      visits=("n_visits", "mean"),
                                      avg_crowd=("avg_crowd", "mean"), time_s=("time_s", "mean"))
             .reindex(methods))
        self.out.append(md(t, "{:.3f}"))
        self.out.append("")
        g = df.pivot_table(index="method", columns="n", values="gap", aggfunc="mean")
        self.p("Średnia luka [%] według N:")
        self.out.append(md(g.reindex(methods).rename(columns=lambda c: f"N={c}"), "{:.2f}"))
        self.out.append("")
        g = df.pivot_table(index="method", columns="budget", values="gap", aggfunc="mean")
        self.p("Średnia luka [%] według budżetu T_max [min]:")
        self.out.append(md(g.reindex(methods).rename(columns=lambda c: f"T_max={c}"), "{:.2f}"))
        self.out.append("")
        plots.boxplot({m: df.loc[df["method"] == m, "gap"].to_numpy() for m in methods
                       if m != "cpsat"}, self.fig / "e1_gap_box.png",
                      "E1: gap to best known profit per run", "gap [%]")
        self.img("e1_gap_box.png", "E1 luka")

        means = df.groupby(inst + ["method"])["profit"].mean().unstack("method")
        pairs = [("acs_ls", "greedy"), ("acs_a", "greedy"), ("acs_ls", "acs_a"),
                 ("acs_ls", "acs_ls+nophi"), ("acs_a", "random")]
        rows = []
        for a, b in pairs:
            if a in means and b in means:
                r = paired(means[a].to_numpy(), means[b].to_numpy())
                rows.append({"A": a, "B": b, "instancje": r["n"], "śr. różnica": r["mean_diff"],
                             "A lepsza": r["wins"], "remis": r["ties"], "B lepsza": r["losses"],
                             "p (Wilcoxon)": pstr(r["p"])})
        self.p("Test Wilcoxona na średnich z 30 ziaren dla każdej instancji (para A-B):")
        self.out.append(md(pd.DataFrame(rows), "{:.4f}", index=False))
        self.out.append("")
        r = paired(means["acs_ls"].to_numpy(), means["greedy"].to_numpy())
        self.k["K5"] = (f"{'tak' if r['p'] < 0.05 and r['mean_diff'] > 0 else 'nie'}: "
                        f"ACS-LS > greedy na {r['wins']}/{r['n']} instancjach, p = {pstr(r['p'])}")

        # K6 - CP-SAT, N = 25
        cp = df[df["method"] == "cpsat"]
        if len(cp):
            k6 = df[(df["n"] == 25) & (df["method"] == "acs_ls")]
            k6 = k6.drop(columns=[c for c in k6.columns if c.startswith("cpsat_")])
            gap_ls = k6["gap"].mean()
            opt = cp["cpsat_status"].eq("OPTIMAL").sum()
            cpb = cp.set_index(inst)[["cpsat_bound", "cpsat_status"]]
            ub = k6.join(cpb, on=inst)
            ub_gap = ((ub["cpsat_bound"] - ub["profit"]) / ub["cpsat_bound"] * 100)
            ub_opt = ub[ub["cpsat_status"] == "OPTIMAL"]
            self.h("### K6. Luka do CP-SAT dla N = 25")
            self.p(f"CP-SAT (czas 0,1 min, tabela zysku co 1 min, limit 120 s, podpowiedź z "
                   f"najlepszej trasy ACS-LS) udowodnił optimum w {opt} z {len(cp)} instancji. "
                   f"Wszystkie trasy CP-SAT oceniono ponownie w `evaluate.py` (D10).")
            t = pd.DataFrame({
                "metryka": ["średnia luka ACS-LS do best_known [%]",
                            "maks. luka ACS-LS do best_known [%]",
                            "średnia luka ACS-LS do górnego ograniczenia CP-SAT [%]",
                            "średnia luka ACS-LS do CP-SAT na instancjach z dowodem optimum [%]",
                            "instancje, gdzie ACS-LS (najlepsze ziarno) = best_known"],
                "wartość": [gap_ls, k6["gap"].max(), ub_gap.mean(),
                            ((ub_opt["cpsat_bound"] - ub_opt["profit"]) / ub_opt["cpsat_bound"]
                             * 100).mean(),
                            float((k6.groupby(inst)["gap"].min() < 1e-6).sum())]})
            self.out.append(md(t, "{:.3f}", index=False))
            self.out.append("")
            self.k["K6"] = (f"{'tak' if gap_ls <= 5 else 'nie'}: średnia luka ACS-LS do "
                            f"best_known = {gap_ls:.2f}% (cel ≤ 5%); CP-SAT optimum w {opt}/"
                            f"{len(cp)} instancji")
        self.concl("E1")

        # E3
        self.h("## E3. Feromon zależny od pory dnia (ACS-A vs ACS-B)")
        if "acs_b" in means:
            r = paired(means["acs_b"].to_numpy(), means["acs_a"].to_numpy())
            self.p(f"Na {r['n']} instancjach E1: ACS-B lepszy {r['wins']}×, remis {r['ties']}×, "
                   f"gorszy {r['losses']}×. Średnia różnica zysku (B − A) = {r['mean_diff']:.4f}, "
                   f"p (Wilcoxon) = {pstr(r['p'])}.")
            g = df[df["method"].isin(["acs_a", "acs_b"])].pivot_table(
                index="budget", columns="method", values="gap", aggfunc="mean")
            self.out.append(md(g.rename(columns=lambda c: f"luka {c} [%]"), "{:.3f}"))
            self.out.append("")
        self.concl("E3")

        # E9
        self.h("## E9. Omijanie tłoku (ACS-LS vs ACS-LS bez kary za tłok)")
        s = df[df["method"].isin(["acs_ls", "acs_ls+static"])]
        t = s.groupby("method").agg(profit=("profit", "mean"), avg_crowd=("avg_crowd", "mean"),
                                    peak_visits=("peak_visits", "mean"),
                                    visits=("n_visits", "mean"))
        self.p("Obie trasy oceniono z λ = 0,8. `peak_visits` = liczba wizyt z tłokiem C > θ = 0,7.")
        self.out.append(md(t, "{:.3f}"))
        self.out.append("")
        cm = s.groupby(inst + ["method"])["avg_crowd"].mean().unstack("method")
        r = paired(cm["acs_ls+static"].to_numpy(), cm["acs_ls"].to_numpy())
        self.p(f"Średni tłok na trasie jest większy bez kary za tłok na {r['wins']} z {r['n']} "
               f"instancji, p (Wilcoxon) = {pstr(r['p'])}.")
        ex = {"exp": "E1", "n": 50, "start_point": "times_square", "t0": "12:00", "budget": 480,
              "persona": "culture", "day_type": "weekday"}
        sel = s[(s["n"] == 50) & (s["start_point"] == "times_square") & (s["t0"] == "12:00")
                & (s["budget"] == 480) & (s["seed"] == 0)]
        if len(sel) == 2:
            routes = []
            for m in ("acs_ls", "acs_ls+static"):
                r0 = sel[sel["method"] == m].iloc[0]
                routes.append((f"{m} ({r0['profit']:.3f})",
                               full_rows(ex, [x["venue_id"] for x in rows_of(r0)])))
            plots.route_timeline(routes, self.fig / "e9_timeline.png",
                                 "E9: Times Square, 12:00, 8 h, N=50 (colour = crowd at arrival)")
            self.img("e9_timeline.png", "E9 oś czasu")
        self.concl("E9")

    # ------------------------------------------------------------ E2
    def e2(self) -> None:
        hist = load_hist(self.res, "E2")
        df = load(self.res, "E2")
        if not hist or df is None:
            return
        self.h("## E2. Zbieżność")
        key_inst = df.set_index("key")[["n", "start_point", "t0", "budget"]]
        rows = []
        for (n, sp, t0, b), grp in key_inst.groupby(["n", "start_point", "t0", "budget"]):
            keys = set(grp.index)
            hs = [h for h in hist if h["key"] in keys and h["kind"] == "history"]
            ref = max(max(h["values"]) for h in hs)
            series, band = {}, {}
            for label in sorted({h["label"] for h in hs}):
                arr = np.array([h["values"] for h in hs if h["label"] == label])
                arr = arr / ref * 100
                series[label] = arr.mean(axis=0)
                band[label] = (np.percentile(arr, 10, axis=0), np.percentile(arr, 90, axis=0))
                final = arr[:, -1]
                to99 = [int(np.argmax(a >= 0.99 * a[-1])) + 1 for a in arr]
                rows.append({"instancja": f"N={n} {sp} {t0} T_max={b}", "metoda": label,
                             "zysk po 500 it. [% ref]": arr[:, 499].mean(),
                             "zysk końcowy [% ref]": final.mean(),
                             "min końcowy [% ref]": final.min(),
                             "it. do 99% końcowego": float(np.median(to99))})
            name = f"e2_conv_n{n}_{sp}_{t0.replace(':', '')}.png"
            plots.curves(series, self.fig / name,
                         f"E2: N={n}, {sp}, {t0}, T_max={b} (mean, 10-90% band)", "iteration",
                         "best profit [% of best found]", band=band, logx=True)
            self.img(name, "E2 zbieżność")
        self.out.append(md(pd.DataFrame(rows), "{:.2f}", index=False))
        self.out.append("")
        self.concl("E2")

    # ------------------------------------------------------------ E4
    def e4(self) -> None:
        df = load(self.res, "E4")
        if df is None:
            return
        self.h("## E4. Wrażliwość parametrów i decyzje projektowe")
        inst = ["start_point", "t0"]
        grid = df[df["variant_label"] == "grid"].copy()
        best = grid.groupby(inst + ["lam"])["profit"].max().rename("best")
        grid = grid.join(best, on=inst + ["lam"])
        grid["gap"] = (grid["best"] - grid["profit"]) / grid["best"] * 100
        self.p("ACS-A, N = 50, 4 instancje, 30 ziaren. Luka liczona do najlepszego zysku dla tej "
               "samej instancji i tej samej wartości λ (λ zmienia funkcję celu).")
        for par in ("beta", "q0", "m", "lam"):
            t = grid.groupby(par).agg(gap_pct=("gap", "mean"), profit=("profit", "mean"),
                                      avg_crowd=("avg_crowd", "mean"), time_s=("time_s", "mean"))
            self.p(f"Efekt główny `{par}`:")
            self.out.append(md(t, "{:.3f}"))
            self.out.append("")
        sub = grid[grid["lam"] == 0.8]
        hm = sub.pivot_table(index="q0", columns="beta", values="gap", aggfunc="mean")
        plots.heatmap(hm.to_numpy(), [f"q0={v}" for v in hm.index],
                      [f"beta={v}" for v in hm.columns], self.fig / "e4_q0_beta.png",
                      "E4: mean gap [%] (ACS-A, lambda=0.8, mean over m)", "gap [%]",
                      cmap="viridis_r")
        self.img("e4_q0_beta.png", "E4 q0 beta")
        design = df[df["variant_label"] == "design"].copy()
        best = design.groupby(inst)["profit"].max().rename("best")
        design = design.join(best, on=inst)
        design["gap"] = (design["best"] - design["profit"]) / design["best"] * 100
        t = design.groupby(["tau0_mode", "local_search", "q0"]).agg(
            gap_pct=("gap", "mean"), gap_max=("gap", "max"), time_s=("time_s", "mean"))
        self.p("Decyzje D1 (wzór τ_0) i D9 (przeszukiwanie lokalne), λ = 0,8:")
        self.out.append(md(t, "{:.3f}"))
        self.out.append("")
        self.concl("E4")

    # ------------------------------------------------------------ E5-E8
    def e5(self) -> None:
        df = load(self.res, "E5")
        if df is None:
            return
        self.h("## E5. Godzina startu")
        cats: list[str] = []
        recs = []
        for _, r in df.iterrows():
            for x in rows_of(r):
                recs.append({"t0": r["t0"], "category": x["category"]})
                if x["category"] not in cats:
                    cats.append(x["category"])
        v = pd.DataFrame(recs)
        share = (v.groupby(["category", "t0"]).size()
                 / df.groupby("t0").size().reindex(v["t0"].unique())).unstack("t0")
        share = share.reindex(columns=sorted(share.columns, key=parse_hhmm)).fillna(0)
        plots.heatmap(share.to_numpy(), list(share.index), list(share.columns),
                      self.fig / "e5_category_by_start.png",
                      "E5: share of routes that visit a category (N=100, 4 h, persona balanced)",
                      "share of routes")
        self.img("e5_category_by_start.png", "E5 mapa ciepła")
        t = df.groupby("t0").agg(profit=("profit", "mean"), visits=("n_visits", "mean"),
                                 avg_crowd=("avg_crowd", "mean"))
        t = t.reindex(sorted(t.index, key=parse_hhmm))
        self.out.append(md(t.T, "{:.2f}"))
        self.out.append("")
        self.concl("E5")

    def e6(self) -> None:
        df = load(self.res, "E6")
        if df is None:
            return
        self.h("## E6. Preferencje (persony)")
        df["vset"] = df["route"].fillna("").map(lambda s: frozenset(s.split(";")) - {""})

        def jac(a, b):
            return len(a & b) / len(a | b) if a | b else 1.0

        named = df[~df["persona"].str.startswith("random")]
        rows = []
        for p, g in named.groupby("persona"):
            sets = list(g["vset"])
            within = np.mean([jac(a, b) for a, b in combinations(sets, 2)])
            cats = pd.Series(";".join(g["categories"].fillna("")).split(";")).value_counts()
            rows.append({"persona": p, "zysk": g["profit"].mean(), "wizyty": g["n_visits"].mean(),
                         "Jaccard (ziarna)": within,
                         "najczęstsze kategorie": ", ".join(cats.index[:4])})
        self.out.append(md(pd.DataFrame(rows), "{:.3f}", index=False))
        self.out.append("")
        ps = sorted(named["persona"].unique())
        m = np.zeros((len(ps), len(ps)))
        for i, a in enumerate(ps):
            for j, b in enumerate(ps):
                sa = list(named.loc[named["persona"] == a, "vset"])
                sb = list(named.loc[named["persona"] == b, "vset"])
                m[i, j] = np.mean([jac(x, y) for x in sa for y in sb])
        plots.heatmap(m, ps, ps, self.fig / "e6_jaccard.png",
                      "E6: mean Jaccard similarity of routes between personas", "Jaccard")
        self.img("e6_jaccard.png", "E6 Jaccard")
        rnd = df[df["persona"].str.startswith("random")]
        if len(rnd):
            first = rnd.groupby("persona")["vset"].first().tolist()
            between = np.mean([jac(a, b) for a, b in combinations(first, 2)])
            self.p(f"{rnd['persona'].nunique()} losowych profili u_c ~ U(0, 1): średni Jaccard "
                   f"między profilami = {between:.3f}; liczba różnych tras = "
                   f"{len(set(first))}.")
        self.concl("E6")

    def e7(self) -> None:
        df = load(self.res, "E7")
        if df is None:
            return
        self.h("## E7. Punkt startu")
        df["vset"] = df["route"].fillna("").map(lambda s: frozenset(s.split(";")) - {""})
        sps = list(dict.fromkeys(df["start_point"]))
        m = np.zeros((len(sps), len(sps)))
        for i, a in enumerate(sps):
            for j, b in enumerate(sps):
                sa = list(df.loc[df["start_point"] == a, "vset"])
                sb = list(df.loc[df["start_point"] == b, "vset"])
                m[i, j] = np.mean([len(x & y) / max(len(x | y), 1) for x in sa for y in sb])
        t = df.groupby("start_point").agg(profit=("profit", "mean"), visits=("n_visits", "mean"),
                                          budget_use=("budget_use", "mean"),
                                          avg_crowd=("avg_crowd", "mean"))
        self.out.append(md(t, "{:.3f}"))
        self.out.append("")
        plots.heatmap(m, sps, sps, self.fig / "e7_jaccard.png",
                      "E7: mean Jaccard similarity of routes between start points", "Jaccard")
        self.img("e7_jaccard.png", "E7 Jaccard")
        self.concl("E7")

    def e8(self) -> None:
        df = load(self.res, "E8")
        if df is None:
            return
        self.h("## E8. Stabilność danych (bootstrap)")
        boot = df[df["profiles_key"] != "profiles"]
        n_routes = len(boot)
        cnt = pd.Series(";".join(boot["route"].fillna("")).split(";")).value_counts()
        cnt = cnt[cnt.index != ""] / n_routes
        core = cnt[cnt >= 0.8]
        full = df[df["profiles_key"] == "profiles"]["profit"].mean()
        loss = (full - boot["profit_full_data"]) / full * 100
        self.p(f"{boot['profiles_key'].nunique()} wersji bootstrap × "
               f"{boot['seed'].nunique()} ziaren = {n_routes} tras. Stabilny rdzeń "
               f"(miejsca w ≥ 80% tras): {len(core)} miejsc. Średnia liczba wizyt na trasie: "
               f"{boot['n_visits'].mean():.2f}.")
        cat_of = {}
        for _, r in boot.iterrows():
            for x in rows_of(r):
                cat_of[x["venue_id"]] = x["category"]
        top = pd.DataFrame({"udział tras": cnt.head(10),
                            "kategoria": [cat_of.get(v, "?") for v in cnt.head(10).index]})
        top.index.name = "venue_id"
        self.out.append(md(top, "{:.2f}"))
        self.out.append("")
        self.p(f"Trasa z profilu bootstrap oceniona na profilu z pełnych danych traci średnio "
               f"{loss.mean():.2f}% zysku (maks. {loss.max():.2f}%) względem trasy planowanej na "
               f"pełnych danych.")
        self.concl("E8")

    # ------------------------------------------------------------ E10-E13
    def e10(self, info: dict) -> None:
        df = load(self.res, "E10")
        if df is None:
            return
        self.h("## E10. Zdarzenie znane rano (skok tłoku 10:00-13:00, np. darmowe wejście)")
        targets = info.get("E10_target", {})
        desc = "; ".join(f"start {t0}: `{v['venue']}` (plan bez zdarzenia: {v['planned_arrival']})"
                         for t0, v in targets.items()) if isinstance(targets, dict) else "?"
        self.p("Miejsce zdarzenia to miejsce, które plan bez zdarzenia (acs_ls, ziarno 0) odwiedza "
               f"w oknie 10:00-13:00, najpierw muzea. {desc}. N = 50, Times Square, 8 h, persona "
               "`culture`, siła s = 1. Kolumny `cel_*` dotyczą miejsca zdarzenia.")
        none = df[df["scenario"] == "none"].groupby("t0")["profit"].mean()
        ev = df[df["scenario"] != "none"].copy()
        ev["koszt"] = ev["t0"].map(none) - ev["profit"]
        t = ev.groupby(["t0", "decay_min", "variant_label"]).agg(
            zysk=("profit", "mean"), koszt=("koszt", "mean"), dozwolona=("feasible", "mean"),
            cel_w_trasie=("target_visited", "mean"),
            cel_w_oknie=("target_in_window", "mean"),
            przybycie=("target_arrival", "mean"))
        t["przybycie"] = t["przybycie"].map(lambda x: "" if np.isnan(x) else fmt_hhmm(x))
        self.out.append(md(t, "{:.3f}"))
        self.out.append("")
        nt = df[df["scenario"] == "none"].groupby("t0").agg(
            zysk=("profit", "mean"), cel_w_trasie=("target_visited", "mean"),
            cel_w_oknie=("target_in_window", "mean"), przybycie=("target_arrival", "mean"))
        nt["przybycie"] = nt["przybycie"].map(lambda x: "" if np.isnan(x) else fmt_hhmm(x))
        self.p("Trasy bez zdarzenia (acs_ls, 30 ziaren):")
        self.out.append(md(nt, "{:.3f}"))
        self.out.append("")
        for t0 in sorted(df["t0"].unique()):
            target = targets.get(t0, {}).get("venue") if isinstance(targets, dict) else None
            routes = []
            base_job = {"exp": "E10", "n": 50, "start_point": "times_square", "t0": t0,
                        "budget": 480, "persona": "culture", "day_type": "weekday"}
            r0 = df[(df["scenario"] == "none") & (df["t0"] == t0) & (df["seed"] == 0)]
            if len(r0):
                routes.append(("no event", full_rows(base_job,
                                                     [x["venue_id"] for x in rows_of(r0.iloc[0])])))
            for td in sorted(ev["decay_min"].unique()):
                r1 = ev[(ev["t0"] == t0) & (ev["decay_min"] == td) & (ev["seed"] == 0)
                        & (ev["method"] == "acs_ls")]
                if len(r1):
                    sc = {"name": "x", "events": [{"type": "crowd_surge", "venue": target,
                                                   "window": ["10:00", "13:00"], "strength": 1.0,
                                                   "decay_min": int(td)}]}
                    routes.append((f"surge, T_d={td} ({r1.iloc[0]['profit']:.3f})",
                                   full_rows({**base_job, "scenario": sc},
                                             [x["venue_id"] for x in rows_of(r1.iloc[0])])))
            name = f"e10_timeline_{t0.replace(':', '')}.png"
            plots.route_timeline(routes, self.fig / name,
                                 f"E10: start {t0}, acs_ls seed 0 (thick border = event venue)",
                                 window=(600, 780), highlight=target)
            self.img(name, "E10 oś czasu")
        self.concl("E10")

    def e11(self, info: dict) -> None:
        df = load(self.res, "E11")
        if df is None:
            return
        tgt = info.get("E11_target", {})
        self.h("## E11. Zdarzenie w trakcie dnia (ogłoszone o 11:00)")
        self.p(f"Skok tłoku 10:00-13:00 (s = 1, T_d = 60 min) w miejscu `{tgt.get('venue', '?')}`, "
               f"które plan poranny (acs_ls, ziarno 0) odwiedza o {tgt.get('planned_arrival', '?')}."
               f" Ponowne planowanie: 50 iteracji. `fixed` = plan bez zdarzenia bez zmian.")
        none = df[df["scenario"] == "none"]["profit"].mean()
        known = df[df["scenario"] == "surge_known"]["profit"].mean()
        ann = df[df["scenario"] == "surge_announced"].copy()
        t = ann.groupby("variant_label").agg(zysk=("profit", "mean"), std=("profit", "std"),
                                             dozwolona=("feasible", "mean"),
                                             cel_w_trasie=("target_visited", "mean"),
                                             cel_w_oknie=("target_in_window", "mean"))
        t["koszt vs bez zdarzenia"] = none - t["zysk"]
        t["strata vs wiedza rano"] = known - t["zysk"]
        self.p(f"Zysk bez zdarzenia: {none:.4f}. Zysk, gdy zdarzenie jest znane rano: "
               f"{known:.4f}.")
        self.out.append(md(t, "{:.4f}"))
        self.out.append("")
        hist = [h for h in load_hist(self.res, "E11") if h["kind"] == "replan_history"]
        if hist:
            series, rows = {}, []
            by_seed: dict = {}
            for h in hist:
                base = h["label"].rsplit("_", 1)[0]
                by_seed.setdefault((base, h["seed"]), []).append(h)
            for label in sorted({h["label"] for h in hist}):
                base = label.rsplit("_", 1)[0]
                curves_, it95, it100 = [], [], []
                for h in [x for x in hist if x["label"] == label]:
                    ref = max(max(x["values"]) for x in by_seed[(base, h["seed"])])
                    v = np.array(h["values"]) / ref * 100
                    curves_.append(v)
                    it95.append(int(np.argmax(v >= 95.0)) + 1 if (v >= 95.0).any() else np.nan)
                    hit = v >= 100.0 - 1e-9
                    it100.append(int(np.argmax(hit)) + 1 if hit.any() else np.nan)
                arr = np.array(curves_)
                series[label] = arr.mean(axis=0)
                rows.append({"wariant": label, "zysk po 1 it. [% ref]": arr[:, 0].mean(),
                             "po 5 it.": arr[:, 4].mean(), "po 10 it.": arr[:, 9].mean(),
                             "po 50 it.": arr[:, -1].mean(),
                             "it. do 95% ref (mediana)": float(np.nanmedian(it95)),
                             "it. do 100% ref (średnia)": float(np.nanmean(it100)),
                             "ref osiągnięty [% uruchomień]": 100 * np.mean(~np.isnan(it100))})
            self.p("Krzywa powrotu po zdarzeniu. Ref = najlepszy zysk podproblemu z wariantu "
                   "zimnego i ciepłego dla tego samego ziarna i tej samej metody. Iteracja 1 "
                   "zaczyna od trasy zachłannej podproblemu, więc próg 95% jest łatwy; "
                   "kolumna „it. do 100% ref” lepiej różnicuje warianty:")
            self.out.append(md(pd.DataFrame(rows), "{:.2f}", index=False))
            self.out.append("")
            plots.curves(series, self.fig / "e11_recovery.png",
                         "E11: replanning after the 11:00 announcement (mean over seeds)",
                         "iteration after the event", "best sub-route profit [% of ref]")
            self.img("e11_recovery.png", "E11 krzywa powrotu")
        self.concl("E11")

    def e12(self, info: dict) -> None:
        df = load(self.res, "E12")
        if df is None:
            return
        self.h("## E12. Zamknięcie miejsca i utrudnienie w ruchu")
        self.p(f"Zamknięte 08:00-12:00: pierwsze miejsce planu bez zdarzeń "
               f"(`{info.get('E12_closed_venue', '?')}`). Parada: Times Square, promień 400 m, "
               f"12:00-15:00, mnożnik czasu przejścia 2. Zdarzenia są znane rano.")
        none = df[df["scenario"] == "none"]["profit"].mean()
        t = df[df["scenario"] != "none"].groupby(["scenario", "variant_label"]).agg(
            zysk=("profit", "mean"), dozwolona=("feasible", "mean"),
            zamkniete_w_trasie=("target_visited", "mean"), wizyty=("n_visits", "mean"))
        t["koszt"] = none - t["zysk"]
        self.p(f"Zysk bez zdarzeń: {none:.4f}. Trasa `fixed` z naruszeniem ograniczeń jest "
               f"niewykonalna w rzeczywistości; jej zysk podano tylko dla porównania.")
        self.out.append(md(t, "{:.4f}"))
        self.out.append("")
        self.concl("E12")

    def e13(self) -> None:
        self.h("## E13. Rola antyferomonu (acs_ls vs acs_ls+nophi)")
        rows = []
        for e, keys in (("E10", ["t0", "decay_min", "seed"]), ("E11", ["seed", "warm"]),
                        ("E12", ["scenario", "seed"])):
            df = load(self.res, e)
            if df is None:
                continue
            df = df[df["scenario"] != "none"]
            if e == "E11":
                df = df[df["scenario"] == "surge_announced"]
            a = df[df["method"] == "acs_ls"].set_index(keys)["profit"]
            b = df[df["method"] == "acs_ls+nophi"].set_index(keys)["profit"]
            j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
            if len(j):
                r = paired(j["a"].to_numpy(), j["b"].to_numpy())
                rows.append({"eksperyment": e, "pary": r["n"], "śr. różnica (z φ − bez φ)":
                             r["mean_diff"], "z φ lepszy": r["wins"], "remis": r["ties"],
                             "bez φ lepszy": r["losses"], "p (Wilcoxon)": pstr(r["p"])})
        self.out.append(md(pd.DataFrame(rows), "{:.4f}", index=False))
        self.out.append("")
        self.e13_maps()
        self.concl("E13")

    def e13b(self, info: dict) -> None:
        df = load(self.res, "E13b")
        if df is None:
            return
        tgt = info.get("E13b_target", {})
        self.h("## E13b. Antyferomon przy szybkim ponownym planowaniu")
        self.p("Scenariusz: start 09:00 (Times Square, N = 100, 8 h, persona `culture`), zdarzenie "
               f"ogłoszone o 10:23 i aktywne do 15:00. Zdarzenie trafia w pierwsze przejście planu "
               f"bez zdarzeń po 10:23 (wyjście o {tgt.get('planned_departure', '?')}) i w miejsce "
               f"`{tgt.get('venue', '?')}` na końcu tego przejścia. Trzy typy: `accident` (wypadek: "
               "promień 250 m, czas przejścia ×50), `closure` (zamknięcie miejsca), `surge` (skok "
               "tłoku). Ponowne planowanie ma 10 albo 50 iteracji, z ciepłym albo zimnym startem. "
               "`g0`/`g1`/`g3` = γ; `phidoc` = antyferomon ze zdarzeń tylko dla skoku tłoku "
               "(docs 4.4), bez `phidoc` = także dla wypadku i zamknięcia.")
        df["warm_s"] = np.where(df["warm"].astype(str) == "True", "warm", "cold")
        t = df.pivot_table(index=["scenario", "group"], columns=["replan_it", "warm_s"],
                           values="profit", aggfunc="mean")
        t.columns = [f"zysk it{a} {b}" for a, b in t.columns]
        feas = df.groupby(["scenario", "group"])["feasible"].mean().rename("dozwolona")
        self.out.append(md(t.join(feas), "{:.4f}"))
        self.out.append("")

        rows = []
        for (sc, it, w), g in df.groupby(["scenario", "replan_it", "warm_s"]):
            p = g.pivot_table(index="seed", columns="group", values="profit")
            for a, b in (("acs_a_g1", "acs_a_g0"), ("acs_a_g3", "acs_a_g0"),
                         ("acs_a_g1", "acs_a_g1_phidoc"), ("acs_ls_g1", "acs_ls_g0")):
                if a in p and b in p:
                    r = paired(p[a].to_numpy(), p[b].to_numpy())
                    rows.append({"zdarzenie": sc, "it.": it, "start": w, "A": a, "B": b,
                                 "śr. różnica A − B": r["mean_diff"], "A lepsza": r["wins"],
                                 "remis": r["ties"], "B lepsza": r["losses"],
                                 "p": pstr(r["p"])})
        self.p("Pary według ziarna (końcowy zysk całego dnia, ocena na prawdzie):")
        self.out.append(md(pd.DataFrame(rows), "{:.4f}", index=False))
        self.out.append("")

        hist = [h for h in load_hist(self.res, "E13b") if h["kind"] == "replan_history"]
        if hist:
            key = df.set_index("key")[["scenario", "group", "replan_it", "warm_s"]]
            ref: dict = {}
            for h in hist:
                sc, grp = key.loc[h["key"], ["scenario", "group"]]
                k = (sc, grp, h["seed"])
                ref[k] = max(ref.get(k, -1.0), max(h["values"]))
            recs = []
            for h in hist:
                sc, grp, it, w = key.loc[h["key"]]
                v = np.array(h["values"]) / ref[(sc, grp, h["seed"])] * 100
                recs.append({"zdarzenie": sc, "wariant": grp, "it.": it, "start": w,
                             "po 1 it.": v[0], "po 5 it.": v[min(4, len(v) - 1)],
                             "na końcu": v[-1]})
            r = pd.DataFrame(recs).groupby(["zdarzenie", "wariant", "it.", "start"]).mean()
            self.p("Zysk podproblemu po 1, 5 iteracjach i na końcu, w % najlepszego zysku tego "
                   "podproblemu (to samo ziarno i ten sam wariant, wszystkie ustawienia "
                   "iteracji i startu):")
            self.out.append(md(r, "{:.2f}"))
            self.out.append("")
        self.concl("E13b")

    def e13_maps(self) -> None:
        """tau and phi before and after the E11 event (acs_ls, seed 0)."""
        info = json.loads((self.res / "experiment_info.json").read_text())
        tgt = info.get("E11_target", {}).get("venue")
        if not tgt:
            return
        from antroute.experiments.common import build_problem, make_solver
        from antroute.solvers.aco import aco_params, event_antipheromone
        from antroute.solvers.replan import plan_day

        job = {"exp": "E11", "n": 50, "start_point": "times_square", "t0": "08:00",
               "budget": 480, "persona": "culture", "day_type": "weekday",
               "scenario": {"name": "s", "events": [
                   {"type": "crowd_surge", "venue": tgt, "window": ["10:00", "13:00"],
                    "strength": 1.0, "decay_min": 60, "announced": "11:00"}]}}
        p = build_problem(job)
        day = plan_day(p, make_solver("acs_ls", 0, None), warm=True)
        if len(day.plans) < 2 or day.plans[1].get("result") is None:
            return
        a = aco_params(_cfg(), "acs_ls")
        nb = int(a["horizon_minutes"] // a["bin_minutes"])
        b = int(parse_hhmm("11:30") // a["bin_minutes"])
        inst = p.instance
        node = inst.node_of(tgt)
        before, after = day.plans[0]["result"], day.plans[1]["result"]
        phi_b = event_antipheromone(p.with_events(480), a["phi_max"], a["bin_minutes"], nb) \
            + before.phi_ants
        phi_a = event_antipheromone(p.with_events(660), a["phi_max"], a["bin_minutes"], nb) \
            + after.phi_ants
        plots.pheromone_map(inst.lat, inst.lon, before.tau, before.route,
                            self.fig / "e13_map_before.png",
                            "E13: morning plan - top 5% tau edges, phi at 11:30",
                            phi_node=phi_b[:, b])
        sub_route = [day.plans[1]["start_node"]] + list(after.route)
        plots.pheromone_map(inst.lat, inst.lon, after.tau, day.route,
                            self.fig / "e13_map_after.png",
                            "E13: after replanning at 11:00 - tau edges, phi at 11:30",
                            phi_node=phi_a[:, b])
        cols = range(int(480 // a["bin_minutes"]), int(1200 // a["bin_minutes"]))
        nodes = sorted(set(before.route) | set(sub_route) | {node})
        mat = np.vstack([phi_b[nodes][:, cols], phi_a[nodes][:, cols]])
        labels = ([f"before: {inst.categories[inst.cat[j]]} #{j}" for j in nodes]
                  + [f"after: {inst.categories[inst.cat[j]]} #{j}" for j in nodes])
        plots.heatmap(mat, labels, [fmt_hhmm(c * a["bin_minutes"]) for c in cols],
                      self.fig / "e13_phi.png",
                      f"E13: antipheromone phi per 30-min bin (event venue #{node})", "phi",
                      cmap="Reds")
        self.img("e13_map_before.png", "E13 mapa przed")
        self.img("e13_map_after.png", "E13 mapa po")
        self.img("e13_phi.png", "E13 antyferomon")

    # ------------------------------------------------------------ main
    def build(self, tests: dict | None) -> str:
        info_path = self.res / "experiment_info.json"
        info = json.loads(info_path.read_text()) if info_path.exists() else {}
        body_start = len(self.out)
        self.e1()
        self.e2()
        self.e4()
        self.e5()
        self.e6()
        self.e7()
        self.e8()
        self.e10(info)
        self.e11(info)
        self.e12(info)
        self.e13()
        self.e13b(info)
        body = self.out[body_start:]
        head = ["# AntRoute PoC - wyniki eksperymentów", "",
                f"Wygenerowano: {date.today().isoformat()}, wersja kodu: "
                f"`{info.get('code_version', '?')}`. Plik generuje "
                f"`python -m antroute.report.summary` z plików `results/*/results.csv`.", "",
                "Wszystkie zyski liczy jedna funkcja `antroute/model/evaluate.py` na problemie ze "
                "wszystkimi zdarzeniami (prawda), z λ = 0,8, chyba że tabela mówi inaczej.", ""]
        head += ["## Kryteria ukończenia v1", "", "| Kryterium | Wynik |", "| --- | --- |"]
        tests = tests or {}
        crit = {
            "K1": "tak: `python run_all.py` (dane → profile → eksperymenty → raport)",
            "K2": tests.get("K2", "zobacz `tests/test_data_profiles.py`"),
            "K3": tests.get("K3", "zobacz `tests/test_evaluate.py`"),
            "K4": tests.get("K4", "zobacz `tests/test_solvers.py`"),
            "K5": self.k.get("K5", "brak wyników E1"),
            "K6": self.k.get("K6", "brak wyników CP-SAT"),
            "K7": tests.get("K7", "zobacz `tests/test_solvers.py`"),
            "K8": tests.get("K8", "zobacz `tests/test_evaluate.py`, `tests/test_solvers.py`"),
            "K9": "tak: ten plik",
        }
        head += [f"| {k} | {v} |" for k, v in crit.items()]
        head += ["", self.notes.get("decyzje", "").strip(), ""]
        return "\n".join(head + body) + "\n"


def _cfg():
    from antroute.experiments.common import cfg

    return cfg()


def test_status() -> dict:
    """Run pytest once and map the result to criteria K2, K3, K4, K7, K8."""
    import subprocess

    r = subprocess.run(["python", "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True)
    last = r.stdout.strip().splitlines()[-1].strip("= ") if r.stdout.strip() else "?"
    ok = r.returncode == 0
    s = f"{'tak' if ok else 'NIE'}: pytest - {last}"
    import os

    cov = subprocess.run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "-o", "addopts=", "tests/test_evaluate.py", "--cov=antroute.model.evaluate",
                          "--cov-report=term"], cwd=ROOT, capture_output=True, text=True,
                         env={**os.environ, "NUMBA_DISABLE_JIT": "1"})
    m = re.search(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", cov.stdout, flags=re.M)
    pct = int(m.group(1)) if m else -1
    return {"K2": s + " (`test_k2_hourly_counts_match_reference`)",
            "K3": (f"{'tak' if ok and pct >= 90 else 'NIE'}: pokrycie `evaluate.py` = {pct}% "
                   f"(cel ≥ 90%, pomiar z `NUMBA_DISABLE_JIT=1`); {last}"),
            "K4": s + " (`test_k4_acs_finds_brute_force_optimum`, ACS-LS)",
            "K7": s + " (`test_k7_same_seed_same_route`)",
            "K8": s + " (testy zdarzeń i ponownego planowania)"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--no-tests", action="store_true")
    a = ap.parse_args()
    res = ROOT / a.results
    tests = None if a.no_tests else test_status()
    text = Summary(res).build(tests)
    (res / "SUMMARY.md").write_text(text, encoding="utf-8")
    print(f"written {res / 'SUMMARY.md'}")


if __name__ == "__main__":
    main()
