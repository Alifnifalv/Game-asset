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
| `videoplayback.mp4` | GiM **adult female** cow preview: the look target of the adult cow (`--asset cow`, index below); for the calf use it only for gait and behaviour. | H.264 1280 × 720, 30 fps, 46.5 s |

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

## Adult cow: `videoplayback.mp4` (the `--asset cow` build)
The look and motion target of the adult cow (`Unity/Cow`). Checked on a 1.5 s contact sheet (1280 x 720, 30 fps, 46.5 s).

| Time (s) | Content | Our clip |
|---|---|---|
| 0-5 | Title cards ("COW", "bos taurus taurus", "animation preview") | - |
| ~5.5-9.5 | Walk | `Walk_Slow`, `Walk` |
| ~10-12 | Trot into gallop; 11.5 s: bounding stride, head up, tail out | `Trot`, `Gallop`, `Leap` |
| ~13-22 | Grazing: muzzle on the grass, one fore stepped forward | `Graze_*` |
| ~23-28.5 | Standing idle, looking around (28 s: best full side still) | `Idle`, `Idle_LookAround` |
| ~29-30 | Death: on her right side, legs out, head on the ground | `Death` |
| ~31-44 | Sternal lying, head turning (37-41 s: head toward the camera) | `Lying_Idle` |
| 44.5 | Credits card | - |

Look (28 s and 11.5 s stills): Simmental / Fleckvieh. Light red-tan neck, shoulders, barrel and rump broken by irregular,
jagged white patches (a white saddle behind the withers, white flecks along the patch borders); white head with tan ears
and a little tan at the poll; white throat, brisket, belly, lower legs and tail; short cream horns curving up and out
with darker tips; a large pink udder with four teats; dark slate hooves; grey-pink muzzle with dark nostrils; big dark
eyes. Sampled colours (lit, 9 x 9 px means): tan 188,132,105; horn 217,192,163; hoof 99,103,123; ear outside 114,71,60.
Scale: withers about 1.4 m (the build uses 1.42 x the calf's authoring rig).

## Rottweiler (male): `Rottweiler (male)/` (the `--asset dog` build)
Stills (GiM *Animalia - Rottweiler*, 1920 x 1080 `.webp`): lying sphinx with a hind leg out (`a4763944`, `8c06f643`),
leaping a wall (`53132155`), open-mouth approach (`91ababf0`), sitting with the tongue out (`843d64c3`), standing on a
container (`59985a6f`). `videoplayback (4).mp4` (1920 x 1080, 30 fps, 64 s):

| Time (s) | Content | Our clip |
|---|---|---|
| 0-5 | Title cards ("ROTTWEILER", "canis lupus familiaris", "animation preview") | - |
| ~5.5-10 | Sniffing walk, nose low | `Walk_Slow` |
| ~10.5-13 | Walk, trot | `Walk`, `Trot` |
| ~14-18.5 | Gallop | `Gallop` |
| ~19-20.5 | Leap | `Jump` |
| ~21-24 | Standing, panting, tongue out | `Idle_Pant` |
| ~24.5-27 | Sniffing the ground | `Idle_Sniff`, `Eat` |
| ~28-33 | Standing idle, looking around (32-33 s: best side stills) | `Idle`, `Idle_LookAround` |
| ~34-41 | Aggressive stance, stepping, barking | `Growl`, `Bark` |
| ~42-44 | Sitting down | `Sit_Start` |
| ~44-54 | Sitting: panting, looking around, scratching | `Sit_Idle` (no scratch: OI-52) |
| ~55-58 | Standing up, barking | `Sit_End`, `Bark` |
| ~58.7 | Play bow | `PlayBow` |
| ~59.7 | Rearing up on the hind legs | - (OI-52) |
| ~60.8 | Lying on its side (death) | `Death` |
| 61.5- | Credits card | - |

Look: male, stocky and muscular; broad skull with a pronounced stop, strong cheeks, deep broad muzzle, black lips; medium
pendant triangular ears set high and wide; dark brown eyes; natural tail (hanging at rest, raised in motion). Black coat
with a blue-grey sheen; mahogany tan: spot over each eye, cheeks, muzzle sides and chin, throat, two chest triangles,
fore legs from the toes up the forearm, hind legs from the toes up the front of the hock and inside the thighs, under the
tail. Pink-lavender tongue. The sample `Dog/` (DogGlb.glb 870 tris, Rigify metarig with 38 bones, clips Bark, Idle,
Idle_Tail_Wag, Lay_Start/Loop, Run, Sit_Start/Loop, Walk at 24 fps) was used as a pose reference for sitting and lying.

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
