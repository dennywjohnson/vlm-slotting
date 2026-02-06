"""
Generate 500 sample SKUs representing slow-moving industrial parts
typically stored in a Vertical Lift Module (VLM).

WHY THIS APPROACH:
- We define "categories" of real industrial parts so the data looks realistic
  (not just random numbers). Each category has typical size/weight ranges.
- Weekly picks follow a right-skewed distribution: most items are slow movers
  (0-3 picks/week), a few are moderate (4-6), and very few are fast (7-10).
  This mirrors the Pareto pattern seen in real warehouses.
- "Eaches" = the quantity of individual items stored for each SKU.
  Small parts (o-rings, fuses) have high counts; large parts (motors) have few.
"""

import csv
import random

# Seed for reproducibility — anyone running this gets the same 500 SKUs.
random.seed(42)

# --------------------------------------------------------------------------
# PART CATEGORIES
# --------------------------------------------------------------------------
# Each category defines realistic size, weight, and eaches ranges.
# "eaches" = how many individual units of this SKU are stored in the VLM.
#
# WHY EACHES VARIES BY CATEGORY:
#   Small parts are cheap and consumed frequently → keep many on hand.
#   Large parts are expensive and rarely fail → keep just a few spares.
# --------------------------------------------------------------------------
CATEGORIES = [
    # SMALL parts — bearings, seals, o-rings, small fasteners
    {
        "descriptions": [
            "Ball Bearing", "Sealed Bearing", "Thrust Bearing",
            "O-Ring Kit", "Shaft Seal", "Lip Seal",
            "Hex Bolt Pack", "Cap Screw Set", "Lock Nut Pack",
            "Dowel Pin Set", "Cotter Pin Kit", "Retaining Ring Kit",
            "Fuse 10A", "Fuse 15A", "Fuse 30A",
        ],
        "length": (0.5, 3.0),
        "width": (0.5, 3.0),
        "height": (0.5, 2.0),
        "weight": (0.05, 1.5),
        "eaches": (20, 200),   # keep lots of small consumables
        "count": 150,
    },
    # SMALL-MEDIUM — sensors, switches, relays, small electronics
    {
        "descriptions": [
            "Proximity Sensor", "Temp Sensor", "Pressure Transducer",
            "Limit Switch", "Toggle Switch", "Rocker Switch",
            "Relay 24V", "Relay 120V", "Contactor Coil",
            "Terminal Block", "Wire Connector Kit", "DIN Rail Mount",
            "LED Indicator", "Push Button Red", "Push Button Green",
        ],
        "length": (1.5, 5.0),
        "width": (1.0, 3.5),
        "height": (1.0, 3.0),
        "weight": (0.1, 2.5),
        "eaches": (5, 50),
        "count": 100,
    },
    # MEDIUM — filters, gaskets, small valves, fittings
    {
        "descriptions": [
            "Hydraulic Filter", "Oil Filter Element", "Air Filter Cartridge",
            "Gasket Set", "Flange Gasket", "Head Gasket",
            "Ball Valve 1in", "Gate Valve 1in", "Check Valve 3/4in",
            "Pipe Fitting Kit", "Elbow Fitting 1in", "Tee Fitting 3/4in",
            "Solenoid Valve 24V", "Pressure Regulator", "Flow Control Valve",
        ],
        "length": (3.0, 8.0),
        "width": (3.0, 6.0),
        "height": (2.0, 5.0),
        "weight": (0.5, 8.0),
        "eaches": (3, 25),
        "count": 100,
    },
    # MEDIUM-LARGE — circuit boards, PLCs, drives, instruments
    {
        "descriptions": [
            "PLC Module", "I/O Card", "HMI Panel 4in",
            "VFD 1HP", "VFD 2HP", "Servo Drive",
            "Power Supply 24V", "Power Supply 48V", "UPS Module",
            "Circuit Board Assy", "Control Board", "Display Module",
            "Encoder", "Resolver", "Signal Conditioner",
        ],
        "length": (4.0, 12.0),
        "width": (3.0, 8.0),
        "height": (2.0, 6.0),
        "weight": (1.0, 15.0),
        "eaches": (1, 10),
        "count": 80,
    },
    # LARGE — motors, pumps, gearboxes, heavy assemblies
    {
        "descriptions": [
            "AC Motor 1HP", "AC Motor 2HP", "DC Motor 1/2HP",
            "Gear Pump", "Centrifugal Pump", "Diaphragm Pump",
            "Gearbox 10:1", "Gearbox 20:1", "Speed Reducer",
            "Cylinder 2in Bore", "Cylinder 3in Bore", "Cylinder 4in Bore",
            "Heat Exchanger", "Manifold Block", "Accumulator",
        ],
        "length": (6.0, 18.0),
        "width": (4.0, 12.0),
        "height": (4.0, 10.0),
        "weight": (5.0, 65.0),
        "eaches": (1, 5),       # expensive — just a few spares
        "count": 70,
    },
]


