"""
VLM Slotting Optimizer  (Direct Mapping Model)
===============================================
Assigns SKUs to cells using a deterministic Pick Priority → Cell Number
mapping across a multi-tower Vertical Lift Module.

KEY CONCEPTS:
  - PICK PRIORITY: Each SKU has a Pick_Priority (1 = fastest mover) within
    its Tray Configuration. This number IS the Cell Number.

  - CELL NUMBER FORMULA: Cell numbers interleave across towers so that
    top-priority SKUs are evenly distributed:
      Cell 1 → Tower 1, Cell 2 → Tower 2, Cell 3 → Tower 3,
      Cell 4 → Tower 1, Cell 5 → Tower 2, ...

  - From a Cell Number, we derive the exact physical location:
      Tower           = ((cell_number - 1) % num_towers) + 1
      Position        = ((cell_number - 1) // num_towers) + 1
      Config Tray #   = ((position - 1) // cells_per_tray) + 1
      Cell Index      = ((position - 1) % cells_per_tray) + 1

  - Cell Index 1 = front-left of the tray (closest to operator, leftmost).
    Numbers increase left-to-right, front-to-back.

  - VALIDATION: The code validates that each SKU physically fits its
    assigned cell (dimensions, height, volume, weight). Placement is
    driven by the data, validation catches errors.

FLOW:
  1. Load SKUs (with Tray_Config and Pick_Priority from the data)
  2. Validate each SKU against its config (dimensions, volume, height)
  3. Map Pick_Priority → Cell Number → (Tower, Tray, Cell)
  4. Check tray weight limits
  5. Output slotting map
"""

import csv
import math
import sys
from dataclasses import dataclass, field


# =========================================================================
# CONFIGURATION
# =========================================================================

def default_config() -> dict:
    """
    Return the default VLM configuration.

    The 4 tray configs represent how many cells (compartments) a tray
    can be divided into. Each config also defines height, tolerance,
    and fill capacity for volume-based validation.
    """
    return {
        # Machine layout
        "zone": "V",              # single character zone label for BIN IDs
        "num_towers": 3,
        "trays_per_tower": 64,    # computed: sum of all height-specific trays

        # Physical tray inventory by height (per tower, both sides combined)
        "trays_2in": 32,          # 16 per side
        "trays_4in": 32,          # 16 per side
        "trays_6in": 0,
        "trays_8in": 0,

        # Slots consumed per tray by height (includes tray + clearance)
        "slots_per_2in_tray": 9,
        "slots_per_4in_tray": 17,
        "slots_per_6in_tray": 49,
        "slots_per_8in_tray": 65,

        # Tray physical dimensions (inches)
        "tray_width": 78.0,       # left-to-right (cells divide this)
        "tray_depth": 24.0,       # front-to-back

        # Tower slot configuration
        "slots_per_tower": 832,   # computed: (32*9)+(32*17)+(0*49)+(0*65)
        "slot_spacing": 0.25,     # inches between each slot track
        "reserved_slots": 10,     # slots reserved for tray shuffling (unusable)

        # Weight
        "tray_max_weight": 750.0,  # lbs per tray (all cells combined)

        # Zone thresholds (% of total picks — top trays by picks/week)
        "golden_zone_pct": 30,
        "silver_zone_pct": 50,
        "bronze_zone_pct": 75,

        # How many tray configurations are defined (keys below)
        "num_tray_configs": 12,

        # Tray configurations: 3 heights (2", 4", 6") × 4 cell counts (6, 8, 16, 30)
        # height     = max item height for this tray layout (inches)
        # height_tol = % an item can exceed the height (e.g. 10 → 10%)
        # fill_pct   = usable fraction of cell volume (e.g. 85 → 85%)
        #
        # 2" height trays (thin/flat parts)
        "tray_config_1_cells": 6,
        "tray_config_1_height": 2.0,
        "tray_config_1_height_tol": 10,
        "tray_config_1_fill_pct": 85,

        "tray_config_2_cells": 8,
        "tray_config_2_height": 2.0,
        "tray_config_2_height_tol": 10,
        "tray_config_2_fill_pct": 85,

        "tray_config_3_cells": 16,
        "tray_config_3_height": 2.0,
        "tray_config_3_height_tol": 10,
        "tray_config_3_fill_pct": 85,

        "tray_config_4_cells": 30,
        "tray_config_4_height": 2.0,
        "tray_config_4_height_tol": 10,
        "tray_config_4_fill_pct": 85,

        # 4" height trays (standard parts)
        "tray_config_5_cells": 6,
        "tray_config_5_height": 4.0,
        "tray_config_5_height_tol": 10,
        "tray_config_5_fill_pct": 85,

        "tray_config_6_cells": 8,
        "tray_config_6_height": 4.0,
        "tray_config_6_height_tol": 10,
        "tray_config_6_fill_pct": 85,

        "tray_config_7_cells": 16,
        "tray_config_7_height": 4.0,
        "tray_config_7_height_tol": 10,
        "tray_config_7_fill_pct": 85,

        "tray_config_8_cells": 30,
        "tray_config_8_height": 4.0,
        "tray_config_8_height_tol": 10,
        "tray_config_8_fill_pct": 85,

        # 6" height trays (tall parts)
        "tray_config_9_cells": 6,
        "tray_config_9_height": 6.0,
        "tray_config_9_height_tol": 10,
        "tray_config_9_fill_pct": 85,

        "tray_config_10_cells": 8,
        "tray_config_10_height": 6.0,
        "tray_config_10_height_tol": 10,
        "tray_config_10_fill_pct": 85,

        "tray_config_11_cells": 16,
        "tray_config_11_height": 6.0,
        "tray_config_11_height_tol": 10,
        "tray_config_11_fill_pct": 85,

        "tray_config_12_cells": 30,
        "tray_config_12_height": 6.0,
        "tray_config_12_height_tol": 10,
        "tray_config_12_fill_pct": 85,

        # Spacing
        "divider_width": 0.5,     # inches per divider between cells
        "item_clearance": 0.25,   # inches clearance on each side of item

        # Algorithm
        "high_pick_threshold": 4,
    }


