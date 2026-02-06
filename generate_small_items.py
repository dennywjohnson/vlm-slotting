"""
Generate 3,500 small-item SKU candidates for VLM slotting.

These SKUs have varied dimensions that may or may not fit the VLM's
tray configurations.  The slotting validator will catch any that
don't physically fit — that's expected and by design.

DIMENSION RANGES:
  Height: 0.5" to 5"
  Width:  0.5" to 12"
  Length: 0.25" to 18"

The script assigns each SKU to the densest tray config it fits in
(most cells per tray).  SKUs that don't fit any config are still
included and assigned to the closest match — validation will flag them.
"""

import csv
import random

random.seed(99)

# --------------------------------------------------------------------------
# DEFAULT VLM SETTINGS (must match slotting.py defaults)
# --------------------------------------------------------------------------
TRAY_WIDTH = 78.0
TRAY_DEPTH = 24.0
DIVIDER_WIDTH = 0.5
ITEM_CLEARANCE = 0.25

# Configs ordered densest-first so we assign to the tightest fit
CONFIG_DEFS = [
    {"num": 4, "cells": 30, "height": 6.0,  "height_tol": 10, "fill_pct": 85},
    {"num": 3, "cells": 16, "height": 12.0, "height_tol": 10, "fill_pct": 85},
    {"num": 2, "cells": 8,  "height": 18.0, "height_tol": 10, "fill_pct": 85},
    {"num": 1, "cells": 6,  "height": 24.0, "height_tol": 10, "fill_pct": 85},
]


def _cell_width(cells: int) -> float:
    return (TRAY_WIDTH - (cells - 1) * DIVIDER_WIDTH) / cells


def _usable_width(cells: int) -> float:
    return _cell_width(cells) - 2 * ITEM_CLEARANCE


def _usable_depth() -> float:
    return TRAY_DEPTH - 2 * ITEM_CLEARANCE


def _eff_vol(cells: int, height: float, fill_pct: int) -> float:
    return _cell_width(cells) * TRAY_DEPTH * height * fill_pct / 100


def fits_config(w: float, l: float, h: float, cfg: dict) -> bool:
    """Check if a single item fits a config (dimensions + height)."""
    uw = _usable_width(cfg["cells"])
    ud = _usable_depth()
    max_h = cfg["height"] * (1 + cfg["height_tol"] / 100)

    if h > max_h:
        return False

    # Allow rotation (swap width and length)
    fits_normal = w <= uw and l <= ud
    fits_rotated = l <= uw and w <= ud
    return fits_normal or fits_rotated


def best_config(w: float, l: float, h: float) -> int:
    """Find the densest config that fits this item.  Returns config number."""
    for cfg in CONFIG_DEFS:
        if fits_config(w, l, h, cfg):
            return cfg["num"]
    # Doesn't fit any — assign to Config 1 (largest), validation will flag it
    return 1


# --------------------------------------------------------------------------
# PART DESCRIPTIONS — realistic small industrial items
# --------------------------------------------------------------------------
DESCRIPTIONS = [
    # Fasteners & hardware
    "Hex Bolt", "Cap Screw", "Machine Screw", "Set Screw",
    "Lock Nut", "Hex Nut", "Wing Nut", "Flange Nut",
    "Flat Washer", "Lock Washer", "Fender Washer",
    "Cotter Pin", "Clevis Pin", "Dowel Pin", "Roll Pin",
    "Retaining Ring", "E-Clip", "Snap Ring",
    "Rivet", "Pop Rivet", "Blind Rivet",
    "Anchor Bolt", "Threaded Rod", "Stud Bolt",
    # Bearings & seals
    "Ball Bearing", "Roller Bearing", "Needle Bearing", "Thrust Bearing",
    "Sealed Bearing", "Flanged Bearing", "Pillow Block",
    "O-Ring", "Shaft Seal", "Oil Seal", "Lip Seal", "Gasket",
    "V-Ring Seal", "Wiper Seal", "Piston Seal",
    # Electrical
    "Fuse 5A", "Fuse 10A", "Fuse 15A", "Fuse 30A",
    "Relay 24V", "Relay 12V", "Relay 120V",
    "Terminal Block", "Wire Connector", "Butt Splice",
    "Ring Terminal", "Spade Terminal", "Pin Terminal",
    "LED Indicator", "Pilot Light", "Signal Lamp",
    "Push Button", "Toggle Switch", "Rocker Switch",
    "Proximity Sensor", "Photoelectric Sensor", "Limit Switch",
    "Temp Sensor", "Pressure Switch", "Level Switch",
    "Contactor", "Overload Relay", "Circuit Breaker",
    "DIN Rail Mount", "Cable Gland", "Cord Grip",
    # Pneumatics & hydraulics
    "Push-to-Connect Fitting", "Barb Fitting", "Quick Coupler",
    "Elbow Fitting", "Tee Fitting", "Straight Fitting",
    "Check Valve", "Needle Valve", "Ball Valve",
    "Solenoid Valve", "Flow Control", "Pressure Regulator",
    "Air Cylinder", "Pneumatic Actuator",
    # Filters & maintenance
    "Air Filter", "Oil Filter", "Hydraulic Filter",
    "Strainer Element", "Filter Cartridge", "Breather Cap",
    "Grease Fitting", "Lubrication Nipple", "Oil Cup",
    # Springs & dampeners
    "Compression Spring", "Extension Spring", "Torsion Spring",
    "Die Spring", "Wave Spring", "Gas Spring",
    "Vibration Mount", "Bumper", "Shock Absorber",
    # Misc
    "Knob", "Handle", "Latch", "Hinge", "Clamp",
    "Spacer", "Shim Pack", "Key Stock", "Coupling Insert",
    "Belt", "Timing Belt", "V-Belt",
    "Sprocket", "Pulley", "Gear",
    "Chain Link", "Master Link", "Connecting Link",
]

