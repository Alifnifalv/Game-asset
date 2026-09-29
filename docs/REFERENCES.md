# References: the look and motion target

The target is GiM Studio's *Animalia - Cow (young)*. The user decided to build it in-house, so the only sources are the
files below plus the close-up description the user gave in chat (copied here so it is not lost). Never modify the
reference media.

## Files in the repo root
| File | What it shows | Format |
|---|---|---|
| `Gemini_Generated_Image_jg2iuljg2iuljg2i.png` | **Primary reference.** Clean side view of the GiM young cow walking (faces right, white background): silhouette, proportions and coat layout. `tools/silhouette_compare.py` compares against it. | PNG 1365 × 768 |
| `2259689e-8b00-47fa-9263-9bfc88ca6d72.webp` | The same calf in a scene, side view, walking; the adult cow in the background. Session scratchpads also held it as `ref2.png` (a pixel-identical PNG copy). | WebP 1920 × 1080 |
| `videoplayback (1).mp4` | GiM young cow animation preview, **1080p**. Use it for motion and for close-up stills (index below). | H.264 1920 × 1080, 30 fps, 43.3 s |
| `Young Cow animation preview.mp4` | The same preview at low resolution. | H.264 640 × 360, 30 fps, 43.3 s |
| `videoplayback.mp4` | GiM **adult female** cow preview (not the calf: use only for gait and behaviour). | H.264 1280 × 720, 30 fps, 46.5 s |

## Timestamp index of `videoplayback (1).mp4`
Checked on a contact sheet of the video. The camera is fixed and the calf moves in a ground bowl.

| Time (s) | Content | Our clip |
|---|---|---|
| 0-~5 | Title cards ("COW", "animation preview") | - |
| ~5.5-8 | Walk (about 41 frames per cycle) | `Walk`, `Walk_RM`; `Walk_Slow(_RM)` (36 f) is closer to this cadence than `Walk` (24 f) |
| ~8.5-10 | Trot into gallop (the reviews used 8.6-13.4 s as the gallop reference) | `Trot`, `Gallop` |
| ~10.5-11.8 | Bounding, airborne gallop / leap strides (fore legs reaching, hind legs kicked back) | `Gallop`, `Leap` |
| ~12-13 | Stops, head lowering into grazing | `Graze_Start` |
| 13.6-20.5 | Grazing: the muzzle rests on the ground; left fore stepped forward | `Graze_Loop` |
| ~21-22.5 | Head coming up | `Graze_End` |
| 22.8-26.5 | Standing idle, looking around | `Idle`, `Idle_LookAround` |
| 26.8-27.9 | Death: falls onto its **right** side, legs out straight, head down (drop in ~13-15 frames) | `Death` |
| ~28-39 | Cut straight to lying (no lie-down or get-up transition is shown). Sternal: white belly and legs visible, one fore leg stretched forward, right fore hoof tucked under the chin; head turns (best stills 29.6-38.7 s) | `Lying_Idle` (and the end pose of `LieDown`) |
| ~40 | Fade out | - |
| 42.5 | Credits card | - |

**Grab a still** (1080p, full frame, about 1 s per frame; create the output folder first):
```bash
python3 -c "import sys, imageio.v3 as iio; t = float(sys.argv[1]); iio.imwrite(f'{sys.argv[2]}/calf_{t:05.1f}s.jpg', iio.imread('videoplayback (1).mp4', index=round(t * 30)), quality=92)" 14.0 <scratch>/hd
```
Earlier sessions kept crops of such stills (1520 × 900) as `<scratchpad>/hd/calf_<t>s.jpg` for t = 7.0, 8.0, 9.1, 11.4,
14.0, 17.0, 20.0, 23.0, 25.0, 30.0, 33.0, 36.4 and 38.7 s. Scratchpads do not survive the session, so regenerate them
with the command above.

## Close-up spec from the user (GiM close-ups, not on disk)
Use this as a checklist when judging the head, coat and lying pose.
- [ ] **Head coat:** orange-brown.
- [ ] **Forehead:** a fluffy **white** blaze/tuft between the ears.
- [ ] **Eyes:** big, dark amber-brown, with a pale rim.
- [ ] **Muzzle:** pale pink, with darker nostrils.
- [ ] **Ears:** orange outside, pale pink inside, with a fringe of fur on the edge.
- [ ] **Lying calf:** white belly and legs; one front leg stretched forward.

## Coat layout seen in the references
Red-pied: orange-brown barrel, rump, neck and head; white forehead blaze, white shoulder band, white brisket, belly, hip
band, lower legs and tail switch; pale muzzle; pale horn-coloured hooves; large ears; hornless.
Scale: withers ≈1.0 m.

## Where the references are used
- `tools/silhouette_compare.py <blend> Gemini_Generated_Image_*.png <out.png>`: side silhouette overlay.
- `tools/calf_textures.py`: coat colours and patch layout (see "Extending: change the coat" in `CLAUDE.md`).
- The clip families: key poses and timings are matched to the video ranges above (the family docstrings and
  `docs/WORKLOG.md` cite the exact seconds).
