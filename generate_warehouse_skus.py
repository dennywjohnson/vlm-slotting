"""
Generate 15,000 machine shop warehouse SKUs for a VLM slotting optimizer.

SCENARIO:
  A precision machine shop with 12 tray configurations:
  3 heights (2", 4", 6") × 4 cell counts (6, 8, 16, 30) = 12 configs.
  1,250 SKUs per config, evenly distributed.

TRAY CONFIGURATIONS (matching slotting.py defaults):
  Config  1:  6-cell 2"H    Config  5:  6-cell 4"H    Config  9:  6-cell 6"H
  Config  2:  8-cell 2"H    Config  6:  8-cell 4"H    Config 10:  8-cell 6"H
  Config  3: 16-cell 2"H    Config  7: 16-cell 4"H    Config 11: 16-cell 6"H
  Config  4: 30-cell 2"H    Config  8: 30-cell 4"H    Config 12: 30-cell 6"H

DESIGN:
  - Volume-aware: total volume (single_vol × eaches) fits effective cell vol
  - Height-aware: item height within tray height + tolerance
  - Dimension-aware: narrow dimension fits cell width with clearance
  - Weekly picks follow a right-skewed Pareto distribution
"""

import csv
import random

random.seed(42)

# --------------------------------------------------------------------------
# VLM SETTINGS (match slotting.py defaults)
# --------------------------------------------------------------------------
TRAY_WIDTH = 78.0
TRAY_DEPTH = 24.0
DIVIDER_WIDTH = 0.5
ITEM_CLEARANCE = 0.25
NUM_TOWERS = 3
TRAYS_PER_TOWER = 50
HEIGHT_TOL = 10   # percent
FILL_PCT = 85     # percent

# 3 heights × 4 cell counts = 12 configs
HEIGHTS = [2.0, 4.0, 6.0]
CELL_COUNTS = [6, 8, 16, 30]

CONFIGS = []
config_num = 1
for h in HEIGHTS:
    for cells in CELL_COUNTS:
        CONFIGS.append({"config": config_num, "cells": cells, "height": h})
        config_num += 1

# Compute effective cell dimensions for each config
for c in CONFIGS:
    cell_w = (TRAY_WIDTH - (c["cells"] - 1) * DIVIDER_WIDTH) / c["cells"]
    c["cell_w"] = cell_w
    c["usable_w"] = cell_w - 2 * ITEM_CLEARANCE
    c["usable_d"] = TRAY_DEPTH - 2 * ITEM_CLEARANCE
    c["max_h"] = c["height"] * (1 + HEIGHT_TOL / 100.0)
    c["eff_vol"] = cell_w * TRAY_DEPTH * c["height"] * FILL_PCT / 100.0

