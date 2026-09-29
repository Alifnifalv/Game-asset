"""Rottweiler animation library: a pose model with analytic leg IK, baked straight to FK quaternion keys.

Every clip is a function frame -> Pose.  DogRig.solve(pose) computes the armature-space matrix of every bone:
  Root      ground transform (root_pos, root_yaw): the root-motion node.
  Hips      body root: body_off (root frame) and body_rot (pitch, roll, yaw) about the COG point.
  spine / neck / head / nose / jaw / tongue / ears / eyes / tail: local rotations (degrees, see `rot`).
  legs      analytic IK per leg from a LegPose (root frame): the MCP/MTP joint position (paw centre), the pastern /
            metatarsus pitch and the toe pitch.  Front legs: the scapula swings with the leg (SCAP_GAIN) about its top.
            UpperArm+Forearm / Thigh+Shin are a 2-bone chain solved in the plane that contains the rest bend (pole =
            the rest elbow/stifle offset carried by the body rotation), so Pose() reproduces the rest pose exactly
            (checked by DogRig.self_test, < 1e-5 m).
There are no constraints anywhere: the bone matrices go straight to keys (every frame, linear).

Sign conventions (FK-checked in self_test):
  body_rot   (pitch + nose down, roll + right side down, yaw + nose to the dog's left)
  rot(p, y, r) on a bone: pitch + = the bone's tip turns DOWN if it points forward, BACK/UP if it hangs down
             (tail lift + = up/back); yaw + = tip to the dog's LEFT (+X); roll + = about the bone's own axis
             (for a forward bone: the right side goes down).
  jaw        degrees open (+ = mouth opens)
  LegPose.pastern  + = flexion (the lower end swings back: carpus / hock folding); toe + = tip down.
Units: meters, degrees, 30 fps. The dog faces -Y.
"""
import math, os, sys
import numpy as np
import bpy
from mathutils import Matrix, Vector, Quaternion

FPS = 30
RIG = "RottweilerRig"
LOD2 = "Rottweiler_LOD2"
COG = Vector((0.0, -0.06, 0.52))          # body rotation pivot (mid trunk)
SCAP_MAX = 35.0                           # deg: the auto scapula swing is clamped to +-SCAP_MAX
SCAP_GAIN = 0.75                          # share of the leg's swing angle taken by the scapula
SLIDE = 0.040                             # max scapula glide toward a far paw (m)
SLIDE_START = 0.010                       # it starts this far before the chain is straight
REACH = 0.9985                            # max fraction of the 2-bone chain length (never fully straight)

LEGS = {
    "FL": dict(side="L", front=True, scap="Scapula.L", upper="UpperArm.L", lower="Forearm.L", foot="FrontFoot.L",
               toe="FrontToe.L"),
    "FR": dict(side="R", front=True, scap="Scapula.R", upper="UpperArm.R", lower="Forearm.R", foot="FrontFoot.R",
               toe="FrontToe.R"),
    "HL": dict(side="L", front=False, scap=None, upper="Thigh.L", lower="Shin.L", foot="HindFoot.L",
               toe="HindToe.L"),
    "HR": dict(side="R", front=False, scap=None, upper="Thigh.R", lower="Shin.R", foot="HindFoot.R",
               toe="HindToe.R"),
}
LOCAL_BONES = ["Spine1", "Spine2", "Spine3", "Neck1", "Neck2", "Head", "Nose", "Jaw", "Tongue1", "Tongue2",
               "Tongue3", "Ear1.L", "Ear2.L", "Ear1.R", "Ear2.R", "Eye.L", "Eye.R",
               "Tail1", "Tail2", "Tail3", "Tail4", "Tail5", "Tail6"]
TAIL = ["Tail1", "Tail2", "Tail3", "Tail4", "Tail5", "Tail6"]


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
    """World rotation for body_rot (pitch + nose down, roll + right side down, yaw + left)."""
    return Rz(yaw) @ Rx(pitch) @ Ry(-roll)


