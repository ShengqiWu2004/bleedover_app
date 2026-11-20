# Bleedover Corrector (desktop app)

A local app around this repo's bleedover correction. Choose an experiment
folder, optionally calibrate a model on it, run the correction with a live
progress bar and ETA, then read the report and look at corrected images.

The app is a thin layer. It imports `utils/`, `simulator/` and `correction/`
unchanged, and it writes the same run folders as `scripts/correct_experiment.py`.
Its outputs work with the notebooks as they are, and the notebooks' runs
show up in the app.

## Install (no Python needed)

Step-by-step guide for the people you share it with: [INSTALL.md](INSTALL.md).
The `.dmg` contains the same guide as *Read me first (install).md*.

Share `packaging/dist/BleedoverCorrector-arm64.dmg` (~105 MB). The person
receiving it:

1. Opens the `.dmg` and drags **Bleedover Corrector** to Applications.
2. Allows it once. The app isn't signed with an Apple developer ID, so macOS
   blocks the first launch. Go to *System Settings → Privacy & Security* and
   click *Open Anyway*. On macOS 14 and older, *right-click → Open* also
   works.
3. Waits up to a minute on that first launch while macOS checks the app. Later
   launches take about 2 s.

The window opens in Chrome or Edge app mode, or in the default browser. The
app has no Dock icon: quit it from **⚙ System → Quit**, or let it quit by
itself 10 minutes after its last window closes (never during a run). Runs go to
`~/Documents/Bleedover Corrector/runs/`. Saved calibrations and preferences go
to `~/Library/Application Support/BleedoverCorrector/`.

The `.dmg` runs on Apple silicon Macs (arm64). For an Intel Mac, build it on an
Intel Mac with the same steps.

### Build the app

```bash
# once: a clean environment with the same package versions as mapa
conda create -n bleedover-build -c conda-forge python=3.12.14
conda activate bleedover-build
pip install numpy==2.3.0 pandas==2.2.3 scipy==1.15.3 pyarrow==20.0.0 matplotlib==3.10.3 \
    pillow==11.2.1 scikit-image==0.25.2 psutil==7.2.2 pyinstaller

# each release (about 1 minute): the .dmg to share, and --install to update your own copy
bash bleedover_app/packaging/build_standalone_macos.sh --install
```

**Publish it.** The download link in the repo's top-level README always fetches
the `.dmg` attached to the newest GitHub Release. On GitHub, go to *Releases →
Draft a new release*. Make a tag (e.g. `app-v1.1`), drag in
`packaging/dist/BleedoverCorrector-arm64.dmg` and publish. Keep the file name
unchanged, or the link breaks. The `.dmg` can't be committed: it's over
GitHub's 100 MB file limit.

The app is built in `packaging/build.noindex/`, a folder Spotlight and Launchpad
skip, so only the copy in `~/Applications` shows up as an app. `packaging/dist/`
holds the `.dmg` to share.

This uses `packaging/bleedover.spec` and `packaging/app_entry.py`. The build
bundles Python, the packages, this repo's `utils/`, `simulator/` and
`correction/`, the two built-in models and the device file. Rebuild after
changing any of them.

## Run from the repo (for development)

```bash
conda activate mapa
cd imager_bleedover
python -m bleedover_app            # opens its own window (Chrome/Edge app mode, else the default browser)
```

No packages beyond `mapa`'s are needed. The server uses the Python standard library, and `psutil` reads the
Mac's memory.

- `bash bleedover_app/packaging/build_macos_app.sh` makes a light `.app` that
  runs this repo's code with `mapa`'s Python (no bundling).
- Options: `--port 8765` (the default), `--no-window`, and `--idle-exit MINUTES`.

## What it does

1. **Experiment.** Browse to a folder holding `ptirf/` and, usually,
   `_metadata.csv` and `exp_details.txt`. The app checks MAPA's outputs
   (alignment transforms per cycle and tile, and `img_results/results.feather`
   with `x, y`). It also reads the flowcell ID (`Flowcell ID: …` in
   `exp_details.txt`) and lists the samples on the flowcell, with which ones
   should glow according to `alignment_matrix.json`.

   **Missing files.** `_metadata.csv` and `exp_details.txt` are optional (amber
   badge, not red). Without `exp_details.txt` you type the flowcell ID.
   Without `_metadata.csv` the cycles are read from the Feather columns
   (`img_0_GG` … `img_17_GG`) and matched, by number, to the `ptirf/Cycle_*`
   folders sorted by name. The app names the first pair, so you can check it.
   This works whenever every cycle has the same type (`img_N`). It doesn't
   work when an experiment mixes several cycle types (`qc1_100_qc2_066_0`, …):
   only `_metadata.csv` records their imaging order, so the app asks for the
   file instead of guessing. See `layout.py`.