# --------------------------------------------------------------------------
# PART DESCRIPTIONS by height tier (machine shop themed)
# --------------------------------------------------------------------------
PARTS_BY_CELLS_AND_HEIGHT = {
    # 6-cell (large parts)
    (6, 2.0): [
        "Flat Plate Bracket", "Base Plate Assembly", "Heat Sink Flat",
        "Mounting Plate", "Cover Plate Large", "Shim Plate Set",
    ],
    (6, 4.0): [
        "Hydraulic Motor", "Gear Housing", "Pump Assembly", "Cylinder Block",
        "Spindle Housing", "Servo Motor", "Gearbox Shell", "Bearing Housing",
    ],
    (6, 6.0): [
        "Tall Gear Housing", "Vertical Motor", "Tower Bearing Assembly",
        "Tall Pump Body", "Spindle Column", "Deep Cylinder Block",
    ],
    # 8-cell (medium parts)
    (8, 2.0): [
        "Flat Valve Body", "Thin Manifold", "Regulator Plate",
        "Flat Collet Set", "Adapter Plate", "Spacer Block Thin",
    ],
    (8, 4.0): [
        "Ball Valve Assembly", "Toolholder BT40", "Manifold Block",
        "Collet Chuck", "Relief Valve", "Solenoid Valve", "Drill Chuck",
    ],
    (8, 6.0): [
        "Tall Valve Assembly", "Deep Manifold Block", "Vertical Toolholder",
        "Extended Collet Chuck", "Tall Filter Housing", "Deep Boring Bar",
    ],
    # 16-cell (small parts)
    (16, 2.0): [
        "Flat Gasket Set", "Shim Pack 0.5mm", "Shim Pack 1.0mm",
        "Thrust Washer Set", "Wave Spring", "Belleville Washer",
        "Copper Gasket", "Seal Plate", "Backing Ring",
    ],
    (16, 4.0): [
        "Deep Groove Bearing", "Angular Contact Bearing", "Thrust Bearing",
        "Shaft Seal", "Lip Seal", "Hydraulic Seal Kit", "Linear Bearing",
        "Needle Bearing", "Cam Follower", "Pillow Block",
    ],
    (16, 6.0): [
        "Tall Bearing Housing", "Deep Seal Assembly", "Extended Spring Kit",
        "Tall Pillow Block", "Deep Cam Follower", "Vertical Bearing Mount",
    ],
    # 30-cell (tiny parts)
    (30, 2.0): [
        "O-Ring Metric Thin", "Flat Washer M3", "Flat Washer M4",
        "Shim 0.1mm", "Shim 0.25mm", "Snap Ring Thin", "Wave Washer M5",
        "Star Washer M4", "Circlip Internal", "PTFE Seal Ring",
    ],
    (30, 4.0): [
        "Hex Bolt M6", "Hex Bolt M8", "Socket Cap Screw M5",
        "Socket Cap Screw M8", "Flat Washer M6", "Lock Washer M8",
        "Hex Nut M6", "Dowel Pin 3mm", "Roll Pin 4mm", "Set Screw M5",
    ],
    (30, 6.0): [
        "Long Hex Bolt M8", "Long Socket Cap M6", "Stud Bolt M10",
        "Standoff M5x40", "Long Dowel Pin 6mm", "Extension Spring Small",
        "Tall Roll Pin 5mm", "Long Set Screw M6",
    ],
}

TOTAL_SKUS = 15000
SKUS_PER_CONFIG = TOTAL_SKUS // len(CONFIGS)  # 1,250 each


def generate_weekly_picks() -> int:
    """Right-skewed Pareto distribution for picks (0-20)."""
    r = random.random()
    if r < 0.40:
        return random.randint(0, 2)
    elif r < 0.65:
        return random.randint(2, 5)
    elif r < 0.80:
        return random.randint(5, 9)
    elif r < 0.92:
        return random.randint(9, 14)
    else:
        return random.randint(14, 20)


def generate_sku(sku_num: int, cfg: dict) -> dict:
    """Generate a single SKU guaranteed to pass validation for its config."""
    usable_w = cfg["usable_w"]
    max_h = cfg["max_h"]
    eff_vol = cfg["eff_vol"]
    config_num = cfg["config"]
    cells = cfg["cells"]
    tray_h = cfg["height"]

    # Dimension ranges by cell count
    if cells <= 6:
        narrow_min, narrow_max = 2.0, usable_w
        wide_max = min(cfg["usable_d"], 18.0)
        w_min, w_max = 0.10, 5.0
        ea_min, ea_max = 1, 12
    elif cells <= 8:
        narrow_min, narrow_max = 1.5, usable_w
        wide_max = min(cfg["usable_d"], 14.0)
        w_min, w_max = 0.05, 3.0
        ea_min, ea_max = 2, 20
    elif cells <= 16:
        narrow_min, narrow_max = 0.3, usable_w
        wide_max = min(cfg["usable_d"], 8.0)
        w_min, w_max = 0.02, 1.5
        ea_min, ea_max = 3, 30
    else:  # 30-cell
        narrow_min, narrow_max = 0.10, usable_w
        wide_max = min(cfg["usable_d"], 4.0)
        w_min, w_max = 0.01, 0.5
        ea_min, ea_max = 5, 50

    # Height range: scale to tray height
    h_min = max(0.03, tray_h * 0.05)
    h_max = max_h * 0.95  # stay safely under tolerance limit

    # Clamp
    narrow_min = max(0.05, narrow_min)
    if narrow_min >= narrow_max:
        narrow_min = narrow_max * 0.5

    narrow = round(random.uniform(narrow_min, narrow_max), 2)
    wide = round(random.uniform(narrow, max(narrow, wide_max)), 2)
    height = round(random.uniform(h_min, h_max), 2)
    weight = round(random.uniform(w_min, w_max), 2)

    # Single SKU volume
    sku_vol = narrow * wide * height

    # Eaches: cap to fit effective cell volume
    max_eaches = random.randint(ea_min, ea_max)
    if sku_vol > 0:
        vol_limit = int(eff_vol / sku_vol)
        eaches = max(1, min(max_eaches, vol_limit))
    else:
        eaches = max_eaches

    weekly_picks = generate_weekly_picks()

    # Randomly assign narrow/wide as width/length
    if random.random() < 0.5:
        length, width = wide, narrow
    else:
        length, width = narrow, wide

    parts = PARTS_BY_CELLS_AND_HEIGHT.get((cells, tray_h), ["Machine Part"])
    desc = random.choice(parts)

    return {
        "SKU": f"WH-{sku_num:05d}",
        "Description": desc,
        "Length_in": length,
        "Width_in": width,
        "Height_in": height,
        "Weight_lbs": weight,
        "Eaches": eaches,
        "Weekly_Picks": weekly_picks,
        "Tray_Config": config_num,
    }


