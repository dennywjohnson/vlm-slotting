"""
Generate top-down physical tray layout views.

Shows each tray as it would appear looking down from above, with the
operator/user standing at the bottom (front) of the tray.

Cell grid layouts:
   6-cell:  1 row  x 6 cols  (A-F)
   8-cell:  2 rows x 4 cols  (A-D)
  16-cell:  4 rows x 4 cols  (A-D)
  30-cell:  5 rows x 6 cols  (A-F)

Pick Priority numbering:
  - Priority 1 = bottom-left (front of tray, closest to operator)
  - Fills left-to-right, then bottom-to-top
  - Highest priority number = top-right (back of tray)

Example 16-cell layout (rows descending, 1=front):
  Row 4 (BACK):   4A=PP13  4B=PP14  4C=PP15  4D=PP16
  Row 3:          3A=PP9   3B=PP10  3C=PP11  3D=PP12
  Row 2:          2A=PP5   2B=PP6   2C=PP7   2D=PP8
  Row 1 (FRONT):  1A=PP1   1B=PP2   1C=PP3   1D=PP4

Reads slotting_map.csv (output of slotting.py).
"""

import csv
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
import numpy as np


# ---------------------------------------------------------------------------
# Grid definitions per cell count
# ---------------------------------------------------------------------------
GRID_LAYOUTS = {
    6:  (1, 6),   # 1 row  x 6 cols
    8:  (2, 4),   # 2 rows x 4 cols
    16: (4, 4),   # 4 rows x 4 cols
    30: (5, 6),   # 5 rows x 6 cols
}


def cell_to_grid(cell_num, num_rows, num_cols):
    """Convert cell number (1-based pick priority) to grid (display_row, col).

    Priority 1 starts at bottom-left, fills left-to-right, bottom-to-top.
    Display row 0 = top of image (back of tray).
    """
    idx = cell_num - 1
    row_from_bottom = idx // num_cols
    col = idx % num_cols
    display_row = (num_rows - 1) - row_from_bottom
    return display_row, col


def col_letter(col_idx):
    return chr(ord("A") + col_idx)


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
    idx = defaultdict(list)
    for r in rows:
        idx[(r["tower"], r["tray"])].append(r)
    for k in idx:
        idx[k].sort(key=lambda c: c["cell"])
    return idx


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------
CMAP = plt.get_cmap("RdYlGn_r")


def picks_color(picks, norm):
    """Color by pick frequency — red=hot, green=cool."""
    return CMAP(norm(picks))


def text_color(bg_rgba):
    r, g, b, _ = bg_rgba
    brightness = 0.299 * r + 0.587 * g + 0.114 * b
    return "white" if brightness < 0.52 else "#1a1a1a"


