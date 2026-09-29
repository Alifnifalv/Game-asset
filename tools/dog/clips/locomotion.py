"""Rottweiler gaits: Walk_Slow (sniffing walk), Walk, Trot, Gallop, each in place and with root motion (_RM).

One gait generator (gait_pose) for all of them.  Per leg: a touch-down phase, a duty factor (stance share of the
cycle) and a stride; in stance the paw is planted (it moves backward in the root frame at the body speed, so with root
motion it stays still in the world) and rolls off over the toe tips at the end; in swing it travels forward on a
minimum-jerk path with a lift, while the carpus (front) / hock (hind) folds.  Body: bob, pitch, roll, spine side bend
(walk) or flexion/extension (gallop), head and tail motion; everything periodic in the cycle, so the clips loop exactly.

  python3 tools/dog/clips/locomotion.py --in build/dog/stage_b.blend [--out-dir <scratch>] [--render]
"""
import math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bpy                      # noqa: F401  (mathutils comes with bpy)
from mathutils import Vector
import dog_anim as D

TAU = 2 * math.pi

# name: speed m/s, frames per cycle, touch-down phase per leg, duty (front, hind), swing lift (front, hind) m,
#       carpus fold deg, hock fold deg, toe roll deg, body bob m, body pitch deg, roll deg, spine side bend deg,
#       spine flex deg (gallop), head bob deg, head pitch deg (neck carriage), tail lift deg, tail wag deg,
#       tail curl deg (the sickle carriage)
GAITS = {
    "Walk_Slow": dict(v=0.55, N=34, td=dict(HL=0.0, FL=0.22, HR=0.5, FR=0.72), duty=(0.70, 0.70), lift=(0.055, 0.045),
                      carpus=80, hock=30, roll_off=28, bob=0.006, pitch=0.6, roll=1.2, side=3.0, flex=0.0,
                      head_bob=1.5, neck=(22, 18), tail=(30, 6), curl=55, sniff=True),
    "Walk": dict(v=1.15, N=20, td=dict(HL=0.0, FL=0.22, HR=0.5, FR=0.72), duty=(0.60, 0.62), lift=(0.070, 0.055),
                 carpus=90, hock=35, roll_off=32, bob=0.008, pitch=0.8, roll=1.5, side=3.5, flex=0.0,
                 head_bob=2.5, neck=(0, 0), tail=(32, 10), curl=58, sniff=False),
    "Trot": dict(v=2.5, N=16, td=dict(FL=0.0, HR=0.0, FR=0.5, HL=0.5), duty=(0.42, 0.42), lift=(0.090, 0.075),
                 carpus=110, hock=45, roll_off=38, bob=0.016, pitch=0.8, roll=0.8, side=1.0, flex=0.0,
                 head_bob=2.0, neck=(4, 2), tail=(35, 8), curl=65, sniff=False),
    # rotary gallop, right fore lead: RH, LH, LF, RF
    "Gallop": dict(v=6.5, N=12, td=dict(HR=0.0, HL=0.10, FL=0.40, FR=0.50), duty=(0.26, 0.26), lift=(0.13, 0.11),
                   carpus=125, hock=60, roll_off=45, bob=0.030, pitch=7.0, roll=1.0, side=0.0, flex=9.0,
                   head_bob=6.0, neck=(8, 4), tail=(40, 6), curl=45, sniff=False),
}
# stance centre per leg relative to the rest paw (m, + = back): the fore paws land a bit ahead of the shoulder
CENTRE = {"FL": 0.030, "FR": 0.030, "HL": -0.030, "HR": -0.030}


HIND_FOLLOW = 0.6      # share of the hind leg's sweep angle taken by the metatarsus in stance


def sweep_deg(rig, leg, mcp):
    """angle (deg, + = paw behind) of the hip -> paw line against the rest pose, in the root frame"""
    I = rig.leg[leg]
    S = I["S"]
    a_now = math.atan2(mcp.y - S.y, S.z - mcp.z)
    a_rest = math.atan2(I["M"].y - S.y, S.z - I["M"].z)
    return math.degrees(a_now - a_rest)


def stride(g):
    return g["v"] * g["N"] / D.FPS


def leg_phase(g, leg, f):
    """(in_stance, u) with u in [0, 1) the stance or swing progress of `leg` at frame f."""
    duty = g["duty"][0 if leg[0] == "F" else 1]
    p = ((f / g["N"]) - g["td"][leg]) % 1.0
    if p < duty:
        return True, p / duty
    return False, (p - duty) / (1 - duty)


