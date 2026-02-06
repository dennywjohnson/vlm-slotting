"""
Generate 500 sample SKUs with assigned Tray Configurations and Pick Priority.

KEY CHANGES FROM PREVIOUS VERSION:
  - Each SKU specifies its Tray_Config (1-4) based on item size
  - Each SKU gets a Pick_Priority (1 thru N) within its config group,
    ranked by Weekly_Picks descending — this drives cell assignment
  - Dimensions are generated to fit within the assigned config's
    cell width, tray height, and effective cell volume

TRAY CONFIG REFERENCE (default settings):
  Config 4 (30-cell): cell width ~2.1", height 6",  tiny parts
  Config 3 (16-cell): cell width ~4.4", height 12", small parts
  Config 2  (8-cell): cell width ~9.3", height 18", medium parts
  Config 1  (6-cell): cell width ~12.6", height 24", large parts
"""

import csv
import random

# Seed for reproducibility — anyone running this gets the same 500 SKUs.
random.seed(42)


# --------------------------------------------------------------------------
# DEFAULT VLM SETTINGS (used to generate data that fits)
# --------------------------------------------------------------------------
TRAY_WIDTH = 78.0
TRAY_DEPTH = 24.0
DIVIDER_WIDTH = 0.5
ITEM_CLEARANCE = 0.25

CONFIG_DEFS = {
    4: {"cells": 30, "height": 6.0,  "height_tol": 10, "fill_pct": 85},
    3: {"cells": 16, "height": 12.0, "height_tol": 10, "fill_pct": 85},
    2: {"cells": 8,  "height": 18.0, "height_tol": 10, "fill_pct": 85},
    1: {"cells": 6,  "height": 24.0, "height_tol": 10, "fill_pct": 85},
}


def _cell_width(cells: int) -> float:
    return (TRAY_WIDTH - (cells - 1) * DIVIDER_WIDTH) / cells


def _usable_cell_width(cells: int) -> float:
    return _cell_width(cells) - 2 * ITEM_CLEARANCE


def _effective_cell_volume(cells: int, height: float, fill_pct: int) -> float:
    return _cell_width(cells) * TRAY_DEPTH * height * fill_pct / 100


# --------------------------------------------------------------------------
# PART CATEGORIES — one per tray config
# --------------------------------------------------------------------------
# Each category generates items that physically fit their assigned config.
#
# "narrow" = the item dimension that goes across the cell width (must fit)
# "wide"   = the item dimension that goes front-to-back (tray depth)
# These get randomly assigned as Width_in / Length_in in the CSV.
# --------------------------------------------------------------------------
CATEGORIES = [
    # CONFIG 4 (30-cell) — tiny parts: bearings, o-rings, fuses, fasteners
    {
        "config": 4,
        "descriptions": [
            "Ball Bearing", "Sealed Bearing", "Thrust Bearing",
            "O-Ring Kit", "Shaft Seal", "Lip Seal",
            "Fuse 10A", "Fuse 15A", "Fuse 30A",
            "Dowel Pin Set", "Cotter Pin Kit", "Retaining Ring Kit",
            "Set Screw Pack", "Spring Pin Kit", "Snap Ring Kit",
        ],
        "narrow": (0.3, 1.5),
        "wide":   (0.3, 4.0),
        "height": (0.3, 5.5),
        "weight": (0.01, 0.5),
        "eaches_range": (10, 100),
        "count": 150,
    },
    # CONFIG 3 (16-cell) — small parts: sensors, switches, relays
    {
        "config": 3,
        "descriptions": [
            "Proximity Sensor", "Temp Sensor", "Pressure Transducer",
            "Limit Switch", "Toggle Switch", "Rocker Switch",
            "Relay 24V", "Relay 120V", "Contactor Coil",
            "Terminal Block", "Wire Connector Kit", "DIN Rail Mount",
            "LED Indicator", "Push Button Red", "Push Button Green",
        ],
        "narrow": (1.0, 3.5),
        "wide":   (1.0, 8.0),
        "height": (1.0, 11.0),
        "weight": (0.1, 3.0),
        "eaches_range": (3, 30),
        "count": 120,
    },
    # CONFIG 2 (8-cell) — medium parts: filters, valves, PLCs
    {
        "config": 2,
        "descriptions": [
            "Hydraulic Filter", "Oil Filter Element", "Air Filter Cartridge",
            "Gasket Set", "Flange Gasket", "Head Gasket",
            "Ball Valve 1in", "Gate Valve 1in", "Check Valve 3/4in",
            "Solenoid Valve 24V", "Pressure Regulator", "Flow Control Valve",
            "PLC Module", "I/O Card", "Power Supply 24V",
        ],
        "narrow": (3.0, 8.5),
        "wide":   (3.0, 16.0),
        "height": (2.0, 16.0),
        "weight": (0.5, 15.0),
        "eaches_range": (1, 15),
        "count": 130,
    },
    # CONFIG 1 (6-cell) — large parts: motors, pumps, gearboxes
    {
        "config": 1,
        "descriptions": [
            "AC Motor 1HP", "AC Motor 2HP", "DC Motor 1/2HP",
            "Gear Pump", "Centrifugal Pump", "Diaphragm Pump",
            "Gearbox 10:1", "Gearbox 20:1", "Speed Reducer",
            "Cylinder 2in Bore", "Cylinder 3in Bore", "Cylinder 4in Bore",
            "VFD 2HP", "Servo Drive", "Heat Exchanger",
        ],
        "narrow": (5.0, 11.5),
        "wide":   (5.0, 20.0),
        "height": (4.0, 22.0),
        "weight": (5.0, 65.0),
        "eaches_range": (1, 5),
        "count": 100,
    },
]


