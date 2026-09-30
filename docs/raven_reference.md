# Raven reference spec (Corvus corax, for Unity; look target: GiM "Animalia - Raven")

This spec merges four checked studies: anatomy, wings/tail, animation and materials. Where a study and its checker
disagreed, the checker's corrected value is used. Where two studies disagreed, the merge decision is recorded in
section 1.4. Every number is for the **final bird** (there is no scale stage).

**Frame:** metres, Z up, the bird faces **-Y**, **+X = the bird's LEFT**, ground z = 0. Y = 0 is at the foot base (MTP)
of the standing foot and X = 0 is the midline. "±X" means the left value is +X and the right value is mirrored.
**Timing:** 30 fps (GiM authored its clips at 60 fps). **L** = total length = 0.62 m.

**References** (the repo is read-only):
- `ravan/*.webp`: 6 GiM stills, also as PNG in `scratchpad/raven/refs/` (session scratchpad).
  - 88c16e0c: perched side view (the main side reference).
  - 0a423e61: flying, seen from above.
  - f6338d68: flying, wings up.
  - 3f2c1cb4 and 4c08d018: head close-ups.
  - 95ce4d97: small, perched on a roof.
- `ravan/videoplayback (6).mp4`: GiM preview, 1920x1080, 30 fps, 1450 frames.
- `ravan/Raven.glb`: the user's sample. It has 2.6k tris, a 48-bone metarig, no weights and no clips. Treat it only as a
  hint for bone naming.

---

## 1. Overview and scale

### 1.1 Look summary
- **Build:** a large, heavy-billed corvid with an all-black glossy plumage.
- **Plumage colour:** a weak violet sheen on the head, nape, mantle and wings. The tail is near-neutral, with **no teal**.
  The breast and belly are warm brown-black and less glossy.
- **Head:** heavy, with a deep, strongly hooked bill. The proximal 40% of the culmen is covered by forward-pointing
  nasal bristles. The forehead is flat and continues the culmen line.
- **Eye:** a dark umber iris about 1 cm across, inside a pale-grey beaded eyelid ring about 1.6 cm across. The ring is a
  GiM exaggeration that reads mostly as specular.
- **Throat:** a shaggy "beard" of lanceolate hackles. This is the strongest silhouette feature of the head.
- **Tail:** long and graduated, wedge/diamond-shaped when spread. The folded primaries stop about 0.09-0.11 m short of
  the tail tip.
- **Legs and feet:** slate-grey, clearly lighter than the plumage. GiM's toes are long and splayed, with big black curved
  claws.
- **Wings:** in the glide, 5 slotted "finger" primaries (P5 partial, P6-P9 clear). The span is 1.08 m, which is short
  for a real raven. This is the GiM look.

### 1.2 Master dimensions (rest standing pose unless stated)
| Item | Value (m) | Ratio to L |
|---|---|---|
| Total length, bill tip to tail tip (chord) | 0.620: bill tip (0,-0.304,0.321), tail tip (0,0.263,0.069) | 1 |
| Horizontal extent | 0.567 | 0.91 |
| Crown height | 0.389 (range +0.00 to +0.03, from the camera elevation) | 0.63 |
| Bill tip height | 0.321 | 0.52 |
| Back line, dorsal silhouette nape to rump | 31 deg front-up (walk: 22-24 deg) | |
| Spine axis T1 to pygostyle | 32 deg | |
| Trunk depth, perpendicular to the axis (with feathers) | 0.155 | 0.25 |
| Width at the folded-wing shoulders | 0.15-0.16 | 0.25 |
| Breast / belly / rump width | 0.12 / 0.10-0.11 / 0.07 | |
| Head length, bill tip to occiput | 0.136 | 0.22 |
| Head height / width at the eyes | 0.065 / 0.052 | 0.10 / 0.084 |
| Gape, rictus to tip | 0.069 | 0.111 |
| Culmen chord | 0.074 | 0.119 |
| Eye centre to bill tip | 0.078 | 0.126 |
| Iris (visible dark disc) | 0.010 (0.0095-0.011) | 0.016 |
| Eyelid ring, outer diameter | 0.016 (0.014-0.017) | 0.026 |
| Femur / tibiotarsus / tarsometatarsus | 0.058 / 0.105 / 0.068 | 0.094 / 0.169 / 0.110 |
| Middle toe + claw | 0.077 (0.054 + 0.023) | 0.124 |
| Tail, central rectrices from the pygostyle | 0.234 | 0.377 |
| Wingspan in glide, tip to tip | **1.08** (plausible 1.04-1.14) | 1.74 |
| Arm chord / folded carpal-to-primary-tip | 0.245 (0.24-0.28) / 0.35 | 0.40 / 0.57 |
| Tail beyond the folded primary tips | 0.09 as built (GiM shows 0.11-0.12, see 4.9 and OQ-1) | 0.15-0.18 |

### 1.3 How it was measured (scales per source)
| Source | Scale | Notes |
|---|---|---|
| 88c16e0c (perched side) | **0.4486 mm/px** (2.23 px/mm); bill tip (487,280) to tail tip (1732,897) = 1382-1389 px = 0.62 m | Origin = the near-foot base at image (1165,995): `Y = (x-1165)*k`, `Z = (995-y)*k`. The camera is 15-25 deg above, so heights may be 3-7% low. The back outline is the measured silhouette edge (dark-pixel scan every 25 px). |
| Video 11.0-13.0 s (walking side) | about 0.954 mm/px at 12.5 s; verticals x1.10 (camera about 25 deg up) | Segmented against the yellow-green background. Used for the walk posture, tarsus and toes. |
| 3f2c1cb4 (head close-up) | 0.142-0.151 mm/px (eye centre to bill tip 544 px = 77-78 mm; gape 456 px) | About 20 deg off side-on, ±15%. Used for the eye, bill texture, hackles and bristles. |
| 4c08d018 (head close-up, 1950x1300) | about 12.7 px/mm (gape 544 px) | |
| 0a423e61 (top view, banking) | body axis 0.642 mm/px (963-972 px along the body = 0.62 m) | An oblique perspective view: body and span axes are 60 deg apart in the image. An affine deskew is in `study/wing_tail/deskew.py`. The X/Y ratio cannot be recovered from it, so the hand was fixed from the folded chord (4.1). |
| f6338d68 (wings up) | 1.233 mm/px | Wrist-to-fingertip 0.33-0.34 m. Shows the ventral surface of the near (left) wing. |
| Front frame 6.2 s | about 12.5 px/cm (from the tarsus) | Widths, ±15%. |
| Video timing | frame f = int(t*30), 0-based | Bird-mask bbox timeline, frame differences, autocorrelation, OpenCV template tracks. |

### 1.4 Merge decisions (conflicts between the studies)
1. **Shoulder joint.** Anatomy had (±0.030,-0.090,0.262) and the wing study had X ±0.045. Both are merged into
   **(±0.040,-0.094,0.264)**. With the wing study's elbow this gives a humerus of **0.086**, which matches the anatomy
   estimate (0.086). The spread-wing planform, which is relative to the shoulder, is unchanged.
2. **Shoulder-to-pygostyle distance.** The top view gives 0.215 and the rigid anatomical trunk gives 0.17.
   - **The anatomical trunk is used.** The top-view "shoulder" (0.165 behind the bill tip in flight) cannot be the
     glenoid: in the standing S-necked bird it already sits 0.21 behind the bill tip.
   - The wing tables stay relative to the shoulder, so nothing else changes. The innermost trailing edge (T3 tip) then
     reaches about 0.04 behind the pygostyle, over the tail base, which is correct for a bird.
3. **Tail length.** Anatomy gave 0.234 (from the 0.62 chord at the 30 deg rest carriage) and the wing study 0.240 (top
   view 0.237). **R1 = 0.234** is used and the wing study's graduation is scaled x0.975 (R6 = 0.191).
4. **Folded wing and tail projection.**
   - The wing study's primary lengths fold (carpal outline to tip) to **0.356**. That matches the video's folded chord of
     0.35, but places the folded tips at Y about 0.19, which leaves **0.090** of tail beyond them.
   - The side still measures 0.11-0.12, with a folded chord of 0.32-0.33.
   - This spec keeps the flight planform and the lengths that are consistent with it (span 1.08). The folded-pose
     targets in 2.2 are the rigid-bone result. If the Unity look test wants the full 0.11, shorten P3-P8 by 7% (OQ-1).
5. **Eye size.** Anatomy gave iris 0.011 and ring 0.017 (gape-scaled). Materials gave opening 9.5 mm and ring 14-15 mm
   (eye-to-bill-scaled). The same pixels were measured with scales 6% apart. **Merged: iris 0.010, ring outer 0.016,
   ring width 2-3 mm.**
6. **Hackle width.** Anatomy gave 5-8 mm (coarse, from 88) and materials 2.5-4.5 mm (the 3f2c close-up). The close-up
   wins: **individual hackles are 3-5 mm wide**. Mesh cards may bundle 2 hackles (6-8 mm).
