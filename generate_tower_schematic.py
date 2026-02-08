"""
Generate an exploded/schematic tower layout diagram for the VLM.

Shows each tower as a vertical structure with:
  - Zone sections (Standard top, Golden center, Standard bottom)
  - Config assignments per zone with tray/SKU counts
  - Physical dimensions and capacity callouts
  - A pulled-out sample tray showing cell layout
  - Summary stats per tower and overall

Reads slotting_map.csv and derives VLM config from defaults.
"""

import csv
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import numpy as np


# ---------------------------------------------------------------------------
# VLM defaults (match slotting.py)
# ---------------------------------------------------------------------------
VLM_DEFAULTS = {
    "num_towers": 3,
    "trays_per_tower": 50,
    "tray_width": 78.0,    # inches
    "tray_depth": 24.0,    # inches
    "tray_max_weight": 750, # lbs
    "golden_start": 20,
    "golden_end": 35,
    "zone": "V",
}


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
                "cell": int(r["Cell"]),
                "tray_config": r["Tray_Config"],
                "picks": int(r["Weekly_Picks"]),
                "cell_weight": float(r["Cell_Weight_lbs"]),
                "zone": r["Tray_Zone"],
            })
    return rows


def analyze(rows):
    """Build per-tower, per-zone statistics."""
    towers = {}
    tray_configs = defaultdict(set)  # (tower, tray) -> config

    for r in rows:
        t = r["tower"]
        if t not in towers:
            towers[t] = {
                "skus": 0, "picks": 0, "weight": 0.0,
                "trays": set(),
                "zones": defaultdict(lambda: {
                    "skus": 0, "picks": 0, "trays": set(),
                    "configs": defaultdict(lambda: {"skus": 0, "trays": set()}),
                }),
            }
        tw = towers[t]
        tw["skus"] += 1
        tw["picks"] += r["picks"]
        tw["weight"] += r["cell_weight"]
        tw["trays"].add(r["tray"])

        zone = r["zone"]
        zd = tw["zones"][zone]
        zd["skus"] += 1
        zd["picks"] += r["picks"]
        zd["trays"].add(r["tray"])
        zd["configs"][r["tray_config"]]["skus"] += 1
        zd["configs"][r["tray_config"]]["trays"].add(r["tray"])

    return towers


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------
def draw_schematic(towers_data, rows, output_path="tower_schematic.png"):
    vlm = VLM_DEFAULTS
    num_towers = vlm["num_towers"]
    trays_per = vlm["trays_per_tower"]
    golden_s = vlm["golden_start"]
    golden_e = vlm["golden_end"]

    # Layout constants
    tower_w = 3.5
    tower_h = 14.0
    tower_gap = 5.5
    left_margin = 2.0
    top_margin = 2.5
    bottom_margin = 3.5

    fig_w = left_margin + num_towers * tower_w + (num_towers - 1) * tower_gap + 4.0
    fig_h = top_margin + tower_h + bottom_margin

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    # Title
    total_skus = sum(t["skus"] for t in towers_data.values())
    total_picks = sum(t["picks"] for t in towers_data.values())
    total_weight = sum(t["weight"] for t in towers_data.values())
    total_trays = sum(len(t["trays"]) for t in towers_data.values())

    ax.text(fig_w / 2, fig_h - 0.4,
            "VLM Tower Schematic — Configuration & Capacity Overview",
            ha="center", va="top", fontsize=15, fontweight="bold")

    # Subtitle with overall stats
    ax.text(fig_w / 2, fig_h - 1.0,
            f"{num_towers} Towers  |  {trays_per} Trays/Tower  |  "
            f"Tray: {vlm['tray_width']}\" W x {vlm['tray_depth']}\" D  |  "
            f"Max {vlm['tray_max_weight']} lbs/tray",
            ha="center", va="top", fontsize=9, color="#666666")
    ax.text(fig_w / 2, fig_h - 1.45,
            f"Loaded: {total_skus} SKUs  |  {total_picks} picks/wk  |  "
            f"{total_weight:,.0f} lbs  |  {total_trays}/{num_towers * trays_per} trays used",
            ha="center", va="top", fontsize=9, color="#666666")

    # Zone proportions (in tower height)
    std_top_trays = golden_s - 1               # trays 1 to golden_s-1
    golden_trays = golden_e - golden_s + 1     # trays golden_s to golden_e
    std_bot_trays = trays_per - golden_e       # trays golden_e+1 to N

    std_top_h = tower_h * std_top_trays / trays_per
    golden_h = tower_h * golden_trays / trays_per
    std_bot_h = tower_h * std_bot_trays / trays_per

    for ti, tower_num in enumerate(sorted(towers_data.keys())):
        tw = towers_data[tower_num]
        tx = left_margin + ti * (tower_w + tower_gap)
        ty_base = bottom_margin  # bottom of tower
        ty_top = ty_base + tower_h

        # --- Tower structure (3 zone sections) ---
        # Standard bottom (trays golden_e+1 to N)
        y_std_bot = ty_base
        ax.add_patch(mpatches.FancyBboxPatch(
            (tx, y_std_bot), tower_w, std_bot_h,
            boxstyle="round,pad=0.05",
            facecolor="#e3f2fd", edgecolor="#1565c0",
            linewidth=1.2))

        # Golden zone (trays golden_s to golden_e)
        y_golden = ty_base + std_bot_h
        ax.add_patch(mpatches.FancyBboxPatch(
            (tx, y_golden), tower_w, golden_h,
            boxstyle="round,pad=0.05",
            facecolor="#fff8e1", edgecolor="#f9a825",
            linewidth=2.0))

        # Standard top (trays 1 to golden_s-1)
        y_std_top = ty_base + std_bot_h + golden_h
        ax.add_patch(mpatches.FancyBboxPatch(
            (tx, y_std_top), tower_w, std_top_h,
            boxstyle="round,pad=0.05",
            facecolor="#e3f2fd", edgecolor="#1565c0",
            linewidth=1.2))

        # --- Tower label ---
        ax.text(tx + tower_w / 2, ty_top + 0.3,
                f"Tower {tower_num}", ha="center", va="bottom",
                fontsize=12, fontweight="bold", color="#37474f")

        # --- Zone labels & config details ---
        # Helper to draw zone info
        def draw_zone_info(y_center, zone_name, zone_data, zone_trays_count,
                           bg_color, text_color):
            # Zone title
            ax.text(tx + tower_w / 2, y_center + 0.5, zone_name,
                    ha="center", va="center", fontsize=8,
                    fontweight="bold", color=text_color)

            if zone_data:
                # Tray/SKU counts
                n_trays = len(zone_data.get("trays", set()))
                n_skus = zone_data["skus"]
                n_picks = zone_data["picks"]
                ax.text(tx + tower_w / 2, y_center + 0.2,
                        f"{n_trays} trays  |  {n_skus} SKUs  |  {n_picks} pk/wk",
                        ha="center", va="center", fontsize=6,
                        color=text_color)

                # Config breakdown
                configs = zone_data["configs"]
                sorted_configs = sorted(configs.items(),
                                        key=lambda x: -x[1]["skus"])
                y_line = y_center - 0.1
                for cfg_name, cfg_data in sorted_configs:
                    n_cfg_trays = len(cfg_data["trays"])
                    ax.text(tx + tower_w / 2, y_line,
                            f"{cfg_name}: {n_cfg_trays} trays, {cfg_data['skus']} SKUs",
                            ha="center", va="center", fontsize=5.5,
                            color=text_color, family="monospace")
                    y_line -= 0.22
            else:
                ax.text(tx + tower_w / 2, y_center,
                        f"{zone_trays_count} trays (empty)",
                        ha="center", va="center", fontsize=6,
                        color="#999999")

        # Standard top zone info
        golden_data = tw["zones"].get("Golden")
        std_data = tw["zones"].get("Standard")

        # For the schematic, we split Standard into "above golden" and "below golden"
        # but the data doesn't distinguish. Show Standard in top, Golden in middle.
        draw_zone_info(
            y_std_top + std_top_h / 2,
            f"STANDARD ZONE (Trays 1-{golden_s - 1})",
            std_data, std_top_trays,
            "#e3f2fd", "#1565c0")

        draw_zone_info(
            y_golden + golden_h / 2,
            f"GOLDEN ZONE (Trays {golden_s}-{golden_e})",
            golden_data, golden_trays,
            "#fff8e1", "#e65100")

        draw_zone_info(
            y_std_bot + std_bot_h / 2,
            f"STANDARD ZONE (Trays {golden_e + 1}-{trays_per})",
            None, std_bot_trays,
            "#e3f2fd", "#1565c0")

        # --- Tower stats at bottom ---
        stat_y = ty_base - 0.3
        stats = [
            f"{tw['skus']} SKUs placed",
            f"{tw['picks']} picks/wk",
            f"{tw['weight']:,.0f} lbs loaded",
            f"{len(tw['trays'])}/{trays_per} trays used",
        ]
        for i, s in enumerate(stats):
            ax.text(tx + tower_w / 2, stat_y - i * 0.28, s,
                    ha="center", va="top", fontsize=7,
                    color="#555555", family="monospace")

    # --- Dimension annotations on the left side ---
    tx0 = left_margin  # first tower x
    ty_base = bottom_margin
    ty_top = ty_base + tower_h

    # Tower height annotation
    dim_x = tx0 - 0.6
    ax.annotate("", xy=(dim_x, ty_base), xytext=(dim_x, ty_top),
                arrowprops=dict(arrowstyle="<->", color="#333333", lw=1.0))
    ax.text(dim_x - 0.15, (ty_base + ty_top) / 2,
            f"{trays_per}\ntrays", ha="right", va="center",
            fontsize=7, color="#333333", rotation=0)

    # Golden zone annotation
    y_golden = ty_base + std_bot_h
    dim_x2 = tx0 - 1.2
    ax.annotate("", xy=(dim_x2, y_golden), xytext=(dim_x2, y_golden + golden_h),
                arrowprops=dict(arrowstyle="<->", color="#e65100", lw=1.0))
    ax.text(dim_x2 - 0.15, y_golden + golden_h / 2,
            f"{golden_trays}\ntrays", ha="right", va="center",
            fontsize=7, color="#e65100", rotation=0)

    # --- Tray dimension callout (bottom right) ---
    callout_x = fig_w - 3.5
    callout_y = 1.2
    tray_draw_w = 2.8
    tray_draw_h = 0.8

    ax.text(callout_x + tray_draw_w / 2, callout_y + tray_draw_h + 0.5,
            "Tray Dimensions", ha="center", va="center",
            fontsize=9, fontweight="bold", color="#37474f")

    # Tray rectangle
    ax.add_patch(mpatches.Rectangle(
        (callout_x, callout_y), tray_draw_w, tray_draw_h,
        facecolor="#eceff1", edgecolor="#37474f", linewidth=1.5))

    # Width annotation
    ax.annotate("", xy=(callout_x, callout_y - 0.15),
                xytext=(callout_x + tray_draw_w, callout_y - 0.15),
                arrowprops=dict(arrowstyle="<->", color="#333", lw=0.8))
    ax.text(callout_x + tray_draw_w / 2, callout_y - 0.3,
            f"{vlm['tray_width']}\"", ha="center", va="center",
            fontsize=7, fontweight="bold")

    # Depth annotation
    ax.annotate("", xy=(callout_x + tray_draw_w + 0.15, callout_y),
                xytext=(callout_x + tray_draw_w + 0.15, callout_y + tray_draw_h),
                arrowprops=dict(arrowstyle="<->", color="#333", lw=0.8))
    ax.text(callout_x + tray_draw_w + 0.35, callout_y + tray_draw_h / 2,
            f"{vlm['tray_depth']}\"", ha="left", va="center",
            fontsize=7, fontweight="bold", rotation=90)

    # Max weight note
    ax.text(callout_x + tray_draw_w / 2, callout_y + tray_draw_h / 2,
            f"Max {vlm['tray_max_weight']} lbs", ha="center", va="center",
            fontsize=7, color="#37474f", fontweight="bold")

    # --- Config summary table (bottom center) ---
    table_x = left_margin + 0.5
    table_y = 0.3
    ax.text(table_x, table_y + 0.8,
            "Tray Configurations:", ha="left", va="bottom",
            fontsize=9, fontweight="bold", color="#37474f")

    # Collect unique configs
    all_configs = set()
    for r in rows:
        all_configs.add(r["tray_config"])

    sorted_cfgs = sorted(all_configs)
    x_pos = table_x
    for cfg in sorted_cfgs:
        cells = int(cfg.split("-")[0])
        symbol = "█" * min(cells // 3, 6)
        ax.text(x_pos, table_y + 0.35, cfg, ha="left", va="center",
                fontsize=6.5, fontweight="bold", color="#37474f",
                family="monospace")
        ax.text(x_pos, table_y + 0.08, f"{cells} cells/tray",
                ha="left", va="center", fontsize=5.5, color="#777777",
                family="monospace")
        x_pos += 2.0
        if x_pos > fig_w - 3:
            x_pos = table_x
            table_y -= 0.7

    fig.savefig(output_path, dpi=170, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  Schematic -> {output_path}")


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

    towers_data = analyze(rows)
    print("Generating tower schematic...")
    draw_schematic(towers_data, rows)

    print("\nDone!")


if __name__ == "__main__":
    main()