# --------------------------------------------------------------------------
# GENERATION
# --------------------------------------------------------------------------

def generate_weekly_picks() -> int:
    """
    Right-skewed distribution (Pareto pattern).
    ~50% get 0-2 picks, ~25% get 2-4, ~15% get 4-7, ~10% get 7-10.
    """
    r = random.random()
    if r < 0.50:
        return random.randint(0, 2)
    elif r < 0.75:
        return random.randint(2, 4)
    elif r < 0.90:
        return random.randint(4, 7)
    else:
        return random.randint(7, 10)


def generate_skus() -> list[dict]:
    """Build 500 SKUs with Tray_Config and Pick_Priority."""
    skus = []
    sku_num = 1
    usable_depth = TRAY_DEPTH - 2 * ITEM_CLEARANCE

    for cat in CATEGORIES:
        cfg = CONFIG_DEFS[cat["config"]]
        eff_vol = _effective_cell_volume(
            cfg["cells"], cfg["height"], cfg["fill_pct"]
        )

        for _ in range(cat["count"]):
            desc = random.choice(cat["descriptions"])

            # Generate dimensions that fit this config
            narrow = round(random.uniform(*cat["narrow"]), 1)
            wide = round(min(random.uniform(*cat["wide"]), usable_depth), 1)
            height = round(random.uniform(*cat["height"]), 1)
            weight = round(random.uniform(*cat["weight"]), 2)

            # Randomly assign narrow/wide as width/length
            if random.random() < 0.5:
                width, length = narrow, wide
            else:
                width, length = wide, narrow

            # Cap eaches so total volume fits the effective cell volume
            sku_vol = length * width * height
            max_eaches = max(1, int(eff_vol / sku_vol)) if sku_vol > 0 else 1
            ea_lo, ea_hi = cat["eaches_range"]
            ea_cap = min(ea_hi, max_eaches)
            eaches = random.randint(min(ea_lo, ea_cap), max(ea_lo, ea_cap))

            skus.append({
                "SKU": f"SKU-{sku_num:04d}",
                "Description": desc,
                "Length_in": length,
                "Width_in": width,
                "Height_in": height,
                "Weight_lbs": weight,
                "Eaches": eaches,
                "Weekly_Picks": generate_weekly_picks(),
                "Tray_Config": cat["config"],
            })
            sku_num += 1

    # Shuffle so the CSV isn't grouped by category
    random.shuffle(skus)

    # ---- ASSIGN PICK PRIORITY ----
    # Group by Tray_Config, sort by Weekly_Picks descending within each group,
    # then assign Pick_Priority 1, 2, 3... (1 = fastest mover in that config).
    config_groups: dict[int, list[dict]] = {}
    for s in skus:
        config_groups.setdefault(s["Tray_Config"], []).append(s)

    for group in config_groups.values():
        group.sort(key=lambda s: (-s["Weekly_Picks"], s["SKU"]))
        for i, s in enumerate(group):
            s["Pick_Priority"] = i + 1

    return skus


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    skus = generate_skus()

    output_file = "sample_skus.csv"
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

    for config_num in sorted(config_groups):
        group = config_groups[config_num]
        picks = [s["Weekly_Picks"] for s in group]
        print(f"  Config {config_num}: {len(group)} SKUs, "
              f"picks {min(picks)}-{max(picks)}/wk, "
              f"top pick priority = 1..{len(group)}")

    # Pick distribution
    print("\nWeekly Picks distribution:")
    pick_counts = [s["Weekly_Picks"] for s in skus]
    for p in range(11):
        count = pick_counts.count(p)
        bar = "#" * count
        print(f"  {p:2d} picks: {count:3d} SKUs  {bar}")


if __name__ == "__main__":
    main()
