"""
VLM Slotting Web App
====================
A simple local web interface for uploading SKU data, running the
slotting algorithm, and viewing/downloading results.

HOW THIS WORKS:
  Flask is a lightweight Python web framework. It turns Python functions
  into web pages. When you visit http://localhost:5000 in your browser,
  Flask calls the index() function and returns HTML.

  The app has three routes (URLs):
    /           → Main page (upload form + results + config)
    /run        → Handles the CSV upload and runs slotting
    /download   → Downloads the slotting map CSV

  Uploaded files are saved to the "uploads" folder, and output goes to
  the project root as "slotting_map.csv".
"""

import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from slotting import run_slotting, default_config

# --------------------------------------------------------------------------
# APP SETUP
# --------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "vlm-slotting-dev-key"

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "slotting_map.csv")

# Store the latest results and config in memory.
# This resets when the server restarts.
latest_results = {
    "rows": None,
    "summary": None,
    "input_filename": None,
    "config": default_config(),  # current config (persists across runs)
}


# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------

# CONFIG_FIELDS defines how each config key maps to the HTML form.
# This is the single source of truth — used by both the /run route
# (to parse form values) and the template (to render form fields).
#
# Tray configurations are handled separately (dynamic add/remove),
# so they are NOT in these lists.  Only the "base" VLM settings live here,
# split into PRE (before tray configs) and POST (after).

CONFIG_FIELDS_PRE = [
    {"key": "zone",              "label": "Zone Label (1 char)",        "type": "str",   "group": "Machine Layout"},
    {"key": "num_towers",        "label": "Number of Towers",           "type": "int",   "group": "Machine Layout"},
    {"key": "trays_per_tower",   "label": "Trays per Tower (total)",    "type": "readonly", "group": "Machine Layout"},
    {"key": "slots_per_tower",   "label": "Slots per Tower (total)",    "type": "readonly", "group": "Machine Layout"},
    {"key": "slot_spacing",      "label": "Slot Spacing (in)",          "type": "float", "group": "Machine Layout"},
    {"key": "reserved_slots",    "label": "Reserved Slots",             "type": "int",   "group": "Machine Layout"},
    {"key": "tower_height_display", "label": "Total Tower Height",    "type": "readonly", "group": "Machine Layout"},
    {"key": "trays_2in",         "label": "2\" Trays per Tower",        "type": "int",   "group": "Tray Inventory"},
    {"key": "slots_per_2in_tray","label": "Slots per 2\" Tray",        "type": "int",   "group": "Tray Inventory"},
    {"key": "trays_4in",         "label": "4\" Trays per Tower",        "type": "int",   "group": "Tray Inventory"},
    {"key": "slots_per_4in_tray","label": "Slots per 4\" Tray",        "type": "int",   "group": "Tray Inventory"},
    {"key": "trays_6in",         "label": "6\" Trays per Tower",        "type": "int",   "group": "Tray Inventory"},
    {"key": "slots_per_6in_tray","label": "Slots per 6\" Tray",        "type": "int",   "group": "Tray Inventory"},
    {"key": "trays_8in",         "label": "8\" Trays per Tower",        "type": "int",   "group": "Tray Inventory"},
    {"key": "slots_per_8in_tray","label": "Slots per 8\" Tray",        "type": "int",   "group": "Tray Inventory"},
    {"key": "tray_width",        "label": "Tray Width (in)",            "type": "float", "group": "Tray Dimensions"},
    {"key": "tray_depth",        "label": "Tray Depth (in)",            "type": "float", "group": "Tray Dimensions"},
    {"key": "tray_max_weight",   "label": "Max Weight per Tray (lbs)",  "type": "float", "group": "Tray Dimensions"},
    {"key": "golden_zone_pct",   "label": "Golden Zone (% of total picks)", "type": "int", "group": "Zone Thresholds"},
    {"key": "silver_zone_pct",   "label": "Silver Zone (% of total picks)", "type": "int", "group": "Zone Thresholds"},
    {"key": "bronze_zone_pct",   "label": "Bronze Zone (% of total picks)", "type": "int", "group": "Zone Thresholds"},
]