def planted(g, leg, f):
    st, u = leg_phase(g, leg, f)
    return st and u < 0.62


def leg_target(rig, g, leg, f):
    front = leg[0] == "F"
    duty = g["duty"][0 if front else 1]
    travel = stride(g) * duty                      # paw travel relative to the body during stance
    I = rig.leg[leg]
    M0 = I["M"].copy(); E0 = I["E"].copy()
    y0 = M0.y + CENTRE[leg]
    st, u = leg_phase(g, leg, f)
    roll_max = g["roll_off"]
    lift = g["lift"][0 if front else 1]
    fold = g["carpus"] if front else -g["hock"]      # the carpus folds the paw back, the hock swings it forward
    # toe-tip pivot for the roll-off (rest geometry): the paw rotates about it
    pivot_off = (E0 - M0)
    if st:
        y = y0 - travel / 2 + travel * u
        r = D.smooth((u - 0.62) / 0.38) * roll_max
        base = Vector((M0.x, y, M0.z))
        tip = base + pivot_off
        # rotate the MCP about the tip by r (tip down = heel up): axis +X
        rel = base - tip
        c, s = math.cos(math.radians(r)), math.sin(math.radians(r))
        rel = Vector((rel.x, rel.y * c - rel.z * s, rel.y * s + rel.z * c))
        mcp = tip + rel
        # loaded mid-stance: the pastern extends a little (carpus sinks)
        if front:     # lands slightly extended, sinks under load, then follows part of the roll-off
            past = D.lerp(-7.0, 0.0, u) - 5.0 * math.sin(math.pi * u) + r * 0.55
        else:         # the metatarsus follows the leg's sweep (the hock angle stays open, never past straight)
            past = -3.0 * math.sin(math.pi * u) + r * 0.30 + HIND_FOLLOW * sweep_deg(rig, leg, mcp)
        return D.LegPose(mcp, pastern=past, toe=r, planted=u < 0.62)
    # swing
    w = u
    y = y0 + travel / 2 - travel * D.smoother(w)
    # lift profile: early peak for the fore legs (the paw folds up), later/lower for the hind
    peak = 0.40 if front else 0.48
    zl = lift * (math.sin(math.pi * min(w / (2 * peak), 0.5)) if w < peak else
                 math.cos(0.5 * math.pi * (w - peak) / (1 - peak)))
    # height of the rolled-off paw at lift-off, fading out
    rel = -pivot_off
    c, s = math.cos(math.radians(roll_max)), math.sin(math.radians(roll_max))
    z_roll = (rel.y * s + rel.z * c) - rel.z
    zr = z_roll * (1 - D.smooth(w / 0.35))
    mcp = Vector((M0.x, y, M0.z + zl + zr))
    # carpus / hock fold: 0 at lift-off (continuous with the roll-off pastern) -> peak -> slight extension -> 0
    past0 = roll_max * 0.55 if front else (roll_max * 0.30 + HIND_FOLLOW * sweep_deg(rig, leg, Vector((M0.x, y0 + travel / 2, M0.z))))
    land = -7.0 if front else 0.0
    fp = 0.35 if front else 0.42
    if w < fp:
        past = D.lerp(past0, fold, D.smooth(w / fp))
    elif w < 0.88:
        past = D.lerp(fold, -9.0 if front else 4.0, D.smooth((w - fp) / (0.88 - fp)))
    else:
        past = D.lerp(-9.0 if front else 4.0, land, D.smooth((w - 0.88) / 0.12))
    if w < 0.5:
        toe = D.lerp(roll_max, 12.0, D.smooth(w / 0.5))
    elif w < 0.9:
        toe = D.lerp(12.0, -8.0, D.smooth((w - 0.5) / 0.4))
    else:
        toe = D.lerp(-8.0, 0.0, D.smooth((w - 0.9) / 0.1))
    if not front:     # reaching forward before touch-down, the metatarsus slants forward with the leg
        past += HIND_FOLLOW * min(0.0, sweep_deg(rig, leg, mcp)) * D.smooth((w - 0.5) / 0.5)
    return D.LegPose(mcp, pastern=past, toe=toe)