7. **Beard length.** The anatomy coordinates run from the chin (-0.247,0.324) to the tips (-0.192,0.240), which is about
   0.10 along the throat. The materials study's 85 mm used a different chin point. **The anatomy coordinates are used.**
8. **Idle body angle.** The animation study read 35-40 deg from a near-frontal view. The side measurement is 31 deg (back)
   and 32 deg (spine) and is used for the rest pose. Idles may pitch up to about 36 deg.
9. **Closed tail width.** Anatomy gave 0.055 at the end of the coverts and 0.045 near the tip. The wing study gave
   0.07-0.08 (low confidence, oblique frame). **Used: 0.055-0.065 mid-tail, narrowing to a pointed-rounded tip about
   0.045 wide** (a stack of 0.05-wide rectrices). See OQ-6.
10. **Walk speed.** Merged at **0.16 m/s** (stride 0.16 m per 30 f cycle). The animation study measured 0.17 m/s, ±30%.

---

## 2. Skeleton

### 2.1 Proposed bone hierarchy
All bones are unconnected, as in the dog pipeline. The rig bakes edit bones one by one.
- `Root` (ground, origin; the root-motion node)
  - `Hips` (synsacrum)
    - `Spine1` > `Spine2` (chest; T1 at its tail)
      - `Neck1` > `Neck2` > `Neck3` > `Head`
        - `Head` > `Jaw` (lower mandible)
        - `Head` > `Eye.X`
        - `Head` > `Lid.X` (optional; GiM 2.3.1 added eyelid bones)
        - `Head` > `Throat` (hackle puff / caw)
      - `Spine2` > `Shoulder.X` (scapular feathers; optional) > `UpperArm.X` > `Forearm.X` > `Hand.X`
        - `UpperArm.X` > `Tert1..3.X`
        - `Forearm.X` > `Sec1..6.X`
        - `Hand.X` > `Alula.X`
        - `Hand.X` > `Prim01..10.X`
    - `Hips` > `TailBase` > `Tail` (pygostyle) > `Rect1..6.X`
    - `Hips` > `Thigh.X` > `Shin.X` > `Tarsus.X` > toes:
      - `Toe3a/b/c.X` (middle)
      - `Toe2a/b.X` (inner)
      - `Toe4a/b.X` (outer)
      - `Hallux_a/b.X` (hind)

Notes on the hierarchy:
- **Feather bones.** Each remex and rectrix is a rigid strip on its own bone. A fan interpolation drives the bones from
  the wing joint angles (and from a tail-spread parameter) and is baked to FK. Covert rows are rigid on
  UpperArm/Forearm/Hand, and interpolated rows get blended weights.
- **Bone count.** About 92 bones. A lean alternative (primaries in 3 groups, secondaries in 2, tail in 3 per side) is
  about 60. See OQ-9.
- **Toe curl.** Toe bones must support curl for GiM's `Add_Fingers_*` grips.

### 2.2 Rest standing pose (folded wings; bird frame)
| Joint | Position (X, Y, Z) | Notes |
|---|---|---|
| Root | (0, 0, 0) | |
| Hips head: synsacrum at the hip station | (0, 0.000, 0.220) | 2.3 cm above the acetabulum |
| Spine1 head: synsacrum front | (0, -0.028, 0.239) | |
| Spine2 head: mid thoracic | (0, -0.058, 0.259) | about 4 cm below the dorsal outline |
| Neck1 head: T1 (neck base) | (0, -0.098, 0.285) | 4.1 cm below the outline |
| Neck2 head: mid neck | (0, -0.140, 0.318) | hidden S-curve; T1 to atlas chord 0.127 |
| Neck3 head: upper neck | (0, -0.180, 0.336) | |
| Head head: atlas / occipital condyle | (0, -0.211, 0.342) | may sit 0.5-1 cm further back |
| Upper-bill hinge (craniofacial), Head tail | (0, -0.246, 0.366) | at the culmen feather base |
| Jaw head: quadrate hinge (midline bone) | (0, -0.224, 0.336) | the real hinges are at X ±0.013, level with the rictus |
| Jaw tail: lower-mandible tip | (0, -0.300, 0.320) | the upper hook overhangs it by about 4 mm |
| Bill tip (upper) | (0, -0.304, 0.321) | |
| Rictus (gape corner) | (±0.013, -0.238, 0.340) | |
| Eye centre | (±0.021, -0.233, 0.354) | |
| Throat (hackle root, suggested) | (0, -0.228, 0.318) to (0, -0.205, 0.275) | |
| TailBase head: caudal vertebrae | (0, 0.032, 0.202) | |
| Tail head: pygostyle | (0, 0.060, 0.186) | 3.9 cm below the outline |
| Tail tip (R1) | (0, 0.263, 0.069) | 30 deg below horizontal, 0.234 long |
| Shoulder (glenoid) | (±0.040, -0.094, 0.264) | merged (1.4-1) |
| Elbow, folded | (±0.055, -0.016, 0.233) | humerus 0.085 |
| Wrist, folded (skeletal) | (±0.060, -0.124, 0.261) | ulna 0.112 |
| Wing bend outline (carpal plus coverts) | (±0.068, -0.132, 0.265) | 0.172 behind the bill tip (measured 0.17-0.18) |
| Hand tip, folded | (±0.057, -0.050, 0.249) | hand 0.075, parallel to the ulna, pointing back |
| Longest primary tips (P6/P7), folded | (±0.013, 0.192, 0.127) | lie on the upper tail surface; 0.090 short of the tail tip |
| Hip (acetabulum) | (±0.026, -0.005, 0.197) | |
| Knee | (±0.045, -0.0455, 0.160) | inside the body; femur 0.058, 42 deg below horizontal pointing forward |
| Ankle (intertarsal) | (±0.040, 0.019, 0.077) | tibiotarsus 0.105, 52 deg below horizontal pointing back; just below the trousers |
| MTP (foot base) | (±0.042, 0.000, 0.012) | tarsometatarsus 0.068, 16 deg from vertical, top behind |
| Toe III joints | (±0.044,-0.017,0.006), (±0.046,-0.030,0.006), (±0.048,-0.042,0.006), claw base (±0.050,-0.054,0.006) | phalanges 0.017/0.013/0.012/0.012 |
| Toe III claw tip | (±0.053, -0.076, 0.002) | foot turned out 8 deg |
| Toe II claw tip (inner) | (±0.029, -0.054, 0.002) | 22 deg inward of III |
| Toe IV claw tip (outer) | (±0.071, -0.050, 0.002) | 22 deg outward of III |
| Hallux claw tip | (±0.036, 0.046, 0.002) | straight back, 10 deg toward the midline |

### 2.3 Spread-wing pose (recommended bind pose for feather modelling)
- **Trunk, legs, head and tail:** as in 2.2.
- **Wings:** laid flat in the plane that contains the lateral X axis and the spine direction
  **u = (0, 0.848, -0.530)** (the spine is 32 deg down-back). When the body is levelled in flight, this plane is
  horizontal.
- **Wing-plane coordinates** (the tables in section 4): x = distance from the midline; y = distance behind the shoulder
  along u.
- **Conversion to the bird frame** (left wing; mirror X for the right):
  `P = (x, -0.094 + 0.848*y, 0.264 - 0.530*y)`.

| Joint / point | Wing plane (x, y) | Bird frame (X, Y, Z) | Segment |
|---|---|---|---|
| Shoulder | (0.040, 0.000) | (0.040, -0.094, 0.264) | |
| Elbow | (0.120, 0.032) | (0.120, -0.067, 0.247) | humerus 0.086, swept 22 deg back from lateral |
| Wrist | (0.222, -0.016) | (0.222, -0.108, 0.272) | ulna/radius 0.113, running forward-out; 1.5 cm behind the leading edge |
| Hand tip | (0.296, 0.000) | (0.296, -0.094, 0.264) | carpometacarpus plus digit 0.076; P10 leaves the leading edge here |
| Leading-edge root (propatagium) | (0.010, -0.028) | (0.010, -0.118, 0.279) | |
| P10 / P9 / P8 tips | see 4.3 | (0.437,-0.087,0.260) / (0.507,-0.071,0.250) / (0.540,-0.018,0.216) | |
| P7 / P6 / P5 tips | | (0.539,0.034,0.184) / (0.516,0.063,0.166) / (0.487,0.083,0.153) | |
| P4 / P1 / S1 tips | | (0.454,0.093,0.147) / (0.289,0.087,0.151) / (0.266,0.089,0.150) | |
| S6 / T3 tips | | (0.141,0.084,0.153) / (0.060,0.086,0.152) | |

**Glide joint angles:** elbow about 132 deg open; wrist about 143 deg (the hand bends 37 deg back from the forearm line).
A straighter wing needs the joint positions moved together; the angles alone cannot be changed (the planform tips were
measured).

### 2.4 Flight attitude (Glide, Fly)
- **Trunk:** pitched about **28 deg nose-down** from rest, so the spine T1->pygostyle falls about 4 deg below horizontal
  going back. That is a slight nose-up attitude.
