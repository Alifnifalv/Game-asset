"""Raven animation library: Pose -> armature-space matrices (analytic FK / IK) -> quaternion keys, plus QA.

Pose (all angles in degrees)
  root_pos, root_yaw      Root motion (yaw + = turn left)
  body_off, body_rot      Hips translation (root frame) and rotation (pitch + = nose down, roll + = right side down,
                          yaw + = left) about COG
  spine {Spine1, Spine2}, neck {Neck1..3}, head   rot(pitch, yaw, roll) in the bone's local frame (pitch + = the bone
                          tips down for a forward bone; yaw + = to the bird's left; see rot())
  jaw                     + = the bill opens (lower mandible down)
  throat                  + = the hackles puff out (Throat bone swings forward/out)
  eyes                    (pitch, yaw) of both eyeballs
  tailbase, tail          rot() of TailBase / Tail (pitch + = the tail tip goes down)
  tail_spread             0 closed .. 1 the glide fan (72 deg); the bind pose is 0.5
  wings {L, R}            WingPose
  legs {L, R}             LegPose

WingPose(fold, arm, elbow, wrist, feathers, elev, sweep, twist, spread, slot, finger_up, hand_twist)
  fold                    master fold 0 (spread, the bind pose) .. 1 (folded against the body; ground clips)
  arm/elbow/wrist/feathers per-joint fold amounts (None = fold): e.g. the upstroke flexes the wrist more than the arm
  elev, sweep, twist      shoulder rotation: elevation (+ = wing up, about the body's long axis), sweep (+ = the
                          wing swings forward, about the wing normal), twist (+ = leading edge down / pronation)
  spread                  primary fan beyond the bind pose (+ = open; each primary by up to `spread` deg, P10 most)
  slot                    primaries rotate about their rachis (+ = the leading vane up: the slots open on the upstroke)
  finger_up               the outer primaries (P5-P10) pitch up (glide: fingertips curl up 10-15 deg)
  hand_twist              extra pronation of the hand (deg)

LegPose(mtp, yaw, grip, thigh, pole, planted)
  mtp                     target of the foot base (the Tarsus tail = MTP joint) in the root frame; None = rest
  yaw                     foot direction change (deg, + = toes turn left)
  grip                    0 = toes flat on the ground (planted), 1 = curled (flight / perch grip)
  thigh                   femur swing (deg, + = knee forward/up) relative to the Hips
  pole                    rotation of the leg plane about the knee-foot line (deg)

The fold targets (rest body frame): the humerus runs back along the flank, the forearm forward, the hand back (spec
2.2); the flight feathers turn about their dorsal normals to lie parallel (primaries along the hand, secondaries and
tertials a few degrees lower) and keep their dorsal stacking (tertials outside ... P10 inside), because the folded
hand lies medial to the forearm and the forearm medial to the elbow (FOLD_LAT).
"""
import math, os, sys
import numpy as np
import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import raven_anatomy as A          # noqa: E402

FPS = 30
RIG = "RavenRig"
LOD2 = "Raven_LOD2"
COG = Vector((0.0, -0.045, 0.200))
REACH = 0.9985
SIDES = "LR"
REMEX = [r[0] for r in A.REMIGES]
PRIMS = [n for n in REMEX if n.startswith("Prim")]
TOES = ["Toe1", "Toe2", "Toe3", "Toe4"]

# fold targets (left side, rest body frame; spec 2.2, 4.9)
FOLD_ELBOW = Vector((0.055, -0.016, 0.205))
FOLD_WRIST = Vector((0.060, -0.124, 0.250))
FOLD_HAND = Vector((0.057, -0.050, 0.236))
FOLD_PTIP = Vector((0.006, 0.192, 0.118))
FOLD_N0 = Vector((1.0, 0.0, 0.10))                       # folded wing plane normal before orthogonalisation
FOLD_LAT = {"elbow": 0.036, "wrist": 0.034, "hand": 0.030}   # lateral offsets from the plane through the shoulder
FOLD_DROP = {"prim": 0.0, "sec": -7.0, "tert": -14.0}      # in-plane angle of the folded feathers vs the primaries
FOLD_FAN = 0.25                                           # deg per feather index: a slight stagger in the fold