def rot(pitch=0.0, yaw=0.0, roll=0.0):
    """Local rotation of a bone (see the module doc). Bone local X ~ -X world (rolls: dog_stage_b.py), local Z up
    for a forward bone / forward for a hanging bone."""
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


def mix_pose_vals(a, b, t):
    if isinstance(a, (tuple, list)):
        return type(a)(lerp(x, y, t) for x, y in zip(a, b))
    return lerp(a, b, t)


class LegPose:
    """Root-frame target of one leg.  mcp = paw centre joint (MCP front / MTP hind); None = rest position."""
    __slots__ = ("mcp", "pastern", "toe", "scap", "pole", "planted", "local")

    def __init__(self, mcp=None, pastern=0.0, toe=0.0, scap=0.0, pole=0.0, planted=False, local=False):
        """local (0..1): pastern / toe measured in the BODY frame (1: a body rolled onto its side, Death) instead of
        the ground frame (0); poses blend it smoothly"""
        self.mcp = None if mcp is None else Vector(mcp)
        self.pastern, self.toe, self.scap, self.pole, self.planted = pastern, toe, scap, pole, planted
        self.local = local

    def copy(self):
        return LegPose(None if self.mcp is None else self.mcp.copy(), self.pastern, self.toe, self.scap, self.pole,
                       self.planted, self.local)


class Pose:
    def __init__(self):
        self.root_pos = Vector((0, 0, 0))
        self.root_yaw = 0.0
        self.body_off = Vector((0, 0, 0))
        self.body_rot = (0.0, 0.0, 0.0)
        self.spine = {"Spine1": (0, 0, 0), "Spine2": (0, 0, 0), "Spine3": (0, 0, 0)}
        self.neck = {"Neck1": (0, 0, 0), "Neck2": (0, 0, 0)}
        self.head = (0.0, 0.0, 0.0)
        self.nose = 0.0                 # + = muzzle tip up (a sniff / snarl lift)
        self.jaw = 0.0
        self.tongue = (0.0, 0.0, 0.0)   # (out m, curl deg + tip down, side deg + left)
        self.ears = {"L": (0, 0, 0), "R": (0, 0, 0)}     # Ear1 (pitch + tip down/back, yaw, roll)
        self.ear_tip = {"L": 0.0, "R": 0.0}              # Ear2 pitch
        self.eyes = (0.0, 0.0)          # (pitch, yaw) both eyes
        self.tail = [(0.0, 0.0)] * 6    # per bone (pitch + up/back, side + left)
        self.legs = {k: LegPose() for k in LEGS}
        self.extra = {}                 # bone -> Quaternion multiplied onto the local rotation

    def copy(self):
        p = Pose()
        p.root_pos = self.root_pos.copy(); p.root_yaw = self.root_yaw
        p.body_off = self.body_off.copy(); p.body_rot = tuple(self.body_rot)
        p.spine = dict(self.spine); p.neck = dict(self.neck); p.head = tuple(self.head)
        p.nose, p.jaw, p.tongue = self.nose, self.jaw, tuple(self.tongue)
        p.ears = dict(self.ears); p.ear_tip = dict(self.ear_tip); p.eyes = tuple(self.eyes)
        p.tail = list(self.tail)
        p.legs = {k: v.copy() for k, v in self.legs.items()}
        p.extra = dict(self.extra)
        return p


def tail_shape(lift=0.0, side=0.0, curl=0.0, wag=0.0, n=6):
    """Per-bone (pitch, side) from whole-tail parameters: lift/side at the base, curl spread along the tail (+ = the
    tip curls up/back), wag = a side swing whose amplitude grows to the tip."""
    out = []
    for i in range(n):
        f = i / (n - 1)
        out.append((lift * (1.0 if i == 0 else 0.25) + curl * (0.3 + 0.7 * f) / n * 2,
                    side * (1.0 if i == 0 else 0.2) + wag * (0.5 + f) / n * 2))
    return out


