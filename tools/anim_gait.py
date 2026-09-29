"""Quadruped gait maths for the calf (pure Python, no bpy).

Conventions (Blender space of the calf rig): Z up, the calf faces -Y, units = meters, 30 fps.
A gait is described per leg by a phase offset and shared stance duty factor. For a cycle phase
p in [0,1) every foot is either in STANCE (planted: in world space it does not move; relative to
the body it slides backward at the body speed) or in SWING (lifted, carried forward on an arc).

Everything here returns offsets relative to the rest pose, so the caller (tools/anim_lib.py)
only adds them to rest positions / rotations of the rig.
"""
from dataclasses import dataclass, field, replace
import math

LEGS = ("LF", "RF", "LH", "RH")          # left/right fore, left/right hind
FPS = 30


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def smoother(t):
    t = min(1.0, max(0.0, t))
    return t * t * t * (t * (6 * t - 15) + 10)


@dataclass
class Gait:
    name: str
    frames: int                  # frames per cycle (loop: frame 0 == frame `frames`)
    stride: float                # meters travelled per cycle (root motion distance)
    duty: float                  # fraction of the cycle a foot is planted
    offsets: dict                # leg -> phase offset of its footfall (touch-down)
    lift: dict                   # leg -> peak foot lift (m)
    hoof_flex: dict              # leg -> max hoof flexion during swing (deg, toe back/up)
    bob: float                   # vertical body oscillation amplitude (m)
    bob_per_cycle: int           # 2 for symmetric gaits, 1 for gallop
    bob_phase: float             # phase of lowest body point
    pitch: float                 # body pitch oscillation (deg), + = nose down
    pitch_phase: float
    roll: float                  # body roll oscillation (deg)
    sway: float                  # lateral body sway (m)
    head_nod: float              # head/neck nod amplitude (deg)
    head_nod_per_cycle: int
    head_nod_phase: float
    neck_carriage: float = 0.0   # static neck pitch offset (deg), + = head lower
    tail_swing: float = 6.0      # tail lateral swing (deg per segment, grows toward tip)
    tail_lift: float = 0.0       # tail raise (deg), gallop lifts the tail
    shoulder_glide: float = 0.03 # scapula fore/aft glide (m) with the front leg swing
    femur_swing: float = 18.0    # hind femur rotation range (deg) following the hind foot
    spine_flex: float = 0.0      # gallop spine flexion (deg)
    spine_phase: float = 0.25    # phase of zero spine flexion on the way to full flexion (sin(2pi(p - spine_phase)))
    tail_phase: float = 0.0      # phase of the tail base's side swing

    @property
    def seconds(self):
        return self.frames / FPS

    @property
    def speed(self):
        return self.stride / self.seconds


# Calf: withers ~1.0 m, hip height ~0.72 m. Froude numbers v^2/(g*h): walk ~0.14, trot ~0.7, gallop ~2.6.
WALK = Gait("Walk", frames=24, stride=0.74, duty=0.62,
            offsets={"LH": 0.00, "LF": 0.25, "RH": 0.50, "RF": 0.75},   # lateral-sequence 4-beat walk
            lift={"LF": 0.085, "RF": 0.085, "LH": 0.065, "RH": 0.065},
            hoof_flex={"LF": 70, "RF": 70, "LH": 55, "RH": 55},
            bob=0.010, bob_per_cycle=2, bob_phase=0.10, pitch=0.8, pitch_phase=0.0,
            roll=1.6, sway=0.010, head_nod=4.5, head_nod_per_cycle=2, head_nod_phase=0.30,
            neck_carriage=4.0, tail_swing=4.0, shoulder_glide=0.028, femur_swing=16.0)

TROT = Gait("Trot", frames=16, stride=1.25, duty=0.42,
            offsets={"LH": 0.00, "RF": 0.00, "RH": 0.50, "LF": 0.50},   # diagonal pairs
            lift={"LF": 0.13, "RF": 0.13, "LH": 0.11, "RH": 0.11},
            hoof_flex={"LF": 85, "RF": 85, "LH": 70, "RH": 70},
            bob=0.028, bob_per_cycle=2, bob_phase=0.18, pitch=1.2, pitch_phase=0.1,
            roll=1.0, sway=0.004, head_nod=2.5, head_nod_per_cycle=2, head_nod_phase=0.35,
            neck_carriage=0.0, tail_swing=3.0, tail_lift=6.0, shoulder_glide=0.035, femur_swing=22.0)

def rephase(g: Gait, d: float) -> Gait:
    """The same gait with normalized time 0 moved to its old phase d: every phase parameter shifted by -d, so the
    baked clip is the old one started d * frames later (for the root-motion clip, re-anchored at the origin)."""
    return replace(g, offsets={k: (v - d) % 1.0 for k, v in g.offsets.items()},
                   bob_phase=(g.bob_phase - d) % 1.0, pitch_phase=(g.pitch_phase - d) % 1.0,
                   head_nod_phase=(g.head_nod_phase - d) % 1.0, spine_phase=(g.spine_phase - d) % 1.0,
                   tail_phase=(g.tail_phase - d) % 1.0)