def get_tray_configs(cfg: dict) -> dict[int, dict]:
    """
    Extract the tray configurations as a dict keyed by config number (1-4).
    Each value is a dict: {cells, height, height_tol, fill_pct}.
    """
    configs = {}
    for i in range(1, cfg.get("num_tray_configs", 4) + 1):
        configs[i] = {
            "cells": cfg[f"tray_config_{i}_cells"],
            "height": cfg[f"tray_config_{i}_height"],
            "height_tol": cfg[f"tray_config_{i}_height_tol"],
            "fill_pct": cfg[f"tray_config_{i}_fill_pct"],
        }
    return configs


def compute_cell_width(tray_width: float, cell_count: int,
                       divider_width: float) -> float:
    """
    Calculate the usable interior width of each cell.

    A tray with N cells has (N-1) internal dividers:
      |  cell  |  cell  |  cell  |  cell  |
              ^^^      ^^^      ^^^
           dividers (N-1 of them)
    """
    total_divider_space = (cell_count - 1) * divider_width
    return (tray_width - total_divider_space) / cell_count


# =========================================================================
# DATA STRUCTURES
# =========================================================================

@dataclass
class SKU:
    """One inventory item to be slotted."""
    sku_id: str
    description: str
    length: float         # inches
    width: float          # inches
    height: float         # inches
    weight: float         # lbs per each
    eaches: int           # quantity stored in this cell
    weekly_picks: int
    tray_config: int      # which config (1-4) this SKU is assigned to
    pick_priority: int    # rank within its config (1 = fastest mover)

    @property
    def cell_weight(self) -> float:
        """Total weight this SKU puts on the tray = weight * eaches."""
        return self.weight * self.eaches

    @property
    def sku_volume(self) -> float:
        """Cubic volume of a single each (length x width x height)."""
        return self.length * self.width * self.height

    @property
    def total_volume(self) -> float:
        """Cubic volume of all eaches (sku_volume x eaches)."""
        return self.sku_volume * self.eaches


# =========================================================================
# DATA LOADING
# =========================================================================

def load_skus(csv_path: str) -> list[SKU]:
    """Read SKUs from a CSV file."""
    skus = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skus.append(SKU(
                sku_id=row["SKU"],
                description=row["Description"],
                length=float(row["Length_in"]),
                width=float(row["Width_in"]),
                height=float(row["Height_in"]),
                weight=float(row["Weight_lbs"]),
                eaches=int(row["Eaches"]),
                weekly_picks=int(row["Weekly_Picks"]),
                tray_config=int(row["Tray_Config"]),
                pick_priority=int(row["Pick_Priority"]),
            ))
    return skus


