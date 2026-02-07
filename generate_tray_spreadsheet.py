"""
Generate spreadsheet-style top-down tray views of VLM slotting results.

Each tray is rendered as a clean data table (one row per cell) with:
  - Cell #, BIN Label, SKU, Description, Picks/Wk, Eaches,
    Wt/Each, Cell Wt, Vol Used, Cell Vol, Vol%
  - Alternating row stripes, header row, totals row
  - Conditional formatting on Vol% and Picks columns

One image per tray config (shows the busiest tray for that config).

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
import numpy as np


# ---------------------------------------------------------------------------
# Load & index
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
                "length": float(r["Length_in"]),
                "width": float(r["Width_in"]),
                "height": float(r["Height_in"]),
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
# Color helpers
# ---------------------------------------------------------------------------
def picks_bg(picks, max_picks):
    """Background color for picks column — gradient white to warm red."""
    if max_picks == 0:
        return "#ffffff"
    t = picks / max_picks
    # White -> light salmon -> red
    r = 1.0
    g = 1.0 - t * 0.6
    b = 1.0 - t * 0.65
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def vol_pct_bg(pct):
    """Background color for volume % — green/yellow/orange/red."""
    if pct < 50:
        return "#e8f5e9"   # light green
    elif pct < 70:
        return "#c8e6c9"   # green
    elif pct < 85:
        return "#fff9c4"   # yellow
    elif pct < 95:
        return "#ffe0b2"   # orange
    else:
        return "#ffcdd2"   # red


def vol_bar_color(pct):
    if pct < 70:
        return "#4caf50"
    elif pct < 90:
        return "#ff9800"
    else:
        return "#f44336"


# ---------------------------------------------------------------------------
# Draw one spreadsheet tray view
# ---------------------------------------------------------------------------
COLUMNS = [
    ("Cell",    3.0),
    ("BIN",     5.5),
    ("SKU",     5.5),
    ("Description", 9.0),
    ("Picks/Wk", 4.2),
    ("Ea",      2.8),
    ("Dims (LxWxH)", 7.5),
    ("Wt/Ea",   3.5),
    ("Cell Wt", 3.8),
    ("Vol Used", 4.5),
    ("Cell Vol", 4.5),
    ("Vol %",   5.5),
]


def draw_tray_spreadsheet(cells_data, config_str, tower, tray, zone,
                          config_cells, output_path):
    """Render a single tray as a spreadsheet table."""

    col_names = [c[0] for c in COLUMNS]
    col_widths = [c[1] for c in COLUMNS]  # relative widths
    total_w = sum(col_widths)
    num_data_rows = config_cells
    num_rows = num_data_rows + 2  # header + data + totals

    # Figure sizing
    scale = 0.155  # inches per width unit
    fig_w = total_w * scale + 1.0
    row_h = 0.30
    fig_h = num_rows * row_h + 2.2

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, total_w)
    ax.set_ylim(0, num_rows)
    ax.invert_yaxis()
    ax.axis("off")

    filled = {c["cell"]: c for c in cells_data}
    total_picks = sum(c["picks"] for c in cells_data)
    total_cell_wt = sum(c["cell_weight"] for c in cells_data)
    total_vol_used = sum(c["total_vol"] for c in cells_data)
    total_cell_vol = cells_data[0]["cell_vol"] * config_cells if cells_data else 0
    max_picks = max((c["picks"] for c in cells_data), default=1)

    # Title
    title = (f"Tray Configuration: {config_str}  |  "
             f"Tower {tower}, Tray {tray}  |  "
             f"{zone} Zone  |  "
             f"{len(cells_data)}/{config_cells} cells  |  "
             f"{total_picks} picks/wk  |  "
             f"{total_cell_wt:.1f} lbs total")
    fig.suptitle(title, fontsize=9.5, fontweight="bold", y=0.97,
                 ha="center", family="monospace")

    # --- Header row ---
    y = 0
    x = 0
    for ci, (name, w) in enumerate(COLUMNS):
        ax.add_patch(mpatches.Rectangle(
            (x, y), w, 1, facecolor="#37474f", edgecolor="#263238",
            linewidth=0.8))
        ax.text(x + w / 2, y + 0.5, name, ha="center", va="center",
                fontsize=7, fontweight="bold", color="white",
                family="monospace")
        x += w

    # --- Data rows ---
    for ri in range(config_cells):
        y = ri + 1
        cell_num = ri + 1
        c = filled.get(cell_num)
        # Alternating stripe
        stripe = "#ffffff" if ri % 2 == 0 else "#f5f7fa"

        x = 0
        for ci, (name, w) in enumerate(COLUMNS):
            # Determine cell background and text
            bg = stripe
            text = ""
            align = "center"
            fontw = "normal"
            fontcolor = "#333333"
            fontsize = 7

            if c is None:
                # Empty cell
                if ci == 0:
                    text = str(cell_num)
                else:
                    text = "-"
                    fontcolor = "#bbbbbb"
            else:
                vol_pct = min(100, c["total_vol"] / c["cell_vol"] * 100) if c["cell_vol"] > 0 else 0

                if name == "Cell":
                    text = str(cell_num)
                    fontw = "bold"
                elif name == "BIN":
                    text = c["bin"]
                    fontsize = 6.5
                    fontw = "bold"
                    fontcolor = "#1565c0"
                elif name == "SKU":
                    text = c["sku"]
                    fontw = "bold"
                elif name == "Description":
                    text = c["desc"][:18]
                    align = "left"
                    fontsize = 6.5
                elif name == "Picks/Wk":
                    text = str(c["picks"])
                    bg = picks_bg(c["picks"], max_picks)
                    fontw = "bold"
                elif name == "Ea":
                    text = str(c["eaches"])
                elif name == "Dims (LxWxH)":
                    text = f"{c['length']:.1f} x {c['width']:.1f} x {c['height']:.1f}"
                    fontsize = 6
                elif name == "Wt/Ea":
                    text = f"{c['weight_each']:.2f}"
                elif name == "Cell Wt":
                    text = f"{c['cell_weight']:.1f}"
                elif name == "Vol Used":
                    text = f"{c['total_vol']:.0f}"
                elif name == "Cell Vol":
                    text = f"{c['cell_vol']:.0f}"
                elif name == "Vol %":
                    bg = vol_pct_bg(vol_pct)
                    # We'll draw a mini bar + text
                    pass

            # Draw cell background
            ax.add_patch(mpatches.Rectangle(
                (x, y), w, 1, facecolor=bg, edgecolor="#dee2e6",
                linewidth=0.5))

            # Special: Vol% column gets a mini bar
            if name == "Vol %" and c is not None:
                vol_pct = min(100, c["total_vol"] / c["cell_vol"] * 100) if c["cell_vol"] > 0 else 0
                # Bar background
                bar_x = x + 0.3
                bar_w_max = w - 2.2
                bar_h = 0.55
                bar_y = y + 0.22
                ax.add_patch(mpatches.Rectangle(
                    (bar_x, bar_y), bar_w_max, bar_h,
                    facecolor="#e0e0e0", edgecolor="#bdbdbd",
                    linewidth=0.3))
                # Bar fill
                fill_w = bar_w_max * vol_pct / 100
                ax.add_patch(mpatches.Rectangle(
                    (bar_x, bar_y), fill_w, bar_h,
                    facecolor=vol_bar_color(vol_pct), edgecolor="none"))
                # Percentage text to the right of bar
                ax.text(bar_x + bar_w_max + 0.2, y + 0.5,
                        f"{vol_pct:.0f}%",
                        ha="left", va="center", fontsize=6.5,
                        fontweight="bold", color="#333333",
                        family="monospace")
            elif text:
                tx = x + w / 2 if align == "center" else x + 0.3
                ax.text(tx, y + 0.5, text, ha=align, va="center",
                        fontsize=fontsize, fontweight=fontw,
                        color=fontcolor, family="monospace")
            x += w

    # --- Totals row ---
    y = config_cells + 1
    x = 0
    overall_vol_pct = (total_vol_used / total_cell_vol * 100) if total_cell_vol > 0 else 0
    for ci, (name, w) in enumerate(COLUMNS):
        bg = "#eceff1"
        text = ""
        fontw = "bold"
        fontcolor = "#333333"
        fontsize = 7
        align = "center"

        if name == "Cell":
            text = "TOTAL"
            fontcolor = "#37474f"
        elif name == "Picks/Wk":
            text = str(total_picks)
        elif name == "Cell Wt":
            text = f"{total_cell_wt:.1f}"
        elif name == "Vol Used":
            text = f"{total_vol_used:.0f}"
        elif name == "Cell Vol":
            text = f"{total_cell_vol:.0f}"

        ax.add_patch(mpatches.Rectangle(
            (x, y), w, 1, facecolor=bg, edgecolor="#b0bec5",
            linewidth=0.8))

        if name == "Vol %" :
            bar_x = x + 0.3
            bar_w_max = w - 2.2
            bar_h = 0.55
            bar_y = y + 0.22
            ax.add_patch(mpatches.Rectangle(
                (bar_x, bar_y), bar_w_max, bar_h,
                facecolor="#e0e0e0", edgecolor="#bdbdbd", linewidth=0.3))
            fill_w = bar_w_max * overall_vol_pct / 100
            ax.add_patch(mpatches.Rectangle(
                (bar_x, bar_y), fill_w, bar_h,
                facecolor=vol_bar_color(overall_vol_pct), edgecolor="none"))
            ax.text(bar_x + bar_w_max + 0.2, y + 0.5,
                    f"{overall_vol_pct:.0f}%",
                    ha="left", va="center", fontsize=6.5,
                    fontweight="bold", color="#333333", family="monospace")
        elif text:
            ax.text(x + w / 2, y + 0.5, text, ha="center", va="center",
                    fontsize=fontsize, fontweight=fontw, color=fontcolor,
                    family="monospace")
        x += w

    # Outer border
    ax.add_patch(mpatches.Rectangle(
        (0, 0), total_w, num_rows, facecolor="none", edgecolor="#37474f",
        linewidth=1.5))

    plt.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.02)
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
    output_dir = "tray_spreadsheets"
    os.makedirs(output_dir, exist_ok=True)

    # Group by config
    config_trays = defaultdict(list)
    for (tower, tray), cells in tray_idx.items():
        if cells:
            config_trays[cells[0]["tray_config"]].append((tower, tray, cells))

    for config_str in sorted(config_trays.keys()):
        trays = config_trays[config_str]
        # Sort by total picks descending — pick busiest
        trays.sort(key=lambda t: sum(c["picks"] for c in t[2]), reverse=True)

        config_cells = int(config_str.split("-")[0])

        # Generate for top 2 trays: busiest and a golden zone one
        golden = [t for t in trays if t[2][0]["zone"] == "Golden"]
        standard = [t for t in trays if t[2][0]["zone"] != "Golden"]

        samples = []
        if golden:
            samples.append(("golden", golden[0]))
        if standard:
            samples.append(("standard", standard[0]))
        if not samples:
            samples.append(("best", trays[0]))

        for label, (tower, tray, cells) in samples:
            safe_name = config_str.replace('"', 'in').replace(" ", "_")
            out_path = os.path.join(
                output_dir,
                f"tray_{safe_name}_T{tower}_tray{tray}.png")
            draw_tray_spreadsheet(
                cells, config_str, tower, tray,
                cells[0]["zone"], config_cells, out_path)
            print(f"  {config_str:14s} Tower {tower} Tray {tray:2d} "
                  f"({cells[0]['zone']:8s}) -> {out_path}")

    print(f"\nDone! {output_dir}/ contains spreadsheet-style tray views.")


if __name__ == "__main__":
    main()
