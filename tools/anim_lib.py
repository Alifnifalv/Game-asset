"""Calf animation library (Blender 5, headless bpy).

Builds clips on the calf rig (build/stage_b.blend conventions: CalfRig, meters, faces -Y, Z up, 30 fps).

How a clip is made
  1. For every frame the clip function returns a `Pose` (root transform, body offsets, spine/neck/head/
     jaw/ear/tail rotations, foot targets + hoof flex, scapula glide, femur swing).
  2. The pose is turned into bone basis matrices with exact forward kinematics (no depsgraph round trips)
     and keyed on every bone.
  3. Leg IK constraints (lower leg -> foot bone, pole = PoleTarget bones, pole angle auto-solved so IK
     reproduces the rest pose) solve the leg chains; the result is baked to FK quaternion keys and the
     constraints are removed. Exported clips are pure FK and play on any engine.

Gaits use a world-space foot planner: a planted foot stays exactly where it touched down (zero slide in
root-motion clips); in-place variants are the same clip without Root keys (feet then slide under the body
like on a treadmill, which is what in-place locomotion needs).
"""
import math, os, sys
from dataclasses import dataclass, field
import bpy
from mathutils import Matrix, Quaternion, Vector, Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anim_gait as G

FPS = 30
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))

LEGS = {
    "LF": dict(chain=("FrontUpperLeg.L", "FrontLowerLeg.L"), foot="IKFrontLeg.L", toe="FF.L", pole="PoleTarget.L", top="FrontShoulder.L"),
    "RF": dict(chain=("FrontUpperLeg.R", "FrontLowerLeg.R"), foot="IKFrontLeg.R", toe="FF.R", pole="PoleTarget.R", top="FrontShoulder.R"),
    "LH": dict(chain=("BackUpperLeg.L", "BackLowerLeg.L"), foot="IKBackLeg.L", toe="FFB.L", pole="PoleTargetBack.L", top="BackLeg.L"),
    "RH": dict(chain=("BackUpperLeg.R", "BackLowerLeg.R"), foot="IKBackLeg.R", toe="FFB.R", pole="PoleTargetBack.R", top="BackLeg.R"),
}
SPINE = ("Back", "Torso", "Torso2", "Torso3")
NECK = ("Neck1", "Neck2", "Neck3")
TAIL = tuple(f"Tail{i}" for i in range(1, 8))


def lerp(a, b, t):
    return a + (b - a) * t


def ease(t, kind="inout"):
    t = min(1.0, max(0.0, t))
    if kind == "linear": return t
    if kind == "in": return t * t
    if kind == "out": return 1 - (1 - t) * (1 - t)
    return t * t * (3 - 2 * t)


@dataclass
class Pose:
    root_pos: Vector = field(default_factory=lambda: Vector((0, 0, 0)))
    root_yaw: float = 0.0                      # deg, + = turn left (CCW seen from above)
    body_off: Vector = field(default_factory=lambda: Vector((0, 0, 0)))   # COG offset in root frame (m)
    body_rot: Vector = field(default_factory=lambda: Vector((0, 0, 0)))   # (pitch + nose down, roll + right side down, yaw + left) deg
    spine: dict = field(default_factory=dict)  # bone -> (pitch, yaw, roll) deg in the bone's rest frame axes (X lateral, Z up)
    neck: list = field(default_factory=lambda: [0.0, 0.0, 0.0])        # pitch per neck bone (+ = head lower)
    neck_yaw: list = field(default_factory=lambda: [0.0, 0.0, 0.0])    # yaw per neck bone (+ = left)
    head: Vector = field(default_factory=lambda: Vector((0, 0, 0)))    # (pitch + down, yaw + left, roll) deg
    jaw: float = 0.0                           # deg open
    ears: dict = field(default_factory=lambda: {"L": Vector((0, 0, 0)), "R": Vector((0, 0, 0))})  # (fwd/back, up/down, twist) deg
    tail: list = field(default_factory=lambda: [(0.0, 0.0)] * 7)       # (side deg + left, lift deg + up) per segment
    feet: dict = field(default_factory=dict)   # leg -> Vector world-space offset from rest (in ROOT frame) (m)
    feet_world: dict = field(default_factory=dict)   # leg -> absolute armature-space position (overrides `feet`)
    flex: dict = field(default_factory=dict)   # leg -> hoof flex deg (+ = toe back/up)
    glide: dict = field(default_factory=dict)  # front leg -> scapula glide (m, + = forward)
    femur: dict = field(default_factory=dict)  # hind leg -> femur swing (deg, + = foot forward)
    top_rot: dict = field(default_factory=dict)  # leg -> (pitch, yaw, roll) extra on FrontShoulder/BackLeg (deg)