# =========================================================================
# PRE-VALIDATION
# =========================================================================

def validate_skus(skus: list[SKU], cfg: dict) -> list[dict]:
    """
    Validate every SKU against its assigned tray configuration.

    Checks:
      1. Dimensions — single item fits cell width x tray depth (with rotation)
      2. Height — single item fits tray height + tolerance
      3. Volume — total SKU volume (all eaches) fits effective cell volume
      4. Pick Priority — no duplicates within a config

    Returns a list of error dicts: {sku_id, check, message}
    An empty list means all SKUs passed validation.
    """
    errors = []
    tray_configs = get_tray_configs(cfg)
    clearance = cfg["item_clearance"]

    # Check for duplicate pick priorities within each config
    priority_map: dict[int, dict[int, list[str]]] = {}
    for sku in skus:
        priority_map.setdefault(sku.tray_config, {})
        priority_map[sku.tray_config].setdefault(sku.pick_priority, [])
        priority_map[sku.tray_config][sku.pick_priority].append(sku.sku_id)

    for config_num, priorities in priority_map.items():
        for priority, sku_ids in priorities.items():
            if len(sku_ids) > 1:
                for sid in sku_ids:
                    errors.append({
                        "sku_id": sid,
                        "check": "duplicate_priority",
                        "message": (f"Pick Priority {priority} is used by "
                                    f"{len(sku_ids)} SKUs in Config {config_num}: "
                                    f"{', '.join(sku_ids)}"),
                    })

    for sku in skus:
        tc = tray_configs.get(sku.tray_config)
        if tc is None:
            errors.append({
                "sku_id": sku.sku_id,
                "check": "invalid_config",
                "message": f"Tray_Config {sku.tray_config} is not defined (must be 1-4)",
            })
            continue

        cell_count = tc["cells"]
        cell_w = compute_cell_width(
            cfg["tray_width"], cell_count, cfg["divider_width"]
        )
        usable_w = cell_w - 2 * clearance
        usable_d = cfg["tray_depth"] - 2 * clearance

        # 1. Dimensional check (allow rotation)
        fits_normal = sku.width <= usable_w and sku.length <= usable_d
        fits_rotated = sku.length <= usable_w and sku.width <= usable_d
        if not (fits_normal or fits_rotated):
            errors.append({
                "sku_id": sku.sku_id,
                "check": "dimensions",
                "message": (f"Item {sku.width}\"W x {sku.length}\"L doesn't fit "
                            f"cell {usable_w:.1f}\"W x {usable_d:.1f}\"D "
                            f"(Config {sku.tray_config}, {cell_count}-cell)"),
            })

        # 2. Height check
        if tc["height"] > 0:
            max_h = tc["height"] * (1 + tc["height_tol"] / 100.0)
            if sku.height > max_h:
                errors.append({
                    "sku_id": sku.sku_id,
                    "check": "height",
                    "message": (f"Item height {sku.height}\" exceeds "
                                f"tray height {tc['height']}\" + "
                                f"{tc['height_tol']}% tolerance = {max_h:.1f}\" "
                                f"(Config {sku.tray_config})"),
                })

        # 3. Volume check
        cell_vol = cell_w * cfg["tray_depth"] * tc["height"]
        eff_vol = cell_vol * tc["fill_pct"] / 100.0
        if eff_vol > 0 and sku.total_volume > eff_vol:
            errors.append({
                "sku_id": sku.sku_id,
                "check": "volume",
                "message": (f"Total SKU volume {sku.total_volume:.1f} cu in "
                            f"({sku.eaches} ea x {sku.sku_volume:.1f}) exceeds "
                            f"effective cell volume {eff_vol:.1f} cu in "
                            f"({tc['fill_pct']}% of {cell_vol:.1f}) "
                            f"(Config {sku.tray_config})"),
            })

    return errors


# =========================================================================
# CELL NUMBER MAPPING
# =========================================================================

def config_letter(config_num: int) -> str:
    """Convert config number to letter: 1=A, 2=B, ... 26=Z."""
    if 1 <= config_num <= 26:
        return chr(64 + config_num)
    return "?"