CONFIG_FIELDS_POST = [
    {"key": "divider_width",     "label": "Divider Width (in)",         "type": "float", "group": "Spacing"},
    {"key": "item_clearance",    "label": "Item Clearance (in)",        "type": "float", "group": "Spacing"},
    {"key": "high_pick_threshold","label": "High Pick Threshold (picks/week)", "type": "int", "group": "Algorithm"},
]

# Per-config fields — each tray config has these four editable values
# plus two calculated display-only values (cell_vol, eff_vol).
TRAY_CONFIG_SUFFIXES = [
    {"suffix": "cells",      "label": "Cells per Tray",       "type": "int",   "default": 6},
    {"suffix": "height",     "label": "Tray Height (in)",     "type": "float", "default": 4.0},
    {"suffix": "height_tol", "label": "Height Tolerance (%)", "type": "int",   "default": 10},
    {"suffix": "fill_pct",   "label": "Fill Capacity (%)",    "type": "int",   "default": 85},
]


def _parse_field(cfg, key, field_type, raw):
    """Parse a single form value into the config dict."""
    if raw is None or raw.strip() == "":
        return
    try:
        if field_type == "str":
            cfg[key] = raw.strip()[:1].upper()
        elif field_type == "int":
            cfg[key] = int(raw)
        else:
            cfg[key] = float(raw)
    except ValueError:
        pass  # keep the previous value if input is invalid


def parse_config_from_form(form) -> dict:
    """
    Read VLM config values from the submitted form data.

    Base fields come from CONFIG_FIELDS_PRE and CONFIG_FIELDS_POST.
    Tray config fields are parsed dynamically based on num_tray_configs.
    """
    cfg = latest_results["config"].copy()

    # Parse base fields (skip readonly computed fields)
    for field in CONFIG_FIELDS_PRE + CONFIG_FIELDS_POST:
        if field["type"] == "readonly":
            continue
        _parse_field(cfg, field["key"], field["type"], form.get(field["key"]))

    # Parse dynamic tray configs
    raw_count = form.get("num_tray_configs")
    num_configs = int(raw_count) if raw_count and raw_count.strip().isdigit() else cfg.get("num_tray_configs", 4)
    num_configs = max(1, min(num_configs, 26))  # clamp 1-26
    cfg["num_tray_configs"] = num_configs

    # Remove old tray config keys that exceed the new count
    old_count = latest_results["config"].get("num_tray_configs", 4)
    for i in range(num_configs + 1, old_count + 1):
        for sf in TRAY_CONFIG_SUFFIXES:
            cfg.pop(f"tray_config_{i}_{sf['suffix']}", None)

    # Parse each tray config's fields (add defaults for new ones)
    for i in range(1, num_configs + 1):
        for sf in TRAY_CONFIG_SUFFIXES:
            key = f"tray_config_{i}_{sf['suffix']}"
            raw = form.get(key)
            if raw is not None and raw.strip() != "":
                _parse_field(cfg, key, sf["type"], raw)
            elif key not in cfg:
                cfg[key] = sf["default"]  # new config gets defaults

    return cfg


# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------