def blend_pose(a: Pose, b: Pose, t: float) -> Pose:
    """component-wise interpolation of two poses"""
    def lv(u, v): return u.lerp(v, t)
    def ld(da, db, fn, default):
        keys = set(da) | set(db)
        return {k: fn(da.get(k, default()), db.get(k, default())) for k in keys}
    out = Pose()
    out.root_pos = lv(a.root_pos, b.root_pos); out.root_yaw = lerp(a.root_yaw, b.root_yaw, t)
    out.body_off = lv(a.body_off, b.body_off); out.body_rot = lv(a.body_rot, b.body_rot)
    out.spine = ld(a.spine, b.spine, lambda u, v: tuple(lerp(p, q, t) for p, q in zip(u, v)), lambda: (0.0, 0.0, 0.0))
    out.neck = [lerp(p, q, t) for p, q in zip(a.neck, b.neck)]
    out.neck_yaw = [lerp(p, q, t) for p, q in zip(a.neck_yaw, b.neck_yaw)]
    out.head = lv(a.head, b.head); out.jaw = lerp(a.jaw, b.jaw, t)
    out.ears = {s: lv(a.ears[s], b.ears[s]) for s in ("L", "R")}
    out.tail = [(lerp(p[0], q[0], t), lerp(p[1], q[1], t)) for p, q in zip(a.tail, b.tail)]
    out.feet = ld(a.feet, b.feet, lambda u, v: u.lerp(v, t), lambda: Vector((0, 0, 0)))
    if a.feet_world or b.feet_world:
        out.feet_world = ld(a.feet_world, b.feet_world, lambda u, v: u.lerp(v, t), lambda: Vector((0, 0, 0)))
    out.flex = ld(a.flex, b.flex, lambda u, v: lerp(u, v, t), lambda: 0.0)
    out.glide = ld(a.glide, b.glide, lambda u, v: lerp(u, v, t), lambda: 0.0)
    out.femur = ld(a.femur, b.femur, lambda u, v: lerp(u, v, t), lambda: 0.0)
    out.top_rot = ld(a.top_rot, b.top_rot, lambda u, v: tuple(lerp(p, q, t) for p, q in zip(u, v)), lambda: (0.0, 0.0, 0.0))
    return out