def build_bin_label(zone: str, physical_tray: int,
                    config_num: int, cell_index: int) -> str:
    """
    Build an 8-character BIN LABEL for a cell.

    Format: Zone(1) + Tray(4) + ConfigLetter(1) + Cell(2)
    Example: V1002B01 = Zone V, Tray 1002 (Tower 1), Config B, Cell 01

    Tray numbers encode the tower: 1xxx = Tower 1, 2xxx = Tower 2, etc.
    """
    return f"{zone}{physical_tray:04d}{config_letter(config_num)}{cell_index:02d}"


def compute_cell_location(pick_priority: int, num_towers: int,
                          cells_per_tray: int,
                          tower_offset: int = 0) -> dict:
    """
    Map a Pick Priority to a physical cell location.

    The cell number interleaves across towers with an optional offset
    to balance which tower gets the #1 pick across configs:
      offset=0: Cell 1 → Tower 1, Cell 2 → Tower 2, Cell 3 → Tower 3
      offset=1: Cell 1 → Tower 2, Cell 2 → Tower 3, Cell 3 → Tower 1
      offset=2: Cell 1 → Tower 3, Cell 2 → Tower 1, Cell 3 → Tower 2

    Returns dict with: cell_number, tower, config_tray, cell_index
    """
    cell_number = pick_priority
    tower = ((cell_number - 1 + tower_offset) % num_towers) + 1
    position_in_tower = ((cell_number - 1) // num_towers) + 1
    config_tray = ((position_in_tower - 1) // cells_per_tray) + 1
    cell_index = ((position_in_tower - 1) % cells_per_tray) + 1
    return {
        "cell_number": cell_number,
        "tower": tower,
        "config_tray": config_tray,
        "cell_index": cell_index,
    }


def assign_physical_trays(skus: list[SKU], cfg: dict) -> dict:
    """
    Determine which physical tray positions each config occupies per tower.

    Strategy:
      1. Group tray configs by their height (2", 4", 6", 8").
      2. Each height group can only use trays from its matching inventory
         pool (trays_2in, trays_4in, etc.).
      3. Within each pool, configs are allocated proportionally to need,
         capped to available trays, with highest-pick configs getting
         the lowest tray numbers.

    Returns: {(tower, config_num, config_tray): physical_tray_num}
    """
    tray_configs = get_tray_configs(cfg)
    num_towers = cfg["num_towers"]

    # Available trays per tower by height
    tray_pools = {
        2.0: cfg.get("trays_2in", 0),
        4.0: cfg.get("trays_4in", 0),
        6.0: cfg.get("trays_6in", 0),
        8.0: cfg.get("trays_8in", 0),
    }

    # Count trays needed per config (max config_tray across all SKUs)
    config_trays_needed: dict[int, int] = {}
    for sku in skus:
        tc = tray_configs[sku.tray_config]
        offset = (sku.tray_config - 1) % num_towers
        loc = compute_cell_location(
            sku.pick_priority, num_towers, tc["cells"], offset
        )
        config_trays_needed[sku.tray_config] = max(
            config_trays_needed.get(sku.tray_config, 0), loc["config_tray"]
        )

    # Total picks per config (for priority ordering)
    config_picks: dict[int, int] = {}
    for sku in skus:
        config_picks[sku.tray_config] = (
            config_picks.get(sku.tray_config, 0) + sku.weekly_picks
        )

    # Group configs by their tray height
    height_groups: dict[float, list[int]] = {}
    for config_num in config_trays_needed:
        h = tray_configs[config_num]["height"]
        height_groups.setdefault(h, []).append(config_num)

    # Assign physical tray positions per tower
    # Tray numbers encode the tower: Tower 1 = 1001+, Tower 2 = 2001+, etc.
    tray_map = {}
    for tower in range(1, num_towers + 1):
        pos = 1  # running position counter within this tower

        # Process each height group (sorted by height for deterministic ordering)
        for height in sorted(height_groups.keys()):
            configs_at_height = height_groups[height]
            pool_size = tray_pools.get(height, 0)

            # Determine allocation for this height group
            needed = {cn: config_trays_needed[cn] for cn in configs_at_height}
            total_needed = sum(needed.values())

            if pool_size == 0:
                alloc = {cn: 0 for cn in configs_at_height}
            elif total_needed > pool_size:
                # Scale proportionally, at least 1 tray each
                alloc = {}
                for cn, n in needed.items():
                    alloc[cn] = max(1, round(n * pool_size / total_needed))
                while sum(alloc.values()) > pool_size:
                    biggest = max(alloc, key=alloc.get)
                    alloc[biggest] -= 1
            else:
                alloc = dict(needed)

            # Sort by picks descending (highest gets first positions)
            sorted_configs = sorted(
                alloc.keys(),
                key=lambda c: config_picks.get(c, 0),
                reverse=True,
            )

            for config_num in sorted_configs:
                trays_for_config = alloc[config_num]
                for ct in range(1, trays_for_config + 1):
                    tray_map[(tower, config_num, ct)] = tower * 1000 + pos
                    pos += 1

    return tray_map


# =========================================================================
# SLOTTING
# =========================================================================

def slot_skus(skus: list[SKU], cfg: dict) -> tuple[list[dict], list[dict]]:
    """
    Main slotting: map each SKU's Pick Priority to a cell location.

    Returns (placed_rows, warnings).
    Warnings include tray weight overages.
    """
    tray_configs = get_tray_configs(cfg)
    num_towers = cfg["num_towers"]
    tray_map = assign_physical_trays(skus, cfg)
    warnings = []

    rows = []
    # Track tray weights: (tower, physical_tray) → total weight
    tray_weights: dict[tuple[int, int], float] = {}

    for sku in skus:
        tc = tray_configs[sku.tray_config]
        offset = (sku.tray_config - 1) % num_towers
        loc = compute_cell_location(
            sku.pick_priority, num_towers, tc["cells"], offset
        )

        physical_tray = tray_map.get(
            (loc["tower"], sku.tray_config, loc["config_tray"])
        )
        if physical_tray is None:
            warnings.append({
                "sku_id": sku.sku_id,
                "type": "no_tray",
                "message": f"No physical tray available for Config {sku.tray_config} "
                           f"Tray {loc['config_tray']} in Tower {loc['tower']}",
            })
            continue

        # Track tray weight
        tray_key = (loc["tower"], physical_tray)
        tray_weights[tray_key] = tray_weights.get(tray_key, 0) + sku.cell_weight

        # Cell volume calculations
        cell_w = compute_cell_width(
            cfg["tray_width"], tc["cells"], cfg["divider_width"]
        )
        cell_vol = cell_w * cfg["tray_depth"] * tc["height"]
        eff_vol = cell_vol * tc["fill_pct"] / 100.0

        # Build BIN LABEL: Zone + Tower + Tray(3) + Config Letter + Cell(2)
        bin_label = build_bin_label(
            cfg["zone"], physical_tray,
            sku.tray_config, loc["cell_index"],
        )

        rows.append({
            "Bin_Label": bin_label,
            "SKU": sku.sku_id,
            "Description": sku.description,
            "Tower": loc["tower"],
            "Tray": physical_tray,
            "Cell": loc["cell_index"],
            "Tray_Config": f"{tc['cells']}-cell {tc['height']:.0f}\"",
            "Config_Tray": loc["config_tray"],
            "Pick_Priority": sku.pick_priority,
            "Weekly_Picks": sku.weekly_picks,
            "Eaches": sku.eaches,
            "Weight_Each_lbs": sku.weight,
            "Cell_Weight_lbs": round(sku.cell_weight, 2),
            "Length_in": sku.length,
            "Width_in": sku.width,
            "Height_in": sku.height,
            "SKU_Vol_in3": round(sku.sku_volume, 1),
            "Total_Vol_in3": round(sku.total_volume, 1),
            "Cell_Vol_in3": round(cell_vol, 1),
            "Fill_Pct": round(sku.total_volume / cell_vol * 100, 1) if cell_vol else 0,
            "Tray_Zone": "Standard",  # updated below by pick-based golden zone
        })

    # Check tray weight limits
    for (tower, tray_num), total_wt in tray_weights.items():
        if total_wt > cfg["tray_max_weight"]:
            warnings.append({
                "sku_id": "N/A",
                "type": "weight",
                "message": (f"Tower {tower} Tray {tray_num}: "
                            f"{total_wt:.1f} lbs exceeds limit "
                            f"of {cfg['tray_max_weight']} lbs"),
            })

    # ---- ZONE ASSIGNMENT: per-SKU based on individual picks/week ----
    # Sort SKUs by picks descending, accumulate, and assign zones:
    # Golden     = top SKUs up to golden_zone_pct% of total picks
    # Silver     = next SKUs up to silver_zone_pct%
    # Bronze     = next SKUs up to bronze_zone_pct%
    # Standard   = remaining SKUs with picks > 0
    # Slow Mover = SKUs with 0 weekly picks
    total_picks = sum(r["Weekly_Picks"] for r in rows)
    golden_limit = total_picks * cfg["golden_zone_pct"] / 100
    silver_limit = total_picks * cfg["silver_zone_pct"] / 100
    bronze_limit = total_picks * cfg["bronze_zone_pct"] / 100

    # Sort by picks descending (stable sort preserves order for ties)
    ranked = sorted(range(len(rows)), key=lambda i: -rows[i]["Weekly_Picks"])

    accumulated = 0
    for idx in ranked:
        picks = rows[idx]["Weekly_Picks"]
        if picks == 0:
            rows[idx]["Tray_Zone"] = "Slow Mover"
        elif accumulated + picks <= golden_limit:
            rows[idx]["Tray_Zone"] = "Golden"
            accumulated += picks
        elif accumulated + picks <= silver_limit:
            rows[idx]["Tray_Zone"] = "Silver"
            accumulated += picks
        elif accumulated + picks <= bronze_limit:
            rows[idx]["Tray_Zone"] = "Bronze"
            accumulated += picks
        else:
            rows[idx]["Tray_Zone"] = "Standard"
            accumulated += picks

    rows.sort(key=lambda r: (r["Tower"], r["Tray"], r["Cell"]))
    return rows, warnings


# =========================================================================
# OUTPUT
# =========================================================================

def write_slotting_map(rows: list[dict], output_path: str):
    """Write the slotting results to a CSV file."""
    if not rows:
        return

    fieldnames = [
        "Bin_Label", "SKU", "Description", "Tower", "Tray", "Cell",
        "Tray_Config", "Config_Tray",
        "Pick_Priority", "Weekly_Picks", "Eaches",
        "Weight_Each_lbs", "Cell_Weight_lbs",
        "Length_in", "Width_in", "Height_in",
        "SKU_Vol_in3", "Total_Vol_in3", "Cell_Vol_in3", "Fill_Pct",
        "Tray_Zone",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict], warnings: list[dict],
                  skus: list[SKU], cfg: dict) -> dict:
    """Build a structured summary dict for the web app."""
    num_towers = cfg["num_towers"]
    total_placed = len(rows)

    # Per-tower stats
    slot_spacing = cfg["slot_spacing"]
    slots_per_tower = cfg["slots_per_tower"]
    reserved_slots = cfg["reserved_slots"]
    usable_slots = slots_per_tower - reserved_slots
    towers = []
    for tower_num in range(1, num_towers + 1):
        tower_rows = [r for r in rows if r["Tower"] == tower_num]
        # Unique trays and their heights
        tray_heights: dict[int, float] = {}
        for r in tower_rows:
            if r["Tray"] not in tray_heights:
                # Parse height from Tray_Config string (e.g. "16-cell 2\"")
                parts = r["Tray_Config"].rstrip('"').rsplit(" ", 1)
                tray_heights[r["Tray"]] = float(parts[-1])
        trays_used = len(tray_heights)
        total_height = sum(tray_heights.values())
        slots_used = int(total_height / slot_spacing) if slot_spacing > 0 else 0

        # Tray inventory utilization by height
        trays_by_height: dict[str, set] = {}
        for r in tower_rows:
            parts = r["Tray_Config"].rstrip('"').rsplit(" ", 1)
            h_str = parts[-1]
            trays_by_height.setdefault(h_str, set()).add(r["Tray"])
        tray_inventory = []
        for h_str, pool_key in [("2", "trays_2in"), ("4", "trays_4in"),
                                 ("6", "trays_6in"), ("8", "trays_8in")]:
            available = cfg.get(pool_key, 0)
            used = len(trays_by_height.get(h_str, set()))
            if available > 0 or used > 0:
                tray_inventory.append({
                    "height": h_str, "used": used, "available": available,
                })

        towers.append({
            "tower": tower_num,
            "trays_used": trays_used,
            "items": len(tower_rows),
            "total_height": round(total_height, 1),
            "slots_used": slots_used,
            "slots_available": usable_slots,
            "slots_total": slots_per_tower,
            "reserved_slots": reserved_slots,
            "tray_inventory": tray_inventory,
            "golden_items": sum(
                1 for r in tower_rows if r["Tray_Zone"] == "Golden"
            ),
            "silver_items": sum(
                1 for r in tower_rows if r["Tray_Zone"] == "Silver"
            ),
            "bronze_items": sum(
                1 for r in tower_rows if r["Tray_Zone"] == "Bronze"
            ),
            "slow_mover_items": sum(
                1 for r in tower_rows if r["Tray_Zone"] == "Slow Mover"
            ),
            "weight": round(
                sum(r["Cell_Weight_lbs"] for r in tower_rows), 1
            ),
        })

    # Overall stats
    all_trays = set((r["Tower"], r["Tray"]) for r in rows)
    golden_rows = [r for r in rows if r["Tray_Zone"] == "Golden"]
    golden_picks = sum(r["Weekly_Picks"] for r in golden_rows)
    silver_rows = [r for r in rows if r["Tray_Zone"] == "Silver"]
    silver_picks = sum(r["Weekly_Picks"] for r in silver_rows)
    bronze_rows = [r for r in rows if r["Tray_Zone"] == "Bronze"]
    bronze_picks = sum(r["Weekly_Picks"] for r in bronze_rows)
    slow_mover_count = sum(1 for r in rows if r["Tray_Zone"] == "Slow Mover")
    total_picks = sum(r["Weekly_Picks"] for r in rows)

    # Config usage
    tray_configs = get_tray_configs(cfg)
    config_usage = {}
    for r in rows:
        key = r["Tray_Config"]
        if key not in config_usage:
            config_usage[key] = {"trays": set(), "items": 0,
                                 "cell_vol": r["Cell_Vol_in3"]}
        config_usage[key]["trays"].add((r["Tower"], r["Tray"]))
        config_usage[key]["items"] += 1
    # Convert sets to counts; add cell dimensions
    for key in config_usage:
        # Find the matching tray config by parsing the key (e.g. "16-cell 2\"")
        tc_match = None
        for tc_num, tc in tray_configs.items():
            label = f"{tc['cells']}-cell {tc['height']:.0f}\""
            if label == key:
                tc_match = tc
                break
        cell_w = round(compute_cell_width(
            cfg["tray_width"], tc_match["cells"], cfg["divider_width"]
        ), 1) if tc_match else 0
        cell_d = cfg["tray_depth"]
        cell_h = tc_match["height"] if tc_match else 0
        config_usage[key] = {
            "trays": len(config_usage[key]["trays"]),
            "items": config_usage[key]["items"],
            "cell_vol": config_usage[key]["cell_vol"],
            "cell_dims": f"{cell_w}\"W x {cell_d}\"D x {cell_h:.0f}\"H",
        }

    # Tray weight stats
    tray_weights: dict[tuple, float] = {}
    for r in rows:
        tk = (r["Tower"], r["Tray"])
        tray_weights[tk] = tray_weights.get(tk, 0) + r["Cell_Weight_lbs"]

    heaviest = max(tray_weights.values()) if tray_weights else 0
    avg_wt = (
        sum(tray_weights.values()) / len(tray_weights)
        if tray_weights else 0
    )

    return {
        "total_placed": total_placed,
        "total_skus": len(skus),
        "trays_used": len(all_trays),
        "trays_total": num_towers * cfg["trays_per_tower"],
        "towers": towers,
        "golden_picks": golden_picks,
        "total_picks": total_picks,
        "golden_pct": round(
            golden_picks / total_picks * 100, 1
        ) if total_picks else 0,
        "silver_picks": silver_picks,
        "silver_pct": round(
            silver_picks / total_picks * 100, 1
        ) if total_picks else 0,
        "golden_count": len(golden_rows),
        "silver_count": len(silver_rows),
        "bronze_picks": bronze_picks,
        "bronze_pct": round(
            bronze_picks / total_picks * 100, 1
        ) if total_picks else 0,
        "bronze_count": len(bronze_rows),
        "slow_mover_count": slow_mover_count,
        "slow_mover_pct": round(
            slow_mover_count / total_placed * 100, 1
        ) if total_placed else 0,
        "heaviest_tray": round(heaviest, 1),
        "avg_tray_weight": round(avg_wt, 1),
        "weight_limit": cfg["tray_max_weight"],
        "config_usage": config_usage,
        "warnings": warnings,
    }


def print_summary(rows: list[dict], warnings: list[dict],
                  skus: list[SKU], cfg: dict):
    """Print a human-readable summary to the console."""
    s = build_summary(rows, warnings, skus, cfg)

    print("=" * 60)
    print("  VLM SLOTTING SUMMARY")
    print("=" * 60)
    print(f"  SKUs placed:    {s['total_placed']} / {s['total_skus']}")
    print(f"  Trays used:     {s['trays_used']} / {s['trays_total']}")
    print()

    print("  Tray configurations:")
    for config_name, usage in sorted(s["config_usage"].items()):
        print(f"    {config_name}: {usage['trays']} trays, "
              f"{usage['items']} items")
    print()

    for t in s["towers"]:
        print(f"  Tower {t['tower']}:")
        print(f"    Trays used:     {t['trays_used']}")
        print(f"    Items stored:   {t['items']}")
        print(f"    Golden:         {t['golden_items']} items")
        print(f"    Silver:         {t['silver_items']} items")
        print(f"    Bronze:         {t['bronze_items']} items")
        print(f"    Slow Movers:    {t['slow_mover_items']} items")
        print(f"    Stacked height: {t['total_height']}\"")
        print(f"    Slots used:     {t['slots_used']} / {t['slots_available']}"
              f" ({t['reserved_slots']} reserved)")
        print(f"    Total weight:   {t['weight']} lbs")
        print()

    if s["total_picks"] > 0:
        print(f"  Golden zone: {s['golden_picks']}/{s['total_picks']}"
              f" weekly picks ({s['golden_pct']}%)")
        print(f"  Silver zone: {s['silver_picks']}/{s['total_picks']}"
              f" weekly picks ({s['silver_pct']}%)")
        print(f"  Bronze zone: {s['bronze_picks']}/{s['total_picks']}"
              f" weekly picks ({s['bronze_pct']}%)")
    print(f"  Slow Movers: {s['slow_mover_count']} SKUs (0 picks/week)")
    print()
    print(f"  Avg tray weight:  {s['avg_tray_weight']} lbs")
    print(f"  Heaviest tray:    {s['heaviest_tray']} lbs"
          f" (limit: {s['weight_limit']} lbs)")

    if warnings:
        print(f"\n  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    [{w['type']}] {w['message']}")

    print("=" * 60)


# =========================================================================
# MAIN
# =========================================================================

def run_slotting(input_csv: str, output_csv: str,
                 cfg: dict | None = None) -> tuple[list[dict], dict]:
    """
    Full slotting pipeline: load → validate → slot → write → summarize.
    Returns (slotting_rows, summary_dict).
    """
    if cfg is None:
        cfg = default_config()

    skus = load_skus(input_csv)
    print(f"Loaded {len(skus)} SKUs from {input_csv}")

    # Show config details
    tray_configs = get_tray_configs(cfg)
    for config_num in sorted(tray_configs):
        tc = tray_configs[config_num]
        cw = compute_cell_width(
            cfg["tray_width"], tc["cells"], cfg["divider_width"]
        )
        cell_vol = cw * cfg["tray_depth"] * tc["height"]
        eff_vol = cell_vol * tc["fill_pct"] / 100.0
        max_h = tc["height"] * (1 + tc["height_tol"] / 100.0)
        print(f"  Config {config_num} ({tc['cells']}-cell): "
              f"{cw:.1f}\"W x {cfg['tray_depth']}\"D x {tc['height']}\"H "
              f"(max {max_h:.1f}\"), "
              f"vol {cell_vol:.0f} -> {eff_vol:.0f} cu in ({tc['fill_pct']}%)")

    # Pre-validate
    errors = validate_skus(skus, cfg)
    if errors:
        print(f"\n  VALIDATION ERRORS ({len(errors)}):")
        for e in errors:
            print(f"    {e['sku_id']}: [{e['check']}] {e['message']}")
        print()

    # Exclude SKUs that failed validation — they don't physically fit
    failed_sku_ids = set(e["sku_id"] for e in errors)
    valid_skus = [s for s in skus if s.sku_id not in failed_sku_ids]
    if failed_sku_ids:
        print(f"  {len(failed_sku_ids)} SKUs excluded from placement due to validation errors")

    # Slot (only valid SKUs)
    rows, warnings = slot_skus(valid_skus, cfg)
    write_slotting_map(rows, output_csv)
    print(f"Slotting map written to {output_csv}")

    summary = build_summary(rows, warnings, skus, cfg)
    summary["validation_errors"] = errors
    print_summary(rows, warnings, skus, cfg)
    return rows, summary


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "sample_skus.csv"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "slotting_map.csv"
    run_slotting(input_file, output_file)