# Transverse gallop, right lead: footfalls LH 0, RH .10, LF .42, RF .52 (written relative to the LH touch-down)...
GALLOP = rephase(Gait("Gallop", frames=14, stride=2.05, duty=0.30,
                      offsets={"LH": 0.00, "RH": 0.10, "LF": 0.42, "RF": 0.52},
                      lift={"LF": 0.19, "RF": 0.19, "LH": 0.16, "RH": 0.16},
                      hoof_flex={"LF": 100, "RF": 100, "LH": 80, "RH": 80},
                      bob=0.040, bob_per_cycle=1, bob_phase=0.30, pitch=3.0, pitch_phase=0.30,
                      roll=1.0, sway=0.0, head_nod=10.0, head_nod_per_cycle=1, head_nod_phase=5 / 7,
                      neck_carriage=-20.0, tail_swing=3.0, tail_lift=18.0, shoulder_glide=0.045,
                      femur_swing=30.0, spine_flex=5.0),
                 5 / 7)
# ...then re-phased so that normalized time 0 is the old frame 10 (LH .286, RH .386, LF .706, RF .806). Unity's
# locomotion blend tree mixes Trot_RM and Gallop_RM at the same normalized time; with this phase every hoof of the
# gallop is within ~0.2 cycle of its trot footfall (was up to 0.47), which cut the simulated 50/50 blend's longest
# hoof skate from 42 to ~10 cm (sweep of 28 shifts; review A1). Head carriage (review A11, GiM reference 10.1-10.6 s:
# head held up): neck_carriage -6 -> -20, body bob 0.055 -> 0.040 m, pitch 6 -> 3 deg, head nod 9 -> 10 deg phased
# (0.0 after the re-phase) to steady the head: head joint 0.73-1.00 m (standing 0.87), was 0.58-0.94 m.

# Slow walk (Unity blend-tree child between Stand and Walk, review A4; its 1.2 s cycle is close to the GiM reference walk's
# 41 frames): same lateral sequence as WALK (so the two blend in phase), shorter stride, higher duty, lower steps.
WALK_SLOW = Gait("Walk_Slow", frames=36, stride=0.54, duty=0.68,
                 offsets={"LH": 0.00, "LF": 0.25, "RH": 0.50, "RF": 0.75},
                 lift={"LF": 0.060, "RF": 0.060, "LH": 0.050, "RH": 0.050},
                 hoof_flex={"LF": 60, "RF": 60, "LH": 48, "RH": 48},
                 bob=0.006, bob_per_cycle=2, bob_phase=0.10, pitch=0.5, pitch_phase=0.0,
                 roll=1.4, sway=0.010, head_nod=3.5, head_nod_per_cycle=2, head_nod_phase=0.30,
                 neck_carriage=4.0, tail_swing=3.0, shoulder_glide=0.022, femur_swing=12.0)

# Adult cow (ASSET=cow, tools/asset_profile.py): the clips are authored on a rig of the calf's height and scaled up by
# FINAL_SCALE afterwards (stage E), so strides stay as they are here (they scale with the body). Cycle times follow
# dynamic similarity (equal Froude number): x sqrt(FINAL_SCALE) = 1.19 (Walk 24 -> 29 f, Trot 16 -> 19, Gallop
# 14 -> 17, Walk_Slow 36 -> 43), final speeds Walk_Slow 0.54, Walk 1.09, Trot 2.80, Gallop 5.13 m/s. The heavier
# adult steps a little lower and bounces less.
try:
    import asset_profile as _AP
except ImportError:                         # imported from elsewhere without tools/ on sys.path
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import asset_profile as _AP
if _AP.IS_COW:
    def _adult(g: Gait) -> Gait:
        return replace(g, frames=round(g.frames * _AP.TIME_SCALE), lift={k: v * 0.9 for k, v in g.lift.items()},
                       bob=g.bob * 0.85)
    WALK_SLOW, WALK, TROT, GALLOP = (_adult(g) for g in (WALK_SLOW, WALK, TROT, GALLOP))

GAITS = {g.name: g for g in (WALK_SLOW, WALK, TROT, GALLOP)}


def leg_phase(g: Gait, leg: str, p: float) -> float:
    """phase of `leg` since its own touch-down, in [0,1)"""
    return (p - g.offsets[leg]) % 1.0


