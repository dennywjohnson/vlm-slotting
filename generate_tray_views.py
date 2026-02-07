"""
Generate 2D tray cell grid views of VLM slotting results.

Produces two types of visualizations:
  1. Tower overview heatmap — all 3 towers side-by-side, each tray as a row
     of cells color-coded by weekly picks. Golden zone highlighted.
  2. Detailed tray grids — zoomed-in view of sample trays for each config,
     showing SKU details per cell (wraps into rows for 16+ cell configs).

Reads slotting_map.csv (output of slotting.py).
"""

import csv
import math
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
import numpy as np


CMAP = plt.get_cmap("RdYlGn_r")  # Red = high picks, Green = low


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def load_slotting_map(path="slotting_map.csv"):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "tower": int(r["Tower"]),
                "tray": int(r["Tray"]),
                "cell": int(r["Cell"]),
                "tray_config": r["Tray_Config"],
                "sku": r["SKU"],
                "desc": r["Description"],
                "picks": int(r["Weekly_Picks"]),
                "eaches": int(r["Eaches"]),
                "weight_each": float(r["Weight_Each_lbs"]),
                "cell_weight": float(r["Cell_Weight_lbs"]),
                "total_vol": float(r["Total_Vol_in3"]),
                "cell_vol": float(r["Cell_Vol_in3"]),
                "zone": r["Tray_Zone"],
                "bin": r["Bin_Label"],
            })
    return rows


def build_tray_index(rows):
    """Index: (tower, tray) -> sorted list of cell dicts."""
    idx = defaultdict(list)
    for r in rows:
        idx[(r["tower"], r["tray"])].append(r)
    for k in idx:
        idx[k].sort(key=lambda c: c["cell"])
    return idx