# ---------------------------------------------------------------------------
# Draw a single top-down tray
# ---------------------------------------------------------------------------
def draw_tray_topdown(cells_data, config_str, tower, tray_num, zone,
                      config_cells, output_path):

    grid_rows, grid_cols = GRID_LAYOUTS.get(config_cells, (1, config_cells))

    filled = {c["cell"]: c for c in cells_data}
    all_picks = [c["picks"] for c in cells_data]
    max_picks = max(all_picks) if all_picks else 1
    norm = Normalize(vmin=0, vmax=max_picks)

    total_picks = sum(c["picks"] for c in cells_data)
    total_weight = sum(c["cell_weight"] for c in cells_data)

    # Cell box sizes
    cell_w = 2.6
    cell_h = 2.0 if grid_rows <= 2 else 1.7

    # Figure dimensions
    grid_total_w = grid_cols * cell_w
    grid_total_h = grid_rows * cell_h

    # Extra space: col headers top, row labels left, front/back labels, title
    left_margin = 0.8
    right_margin = 0.4
    top_margin = 1.8   # title + "BACK" label + col headers
    bottom_margin = 1.2  # "FRONT" label

    fig_w = left_margin + grid_total_w + right_margin
    fig_h = top_margin + grid_total_h + bottom_margin

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # Coordinate system: grid origin at (left_margin, top_margin)
    # x goes right, y goes down
    ax.set_xlim(0, fig_w)
    ax.set_ylim(fig_h, 0)  # inverted: 0 at top
    ax.set_aspect("equal")
    ax.axis("off")

    gx0 = left_margin
    gy0 = top_margin

    # --- Title ---
    title = (f"{config_str}  |  Tower {tower}, Tray {tray_num}  |  "
             f"{zone} Zone  |  {total_picks} picks/wk  |  "
             f"{total_weight:.1f} lbs")
    ax.text(fig_w / 2, 0.35, title, ha="center", va="top",
            fontsize=10, fontweight="bold", family="sans-serif")

    # --- BACK label (top) ---
    ax.text(fig_w / 2, gy0 - 0.55, "BACK  (far side of tray)",
            ha="center", va="center", fontsize=9,
            color="#78909c", fontweight="bold", style="italic")

    # Bracket line for BACK
    bk_y = gy0 - 0.25
    ax.plot([gx0, gx0 + grid_total_w], [bk_y, bk_y],
            color="#b0bec5", linewidth=1.5)

    # --- FRONT label (bottom) ---
    front_y = gy0 + grid_total_h + 0.55
    ax.text(fig_w / 2, front_y,
            "FRONT  (operator side)",
            ha="center", va="center", fontsize=10,
            color="#1565c0", fontweight="bold")
    # Arrow pointing up toward the tray
    ax.annotate("", xy=(fig_w / 2, front_y - 0.35),
                xytext=(fig_w / 2, front_y - 0.15),
                arrowprops=dict(arrowstyle="->", color="#1565c0", lw=1.5))

    # Bracket line for FRONT
    fr_y = gy0 + grid_total_h + 0.2
    ax.plot([gx0, gx0 + grid_total_w], [fr_y, fr_y],
            color="#1565c0", linewidth=2)

    # --- Column headers (A, B, C, ...) ---
    for ci in range(grid_cols):
        cx = gx0 + ci * cell_w + cell_w / 2
        cy = gy0 - 0.08
        ax.text(cx, cy, col_letter(ci), ha="center", va="bottom",
                fontsize=11, fontweight="bold", color="#37474f")

    # --- Row labels (descending: bottom=1, top=N) ---
    for ri in range(grid_rows):
        rx = gx0 - 0.15
        ry = gy0 + ri * cell_h + cell_h / 2
        row_label = grid_rows - ri  # bottom row = 1, top row = N
        ax.text(rx, ry, str(row_label), ha="right", va="center",
                fontsize=11, fontweight="bold", color="#37474f")

    # --- Draw cells ---
    for cell_num in range(1, config_cells + 1):
        dr, dc = cell_to_grid(cell_num, grid_rows, grid_cols)
        x = gx0 + dc * cell_w
        y = gy0 + dr * cell_h

        c = filled.get(cell_num)

        if c is None:
            # Empty cell
            ax.add_patch(mpatches.FancyBboxPatch(
                (x + 0.04, y + 0.04), cell_w - 0.08, cell_h - 0.08,
                boxstyle="round,pad=0.03",
                facecolor="#fafafa", edgecolor="#e0e0e0",
                linewidth=0.8, linestyle="--", zorder=2))
            row_label = grid_rows - dr
            ax.text(x + cell_w / 2, y + cell_h * 0.35,
                    f"{row_label}{col_letter(dc)}", ha="center", va="center",
                    fontsize=8, color="#cccccc", fontweight="bold", zorder=3)
            ax.text(x + cell_w / 2, y + cell_h * 0.6,
                    "EMPTY", ha="center", va="center",
                    fontsize=7, color="#cccccc", zorder=3)
            continue

        bg = picks_color(c["picks"], norm)
        tc = text_color(bg)
        vol_pct = min(100, c["total_vol"] / c["cell_vol"] * 100) if c["cell_vol"] > 0 else 0

        # Cell background
        ax.add_patch(mpatches.FancyBboxPatch(
            (x + 0.04, y + 0.04), cell_w - 0.08, cell_h - 0.08,
            boxstyle="round,pad=0.03",
            facecolor=bg, edgecolor="#555555",
            linewidth=1.0, zorder=2))

        # Cell address + priority (top line)
        row_label = grid_rows - dr
        addr = f"{row_label}{col_letter(dc)}"
        ax.text(x + 0.15, y + 0.15, addr,
                ha="left", va="top", fontsize=7,
                fontweight="bold", color=tc, zorder=3)
        ax.text(x + cell_w - 0.15, y + 0.15, f"PP:{cell_num}",
                ha="right", va="top", fontsize=5.5,
                color=tc, alpha=0.7, zorder=3)

        # SKU (prominent, centered)
        sku_y = y + cell_h * 0.32
        ax.text(x + cell_w / 2, sku_y, c["sku"],
                ha="center", va="center", fontsize=8,
                fontweight="bold", color=tc, zorder=3)

        # Description
        desc = c["desc"][:15] + ".." if len(c["desc"]) > 17 else c["desc"]
        ax.text(x + cell_w / 2, y + cell_h * 0.48, desc,
                ha="center", va="center", fontsize=5.5,
                color=tc, style="italic", zorder=3)

        # Picks + Eaches line
        ax.text(x + cell_w / 2, y + cell_h * 0.63,
                f"{c['picks']} pk/wk  |  {c['eaches']} ea",
                ha="center", va="center", fontsize=5.5,
                color=tc, zorder=3)

        # BIN Label
        ax.text(x + cell_w / 2, y + cell_h * 0.76,
                c["bin"],
                ha="center", va="center", fontsize=5.5,
                color=tc, zorder=3)

        # Volume fill bar at bottom of cell
        bar_margin = 0.2
        bar_y = y + cell_h * 0.88
        bar_h = cell_h * 0.06
        bar_full_w = cell_w - 2 * bar_margin - 0.08
        bar_x = x + bar_margin + 0.04

        # Bar background
        ax.add_patch(mpatches.Rectangle(
            (bar_x, bar_y - bar_h / 2), bar_full_w, bar_h,
            facecolor="#ffffff55", edgecolor=tc, linewidth=0.4,
            alpha=0.5, zorder=3))
        # Bar fill
        fill_w = bar_full_w * vol_pct / 100
        if vol_pct < 70:
            bar_color = "#4caf50"
        elif vol_pct < 90:
            bar_color = "#ff9800"
        else:
            bar_color = "#f44336"
        ax.add_patch(mpatches.Rectangle(
            (bar_x, bar_y - bar_h / 2), fill_w, bar_h,
            facecolor=bar_color, edgecolor="none", zorder=4))

        # Vol % text
        ax.text(bar_x + bar_full_w + 0.1, bar_y,
                f"{vol_pct:.0f}%", ha="left", va="center",
                fontsize=4.5, color=tc, fontweight="bold", zorder=5)

    # --- Outer tray border ---
    ax.add_patch(mpatches.Rectangle(
        (gx0, gy0), grid_total_w, grid_total_h,
        facecolor="none", edgecolor="#37474f",
        linewidth=2.0, zorder=5))

    # --- Pick priority legend ---
    legend_y = fig_h - 0.15
    ax.text(gx0, legend_y,
            f"PP = Pick Priority  |  PP:1 = front-left (most accessible)  |  "
            f"PP:{config_cells} = back-right  |  "
            f"Color: red=high picks, green=low picks",
            ha="left", va="bottom", fontsize=5.5,
            color="#78909c", style="italic")

    fig.savefig(output_path, dpi=170, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)


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

    tray_idx = build_tray_index(rows)
    output_dir = "tray_topdown"
    os.makedirs(output_dir, exist_ok=True)

    # Group by config
    config_trays = defaultdict(list)
    for (tower, tray), cells in tray_idx.items():
        if cells:
            config_trays[cells[0]["tray_config"]].append((tower, tray, cells))

    for config_str in sorted(config_trays.keys()):
        trays = config_trays[config_str]
        trays.sort(key=lambda t: sum(c["picks"] for c in t[2]), reverse=True)

        config_cells = int(config_str.split("-")[0])
        if config_cells not in GRID_LAYOUTS:
            print(f"  SKIP {config_str} — no grid layout defined for {config_cells} cells")
            continue

        # Pick busiest golden zone tray, fall back to busiest overall
        golden = [t for t in trays if t[2][0]["zone"] == "Golden"]
        best = golden[0] if golden else trays[0]
        tower, tray_num, cells = best

        safe_name = config_str.replace('"', 'in').replace(" ", "_")
        out_path = os.path.join(output_dir, f"topdown_{safe_name}.png")

        draw_tray_topdown(cells, config_str, tower, tray_num,
                          cells[0]["zone"], config_cells, out_path)
        print(f"  {config_str:14s} Tower {tower} Tray {tray_num:2d} "
              f"({cells[0]['zone']:8s}) -> {out_path}")

    print(f"\nDone! {output_dir}/ contains top-down tray layout views.")


if __name__ == "__main__":
    main()
