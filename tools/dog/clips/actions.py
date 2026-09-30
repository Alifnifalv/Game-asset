"""One-shot actions: Jump (leap forward, root motion 1.6 m), Attack (lunge and bite), PlayBow, Death (falls onto its
right side; ends lying still, root under the carcass).

Paw tracks of the Jump are given in the WORLD frame while planted and in the root frame while airborne
(LegTrack), so planted paws do not slide while the root moves.

  python3 tools/dog/clips/actions.py --in build/dog/stage_b.blend [--out-dir <scratch>]
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import bpy  # noqa: F401
from mathutils import Vector
import dog_anim as D
import _common as C

TAU = 2 * math.pi


def keyed(keys, f):
    """keys [(frame, value)], value float or tuple/Vector; smootherstep between keys"""
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, a), (f1, b) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            e = D.smoother((f - f0) / (f1 - f0)) if f1 > f0 else 1.0
            if isinstance(a, Vector):
                return a.lerp(b, e)
            if isinstance(a, tuple):
                return tuple(D.lerp(x, y, e) for x, y in zip(a, b))
            return D.lerp(a, b, e)
    return keys[-1][1]


class LegTrack:
    """keys: (frame, 'w'|'r', Vector position, pastern, toe); 'w' = world (planted), 'r' = relative to the body
    (root + body offset: airborne paws follow the body's arc). Blended in the world frame."""

    def __init__(self, keys, root_fn, body_fn=None):
        """body_fn(f) -> 4x4 body transform in the root frame (offset + rotation about the COG)"""
        self.keys, self.root_fn = keys, root_fn
        self.body_fn = body_fn

    def rel(self, p, f):
        q = (self.body_fn(f) @ p) if self.body_fn else p
        return q + self.root_fn(f)

    def world(self, i):
        f, mode, p, _, _ = self.keys[i]
        return p.copy() if mode == "w" else self.rel(p, f)

    def at(self, f):
        K = self.keys
        if f <= K[0][0]:
            i0 = i1 = 0; e = 0.0
        elif f >= K[-1][0]:
            i0 = i1 = len(K) - 1; e = 0.0
        else:
            i0 = max(i for i in range(len(K)) if K[i][0] <= f); i1 = min(i0 + 1, len(K) - 1)
            e = D.smoother((f - K[i0][0]) / (K[i1][0] - K[i0][0])) if i1 != i0 else 0.0
        if K[i0][1] == "r" and K[i1][1] == "r":       # airborne span: blend relative to the body
            p = self.rel(K[i0][2].lerp(K[i1][2], e), f)
        else:
            p = self.world(i0).lerp(self.world(i1), e)
        past = D.lerp(K[i0][3], K[i1][3], e); toe = D.lerp(K[i0][4], K[i1][4], e)
        return p - self.root_fn(f), past, toe


# ----------------------------------------------------------------------------------------------- Jump
JUMP_N, JUMP_D = 44, 1.60


def jump_root(f):
    # the root follows the body over the ground: still during the crouch, then a smooth ramp to JUMP_D
    return Vector((0, -JUMP_D * D.smoother((f - 10) / (37 - 10)), 0))


# take-off / landing frames per leg (the right side a frame later: the paws never move as a perfect pair)
TAKEOFF = {"FL": 11, "FR": 12, "HL": 14, "HR": 15}
LAND = {"FL": 30, "FR": 31, "HL": 34, "HR": 35}
SETTLE = {"FL": (37, 42), "FR": (38, 43), "HL": (38, 43), "HR": (39, 44)}


def jump_body(f):
    return Vector((0, keyed([(0, 0.0), (9, 0.03), (15, -0.02), (27, 0.0), (33, -0.02), (44, 0.0)], f),
                   keyed([(0, 0.0), (9, -0.085), (13, -0.03), (15, 0.03), (20, 0.16), (24, 0.20), (28, 0.10),
                          (31, 0.0), (33, -0.05), (38, -0.02), (44, 0.0)], f)))



def jump_pitch(f):
    return keyed([(0, 0.0), (9, 5.0), (14, -13.0), (19, -10.0), (24, 0.0), (29, 11.0), (33, 7.0), (38, -2.0),
                  (44, 0.0)], f)


def jump_body_matrix(f):
    return D.T(jump_body(f)) @ D.T(D.COG) @ D.body_matrix(jump_pitch(f), 0, 0) @ D.T(-D.COG)


def jump(f, N=JUMP_N):
    R = C.rest_mcp
    P = D.Pose()
    root = jump_root(f)
    P.root_pos = root
    # body: crouch, extend up, flight arc, landing absorb (root frame)
    P.body_off = jump_body(f)
    P.body_rot = (jump_pitch(f), 0.0, 0.0)
    fl = keyed([(0, 0.0), (9, 3.0), (15, -1.5), (21, 3.0), (27, -2.0), (33, 3.0), (44, 0.0)], f)
    P.spine = {"Spine1": (fl, 0, 0), "Spine2": (fl * 0.8, 0, 0), "Spine3": (fl * 0.5, 0, 0)}
    hp = keyed([(0, 0.0), (9, 14.0), (15, -12.0), (24, 4.0), (30, -6.0), (36, 4.0), (44, 0.0)], f)
    C.look(P, pitch=hp)
    P.tail = D.tail_shape(lift=keyed([(0, 0.0), (12, 20.0), (22, 45.0), (30, 30.0), (44, 0.0)], f), curl=10)
    P.ears = {s: (keyed([(0, 0.0), (9, 20.0), (20, 35.0), (30, -10.0), (36, 12.0), (44, 0.0)], f), 0, 0) for s in "LR"}
    P.jaw = keyed([(0, 0.0), (14, 6.0), (28, 10.0), (40, 0.0)], f)
    end = Vector((0, -JUMP_D, 0))
    for k in D.LEGS:
        r = R(k)
        to, la = TAKEOFF[k], LAND[k]
        s0, s1 = SETTLE[k]
        land_w = r + jump_root(la) + Vector((0, -0.05 if k[0] == "F" else -0.03, 0))
        if k[0] == "F":
            keys = [(0, "w", r, 0, 0), (to - 6, "w", r, 0, 0), (to - 2, "w", D.rolled_mcp(k, r, 10), 4, 10),
                    (to, "w", D.rolled_mcp(k, r, 30), 18, 30),
                    (to + 2, "r", r + Vector((0, 0.05, 0.03)), 60, 30),
                    (to + 5, "r", r + Vector((0, 0.03, 0.10)), 115, 20),
                    (24, "r", r + Vector((0, -0.12, 0.16)), 90, 10),
                    (la - 3, "r", r + Vector((0, -0.08, 0.02)), -6, -5),
                    (la, "w", land_w, -6, 0), (s0, "w", land_w, 0, 0), (s1, "w", r + end, 0, 0)]
        else:
            keys = [(0, "w", r, 0, 0), (to - 6, "w", r, 0, 0), (to - 3, "w", D.rolled_mcp(k, r, 12), 10, 12),
                    (to, "w", D.rolled_mcp(k, r, 40), 30, 40),
                    (to + 4, "r", r + Vector((0, 0.16, 0.10)), 20, 30),
                    (26, "r", r + Vector((0, -0.02, 0.18)), -40, 10),
                    (la - 2, "r", r + Vector((0, -0.04, 0.05)), -5, 0),
                    (la, "w", land_w, 0, 0), (s0, "w", land_w, 0, 0), (s1, "w", r + end, 0, 0)]
        mcp, past, toe = LegTrack(keys, jump_root, jump_body_matrix).at(f)
        if s0 < f < s1:            # the settling step is lifted
            u = (f - s0) / (s1 - s0)
            mcp = mcp + Vector((0, 0, 0.035 * math.sin(math.pi * u)))
            past += (30 if k[0] == "F" else 0) * math.sin(math.pi * u)
        P.legs[k] = D.LegPose(mcp, pastern=past, toe=toe)
    return P


# ----------------------------------------------------------------------------------------------- Attack
def attack(f, N=34):
    P = C.timeline([(0, C.stand()), (7, _attack_crouch()), (13, _attack_lunge()), (18, _attack_lunge()),
                    (26, _attack_crouch()), (N, C.stand())], f)
    # jaw: opens on the lunge, snaps shut at f14, then the head shakes the grip
    P.jaw += keyed([(0, 0.0), (7, 6.0), (11, 42.0), (13, 44.0), (15, 4.0), (24, 6.0), (30, 0.0), (34, 0.0)], f)
    P.nose += keyed([(0, 0.0), (7, 6.0), (13, 8.0), (26, 6.0), (34, 0.0)], f)
    if 15 <= f <= 24:
        C.look(P, roll=16 * math.sin(TAU * (f - 15) / 5), yaw=8 * math.sin(TAU * (f - 15) / 5))
    return P


def _attack_crouch():
    P = C.growl_pose()
    P.body_off = P.body_off + Vector((0, 0.03, -0.03))
    return P


def _attack_lunge():
    P = C.growl_pose()
    P.body_off = Vector((0, -0.13, 0.02))
    P.body_rot = (-4, 0, 0)
    C.look(P, pitch=-8)
    P.legs["FL"] = C.leg("FL", dy=-0.16); P.legs["FR"] = C.leg("FR", dy=-0.16)
    P.tail = D.tail_shape(lift=40, curl=80)
    return P


# ----------------------------------------------------------------------------------------------- PlayBow
def _bow():
    P = D.Pose()
    P.body_rot = (30, 0, 0)
    P.body_off = Vector((0, -0.02, -0.13))
    P.spine = {"Spine1": (-4, 0, 0), "Spine2": (-3, 0, 0), "Spine3": (2, 0, 0)}
    P.neck = {"Neck1": (2, 0, 0), "Neck2": (2, 0, 0)}          # (8, 6) on the old head carriage (_common)
    P.head = (-14, 0, 0)
    P.legs["FL"] = D.LegPose(C.rest_mcp("FL") + Vector((0, -0.26, 0)), pastern=-60, toe=0, scap=-5)
    P.legs["FR"] = D.LegPose(C.rest_mcp("FR") + Vector((0, -0.26, 0)), pastern=-60, toe=0, scap=-5)
    P.tail = D.tail_shape(lift=40, curl=70)
    P.ears = {"L": (-12, 0, 0), "R": (-12, 0, 0)}
    P.jaw = 16; P.tongue = (0.02, 25, 0)
    return P


def playbow(f, N=64):
    P = C.timeline([(0, C.stand()), (12, _bow()), (50, _bow()), (N, C.stand())], f)
    w = D.smooth(f / 10) * (1 - D.smooth((f - 52) / 10))
    C.wag(P, f / N, amp=26 * w, rate=6)
    P.body_rot = (P.body_rot[0], P.body_rot[1] + 3 * w * math.sin(TAU * 4 * f / N), P.body_rot[2])
    return P


# ----------------------------------------------------------------------------------------------- Death
def _dead():
    """lying on the right side, legs limp and stacked, head on the ground"""
    P = D.Pose()
    P.root_pos = Vector((0, 0, 0))
    P.body_rot = (0, 86, 0)
    P.body_off = Vector((0.33, 0.0, -0.300))
    P.spine = {"Spine1": (0, 4, 0), "Spine2": (0, 3, 0), "Spine3": (0, 2, 0)}
    P.neck = {"Neck1": (0, -8, -6), "Neck2": (-4, -6, -10)}
    P.head = (6, 0, -18)
    P.jaw = 8; P.tongue = (0.03, 55, 10)
    P.ears = {"L": (30, 0, 0), "R": (-20, 0, 0)}
    # legs limp toward +X (world), the lower (right) legs on the ground, the upper ones resting on them
    for k, dy, dz, past in (("FR", -0.30, 0.060, -25), ("FL", -0.26, 0.140, -35),
                            ("HR", 0.40, 0.060, -15), ("HL", 0.34, 0.145, -25)):
        P.legs[k] = D.LegPose(Vector((0.66, dy, dz)), pastern=past, toe=25, local=1.0)
    P.tail = D.tail_shape(side=-25, curl=-20)
    return P


DEATH_REL = {"FL": Vector((0.02, -0.04, 0.11)), "FR": Vector((-0.01, -0.06, 0.08)),     # bent, relaxed legs in the
             "HL": Vector((0.02, 0.07, 0.10)), "HR": Vector((-0.01, 0.09, 0.07))}       # body frame (from rest)
DEATH_PASTERN = {"FL": 35, "FR": 25, "HL": -30, "HR": -20}


def death(f, N=80):
    """Stagger, the legs buckle, the body rolls onto its right side and lies still.  The body is keyed; the paws go
    from their planted stance (ground frame) to relaxed bent legs carried by the body (body frame), so they rotate
    with the body instead of sweeping under it, and never go below the ground."""
    stagger = D.Pose()
    stagger.body_off = Vector((0.02, 0.01, -0.06)); stagger.body_rot = (3, -8, 0)
    C.look(stagger, pitch=18, roll=-10)
    stagger.tail = D.tail_shape(lift=-15)
    buckle = D.Pose()
    buckle.body_off = Vector((0.10, 0.0, -0.20)); buckle.body_rot = (10, 38, 0)
    C.look(buckle, pitch=22, roll=-25)
    buckle.tail = D.tail_shape(side=-10)
    impact = _dead()
    impact.body_off = impact.body_off + Vector((0, 0, -0.012))
    settle = _dead()
    P = C.timeline([(0, C.stand()), (12, stagger), (28, buckle), (40, impact), (46, settle), (N, settle)], f,
                   lift=0.0)
    Mb = D.T(P.body_off) @ D.T(D.COG) @ D.body_matrix(*P.body_rot) @ D.T(-D.COG)
    w = D.smoother((f - 10) / (36 - 10))
    for k in D.LEGS:
        r = C.rest_mcp(k)
        carried = Mb @ (r + DEATH_REL[k])
        m = r.lerp(carried, w)
        # the legs on the down side slide out (fore forward, hind back) while the body falls onto them, so the
        # chain never folds flat under its own shoulder / hip
        if 14 <= f <= 38:
            bump = math.sin(math.pi * (f - 14) / 24)
            m = m + Vector((0, {"FR": -0.14, "FL": -0.06, "HR": 0.10, "HL": 0.05}[k] * bump, 0))
        m.z = max(m.z, 0.036 + 0.02 * w)
        P.legs[k] = D.LegPose(m, pastern=DEATH_PASTERN[k] * w, toe=20 * w, local=w)
    return P


CLIPS = [
    ("Jump", JUMP_N, jump, False),
    ("Attack", 34, attack, False),
    ("PlayBow", 64, playbow, False),
    ("Death", 80, death, False),
]


def build(rig):
    names = []
    for name, N, fn, loop in CLIPS:
        rig.make_clip(name, N, lambda f, fn=fn, N=N: fn(f, N), loop=loop, reach=(name != "Death"))
        names.append(name)
    return names


def planted_fn(name):
    if name == "Jump":
        return lambda leg, f: f <= TAKEOFF[leg] - 6 or LAND[leg] <= f <= SETTLE[leg][0]
    return None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
                                                             "build", "dog", "stage_b.blend"))
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.inp))
    rig = D.DogRig()
    for name, N, fn, loop in CLIPS:
        act = rig.make_clip(name, N, lambda f, fn=fn, N=N: fn(f, N), loop=loop, reach=(name != "Death"))
        D.qa_clip(rig, act, planted_fn=planted_fn(name))
        print(f"   body drop (reach pass) max {act['dog_body_drop_mm']:.1f} mm")
    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(a.out_dir), "actions.blend"))
