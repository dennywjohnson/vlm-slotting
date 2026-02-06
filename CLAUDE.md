# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Python 3.12 is installed but **not on PATH** in bash. Use the full path:
```
C:/Users/denny/AppData/Local/Programs/Python/Python312/python.exe
```

## Commands

```bash
# Run the web app (serves on http://localhost:5000)
C:/Users/denny/AppData/Local/Programs/Python/Python312/python.exe app.py

# Run slotting algorithm directly (CLI)
C:/Users/denny/AppData/Local/Programs/Python/Python312/python.exe slotting.py [input.csv] [output.csv]

# Regenerate sample data (500 SKUs, seeded for reproducibility)
C:/Users/denny/AppData/Local/Programs/Python/Python312/python.exe generate_sample_data.py
```

No test framework, linter, or build system is configured.

## Architecture

This is a VLM (Vertical Lift Module) slotting optimizer — it assigns SKUs to physical cell locations across a multi-tower vertical lift module.

### Data Flow

1. **Input**: CSV with columns `SKU, Description, Length_in, Width_in, Height_in, Weight_lbs, Eaches, Weekly_Picks, Tray_Config, Pick_Priority`
2. **`slotting.py:run_slotting()`** orchestrates: load CSV → validate SKUs → slot into cells → write output CSV → build summary
3. **Output**: `slotting_map.csv` with bin labels, physical locations, and validation results

### Core Algorithm (`slotting.py`)

The slotting model uses **direct mapping**: `Pick_Priority` (from input data) IS the cell number within a tray configuration.

**Cell Number → Physical Location mapping** interleaves across towers for even distribution:
- Cell 1 → Tower 1, Cell 2 → Tower 2, Cell 3 → Tower 3, Cell 4 → Tower 1, ...
- From a cell number: `tower = ((cell-1) % num_towers) + 1`, then derive config_tray and cell_index

**Physical tray assignment** (`assign_physical_trays`): configs with highest total weekly picks get golden zone tray positions (center-out spiral).

**Validation** (`validate_skus`): checks dimensional fit (with rotation), height tolerance, volume capacity, and duplicate pick priorities — all run before slotting but don't block placement.

### Tray Configurations

Each config defines a cell layout (how many cells divide a tray). Default: 4 configs with 6, 8, 16, 30 cells. Configs are numbered 1-4 and stored as flat keys in the config dict: `tray_config_{N}_{cells|height|height_tol|fill_pct}`.

**BIN Label format**: `Zone(1) + Tower(1) + Tray(3) + ConfigLetter(1) + Cell(2)` — e.g., `V1002B01`

### Web App (`app.py` + `templates/index.html`)

Flask app with three routes: `/` (main page), `/run` (POST with CSV + config form), `/download` (CSV download). Single-page UI with collapsible config panel, summary dashboard, and sortable/filterable results table. Config state persists in memory across runs (resets on server restart).

Config form fields are defined in `CONFIG_FIELDS_PRE`, `CONFIG_FIELDS_POST`, and `TRAY_CONFIG_SUFFIXES` — these are the single source of truth for both form parsing and rendering. Tray configs support dynamic add/remove in the UI.

### Key Gotchas

- `get_tray_configs()` returns configs keyed by number (1-based), not by cell count
- Cell weight = `Weight_lbs * Eaches` (total weight in the cell, not per-item)
- `app.secret_key` is hardcoded for dev use only
