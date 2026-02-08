"""
Generate 500 warehouse SKUs with assigned Tray Configurations and Pick Priority.

REALISTIC WAREHOUSE DISTRIBUTION:
  - Most SKUs are slow movers (0 weekly picks) — typical of a VLM storing
    maintenance spares, repair parts, and low-velocity inventory
  - Per tray config: max 20 picks/week, only 5 SKUs at that peak,
    2 SKUs at each level 1-19, rest are zero-pick storage items

TRAY CONFIG REFERENCE (matches slotting.py configs 1-8):
  2" height trays (flat/thin items):
    Config 1  (6-cell):  cell width ~12.6"  — large flat (plates, panels)
    Config 2  (8-cell):  cell width ~9.3"   — medium flat (PCBs, brackets)
    Config 3  (16-cell): cell width ~4.4"   — small flat (clips, clamps)
    Config 4  (30-cell): cell width ~2.1"   — tiny flat (washers, O-rings)
  4" height trays (standard items):
    Config 5  (6-cell):  cell width ~12.6"  — large (motors, pumps)
    Config 6  (8-cell):  cell width ~9.3"   — medium (valves, filters)
    Config 7  (16-cell): cell width ~4.4"   — small (sensors, relays)
    Config 8  (30-cell): cell width ~2.1"   — tiny (bearings, fuses)
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
    1: {"cells": 6,  "height": 2.0, "height_tol": 10, "fill_pct": 85},
    2: {"cells": 8,  "height": 2.0, "height_tol": 10, "fill_pct": 85},
    3: {"cells": 16, "height": 2.0, "height_tol": 10, "fill_pct": 85},
    4: {"cells": 30, "height": 2.0, "height_tol": 10, "fill_pct": 85},
    5: {"cells": 6,  "height": 4.0, "height_tol": 10, "fill_pct": 85},
    6: {"cells": 8,  "height": 4.0, "height_tol": 10, "fill_pct": 85},
    7: {"cells": 16, "height": 4.0, "height_tol": 10, "fill_pct": 85},
    8: {"cells": 30, "height": 4.0, "height_tol": 10, "fill_pct": 85},
}


def _cell_width(cells: int) -> float:
    return (TRAY_WIDTH - (cells - 1) * DIVIDER_WIDTH) / cells


def _usable_cell_width(cells: int) -> float:
    return _cell_width(cells) - 2 * ITEM_CLEARANCE


def _effective_cell_volume(cells: int, height: float, fill_pct: int) -> float:
    return _cell_width(cells) * TRAY_DEPTH * height * fill_pct / 100


# --------------------------------------------------------------------------
# PART CATEGORIES — one per tray config (8 total)
# --------------------------------------------------------------------------
# "narrow" = dimension across cell width (must fit)
# "wide"   = dimension front-to-back (tray depth)
# Randomly assigned as Width_in / Length_in in the CSV.
# --------------------------------------------------------------------------
CATEGORIES = [
    # --- 2" HEIGHT TRAYS (flat/thin items) ---

    # CONFIG 1 (6-cell, 2") — large flat: plates, panels, shields
    {
        "config": 1,
        "descriptions": [
            "Steel Cover Plate", "Access Panel", "Mounting Plate",
            "Sheet Metal Blank", "Base Plate", "Wear Plate",
            "Back Panel", "Side Panel", "Floor Plate",
            "Heat Shield", "Drip Tray", "Splash Guard",
            "Machine Guard", "Inspection Cover", "Door Panel",
        ],
        "narrow": (5.0, 11.5),
        "wide":   (5.0, 20.0),
        "height": (0.3, 1.8),
        "weight": (1.0, 15.0),
        "eaches_range": (1, 3),
        "count": 63,
    },
    # CONFIG 2 (8-cell, 2") — medium flat: PCBs, brackets, shims
    {
        "config": 2,
        "descriptions": [
            "Control Board", "Relay Board", "PCB Assembly",
            "Mounting Bracket", "Angle Bracket", "U-Bracket",
            "Shim Pack 0.010", "Shim Pack 0.020", "Shim Pack 0.050",
            "Backing Plate", "Adapter Plate", "Wear Strip",
            "Gasket Sheet", "Cork Gasket", "Rubber Mat",
        ],
        "narrow": (3.0, 8.5),
        "wide":   (3.0, 16.0),
        "height": (0.2, 1.8),
        "weight": (0.3, 8.0),
        "eaches_range": (1, 5),
        "count": 63,
    },
    # CONFIG 3 (16-cell, 2") — small flat: clips, clamps, labels
    {
        "config": 3,
        "descriptions": [
            "Hose Clamp", "Cable Clip", "P-Clip",
            "Name Plate", "Warning Label", "ID Tag",
            "Flat Washer Kit", "Lock Washer Kit", "Wave Washer Kit",
            "Shim Washer", "Spacer Plate", "Retainer Clip",
            "Contact Tip", "Brush Plate", "Brake Pad",
        ],
        "narrow": (1.0, 3.5),
        "wide":   (1.0, 8.0),
        "height": (0.1, 1.8),
        "weight": (0.05, 2.0),
        "eaches_range": (3, 20),
        "count": 63,
    },
    # CONFIG 4 (30-cell, 2") — tiny flat: washers, O-rings, spacers
    {
        "config": 4,
        "descriptions": [
            "O-Ring", "Flat Washer", "Thrust Washer",
            "Spacer 1/8", "Spacer 1/4", "Spacer 1/2",
            "Felt Seal", "Backup Ring", "Wiper Seal",
            "Shim 0.005", "Shim 0.010", "Shim 0.015",
            "Wave Spring", "Snap Ring", "E-Clip",
        ],
        "narrow": (0.3, 1.5),
        "wide":   (0.3, 4.0),
        "height": (0.1, 1.8),
        "weight": (0.01, 0.5),
        "eaches_range": (10, 100),
        "count": 63,
    },

    # --- 4" HEIGHT TRAYS (standard items) ---

    # CONFIG 5 (6-cell, 4") — large: motors, pumps, gearboxes
    {
        "config": 5,
        "descriptions": [
            "AC Motor 1HP", "DC Motor 1/2HP", "Gear Motor",
            "Gear Pump", "Centrifugal Pump", "Diaphragm Pump",
            "Gearbox 10:1", "Gearbox 20:1", "Speed Reducer",
            "Cylinder 2in Bore", "Cylinder 3in Bore", "Cylinder 4in Bore",
            "VFD 2HP", "Servo Drive", "Heat Exchanger",
        ],
        "narrow": (5.0, 11.5),
        "wide":   (5.0, 20.0),
        "height": (2.0, 3.8),
        "weight": (2.0, 30.0),
        "eaches_range": (1, 3),
        "count": 62,
    },
    # CONFIG 6 (8-cell, 4") — medium: valves, filters, PLCs
    {
        "config": 6,
        "descriptions": [
            "Hydraulic Filter", "Oil Filter", "Air Filter Cartridge",
            "Ball Valve 1in", "Gate Valve 1in", "Check Valve 3/4in",
            "Solenoid Valve 24V", "Pressure Regulator", "Flow Control Valve",
            "PLC Module", "I/O Card", "Power Supply 24V",
            "Coupling Insert", "Shaft Coupling", "Flex Coupling",
        ],
        "narrow": (3.0, 8.5),
        "wide":   (3.0, 16.0),
        "height": (1.5, 3.8),
        "weight": (0.5, 12.0),
        "eaches_range": (1, 8),
        "count": 62,
    },
    # CONFIG 7 (16-cell, 4") — small: sensors, relays, switches
    {
        "config": 7,
        "descriptions": [
            "Proximity Sensor", "Temp Sensor", "Pressure Transducer",
            "Limit Switch", "Toggle Switch", "Rocker Switch",
            "Relay 24V", "Relay 120V", "Contactor Coil",
            "Terminal Block", "Wire Connector Kit", "DIN Rail Mount",
            "LED Indicator", "Push Button Red", "Push Button Green",
        ],
        "narrow": (1.0, 3.5),
        "wide":   (1.0, 8.0),
        "height": (1.0, 3.8),
        "weight": (0.1, 3.0),
        "eaches_range": (2, 20),
        "count": 62,
    },
    # CONFIG 8 (30-cell, 4") — tiny: bearings, fuses, pins
    {
        "config": 8,
        "descriptions": [
            "Ball Bearing", "Sealed Bearing", "Thrust Bearing",
            "Fuse 10A", "Fuse 15A", "Fuse 30A",
            "Dowel Pin Set", "Cotter Pin Kit", "Retaining Ring Kit",
            "Set Screw Pack", "Spring Pin Kit", "Roll Pin Kit",
            "Wire Ferrule", "Crimp Terminal", "Butt Splice",
        ],
        "narrow": (0.3, 1.5),
        "wide":   (0.3, 4.0),
        "height": (0.3, 3.8),
        "weight": (0.01, 0.5),
        "eaches_range": (5, 50),
        "count": 62,
    },
]


# --------------------------------------------------------------------------
# WEEKLY PICK DISTRIBUTION (realistic slow-moving warehouse)
# --------------------------------------------------------------------------

def assign_weekly_picks(group: list[dict]) -> None:
    """
    Assign Weekly_Picks to a config group using a realistic warehouse
    distribution.  Most items in a VLM are slow movers.

    Per config group:
      - 5 SKUs get 20 picks/week  (the hot movers)
      - 2 SKUs each at 19, 18, 17, ... 1 picks/week
      - All remaining SKUs get 0  (bulk of the inventory)

    Total non-zero per group: 5 + (19 * 2) = 43
    """
    # Build the pick values list
    picks = [20] * 5
    for p in range(19, 0, -1):
        picks.extend([p] * 2)
    # Fill remaining slots with 0
    remaining = len(group) - len(picks)
    picks.extend([0] * remaining)

    # Shuffle so the non-zero picks aren't clustered by SKU number
    random.shuffle(picks)

    for sku, weekly in zip(group, picks):
        sku["Weekly_Picks"] = weekly


# --------------------------------------------------------------------------
# GENERATION
# --------------------------------------------------------------------------

def generate_skus() -> list[dict]:
    """Build 500 warehouse SKUs with Tray_Config and Pick_Priority."""
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
                "Weekly_Picks": 0,  # assigned below by config group
                "Tray_Config": cat["config"],
            })
            sku_num += 1

    # Shuffle so the CSV isn't grouped by category
    random.shuffle(skus)

    # ---- ASSIGN WEEKLY PICKS per config group ----
    config_groups: dict[int, list[dict]] = {}
    for s in skus:
        config_groups.setdefault(s["Tray_Config"], []).append(s)

    for group in config_groups.values():
        assign_weekly_picks(group)

    # ---- ASSIGN PICK PRIORITY ----
    # Sort by Weekly_Picks descending within each config group,
    # then assign Pick_Priority 1, 2, 3... (1 = fastest mover).
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

    for config_num in sorted(config_groups):
        group = config_groups[config_num]
        picks = [s["Weekly_Picks"] for s in group]
        non_zero = sum(1 for p in picks if p > 0)
        print(f"  Config {config_num}: {len(group):3d} SKUs, "
              f"picks 0-{max(picks)}/wk, "
              f"{non_zero} active / {len(group) - non_zero} zero-pick")

    # Pick distribution across all SKUs
    print("\nWeekly Picks distribution:")
    pick_counts = [s["Weekly_Picks"] for s in skus]
    for p in range(21):
        count = pick_counts.count(p)
        bar = "#" * count
        print(f"  {p:2d} picks: {count:3d} SKUs  {bar}")

    total_picks = sum(pick_counts)
    zero_count = pick_counts.count(0)
    print(f"\n  Total weekly picks: {total_picks}")
    print(f"  Zero-pick SKUs: {zero_count} / {len(skus)} "
          f"({100 * zero_count / len(skus):.0f}%)")


if __name__ == "__main__":
    main()
