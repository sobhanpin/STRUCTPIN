# DEVELOPMENT_STATUS

Last updated: 2026-11-14

## Current milestone
M1 Foundation (in progress)

## Completed in code (delivered, not yet run by owner)
- Shared structural data model with validation (`src/structpin/model/structural_model.py`).
- Dense linear solver with singularity detection (`src/structpin/fem/linalg.py`).
- 2D frame element stiffness, transformation, consistent UDL loads, assembly, reactions, end actions (`src/structpin/fem/frame2d.py`).
- Benchmark tests (`tests/test_frame2d_benchmarks.py`).

## Tested
- NOT YET EXECUTED. Owner must run the tests (see steps in the session reply) and record the output here.

## Not started
- Desktop shell, localization, logging, project file save/load, 3D viewport, UI, persistence, documents listed in the master prompt except this file and README.

## Known limitations
- 2D only (x, y, rz). No 3D frames yet.
- Dense solver: fine for small models, not for large ones.
- No matrix scaling: ill-conditioning possible in extreme stiffness ratios.
- No member loads other than uniform transverse loads.
- No support settlement, releases, or second-order effects.

## Next action
Owner runs the tests on Windows 10 and pastes the full output into the chat. Then start the desktop shell and project file persistence.