def foot_offset(g: Gait, leg: str, p: float):
    """Foot target relative to its rest position, in BODY space (root motion removed):
    returns (dy, dz, flex_deg). Forward is -Y, so a foot ahead of rest has dy < 0.
    Stance: slides linearly from +half (ahead) to -half (behind) = matches body speed exactly.
    Swing: eased return with a lift arc; front feet peak early (knee snaps up), hind a bit later.
    """
    q = leg_phase(g, leg, p)
    half = g.stride * g.duty / 2.0               # stance length / 2 (body-relative sweep)
    front = leg.endswith("F")
    if q < g.duty:                                # stance
        s = q / g.duty
        u = half - 2 * half * s                   # +half -> -half (forward positive)
        # heel roll-off in the last 15% of stance
        flex = -g.hoof_flex[leg] * 0.25 * smooth((s - 0.85) / 0.15)
        return (-u, 0.0, flex)
    s = (q - g.duty) / (1.0 - g.duty)             # swing 0..1
    u = -half + 2 * half * smoother(s)
    peak = 0.40 if front else 0.50
    if s < peak:
        h = math.sin(0.5 * math.pi * s / peak)
    else:
        h = math.cos(0.5 * math.pi * (s - peak) / (1 - peak))
    h = max(0.0, h) ** 1.3
    flex = -g.hoof_flex[leg] * math.sin(math.pi * min(1.0, s / 0.85)) * (1 if s < 0.85 else 0) \
        - g.hoof_flex[leg] * 0.25 * (1 - smooth(s / 0.15))
    return (-u, g.lift[leg] * h, flex)


def body_offset(g: Gait, p: float):
    """(dz, pitch_deg, roll_deg, sway_x) of the body (COG) at cycle phase p."""
    n = g.bob_per_cycle
    dz = -g.bob * math.cos(2 * math.pi * n * (p - g.bob_phase))
    pitch = g.pitch * math.sin(2 * math.pi * (p - g.pitch_phase)) if n == 1 else \
        g.pitch * math.sin(2 * math.pi * 2 * (p - g.pitch_phase))
    # weight shifts toward the side whose hind foot is planted
    roll = g.roll * math.sin(2 * math.pi * (p - g.offsets["LH"] - 0.25))
    sway = g.sway * math.sin(2 * math.pi * (p - g.offsets["LH"] - 0.25))
    return dz, pitch, roll, sway


def head_offset(g: Gait, p: float):
    """(neck_pitch_deg, head_pitch_deg): nod follows the fore footfalls."""
    n = g.head_nod_per_cycle
    nod = g.head_nod * math.sin(2 * math.pi * n * (p - g.head_nod_phase))
    return g.neck_carriage + 0.6 * nod, 0.4 * nod


def shoulder_glide(g: Gait, leg: str, p: float):
    """scapula fore/aft glide for front legs (m, forward negative Y), follows the foot sweep"""
    dy, _, _ = foot_offset(g, leg, p)
    half = g.stride * g.duty / 2.0
    return g.shoulder_glide * (dy / half if half else 0.0)


def femur_angle(g: Gait, leg: str, p: float):
    """hind femur swing (deg, + = foot forward) proportional to the hind foot sweep"""
    dy, dz, _ = foot_offset(g, leg, p)
    half = g.stride * g.duty / 2.0
    return g.femur_swing * (-dy / half if half else 0.0) * 0.5 + 12.0 * (dz / max(1e-6, g.lift[leg])) * 0.5


def tail_offset(g: Gait, p: float, segment: int):
    """(side_deg, lift_deg) for tail segment 1..7: a travelling wave with lag toward the tip"""
    lag = 0.07 * segment
    side = g.tail_swing * (0.4 + 0.15 * segment) * math.sin(2 * math.pi * (p - g.tail_phase - lag))
    lift = g.tail_lift * (1.0 - 0.1 * segment)
    return side, lift


# ------------------------------------------------------------------------------------------
if __name__ == "__main__":
    # self-test: in root-motion space a planted foot must not move (no foot sliding by design)
    for g in GAITS.values():
        worst = 0.0
        for leg in LEGS:
            planted = None
            for f in range(g.frames + 1):
                p = f / g.frames
                dy, dz, _ = foot_offset(g, leg, p)
                world_y = dy - g.speed * (f / FPS)          # root moves -Y at `speed`
                if leg_phase(g, leg, p) < g.duty and dz == 0.0:
                    if planted is None:
                        planted = world_y
                    worst = max(worst, abs(world_y - planted))
                else:
                    planted = None
        # loop continuity
        cont = max(abs(foot_offset(g, l, 0.0)[i] - foot_offset(g, l, 1.0)[i]) for l in LEGS for i in range(3))
        print(f"{g.name:7s} speed {g.speed:4.2f} m/s  cycle {g.seconds:.3f}s  stance sweep {g.stride*g.duty:.2f} m  "
              f"max planted slide {worst*1000:.2f} mm  loop discontinuity {cont:.2e}")
