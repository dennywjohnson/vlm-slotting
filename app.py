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
# WHY A LIST OF DICTS?
#   Rather than hardcoding form parsing logic for each field, we
#   describe the fields declaratively. This makes it easy to add new
#   config options later — just add one entry here and it appears in
#   the form automatically.
CONFIG_FIELDS = [
    {"key": "num_towers",        "label": "Number of Towers",           "type": "int",   "group": "Machine Layout"},
    {"key": "trays_per_tower",   "label": "Trays per Tower",            "type": "int",   "group": "Machine Layout"},
    {"key": "tray_width",        "label": "Tray Width (in)",            "type": "float", "group": "Tray Dimensions"},
    {"key": "tray_depth",        "label": "Tray Depth (in)",            "type": "float", "group": "Tray Dimensions"},
    {"key": "tray_max_weight",   "label": "Max Weight per Tray (lbs)",  "type": "float", "group": "Tray Dimensions"},
    {"key": "golden_zone_start", "label": "Golden Zone Start (tray #)", "type": "int",   "group": "Golden Zone"},
    {"key": "golden_zone_end",   "label": "Golden Zone End (tray #)",   "type": "int",   "group": "Golden Zone"},
    {"key": "tray_config_1",     "label": "Config 1 (cells per tray)",  "type": "int",   "group": "Tray Configurations"},
    {"key": "tray_config_2",     "label": "Config 2 (cells per tray)",  "type": "int",   "group": "Tray Configurations"},
    {"key": "tray_config_3",     "label": "Config 3 (cells per tray)",  "type": "int",   "group": "Tray Configurations"},
    {"key": "tray_config_4",     "label": "Config 4 (cells per tray)",  "type": "int",   "group": "Tray Configurations"},
    {"key": "divider_width",     "label": "Divider Width (in)",         "type": "float", "group": "Spacing"},
    {"key": "item_clearance",    "label": "Item Clearance (in)",        "type": "float", "group": "Spacing"},
    {"key": "high_pick_threshold","label": "High Pick Threshold (picks/week)", "type": "int", "group": "Algorithm"},
]


def parse_config_from_form(form) -> dict:
    """
    Read VLM config values from the submitted form data.

    WHY NOT JUST USE request.form.get() DIRECTLY?
      By looping over CONFIG_FIELDS, we get automatic type conversion
      (int/float) and fallback to the current config if a field is
      missing. This prevents crashes from bad input.
    """
    cfg = latest_results["config"].copy()

    for field in CONFIG_FIELDS:
        raw = form.get(field["key"])
        if raw is not None and raw.strip() != "":
            try:
                if field["type"] == "int":
                    cfg[field["key"]] = int(raw)
                else:
                    cfg[field["key"]] = float(raw)
            except ValueError:
                pass  # keep the previous value if input is invalid

    return cfg


# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------

@app.route("/")
def index():
    """
    Main page. Shows the upload form, config panel, and (if available)
    the latest slotting results with summary stats.
    """
    return render_template(
        "index.html",
        rows=latest_results["rows"],
        summary=latest_results["summary"],
        input_filename=latest_results["input_filename"],
        config=latest_results["config"],
        config_fields=CONFIG_FIELDS,
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
    if cfg["golden_zone_start"] > cfg["golden_zone_end"]:
        flash("Golden Zone Start must be <= Golden Zone End.", "error")
        return redirect(url_for("index"))
    if cfg["golden_zone_end"] > cfg["trays_per_tower"]:
        flash("Golden Zone End can't exceed Trays per Tower.", "error")
        return redirect(url_for("index"))

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

        flash(
            f"Slotting complete! {summary['total_placed']} SKUs placed"
            f" across {summary['trays_used']} trays.",
            "success",
        )
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