- **Neck:** extended about 2-3 cm forward; the head is level and horizon-stabilised.
- **Tail:** in line with the body and half-spread (glide fan 4.8).
- **Legs:** tucked under the body. Tarsi folded back against the belly, toes curled.
- **Wings:** as in 2.3. The arm dihedral is 0 to +5 deg, and the fingertips curl up 10-15 deg.

### 2.5 Invariant bone lengths (the rig must keep them in every pose)
| Bone | Length (m) |
|---|---|
| Femur | 0.058 |
| Tibiotarsus | 0.105 |
| Tarsometatarsus | 0.068 |
| Humerus | 0.086 |
| Ulna | 0.113 |
| Hand (carpometacarpus + digit) | 0.076 |
| Neck chord, T1 to atlas | 0.127 (the S-curve extends by up to about 0.03 in flight or when stretching) |

Leg IK: 2-bone analytic from hip, knee-pole and ankle, plus a tarsus hinge to the MTP (as in the dog pipeline). A planted
foot is pinned at the MTP and the claw tips.

---

## 3. Body, head, bill, legs and feet

### 3.1 Side profile outline (rest; (Y, Z) on the midline)
The **dorsal** outline behind the nape is the measured silhouette edge. On a rounded back that edge lies less than 0.5 cm
above the midline profile, so it can be used directly.

**Dorsal line:**
- Head:
  - bill tip (-0.304,0.321), (-0.290,0.337)
  - bristle front (-0.270,0.356), culmen feather base (-0.248,0.369)
  - forehead (-0.229,0.381), crown (-0.209,0.389), (-0.190,0.386)
  - occiput (-0.168,0.375)
- Nape and back:
  - (-0.141,0.358), (-0.119,0.340), (-0.096,0.323), (-0.074,0.311), (-0.052,0.297)
  - (-0.029,0.280), (-0.007,0.262), (0.016,0.251), (0.038,0.238), (0.061,0.224)
  - (0.083,0.211), (0.105,0.202), (0.128,0.193)
  - rump and wing stack (0.150,0.183)
- Wing stack and tail:
  - tertial/secondary ends (0.162,0.173), (0.173,0.163)
  - primary tips over the tail about (0.19,0.13)
  - tail upper surface (0.200,0.109), tail tip (0.263,0.069)

**Ventral line:**
- Head and throat:
  - bill tip, lower-mandible edge (-0.275,0.322), chin (-0.247,0.324)
  - hackle front (-0.231,0.312), (-0.213,0.276), hackle tips (-0.192,0.240)
- Breast and belly:
  - breast, fullest forward point (-0.188,0.231), (-0.168,0.195), (-0.132,0.166)
  - belly (-0.079,0.130), trouser front (-0.047,0.105)
- Legs: trouser bottom (Y -0.02 to 0.02, z 0.067-0.075).
- Rear:
  - vent feathers (0.058,0.095)
  - undertail coverts (0.115,0.103), their end (0.155,0.113)
  - tail underside (0.230,0.084), tail tip

### 3.2 Widths (front frame 6.2 s, ±15%)
| Region | Width |
|---|---|
| Folded-wing shoulders | 0.15-0.16 |
| Breast below the wings | 0.12 |
| Belly | 0.10-0.11 |
| Rump | 0.07 |
| Neck with hackles | 0.080 (wider than the head) |
| Head at the eyes (feathered) | 0.052 |
| Head at the crown | 0.044 |
| Head at the cheeks / bill base | 0.040 |
| Eye bulge | to X ±0.025 |
| Stance: MTPs apart | 0.084 at rest; 0.10-0.11 while walking; feet parallel, turned out 5-10 deg |

### 3.3 Head and eye
**Crown:**
- The top is at (0,-0.209,0.389), 2.4 cm behind and 3.5 cm above the eye.
- The forehead rises at about **31 deg** (continuing the culmen), then flattens to about 20 deg into a crown that peaks
  slightly behind the eye.
- The occiput (0,-0.168,0.375) rounds straight into a thick nape with no notch.
- The skull without the bill (rictus to occiput) is about 0.070 long.

**Eye:**
- Centre (±0.021,-0.233,0.354): 0.5 cm behind and 1.4-1.5 cm above the rictus.
- The visible dark iris/opening is **0.010**, almond-shaped and slightly tilted. The pupil is only faintly darker.
- The pale **beaded eyelid ring** has an outer diameter of **0.016** and is 2-3 mm wide (a wet, beaded lid margin, not the
  nictitating membrane).
- The cornea is highly reflective. Use a separate cornea shell.
- For a blink, the third eyelid is a whitish sheet.

### 3.4 Bill
**Culmen:**
- The chord from the feather base (0,-0.248,0.369) to the tip is **0.074**.
- The proximal half is nearly straight, sloping 31-32 deg down-forward. The distal third curves strongly (55-70 deg) into
  a short hook.

**Gape:**
- **0.069** long. The bill axis tilts 16 deg below horizontal.
- The tomium runs from the rictus through (-0.270,0.334) to (-0.300,0.325), sagging slightly in the middle and ending
  under the hook.
- The gonys is almost straight, rising about 3 deg toward the tip.
- A small pale-grey gape flange (about 5 mm) sits at the rictus.

**Depth:**

| Station | Depth |
|---|---|
| Feather line | 0.034 (0.030 perpendicular to the bill axis) |
| Nostril / bristle front | 0.028-0.030 |
| 2/3 of the length | 0.018 |
| Hook | 0.006 |

The upper mandible takes about 60% of the depth.

**Width:**

| Station | Width |
|---|---|
| Base | 0.022 (0.026 across the gape flanges) |
| Mid-length | 0.014 |
| About 1 cm from the tip | 0.006 |

**Nasal bristles:**
- A dense tuft of stiff, forward-and-down-pointing feathers, 0.021-0.026 long.
- It covers the top and sides of the proximal **35-40%** of the culmen, to (0,-0.270,0.356), about 0.044-0.048 from the
  tip, and reaches halfway down the sides of the upper mandible.
- It hides the nostril, an 8x5 mm oval at (±0.009,-0.258,0.352).
- Finer rictal bristles sit at the gape.

### 3.5 Neck and throat hackles
**Neck:** thick and short-looking, fully feathered and merging into the head and mantle. Side-view depth is about 0.08 at
z 0.30.

**Hackles:**
- Pointed, lanceolate feathers with separated, jagged tips pointing down-forward.
- Full length 0.035-0.050; exposed 10-22 mm; **width 3-5 mm**.
- They cover the throat from the chin (-0.247,0.324) to the tips at about (-0.192,0.240). The front outline runs at about
  57 deg.
- They stand 1.5-2.5 cm off the throat surface and wrap round the neck sides to X ±0.035-0.040, below the ear coverts.
- The tips overlap the upper breast.
- The `Throat` bone puffs them for Caw/Attack.

### 3.6 Body plumage, trousers and undertail
**Breast and belly:** the fullest forward point is at (-0.188,0.231). The underside is a smooth convex curve to the belly.

**Vent:**
- The vent feather contour (0.058,0.095) lies about 9 cm below the pygostyle. The cloaca skin is only about 3 cm below it;
  the rest is loose feathering.
- The back surface (rump plus wing stack) is about 3.9 cm above the pygostyle.

**Folded wing:**
- It covers the flank down to about z 0.14 at mid-body. The flank feathers overlap its lower edge by 2-3 cm, and the
  scapulars cover its top edge by 2-3 cm over the front half.
- In side view it covers 75-80% of the body depth.
- Its top edge is steeper (33-36 deg) than the back and lies 1-2 cm below it. **Do not use that edge as the back line.**

**Trousers (feathered tibia):** shaggy, loose-tipped feathers down to z 0.067-0.075, just covering the ankle. Each is
0.035-0.040 across; the front edge is at Y -0.047.

**Undertail coverts:** long and black. They end about 0.11 from the pygostyle along the tail (about 47% of it), at
(0,0.155,0.113), and bulge 1-1.5 cm below the tail underside. The uppertail coverts are hidden under the wing tips.

### 3.7 Legs and feet
**Tarsus:**
- Length 0.068, pitched 16 deg from vertical with the top behind.
- Section at mid-length: 9 mm front-to-back x 6.5 mm side-to-side. 11 mm at the ankle, 10 mm at the MTP.
- The front is scutellate (7-8 transverse plates, 7-9 mm each); the sides are reticulate.