class Calf:
    def __init__(self, blend):
        bpy.ops.wm.open_mainfile(filepath=blend)
        self.sc = bpy.context.scene
        self.sc.render.fps, self.sc.render.fps_base = FPS, 1.0
        self.arm = bpy.data.objects["CalfRig"]
        self.bones = self.arm.data.bones
        self.rest = {b.name: b.matrix_local.copy() for b in self.bones}
        self.par = {b.name: (b.parent.name if b.parent else None) for b in self.bones}
        order, seen = [], set()
        def visit(n):
            if n in seen: return
            if self.par[n]: visit(self.par[n])
            seen.add(n); order.append(n)
        for b in self.bones: visit(b.name)
        self.order = order
        for pb in self.arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
        self.cog = Vector((0, -0.05, 0.68))     # body pitch/roll pivot (m)
        self.pole_angle = {}
        self.withers = self.rest["Torso3"].translation.z + 0.3

    # ---------------------------------------------------------------- FK maths
    def rel(self, n):
        p = self.par[n]
        return (self.rest[p].inverted() @ self.rest[n]) if p else self.rest[n]

    def fk(self, basis):
        """basis: bone -> Matrix(4x4); returns armature-space pose matrices"""
        pose = {}
        for n in self.order:
            p = self.par[n]
            m = (pose[p] @ self.rel(n)) if p else self.rest[n]
            pose[n] = m @ basis.get(n, Matrix.Identity(4))
        return pose

    def basis_for(self, n, pose, target):
        """basis matrix that puts bone n at armature-space matrix `target` given parent pose"""
        p = self.par[n]
        m = (pose[p] @ self.rel(n)) if p else self.rest[n]
        return m.inverted() @ target

    def rot_about(self, n, axis_arm, deg):
        """local rotation of bone n about an ARMATURE-space axis (as seen in the rest pose)"""
        ax = (self.rest[n].to_3x3().inverted() @ axis_arm).normalized()
        return Quaternion(ax, math.radians(deg))

    def rest_head(self, n):
        return self.rest[n].translation.copy()

    # ---------------------------------------------------------------- pose -> basis
    def pose_to_basis(self, P: Pose):
        B = {}
        rootT = Matrix.Translation(P.root_pos) @ Matrix.Rotation(math.radians(P.root_yaw), 4, "Z")
        # Root: armature-space target = rootT @ rest
        B["Root"] = self.rest["Root"].inverted() @ (rootT @ self.rest["Root"])
        # Body: offset + rotation about the COG, expressed in the root frame
        pr, rr, yr = (math.radians(v) for v in P.body_rot)
        R = (Matrix.Rotation(yr, 4, "Z") @ Matrix.Rotation(pr, 4, "X") @ Matrix.Rotation(-rr, 4, "Y"))
        bodyT = rootT @ Matrix.Translation(P.body_off) @ Matrix.Translation(self.cog) @ R @ Matrix.Translation(-self.cog)
        pose = self.fk(B)
        B["Body"] = self.basis_for("Body", pose, bodyT @ self.rest["Body"])
        # spine / neck / head: local rotations about rest-frame armature axes
        def q_pyr(n, pitch=0.0, yaw=0.0, roll=0.0):
            return (self.rot_about(n, Z, yaw) @ self.rot_about(n, X, pitch) @ self.rot_about(n, Y, roll))
        for n, (pt, yw, rl) in P.spine.items():
            B[n] = q_pyr(n, pt, yw, rl).to_matrix().to_4x4()
        for i, n in enumerate(NECK):
            B[n] = q_pyr(n, P.neck[i], P.neck_yaw[i]).to_matrix().to_4x4()
        B["Head"] = q_pyr("Head", P.head.x, P.head.y, P.head.z).to_matrix().to_4x4()
        B["Jaw"] = self.rot_about("Jaw", X, -P.jaw).to_matrix().to_4x4()    # opening = chin down
        for s in ("L", "R"):
            e = P.ears[s]; n = "Ear." + s
            sgn = 1 if s == "L" else -1
            q = self.rot_about(n, Z, -sgn * e.x) @ self.rot_about(n, Y, sgn * e.y) @ self.rot_about(n, X, e.z)
            B[n] = q.to_matrix().to_4x4()
        for i, n in enumerate(TAIL):
            side, lift = P.tail[i]
            B[n] = (self.rot_about(n, Z, side) @ self.rot_about(n, X, lift)).to_matrix().to_4x4()
        # scapula glide (front) / femur swing (hind) / extra top rotations
        for leg, d in LEGS.items():
            top = d["top"]
            m = Matrix.Identity(4)
            if leg.endswith("F"):
                g = P.glide.get(leg, 0.0)
                m = Matrix.Translation(self.rest[top].to_3x3().inverted() @ Vector((0, -g, 0)))
            else:
                m = self.rot_about(top, X, -P.femur.get(leg, 0.0)).to_matrix().to_4x4()
            if leg in P.top_rot:
                pt, yw, rl = P.top_rot[leg]
                m = m @ q_pyr(top, pt, yw, rl).to_matrix().to_4x4()
            B[top] = m
        # feet (children of Root): position target + hoof flex about the fetlock
        pose = self.fk(B)
        for leg, d in LEGS.items():
            f = d["foot"]
            h = self.rest_head(f)
            if leg in P.feet_world:
                tgt = P.feet_world[leg]
                M = Matrix.Translation(tgt) @ Matrix.Rotation(math.radians(P.root_yaw), 4, "Z") @ \
                    Matrix.Rotation(math.radians(P.flex.get(leg, 0.0)), 4, "X") @ Matrix.Translation(-h) @ self.rest[f]
            else:
                off = P.feet.get(leg, Vector((0, 0, 0)))
                M = rootT @ Matrix.Translation(h + off) @ Matrix.Rotation(math.radians(P.flex.get(leg, 0.0)), 4, "X") \
                    @ Matrix.Translation(-h) @ self.rest[f]
            B[f] = self.basis_for(f, pose, M)
            fl = P.flex.get(leg, 0.0)
            B[d["toe"]] = self.rot_about(d["toe"], X, 0.35 * fl).to_matrix().to_4x4()
        return B

    # ---------------------------------------------------------------- IK
    def add_ik(self):
        cons = {}
        for leg, d in LEGS.items():
            pb = self.arm.pose.bones[d["chain"][-1]]
            for c in list(pb.constraints):
                pb.constraints.remove(c)
            c = pb.constraints.new("IK")
            c.target, c.subtarget = self.arm, d["foot"]
            c.pole_target, c.pole_subtarget = self.arm, d["pole"]
            c.chain_count, c.use_tail, c.use_stretch = 2, True, False
            c.iterations = 500
            cons[leg] = c
        self._solve_poles(cons)
        return cons

    def _chain_drift(self, leg):
        dg = bpy.context.evaluated_depsgraph_get(); dg.update()
        ae = self.arm.evaluated_get(dg)
        worst = 0.0
        for n in LEGS[leg]["chain"]:
            a = ae.pose.bones[n].matrix.to_quaternion(); b = self.rest[n].to_quaternion()
            worst = max(worst, math.degrees(a.rotation_difference(b).angle))
        return worst

    def _solve_poles(self, cons):
        for pb in self.arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        if self.arm.animation_data: self.arm.animation_data.action = None
        for leg, c in cons.items():
            best = (1e9, 0.0)
            for deg in range(-180, 180, 2):
                c.pole_angle = math.radians(deg)
                e = self._chain_drift(leg)
                if e < best[0]: best = (e, deg)
            lo = best[1]
            for k in range(-40, 41):
                deg = lo + k * 0.05
                c.pole_angle = math.radians(deg)
                e = self._chain_drift(leg)
                if e < best[0]: best = (e, deg)
            c.pole_angle = math.radians(best[1])
            self.pole_angle[leg] = best
            print(f"  IK {leg}: pole angle {best[1]:.2f} deg, rest drift {best[0]:.4f} deg")

    def remove_ik(self):
        for d in LEGS.values():
            pb = self.arm.pose.bones[d["chain"][-1]]
            for c in list(pb.constraints):
                pb.constraints.remove(c)

    # ---------------------------------------------------------------- clip writer
    def make_clip(self, name, frames, pose_fn, keep_root=True, loop=True):
        """pose_fn(frame) -> Pose for frame in 0..frames (inclusive). Writes action `name`."""
        old = bpy.data.actions.get(name)
        if old: bpy.data.actions.remove(old)
        act = bpy.data.actions.new(name)
        self.arm.animation_data_create()
        self.arm.animation_data.action = act
        cons = self.add_ik()
        chain_bones = [n for d in LEGS.values() for n in d["chain"]]
        keyed = [n for n in self.order if n not in chain_bones]
        for f in range(frames + 1):
            B = self.pose_to_basis(pose_fn(f))
            for n in keyed:
                pb = self.arm.pose.bones[n]
                m = B.get(n, Matrix.Identity(4))
                loc, rot, scl = m.decompose()
                pb.location, pb.rotation_quaternion, pb.scale = loc, rot, Vector((1, 1, 1))
                pb.keyframe_insert("location", frame=f, group=n)
                pb.keyframe_insert("rotation_quaternion", frame=f, group=n)
        # evaluate IK per frame and bake the leg chains to FK
        baked = {n: [] for n in chain_bones}
        for f in range(frames + 1):
            self.sc.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            ae = self.arm.evaluated_get(dg)
            for n in chain_bones:
                pbe = ae.pose.bones[n]
                par = ae.pose.bones[self.par[n]].matrix
                local = (par @ self.rel(n)).inverted() @ pbe.matrix
                baked[n].append(local.to_quaternion())
        self.remove_ik()
        for n, qs in baked.items():
            pb = self.arm.pose.bones[n]
            prev = None
            for f, q in enumerate(qs):
                if prev is not None and prev.dot(q) < 0: q = -q
                prev = q
                pb.location, pb.rotation_quaternion = Vector((0, 0, 0)), q
                pb.keyframe_insert("location", frame=f, group=n)
                pb.keyframe_insert("rotation_quaternion", frame=f, group=n)
        # quaternion hemisphere continuity + linear interpolation (every frame is keyed)
        for l in act.layers:
            for st in l.strips:
                for cb in st.channelbags:
                    for fc in cb.fcurves:
                        for kp in fc.keyframe_points: kp.interpolation = "LINEAR"
        self._fix_quat_flips(act)
        if not keep_root:
            self._strip_root(act)
        act.use_frame_range = True
        act.frame_start, act.frame_end = 0, frames
        act.use_cyclic = loop
        act.use_fake_user = True
        return act

    def _fix_quat_flips(self, act):
        for l in act.layers:
            for st in l.strips:
                for cb in st.channelbags:
                    by_bone = {}
                    for fc in cb.fcurves:
                        if fc.data_path.endswith("rotation_quaternion"):
                            by_bone.setdefault(fc.data_path, [None] * 4)[fc.array_index] = fc
                    for fcs in by_bone.values():
                        if None in fcs: continue
                        n = len(fcs[0].keyframe_points)
                        prev = None
                        for i in range(n):
                            q = Quaternion([fcs[j].keyframe_points[i].co[1] for j in range(4)])
                            if prev is not None and prev.dot(q) < 0:
                                for j in range(4):
                                    fcs[j].keyframe_points[i].co[1] *= -1
                                q = -q
                            prev = q
                        for fc in fcs: fc.update()

    def _strip_root(self, act):
        for l in act.layers:
            for st in l.strips:
                for cb in st.channelbags:
                    for fc in list(cb.fcurves):
                        if fc.data_path.startswith('pose.bones["Root"]'):
                            val = 1.0 if (fc.data_path.endswith("rotation_quaternion") and fc.array_index == 0) else 0.0
                            for kp in fc.keyframe_points:
                                kp.co[1] = val; kp.handle_left[1] = val; kp.handle_right[1] = val
                            fc.update()

    def duplicate_in_place(self, act, name):
        """copy of a root-motion clip with the Root bone frozen at the origin"""
        old = bpy.data.actions.get(name)
        if old: bpy.data.actions.remove(old)
        cp = act.copy(); cp.name = name
        self._strip_root(cp)
        cp.use_fake_user = True
        return cp

    # ---------------------------------------------------------------- QA
    def hoof_positions(self, act, frames):
        """world positions of the 4 fetlocks + hoof tips per frame"""
        self.arm.animation_data.action = act
        out = []
        for f in range(frames + 1):
            self.sc.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get(); ae = self.arm.evaluated_get(dg)
            row = {}
            for leg, d in LEGS.items():
                row[leg] = (ae.matrix_world @ ae.pose.bones[d["foot"]].head, ae.matrix_world @ ae.pose.bones[d["toe"]].tail,
                            ae.matrix_world @ ae.pose.bones[d["chain"][-1]].tail)
            out.append(row)
        return out

    def qa(self, act, frames, planted_fn=None, label=""):
        """foot/IK gap, slide of planted feet, ground penetration, loop seam. planted_fn(leg, f)->bool"""
        rows = self.hoof_positions(act, frames)
        gap = max((r[l][2] - r[l][0]).length for r in rows for l in LEGS)
        pen = min(r[l][1].z for r in rows for l in LEGS)
        slide = 0.0
        if planted_fn:
            for leg in LEGS:
                anchor = None
                for f, r in enumerate(rows):
                    if planted_fn(leg, f):
                        if anchor is None: anchor = r[leg][0]
                        slide = max(slide, (r[leg][0].xy - anchor.xy).length)
                    else:
                        anchor = None
        seam = max((rows[0][l][0] - rows[-1][l][0]).length for l in LEGS)
        print(f"QA {label or act.name}: IK gap {gap*1000:.2f} mm | min hoof tip z {pen*1000:.1f} mm | "
              f"planted slide {slide*1000:.2f} mm | fetlock loop seam {seam*1000:.2f} mm")
        return dict(gap=gap, pen=pen, slide=slide, seam=seam)