# --------------------------------------------------------------------------
# GENERATION
# --------------------------------------------------------------------------

def generate_weekly_picks() -> int:
    """Pareto-like distribution: most SKUs are slow movers."""
    r = random.random()
    if r < 0.45:
        return random.randint(0, 1)
    elif r < 0.70:
        return random.randint(1, 3)
    elif r < 0.85:
        return random.randint(3, 5)
    elif r < 0.95:
        return random.randint(5, 8)
    else:
        return random.randint(8, 15)


def generate_skus() -> list[dict]:
    """Build 3,500 SKUs with varied dimensions."""
    skus = []

    for i in range(1, 3501):
        # Random dimensions within the user-specified ranges
        height = round(random.uniform(0.5, 5.0), 2)
        width  = round(random.uniform(0.5, 12.0), 2)
        length = round(random.uniform(0.25, 18.0), 2)
        weight = round(random.uniform(0.01, 8.0), 2)

        # Find the best (densest) config this item fits
        config = best_config(width, length, height)

        # Eaches: smaller items tend to get more per cell
        cfg_def = next(c for c in CONFIG_DEFS if c["num"] == config)
        eff = _eff_vol(cfg_def["cells"], cfg_def["height"], cfg_def["fill_pct"])
        sku_vol = length * width * height
        max_ea = max(1, int(eff / sku_vol)) if sku_vol > 0 else 1
        # Vary the eaches — don't always fill to max
        ea_hi = min(50, max_ea)
        eaches = random.randint(1, max(1, ea_hi))

        skus.append({
            "SKU": f"SM-{i:05d}",
            "Description": random.choice(DESCRIPTIONS),
            "Length_in": length,
            "Width_in": width,
            "Height_in": height,
            "Weight_lbs": weight,
            "Eaches": eaches,
            "Weekly_Picks": generate_weekly_picks(),
            "Tray_Config": config,
        })

    # Shuffle before assigning priority
    random.shuffle(skus)

    # Assign Pick_Priority per config group (1 = most picks)
    config_groups: dict[int, list[dict]] = {}
    for s in skus:
        config_groups.setdefault(s["Tray_Config"], []).append(s)

    for group in config_groups.values():
        group.sort(key=lambda s: (-s["Weekly_Picks"], s["SKU"]))
        for idx, s in enumerate(group):
            s["Pick_Priority"] = idx + 1

    return skus


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    skus = generate_skus()

    output_file = "SKU_Data_Small_Items.csv"
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

    total_fit = 0
    for config_num in sorted(config_groups):
        group = config_groups[config_num]
        picks = [s["Weekly_Picks"] for s in group]
        total_fit += len(group)
        cfg_def = next(c for c in CONFIG_DEFS if c["num"] == config_num)
        print(f"  Config {config_num} ({cfg_def['cells']}-cell): "
              f"{len(group)} SKUs, picks {min(picks)}-{max(picks)}/wk")

    # Count items that truly don't fit ANY config
    no_fit = 0
    for s in skus:
        w, l, h = s["Width_in"], s["Length_in"], s["Height_in"]
        if not any(fits_config(w, l, h, c) for c in CONFIG_DEFS):
            no_fit += 1
    print(f"\n  SKUs that don't fit any config: {no_fit}")

    # Dimension distribution
    heights = [s["Height_in"] for s in skus]
    widths  = [s["Width_in"] for s in skus]
    lengths = [s["Length_in"] for s in skus]
    print(f"\n  Height range: {min(heights):.2f}\" - {max(heights):.2f}\"")
    print(f"  Width range:  {min(widths):.2f}\" - {max(widths):.2f}\"")
    print(f"  Length range: {min(lengths):.2f}\" - {max(lengths):.2f}\"")

    # Pick distribution
    print("\nWeekly Picks distribution:")
    pick_counts = [s["Weekly_Picks"] for s in skus]
    max_p = max(pick_counts)
    for p in range(max_p + 1):
        count = pick_counts.count(p)
        bar = "#" * (count // 10)
        print(f"  {p:2d} picks: {count:4d} SKUs  {bar}")


if __name__ == "__main__":
    main()
