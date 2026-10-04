# 0015: OCR experiment on the panorama crops

- **Status:** Accepted. OCR is not the missing piece; the imagery tier is data-limited.
- **Date:** 2026-10-04
- **Code:** `ocr.py` (Apple Vision text recognition, position split, name matching), `scripts/ocr_experiment.py`, `scripts/ocr_experiment_report.py`

## What was tried

The vision-language model reads a sign on only 20% of commercial or mixed buildings (0014). A dedicated OCR model might read more. I used **Apple's on-device Vision text recogniser** (no model download, macOS only, bindings via `pyobjc-framework-Vision`) on the same 136 East Passyunk crops, with positions: text near the middle of an aimed view is attributed to the target, text toward the sides to neighbours. Two renderings per building: the 1024-pixel view used so far, and a native-resolution render upscaled 2x with Lanczos (no interpolation blur before the upscale).

## Results

| | commercial or mixed (107) | other (29) |
|---|---|---|
| OCR, centre text, native x2 | **17%** | 7% |
| OCR, centre text, 1024 view | 15% | 7% |
| VLM tight-v4 own-sign (re-parsed) | 20% | 7% |

Jev with the OCR text added (native x2): TP 31 to 34, FP 1 to 1, recall 0.29 to 0.32, AUROC 0.851 to 0.863, AP 0.948 to 0.952. It rescues **0 of the stacker's 18 misses**. The text OCR does read is often fragmentary ("SAL", "PISTE", "MOÒN, IGHT", "SISTOLA:"), not clean business names; that happens because a panorama spreads 5,376 pixels over 360 degrees, so a sign's letters are a few pixels tall.

## Findings

1. **OCR does not beat the VLM here.** Similar rates, fragmentary text, no rescue beyond the stacker. The VLM's context-aware reading is about as good as OCR's pixel reading at this resolution.
2. **The imagery tier is limited by what the crops contain, not by the reader.** I reviewed six random commercial or mixed buildings where neither OCR nor the VLM found a sign (of 80 such buildings). In all six no legible sign for the target exists in the crop: a large mural wall, a parked car and a cyclist blocking the view (twice), a corner building whose awning carries no text (the only words in frame were a street sign and a neighbour's), a bare white facade, and a view aimed at an intersection. Occlusion, framing at corners, blank awnings and murals are the limit.
3. **The licensed-name check is not a usable yardstick.** I tried to score text against the licensed business names near each building. Licence names are legal entities ("BENTLEY0925 LLC", "See & puck LLC (Soa)"), not trade names, and the licence point often belongs to a neighbouring business, so a correct read scored as a miss (0 of 77 for both methods). The matcher itself works (tests cover partial reads such as "MOON, IGHT" against "MoonNight LLC"), the reference does not. Discarded.
4. **Tooling quirk worth remembering:** Apple Vision returned nothing for a JPEG crop that returned text as PNG data. `read_text` therefore passes decoded pixels as PNG data, and a missing path raises instead of silently returning nothing.

## Conclusion for the imagery tier

Three attempts (a VLM, a tighter VLM view with a position-aware caption, and OCR) converge: with this imagery, **a building's sign is legible for roughly one commercial building in five, the readers cannot do much better, and what they read adds little beyond the stacker** (0 to 1 rescued of 18). I am stopping model changes here. The tier stays in the codebase, documented, as a measured low-yield addition. Further gains would need different data (several views per building, newer imagery, or something other than street photos), not a better reader. The 7B vision model remains untried; the review of failures suggests it would not change the picture, so I am not spending the 5.5 GB download on it.
