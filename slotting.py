"""
VLM Slotting Optimizer  (Cell-Based Model)
==========================================
Assigns SKUs to cells across a multi-tower Vertical Lift Module.

KEY CONCEPTS:
  - TRAY CONFIGURATION: Each tray is set up with a fixed number of
    equal-width cells (e.g. 6, 8, 16, or 30). Think of it as a tray
    with physical dividers creating compartments.

  - 1 SKU PER CELL: Each cell holds exactly one SKU. The "Eaches"
    field in the data tells us how many individual items of that SKU
    are stored in the cell. The cell weight = Weight_lbs * Eaches.

  - TRAY CONFIG SELECTION: When a SKU needs a tray, we pick the
    config with the SMALLEST cells that still fit the item. This
    maximizes density — small items go on 30-cell trays, large items
    go on 6-cell trays.

  - Trays start unconfigured. The first SKU placed on a tray
    determines its configuration (how many cells it has). Once set,
    a tray's config is locked.

ALGORITHM:
  1. Sort SKUs by weekly picks (highest first)
  2. For each SKU, find the smallest tray config it fits in
  3. Look for existing trays of that config with empty cells
  4. If none, assign that config to an unused tray
  5. Golden zone priority for high-pick SKUs
  6. Tower rotation for even distribution
"""

import csv
import sys
from dataclasses import dataclass, field


# =========================================================================
# CONFIGURATION
# =========================================================================

def default_config() -> dict:
    """
    Return the default VLM configuration.

    The 4 tray configs represent how many cells (compartments) a tray
    can be divided into. Fewer cells = wider cells = bigger items.
    """
    return {
        # Machine layout
        "num_towers": 3,
        "trays_per_tower": 50,

        # Tray physical dimensions (inches)
        "tray_width": 78.0,       # left-to-right (cells divide this)
        "tray_depth": 24.0,       # front-to-back

        # Weight
        "tray_max_weight": 750.0,  # lbs per tray (all cells combined)

        # Golden zone
        "golden_zone_start": 20,
        "golden_zone_end": 35,

        # Tray configurations — number of cells per tray.
        # These are the 4 available divider layouts.
        #   6 cells  → ~12.6" wide cells (motors, pumps)
        #   8 cells  → ~9.3"  wide cells (PLCs, drives)
        #  16 cells  → ~4.4"  wide cells (filters, valves)
        #  30 cells  → ~2.1"  wide cells (bearings, fuses)
        "tray_config_1": 6,
        "tray_config_2": 8,
        "tray_config_3": 16,
        "tray_config_4": 30,

        # Spacing
        "divider_width": 0.5,     # inches per divider between cells
        "item_clearance": 0.25,   # inches clearance on each side of item

        # Algorithm
        "high_pick_threshold": 4,
    }


def get_tray_configs(cfg: dict) -> list[int]:
    """
    Extract the list of tray configurations (cell counts) from config.
    Returns them sorted MOST cells first → fewest cells last.

    WHY THIS ORDER?
      More cells = smaller cells = better density. We want the algorithm
      to try fitting items into the densest tray config first. A small
      bearing should go on a 30-cell tray, not waste a slot on a 6-cell.
    """
    configs = sorted({
        cfg["tray_config_1"],
        cfg["tray_config_2"],
        cfg["tray_config_3"],
        cfg["tray_config_4"],
    }, reverse=True)
    return configs