# ---------------------------------------------------------------------------
# 1. Tower overview heatmap
# ---------------------------------------------------------------------------
def generate_tower_overview(rows, output_path="tray_overview.png",
                            golden_start=20, golden_end=35):
    tray_idx = build_tray_index(rows)

    towers = sorted(set(r["tower"] for r in rows))
    all_trays = sorted(set(r["tray"] for r in rows))
    min_tray, max_tray = min(all_trays), max(all_trays)
    num_trays = max_tray - min_tray + 1

    all_picks = [r["picks"] for r in rows]
    max_picks = max(all_picks) if all_picks else 1
    norm = Normalize(vmin=0, vmax=max_picks)

    # Collect config labels for each tray across all towers (for the left labels)
    tray_config_labels = {}
    for (tower, tray), cells in tray_idx.items():
        if cells and tray not in tray_config_labels:
            tray_config_labels[tray] = cells[0]["tray_config"]

    # Figure sizing — wider left margin for config labels
    tower_width = 5.5
    fig_w = len(towers) * tower_width + 5.0
    row_h = 0.30
    fig_h = num_trays * row_h + 4.0

    fig = plt.figure(figsize=(fig_w, fig_h))

    # Create axes with extra left margin for config labels
    left_margin = 0.12
    axes = []
    usable_w = 1.0 - left_margin - 0.04
    tw = usable_w / len(towers) * 0.88
    gap = usable_w / len(towers) * 0.12
    for ti in range(len(towers)):
        x0 = left_margin + ti * (tw + gap)
        ax = fig.add_axes([x0, 0.08, tw, 0.85])
        axes.append(ax)

    fig.suptitle("VLM Tower Overview — Tray Cell Heatmap by Weekly Picks",
                 fontsize=16, fontweight="bold", y=0.97)

    for ti, tower_num in enumerate(towers):
        ax = axes[ti]
        ax.set_title(f"Tower {tower_num}", fontsize=13, fontweight="bold",
                     pad=10)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, num_trays)
        ax.set_yticks([t - min_tray + 0.5 for t in range(min_tray, max_tray + 1)])
        ax.set_yticklabels([str(t) for t in range(min_tray, max_tray + 1)],
                           fontsize=6.5)
        ax.set_xticks([])
        ax.invert_yaxis()
        ax.tick_params(axis="y", length=0, pad=4)

        if ti == 0:
            ax.set_ylabel("Tray #", fontsize=10, labelpad=8)

        # Golden zone band — more visible
        gz_y_start = golden_start - min_tray
        gz_y_end = golden_end - min_tray + 1
        ax.axhspan(gz_y_start, gz_y_end, color="#FFD700", alpha=0.22,
                    zorder=0)
        ax.axhline(gz_y_start, color="#B8860B", linewidth=1.5, linestyle="--",
                    zorder=5)
        ax.axhline(gz_y_end, color="#B8860B", linewidth=1.5, linestyle="--",
                    zorder=5)

        # Golden zone label on right side of last tower
        if ti == len(towers) - 1:
            gz_mid = (gz_y_start + gz_y_end) / 2
            ax.annotate("GOLDEN\nZONE", xy=(1.0, gz_mid),
                        xycoords=("axes fraction", "data"),
                        xytext=(8, 0), textcoords="offset points",
                        fontsize=8, color="#8B6914", fontweight="bold",
                        va="center", ha="left")

        for tray_num in range(min_tray, max_tray + 1):
            cells = tray_idx.get((tower_num, tray_num), [])
            y = tray_num - min_tray
            if not cells:
                ax.add_patch(mpatches.Rectangle(
                    (0.02, y + 0.08), 0.96, 0.84,
                    facecolor="#f0f0f0", edgecolor="#cccccc",
                    linewidth=0.5, zorder=2))
                continue

            config_str = cells[0]["tray_config"]
            config_cells = int(config_str.split("-")[0])
            cell_w = 0.96 / config_cells
            x_start = 0.02

            filled_map = {c["cell"]: c for c in cells}
            for ci in range(1, config_cells + 1):
                x = x_start + (ci - 1) * cell_w
                if ci in filled_map:
                    c = filled_map[ci]
                    color = CMAP(norm(c["picks"]))
                    ax.add_patch(mpatches.Rectangle(
                        (x, y + 0.08), cell_w - 0.003, 0.84,
                        facecolor=color, edgecolor="#666666",
                        linewidth=0.3, zorder=2))
                    # SKU label only for 6-cell
                    if config_cells <= 6:
                        rr, gg, bb, _ = color
                        bright = 0.299 * rr + 0.587 * gg + 0.114 * bb
                        tc = "white" if bright < 0.55 else "#111111"
                        ax.text(x + cell_w / 2, y + 0.5,
                                c["sku"].replace("WH-", ""),
                                ha="center", va="center", fontsize=4.5,
                                color=tc, fontweight="bold", zorder=3)
                else:
                    ax.add_patch(mpatches.Rectangle(
                        (x, y + 0.08), cell_w - 0.003, 0.84,
                        facecolor="#f8f8f8", edgecolor="#dddddd",
                        linewidth=0.3, zorder=2))

            # Config label — only on Tower 1's left side
            if ti == 0:
                ax.text(-0.04, y + 0.5, config_str,
                        ha="right", va="center", fontsize=5.5,
                        color="#444444", fontweight="bold",
                        transform=ax.get_yaxis_transform(),
                        zorder=3)

    # Colorbar at bottom
    sm = plt.cm.ScalarMappable(cmap=CMAP, norm=norm)
    sm.set_array([])
    cbar_ax = fig.add_axes([0.25, 0.035, 0.50, 0.012])
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
    cbar.set_label("Weekly Picks", fontsize=9, labelpad=4)
    cbar.ax.tick_params(labelsize=7)

    # Legend
    legend_elements = [
        mpatches.Patch(facecolor="#FFD700", alpha=0.35, edgecolor="#B8860B",
                       linewidth=1.5, linestyle="--",
                       label=f"Golden Zone (trays {golden_start}-{golden_end})"),
        mpatches.Patch(facecolor="#f0f0f0", edgecolor="#cccccc",
                       label="Empty / unassigned tray"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=2,
               fontsize=8, frameon=True, bbox_to_anchor=(0.5, 0.0))

    fig.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  Tower overview -> {output_path}")


# ---------------------------------------------------------------------------
# 2. Detailed tray grids — wraps cells into rows for 16+ cell configs
# ---------------------------------------------------------------------------
def _draw_cell(ax, x, y, w, h, cell_data, norm, cell_num, compact=False):
    """Draw a single cell box at (x, y) with width w and height h."""
    c = cell_data
    if c is None:
        # Empty cell
        rect = mpatches.FancyBboxPatch(
            (x + 0.05, y + 0.05), w - 0.1, h - 0.1,
            boxstyle="round,pad=0.03",
            facecolor="#f5f5f5", edgecolor="#cccccc",
            linewidth=0.8, linestyle="--", zorder=2)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, "EMPTY",
                ha="center", va="center", fontsize=6,
                color="#cccccc", fontweight="bold", zorder=3)
        ax.text(x + w / 2, y + 0.01, f"Cell {cell_num}",
                ha="center", va="bottom", fontsize=4.5,
                color="#aaaaaa", zorder=3)
        return

    color = CMAP(norm(c["picks"]))
    vol_pct = min(100, c["total_vol"] / c["cell_vol"] * 100) if c["cell_vol"] > 0 else 0

    rect = mpatches.FancyBboxPatch(
        (x + 0.04, y + 0.04), w - 0.08, h - 0.08,
        boxstyle="round,pad=0.04",
        facecolor=color, edgecolor="#444444",
        linewidth=1.0, zorder=2)
    ax.add_patch(rect)

    # Text color
    rr, gg, bb, _ = color
    brightness = 0.299 * rr + 0.587 * gg + 0.114 * bb
    tc = "white" if brightness < 0.55 else "#222222"

    cx = x + w / 2

    if compact:
        # Compact layout for 16+ cell configs
        fs_sku, fs_desc, fs_info, fs_vol = 6.5, 5, 5.5, 4.5
        line_positions = [0.82, 0.64, 0.48, 0.32, 0.15]
    else:
        fs_sku, fs_desc, fs_info, fs_vol = 7.5, 6, 6.5, 5
        line_positions = [0.85, 0.68, 0.53, 0.38, 0.15]

    # SKU
    ax.text(cx, y + h * line_positions[0], c["sku"],
            ha="center", va="center", fontsize=fs_sku,
            fontweight="bold", color=tc, zorder=3)
    # Description
    max_len = 12 if compact else 16
    desc = c["desc"][:max_len-2] + ".." if len(c["desc"]) > max_len else c["desc"]
    ax.text(cx, y + h * line_positions[1], desc,
            ha="center", va="center", fontsize=fs_desc,
            color=tc, style="italic", zorder=3)
    # Picks
    ax.text(cx, y + h * line_positions[2], f"{c['picks']} picks/wk",
            ha="center", va="center", fontsize=fs_info,
            color=tc, zorder=3)
    # Eaches x weight
    ax.text(cx, y + h * line_positions[3],
            f"{c['eaches']}ea x {c['weight_each']:.2f}lb",
            ha="center", va="center", fontsize=fs_desc,
            color=tc, zorder=3)

    # Volume fill bar
    bar_y = y + h * line_positions[4]
    bar_h = h * 0.08
    bar_full = w - 0.3
    bar_w = bar_full * vol_pct / 100
    ax.add_patch(mpatches.Rectangle(
        (x + 0.15, bar_y - bar_h / 2), bar_full, bar_h,
        facecolor="#ffffff55", edgecolor=tc,
        linewidth=0.5, zorder=3))
    fill_color = "#2ecc40" if vol_pct < 70 else "#ff851b" if vol_pct < 90 else "#ff4136"
    ax.add_patch(mpatches.Rectangle(
        (x + 0.15, bar_y - bar_h / 2), bar_w, bar_h,
        facecolor=fill_color, edgecolor="none", zorder=4))
    ax.text(cx, bar_y, f"{vol_pct:.0f}%",
            ha="center", va="center", fontsize=fs_vol,
            color=tc, fontweight="bold", zorder=5)

    # Cell number below
    ax.text(cx, y + 0.01, f"Cell {cell_num}",
            ha="center", va="bottom", fontsize=4.5,
            color="#888888", zorder=3)


