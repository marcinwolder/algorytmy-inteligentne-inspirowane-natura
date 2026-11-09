"""WP10: simple matplotlib plots (PNG, no styling) and an optional folium route map."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from antroute.config import fmt_hhmm  # noqa: E402


def _hour_axis(ax, t_min, t_max):
    ticks = np.arange(np.floor(t_min / 60) * 60, t_max + 60, 60)
    ax.set_xticks(ticks)
    ax.set_xticklabels([fmt_hhmm(t) for t in ticks], rotation=45, fontsize=8)


def route_timeline(routes: list[tuple[str, list[dict]]], path: Path, title: str = "",
                   window: tuple[float, float] | None = None, highlight: str | None = None,
                   ) -> None:
    """Gantt chart: one row per route; bars = stays coloured by crowd C_i(a_i)."""
    fig, ax = plt.subplots(figsize=(11, 1.1 + 0.8 * len(routes)))
    cmap = plt.get_cmap("RdYlGn_r")
    lo, hi = 1e9, 0.0
    for y, (_label, rows) in enumerate(routes):
        for r in rows:
            a, s = r["arrival"], r["stay"]
            lo, hi = min(lo, a), max(hi, a + s)
            ax.barh(y, s, left=a, color=cmap(min(r["crowd"], 1.0)),
                    edgecolor="black" if r["venue_id"] == highlight else "grey",
                    linewidth=2.5 if r["venue_id"] == highlight else 0.5)
            ax.text(a + s / 2, y, r["category"].replace(" ", "\n"), ha="center", va="center",
                    fontsize=6)
    if window:
        ax.axvspan(window[0], window[1], color="purple", alpha=0.12, label="event window")
        ax.legend(loc="upper right", fontsize=7)
    ax.set_yticks(range(len(routes)))
    ax.set_yticklabels([r[0] for r in routes], fontsize=8)
    ax.invert_yaxis()
    _hour_axis(ax, lo, hi)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
    fig.colorbar(sm, ax=ax, label="crowd C at arrival", pad=0.01)
    ax.set_title(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def curves(series: dict[str, np.ndarray], path: Path, title: str, xlabel: str, ylabel: str,
           band: dict[str, tuple[np.ndarray, np.ndarray]] | None = None, logx: bool = False,
           ) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    for label, y in series.items():
        x = np.arange(1, len(y) + 1)
        ax.plot(x, y, label=label, linewidth=1.3)
        if band and label in band:
            ax.fill_between(x, band[label][0], band[label][1], alpha=0.15)
    if logx:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=9)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def boxplot(groups: dict[str, np.ndarray], path: Path, title: str, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.boxplot(list(groups.values()), showfliers=False)
    ax.set_xticks(range(1, len(groups) + 1))
    ax.set_xticklabels(list(groups), rotation=20, fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def heatmap(mat: np.ndarray, rows: list[str], cols: list[str], path: Path, title: str,
            cbar: str, fmt: str = "{:.2f}", cmap: str = "viridis") -> None:
    fig, ax = plt.subplots(figsize=(1.2 + 0.55 * len(cols), 1.2 + 0.4 * len(rows)))
    im = ax.imshow(mat, aspect="auto", cmap=cmap)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, fontsize=8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=8)
    if mat.size <= 300:
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                if np.isfinite(mat[i, j]):
                    ax.text(j, i, fmt.format(mat[i, j]), ha="center", va="center", fontsize=6,
                            color="white" if mat[i, j] < np.nanmean(mat) else "black")
    fig.colorbar(im, ax=ax, label=cbar)
    ax.set_title(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def pheromone_map(lat, lon, tau: np.ndarray, route: list[int], path: Path, title: str,
                  phi_node: np.ndarray | None = None, top: float = 0.05) -> None:
    """Strongest tau edges (top share), best route, nodes coloured by antipheromone."""
    fig, ax = plt.subplots(figsize=(5, 6))
    t = tau.max(axis=0) if tau.ndim == 3 else tau
    t = t / t.max()
    thr = np.quantile(t[t > 0], 1 - top)
    for i, j in zip(*np.nonzero(t >= thr), strict=True):
        ax.plot([lon[i], lon[j]], [lat[i], lat[j]], color="tab:blue", alpha=0.2 + 0.6 * t[i, j],
                linewidth=0.5 + 2 * t[i, j])
    path_nodes = [0] + list(route) + [0]
    ax.plot(lon[path_nodes], lat[path_nodes], color="black", linewidth=2, label="best route")
    c = phi_node if phi_node is not None else np.zeros(len(lat))
    sc = ax.scatter(lon[1:], lat[1:], c=c[1:], cmap="Reds", s=18, edgecolors="grey",
                    linewidths=0.3, zorder=3)
    ax.scatter([lon[0]], [lat[0]], marker="*", s=150, color="gold", edgecolors="black", zorder=4,
               label="start")
    fig.colorbar(sc, ax=ax, label="antipheromone phi (current bin)", shrink=0.7)
    ax.set_title(title, fontsize=9)
    ax.legend(fontsize=7, loc="lower right")
    ax.set_aspect(1 / np.cos(np.radians(np.mean(lat))))
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def folium_route(problem, rows: list[dict], path: Path) -> None:
    """Optional (S): plain HTML map of one route."""
    import folium

    inst = problem.instance
    start = (inst.lat[0], inst.lon[0])
    m = folium.Map(location=start, zoom_start=14, tiles="cartodbpositron")
    folium.Marker(start, tooltip="start").add_to(m)
    pts = [start]
    for k, r in enumerate(rows, 1):
        j = r["node"]
        pts.append((inst.lat[j], inst.lon[j]))
        folium.CircleMarker((inst.lat[j], inst.lon[j]), radius=7, fill=True,
                            tooltip=f"{k}. {fmt_hhmm(r['arrival'])} {r['category']} "
                                    f"crowd={r['crowd']:.2f} profit={r['profit']:.3f}").add_to(m)
    pts.append(start)
    folium.PolyLine(pts, weight=3).add_to(m)
    m.save(str(path))