def gait_pose(rig, name, f, root_motion=False):
    g = GAITS[name]
    N = g["N"]
    t = (f % N) / N
    P = D.Pose()
    for leg in D.LEGS:
        P.legs[leg] = leg_target(rig, g, leg, f)
    # body: two bobs per cycle (walk / trot), one big rocking wave (gallop)
    if name == "Gallop":
        ph = TAU * t
        P.body_off = Vector((0, 0, g["bob"] * math.sin(ph - 0.8) - 0.012))
        P.body_rot = (g["pitch"] * math.sin(ph + 0.6), g["roll"] * math.sin(ph), 0.0)
        fl = g["flex"] * math.sin(ph + 1.2)             # + = back arched (flexed, gathered)
        P.spine = {"Spine1": (-fl, 0, 0), "Spine2": (-fl * 0.8, 0, 0), "Spine3": (-fl * 0.4, 0, 0)}
        hp = g["head_bob"] * math.sin(ph + 2.2)
        P.neck = {"Neck1": (g["neck"][0] + hp * 0.4, 0, 0), "Neck2": (g["neck"][1] + hp * 0.3, 0, 0)}
        P.head = (-hp * 0.3, 0, 0)
    else:
        ph2 = 2 * TAU * t
        P.body_off = Vector((0, 0, -g["bob"] * math.cos(ph2 - TAU * g["td"]["HL"] * 2)))
        # roll toward the stance side of the hind legs; side bend with the fore/hind pairs
        P.body_rot = (g["pitch"] * math.sin(ph2), g["roll"] * math.sin(TAU * t), 0.0)
        sb = g["side"] * math.sin(TAU * t + 0.4)
        P.spine = {"Spine1": (0, sb, 0), "Spine2": (0, -sb * 0.3, 0), "Spine3": (0, -sb * 0.7, 0)}
        hb = g["head_bob"] * math.sin(ph2 + 1.0)
        P.neck = {"Neck1": (g["neck"][0] + hb * 0.5, sb * 0.6, 0), "Neck2": (g["neck"][1] + hb * 0.5, sb * 0.4, 0)}
        P.head = (-hb * 0.6, sb * 0.3, 0)
        if g.get("sniff"):
            # nose to the ground, sniffing left and right
            P.head = (P.head[0] + 12, 8 * math.sin(TAU * t), 0)
            P.nose = 3.0 * max(0.0, math.sin(4 * TAU * t))
    # tail: lifted, swinging with the gait
    P.tail = D.tail_shape(lift=g["tail"][0], curl=g.get("curl", 10), wag=g["tail"][1] * math.sin(TAU * t + 1.0))
    # ears bounce
    eb = 6 * math.sin(2 * TAU * t + 2.0) if name != "Gallop" else 14 * math.sin(TAU * t + 2.5) + 10
    P.ears = {"L": (eb, 0, 0), "R": (eb, 0, 0)}
    P.ear_tip = {"L": eb * 0.6, "R": eb * 0.6}
    if name in ("Trot", "Gallop"):
        P.jaw = 8 if name == "Trot" else 16                  # mouth a little open (panting)
        P.tongue = (0.012, 10, 0) if name == "Gallop" else (0.0, 0, 0)
    if root_motion:
        P.root_pos = Vector((0, -g["v"] * f / D.FPS, 0))
    return P


def build(rig):
    names = []
    for name, g in GAITS.items():
        N = g["N"]
        for rm in (False, True):
            clip = name + ("_RM" if rm else "")
            rig.make_clip(clip, N, lambda f, n=name, r=rm: gait_pose(rig, n, f, r), loop=True)
            names.append(clip)
    return names


def planted_fn(name):
    """only the root-motion gaits keep planted paws still in the world (in place, the paws move with the ground)"""
    if not name.endswith("_RM"):
        return None
    g = GAITS[name.replace("_RM", "")]
    return lambda leg, f: planted(g, leg, f)


if __name__ == "__main__":
    import argparse, bpy
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(os.path.dirname(os.path.dirname(HERE)), "..", "build",
                                                             "dog", "stage_b.blend"))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--only", default=None)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.inp))
    rig = D.DogRig()
    for name in GAITS:
        if a.only and name not in a.only.split(","):
            continue
        for rm in (False, True):
            clip = name + ("_RM" if rm else "")
            act = rig.make_clip(clip, GAITS[name]["N"], lambda f, n=name, r=rm: gait_pose(rig, n, f, r), loop=True)
            D.qa_clip(rig, act, planted_fn=planted_fn(clip) if rm else None)
            print(f"   body drop (reach pass) max {act['dog_body_drop_mm']:.1f} mm")
    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(a.out_dir), "locomotion.blend"))