**Toes:**
- III (middle): 0.054 + claw 0.023 (range 0.072-0.083 in total).
- II (inner): 0.038 + claw 0.018.
- IV (outer): 0.041 + claw 0.017.
- I (hallux): 0.025-0.026 + claw 0.021. This is the largest and most curved claw.
- Spread between II and IV is about 45 deg (up to 55 is acceptable for GiM's splay).
- Toes are 6-7 mm thick at the base and 4 mm at the tip. Bulbous pads sit under each joint and add about 5 mm below the
  MTP line. Transverse scutes (3-5 mm) run on top, with 1-2 mm reticulate scales on the sides and pads.

**Claws:**
- Black to dark horn, darker than the toes, with a slightly paler tip.
- Arc 110-130 deg, 5 mm deep at the base, needle-pointed. Visible chord 18-20 mm.
- On flat ground the claw tips touch z = 0.

GiM's toes are longer than a real raven's (6.5-7 cm).

---

## 4. Wings and tail
Wing tables are for the LEFT wing in the glide, in the wing plane of 2.3: x from the midline, y behind the shoulder along
the body axis. Mirror x for the right wing.

### 4.1 Global wing numbers
| Quantity | Value | Note |
|---|---|---|
| Span, tip to tip | 1.08 (1.04-1.14) | 1.74 L. Derived: arm from anatomy, plus a hand fixed from GiM's folded chord (0.32-0.35 in two sources, and 0.33-0.34 wrist-to-fingertip in f6338). |
| Half-span | 0.54 | |
| Arm chord, leading to trailing edge | 0.245 (0.24-0.28) | uses a 0.857 perspective factor for the near wing; without it 0.28 |
| Hand chord at P3-P4 | 0.22-0.23 | tapers to a square, fingered tip |
| Wrist to the longest primary tip | 0.358 (P7), 0.356 (P6), 0.348 (P5) | |
| Area, one wing | 0.113 m² | total with the body strip about 0.23 m²; aspect ratio about 5.1 |
| Wrist position | x 0.222 (41% of the half-span) | |
| Leading edge | straight at y -0.025 to -0.032 from x 0.01 to just past the wrist, then swept back about 12 deg to the P10 tip | |
| Tip | square: P8 and P7 both reach x 0.54 | |
| Dihedral in glide | arm 0 to +5 deg; fingertips curl up 10-15 deg | visual estimates |

### 4.2 Planform outline (left wing, glide; x, y)
**Leading edge:**
- (0.010,-0.028) root at the neck
- (0.042,-0.025), (0.117,-0.029), (0.183,-0.032)
- (0.221,-0.031) wrist
- (0.248,-0.032), (0.299,-0.026), (0.352,-0.012), (0.402,-0.006)
- (0.437,0.008) P10 tip

**Tip:**
- P9 (0.507,0.027), P8 (0.540,0.090), P7 (0.539,0.151), P6 (0.516,0.185), P5 (0.487,0.209)

**Trailing edge:**
- P4 (0.454,0.221), P3 (0.399,0.215), P2 (0.340,0.210), P1 (0.289,0.214)
- S2 (0.249,0.218), S4 (0.191,0.215), S6/T1 (0.129,0.209), T2 (0.082,0.207)
- T3 (0.052,0.214), the root, against the flank

The finger gaps (P5/P6-P9) are open slots; the outline passes through the tips only. The machine-readable version is
`study/wing_tail_check/planform_corrected.json` (its skeleton has the shoulder at x 0.045; this spec uses 0.040).

### 4.3 Remiges (flight feathers)
Base = calamus on the bone (estimated): primaries 0.8 cm behind the hand bone, secondaries 1.2 cm behind the ulna,
tertials at the elbow/humerus. Tips are measured. The angle is measured from rearward (+y) toward outboard.

| Feather | Base (x,y) | Tip (x,y) | Build length | Rachis angle (deg) | Width (full / distal) |
|---|---|---|---|---|---|
| P10 | (0.296,0.008) | (0.437,0.008) | 0.14 | 90 | narrow, pointed; runs along the leading edge under the primary coverts/alula |
| P9 | (0.288,0.006) | (0.507,0.027) | 0.225 | 85 | 0.035 / 0.016-0.020 |
| P8 | (0.279,0.004) | (0.540,0.090) | 0.275 | 72 | 0.037 / 0.016-0.020 |
| P7 | (0.271,0.003) | (0.539,0.151) | 0.30 | 61 | 0.038 / 0.018-0.020 |
| P6 | (0.263,0.001) | (0.516,0.185) | 0.31 | 54 | 0.040 / 0.020 |
| P5 | (0.255,-0.001) | (0.487,0.209) | 0.305 | 48 | 0.038, slight narrowing |
| P4 | (0.247,-0.003) | (0.454,0.221) | 0.295 | 43 | 0.035-0.038 |
| P3 | (0.238,-0.004) | (0.399,0.215) | 0.27 | 36 | 0.035-0.038 |
| P2 | (0.230,-0.006) | (0.340,0.210) | 0.24 | 27 | 0.035-0.038 |
| P1 | (0.222,-0.008) | (0.289,0.214) | 0.23 | 17 | 0.035-0.038 |
| S1 | (0.222,-0.004) | (0.266,0.216) | 0.225 | 11 | 0.040-0.045 |
| S2 | (0.205,0.004) | (0.244,0.218) | 0.22 | 10 | 0.040-0.045 |
| S3 | (0.188,0.012) | (0.222,0.217) | 0.21 | 9 | 0.040-0.045 |
| S4 | (0.171,0.020) | (0.195,0.215) | 0.20 | 7 | 0.040-0.045 |
| S5 | (0.154,0.028) | (0.168,0.213) | 0.19 | 4 | 0.040-0.045 |
| S6 | (0.137,0.036) | (0.141,0.210) | 0.18 | 1 | 0.040-0.045 |
| T1 (S7) | (0.098,0.040) | (0.114,0.208) | 0.17 | 5 | 0.045 |
| T2 (S8) | (0.076,0.036) | (0.087,0.207) | 0.17 | 4 | 0.045 |
| T3 (S9) | (0.054,0.032) | (0.060,0.212) | 0.175 | 2 | 0.045; the innermost, covering the flank join |

- **Counts:** 10 primaries (P10 short), 6 secondaries + 3 tertials, 12 rectrices. About 9 scallops are visible along the
  arm, 0.027 apart.
- **Length order:** P6 = P7 longest, then P5 and P8 (P8 7-12% shorter than P7), then P9 (25-30% shorter). P10 is about
  45% of P7.
- **Fan:** P1 at 17 deg to P10 at 90 deg (73 deg in total). Adjacent rachises are 6-13 deg apart.

### 4.4 Fingers (emargination) and spread states
**Glide (top view):**
- P6-P9 are clearly separated fingers and P5 is partial. P1-P4 overlap, with rounded tips.
- Separation covers 35-40% of the feather length on P6-P9 and 20-25% on P5.
- Tip-to-tip spacing: P9-P8 0.071, P8-P7 0.061, P7-P6 0.041, P6-P5 0.038. The P5-P9 tips span 0.18.

**Emargination:**
- The outer-web step-narrowing starts, measured back from the tip, at: P9 0.10, P8 0.10, P7 0.09, P6 0.075, P5 0.05
  (partial).
- Inner-web notches are on P6-P9, a little nearer the base.

**Upstroke (f6338d68; video 17.3, 17.9, 18.9 s):**
- The hand is flexed and swept back 40-50 deg.
- Each primary rotates about its shaft to open slots; gaps are 1-1.5 cm.
- The fan is about half the glide spread (P5-P9 tips span about 0.09); separation shows over 20-25% of the length.

**Downstroke:** fully extended. The fan is as wide as the glide or wider, and the fingertips bend up and back under load.

**Folded:** the primaries are stacked with no separation.

### 4.5 Feather shapes (for strip modelling)
| Group | Width/length | Outer-vane share of the width | Taper and tip | Curvature |
|---|---|---|---|---|
| P6-P9 | 0.12-0.15 near the base; 0.06-0.08 on the emarginated part | 25-30% | step-narrowing, then a parallel finger with a rounded-pointed tip | gentle backward curve in the wing plane (5-8 deg over the distal third); cambered (concave below); tip curls up 10-15 deg in glide |
| P5 | about 0.12 | 30% | slight narrowing, rounded tip | as above, less |
| P1-P4 | 0.13-0.16 | 35% | parallel sides, broad rounded tip | slight backward curve and camber |
| Secondaries | 0.19-0.22 | 40% | parallel; blunt tip with a tiny point at the shaft. Adjacent tips form scallops 0.027 apart and 0.008-0.012 deep. | nearly flat, slight camber |
| Tertials | 0.25-0.28 | 45-50% | broad, rounded | flat; lie over the inner secondaries |
| Greater coverts | 0.35-0.40 (about 0.08 x 0.03) | 45% | rounded (the scalloped row) | follow the wing surface |
| Primary coverts | 0.30-0.35 (0.08-0.09 x 0.028) | 35% | rounded | follow the wing surface |
| Rectrices | about 0.20 (0.234 x 0.05) | R1 50%, R6 40% | parallel; rounded, slightly ragged tip | flat; slight downward curve when closed |

- **Shafts:** the rachises of the primaries, primary coverts and rectrices are pale grey-white on top and clearly
  visible; the secondary shafts are slightly less visible.
- **Rachis width:** 1.5-2.5 mm at the base, tapering.

### 4.6 Coverts
**Dorsal coverts:**
- **Marginal/lesser:** a soft band 3-4 cm deep along the leading edge and propatagium, blending into the body.
- **Median:** one row, 0.04-0.05 long, with faint scallops 5-7 cm behind the leading edge.
- **Greater secondary coverts:**
  - One prominent row with dark, rounded, scalloped tips and one covert per secondary/tertial.
  - Rooted on the ulna/humerus line, 0.06-0.08 long (up to 0.10 for the tertial coverts).
  - Tip line (x,y): (0.028,0.100), (0.057,0.098), (0.087,0.094), (0.108,0.087), (0.129,0.086), (0.153,0.078),
    (0.176,0.072), (0.201,0.065).
  - The tips sit at 39-54% of the chord and cover 25-35% of each secondary.
- **Greater primary coverts:** 0.08-0.09 long (shorter toward P10), with pale shafts. Tips at (0.251,0.084),
  (0.277,0.077), (0.298,0.037), (0.325,0.035). They cover the base third of the exposed primaries.
- **Alula:** 3 feathers at the wrist along the leading edge, the longest 0.06-0.07. Not separately visible in GiM.
- **Coverage:** from above there are about 3 rows on the arm, and together they cover 45-55% of the arm chord.

**Underwing:**
- Black/dark-grey coverts and axillaries in 2-3 scalloped rows, covering 40-50% of the chord.
- The underside of the flight feathers is paler, satin grey. There are no pale patches.

### 4.7 Overlap order (dorsal view, spread)
1. **Remiges:** each feather's outer (leading) vane lies over the inner vane of the next feather outward.
   - Dorsally, T3 lies over T2 over T1 over S6 ... over S1, S1 over P1, and P1 over P2 ... over P10.
   - Folded, from top to bottom: tertials, secondaries, P1 ... P10 (lowest).
2. **Coverts over remiges:** greater coverts over the bases of the flight feathers, median over greater, lesser over
   median, and the alula over the primary coverts. Within the greater-secondary row the outer covert may lie over the
   inner one (optional).
3. **Body feathers:** the scapulars lie over the tertial bases and inner coverts; the tertials lie over the inner
   secondaries.
4. **Tail:** R1 is on top, then R2 ... R6 at the bottom. The uppertail coverts cover about the base 40% of the tail.

### 4.8 Tail (12 rectrices, graduated)
| Pair | Length from the pygostyle | Width | Glide rachis angle from the midline | Closed angle |
|---|---|---|---|---|
| R1 | 0.234 | 0.050 | ±3 | ±0.5 |
| R2 | 0.230 | 0.050 | ±9 | ±1 |
| R3 | 0.223 | 0.049 | ±15 | ±1.5 |
| R4 | 0.214 | 0.047 | ±21 | ±2.5 |
| R5 | 0.204 | 0.045 | ±28 | ±3 |
| R6 | 0.191 | 0.042 | ±36 | ±4 |

- **Graduation:** 0.043 (R6 is 82% of R1). The stepped wedge tip is visible in 88c16e0c.
- **Glide:** a symmetric 72 deg fan. The R6 tips sit ±0.112 from the axis, so the width across the tips is about
  0.26-0.28.
- **Take-off and flapping:** the fan is as wide or wider and pressed down.
- **Closed:** 0.055-0.065 wide at mid-tail, narrowing to a pointed-rounded tip about 0.045 wide. The cross-section is
  slightly tented, with the outer feathers about 10 deg lower per side.
- **Carriage** (pygostyle to tip):

  | Pose | Tail angle |
  |---|---|
  | Rest | 30 deg below horizontal (in line with the 32 deg spine) |
  | Walk | 20-24 deg, parallel to the back |
  | Perched on an edge | 36-40 deg (about 5 deg drooped) |
  | Eat / Drink | rises to about horizontal |

### 4.9 Folded wing (Stand pose)
| Item | Value |
|---|---|
| Carpal (wing bend with coverts) | (±0.068,-0.132,0.265), 0.172 behind the bill tip, just behind and below the hackles, in the upper third of the body depth. With the marginal coverts it forms the "shoulder" bump; the breast feathers overlap it by 1-2 cm. |
| Skeleton | as in 2.2 (humerus back along the body, elbow folded about 25-30 deg, hand fully flexed and parallel to the ulna) |
| P6/P7 tips, as built | (±0.013,0.192,0.127): the carpal-outline-to-tip distance is 0.356; the tips sit 1.5 cm above the tail axis, 0.090 short of the tail tip |
| GiM measurement | carpal-to-tip 0.32-0.33 (88) / 0.35 (video 12.5 s); tail beyond the tips 0.11-0.12 (88) / 0.11 (video). See OQ-1. |
| Both wings | the primary tips meet over the uppertail at the same distance, with little crossing |
| Secondary tips | form the lower-rear edge of the wing, about 0.06 (along the wing axis) short of the primary tips; the tertials end with or just short of them |
| Primaries visible beyond the tertials | 0.05-0.07; only 3-4 stacked tips are readable |
| Greater coverts | a band with pale shaft streaks, running diagonally down-back across the front 40% of the wing |
| Idle | coverts and secondaries slightly ruffled, with glints (video 10.5-13.5 s); sleek in 88 |

---

## 5. Materials

### 5.1 Findings
- **Measurement.** Screen colours were measured (mid / dark / hi bands) and tint was judged in **CIE Lab**, not HSV,
  which is unstable on near-black pixels. The studio background is sRGB about 195,197,92 (Lab C about 53, hue 106).
  Because that bounce light is yellow-green, it cannot cause a violet tint.
- **Violet plumage bias.** All glossy plumage has one weak violet bias: Lab hue 305-320, chroma C 2-5.
  - It is strongest on the head (C 4-5) and weaker on the wings (C 2-3).
  - About C 1.4 of it is a global grade: the neutral bill also reads hue 345, C 1.4.
- **Wings.** Violet in the studio. In the sunny exterior stills they read blue to blue-violet (C 2-5), mainly in the
  sky-filled darks. Use a slightly bluer version of the plumage tint.
- **Tail.** Near-neutral (studio C 1.7; 0a42 faint olive C 1.5). **No teal.**
- **Throat hackles.** Near-neutral (C 0.4-1.1). Their highlights come from the spear shapes.
- **Breast, belly, flanks, undertail.** Less glossy, warm brown-black (Lab hue 30-60, C about 3).
- **Relative albedo (linear, same frame):**

  | Pair | Ratio |
  |---|---|
  | Head : mantle | 1.3 |
  | Wings : head | about 0.5 (conflicting evidence, 0.16-1.0) |
  | Bill : head | about 1.0 |
  | Tarsus : head | about 1.7 |
  | Lores : cheek | 0.72 |
  | Lit hackles : cheek | 0.87 (albedo about 0.75) |

- **Absolute anchor.** Melanin-black feathers reflect 3-5%. The head is set to sRGB about 60 (linear 0.044). Expect ±15%
  on the whole plumage set after a Unity look test.
- **Gloss** (hi/mid contrast):
  - Crown, hackles, breast and bill are about 1.5 (broad, soft sheen).
  - Legs 2.1.
  - Primaries 3.3, coverts 5.2, folded wing 7.8 (crisp rim highlights).
- **Not colour.** The golden legs, iris and breast in 88c16e0c / 95ce4d97 are a sunset grade. The white flecks on the
  folded-wing tips (video 10.5-14 s) are glints and light card undersides. **Do not paint either.**

### 5.2 Recommended Unity PBR set (Standard, Specular setup)
- **Shader:** `Standard (Specular setup)`, so the specular colour can carry the fake iridescence. Smoothness goes in the
  alpha of `_SpecGlossMap`; albedo alpha is the cutout. Feathers use Cutout mode.
- **Tinted F0:** every tinted value keeps a linear luminance of about 0.038-0.04.
- **Two-sided feathers:** either use flipped duplicate faces mapped to an "underside" atlas region (doubles the tris), or
  a Cull Off + VFACE custom shader (needs a Unity check).

| Region | Albedo sRGB | Specular F0 sRGB | Smoothness | Notes |
|---|---|---|---|---|
| Head, crown, face | 60,58,66 | 58,52,70 (violet) | 0.38-0.45 | matte-velvety; fine barb normal |
| Lores / around the eye | 50,49,55 | 58,52,70 | 0.35 | darker mask; add AO |
| Nape, neck | 56,54,61 | 58,52,70 | 0.45 | |
| Throat hackles | 53,52,59 (gaps/AO down to 8-12) | 56,54,66 | 0.50-0.55 | one highlight per spear; strong AO between |
| Mantle, back, scapulars | 52,51,57 | 58,52,70 | 0.55 | scaly; darker feather edges |
| Breast, belly, flanks | 50,46,42 | 56,56,56 | 0.30-0.35 | warm; fluffier edges |
| Thighs, undertail coverts | 44,42,42 | 56,56,56 | 0.30 | |
| Wing coverts | 42,43,49 | 52,54,74 (blue-violet) | 0.62 | |
| Remiges, upper side | 38,39,46 | 52,54,74 | 0.68-0.75 | glossiest; rim glints |
| Remiges, underside | 58,58,62 | 56,56,58 | 0.45 | paler, silvery |
| Tail, upper side | 40,41,46 | 54,55,62 | 0.62 | no teal |
| Rachis (remiges, tail) | 96,96,100 | 56 | 0.70 | 1.5-2.5 mm at the base, tapering |
| Frayed tips / vane splits | 58,58,64 | - | 0.40 | |
| Bill, base to mid | 60,59,58 | 56 | 0.50 | longitudinal grain normal |
| Bill, distal 14-16 mm (grading from about 30 mm) | to 112,111,107 at the tip | 56 | 0.35 | worn; a few pale specks (about 140) |
| Tomium line | 74,73,71 | 56 | 0.45 | |
| Nasal bristles (hair cards) | 50,49,54 | 56 | 0.60 | glints to about 180 on screen |
| Eyelid ring | 88,88,92 | 56 | 0.78-0.82 | beaded normal |
| Iris | outer 62,52,44; inner 46,39,33; limbal ring 22,19,17 | cornea 0.04 | cornea 0.95 | low saturation; separate cornea shell |
| Pupil | 12,11,11 | | | faint |
| Tarsus and toe scutes | 78,77,79 | 56 | 0.50 | |
| Scute edges / crevices | 112,111,113 / 28,28,31 | | 0.55 / 0.30 | |
| Claws | 40,38,37, tips to 62,58,54 | 56 | 0.62 | darker than the toes |
| Mouth interior / palate | 30,29,33 | 56 | 0.55-0.60 | near-black slate, slightly blue; mandible inner edges grey |
| Tongue | 46,40,43 | | 0.6 | never seen; a guess |

**Metallic fallback:** metallic 0 and the same albedo, with the tints pushed into the albedo at about 2x chroma:

| Region | Albedo sRGB |
|---|---|
| Head (violet) | 62,57,70 |
| Wings (blue-violet) | 39,40,50 |
| Tail | 40,41,46 |
| Breast (warm) | 51,46,41 |

Keep the smoothness values above.

### 5.3 Detail (normal / AO) maps
- **Head:**
  - Fine barb striations along the feather flow (backward from the bill, radiating round the eye), period 0.6-1.1 mm, low
    strength.
  - Individual feathers under 7-8 mm, so hardly visible.
- **Hackles:**
  - Separate spears with a central rachis ridge and barbs at 30 deg.
  - Ragged tips and strong AO in the gaps.
- **Body contour feathers:** rounded, overlapping "scales" with a step at each edge. Exposed width:
  - back 12-22 mm
  - breast 7-12 mm
  - scapulars and uppertail coverts 25-37 mm
- **Remiges and rectrices:**
  - Raised rachis; barbs at 20-35 deg toward the tip, spaced 0.5-1 mm.
  - Vane splits every 5-15 mm; frayed trailing edges and tips.
  - Primaries are 28-38 mm wide.
- **Bill:** longitudinal ridges spaced 0.85-1.4 mm, micro-pitting, and a smoother worn tip.
- **Legs:** see 3.7. Deep crevices.
- **Eyelid:** a ring of beads (0.7-1 mm).

### 5.4 Measured screen colours (key rows; sRGB mid [dark / hi], Lab tint)
| Region | Source | mid [dark / hi] | Tint |
|---|---|---|---|
| Crown, studio | v12.0 | 112,109,118 [83 / 176] | violet, hue 310, C 4.2 |
| Head, flight, studio | v20.5 | 129,126,135 [74 / 179] | violet, hue 305, C 5.3 (strongest) |
| Wing upper side, flight, studio | v20.5 | 129-130,126-127,131 [35-60 / 174-178] | hue 317-320, C 2.1-2.2 |
| Mantle, flight, studio | v20.5 | 114,112,118 | violet, C 3.4 |
| Folded wing, studio | v12.0 | 46,45,49 [31 / 109] | hue 306, C 3.1 |
| Tail upper, studio | v12.0 | 123,119,120 | neutral, C 1.7 |
| Breast, shade side, studio | v12.0 | 39,34,33 | warm, hue 30, C 2.8 |
| Secondaries, top | 0a42 | 39,43,50 | blue, hue 274, C 5.0 (skylight) |
| Tail, top | 0a42 | 49,53,51 | faint olive, hue 143, C 1.5 |
| Hackles, lit | 3f2c / 4c08 | 62,61,63 / 56,56,57 | C 1.1 / 0.4 |
| Bill, studio | v12.0 / v20.5 / v41.9 | 106 / 125 / 138 (grey) | neutral |
| Tarsus, lit, studio | v12.0 | 129-141,124-136,121-135 | 1.66-1.9x the crown (linear) |
| Mouth interior | v41.9 (frame 1257) | 24,25,29 to 29,29,33 | slight blue, hue 284-295 |
| Iris | 3f2c / 4c08 | 50,48,47 / 64,60,56 | HSV saturation 0.06-0.08 |

The full table is in the materials study (`study/materials/samples.txt`, `study/materials_check/samp.py`). Swatches are
in `study/materials_check/palette_corrected.png`.

---

## 6. Clip catalogue

### 6.1 Video structure (`videoplayback (6).mp4`; f = 0-based frame, t = f/30)
- **Title and cards:**
  - 0 to about 4.9 s: title card.
  - f147-172: fade-in.
  - f1340-1366: fade-out.
  - About 46-48 s: copyright card.
- **Hard cuts:** f550 -> f551 (ground to the flight close-up) and f703 -> f704 (flight back to the ground).
- **Blends:** Idle_Look -> Turn -> Idle -> Walk are blended. **Walk -> TakeOff is a hard switch** at f502 -> f503 (the
  wings jump from folded to fully raised). Do not copy that pop.
- **Camera:** it tracks the bird, the floor is untextured and the key light moves with the camera, so the preview cannot
  show whether Walk is in-place or uses root motion. The flight is in place relative to the camera; the shadow is about
  0.5-1 m below the bird.
- **GiM's own statement:** clips are authored at 60 fps, in-place and in-space.

### 6.2 What the preview shows
| # | Time (s) | Frames | Our clip (probable GiM name) | Loop | Notes |
|---|---|---|---|---|---|
| 1 | 5.50-9.30 | 165-279 | Idle_Look (Stand_01 + Add_Look_*) | loop | near-frontal; feet planted, staggered by one foot-length |
| 2 | 9.30-10.30 | 279-309 | Turn_R90 (Trans_TurnR90) | one-shot | turns about 70-90 deg to its right in 2 steps; possibly helped by a camera orbit |
| 3 | 10.30-14.93 | 309-448 | Idle (Stand_00) | loop | side view; head looks, breathing |
| 4 | 14.93-16.77 | 448-502 | Walk (Loco_Walk) | loop | 2 cycles, blended in from Idle |
| 5 | 16.77-18.33 | 503-550 | TakeOff (Trans_Stand_to_Flying) | one-shot | 3 wing tops; the feet stay within 0-10 cm of the ground; cut before any climb |
| 6 | 18.37-19.60 | 551-588 | Fly (Loco_Flying_Flapping) | loop | 2 beats, then blends to glide |
| 7 | 19.60-23.43 | 588-703 | Glide (Loco_Flying_Glide) | loop | |
| 8 | 23.47-34.50 | 704-1035 | Eat (Eating_01/02) | loop | 3 bouts |
| 9 | 34.50-40.30 | 1035-1209 | Drink (Drinking_01) | loop | 2 cycles of 90 f |
| 10 | 40.30-41.20 | 1209-1236 | Idle | | |
| 11 | 41.20-42.85 | 1236-1286 | Attack (Attack_Squabble) | one-shot | |
| 12 | 42.85-43.23 | 1286-1297 | Idle | | |
| 13 | 43.23 to about 44.7 | 1297-1340 | Death (Death_Stand_L/R) | one-shot + hold | |

Not shown: Caw, Hop, TurnL, Walk start/stop, Landing, hits, Sitting_Nest, Stand_Twig.

### 6.3 Key poses and timing
**Idle / Idle_Look:**
- **Stance:** staggered stance, back 31-36 deg, tail tip low, wings folded with the primary tips over the tail.
- **Saccades:** 3-5 f per head turn (for example about 70 deg of yaw between f235 and f245). Holds last 0.5-1.5 s. Head
  roll 10-20 deg, plus slow drifts.
- **Side idle:** bill closed; the head raises and lowers ±15 deg; a slight neck stretch at 13.1-13.4 s.
- **Key frames:**
  - Idle_Look: f186, f210, f236, f250, f276.
  - Idle: f345, f372, f393, f420, f441.

**Turn_R90** (30 f):
- The body yaws from near-frontal (f270) to right profile (f302).
- One foot swings at f288-296 and a smaller second step comes by f300-303.
- The head leads the body by 3-5 f.
- Key frames: f279, f285, f291, f297, f303, f309.

**Walk:**

| Event | Far (dark) leg | Near (light) leg |
|---|---|---|
| Lift-off | f448, f477 | f461, f491 |
| Touchdown | about f455, f485 | about f469, f499 |

- **Cycle:** 29-30 f (autocorrelation lag 30). Swing 7-8 f (26%), with long double-support phases.
- **Head:** a vertical/forward bob once per step (about 15 f), plus a lateral sway once per stride (29-30 f), 2-4 cm peak
  to peak. It reads as a waddle plus a head thrust, not a pigeon head-lock.
- **Body:** back line 22-24 deg; tail parallel to it.
- **Speed and stride:** about 0.16-0.17 m/s, stride about 0.16 m (0.26 L), ±30%.
- **Key frames:** f449, f456, f464, f470, f477, f491.

**TakeOff** (48 f visible):
- f503: the wings are already up (the pop).
- f504-510: the first downstroke, fast and blurred. The body pitches 30-40 deg nose-down.
- f511: the feet leave the ground and swing forward.
- **Wing tops:** f503, f517, f536, so the beats are **14 f then 19 f**.
- **Strokes:** downstrokes about 6 f; upstrokes 7-12 f, with f525-532 a wings-half-raised hold.
- **Legs and tail:** the legs dangle, flexed, toes curled. The tail spreads in the downstrokes.
- **Height:** near-touches at f523 and f547. The preview cuts before any climb.
- **Key frames:** f503, f507, f511, f518, f531, f537.

**Fly (flapping):**

| Phase | Frames | Pose |
|---|---|---|
| Bottom | f559-560 | wingtip -60 to -70 deg |
| Upstroke | f561-567 (about 8 f) | wrist flexed, hand swept back and in; shortest span at f563-565 |
| Top | f568-569 | +60 to 70 deg, extended |
| Downstroke | f570-578 (9-10 f) | fast, fully extended, blurred |

- **Period: 19 f** (0.63 s, 1.6 Hz). Amplitude 120-140 deg.
- The body bobs up 1-2 cm on the downstroke; the head is steady.
- Tail closed to half-spread; feet tucked.

**Glide:**
- Wings near flat (0-10 deg); the outer 5-6 primaries are slotted, with the tips curving up. The hand is slightly swept.
- Tail half-spread.
- The body floats ±1.5 cm over about 2 s (f608 up, f648 down). No banking.
- Key frames: f596, f620, f644, f668, f692, f700.

**Eat:**

| Bout | Lower | Bill on the ground | Rise | Then |
|---|---|---|---|---|
| A | f735-747 (12 f) | f744-778 (34 f), 2 bill opens (gape 15-20 deg, open about f762-770) | fast jerk up f780-790 (9 f, small sideways flick) | upright 26.3-27.0 s |
| B | from about f813 | f819-858 (open about f837-839) | f859-867 | swallow gape f869-871 |
| C | look up 29.1-30.3 s, slow peer down f909-933 | f939-978 | f979-990 | upright 33.0-34.5 s |

- Onsets are 2.6 s, then 3.2-3.4 s apart.
- At full depth the body pitches nose-down 60-70 deg and the bill tip reaches the ground. The tarsi stay planted with a
  little more ankle flex, and the tail rises to about horizontal.
- Key frames: f720, f744, f766, f784, f837, f869.

**Drink** (90 f):

| Phase | Time (s) | Frames |
|---|---|---|
| Lower | 34.6-35.0 | 12 |
| Dip (bill at or just below the ground; the deepest bow; tail up) | 35.0-35.9 | 27 |
| Raise | 35.9-36.4 | 15 |
| Head back (bill about 40 deg above horizontal at f1098, easing to 15 deg by f1112; swallowing) | 36.4-37.2 | 24 |
| Return to level | 37.2-37.6 | 12 |

Key frames: f1038, f1062, f1074, f1090, f1098, f1112.

**Attack** (Attack_Squabble, 48 f):

| Phase | Frames | Pose |
|---|---|---|
| Crouch | f1236-1241 | head and body lowering |
| Wing flare | f1242-1247 | wings raised and opened high, body lunging forward |
| Strike hop | f1248-1256 | big forward-down flap, both feet off the ground; bill open 30-40 deg; head thrust |
| Recover | f1258-1264 | wings half-open and level, then folding; gape closed by about f1262 |
| Hunched hold | f1264-1276 | crouched, wings half-folded and held off the body, feathers ruffled |
| Rise / settle | f1278-1286 | stands to the idle pose; tail flicks |

- Forward lunge of about 0.1-0.2 m.
- Key frames: f1238, f1244, f1250, f1256, f1266, f1282.

**Death:**
- f1297: standing; the head starts to tilt.
- f1298-1305 (8 f): collapse. The head drops and the body tips forward and sideways.
- f1305-1313: impact bounce and settle.
- From about f1313: static. The bird lies on its side (probably its right) with the belly and legs toward the camera,
  legs stiff and extended back and sideways, toes curled, wings loosely closed, head on the ground.
- Key frames: f1296, f1300, f1302, f1304, f1308, f1330.

### 6.4 Timing summary (30 fps)
| Quantity | Value |
|---|---|
| Walk cycle | 29-30 f; swing 7-8 f per leg |
| Walk stride / speed | 0.16 m (0.26 L) / 0.16 m/s (±30%) |
| Walk head bob / sway | 15 f (per step) / 29-30 f (per stride); 2-4 cm |
| Head saccade | 3-5 f; holds 15-45 f |
| Turn 90 | about 30 f, 2 steps |
| Flap (cruise) | 19 f per beat: up about 8 f, down about 10 f; amplitude about 130 deg |
| Flap (take-off) | 14 f, then 19 f; downstrokes about 6 f |
| Glide float | ±1.5 cm over about 2 s |
| Eat bout | lower 12 f, hold 34-40 f (2 bill opens of about 8 f), jerk up 9 f |
| Drink cycle | 90 f (12 / 27 / 15 / 24 / 12) |
| Attack | 48 f; gape about 35 deg at f1250-1259 |
| Death | collapse 8 f, settle 8 f, then hold |

GiM's flap (1.6 Hz) is about half a real raven's (3-4 Hz). **Match GiM** and use the Animator speed for faster flight.

### 6.5 GiM's published clip list (48; from web-search summaries)
- **Additive:**
  - Add_Cawing
  - Add_Fingers_ClosedMedium, Add_Fingers_ClosedTight, Add_Fingers_ClosedWide, Add_Fingers_Relaxed
  - Add_Hit_Chest/Head/Pelvis_Left/Right
  - Add_Look_Down/Left/LeftDown/LeftUp/Neutral/Right/RightDown/RightUp/Up
  - Add_Neutral
- **Actions:** Attack_Squabble; Death_Stand_Left(_Pose), Death_Stand_Right(_Pose); Drinking_01; Eating_01/02.
- **Locomotion:** Loco_Flying_Flapping, Loco_Flying_Glide, Loco_Hooping (sic: hopping), Loco_Walk.
- **Stands:** Sitting_Nest_01/02, Stand_00/01/02, Stand_Twig_01/02.
- **Transitions:** Trans_Flying_to_Stand, Trans_Stand_to_Flying, Trans_TurnL90(_OnSpot), Trans_TurnR90(_OnSpot),
  Trans_WalkStart, Trans_WalkStop.

Changelog: 2.3.1 added eyelid bones and extra neck/belly bones, and fixed a sliding foot in a turn.

### 6.6 Proposed clip list (30 fps; 41 clips, 42 with Caw_x3)
**Conventions:**
- RM = root motion on `Root`. `_IP` = an in-place twin, exported as a separate clip.
- Ground clips start and end on `stand()`; flight clips start and end on `fly_neutral()`.

| Clip | Loop | Root motion | Frames | Content / timing |
|---|---|---|---|---|
| Idle | loop | none | 120 | breathing (chest/belly scale ±1.5%, period 60-75 f), 1-2 small saccades (4 f), a tail flick |
| Idle_Look | loop | none | 180 | 4-5 saccades (3-5 f) left/right/tilt, holds 20-45 f |
| Idle_Preen | one-shot | none | 120 | head to the shoulder/wing coverts, 3 nibbles, return |
| Idle_Shake | one-shot | none | 45 | body ruffle (Throat/Hips scale puff), wings loosened, tail wag at 3 Hz; 10 f shake |
| Caw (+ Caw_x3) | one-shot | none | 45 | f0-8 bow (body +15 deg, neck forward); f8-14 bill opens to 30 deg, hackles puff, tail flicks down; hold 8 f; closed by f30; back by f45. Caw_x3: 3 calls 12-15 f apart |
| Eat | loop | none | 96 | lower 12; bill on the ground 36 (2 opens of 8 f, gape 15-20 deg, small tugs); jerk up 9; swallow gape 6; upright look 33 |
| Drink | loop | none | 90 | lower 12; dip 27 (bill tip 0-1 cm below z=0); raise 15; bill +40 deg for 24 (2 gulps); return 12 |
| Walk (+ Walk_IP) | loop | RM | 30 | 1 stride of 0.16 m, 0.16 m/s; swing 8 f per leg, half a cycle apart; head bob per step; lateral sway ±1.5 cm per stride; back 22-24 deg |
| Walk_Start / Walk_Stop | one-shot | RM | 15 / 15 | first / last half-step |
| Hop (+ Hop_IP) | loop | RM | 20 | 2-footed: crouch 5, push-off 3, air 8 (apex 6-8 cm, wings twitch half-open), land 4; 0.30 m per hop, 0.45 m/s |
| Turn_L90 / Turn_R90 | one-shot | RM yaw ±90 deg | 30 | 2 steps; the head leads by 4 f |
| Turn_L90_OnSpot / Turn_R90_OnSpot | one-shot | RM yaw ±90 deg, no translation | 20 | one small hop-turn, wings slightly opened |
| Attack | one-shot | RM, about 0.15 m forward | 48 | crouch 6, flare 6, lunge-hop and flap 8 (gape 35 deg), recover 8, hunched hold 12, rise 8 |
| Hit_L / Hit_R | one-shot | none | 15 | flinch away, wings jerk half-open for 5 f, ruffle |
| Death_L / Death_R | one-shot | small RM | 45 | collapse 8, bounce 8, settle 10; the last frame is the dead pose |
| Death_Pose_L / Death_Pose_R | loop | none | 2 | GiM Death_Stand_*_Pose (ragdoll start / corpse) |
| TakeOff | one-shot | RM up 1.2-1.5, forward 4.5-6, ending at 6-8 m/s | 45 | crouch 6; spring and first downstroke 8 (feet leave at about f10); 2 climbing beats (about 14 then 17 f, downstrokes about 6 f), legs trailing then tucked; ends on fly_neutral, phase-matched to Fly |
| Fly (+ Fly_IP) | loop | RM forward 8 m/s (8-10) | 20 | 1 beat: down 10-11, up 9-10 (wrist flexed, hand swept back); amplitude 130 deg; body bob 1-2 cm |
| Fly_Fast | loop | RM | 16 | optional; higher amplitude |
| Glide (+ Glide_IP) | loop | RM 8-10 m/s | 120 | as in 2.4; primaries slotted; ±1.5 cm float; tail and primary flex |
| Glide_Bank_L / Glide_Bank_R | loop | RM, yaw rate 30-40 deg/s | 60 | 25-30 deg roll (coordinated: yaw rate = g·tan(bank)/V); inner wing slightly flexed; tail twisted into the turn; head level |
| Fly_Turn_L / Fly_Turn_R | loop | RM yaw about 25 deg/s | 40 | 2 flaps at 20 deg bank (optional) |
| Flap_to_Glide / Glide_to_Flap | one-shot | RM | 15 / 15 | transitions, or a cross-fade at the end of a beat |
| Hover (brake flap) | loop | none | 16 | body pitched up 40 deg, legs forward (landing approach) |
| Land | one-shot | RM down 1.0-1.5, forward 4-5, from glide speed to 0 | 45 | glide-in 10; flare 8 (body up 45-60 deg, tail spread, legs forward); 2 braking beats 14; touchdown at about f32; fold and hop-settle onto stand() by f45 |
| Death_Fly | one-shot | RM falling | 40 | optional: wings collapse, tumble, ends on the dead pose |
| Perch_Idle | loop | none | 120 | optional: toes gripping (twig / roof edge; GiM Stand_Twig) |
| Sit_Nest | loop | none | 120 | optional: body lowered onto the tarsi |

**v1 priority set (24 clips):** Idle, Idle_Look, Caw, Eat, Drink, Walk, Walk_IP, Hop, Hop_IP, Turn_L90, Turn_R90, Attack,
Hit_L, Hit_R, Death_L, Death_R, TakeOff, Fly, Fly_IP, Glide, Glide_IP, Glide_Bank_L, Glide_Bank_R, Land.

**Continuity:**
- TakeOff must end at Fly's root velocity (nominal 8 m/s), and Land must start at Glide's.
- TakeOff starts from stand() / the walk pose itself (no pop).
- Suggested QA, in the style of the dog gate:
  - planted-foot slide ≤ 0.1 mm on Walk/Turn/idles
  - loop seam ≤ 0.01 mm
  - joint limits: knee/ankle never hyperextended; wrist/elbow within the fold-to-glide range
  - no feather-strip interpenetration in the folded pose (tertials over secondaries over primaries)
  - LOD bodies never below the ground except in Death / Eat / Drink (where the bill tip is allowed to reach z = -0.01)

---

## 7. Open questions
1. **Folded primary length vs tail projection (most visible).** With the flight-derived primaries (P6/P7 0.31/0.30) the
   rigid fold leaves 0.090 of tail beyond the primary tips; GiM shows 0.11-0.12.
   - Option: shorten P3-P8 by 7% (span 1.08 -> about 1.05, still inside the plausible range).
   - Option: fold the hand slightly further inward/forward.
   - Decide after a side-by-side render against 88c16e0c.
2. **Span 1.08** is derived, not measured (the top view cannot fix the X/Y ratio); the plausible range is 1.04-1.14.
   The arm chord of 0.245 depends on a 0.857 perspective factor (0.28 without it).
3. **Shoulder and trunk length.** The glenoid at (±0.040,-0.094,0.264) is an estimate. The top view suggests a longer
   shoulder-to-pygostyle distance (0.215 vs 0.17) and it was overruled. Check the wing root in a flight render against
   0a423e61 / f6338d68.
4. **No orthographic side view.** Heights from 88c16e0c may be 3-7% low (crown 0.389, +0 to +0.03). The atlas could sit
   0.5-1 cm further back. Widths are ±15%.
5. **Toes.** Middle toe 0.072-0.083 (0.077 chosen); hallux ±0.005; toe spread 45-55 deg.
6. **Closed tail width** (0.045-0.065) and the tail lengths/graduation (±2 cm) mix top-view data with real-bird data. The
   glide fan angle comes from a twisted, asymmetric fan.
7. **Feather identity.**
   - The secondary count (6 + 3 tertials) is the real-bird count; GiM shows about 9 arm scallops.
   - The P1-P4 labels in f6338d68 are tentative.
   - Which folded tip cluster in 88c16e0c belongs to which wing is unconfirmed.
   - The alula is not visible in GiM.
   - The reversed greater-covert overlap is optional.
8. **Walk.** In-place vs root motion cannot be told from the preview (we ship both). The speed of 0.16 m/s is ±30%.
9. **Rig size.** About 92 bones with per-feather bones, against about 60 in a grouped version. Choose before stage B.
   GiM also has extra neck/belly and eyelid bones.
10. **TakeOff climb and Land distances** are design values: the preview cuts before the climb, and no landing is shown.
    The flap rate (1.6 Hz) is GiM's, not a real raven's.
11. **Materials.**
    - Absolute albedo is anchored on 3-5% melanin reflectance (±15% after a Unity look test).
    - The wing albedo evidence conflicts (0.16-1.0x the head; 0.5x chosen).
    - The tint strength is a judgement call.
    - The tongue colour is a guess.
    - The Unity sRGB 30-50 dark-albedo floor and the Cull Off/VFACE two-sided shader need a Unity check.
12. **Death side** is ambiguous in the preview; both L and R are planned. **Eat** may be one clip or Eating_01 + 02.
13. **Clips with no reference** (Caw, Hop, Land, Hit, Glide_Bank, Idle_Preen, Hover) are designed from raven behaviour.

---

## Appendix: evidence files (under `scratchpad/raven/study/`)
- **Anatomy:**
  - `anatomy/annot_88c16e0c.png`, `annot_video_12.6.png`, `schematic_rest.png`
  - `anatomy/g88_head.png`, `g88_breast.png`, `g88_tail.png`, `g88_feet2.png`, `g4c.png`, `g3f.png`, `g126*.png`,
    `g_front62.png`, `walk_sheet.png`
  - Checker: `anatomy_check/check_88_outline.png` (measured silhouette vs the study), `check_126_outline.png`,
    `g88_*.png`, `feet_f_12.6.png`, `overlay.py`
- **Wings and tail:**
  - `wing_tail/annot_top_view.png`, `planform_deskewed.png` (mirrored/ventral drawing), `annot_f6338_fingers.png`,
    `annot_perched_88c16e0c.png`, `annot_perched_v12.5.png`, `grid_*.png`, `sheet_flight.png`, `deskew.py`,
    `build_final.py`
  - Checker: `wing_tail_check/planform_corrected.json` (use this), `planform_compare.png`, `folded_88c16e0c.png`,
    `hand_grid.png`, `top_wrist_grid.png`, `perch_v12.5.png`, `f6338_grid.png`
- **Animation:**
  - `anim/catalogue_keyposes.png`, `timeline_segments.png`, `timeline_mask.png`, `s_walk_feet.png`, `s_flap_cycle.png`,
    `s_takeoff_*.png`, `s_glide.png`, `s_eat_*.png`, `s_drink*.png`, `s_attack_big.png`, `s_death.png`,
    `s_turn_feet.png`, `track.py`
  - Checker: `anim_check/cut503.png`, `flap.png`, `to.png`, `turn.png`, `eat.png`, `drink.png`, `drinkup.png`,
    `att.png`, `death.png`, `diff.npy`, `mask.npy`
- **Materials:**
  - `materials/samples.txt`, `boxes.json`, `boxes_*.png`, `chroma5x_*.png`, `c_*.png` (eye, bill, nasal, hackles,
    feet, gape crops)
  - Checker: `materials_check/palette_corrected.png`, `samp.py`, `boxes1-3.py`, `eye_grid.png`, `eye4c.png`,
    `eye88.png`, `hackle_grid.png`, `mouth_zoom.png`
