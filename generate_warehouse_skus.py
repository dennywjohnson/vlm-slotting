"""
Generate ~2,160 machine shop warehouse SKUs for a VLM slotting optimizer.

SCENARIO:
  A precision machine shop storing fasteners, bearings, seals, tooling,
  fittings, and small mechanical components. Items are small, specialized,
  and stored in modest quantities.

DESIGN:
  - SKU count per config is proportional to cell count, targeting ~12 trays
    per config per tower for even tray distribution:
      Config 1 ( 6-cell):  216 SKUs  (motors, housings, large fittings)
      Config 2 ( 8-cell):  288 SKUs  (valves, manifolds, toolholders)
      Config 3 (16-cell):  576 SKUs  (bearings, seals, small fittings)
      Config 4 (30-cell): 1080 SKUs  (washers, nuts, bolts, pins, O-rings)
  - Volume-aware: each SKU's total volume (single_vol * eaches) is
    guaranteed to fit within the effective cell volume of its config
  - Height-aware: single item height stays within tray height + tolerance
  - Dimension-aware: narrow dimension fits the cell width with clearance
  - Weekly picks follow a right-skewed Pareto distribution

EFFECTIVE CELL VOLUMES (at default config):
  Config 1 ( 6-cell): 1026.8 cu in
  Config 2 ( 8-cell):  759.9 cu in
  Config 3 (16-cell):  359.6 cu in
  Config 4 (30-cell):  172.7 cu in
"""

import csv
import random
import math

random.seed(42)

# --------------------------------------------------------------------------
# VLM SETTINGS (match slotting.py defaults)
# --------------------------------------------------------------------------
TRAY_WIDTH = 78.0
TRAY_DEPTH = 24.0
TRAY_HEIGHT = 4.0
HEIGHT_TOL = 10        # percent
FILL_PCT = 85          # percent
DIVIDER_WIDTH = 0.5
ITEM_CLEARANCE = 0.25

CONFIGS = [
    {"config": 1, "cells": 6},
    {"config": 2, "cells": 8},
    {"config": 3, "cells": 16},
    {"config": 4, "cells": 30},
]

# Compute effective cell dimensions for each config
for c in CONFIGS:
    cell_w = (TRAY_WIDTH - (c["cells"] - 1) * DIVIDER_WIDTH) / c["cells"]
    c["cell_w"] = cell_w
    c["usable_w"] = cell_w - 2 * ITEM_CLEARANCE
    c["usable_d"] = TRAY_DEPTH - 2 * ITEM_CLEARANCE
    c["max_h"] = TRAY_HEIGHT * (1 + HEIGHT_TOL / 100.0)
    c["eff_vol"] = cell_w * TRAY_DEPTH * TRAY_HEIGHT * FILL_PCT / 100.0

# --------------------------------------------------------------------------
# PART DESCRIPTIONS by config (machine shop themed)
# --------------------------------------------------------------------------
PARTS_BY_CONFIG = {
    1: [  # Large parts — housings, motors, manifolds
        "Hydraulic Motor", "Gear Housing", "Pump Assembly", "Cylinder Block",
        "Spindle Housing", "Servo Motor", "Gearbox Shell", "Valve Body Large",
        "Bearing Housing", "Coupling Assembly", "Motor Mount Bracket",
        "Pneumatic Cylinder", "Linear Actuator", "Chuck Body", "Rotary Table Base",
    ],
    2: [  # Medium parts — valves, toolholders, fittings
        "Ball Valve Assembly", "Toolholder BT40", "Manifold Block", "Collet Chuck",
        "Hydraulic Fitting", "Relief Valve", "Solenoid Valve", "Flow Control Valve",
        "Quick-Change Holder", "End Mill Holder", "Drill Chuck", "Boring Bar Holder",
        "Pressure Regulator", "Filter Housing", "Directional Valve",
    ],
    3: [  # Small parts — bearings, seals, small fittings
        "Deep Groove Bearing", "Angular Contact Bearing", "Thrust Bearing",
        "Shaft Seal", "Lip Seal", "Hydraulic Seal Kit", "Pipe Fitting 1/2",
        "O-Ring Kit Large", "Linear Bearing", "Needle Bearing",
        "Cam Follower", "Rod End Bearing", "Pillow Block", "Spring Assortment",
        "Retaining Ring Set",
    ],
    4: [  # Tiny parts — washers, nuts, bolts, pins, O-rings
        "Hex Bolt M6", "Hex Bolt M8", "Socket Cap Screw M5", "Socket Cap Screw M8",
        "Flat Washer M6", "Lock Washer M8", "Hex Nut M6", "Hex Nut M10",
        "Dowel Pin 3mm", "Dowel Pin 5mm", "Roll Pin 4mm", "Cotter Pin",
        "O-Ring AS568", "Set Screw M5", "Grub Screw M4",
    ],
}


