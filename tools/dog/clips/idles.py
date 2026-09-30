"""Standing idles and social clips: Idle, Idle_Pant, Idle_LookAround, Idle_Sniff, Bark, Growl, Eat.

Loops start and end on their own base pose (Idle / Idle_Pant / Idle_LookAround on the rest pose = Pose(), so they
blend with the gaits); Bark is a one-shot from and back to the rest pose.

  python3 tools/dog/clips/idles.py --in build/dog/stage_b.blend [--out-dir <scratch>]
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import bpy  # noqa: F401
from mathutils import Vector
import dog_anim as D
import _common as C

TAU = 2 * math.pi


def idle(f, N=120):
    t = f / N
    P = C.stand()
    C.breathe(P, t, 1.0, rate=3)
    # slow weight shift and a small head drift
    P.body_off = P.body_off + Vector((0.004 * math.sin(TAU * t), 0, 0))
    P.body_rot = (0, 0.8 * math.sin(TAU * t), 0)
    C.look(P, pitch=2 * math.sin(TAU * t + 0.5), yaw=6 * math.sin(TAU * t))
    # ear twitch at 70 %, tail slow sway
    tw = max(0.0, math.sin(TAU * (t - 0.68) * 6)) if 0.68 < t < 0.68 + 1 / 12 else 0.0
    C.ears(P, (-10 * tw, 0, 0))
    C.wag(P, t, amp=6, rate=1)
    return P


def idle_pant(f, N=60):
    t = f / N
    P = C.stand()
    C.look(P, pitch=12)                 # head lowered, muzzle down (GiM video 21.5)
    C.pant(P, t, rate=8)
    C.wag(P, t, amp=10, rate=2)
    C.ears(P, (6, 0, 0))
    return P


def idle_lookaround(f, N=150):
    t = f / N
    P = C.stand()
    C.breathe(P, t, 1.0, rate=4)
    keys = [(0.0, 0, 0, 0), (0.15, 0, 0, 0), (0.30, -6, 55, 8), (0.45, -6, 55, 8), (0.62, -2, -48, -6),
            (0.78, -2, -48, -6), (0.92, 0, 0, 0), (1.0, 0, 0, 0)]
    for (t0, p0, y0, r0), (t1, p1, y1, r1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            e = D.smoother((t - t0) / (t1 - t0)) if t1 > t0 else 0
            C.look(P, pitch=D.lerp(p0, p1, e), yaw=D.lerp(y0, y1, e), roll=D.lerp(r0, r1, e))
            alert = abs(D.lerp(y0, y1, e)) / 55
            C.ears(P, (-14 * alert, 0, 0))
            P.body_rot = (0, 0, D.lerp(y0, y1, e) * 0.06)
            break
    C.wag(P, t, amp=5, rate=1)
    return P


def idle_sniff(f, N=60):
    t = f / N
    P = C.sniff_pose()
    P.nose = 4 * max(0.0, math.sin(TAU * 6 * t))
    C.look(P, yaw=10 * math.sin(TAU * t))
    P.body_off = P.body_off + Vector((0, 0, 0.002 * math.sin(TAU * 6 * t)))
    C.wag(P, t, amp=8, rate=2)
    return P


def idle_sniff_clip(f, N=60):
    """loop in the sniff pose; the blend in/out from Idle is done by the Animator transition"""
    return idle_sniff(f, N)


def bark_clip(f, N=40):
    """two barks: lean in, head up-forward, jaw snaps; one-shot from/to the rest pose"""
    base = C.stand()
    lean = D.Pose()
    lean.body_off = Vector((0, -0.025, -0.015)); lean.body_rot = (2, 0, 0)
    lean.legs["FL"] = C.leg("FL"); lean.legs["FR"] = C.leg("FR")
    lean.neck = {"Neck1": (-6, 0, 0), "Neck2": (-4, 0, 0)}     # the head-carriage compensation (_common)
    C.look(lean, pitch=-2)
    lean.tail = D.tail_shape(lift=35, curl=80)
    lean.ears = {"L": (12, 0, 0), "R": (12, 0, 0)}
    P = C.timeline([(0, base), (8, lean), (32, lean), (40, base)], f)
    # bark pulses at f 10 and 21: jaw snaps open over 3 frames, closes over 5; head/chest jolt
    for fb in (10, 21):
        d = f - fb
        if 0 <= d < 9:
            o = math.sin(math.pi * min(d / 3, 1) / 2) if d < 3 else 1 - D.smooth((d - 3) / 6)
            P.jaw += 34 * o
            P.nose += 3 * o
            C.look(P, pitch=2 * o)
            P.body_off = P.body_off + Vector((0, -0.006 * o, 0.004 * o))
            sp = dict(P.spine); a, b, c = sp["Spine3"]; sp["Spine3"] = (a + 2 * o, b, c); P.spine = sp
    return P


def growl(f, N=60):
    t = f / N
    P = C.growl_pose()
    # rumbling: small fast vibration of the chest + lips twitching
    v = math.sin(TAU * 10 * t)
    P.body_off = P.body_off + Vector((0, 0, 0.0015 * v))
    P.jaw += 2.5 * math.sin(TAU * 3 * t)
    P.nose += 1.5 * max(0.0, v)
    C.look(P, yaw=4 * math.sin(TAU * t))
    return P


def eat(f, N=60):
    t = f / N
    P = C.sniff_pose()
    C.look(P, pitch=6)
    # chewing: jaw open/close twice a second, head bobs
    chew = 0.5 - 0.5 * math.cos(TAU * 4 * t)
    P.jaw += 14 * chew
    C.look(P, pitch=-4 * chew, roll=3 * math.sin(TAU * 2 * t))
    P.ears = {"L": (5, 0, 0), "R": (5, 0, 0)}
    return P


CLIPS = [
    ("Idle", 120, idle, True),
    ("Idle_Pant", 60, idle_pant, True),
    ("Idle_LookAround", 150, idle_lookaround, True),
    ("Idle_Sniff", 60, idle_sniff_clip, True),
    ("Bark", 40, bark_clip, False),
    ("Growl", 60, growl, True),
    ("Eat", 60, eat, True),
]


def build(rig):
    names = []
    for name, N, fn, loop in CLIPS:
        rig.make_clip(name, N, lambda f, fn=fn, N=N: fn(f, N), loop=loop)
        names.append(name)
    return names


def planted_fn(name):
    return lambda leg, f: True        # every idle keeps all four paws down (steps are blended by the timeline)


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
        act = rig.make_clip(name, N, lambda f, fn=fn, N=N: fn(f, N), loop=loop)
        D.qa_clip(rig, act, planted_fn=planted_fn(name))
    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(a.out_dir), "idles.blend"))