def compute_cell_width(tray_width: float, cell_count: int,
                       divider_width: float) -> float:
    """
    Calculate the usable interior width of each cell.

    A tray with N cells has (N-1) internal dividers:
      |  cell  |  cell  |  cell  |  cell  |
              ^^^      ^^^      ^^^
           dividers (N-1 of them)

    usable_per_cell = (tray_width - (N-1) * divider_width) / N
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
    length: float       # inches (item depth dimension)
    width: float        # inches (item width dimension)
    height: float       # inches
    weight: float       # lbs per each
    eaches: int         # quantity stored in this cell
    weekly_picks: int

    @property
    def cell_weight(self) -> float:
        """Total weight this SKU puts on the tray = weight * eaches."""
        return self.weight * self.eaches


@dataclass
class Tray:
    """
    One tray in a VLM tower.

    A tray starts unconfigured (cell_count=None). When the first SKU is
    placed, it gets configured with a cell count and fixed cell width.
    After that, it has exactly cell_count slots, each holding 0 or 1 SKU.
    """
    tower: int
    tray_num: int

    # Config values (from VLM config, set at creation)
    tray_width: float = 78.0
    tray_depth: float = 24.0
    max_weight: float = 750.0
    golden_start: int = 20
    golden_end: int = 35
    divider_width: float = 0.5
    item_clearance: float = 0.25

    # Tray configuration (set when first SKU is placed)
    cell_count: int | None = None      # None = unconfigured
    cell_width: float = 0.0            # usable width per cell

    # State — cells is a list of (SKU | None), length = cell_count
    cells: list = field(default_factory=list)
    used_weight: float = 0.0

    @property
    def is_golden(self) -> bool:
        return self.golden_start <= self.tray_num <= self.golden_end

    @property
    def is_configured(self) -> bool:
        return self.cell_count is not None

    @property
    def empty_cells(self) -> int:
        """How many cells are still available."""
        if not self.is_configured:
            return 0
        return sum(1 for c in self.cells if c is None)

    @property
    def remaining_weight(self) -> float:
        return self.max_weight - self.used_weight

    def configure(self, cell_count: int):
        """
        Lock this tray into a specific cell layout.
        Called once when the first SKU is assigned to this tray.
        """
        self.cell_count = cell_count
        self.cell_width = compute_cell_width(
            self.tray_width, cell_count, self.divider_width
        )
        self.cells = [None] * cell_count

    def can_fit_sku(self, sku: SKU) -> bool:
        """Check if a SKU fits in an empty cell on this tray."""
        if not self.is_configured or self.empty_cells == 0:
            return False
        if sku.cell_weight > self.remaining_weight:
            return False
        return self._item_fits_cell(sku)

    def _item_fits_cell(self, sku: SKU) -> bool:
        """Check if the item physically fits in a cell (with clearance)."""
        cw = self.cell_width - 2 * self.item_clearance   # usable space
        cd = self.tray_depth - 2 * self.item_clearance

        # Try normal orientation: width in cell width, length in cell depth
        if sku.width <= cw and sku.length <= cd:
            return True
        # Try rotated: length in cell width, width in cell depth
        if sku.length <= cw and sku.width <= cd:
            return True
        return False

    def place(self, sku: SKU) -> int:
        """
        Place a SKU in the first empty cell. Returns the cell index (1-based).
        """
        for i, cell in enumerate(self.cells):
            if cell is None:
                self.cells[i] = sku
                self.used_weight += sku.cell_weight
                return i + 1  # 1-based for user-friendly display
        raise ValueError("No empty cell available")


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
            ))
    return skus


# =========================================================================
# SLOTTING ALGORITHM
# =========================================================================

def create_vlm(cfg: dict) -> list[Tray]:
    """Create all trays (unconfigured) across all towers."""
    trays = []
    for tower in range(1, cfg["num_towers"] + 1):
        for tray_num in range(1, cfg["trays_per_tower"] + 1):
            trays.append(Tray(
                tower=tower,
                tray_num=tray_num,
                tray_width=cfg["tray_width"],
                tray_depth=cfg["tray_depth"],
                max_weight=cfg["tray_max_weight"],
                golden_start=cfg["golden_zone_start"],
                golden_end=cfg["golden_zone_end"],
                divider_width=cfg["divider_width"],
                item_clearance=cfg["item_clearance"],
            ))
    return trays


def find_compatible_configs(sku: SKU, tray_configs: list[int],
                            cfg: dict) -> list[int]:
    """
    Return which tray configs (cell counts) can physically hold this SKU.

    We check each config's cell width against the item dimensions.
    Returns a list sorted from smallest cells to largest (prefer tight fit).

    WHY SMALLEST FIRST?
      If a small bearing fits in a 30-cell tray, we don't want it
      wasting a cell on a 6-cell tray. Small cells for small items,
      big cells for big items.
    """
    compatible = []
    clearance = cfg["item_clearance"]

    for cell_count in tray_configs:
        cell_w = compute_cell_width(
            cfg["tray_width"], cell_count, cfg["divider_width"]
        )
        usable_w = cell_w - 2 * clearance
        usable_d = cfg["tray_depth"] - 2 * clearance

        # Normal orientation or rotated
        fits_normal = sku.width <= usable_w and sku.length <= usable_d
        fits_rotated = sku.length <= usable_w and sku.width <= usable_d

        if fits_normal or fits_rotated:
            compatible.append(cell_count)

    # Sorted most-cells-first since tray_configs is sorted descending
    return compatible


def slot_skus(skus: list[SKU], cfg: dict) -> tuple[list[Tray], list[SKU]]:
    """
    Main slotting algorithm. Returns (trays, unplaced_skus).

    STRATEGY:
      1. Sort SKUs by weekly_picks descending
      2. For each SKU, find the smallest tray config it fits in
      3. Among trays with that config, find one with empty cells + weight
      4. If no existing tray works, configure an unused tray
      5. Golden zone priority for high-pick items
      6. Tower rotation for balance
    """
    trays = create_vlm(cfg)
    tray_configs = get_tray_configs(cfg)
    num_towers = cfg["num_towers"]
    high_pick = cfg["high_pick_threshold"]
    golden_mid = (cfg["golden_zone_start"] + cfg["golden_zone_end"]) / 2

    sorted_skus = sorted(skus, key=lambda s: (-s.weekly_picks, -s.cell_weight))

    # Group trays by tower
    trays_by_tower: dict[int, list[Tray]] = {}
    for t in trays:
        trays_by_tower.setdefault(t.tower, []).append(t)

    unplaced = []

    for idx, sku in enumerate(sorted_skus):
        # Which tray configs can hold this item?
        compatible = find_compatible_configs(sku, tray_configs, cfg)
        if not compatible:
            unplaced.append(sku)
            continue

        # Tower rotation for balance
        tower_order = [
            ((idx + t) % num_towers) + 1
            for t in range(num_towers)
        ]

        placed = False

        # Try each compatible config (smallest cells first)
        for target_config in compatible:
            if placed:
                break

            # Build priority list: golden trays first for high-pick items
            golden_trays = []
            other_trays = []
            for tower_num in tower_order:
                for t in trays_by_tower[tower_num]:
                    if t.is_golden:
                        golden_trays.append(t)
                    else:
                        other_trays.append(t)

            # Sort non-golden by proximity to golden zone
            other_trays.sort(key=lambda t: abs(t.tray_num - golden_mid))

            if sku.weekly_picks >= high_pick:
                priority = golden_trays + other_trays
            else:
                priority = other_trays + golden_trays

            # PASS 1: Find an existing tray with this config that has room
            for tray in priority:
                if (tray.is_configured
                        and tray.cell_count == target_config
                        and tray.can_fit_sku(sku)):
                    tray.place(sku)
                    placed = True
                    break

            if placed:
                break

            # PASS 2: Configure an unused tray with this config
            for tray in priority:
                if not tray.is_configured:
                    tray.configure(target_config)
                    if tray.can_fit_sku(sku):
                        tray.place(sku)
                        placed = True
                        break

        if not placed:
            unplaced.append(sku)

    return trays, unplaced


# =========================================================================
# OUTPUT
# =========================================================================

def write_slotting_map(trays: list[Tray], output_path: str):
    """Write the slotting results to a CSV file."""
    fieldnames = [
        "SKU", "Description", "Tower", "Tray", "Cell",
        "Tray_Config", "Weekly_Picks", "Eaches",
        "Weight_Each_lbs", "Cell_Weight_lbs",
        "Length_in", "Width_in", "Height_in",
        "Tray_Zone",
    ]

    rows = []
    for tray in trays:
        if not tray.is_configured:
            continue
        for cell_idx, sku in enumerate(tray.cells):
            if sku is None:
                continue
            rows.append({
                "SKU": sku.sku_id,
                "Description": sku.description,
                "Tower": tray.tower,
                "Tray": tray.tray_num,
                "Cell": cell_idx + 1,
                "Tray_Config": f"{tray.cell_count}-cell",
                "Weekly_Picks": sku.weekly_picks,
                "Eaches": sku.eaches,
                "Weight_Each_lbs": sku.weight,
                "Cell_Weight_lbs": round(sku.cell_weight, 2),
                "Length_in": sku.length,
                "Width_in": sku.width,
                "Height_in": sku.height,
                "Tray_Zone": "Golden" if tray.is_golden else "Standard",
            })

    rows.sort(key=lambda r: (r["Tower"], r["Tray"], r["Cell"]))

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return rows


def build_summary(trays: list[Tray], unplaced: list[SKU],
                  rows: list[dict], cfg: dict) -> dict:
    """Build a structured summary dict for the web app."""
    used_trays = [t for t in trays if t.is_configured]
    total_placed = sum(
        sum(1 for c in t.cells if c is not None) for t in used_trays
    )
    total_cells = sum(t.cell_count for t in used_trays)
    occupied_cells = sum(
        sum(1 for c in t.cells if c is not None) for t in used_trays
    )

    # Per-tower stats
    towers = []
    for tower_num in range(1, cfg["num_towers"] + 1):
        tower_trays = [t for t in used_trays if t.tower == tower_num]
        towers.append({
            "tower": tower_num,
            "trays_used": len(tower_trays),
            "items": sum(
                sum(1 for c in t.cells if c is not None) for t in tower_trays
            ),
            "golden_items": sum(
                sum(1 for c in t.cells if c is not None)
                for t in tower_trays if t.is_golden
            ),
            "weight": round(sum(t.used_weight for t in tower_trays), 1),
        })

    # Golden zone stats
    golden_rows = [r for r in rows if r["Tray_Zone"] == "Golden"]
    golden_picks = sum(r["Weekly_Picks"] for r in golden_rows)
    total_picks = sum(r["Weekly_Picks"] for r in rows)

    # Tray config usage breakdown
    config_usage = {}
    for t in used_trays:
        key = f"{t.cell_count}-cell"
        if key not in config_usage:
            config_usage[key] = {"trays": 0, "occupied": 0, "total_cells": 0}
        config_usage[key]["trays"] += 1
        config_usage[key]["total_cells"] += t.cell_count
        config_usage[key]["occupied"] += sum(1 for c in t.cells if c is not None)

    summary = {
        "total_placed": total_placed,
        "total_unplaced": len(unplaced),
        "trays_used": len(used_trays),
        "trays_total": len(trays),
        "total_cells": total_cells,
        "occupied_cells": occupied_cells,
        "cell_utilization": round(occupied_cells / total_cells * 100, 1) if total_cells else 0,
        "towers": towers,
        "golden_picks": golden_picks,
        "total_picks": total_picks,
        "golden_pct": round(golden_picks / total_picks * 100, 1) if total_picks else 0,
        "avg_weight_util": 0.0,
        "heaviest_tray": 0.0,
        "weight_limit": cfg["tray_max_weight"],
        "config_usage": config_usage,
        "unplaced_skus": [
            {
                "sku_id": s.sku_id,
                "description": s.description,
                "dims": f"{s.length}x{s.width}x{s.height}",
                "weight": s.weight,
                "eaches": s.eaches,
            }
            for s in unplaced
        ],
    }

    if used_trays:
        weight_pcts = [t.used_weight / cfg["tray_max_weight"] * 100
                       for t in used_trays]
        summary["avg_weight_util"] = round(
            sum(weight_pcts) / len(weight_pcts), 1
        )
        summary["heaviest_tray"] = round(
            max(t.used_weight for t in used_trays), 1
        )

    return summary


def print_summary(trays: list[Tray], unplaced: list[SKU],
                  rows: list[dict], cfg: dict):
    """Print a human-readable summary to the console."""
    s = build_summary(trays, unplaced, rows, cfg)

    print("=" * 60)
    print("  VLM SLOTTING SUMMARY")
    print("=" * 60)
    print(f"  SKUs placed:    {s['total_placed']}")
    print(f"  SKUs unplaced:  {s['total_unplaced']}")
    print(f"  Trays used:     {s['trays_used']} / {s['trays_total']}")
    print(f"  Cells:          {s['occupied_cells']} / {s['total_cells']}"
          f" ({s['cell_utilization']}% utilized)")
    print()

    # Tray config breakdown
    print("  Tray configurations:")
    for config_name, usage in sorted(s["config_usage"].items()):
        print(f"    {config_name}: {usage['trays']} trays,"
              f" {usage['occupied']}/{usage['total_cells']} cells used")
    print()

    for t in s["towers"]:
        print(f"  Tower {t['tower']}:")
        print(f"    Trays used:     {t['trays_used']}")
        print(f"    Items stored:   {t['items']}")
        print(f"    Golden zone:    {t['golden_items']} items")
        print(f"    Total weight:   {t['weight']} lbs")
        print()

    if s["total_picks"] > 0:
        print(f"  Golden zone pick coverage: {s['golden_picks']}/{s['total_picks']}"
              f" weekly picks ({s['golden_pct']}%)")
    print()
    print(f"  Avg tray weight utilization: {s['avg_weight_util']}%")
    print(f"  Heaviest tray: {s['heaviest_tray']} lbs"
          f" (limit: {s['weight_limit']} lbs)")
    print()

    if s["unplaced_skus"]:
        print("  UNPLACED ITEMS:")
        for u in s["unplaced_skus"]:
            print(f"    {u['sku_id']}: {u['description']}"
                  f" ({u['dims']} in, {u['weight']} lbs,"
                  f" {u['eaches']} eaches)")
    print("=" * 60)


# =========================================================================
# MAIN
# =========================================================================

def run_slotting(input_csv: str, output_csv: str,
                 cfg: dict | None = None) -> tuple[list[dict], dict]:
    """
    Full slotting pipeline: load → slot → write → summarize.
    Returns (slotting_rows, summary_dict).
    """
    if cfg is None:
        cfg = default_config()

    skus = load_skus(input_csv)
    print(f"Loaded {len(skus)} SKUs from {input_csv}")

    # Show cell widths for each config
    for cc in get_tray_configs(cfg):
        cw = compute_cell_width(cfg["tray_width"], cc, cfg["divider_width"])
        print(f"  {cc}-cell tray: {cw:.1f}\" per cell")

    trays, unplaced = slot_skus(skus, cfg)
    rows = write_slotting_map(trays, output_csv)
    print(f"Slotting map written to {output_csv}")

    summary = build_summary(trays, unplaced, rows, cfg)
    print_summary(trays, unplaced, rows, cfg)
    return rows, summary


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "sample_skus.csv"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "slotting_map.csv"
    run_slotting(input_file, output_file)