def generate_weekly_picks() -> int:
    """
    Generate a weekly pick count with a right-skewed distribution.

    WHY: In most warehouses, ~80% of picks come from ~20% of SKUs (Pareto).
    So we want MOST items to have low pick counts (0-3), with a long tail.
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
    """Build the list of 500 SKU dictionaries."""
    skus = []
    sku_num = 1

    for cat in CATEGORIES:
        for _ in range(cat["count"]):
            desc = random.choice(cat["descriptions"])

            length = round(random.uniform(*cat["length"]), 1)
            width = round(random.uniform(*cat["width"]), 1)
            height = round(random.uniform(*cat["height"]), 1)
            weight = round(random.uniform(*cat["weight"]), 2)
            eaches = random.randint(*cat["eaches"])

            skus.append({
                "SKU": f"SKU-{sku_num:04d}",
                "Description": desc,
                "Length_in": length,
                "Width_in": width,
                "Height_in": height,
                "Weight_lbs": weight,
                "Eaches": eaches,
                "Weekly_Picks": generate_weekly_picks(),
            })
            sku_num += 1

    # Shuffle so the CSV isn't grouped by category — more realistic
    random.shuffle(skus)
    return skus


def main():
    skus = generate_skus()

    output_file = "sample_skus.csv"
    fieldnames = [
        "SKU", "Description", "Length_in", "Width_in",
        "Height_in", "Weight_lbs", "Eaches", "Weekly_Picks",
    ]

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(skus)

    # Print a quick summary
    print(f"Generated {len(skus)} SKUs -> {output_file}\n")

    # Pick frequency distribution
    pick_counts = [s["Weekly_Picks"] for s in skus]
    print("Weekly Picks distribution:")
    for picks in range(11):
        count = pick_counts.count(picks)
        bar = "#" * count
        print(f"  {picks:2d} picks: {count:3d} SKUs  {bar}")

    # Eaches distribution
    eaches = [s["Eaches"] for s in skus]
    print(f"\nEaches range: {min(eaches)} - {max(eaches)}")
    print(f"Avg eaches:   {sum(eaches)/len(eaches):.1f}")

    # Weight distribution (per each)
    weights = [s["Weight_lbs"] for s in skus]
    print(f"\nWeight/each range: {min(weights):.2f} - {max(weights):.2f} lbs")

    # Cell weight = weight * eaches (what the tray actually carries)
    cell_weights = [s["Weight_lbs"] * s["Eaches"] for s in skus]
    print(f"Cell weight range:  {min(cell_weights):.1f} - {max(cell_weights):.1f} lbs")
    print(f"Avg cell weight:    {sum(cell_weights)/len(cell_weights):.1f} lbs")

    # Size distribution
    widths = [s["Width_in"] for s in skus]
    print(f"\nItem width range: {min(widths):.1f} - {max(widths):.1f} in")
    print(f"  (determines which tray config an item fits in)")


if __name__ == "__main__":
    main()