2. **FASTQ.** By default the app uses `<experiment>/fastq`. Switch to *FASTQ
   library* to pick a shared library folder; it's remembered between
   launches. The app then looks for the folder named after the flowcell ID,
   ignoring case, up to two levels deep; the ID must stand alone in the name
   (`251009_MHFVK` matches, `XMHFVKY` doesn't). If `exp_details.txt` has no ID,
   or nothing matches, type the ID and press *Match*. The FASTQ folder is shown
   and recorded in the run's `config.json`, and its sample files are
   cross-checked against the samples in the Feather table. The correction
   itself reads the Feather table, not the FASTQ files.
3. **Model.** There are two built-in models, picked by held-out tests on isolated
   dots from five experiments (see `model_catalog.py`):
   - **Standard** (pooled Gaussian PSF) was best or tied on every experiment.
   - **Cross-check** (QC-only Gaussian PSF) tests whether a result depends on
     the learned PSF.

   If the model has no calibration for the experiment, tick *Calibrate first*.
   The app fits `counts = gain × RFU + offset` from isolated, lit dots, using
   the sparsest cycles by default (recipe of
   `notebooks/261117_accperct_calibration.ipynb`). Calibration uses the PSF
   only; the image model (Voronoi or additive) doesn't enter, because an
   isolated dot has no neighbours. The line is saved in the app's data folder
   as soon as it's fitted, so later runs reuse it even if a correction fails.
   The ⚙ *System* button lists the saved calibrations and lets you delete
   them; the built-in models and their calibrations can't be deleted.
4. **Correction.** Choose the image model (Voronoi or additive), the number of
   workers (each newly opened experiment starts at the suggested number for
   this computer and that experiment's density), and optionally cycles, tiles, prior, softness and steps. Only
   aligned tiles are run. The estimate comes from your earlier runs
   (`results/*/summary.csv`) and is scaled by cluster density. Memory per worker
   is shown, and you're warned when the workers won't fit.
5. **Progress bar** (bottom): the stage, images done, the last image's R², the
   time left (from observed speed once every worker has finished an image),
   *Cancel*, and the full log.
6. **Results.** Only runs of the experiment chosen at the top are listed. That
   includes script runs, so different versions (model, image model, settings)
   can be compared. A stats line comes first, then one row of tabs:
   - **Library**: the library analysis (see below), or how to set it up.
   - **Image fit**: image R² before and after correction.
   - **Cluster change**: Feather vs corrected RFU per cluster.
   - **Crowding**: RFU change by distance to the nearest lit neighbour.
   - **Samples**: median RFU per sequencing sample, lit vs dark.
   - **Calibration**: shown if one ran.
   - **Per cycle**: a table by cycle.
   - **Not corrected**: shown only if some images failed.

   Each figure says how to read it and what it means biologically. *Build
   report* makes a report for runs that have none.

   **Resume.** A stopped run keeps every image it finished. Starting the same
   method again offers to resume it, and only the remaining images are run.

   **Clean up (🧹).** Lists this experiment's runs: finished in green,
   incomplete in red. You can delete the incomplete ones, or chosen others.
7. **Image viewer.** Click anywhere on a tile to see six panels for a
   64/128/256 px window:
   - the real image;
   - the image simulated from Feather RFU;
   - the image simulated after correction;
   - each cluster's change;
   - both residuals.

   It shows the run chosen in Results, including a run that's still going: every
   image finished so far is listed.
   The crop is re-rendered from the saved tables, so nothing extra is stored.
   It matches `correction.reconstruct_image` to within float32 rounding.

## Library analysis (optional)

For flowcells that carry a designed library, card 3 groups the replicate
clusters of each library member and compares them before and after correction.

**Setting it up.** Turn the card on, pick the sequencing sample that holds the
library, and type its structure from the start of the read: `A/C/G/T` are
fixed and each `N` is a variable base. For example, the three-way junction is
`GGAGGCTCTCGGGACGAC NN GGATTTTCC NNNN ACGAAGT NN GTCGTCCCGATGCTGCAAGTAG`.
The rules are the same as in `sequence_replicates_across_flowcells.ipynb`.
*Check* tries the structure on 200,000 reads of that sample. The settings are
saved per experiment.

**When it runs.** After every correction of that experiment, or on demand from
Results for any finished run.

**What it reports.** Values are compared as light above zero (`RFU − zero
point`), and spread is the normalized SD of each member's replicates (SD ÷
mean). Only trusted clusters count, and only members with at least *Min
replicates* of them.

The figures are shown for the brightest cycle, as sub-tabs under Results → Library:
- **Normalized SD**: its distribution over sequences, before vs after.
- **Each sequence**: every sequence's normalized SD after vs before, and the
  share that got tighter.
- **Within sequences**: each cluster ÷ its sequence's mean, pooled.
- **Base heatmap**: signal by base and position. Shown when all members have
  the same length.
- **Sequences**: a searchable, sortable table.
- **SD by cycle**: median normalized SD per cycle.
- **Member signal**: each member's median signal before vs after, with rank
  agreement.
- **Replicates**: clusters per member.

`app_report/library/by_member.feather` holds every member × cycle, with
replicates, mean, median and normalized SD for both versions.

## Where things go

| What | Where |
| --- | --- |
| Run folder (same layout as the script) | `results/<YYMMDD_HHMMSS>_correct_<experiment>_app_<renderer>/` from the repo; `~/Documents/Bleedover Corrector/runs/` in the installed app |
| Corrected Feather-shaped table | `<run>/<experiment>/corrected_results.feather` |
| Report (figures, `report.json`, calibration) | `<run>/app_report/` |
| The job as run | `<run>/app_job.json`, `<run>/config.json` |
| The model a run used (shape + calibration) | `<run>/model.json` |
| Your saved calibrations | `~/Library/Application Support/BleedoverCorrector/calibrations.json` |
| Library set up per experiment | `~/Library/Application Support/BleedoverCorrector/libraries.json` |
| Library analysis of a run | `<run>/app_report/library/` |
| Preferences (FASTQ library, last folder, image model, extra run folders) | `~/Library/Application Support/BleedoverCorrector/preferences.json` |

## Code layout

| Module | Responsibility |
| --- | --- |
| `__main__.py` | Launcher: starts the server and opens a window. |
| `server.py` | HTTP plumbing (localhost only, Host/Origin checks, CSP), static files, server-sent progress events. |
| `api.py` | What each button does: JSON in, JSON out. |
| `experiment_info.py` | Reads a folder (`_metadata.csv`, `exp_details.txt`, transforms, Feather metadata, samples). |
| `layout.py` | Cycle → image folder map for folders without `_metadata.csv` (installed into the repo's `load_experiment`). |
| `roles.py` | Sample → role (FM / QC1 / QC2 / library / undetermined); normalises `alignment_matrix.json`. |
| `fastq.py` | FASTQ folder: inside the experiment, or matched by flowcell ID in a library. |
| `model_catalog.py` | The two built-in models (`default_models/`), why they were chosen, and which calibration applies. |
| `calibrations.py` | The user's saved calibrations (add, replace, delete). |
| `library.py` | Library structure (N template) → library member per read; per-experiment library settings. |
| `run_index.py` | An experiment's runs, their method, and which can be resumed. |
| `timing.py` | ETA from past runs, memory per worker, live stage clock. |
| `jobs.py` | One subprocess job at a time; parses its events into the live state. |
| `pipeline/` | Runs in the subprocess: `calibrate.py`, `correct.py`, `report.py`, `plots.py`, `events.py`, and the library analysis (`library_report.py`, `library_stats.py`, `library_plots.py`). |
| `viewer.py` | Re-renders crops of corrected images. |
| `dialogs.py` | Native folder picker (AppleScript on macOS, tkinter elsewhere). |
| `static/` | The page: `index.html`, `app.css`, `js/*.js` (ES modules), manifest, service worker, icons. |
| `packaging/` | Standalone app (`bleedover.spec`, `app_entry.py`, `build_standalone_macos.sh`), the light repo `.app`, icon generator. |
| `tests/` | `python -m pytest bleedover_app/tests` (real-data tests skip without the T7 drive). |

**Web practice followed** (web.dev guidance):

- semantic landmarks and native controls (`<progress>`, `<dialog>`, fieldsets);
- the ARIA tabs pattern with keyboard support;
- visible focus, `aria-live` status, and no colour-only meaning (icons + text);
- light/dark themes from the system, and `prefers-reduced-motion` / forced-colours support;
- image sizes reserved (no layout shift), each figure loaded only when its tab is opened, and no framework or CDN;
- a strict Content-Security-Policy;
- installable as a PWA (manifest + service worker).

The page is laid out for desktop screens (≥ 1024 px).
