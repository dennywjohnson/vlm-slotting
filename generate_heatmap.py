"""
Generate a pick frequency heatmap across all VLM towers.

Each tray is a single colored block — color intensity = total weekly picks
for that tray. Proves the golden zone optimization is working by showing
the hottest trays concentrated in the center band.

Layout: 3 towers side-by-side, trays stacked vertically (top=tray 1,
bottom=tray N). Each tray block shows: tray #, config type, total picks,
# SKUs. Golden zone band highlighted.

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
# Load & aggregate
# ---------------------------------------------------------------------------
def load_slotting_map(path="slotting_map.csv"):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "tower": int(r["Tower"]),
                "tray": int(r["Tray"]),
                "tray_config": r["Tray_Config"],
                "picks": int(r["Weekly_Picks"]),
                "zone": r["Tray_Zone"],
            })
    return rows


def aggregate_trays(rows):
    """Aggregate to one record per (tower, tray)."""
    agg = defaultdict(lambda: {"picks": 0, "skus": 0, "config": "", "zone": ""})
    for r in rows:
        key = (r["tower"], r["tray"])
        agg[key]["picks"] += r["picks"]
        agg[key]["skus"] += 1
        agg[key]["config"] = r["tray_config"]
        agg[key]["zone"] = r["zone"]
    return agg


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------
def generate_heatmap(rows, output_path="pick_heatmap.png",
                     golden_start=20, golden_end=35, trays_per_tower=50):

    agg = aggregate_trays(rows)
    towers = sorted(set(r["tower"] for r in rows))

    # Pick range for color scale
    all_picks = [v["picks"] for v in agg.values()]
    max_picks = max(all_picks) if all_picks else 1
    norm = Normalize(vmin=0, vmax=max_picks)
    cmap = plt.get_cmap("YlOrRd")  # Yellow (cool) -> Orange -> Red (hot)

    # Figure sizing
    tower_w = 3.2   # inches per tower column
    tray_h = 0.42   # inches per tray row
    gap = 1.8       # gap between towers for labels
    left_margin = 1.0
    right_margin = 1.5

    fig_w = left_margin + len(towers) * tower_w + (len(towers) - 1) * gap + right_margin
    fig_h = trays_per_tower * tray_h + 3.5

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(fig_h, 0)
    ax.axis("off")

    # Title
    total_picks = sum(v["picks"] for v in agg.values())
    total_skus = sum(v["skus"] for v in agg.values())
    golden_picks = sum(v["picks"] for k, v in agg.items()
                       if golden_start <= k[1] <= golden_end)
    golden_pct = golden_picks / total_picks * 100 if total_picks > 0 else 0

    ax.text(fig_w / 2, 0.3,
            "VLM Pick Frequency Heatmap",
            ha="center", va="top", fontsize=16, fontweight="bold")
    ax.text(fig_w / 2, 0.85,
            f"{total_skus} SKUs  |  {total_picks} total picks/wk  |  "
            f"Golden zone: {golden_picks} picks/wk ({golden_pct:.0f}%)",
            ha="center", va="top", fontsize=10, color="#555555")

    top_y = 1.5  # where the grid starts

    for ti, tower_num in enumerate(towers):
        tx = left_margin + ti * (tower_w + gap)

        # Tower header
        ax.text(tx + tower_w / 2, top_y - 0.15,
                f"Tower {tower_num}", ha="center", va="bottom",
                fontsize=12, fontweight="bold", color="#37474f")

        for tray_num in range(1, trays_per_tower + 1):
            y = top_y + (tray_num - 1) * tray_h
            key = (tower_num, tray_num)
            data = agg.get(key)

            in_golden = golden_start <= tray_num <= golden_end

            if data is None or data["picks"] == 0:
                # Empty tray
                fc = "#f5f5f5"
                ec = "#e0e0e0"
                lw = 0.5

                ax.add_patch(mpatches.Rectangle(
                    (tx, y), tower_w, tray_h,
                    facecolor=fc, edgecolor=ec, linewidth=lw))

                # Tray number only
                ax.text(tx + 0.15, y + tray_h / 2, str(tray_num),
                        ha="left", va="center", fontsize=6,
                        color="#cccccc")
            else:
                # Filled tray
                color = cmap(norm(data["picks"]))
                ec = "#b71c1c" if data["picks"] > max_picks * 0.8 else "#888888"
                lw = 0.8

                ax.add_patch(mpatches.Rectangle(
                    (tx, y), tower_w, tray_h,
                    facecolor=color, edgecolor=ec, linewidth=lw))

                # Text color based on brightness
                r, g, b, _ = color
                brightness = 0.299 * r + 0.587 * g + 0.114 * b
                tc = "white" if brightness < 0.5 else "#1a1a1a"

                # Tray number (left)
                ax.text(tx + 0.12, y + tray_h / 2, str(tray_num),
                        ha="left", va="center", fontsize=6.5,
                        fontweight="bold", color=tc)

                # Config type (center-left)
                ax.text(tx + 0.65, y + tray_h / 2, data["config"],
                        ha="left", va="center", fontsize=5.5,
                        color=tc)

                # Picks (center-right)
                ax.text(tx + tower_w - 0.9, y + tray_h / 2,
                        f"{data['picks']} pk",
                        ha="right", va="center", fontsize=6,
                        fontweight="bold", color=tc)

                # SKU count (right)
                ax.text(tx + tower_w - 0.12, y + tray_h / 2,
                        f"{data['skus']} SKUs",
                        ha="right", va="center", fontsize=5.5,
                        color=tc)

            # Golden zone left bracket
            if in_golden and ti == 0:
                bx = tx - 0.25
                if tray_num == golden_start:
                    ax.plot([bx + 0.12, bx, bx], [y, y, y + tray_h],
                            color="#B8860B", linewidth=1.5, solid_capstyle="round")
                elif tray_num == golden_end:
                    ax.plot([bx + 0.12, bx, bx], [y + tray_h, y + tray_h, y],
                            color="#B8860B", linewidth=1.5, solid_capstyle="round")
                else:
                    ax.plot([bx, bx], [y, y + tray_h],
                            color="#B8860B", linewidth=1.5)

            # Golden zone right bracket (after last tower)
            if in_golden and ti == len(towers) - 1:
                bx = tx + tower_w + 0.25
                if tray_num == golden_start:
                    ax.plot([bx - 0.12, bx, bx], [y, y, y + tray_h],
                            color="#B8860B", linewidth=1.5, solid_capstyle="round")
                elif tray_num == golden_end:
                    ax.plot([bx - 0.12, bx, bx], [y + tray_h, y + tray_h, y],
                            color="#B8860B", linewidth=1.5, solid_capstyle="round")
                else:
                    ax.plot([bx, bx], [y, y + tray_h],
                            color="#B8860B", linewidth=1.5)

        # Golden zone label (right side of last tower)
        if ti == len(towers) - 1:
            gz_mid_y = top_y + ((golden_start + golden_end) / 2 - 1) * tray_h + tray_h / 2
            ax.text(tx + tower_w + 0.55, gz_mid_y,
                    "GOLDEN\nZONE",
                    ha="left", va="center", fontsize=9,
                    fontweight="bold", color="#B8860B")
            ax.text(tx + tower_w + 0.55, gz_mid_y + 0.7,
                    f"Trays {golden_start}-{golden_end}",
                    ha="left", va="center", fontsize=7,
                    color="#B8860B", style="italic")

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar_ax = fig.add_axes([0.25, 0.015, 0.50, 0.010])
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
    cbar.set_label("Weekly Picks per Tray", fontsize=9, labelpad=4)
    cbar.ax.tick_params(labelsize=7)

    # Legend at bottom
    bottom_y = fig_h - 0.3
    ax.text(fig_w / 2, bottom_y,
            "Each block = 1 tray  |  Color = total weekly picks  |  "
            "Hotter color = more picks  |  Empty trays in gray",
            ha="center", va="center", fontsize=7, color="#888888",
            style="italic")

    fig.savefig(output_path, dpi=170, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  Heatmap -> {output_path}")


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

    print("Generating pick frequency heatmap...")
    generate_heatmap(rows)

    print("\nDone!")


if __name__ == "__main__":
    main()