def rad(d):
    return math.radians(d)


def Rx(a):
    return Matrix.Rotation(rad(a), 4, "X")


def Ry(a):
    return Matrix.Rotation(rad(a), 4, "Y")


def Rz(a):
    return Matrix.Rotation(rad(a), 4, "Z")


def T(v):
    return Matrix.Translation(Vector(v))


def body_matrix(pitch, roll, yaw):
    return Rz(yaw) @ Rx(pitch) @ Ry(-roll)


def rot(pitch=0.0, yaw=0.0, roll=0.0):
    """local rotation: bone local X ~ -X world for sagittal bones (stage B rolls) -> pitch + = the bone's tip down
    for a forward-pointing bone; yaw about local Z; roll about the bone axis"""
    return (Quaternion((0, 0, 1), rad(yaw)) @ Quaternion((1, 0, 0), rad(-pitch))
            @ Quaternion((0, 1, 0), rad(roll)))


def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def smoother(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * t * (t * (t * 6 - 15) + 10)


def lerp(a, b, t):
    return a + (b - a) * t


class WingPose:
    FIELDS = ("fold", "arm", "elbow", "wrist", "feathers", "elev", "sweep", "twist", "spread", "slot", "finger_up",
              "hand_twist")

    def __init__(self, fold=0.0, arm=None, elbow=None, wrist=None, feathers=None, elev=0.0, sweep=0.0, twist=0.0,
                 spread=0.0, slot=0.0, finger_up=0.0, hand_twist=0.0):
        self.fold, self.arm, self.elbow, self.wrist, self.feathers = fold, arm, elbow, wrist, feathers
        self.elev, self.sweep, self.twist, self.spread, self.slot = elev, sweep, twist, spread, slot
        self.finger_up, self.hand_twist = finger_up, hand_twist

    def get(self, k):
        v = getattr(self, k)
        return self.fold if v is None else v

    def copy(self):
        return WingPose(**{k: getattr(self, k) for k in self.FIELDS})


class LegPose:
    def __init__(self, mtp=None, yaw=0.0, grip=0.0, thigh=0.0, pole=0.0, planted=False):
        self.mtp = None if mtp is None else Vector(mtp)
        self.yaw, self.grip, self.thigh, self.pole, self.planted = yaw, grip, thigh, pole, planted

    def copy(self):
        return LegPose(None if self.mtp is None else self.mtp.copy(), self.yaw, self.grip, self.thigh, self.pole,
                       self.planted)


class Pose:
    def __init__(self):
        self.root_pos = Vector((0, 0, 0)); self.root_yaw = 0.0
        self.body_off = Vector((0, 0, 0)); self.body_rot = (0.0, 0.0, 0.0)
        self.spine = {"Spine1": (0, 0, 0), "Spine2": (0, 0, 0)}
        self.neck = {"Neck1": (0, 0, 0), "Neck2": (0, 0, 0), "Neck3": (0, 0, 0)}
        self.head = (0.0, 0.0, 0.0)
        self.jaw = 0.0; self.throat = 0.0; self.eyes = (0.0, 0.0)
        self.tailbase = (0.0, 0.0, 0.0); self.tail = (0.0, 0.0, 0.0); self.tail_spread = A.TAIL_BIND_SPREAD
        self.wings = {s: WingPose() for s in SIDES}
        self.legs = {s: LegPose() for s in SIDES}
        self.extra = {}

    def copy(self):
        P = Pose()
        P.root_pos = self.root_pos.copy(); P.root_yaw = self.root_yaw
        P.body_off = self.body_off.copy(); P.body_rot = tuple(self.body_rot)
        P.spine = dict(self.spine); P.neck = dict(self.neck); P.head = tuple(self.head)
        P.jaw, P.throat, P.eyes = self.jaw, self.throat, tuple(self.eyes)
        P.tailbase, P.tail, P.tail_spread = tuple(self.tailbase), tuple(self.tail), self.tail_spread
        P.wings = {s: w.copy() for s, w in self.wings.items()}
        P.legs = {s: l.copy() for s, l in self.legs.items()}
        P.extra = dict(self.extra)
        return P


def _mix(a, b, t):
    if isinstance(a, Vector):
        return a.lerp(b, t)
    if isinstance(a, (tuple, list)):
        return type(a)(lerp(x, y, t) for x, y in zip(a, b))
    if a is None or b is None:
        return a if t < 0.5 else b
    return lerp(a, b, t)


def blend(p0, p1, t):
    """linear blend of two poses (angles, offsets, fold amounts, foot targets)"""
    P = p0.copy()
    P.root_pos = p0.root_pos.lerp(p1.root_pos, t); P.root_yaw = lerp(p0.root_yaw, p1.root_yaw, t)
    P.body_off = p0.body_off.lerp(p1.body_off, t); P.body_rot = _mix(p0.body_rot, p1.body_rot, t)
    P.spine = {k: _mix(p0.spine[k], p1.spine[k], t) for k in p0.spine}
    P.neck = {k: _mix(p0.neck[k], p1.neck[k], t) for k in p0.neck}
    P.head = _mix(p0.head, p1.head, t)
    P.jaw = lerp(p0.jaw, p1.jaw, t); P.throat = lerp(p0.throat, p1.throat, t); P.eyes = _mix(p0.eyes, p1.eyes, t)
    P.tailbase = _mix(p0.tailbase, p1.tailbase, t); P.tail = _mix(p0.tail, p1.tail, t)
    P.tail_spread = lerp(p0.tail_spread, p1.tail_spread, t)
    for s in SIDES:
        w0, w1 = p0.wings[s], p1.wings[s]
        P.wings[s] = WingPose(**{k: (_mix(w0.get(k), w1.get(k), t) if k in ("arm", "elbow", "wrist", "feathers")
                                     else _mix(getattr(w0, k), getattr(w1, k), t)) for k in WingPose.FIELDS})
        l0, l1 = p0.legs[s], p1.legs[s]
        m0 = l0.mtp if l0.mtp is not None else _REST_MTP[s]
        m1 = l1.mtp if l1.mtp is not None else _REST_MTP[s]
        P.legs[s] = LegPose(m0.lerp(m1, t), lerp(l0.yaw, l1.yaw, t), lerp(l0.grip, l1.grip, t),
                            lerp(l0.thigh, l1.thigh, t), lerp(l0.pole, l1.pole, t), l0.planted and l1.planted)
    keys = set(p0.extra) | set(p1.extra)
    P.extra = {k: p0.extra.get(k, Quaternion()).slerp(p1.extra.get(k, Quaternion()), t) for k in keys}
    return P


_REST_MTP = {}


def _side(v, s):
    v = Vector(v)
    return v if s == "L" else Vector((-v.x, v.y, v.z))


class RavenRig:
    def __init__(self, arm=None):
        self.arm = arm or bpy.data.objects[RIG]
        bones = self.arm.data.bones
        self.order = [b.name for b in bones]
        self.rest = {b.name: b.matrix_local.copy() for b in bones}
        self.par = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.length = {b.name: b.length for b in bones}
        self.relm = {}
        for n in self.order:
            p = self.par[n]
            self.relm[n] = (self.rest[p].inverted() @ self.rest[n]) if p else self.rest[n].copy()
        for pb in self.arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
        self.clip_poses = {}
        self.leg = {}
        for s in SIDES:
            K = self.head(f"Shin.{s}"); An = self.head(f"Tarsus.{s}"); M = self.tail(f"Tarsus.{s}")
            u = (M - K).normalized()
            pole = (An - K) - u * (An - K).dot(u)
            n = (M - K).cross(An - K).normalized()
            info = dict(K=K, A=An, M=M, pole=pole.normalized(), n=n, L2=(An - K).length, L3=(M - An).length)
            for b, (a0, a1) in ((f"Shin.{s}", (K, An)), (f"Tarsus.{s}", (An, M))):
                F = self._frame((a1 - a0).normalized(), n)
                info["rel_" + b] = F.inverted() @ self.rest[b].to_3x3()
            self.leg[s] = info
            _REST_MTP[s] = M.copy()
        self._fold_targets()

    def head(self, b):
        return self.rest[b].to_translation()

    def tail(self, b):
        return (self.rest[b] @ Vector((0, self.length[b], 0, 1))).to_3d()

    @staticmethod
    def _frame(y, n):
        x = (n - y * n.dot(y))
        if x.length < 1e-9:
            x = Vector((1, 0, 0)) - y * y.x
        x.normalize()
        z = x.cross(y)
        return Matrix((x, y, z)).transposed()

    @staticmethod
    def _frame_yz(y, z):
        """3x3 with local Y = y and local Z as close to z as possible"""
        y = y.normalized()
        z = (z - y * z.dot(y)).normalized()
        x = y.cross(z)
        return Matrix((x, y, z)).transposed()

    # ------------------------------------------------------------------------------------------ fold targets
    def _fold_targets(self):
        """local (parent-relative) rotations of the arm and feather bones at the full fold, per side"""
        self.fold_q = {}
        for s in SIDES:
            S = self.head(f"UpperArm.{s}")
            d_b = (_side(FOLD_PTIP, s) - _side(FOLD_WRIST, s)).normalized()
            n0 = _side(FOLD_N0, s)
            n_f = (n0 - d_b * n0.dot(d_b)).normalized()
            self.fold_n = getattr(self, "fold_n", {}); self.fold_n[s] = n_f

            def lat(p, key):
                p = _side(p, s)
                return p - n_f * (p - S).dot(n_f) + n_f * FOLD_LAT[key]
            E, Wr, H = lat(FOLD_ELBOW, "elbow"), lat(FOLD_WRIST, "wrist"), lat(FOLD_HAND, "hand")
            world = {}                                   # folded armature-space 3x3 per bone
            pos = {}
            # arm chain by FK with aimed directions
            world[f"UpperArm.{s}"] = self._frame_yz(E - S, n_f)
            e_fk = S + world[f"UpperArm.{s}"] @ Vector((0, self.length[f"UpperArm.{s}"], 0))
            world[f"Forearm.{s}"] = self._frame_yz(Wr - e_fk, n_f)
            w_fk = e_fk + world[f"Forearm.{s}"] @ Vector((0, self.length[f"Forearm.{s}"], 0))
            world[f"Hand.{s}"] = self._frame_yz(H - w_fk, n_f)
            up = Vector((0, 0, 1))                        # in-plane 'up': the plane direction closest to world up
            e_u = (up - d_b * up.dot(d_b) - n_f * up.dot(n_f)).normalized()     # (same sense on both sides)
            for i, name in enumerate(REMEX):
                kind = "prim" if name.startswith("Prim") else ("sec" if name.startswith("Sec") else "tert")
                ang = rad(FOLD_DROP[kind] + FOLD_FAN * (A.REMEX_ORDER.index(name) - 9))
                d = d_b * math.cos(ang) + e_u * math.sin(ang)
                world[f"{name}.{s}"] = self._frame_yz(d, n_f)
            # alula lies along the hand
            world[f"Alula.{s}"] = self._frame_yz(H - w_fk, n_f)
            # local rotations: q_local = (R_parent_pose * R_rel)^-1 * R_pose (rotations only)
            q = {}
            for b in (f"UpperArm.{s}", f"Forearm.{s}", f"Hand.{s}", f"Alula.{s}") + tuple(f"{n}.{s}" for n in REMEX):
                p = self.par[b]
                Rp = world[p] if p in world else self.rest[p].to_3x3()
                Rrel = self.relm[b].to_3x3()
                q[b] = ((Rp @ Rrel).inverted() @ world[b]).to_quaternion()
            self.fold_q[s] = q
            self.fold_world = getattr(self, "fold_world", {}); self.fold_world[s] = world

    # ------------------------------------------------------------------------------------------ solver
    def solve(self, P):
        M = {}
        W = T(P.root_pos) @ Rz(P.root_yaw)
        self.W = W
        M["Root"] = W @ self.rest["Root"]
        B = body_matrix(*P.body_rot)
        hips_world = W @ T(P.body_off) @ T(COG) @ B @ T(-COG)
        M["Hips"] = hips_world @ self.rest["Hips"]
        self.body_world = hips_world
        local = {}
        for n, v in P.spine.items():
            local[n] = rot(*v)
        for n, v in P.neck.items():
            local[n] = rot(*v)
        local["Head"] = rot(*P.head)
        local["Jaw"] = rot(P.jaw)                        # the Jaw bone points forward: + pitch = tip down = open
        local["Throat"] = rot(-P.throat)
        for s in SIDES:
            local[f"Eye.{s}"] = rot(P.eyes[0], P.eyes[1])
        local["TailBase"] = rot(*P.tailbase)
        local["Tail"] = rot(*P.tail)
        # tail fan: each rectrix turns about its dorsal normal (local Z) from its bind angle to the target spread
        for s in SIDES:
            sx = 1.0 if s == "L" else -1.0
            for i in range(6):
                da = A.rectrix_angle(i, P.tail_spread) - A.rectrix_angle(i, A.TAIL_BIND_SPREAD)
                local[f"Rect{i + 1}.{s}"] = Quaternion((0, 0, 1), self._fan_sign(f"Rect{i + 1}.{s}", sx) * rad(da))
        for s in SIDES:
            local.update(self._wing_local(s, P.wings[s]))
        for n, q in P.extra.items():
            local[n] = local.get(n, Quaternion()) @ q
        for n in self.order:
            if n in M:
                continue
            p = self.par[n]
            if p not in M:
                continue
            if n.startswith(("Shin", "Tarsus", "Toe")):
                continue
            base = M[p] @ self.relm[n]
            M[n] = base @ (local[n].to_matrix().to_4x4() if n in local else Matrix.Identity(4))
        self.last_reach = {}
        for s in SIDES:
            self._solve_leg(s, P.legs[s], M, B)
        for n in self.order:
            if n not in M:
                M[n] = M[self.par[n]] @ self.relm[n]
        return M

    def _fan_sign(self, bone, sx):
        """+1 when a positive rotation about the bone's local Z moves its tip away from the midline (+X for .L)"""
        key = ("fan", bone)
        if key not in self.__dict__.setdefault("_cache", {}):
            R = self.rest[bone].to_3x3()
            y, z = R.col[1], R.col[2]
            self._cache[key] = 1.0 if z.cross(y).x * sx > 0 else -1.0
        return self._cache[key]

    def _wing_local(self, s, wp):
        """local rotations of the wing bones for a WingPose"""
        out = {}
        fq = self.fold_q[s]
        sx = 1.0 if s == "L" else -1.0
        amt = {f"UpperArm.{s}": wp.get("arm"), f"Forearm.{s}": wp.get("elbow"), f"Hand.{s}": wp.get("wrist"),
               f"Alula.{s}": wp.get("wrist")}
        for n in REMEX:
            amt[f"{n}.{s}"] = wp.get("feathers")
        for b, t in amt.items():
            out[b] = Quaternion().slerp(fq[b], min(max(t, 0.0), 1.0)) if t > 0 else Quaternion()
        # shoulder motion, expressed in the parent (Shoulder) space about the UpperArm head
        ua = f"UpperArm.{s}"
        if wp.elev or wp.sweep or wp.twist:
            Rrel = self.relm[ua].to_3x3()
            fwd = Vector((0, -1, 0))                       # body long axis (forward) in the rest frame
            # elevation: about the forward axis (+ = up for both sides), sweep about world Z (+ = forward),
            # twist about the humerus (+ = leading edge down)
            hum = (self.rest[ua].to_3x3() @ Vector((0, 1, 0))).normalized()
            Rw = (Quaternion(fwd, rad(wp.elev) * sx) @ Quaternion(Vector((0, 0, 1)), rad(wp.sweep) * -sx)
                  @ Quaternion(hum, rad(wp.twist) * sx))
            # world-space delta about the shoulder -> parent space (the Shoulder bone's rest frame)
            Rp = self.rest[self.par[ua]].to_3x3()
            qd = (Rp.inverted() @ Rw.to_matrix() @ Rp).to_quaternion()
            out[ua] = (Rrel.to_quaternion().inverted() @ qd @ Rrel.to_quaternion()) @ out[ua]
        if wp.hand_twist:
            out[f"Hand.{s}"] = out[f"Hand.{s}"] @ Quaternion((0, 1, 0), rad(wp.hand_twist))
        # primaries: fan spread (about local Z), slotting (about the rachis, local Y), fingers up (about local X)
        for i, n in enumerate(PRIMS[::-1]):              # P1 .. P10
            b = f"{n}.{s}"
            k = (i + 1) / 10.0
            q = out[b]
            if wp.spread:
                q = q @ Quaternion((0, 0, 1), self._spread_sign(b) * rad(wp.spread * k))
            if wp.slot:
                q = q @ Quaternion((0, 1, 0), rad(wp.slot * k) * sx)
            if wp.finger_up and i >= 4:
                q = q @ Quaternion((1, 0, 0), rad(wp.finger_up * (i - 3) / 6.0))
            out[b] = q
        return out

    def _spread_sign(self, bone):
        """+1 when a positive local-Z rotation moves the primary's tip toward the leading edge (forward, -Y)"""
        key = ("spread", bone)
        c = self.__dict__.setdefault("_cache", {})
        if key not in c:
            R = self.rest[bone].to_3x3()
            y, z = R.col[1], R.col[2]
            c[key] = 1.0 if z.cross(y).y < 0 else -1.0
        return c[key]

    def _solve_leg(self, s, lp, M, Bbody):
        I = self.leg[s]
        th, sh, ta = f"Thigh.{s}", f"Shin.{s}", f"Tarsus.{s}"
        M[th] = M["Hips"] @ self.relm[th] @ rot(lp.thigh).to_matrix().to_4x4()
        K = M[th] @ Vector((0, self.length[th], 0, 1))
        K = K.to_3d()
        tgt = self.W @ (lp.mtp if lp.mtp is not None else I["M"])
        body3 = (self.body_world.to_3x3())
        pole = (body3 @ I["pole"])
        yawq = Quaternion((0, 0, 1), rad(lp.yaw + 0.0))
        pole = (self.W.to_3x3() @ Rz(lp.yaw).to_3x3() @ self.W.to_3x3().inverted()) @ pole
        L2, L3 = I["L2"], I["L3"]
        v = tgt - K
        d = v.length
        dmax = (L2 + L3) * REACH
        self.last_reach[s] = d - dmax
        d = min(max(d, abs(L2 - L3) + 1e-4), dmax)
        u = v.normalized()
        if lp.pole:
            pole = Quaternion(u, rad(lp.pole)) @ pole
        pv = (pole - u * pole.dot(u)).normalized()
        a = (d * d + L2 * L2 - L3 * L3) / (2 * d)
        h = math.sqrt(max(L2 * L2 - a * a, 0.0))
        Aj = K + u * a + pv * h
        Mt = K + u * d                                   # the reachable foot point
        n = (Mt - K).cross(Aj - K).normalized()
        for b, (a0, a1) in ((sh, (K, Aj)), (ta, (Aj, Mt))):
            F = self._frame((a1 - a0).normalized(), n)
            R = F @ I["rel_" + b]
            M[b] = T(a0) @ R.to_4x4()
        # toes: world-anchored around the foot target, yawed with the root and the foot; grip curls them
        Ry_ = self.W.to_3x3() @ Rz(lp.yaw).to_3x3()
        for toe in TOES:
            a_, b_ = f"{toe}a.{s}", f"{toe}b.{s}"
            off = self.head(a_) - I["M"]
            ha = tgt + Ry_ @ off
            Ra = Ry_ @ self.rest[a_].to_3x3() @ rot(-35 * lp.grip).to_matrix()
            M[a_] = T(ha) @ Ra.to_4x4()
            M[b_] = M[a_] @ self.relm[b_] @ rot(-55 * lp.grip).to_matrix().to_4x4()

    # ------------------------------------------------------------------------------------------ keys
    def basis(self, M):
        out = {}
        for n in self.order:
            p = self.par[n]
            parent_m = (M[p] @ self.relm[n]) if p else self.rest[n]
            out[n] = parent_m.inverted() @ M[n]
        return out

    def apply(self, P):
        B = self.basis(self.solve(P))
        for n, m in B.items():
            self.arm.pose.bones[n].matrix_basis = m
        return B

    def new_action(self, name):
        old = bpy.data.actions.get(name)
        if old:
            bpy.data.actions.remove(old)
        act = bpy.data.actions.new(name)
        slot = act.slots.new(id_type="OBJECT", name=RIG)
        layer = act.layers.new("Layer")
        strip = layer.strips.new(type="KEYFRAME")
        strip.channelbag(slot, ensure=True)
        act.use_fake_user = True
        return act

    def use_action(self, act):
        ad = self.arm.animation_data_create()
        ad.action = act
        if act.slots:
            ad.action_slot = act.slots[0]

    def write_curves(self, act, samples):
        cb = act.layers[0].strips[0].channelbag(act.slots[0], ensure=True)
        for n, rows in samples.items():
            prev = None; qs = []
            for loc, q in rows:
                q = q.copy()
                if prev is not None and prev.dot(q) < 0:
                    q.negate()
                prev = q; qs.append(q)
            nfr = len(rows)
            for path, ncomp, get in ((f'pose.bones["{n}"].location', 3, lambda i, c: rows[i][0][c]),
                                     (f'pose.bones["{n}"].rotation_quaternion', 4, lambda i, c: qs[i][c])):
                for c in range(ncomp):
                    fc = cb.fcurves.new(path, index=c, group_name=n)
                    fc.keyframe_points.add(nfr)
                    co = np.empty(2 * nfr); co[0::2] = np.arange(nfr); co[1::2] = [get(i, c) for i in range(nfr)]
                    fc.keyframe_points.foreach_set("co", co)
                    fc.keyframe_points.foreach_set("interpolation", [1] * nfr)
                    fc.update()

    def make_clip(self, name, frames, pose_fn, loop=True):
        """pose_fn(f) -> Pose for f in 0..frames (inclusive); loops: frame `frames` must equal frame 0"""
        act = self.new_action(name)
        poses = [pose_fn(f) for f in range(frames + 1)]
        samples = {n: [] for n in self.order}
        reach = {s: -1.0 for s in SIDES}
        for P in poses:
            B = self.basis(self.solve(P))
            for s in SIDES:
                reach[s] = max(reach[s], self.last_reach[s])
            for n in self.order:
                loc, q, _ = B[n].decompose()
                samples[n].append((loc, q))
        self.write_curves(act, samples)
        act.use_frame_range = True
        act.frame_start, act.frame_end = 0, frames
        act.use_cyclic = loop
        act["raven_reach_mm"] = max(reach.values()) * 1000
        self.clip_poses[name] = poses
        return act

    def self_test(self):
        B = self.basis(self.solve(Pose()))
        return max(abs(m[i][j] - (1.0 if i == j else 0.0)) for m in B.values() for i in range(4) for j in range(4))


# ================================================================================================= standard poses
def stand():
    """the perched standing pose (spec 2.2): wings folded, tail closed along the body, toes flat"""
    P = Pose()
    for s in SIDES:
        P.wings[s] = WingPose(fold=1.0)
    P.tail_spread = 0.0
    return P


def fly_neutral():
    """level flight attitude (spec 2.4): trunk pitched 28 deg nose-down (spine ~horizontal), neck extended, head level,
    wings spread (bind planform), tail half spread, legs tucked back, toes curled"""
    P = Pose()
    P.body_rot = (28.0, 0.0, 0.0)
    P.body_off = Vector((0, 0, 0.05))
    P.neck = {"Neck1": (-10, 0, 0), "Neck2": (-6, 0, 0), "Neck3": (8, 0, 0)}
    P.head = (-6.0, 0.0, 0.0)
    P.tail_spread = 0.5
    for s in SIDES:
        P.legs[s] = LegPose(_side(Vector((0.030, 0.090, 0.140)), s), grip=1.0, thigh=-10)
    return P


# ================================================================================================= QA helpers
def eval_bone_heads(arm, names):
    dg = bpy.context.evaluated_depsgraph_get()
    ae = arm.evaluated_get(dg)
    return {n: (ae.matrix_world @ ae.pose.bones[n].head).copy() for n in names}


def lod_vertices(obj_name=LOD2):
    ob = bpy.data.objects[obj_name]
    dg = bpy.context.evaluated_depsgraph_get()
    oe = ob.evaluated_get(dg)
    me = oe.to_mesh()
    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co)
    oe.to_mesh_clear()
    co = co.reshape(-1, 3)
    mw = np.array(ob.matrix_world)
    return co @ mw[:3, :3].T + mw[:3, 3]


