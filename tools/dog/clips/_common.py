"""Shared key-pose tools for the Rottweiler clip families (not a family itself: the leading '_' keeps
dog_animations.py from importing it as one).

  timeline(keys, f)     keys = [(frame, Pose), ...]: eased (smootherstep) blend between neighbouring keys; a paw
                        that moves more than 1 cm between two keys is lifted on an arc (it steps, never drags)
  stand()               the rest pose (== Pose(), so every family's boundary pose matches Idle / the gaits)
  sit_pose() / lie_pose() / sniff_pose() / growl_pose()   the reusable held poses
  breathe / wag / pant  additive layers (periodic in the clip length, so loops stay exact)

Head carriage: the rest head is set low (anatomy.HEAD_POS / HEAD_PITCH, the nose level with the withers top), which
lowers the rest Neck1 by 6.1 deg and Neck2 by 10.0 deg (world elevation) and the head by 10 deg. Poses that set the
neck and head explicitly were tuned on the old, higher carriage and carry the compensation Neck1 -6, Neck2 -4, Head 0
(restores the world orientation of every neck and head bone); gaits and look-only idles inherit the low carriage.
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bpy  # noqa: F401
from mathutils import Vector
import dog_anim as D

TAU = 2 * math.pi


def stand():
    return D.Pose()


def rest_mcp(leg):
    return D._REST_MCP[leg].copy()


def leg(legname, dx=0.0, dy=0.0, dz=0.0, pastern=0.0, toe=0.0, scap=0.0, pole=0.0):
    return D.LegPose(rest_mcp(legname) + Vector((dx, dy, dz)), pastern=pastern, toe=toe, scap=scap, pole=pole)


def timeline(keys, f, lift=0.04):
    """keys sorted by frame; returns the blended Pose at frame f."""
    if f <= keys[0][0]:
        return keys[0][1].copy()
    if f >= keys[-1][0]:
        return keys[-1][1].copy()
    for (f0, p0), (f1, p1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            t = (f - f0) / (f1 - f0)
            e = D.smoother(t)
            P = D.blend(p0, p1, e)
            for k in D.LEGS:
                a = p0.legs[k].mcp if p0.legs[k].mcp is not None else rest_mcp(k)
                b = p1.legs[k].mcp if p1.legs[k].mcp is not None else rest_mcp(k)
                dist = (Vector((a.x, a.y, 0)) - Vector((b.x, b.y, 0))).length
                if P.legs[k].mcp is None:
                    P.legs[k].mcp = rest_mcp(k)
                if dist > 0.01 and lift > 0:
                    h = min(lift, 0.02 + dist * 0.35) * math.sin(math.pi * e)
                    P.legs[k].mcp = P.legs[k].mcp + Vector((0, 0, h))
                    if k[0] == "F":        # the carpus folds; a hind step keeps the hock angle (no compression)
                        P.legs[k].pastern += 35 * math.sin(math.pi * e)
                    P.legs[k].toe += 10 * math.sin(math.pi * e)
            return P
    return keys[-1][1].copy()


# --------------------------------------------------------------------------------------------- held poses
def sniff_pose():
    """nose to the ground: neck down, fore legs a little forward, the rump slightly up"""
    P = D.Pose()
    P.body_rot = (10, 0, 0)
    P.body_off = Vector((0, -0.02, -0.05))
    P.spine = {"Spine1": (3, 0, 0), "Spine2": (4, 0, 0), "Spine3": (6, 0, 0)}
    P.neck = {"Neck1": (60, 0, 0), "Neck2": (16, 0, 0)}       # (66, 20) on the old carriage
    P.head = (-28, 0, 0)
    P.tail = D.tail_shape(lift=35, curl=75)
    P.ears = {"L": (-8, 0, 0), "R": (-8, 0, 0)}
    return P


def growl_pose():
    """aggressive stance: weight forward, head low and forward, lips lifted, ears back, tail up and stiff"""
    P = D.Pose()
    P.body_rot = (5, 0, 0)
    P.body_off = Vector((0, -0.03, -0.07))                      # a stalking crouch: legs flexed, belly low (GiM)
    P.spine = {"Spine1": (-2, 0, 0), "Spine2": (-1, 0, 0), "Spine3": (2, 0, 0)}
    P.neck = {"Neck1": (28, 0, 0), "Neck2": (8, 0, 0)}        # (34, 12) on the old carriage
    P.head = (-34, 0, 0)
    P.jaw = 9; P.nose = 5
    # the paws stay where Idle has them (an Animator crossfade must not skate them)
    P.tail = D.tail_shape(lift=35, curl=90)
    P.ears = {"L": (0, 15, 15), "R": (0, -15, -15)}            # swung back and out, clear of the skull
    P.ear_tip = {"L": 8, "R": 8}
    return P


def sit_pose():
    """sitting square: the rump on the ground, hocks flat, fore legs straight, head level"""
    P = D.Pose()
    P.body_rot = (-46, 0, 0)
    P.body_off = Vector((0, 0.02, -0.155))
    P.spine = {"Spine1": (0, 0, 0), "Spine2": (0, 0, 0), "Spine3": (0, 0, 0)}
    P.neck = {"Neck1": (14, 0, 0), "Neck2": (6, 0, 0)}        # (20, 10) on the old carriage
    P.head = (16, 0, 0)
    P.legs["FL"] = leg("FL", dx=0.004, dy=0.05); P.legs["FR"] = leg("FR", dx=-0.004, dy=0.05)
    # hind: metatarsus flat on the ground, the paw forward under the chest
    P.legs["HL"] = D.LegPose(Vector((0.108, 0.080, 0.036)), pastern=-86, toe=0)
    P.legs["HR"] = D.LegPose(Vector((-0.108, 0.080, 0.036)), pastern=-86, toe=0)
    P.tail = D.tail_shape(lift=-38, side=18, curl=-30)
    return P


def lie_pose():
    """sphinx lying: belly on the ground, fore legs straight forward on the ground, hind legs folded beside the
    body with the metatarsi flat, head up"""
    P = D.Pose()
    P.body_rot = (-2, 4, 0)
    P.body_off = Vector((0, 0.03, -0.300))
    P.spine = {"Spine1": (0, 3, 0), "Spine2": (0, 2, 0), "Spine3": (0, 0, 0)}
    P.neck = {"Neck1": (-22, 0, 0), "Neck2": (-10, 0, 0)}     # (-16, -6) on the old carriage
    P.head = (24, 0, 0)
    # fore: forearms on the ground, paws forward
    for k, sx in (("FL", 1), ("FR", -1)):
        P.legs[k] = D.LegPose(Vector((sx * 0.085, -0.575, 0.030)), pastern=-60, toe=0, scap=-10)
    for k, sx in (("HL", 1), ("HR", -1)):
        P.legs[k] = D.LegPose(Vector((sx * 0.150, 0.020, 0.042)), pastern=-84, toe=0, pole=sx * 25)
    P.tail = D.tail_shape(lift=-62, side=30, curl=-20)
    return P


# --------------------------------------------------------------------------------------------- layers
def breathe(P, t, amp=1.0, rate=1.0):
    """t in [0, 1) of a loop; rate = breaths per loop (integer for loops)"""
    s = math.sin(TAU * rate * t)
    P.body_off = P.body_off + Vector((0, 0, 0.0025 * amp * s))
    sp = dict(P.spine)
    a, b, c = sp["Spine2"]; sp["Spine2"] = (a - 0.6 * amp * s, b, c)
    P.spine = sp
    return P


def pant(P, t, rate, jaw=24, out=0.035):
    """mouth open, tongue out and hanging, fast shallow breaths (rate per loop)"""
    s = math.sin(TAU * rate * t)
    P.jaw = P.jaw + jaw + 3 * s
    P.tongue = (out + 0.004 * s, 38 + 6 * s, 0)
    P.body_off = P.body_off + Vector((0, 0, 0.002 * s))
    sp = dict(P.spine); a, b, c = sp["Spine2"]; sp["Spine2"] = (a - 1.0 * s, b, c); P.spine = sp
    return P


def wag(P, t, amp=25, rate=2.0, lift=None):
    tail = list(P.tail)
    w = D.tail_shape(wag=amp * math.sin(TAU * rate * t))
    P.tail = [(a[0] + b[0], a[1] + b[1]) for a, b in zip(tail, w)]
    if lift is not None:
        P.tail = [(a[0] + (lift if i == 0 else 0), a[1]) for i, a in enumerate(P.tail)]
    return P


def look(P, pitch=0.0, yaw=0.0, roll=0.0):
    """turn the head: split over Neck1, Neck2, Head"""
    n1, n2 = P.neck["Neck1"], P.neck["Neck2"]
    P.neck = {"Neck1": (n1[0] + pitch * 0.3, n1[1] + yaw * 0.3, n1[2]),
              "Neck2": (n2[0] + pitch * 0.3, n2[1] + yaw * 0.35, n2[2])}
    P.head = (P.head[0] + pitch * 0.4, P.head[1] + yaw * 0.35, P.head[2] + roll)
    return P


def ears(P, l, r=None, tip=None):
    r = l if r is None else r
    P.ears = {"L": tuple(a + b for a, b in zip(P.ears["L"], l)), "R": tuple(a + b for a, b in zip(P.ears["R"], r))}
    if tip is not None:
        P.ear_tip = {"L": P.ear_tip["L"] + tip, "R": P.ear_tip["R"] + tip}
    return P