def generate_detailed_tray_views(rows, output_dir="tray_details"):
    os.makedirs(output_dir, exist_ok=True)
    tray_idx = build_tray_index(rows)

    config_trays = defaultdict(list)
    for (tower, tray), cells in tray_idx.items():
        if cells:
            config_trays[cells[0]["tray_config"]].append((tower, tray, cells))

    all_picks = [r["picks"] for r in rows]
    max_picks = max(all_picks) if all_picks else 1
    norm = Normalize(vmin=0, vmax=max_picks)

    for config_str in sorted(config_trays.keys()):
        trays = config_trays[config_str]
        trays.sort(key=lambda t: sum(c["picks"] for c in t[2]), reverse=True)

        # Select 3 sample trays: busiest, median, lightest
        if len(trays) >= 3:
            sample_trays = [trays[0], trays[len(trays) // 2], trays[-1]]
        else:
            sample_trays = trays[:3]

        config_cells = int(config_str.split("-")[0])

        # Determine grid layout for cells
        if config_cells <= 8:
            cols_per_row = config_cells
            compact = False
        elif config_cells <= 16:
            cols_per_row = 8  # 2 rows of 8
            compact = True
        else:
            cols_per_row = 10  # 3 rows of 10
            compact = True

        num_rows_per_tray = math.ceil(config_cells / cols_per_row)

        # Cell box dimensions
        cell_w = max(1.6, min(2.8, 20.0 / cols_per_row))
        cell_h = 1.8 if not compact else 1.5

        # Figure dimensions
        grid_w = cols_per_row * cell_w
        grid_h = num_rows_per_tray * (cell_h + 0.25)  # +gap between rows
        tray_block_h = grid_h + 1.2  # title + padding

        fig_w = grid_w + 1.5
        fig_h = len(sample_trays) * tray_block_h + 2.0

        fig, axes = plt.subplots(len(sample_trays), 1,
                                 figsize=(min(fig_w, 22), fig_h),
                                 squeeze=False)

        fig.suptitle(f"Tray Detail — {config_str} Configuration",
                     fontsize=15, fontweight="bold", y=0.98)

        labels = ["Busiest Tray", "Median Tray", "Lightest Tray"]

        for si, (tower, tray, cells) in enumerate(sample_trays):
            ax = axes[si][0]
            total_picks = sum(c["picks"] for c in cells)
            total_weight = sum(c["cell_weight"] for c in cells)
            zone = cells[0]["zone"] if cells else "?"

            ax.set_title(
                f"{labels[si] if si < len(labels) else 'Tray'}: "
                f"Tower {tower}, Tray {tray}  |  "
                f"{zone} Zone  |  "
                f"{total_picks} picks/wk  |  "
                f"{total_weight:.1f} lbs  |  "
                f"{len(cells)}/{config_cells} cells filled",
                fontsize=10, fontweight="bold", pad=14, loc="left")

            ax.set_xlim(-0.3, cols_per_row * cell_w + 0.3)
            ax.set_ylim(-0.3, num_rows_per_tray * (cell_h + 0.25) + 0.1)
            ax.set_aspect("equal")
            ax.axis("off")
            ax.invert_yaxis()

            filled = {c["cell"]: c for c in cells}

            for ci in range(1, config_cells + 1):
                col = (ci - 1) % cols_per_row
                row = (ci - 1) // cols_per_row
                x = col * cell_w
                y = row * (cell_h + 0.25)
                cell_data = filled.get(ci)
                _draw_cell(ax, x, y, cell_w, cell_h, cell_data, norm, ci, compact)

            # Row separator labels for multi-row layouts
            if num_rows_per_tray > 1:
                for row_idx in range(num_rows_per_tray):
                    start_cell = row_idx * cols_per_row + 1
                    end_cell = min((row_idx + 1) * cols_per_row, config_cells)
                    label_y = row_idx * (cell_h + 0.25) + cell_h / 2
                    ax.text(-0.2, label_y, f"{start_cell}-{end_cell}",
                            ha="right", va="center", fontsize=6,
                            color="#999999", rotation=0, zorder=3)

        plt.tight_layout(rect=[0.02, 0, 1, 0.95])
        safe_name = config_str.replace('"', 'in').replace(" ", "_")
        out_path = os.path.join(output_dir, f"tray_detail_{safe_name}.png")
        fig.savefig(out_path, dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)
        print(f"  Detail view -> {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "slotting_map.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found. Run slotting.py first.")
        sys.exit(1)

    print(f"Loading {csv_path}...")
    rows = load_slotting_map(csv_path)
    print(f"  {len(rows)} placements loaded.\n")

    print("Generating tower overview heatmap...")
    generate_tower_overview(rows)

    print("\nGenerating detailed tray views...")
    generate_detailed_tray_views(rows)

    print("\nDone! Files:")
    print("  tray_overview.png         — tower heatmap")
    print("  tray_details/*.png        — per-config detail grids")


if __name__ == "__main__":
    main()
