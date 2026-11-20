# Installing Bleedover Corrector

**Quick answer:** you don't need Python, conda or any environment. You need
one file, `BleedoverCorrector-arm64.dmg` (about 105 MB). Installing takes about
a minute, and most of that is the first launch.

## What you need

- A Mac with Apple silicon (M1, M2, M3 or later) running macOS 12 or newer. To
  check, open  → *About This Mac*: *Chip* should say "Apple M…". The app does
  not run on Intel Macs.
- About 250 MB of free disk space for the app, plus room for correction
  results. A full experiment can take several GB.
- Your experiment folder, for example on the T7 drive. It must hold MAPA's
  outputs: `ptirf/`, `analysis/img_transformations/` and
  `img_results/results.feather`. `_metadata.csv` and `exp_details.txt` help but
  are optional.
- Memory: each correction worker uses about 5 GB. The app suggests how many
  workers your Mac can run.

## Install

1. **Open the `.dmg`** (double-click it). A window opens with the app and an
   *Applications* shortcut.
2. **Drag *Bleedover Corrector* onto *Applications*.** Then eject the `.dmg`.
3. **Open it the first time.** Double-click the app in Applications. The app
   isn't signed with a paid Apple developer ID, so macOS blocks the first launch
   with a message like *"Bleedover Corrector" can't be opened*. Click **Done**
   (not *Move to Trash*), then:
   - open **System Settings → Privacy & Security**, scroll down to the line
     about Bleedover Corrector, and click **Open Anyway**;
   - confirm with your password or Touch ID, and click **Open**.

   On macOS 14 and older you can instead **right-click the app → Open**, then
   click **Open**.
4. **Wait up to a minute.** macOS checks the whole app on its first launch.
   Later launches take about 2 seconds.

A window opens showing **Browse**. You only do steps 3 and 4 once.

## Using it day to day

- **Open:** double-click the app. If it's already open, it brings back the
  window instead of starting a second copy.
- **Window:** the app opens in Chrome or Edge without the address bar if you
  have one of them, otherwise in your default browser. That's normal: the app
  runs only on your Mac, and nothing is sent anywhere.
- **No Dock icon:** quit from **⚙ System → Quit**. Otherwise the app quits by
  itself 10 minutes after you close its window, but never during a correction.
- **Where things go:**
  - correction results: `~/Documents/Bleedover Corrector/runs/`
  - calibrations and settings: `~/Library/Application Support/BleedoverCorrector/`

  Your experiment folders are only read, never changed.

## Updating

Install the new `.dmg` the same way and choose **Replace** when asked. Your
results, calibrations and settings are kept. Don't replace the app during a
correction: quit it first (**⚙ System → Quit**).

## Uninstalling

Drag the app from Applications to the Trash. To remove everything, also delete
`~/Library/Application Support/BleedoverCorrector/`. Delete
`~/Documents/Bleedover Corrector/` only if you no longer need the results.

## If something goes wrong

- **"Bleedover Corrector is damaged and can't be opened"**: macOS says this
  about some downloaded apps it can't check. Open *Terminal* and run the
  following line, then open the app again:

  ```bash
  xattr -dr com.apple.quarantine "/Applications/Bleedover Corrector.app"
  ```

- **"Bad CPU type" or the app does nothing**: it's an Intel Mac. Ask for an
  Intel build, which has to be made on an Intel Mac.
- **The page says "Failed to fetch"**: the app was quit while its window was
  open. Double-click the app again.
- **An experiment won't open**: check that the drive is connected. The red
  badges under the folder path say which file is missing.