def _compute_derived_config(cfg):
    """Compute all derived config values from tray inventory."""
    # Total trays per tower
    cfg["trays_per_tower"] = (
        cfg.get("trays_2in", 0) + cfg.get("trays_4in", 0) +
        cfg.get("trays_6in", 0) + cfg.get("trays_8in", 0)
    )
    # Total slots per tower (tray count × slots per tray for each height)
    cfg["slots_per_tower"] = (
        cfg.get("trays_2in", 0) * cfg.get("slots_per_2in_tray", 9) +
        cfg.get("trays_4in", 0) * cfg.get("slots_per_4in_tray", 17) +
        cfg.get("trays_6in", 0) * cfg.get("slots_per_6in_tray", 49) +
        cfg.get("trays_8in", 0) * cfg.get("slots_per_8in_tray", 65)
    )
    # Tower height from slots × spacing
    total_inches = cfg["slots_per_tower"] * cfg["slot_spacing"]
    feet = int(total_inches // 12)
    inches = round(total_inches % 12, 1)
    if inches == 0:
        cfg["tower_height_display"] = f"{feet}' 0\""
    else:
        cfg["tower_height_display"] = f"{feet}' {inches}\""


@app.route("/")
def index():
    """
    Main page. Shows the upload form, config panel, and (if available)
    the latest slotting results with summary stats.
    """
    cfg = latest_results["config"]
    _compute_derived_config(cfg)
    return render_template(
        "index.html",
        rows=latest_results["rows"],
        summary=latest_results["summary"],
        input_filename=latest_results["input_filename"],
        config=cfg,
        config_fields_pre=CONFIG_FIELDS_PRE,
        config_fields_post=CONFIG_FIELDS_POST,
        num_tray_configs=cfg.get("num_tray_configs", 4),
    )


@app.route("/run", methods=["POST"])
def run():
    """Handle CSV upload, read config from form, and run slotting."""
    if "file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("index"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("index"))

    if not file.filename.lower().endswith(".csv"):
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("index"))

    # Parse config from the form (user may have changed values)
    cfg = parse_config_from_form(request.form)

    # Basic validation
    if not (1 <= cfg["golden_zone_pct"] <= 100):
        flash("Golden Zone % must be between 1 and 100.", "error")
        return redirect(url_for("index"))
    if not (1 <= cfg["silver_zone_pct"] <= 100):
        flash("Silver Zone % must be between 1 and 100.", "error")
        return redirect(url_for("index"))
    if not (1 <= cfg["bronze_zone_pct"] <= 100):
        flash("Bronze Zone % must be between 1 and 100.", "error")
        return redirect(url_for("index"))
    if cfg["silver_zone_pct"] <= cfg["golden_zone_pct"]:
        flash("Silver Zone % must be greater than Golden Zone %.", "error")
        return redirect(url_for("index"))
    if cfg["bronze_zone_pct"] <= cfg["silver_zone_pct"]:
        flash("Bronze Zone % must be greater than Silver Zone %.", "error")
        return redirect(url_for("index"))

    # Compute derived config values (trays_per_tower, slots_per_tower, tower height)
    _compute_derived_config(cfg)

    # Save config for next page load (so the form remembers your values)
    latest_results["config"] = cfg

    # Save uploaded file and run
    input_path = os.path.join(UPLOAD_FOLDER, "input.csv")
    file.save(input_path)

    try:
        rows, summary = run_slotting(input_path, OUTPUT_CSV, cfg)

        latest_results["rows"] = rows
        latest_results["summary"] = summary
        latest_results["input_filename"] = file.filename

        msg = (f"Slotting complete! {summary['total_placed']} SKUs placed"
               f" across {summary['trays_used']} trays.")
        if summary.get("validation_errors"):
            msg += (f" ({len(summary['validation_errors'])} validation"
                    f" error{'s' if len(summary['validation_errors']) != 1 else ''})")
        if summary.get("warnings"):
            msg += (f" ({len(summary['warnings'])}"
                    f" warning{'s' if len(summary['warnings']) != 1 else ''})")
        flash(msg, "success")
    except Exception as e:
        flash(f"Error running slotting: {e}", "error")

    return redirect(url_for("index"))


@app.route("/download")
def download():
    """Send the slotting_map.csv file as a download."""
    if not os.path.exists(OUTPUT_CSV):
        flash("No slotting map available. Upload and run first.", "error")
        return redirect(url_for("index"))

    return send_file(
        OUTPUT_CSV,
        as_attachment=True,
        download_name="slotting_map.csv",
    )


# --------------------------------------------------------------------------
# START THE SERVER
# --------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  VLM Slotting Tool")
    print("  Open http://localhost:5000 in your browser\n")
    app.run(debug=True, port=5000)