def blend(p0, p1, t):
    """Interpolate two poses (legs: positions and angles)."""
    if t <= 0:
        return p0.copy()
    if t >= 1:
        return p1.copy()
    p = p0.copy()
    p.root_pos = p0.root_pos.lerp(p1.root_pos, t); p.root_yaw = lerp(p0.root_yaw, p1.root_yaw, t)
    p.body_off = p0.body_off.lerp(p1.body_off, t); p.body_rot = mix_pose_vals(p0.body_rot, p1.body_rot, t)
    p.spine = {k: mix_pose_vals(p0.spine[k], p1.spine[k], t) for k in p0.spine}
    p.neck = {k: mix_pose_vals(p0.neck[k], p1.neck[k], t) for k in p0.neck}
    p.head = mix_pose_vals(p0.head, p1.head, t)
    p.nose = lerp(p0.nose, p1.nose, t); p.jaw = lerp(p0.jaw, p1.jaw, t)
    p.tongue = mix_pose_vals(p0.tongue, p1.tongue, t)
    p.ears = {k: mix_pose_vals(p0.ears[k], p1.ears[k], t) for k in p0.ears}
    p.ear_tip = {k: lerp(p0.ear_tip[k], p1.ear_tip[k], t) for k in p0.ear_tip}
    p.eyes = mix_pose_vals(p0.eyes, p1.eyes, t)
    p.tail = [mix_pose_vals(a, b, t) for a, b in zip(p0.tail, p1.tail)]
    for k in LEGS:
        a, b = p0.legs[k], p1.legs[k]
        rest = None
        am = a.mcp if a.mcp is not None else None
        bm = b.mcp if b.mcp is not None else None
        if am is None and bm is None:
            m = None
        else:
            m = (am if am is not None else _REST_MCP[k]).lerp(bm if bm is not None else _REST_MCP[k], t)
        p.legs[k] = LegPose(m, lerp(a.pastern, b.pastern, t), lerp(a.toe, b.toe, t), lerp(a.scap, b.scap, t),
                            lerp(a.pole, b.pole, t), a.planted and b.planted, lerp(float(a.local), float(b.local), t))
    keys = set(p0.extra) | set(p1.extra)
    p.extra = {k: p0.extra.get(k, Quaternion()).slerp(p1.extra.get(k, Quaternion()), t) for k in keys}
    return p


_REST_MCP = {}
_REST_TIP = {}


def rolled_mcp(leg, mcp, angle):
    """MCP position of a paw planted at `mcp` (rest height) rolled over its toe tip by `angle` deg (heel up)"""
    tip = mcp + _REST_TIP[leg]
    rel = mcp - tip
    c, s_ = math.cos(rad(angle)), math.sin(rad(angle))
    return tip + Vector((rel.x, rel.y * c - rel.z * s_, rel.y * s_ + rel.z * c))


