"""Sitting and lying: Sit_Start, Sit_Idle, Sit_End, Lie_Start, Lying_Idle, Lie_End.

Start clips go from the rest pose (Pose()) to the held pose, End clips back; the idles loop on the held pose, so
Start -> Idle -> End chain without a pop (checked by the BOUNDARY lines of the QA).  The hind paws step forward
under the body when sitting (the timeline lifts them on an arc); lying goes through the sit and walks the fore paws
forward.

  python3 tools/dog/clips/sit_lie.py --in build/dog/stage_b.blend [--out-dir <scratch>]
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import bpy  # noqa: F401
from mathutils import Vector
import dog_anim as D
import _common as C

TAU = 2 * math.pi


def _crouch_mid():
    """half-way into the sit: the rump goes down and back first, the hind paws have not moved yet"""
    P = D.blend(C.stand(), C.sit_pose(), 0.45)
    for k in ("HL", "HR"):
        P.legs[k] = C.stand().legs[k]
        P.legs[k].pastern = 25
    return P


def sit_start(f, N=36):
    return C.timeline([(0, C.stand()), (14, _crouch_mid()), (N, C.sit_pose())], f)


def sit_idle(f, N=90):
    t = f / N
    P = C.sit_pose()
    C.pant(P, t, rate=9, jaw=18, out=0.028)
    C.look(P, yaw=10 * math.sin(TAU * t), pitch=-3 * math.sin(2 * TAU * t))
    C.ears(P, (4 * math.sin(TAU * t + 1), 0, 0))
    return P


def sit_end(f, N=30):
    mid = _crouch_mid()
    mid.body_off = mid.body_off + Vector((0, -0.02, 0.03))
    return C.timeline([(0, C.sit_pose()), (14, mid), (N, C.stand())], f)


def _lie_mid():
    """from the sit: the fore paws walk forward, the chest goes down"""
    P = D.blend(C.sit_pose(), C.lie_pose(), 0.5)
    P.body_rot = (-12, 2, 0)
    P.body_off = Vector((0, 0.03, -0.26))
    return P


def lie_start(f, N=60):
    s = C.sit_pose()
    return C.timeline([(0, C.stand()), (16, _crouch_mid()), (30, s), (44, _lie_mid()), (N, C.lie_pose())], f)


def lying_idle(f, N=120):
    t = f / N
    P = C.lie_pose()
    C.breathe(P, t, amp=1.2, rate=4)
    C.look(P, yaw=18 * math.sin(TAU * t), pitch=-4 * math.sin(2 * TAU * t))
    C.ears(P, (3 * math.sin(TAU * 2 * t), 0, 0))
    C.wag(P, t, amp=5, rate=1)
    return P


def lie_end(f, N=50):
    s = C.sit_pose()
    return C.timeline([(0, C.lie_pose()), (14, _lie_mid()), (26, s), (38, _crouch_mid()), (N, C.stand())], f)


CLIPS = [
    ("Sit_Start", 36, sit_start, False),
    ("Sit_Idle", 90, sit_idle, True),
    ("Sit_End", 30, sit_end, False),
    ("Lie_Start", 60, lie_start, False),
    ("Lying_Idle", 120, lying_idle, True),
    ("Lie_End", 50, lie_end, False),
]


def build(rig):
    names = []
    for name, N, fn, loop in CLIPS:
        rig.make_clip(name, N, lambda f, fn=fn, N=N: fn(f, N), loop=loop)
        names.append(name)
    return names


def planted_fn(name):
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
        act = rig.make_clip(name, N, lambda f, fn=fn, N=N: fn(f, N), loop=loop)
        D.qa_clip(rig, act)
        print(f"   body drop (reach pass) max {act['dog_body_drop_mm']:.1f} mm")
    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(a.out_dir), "sit_lie.blend"))