# ============================================================================== gaits
def gait_pose_fn(calf: Calf, g: G.Gait, cycles=1, turn_deg=0.0, speed_scale=1.0):
    """Pose function for a gait. Straight line along -Y (root motion) or turning in place when
    `turn_deg` != 0 (root yaws turn_deg over the clip, speed_scale 0 = on the spot)."""
    N = g.frames * cycles
    v = g.speed * speed_scale
    def root_at(t_frames):
        s = t_frames / N
        yaw = turn_deg * s
        pos = Vector((0, -v * t_frames / FPS, 0)) if not turn_deg else Vector((0, 0, 0))
        return pos, yaw

    rest_feet = {leg: calf.rest_head(d["foot"]) for leg, d in LEGS.items()}

    def home(leg, t_frames):
        pos, yaw = root_at(t_frames)
        return pos + Matrix.Rotation(math.radians(yaw), 3, "Z") @ rest_feet[leg]

    T = g.frames
    def foot_world(leg, f):
        """world fetlock position via the planner (planted = home at mid-stance of that step)"""
        q_off = g.offsets[leg]
        # time (frames) since the current step's touch-down
        ph = ((f / T) - q_off) % 1.0
        td = f - ph * T                          # touch-down frame of the current/last step
        if ph < g.duty:
            return home(leg, td + g.duty * T / 2), 0.0, 0.0
        s = (ph - g.duty) / (1 - g.duty)
        a = home(leg, td + g.duty * T / 2)                  # lift-off position
        b = home(leg, td + T + g.duty * T / 2)              # next planted position
        _, dz, _ = G.foot_offset(g, leg, (q_off + ph) % 1.0)
        p = a.lerp(b, G.smoother(s))
        p.z += dz * (1.0 if speed_scale > 0.3 or turn_deg else 0.6)
        return p, s, dz

    def fn(f):
        p = (f % T) / T
        P = Pose()
        P.root_pos, P.root_yaw = root_at(f)
        dz, pitch, roll, sway = G.body_offset(g, p)
        P.body_off = Vector((sway, 0, dz))
        P.body_rot = Vector((pitch, roll, 0))
        if g.spine_flex:
            flex = g.spine_flex * math.sin(2 * math.pi * (p - 0.25))
            P.spine = {"Torso": (flex, 0, 0), "Torso2": (0.5 * flex, 0, 0)}
        neck_p, head_p = G.head_offset(g, p)
        P.neck = [neck_p * 0.3, neck_p * 0.35, neck_p * 0.35]
        P.head = Vector((head_p, 0, 0))
        for i in range(7):
            P.tail[i] = G.tail_offset(g, p, i + 1)
        ear_bounce = 3.0 * math.sin(2 * math.pi * g.bob_per_cycle * (p - g.bob_phase - 0.1))
        P.ears = {"L": Vector((4.0, -ear_bounce, 0)), "R": Vector((4.0, -ear_bounce, 0))}
        for leg in LEGS:
            w, s, dzf = foot_world(leg, f)
            P.feet_world[leg] = w
            _, _, flex = G.foot_offset(g, leg, p)
            P.flex[leg] = -flex
            if leg.endswith("F"):
                P.glide[leg] = G.shoulder_glide(g, leg, p) * -1.0
            else:
                P.femur[leg] = G.femur_angle(g, leg, p)
        return P
    return N, fn


def planted_fn_for(g: G.Gait):
    def f(leg, fr):
        return G.leg_phase(g, leg, (fr % g.frames) / g.frames) < g.duty * 0.98
    return f