class DogRig:
    def __init__(self, arm=None):
        self.arm = arm or bpy.data.objects[RIG]
        self.sc = bpy.context.scene
        bones = self.arm.data.bones
        self.order = [b.name for b in bones]                 # parents before children (creation order)
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
        self._prev_n = None          # set to {} while a clip is solved frame by frame (leg plane continuity)
        # legs: rest geometry for the IK
        self.leg = {}
        for k, L in LEGS.items():
            up, lo, ft, to = L["upper"], L["lower"], L["foot"], L["toe"]
            S = self.head(up); K = self.head(lo); C = self.head(ft); M = self.head(to); E = self.tail(to)
            n = (C - S).cross(K - S).normalized()             # leg plane normal (rest)
            # pole: rest knee offset from the S-C line, in the body (Hips) frame
            u = (C - S).normalized()
            pole = (K - S) - u * (K - S).dot(u)
            info = dict(S=S, K=K, C=C, M=M, E=E, n=n, pole=pole.normalized(),
                        L1=(K - S).length, L2=(C - K).length, L3=(M - C).length,
                        dir_foot=(M - C).normalized(), dir_toe=(E - M).normalized())
            # rest rotation of each chain bone relative to the frame built from (its direction, the plane normal)
            for b, (a0, a1) in ((up, (S, K)), (lo, (K, C)), (ft, (C, M)), (to, (M, E))):
                F = self._frame((a1 - a0).normalized(), n)
                info["rel_" + b] = F.inverted() @ self.rest[b].to_3x3()
            self.leg[k] = info
            _REST_MCP[k] = M.copy()
            _REST_TIP[k] = E - M

    # ---- helpers
    def head(self, b):
        return self.rest[b].to_translation()

    def tail(self, b):
        return (self.rest[b] @ Vector((0, self.length[b], 0, 1))).to_3d()

    @staticmethod
    def _frame(y, n):
        """3x3 frame: Y = y, X = n made orthogonal to y, Z = X x Y."""
        x = (n - y * n.dot(y))
        if x.length < 1e-9:
            x = Vector((1, 0, 0)) - y * y.x
        x.normalize()
        z = x.cross(y)
        return Matrix((x, y, z)).transposed()

    def rest_mcp(self, leg):
        return self.leg[leg]["M"].copy()

    # ---- the solver
    def solve(self, P):
        """armature-space 4x4 matrix of every bone for the pose P; also self.last_reach[leg] (> 0 = clamped)."""
        M = {}
        W = T(P.root_pos) @ Rz(P.root_yaw)                           # root frame -> armature
        self.W = W
        M["Root"] = W @ self.rest["Root"]
        B = body_matrix(*P.body_rot)
        hips_world = W @ T(P.body_off) @ T(COG) @ B @ T(-COG)
        M["Hips"] = hips_world @ self.rest["Hips"]
        self.body_world = hips_world
        local = {}
        for n in ("Spine1", "Spine2", "Spine3"):
            local[n] = rot(*P.spine[n])
        for n in ("Neck1", "Neck2"):
            local[n] = rot(*P.neck[n])
        local["Head"] = rot(*P.head)
        local["Nose"] = rot(P.nose)
        local["Jaw"] = rot(-P.jaw)
        out, curl, side = P.tongue
        local["Tongue1"] = rot(curl * 0.2, side * 0.4)
        local["Tongue2"] = rot(curl * 0.35, side * 0.3)
        local["Tongue3"] = rot(curl * 0.45, side * 0.3)
        for s in "LR":
            local[f"Ear1.{s}"] = rot(*P.ears[s])
            local[f"Ear2.{s}"] = rot(P.ear_tip[s])
            local[f"Eye.{s}"] = rot(P.eyes[0], P.eyes[1])
        for i, n in enumerate(TAIL):
            local[n] = rot(P.tail[i][0], P.tail[i][1])
        for n, q in P.extra.items():
            local[n] = local.get(n, Quaternion()) @ q
        tongue_off = {"Tongue1": Vector((0, out, 0))}                 # slide along the bone (local Y)
        self.last_reach = {}
        self.last_comp = {k: 0.0 for k in LEGS}
        for n in self.order:
            if n in M:
                continue
            p = self.par[n]
            if n in local:
                base = M[p] @ self.relm[n]
                loc = tongue_off.get(n)
                Lm = local[n].to_matrix().to_4x4()
                if loc is not None:
                    Lm = T(loc) @ Lm
                M[n] = base @ Lm
        for k in LEGS:
            self._solve_leg(k, P.legs[k], M, B)
        # anything left (no local rotation given): rigid on the parent
        for n in self.order:
            if n not in M:
                M[n] = M[self.par[n]] @ self.relm[n]
        return M

    def _solve_leg(self, k, lp, M, Bbody):
        L = LEGS[k]; I = self.leg[k]
        W = self.W
        W3 = W.to_3x3()
        body3 = self.body_world.to_3x3()
        # target (root frame -> armature)
        m_rf = lp.mcp if lp.mcp is not None else I["M"]
        mcp = W @ m_rf
        # pastern / toe angles about the ground's lateral axis, or the body's (local weight 0..1, blended smoothly:
        # a leg lying on the body's side needs the body frame, a standing one the ground frame)
        def dirs(F3):
            lat = F3 @ Vector((1, 0, 0))
            return ((Matrix.Rotation(rad(lp.pastern), 3, lat) @ (F3 @ I["dir_foot"])).normalized(),
                    (Matrix.Rotation(rad(lp.toe), 3, lat) @ (F3 @ I["dir_toe"])).normalized())
        wl = float(lp.local)
        if wl <= 0.0:
            dfoot, dtoe = dirs(W3)
        elif wl >= 1.0:
            dfoot, dtoe = dirs(body3)
        else:
            (g1, g2), (b1, b2) = dirs(W3), dirs(body3)
            dfoot = g1.slerp(b1, wl).normalized(); dtoe = g2.slerp(b2, wl).normalized()
        C = mcp - dfoot * I["L3"]
        # the chain root
        if L["front"]:
            sc = L["scap"]
            base = M[self.par[sc]] @ self.relm[sc]
            # auto swing: angle of the target line (shoulder -> carpus) about the lateral axis vs rest, in the body frame
            S_rest_now = (base @ Vector((0, self.length[sc], 0, 1))).to_3d()
            v_now = (body3.inverted() @ (C - S_rest_now))
            v_rest = I["C"] - I["S"]
            # angle from straight down, + backward; the forward swing of the target line is rest - now
            fwd = math.degrees(math.atan2(v_rest.y, -v_rest.z) - math.atan2(v_now.y, max(-v_now.z, 0.05)))
            fwd = (fwd + 180.0) % 360.0 - 180.0
            # clamped: a target beside or above the shoulder (a body rolled onto its side) must not spin the scapula
            sw = max(-SCAP_MAX, min(SCAP_MAX, SCAP_GAIN * fwd)) + lp.scap
            M[sc] = base @ rot(-sw).to_matrix().to_4x4()             # + sw = scapula lower end forward
            S = (M[sc] @ Vector((0, self.length[sc], 0, 1))).to_3d()
            # thoracic sling: no collarbone, the scapula glides on the chest wall toward a far target (<= SLIDE)
            ex = (C - S).length - REACH * (I["L1"] + I["L2"]) + SLIDE_START
            if ex > 0:
                dv = (C - S).normalized() * min(ex, SLIDE)
                M[sc] = T(dv) @ M[sc]
                S = S + dv
        else:
            S = (M[self.par[L["upper"]]] @ self.relm[L["upper"]]).to_translation()
        L1, L2 = I["L1"], I["L2"]
        ref = self._prev_n.get(k) if self._prev_n is not None else None

        def two_bone(C):
            d = C - S
            dl = d.length
            mx = REACH * (L1 + L2); mn = abs(L1 - L2) * 1.02
            self.last_reach[k] = dl - mx
            self.last_comp[k] = 0.0
            if dl > mx:
                C = S + d * (mx / dl); d = C - S; dl = mx
            elif dl < mn:
                self.last_comp[k] = mn - dl                 # too compressed (the QA IK gap shows it)
                C = S + d * (mn / dl); d = C - S; dl = mn
            u = d / dl
            pole = body3 @ I["pole"]
            if lp.pole:
                pole = Matrix.Rotation(rad(lp.pole), 3, u) @ pole
            v = pole - u * pole.dot(u)
            v.normalize()
            ca = (L1 * L1 + dl * dl - L2 * L2) / (2 * L1 * dl)
            ca = min(max(ca, -1.0), 1.0)
            sa = math.sqrt(1 - ca * ca)
            K = S + (u * ca + v * sa) * L1
            n = (C - S).cross(K - S).normalized()
            # sign: continuous with the previous frame of the clip being baked (a leg plane that turns through 90 deg
            # relative to the body, e.g. a body rolling onto its side, must not flip); else the rest side
            if n.dot(ref if ref is not None else body3 @ I["n"]) < 0:
                n = -n
            return C, K, n

        def into_plane(dv, n, lim=0.3):
            """the carpus / hock and the toes are hinges: limit the out-of-plane part of a direction to `lim`
            (the rest pose is far inside that, so Pose() stays exact; a far-out direction no longer degenerates
            the bone frame)"""
            o = dv.dot(n)
            if abs(o) <= lim:
                return dv
            return (dv - n * (o - math.copysign(lim, o))).normalized()

        C, K, n = two_bone(C)
        df2 = into_plane(dfoot, n)
        if (df2 - dfoot).length > 1e-9:
            dfoot = df2
            C, K, n = two_bone(mcp - dfoot * I["L3"])
        dtoe = into_plane(dtoe, n)
        if self._prev_n is not None:
            self._prev_n[k] = n.copy()

        def place(bone, a0, a1):
            F = self._frame((a1 - a0).normalized(), n)
            R = F @ I["rel_" + bone]
            m = R.to_4x4(); m.translation = a0
            M[bone] = m
        place(L["upper"], S, K)
        place(L["lower"], K, C)
        place(L["foot"], C, mcp)
        place(L["toe"], mcp, mcp + dtoe)

    # ---- matrices -> local basis
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
            pb = self.arm.pose.bones[n]
            pb.matrix_basis = m
        return B

    # ---- actions
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

    def reach_pass(self, poses, loop, iters=5, window=3):
        """Lower the body (body_off.z) wherever a paw target is out of reach, so planted paws never slide; the
        correction is spread over +-window frames with a raised-cosine falloff (cyclic for loops: frame n-1 is the
        same instant as frame 0 and gets the same correction). Returns the per-frame drop (m)."""
        n = len(poses)
        m = n - 1 if (loop and n > 1) else n          # unique frames
        total = np.zeros(n)
        for _ in range(iters):
            need = np.zeros(m)
            self._prev_n = {}
            for i in range(m):
                self.solve(poses[i])
                need[i] = max(0.0, max(self.last_reach.values()) + 0.0005)
            if need.max() <= 0.0005:
                break
            idx = np.arange(m)
            mx = need.copy()
            for d in range(1, window + 1):
                wgt = 0.5 + 0.5 * math.cos(math.pi * d / (window + 1))
                for sgn in (-1, 1):
                    j = (idx + sgn * d) % m if loop else np.clip(idx + sgn * d, 0, m - 1)
                    mx = np.maximum(mx, need[j] * wgt)
            corr = np.append(mx, mx[0]) if m < n else mx
            for i, P in enumerate(poses):
                P.body_off = P.body_off + Vector((0, 0, -corr[i] * 1.05))
            total += corr * 1.05
        self._prev_n = None
        return total

    def make_clip(self, name, frames, pose_fn, loop=True, reach=True):
        """pose_fn(f) -> Pose for f in 0..frames (inclusive); loops: frame `frames` must equal frame 0."""
        act = self.new_action(name)
        poses = [pose_fn(f) for f in range(frames + 1)]
        drop = self.reach_pass(poses, loop) if reach else np.zeros(len(poses))
        samples = {n: [] for n in self.order}
        reach = {k: -1.0 for k in LEGS}
        self._prev_n = {}
        for P in poses:
            B = self.basis(self.solve(P))
            for k in LEGS:
                reach[k] = max(reach[k], self.last_reach[k])
            for n in self.order:
                loc, q, _ = B[n].decompose()
                samples[n].append((loc, q))
        self._prev_n = None
        self.write_curves(act, samples)
        act.use_frame_range = True
        act.frame_start, act.frame_end = 0, frames
        act.use_cyclic = loop
        act["dog_reach_mm"] = max(reach.values()) * 1000
        act["dog_body_drop_mm"] = float(np.max(drop)) * 1000
        self._poses = poses
        self.clip_poses[name] = poses
        return act

    # ---- self test: Pose() is the rest pose
    def self_test(self):
        B = self.basis(self.solve(Pose()))
        return max(abs(m[i][j] - (1.0 if i == j else 0.0)) for m in B.values() for i in range(4) for j in range(4))