def generate_skus() -> list[dict]:
    configs_by_num = {c["config"]: c for c in CONFIGS}
    skus = []
    sku_num = 1

    for cfg in CONFIGS:
        for _ in range(SKUS_PER_CONFIG):
            skus.append(generate_sku(sku_num, cfg))
            sku_num += 1

    # Shuffle so the CSV isn't grouped by config
    random.shuffle(skus)

    # Assign Pick_Priority within each config group (ranked by picks desc)
    config_groups: dict[int, list[dict]] = {}
    for s in skus:
        config_groups.setdefault(s["Tray_Config"], []).append(s)

    for group in config_groups.values():
        group.sort(key=lambda s: (-s["Weekly_Picks"], s["SKU"]))
        for i, s in enumerate(group):
            s["Pick_Priority"] = i + 1

    return skus


def main():
    skus = generate_skus()

    output_file = "warehouse_skus.csv"
    fieldnames = [
        "SKU", "Description", "Length_in", "Width_in", "Height_in",
        "Weight_lbs", "Eaches", "Weekly_Picks", "Tray_Config", "Pick_Priority",
    ]

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(skus)

    print(f"Generated {len(skus)} SKUs -> {output_file}\n")

    # Summary by config
    configs_by_num = {c["config"]: c for c in CONFIGS}
    config_groups: dict[int, list[dict]] = {}
    for s in skus:
        config_groups.setdefault(s["Tray_Config"], []).append(s)

    for config_num in sorted(config_groups):
        group = config_groups[config_num]
        cfg = configs_by_num[config_num]
        picks = [s["Weekly_Picks"] for s in group]
        total_picks = sum(picks)
        vols = [s["Length_in"] * s["Width_in"] * s["Height_in"] * s["Eaches"] for s in group]
        eaches = [s["Eaches"] for s in group]
        trays_needed = len(group) / (cfg["cells"] * NUM_TOWERS)
        print(f"  Config {config_num:2d} ({cfg['cells']:2d}-cell {cfg['height']:.0f}\"H): "
              f"{len(group):5d} SKUs, "
              f"picks {total_picks:5d}/wk, "
              f"avg ea {sum(eaches)/len(eaches):4.1f}, "
              f"avg vol {sum(vols)/len(vols):6.1f}/{cfg['eff_vol']:.0f} cu in, "
              f"~{trays_needed:.1f} trays/twr")

    # Validation preview
    over_vol = over_height = over_dim = 0
    for s in skus:
        cfg = configs_by_num[s["Tray_Config"]]
        sku_vol = s["Length_in"] * s["Width_in"] * s["Height_in"]
        total_vol = sku_vol * s["Eaches"]
        if total_vol > cfg["eff_vol"]:
            over_vol += 1
        if s["Height_in"] > cfg["max_h"]:
            over_height += 1
        narrow = min(s["Length_in"], s["Width_in"])
        if narrow > cfg["usable_w"]:
            over_dim += 1

    print(f"\n  Volume violations:    {over_vol}")
    print(f"  Height violations:    {over_height}")
    print(f"  Dimension violations: {over_dim}")
    print(f"  Total: {len(skus)} SKUs ({SKUS_PER_CONFIG} per config × {len(CONFIGS)} configs)")


if __name__ == "__main__":
    main()