# SKUs per config: sized to fill ~12 trays per config per tower (3 towers)
# This ensures even tray distribution and all SKUs fit the physical VLM.
#   Config 1:  6 cells * 12 trays * 3 towers = 216 SKUs
#   Config 2:  8 cells * 12 trays * 3 towers = 288 SKUs
#   Config 3: 16 cells * 12 trays * 3 towers = 576 SKUs
#   Config 4: 30 cells * 12 trays * 3 towers = 1080 SKUs
#   Total: 2,160 SKUs
NUM_TOWERS = 3
TRAYS_PER_CONFIG_PER_TOWER = 12
SKUS_PER_CONFIG = {
    c["config"]: c["cells"] * TRAYS_PER_CONFIG_PER_TOWER * NUM_TOWERS
    for c in CONFIGS
}


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
    """
    Generate a single SKU that is guaranteed to pass validation for its config.

    Strategy:
      1. Pick narrow dimension to fit cell width
      2. Pick length to fit usable depth
      3. Pick height under max allowed
      4. Pick eaches, then verify total volume fits effective cell volume
         If not, reduce eaches until it fits
    """
    usable_w = cfg["usable_w"]
    usable_d = cfg["usable_d"]
    max_h = cfg["max_h"]
    eff_vol = cfg["eff_vol"]
    config_num = cfg["config"]

    # Narrow dimension: sized for this config's cell width
    # Use config-specific ranges to keep parts realistic
    if config_num == 1:
        narrow = round(random.uniform(4.0, usable_w), 2)
        wide_max = min(usable_d, 18.0)
    elif config_num == 2:
        narrow = round(random.uniform(2.5, usable_w), 2)
        wide_max = min(usable_d, 14.0)
    elif config_num == 3:
        narrow = round(random.uniform(0.5, usable_w), 2)
        wide_max = min(usable_d, 8.0)
    else:  # config 4 — tiny parts
        narrow = round(random.uniform(0.15, usable_w), 2)
        wide_max = min(usable_d, 4.0)

    wide = round(random.uniform(narrow, wide_max), 2)

    # Height: must stay under tray height + tolerance
    if config_num == 4:
        height = round(random.uniform(0.05, min(1.5, max_h)), 2)
    elif config_num == 3:
        height = round(random.uniform(0.10, min(2.5, max_h)), 2)
    elif config_num == 2:
        height = round(random.uniform(0.25, min(3.5, max_h)), 2)
    else:
        height = round(random.uniform(0.50, max_h), 2)

    # Weight per each (lighter for smaller configs)
    if config_num == 4:
        weight = round(random.uniform(0.01, 0.5), 2)
    elif config_num == 3:
        weight = round(random.uniform(0.02, 1.5), 2)
    elif config_num == 2:
        weight = round(random.uniform(0.05, 3.0), 2)
    else:
        weight = round(random.uniform(0.10, 5.0), 2)

    # Single SKU volume
    sku_vol = narrow * wide * height

    # Eaches: start with a realistic range, then cap to fit cell volume
    if config_num == 4:
        max_eaches = random.randint(5, 50)
    elif config_num == 3:
        max_eaches = random.randint(3, 30)
    elif config_num == 2:
        max_eaches = random.randint(2, 20)
    else:
        max_eaches = random.randint(1, 10)

    # Ensure total volume fits: eaches * sku_vol <= eff_vol
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

    # Pick a realistic description
    parts = PARTS_BY_CONFIG[config_num]
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
    skus = []
    sku_num = 1

    for cfg in CONFIGS:
        count = SKUS_PER_CONFIG[cfg["config"]]
        for _ in range(count):
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
    config_groups: dict[int, list[dict]] = {}
    for s in skus:
        config_groups.setdefault(s["Tray_Config"], []).append(s)

    num_towers = 3
    for config_num in sorted(config_groups):
        group = config_groups[config_num]
        cfg = [c for c in CONFIGS if c["config"] == config_num][0]
        picks = [s["Weekly_Picks"] for s in group]
        total_picks = sum(picks)
        vols = [s["Length_in"] * s["Width_in"] * s["Height_in"] * s["Eaches"] for s in group]
        eaches = [s["Eaches"] for s in group]
        trays_filled = len(group) / (cfg["cells"] * num_towers)
        print(f"  Config {config_num} ({cfg['cells']:2d}-cell): {len(group)} SKUs, "
              f"total picks {total_picks}/wk, "
              f"avg eaches {sum(eaches)/len(eaches):.1f}, "
              f"avg total vol {sum(vols)/len(vols):.1f} cu in "
              f"(eff_vol {cfg['eff_vol']:.0f}), "
              f"~{trays_filled:.1f} trays/tower")

    # Validation preview
    over_vol = 0
    over_height = 0
    for s in skus:
        cfg = [c for c in CONFIGS if c["config"] == s["Tray_Config"]][0]
        sku_vol = s["Length_in"] * s["Width_in"] * s["Height_in"]
        total_vol = sku_vol * s["Eaches"]
        if total_vol > cfg["eff_vol"]:
            over_vol += 1
        if s["Height_in"] > cfg["max_h"]:
            over_height += 1
    print(f"\n  Volume violations: {over_vol}")
    print(f"  Height violations: {over_height}")


if __name__ == "__main__":
    main()