# ================================================================================================= QA
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


_PAW_MASK = {}


def paw_mask(obj_name=LOD2):
    """vertices weighted mostly to paw bones (FrontFoot/FrontToe/HindFoot/HindToe) - allowed to touch the ground"""
    if obj_name in _PAW_MASK:
        return _PAW_MASK[obj_name]
    ob = bpy.data.objects[obj_name]
    gi = {g.index: g.name for g in ob.vertex_groups}
    m = np.zeros(len(ob.data.vertices), bool)
    for v in ob.data.vertices:
        w = sum(g.weight for g in v.groups if any(s in gi[g.group] for s in ("Toe", "Foot")))
        m[v.index] = w > 0.5
    _PAW_MASK[obj_name] = m
    return m


def qa_clip(rig, act, planted_fn=None, loop=None, label=None, ground=True, verbose=True):
    """Evaluate a clip in Blender: IK gap (paw joint vs target, from the stored poses), planted slide (world MCP
    motion while planted_fn(leg, f)), loop seam, LOD2 ground clearance (non-paw min z / paw min z).
    Returns a dict and prints one line per metric."""
    label = label or act.name
    rig.use_action(act)
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    loop = act.use_cyclic if loop is None else loop
    sc = bpy.context.scene
    toes = {k: LEGS[k]["toe"] for k in LEGS}
    gap = 0.0; slide = {k: 0.0 for k in LEGS}; prev = {}
    zmin_body, zmin_paw = 1e9, 1e9
    poses = rig.clip_poses.get(act.name)
    paws = paw_mask() if ground else None
    first = last = None
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        H = eval_bone_heads(rig.arm, list(toes.values()) + ["Root"])
        if poses is not None and f < len(poses):
            P = poses[f]
            W = T(P.root_pos) @ Rz(P.root_yaw)
            for k in LEGS:
                tgt = W @ (P.legs[k].mcp if P.legs[k].mcp is not None else rig.leg[k]["M"])
                gap = max(gap, (H[toes[k]] - tgt).length)
        for k in LEGS:
            if planted_fn and planted_fn(k, f) and planted_fn(k, f - 1) and k in prev:
                slide[k] = max(slide[k], (H[toes[k]] - prev[k]).length)
            prev[k] = H[toes[k]]
        if ground:
            V = lod_vertices()
            zmin_body = min(zmin_body, V[~paws, 2].min()); zmin_paw = min(zmin_paw, V[paws, 2].min())
        if f == f0:
            first = {k: H[toes[k]] - H["Root"] for k in LEGS}      # root-relative: root motion is not a seam
        last = {k: H[toes[k]] - H["Root"] for k in LEGS}
    seam = max((first[k] - last[k]).length for k in LEGS) if loop else 0.0
    res = dict(gap_mm=gap * 1000, slide_mm=max(slide.values()) * 1000, seam_mm=seam * 1000,
               body_min_cm=zmin_body * 100, paw_min_cm=zmin_paw * 100, reach_mm=act.get("dog_reach_mm", 0.0))
    if verbose:
        print(f"QA {label}: IK gap {res['gap_mm']:.3f} mm | planted slide {res['slide_mm']:.2f} mm | "
              f"loop seam {res['seam_mm']:.3f} mm | reach {res['reach_mm']:.1f} mm | LOD2 min z body "
              f"{res['body_min_cm']:.2f} cm, paws {res['paw_min_cm']:.2f} cm")
    return res