def qa_clip(rig, act, planted_fn=None, loop=None, label=None, verbose=True):
    """IK gap (foot target vs the Tarsus tail), planted slide (MTP world motion while planted), loop seam (root-
    relative, every bone head), LOD2 min z of the body (non-foot) and the feet"""
    label = label or act.name
    rig.use_action(act)
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    loop = act.use_cyclic if loop is None else loop
    sc = bpy.context.scene
    poses = rig.clip_poses.get(act.name)
    gap = 0.0; slide = {s: 0.0 for s in SIDES}; prev = {}
    first = last = None
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ae = rig.arm.evaluated_get(dg)
        H = {n: ae.pose.bones[n].head.copy() for n in rig.order}
        mtp = {s: ae.pose.bones[f"Tarsus.{s}"].tail.copy() for s in SIDES}
        if poses is not None and f < len(poses):
            P = poses[f]
            W = T(P.root_pos) @ Rz(P.root_yaw)
            for s in SIDES:
                tg = W @ (P.legs[s].mtp if P.legs[s].mtp is not None else rig.leg[s]["M"])
                gap = max(gap, (mtp[s] - tg).length)
        for s in SIDES:
            if planted_fn and planted_fn(s, f) and planted_fn(s, f - 1) and s in prev:
                slide[s] = max(slide[s], (mtp[s] - prev[s]).length)
            prev[s] = mtp[s]
        rel = {n: H[n] - H["Root"] for n in rig.order}
        if f == f0:
            first = rel
        last = rel
    seam = max((first[n] - last[n]).length for n in rig.order) if loop else 0.0
    res = dict(gap_mm=gap * 1000, slide_mm=max(slide.values()) * 1000, seam_mm=seam * 1000,
               reach_mm=act.get("raven_reach_mm", 0.0))
    if verbose:
        print(f"QA {label}: IK gap {res['gap_mm']:.3f} mm | planted slide {res['slide_mm']:.3f} mm | "
              f"loop seam {res['seam_mm']:.4f} mm | reach {res['reach_mm']:.1f} mm")
    return res
