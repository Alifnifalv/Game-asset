"""Validate the Unity/glTF export of the calf against the source .blend.

Usage
  python3 tools/validate_export.py --fbx Unity/Calf/Calf.fbx --glb Unity/Calf/Calf.glb --src build/stage_d.blend
          [--json report.json] [--render-dir DIR] [--tol-mm 1.0] [--no-gltf-validator] [--node-dir build/node_tools]

Prints one PASS / FAIL / WARN / INFO line per check (with the measured numbers) and exits 1 if any check FAILs.

Checks
  source      bones, LOD triangle counts, rest bounding box, actions + frame ranges, reference bone world positions
              (pose reset to rest, NLA off, one action at a time: unkeyed channels = rest pose).
  FBX (raw)   the file is parsed directly (no Blender importer involved), i.e. what Unity's FBX SDK reads:
              axis system + UnitScaleFactor, transforms of the nodes above the skeleton (Unity root scale / rotation),
              only calf nodes (no camera / light), skeleton joints == source bones (minus dropped helpers), no leaf
              bones, per-LOD triangle counts, normals / tangents / binormals / UV layers, skin clusters (influences <=
              4, weight sums), takes (names, LocalStart/Stop -> frame ranges), and every take evaluated with FBX
              transform maths (T * Rpre * R(XYZ) * S) -> bone world positions compared with the source, both in
              Blender space and reported in Unity space (X mirrored) for the facing check; materials and texture
              file references.
  FBX (Blender re-import into a fresh scene)  bones, LOD objects + triangle counts, vertex-group influences and
              sums, rest dimensions, facing, actions + frame ranges, bone world positions per sampled frame vs source,
              LOD0 skinned-vertex deviation vs source (effect of the 4-influence limit), materials + images.
  GLB (raw)   JSON + BIN parsed directly: skin joints, attributes (JOINTS_0/WEIGHTS_0 only, weight sums), triangle
              count, animations (names, durations), glTF-native evaluation of every animation vs source, inverse bind
              matrices vs rest pose, materials / embedded images.
  GLB (Blender re-import)  bones, dimensions, facing, actions, bone world positions vs source.
  Khronos glTF-Validator  (npm package gltf-validator, installed on first use into --node-dir) errors / warnings.
"""
import argparse, json, math, os, re, shutil, struct, subprocess, sys, time, zlib

import numpy as np
import bpy
from mathutils import Matrix, Vector, Euler, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
T0 = time.time()
RESULTS = []
KEY_BONES = ["Head", "FF.L", "FF.R", "FFB.L", "FFB.R", "Tail7"]
KEY_FALLBACK = {"FF.L": "IKFrontLeg.L", "FF.R": "IKFrontLeg.R", "FFB.L": "IKBackLeg.L", "FFB.R": "IKBackLeg.R"}
LOD_RE = re.compile(r"_LOD(\d+)$")
FBX_KTIME = 46186158000


def check(section, name, status, detail=""):
    """status: True -> PASS, False -> FAIL, 'WARN' / 'INFO'"""
    tag = {True: "PASS", False: "FAIL"}.get(status, status)
    RESULTS.append({"section": section, "check": name, "status": tag, "detail": detail})
    print("%-4s  [%-9s] %-40s %s" % (tag, section, name, detail), flush=True)
    return status is True


def log(*a):
    print("[validate %6.1fs]" % (time.time() - T0), *a, flush=True)


def mm(x):
    return "%.3f mm" % (x * 1000.0)


# ============================================================================================ FBX binary reader
class FbxNode:
    __slots__ = ("name", "props", "children")

    def __init__(self, name, props, children):
        self.name, self.props, self.children = name, props, children

    def find(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def findall(self, name):
        return [c for c in self.children if c.name == name]


_FBX_ARR = {b"f": np.float32, b"d": np.float64, b"l": np.int64, b"i": np.int32, b"b": np.bool_}


def read_fbx(path):
    data = open(path, "rb").read()
    if not data.startswith(b"Kaydara FBX Binary  \x00"):
        raise ValueError("not a binary FBX: %s" % path)
    version = struct.unpack_from("<I", data, 23)[0]
    hdr = struct.Struct("<QQQ" if version >= 7500 else "<III")
    sentinel = hdr.size + 1

    def read_props(off, n):
        props = []
        for _ in range(n):
            t = data[off:off + 1]
            off += 1
            if t == b"Y":
                props.append(struct.unpack_from("<h", data, off)[0]); off += 2
            elif t == b"C":
                props.append(bool(data[off])); off += 1
            elif t == b"I":
                props.append(struct.unpack_from("<i", data, off)[0]); off += 4
            elif t == b"F":
                props.append(struct.unpack_from("<f", data, off)[0]); off += 4
            elif t == b"D":
                props.append(struct.unpack_from("<d", data, off)[0]); off += 8
            elif t == b"L":
                props.append(struct.unpack_from("<q", data, off)[0]); off += 8
            elif t in (b"S", b"R"):
                ln = struct.unpack_from("<I", data, off)[0]; off += 4
                raw = data[off:off + ln]; off += ln
                props.append(raw.decode("utf-8", "replace") if t == b"S" else raw)
            elif t in _FBX_ARR:
                alen, enc, clen = struct.unpack_from("<III", data, off); off += 12
                raw = data[off:off + clen]; off += clen
                if enc == 1:
                    raw = zlib.decompress(raw)
                props.append(np.frombuffer(raw, dtype=_FBX_ARR[t], count=alen).copy())
            else:
                raise ValueError("unknown FBX property type %r at %d" % (t, off - 1))
        return props

    def read_node(off):
        end, nprops, plen = hdr.unpack_from(data, off)
        off += hdr.size
        if end == 0:
            return None, off
        nlen = data[off]; off += 1
        name = data[off:off + nlen].decode("ascii"); off += nlen
        props = read_props(off, nprops)
        off += plen
        children = []
        while off < end:
            if end - off == sentinel:
                break
            ch, off = read_node(off)
            if ch is None:
                break
            children.append(ch)
        return FbxNode(name, props, children), end

    off, top = 27, []
    while off < len(data) - sentinel:
        n, off2 = read_node(off)
        if n is None:
            break
        top.append(n)
        off = off2
    return version, FbxNode("<root>", [], top)


def props70(node):
    p = node.find("Properties70") if node is not None else None
    out = {}
    if p is not None:
        for P in p.findall("P"):
            out[P.props[0]] = P.props[4:]
    return out


def fbx_name(s):
    return s.split("\x00\x01", 1)[0]


class FbxScene:
    """the parts of an FBX file the checks need, with the connection graph resolved"""

    def __init__(self, path):
        self.path = path
        self.version, root = read_fbx(path)
        self.gs = props70(root.find("GlobalSettings"))
        objs = root.find("Objects")
        self.objs = {}
        for n in objs.children:
            self.objs[n.props[0]] = n
        self.conns = []
        for c in root.find("Connections").findall("C"):
            self.conns.append((c.props[0], c.props[1], c.props[2], c.props[3] if len(c.props) > 3 else None))
        self.children_of, self.parents_of = {}, {}
        for typ, ch, pa, prop in self.conns:
            self.children_of.setdefault(pa, []).append((ch, typ, prop))
            self.parents_of.setdefault(ch, []).append((pa, typ, prop))
        self.models = {u: n for u, n in self.objs.items() if n.name == "Model"}
        self.model_parent = {}
        for u in self.models:
            ps = [pa for pa, typ, prop in self.parents_of.get(u, []) if typ == "OO" and (pa == 0 or pa in self.models)]
            self.model_parent[u] = ps[0] if ps else 0
        self.mprops = {u: props70(n) for u, n in self.models.items()}
        self.takes = [(t.props[0], [c for c in t.children]) for t in (root.find("Takes").findall("Take") if root.find("Takes") else [])]

    def kind(self, uid):
        return self.objs[uid].props[2] if uid in self.objs and len(self.objs[uid].props) > 2 else None

    def name(self, uid):
        return fbx_name(self.objs[uid].props[1])

    def linked(self, uid, node_name, parent=False, prop=None):
        lst = self.parents_of.get(uid, []) if parent else self.children_of.get(uid, [])
        return [u for u, typ, p in lst if u in self.objs and self.objs[u].name == node_name and (prop is None or p == prop)]

    @property
    def fps(self):
        if "CustomFrameRate" in self.gs and self.gs.get("TimeMode", [0])[0] == 14:
            return self.gs["CustomFrameRate"][0]
        modes = {1: 120, 2: 100, 3: 60, 4: 50, 5: 48, 6: 30, 7: 30, 8: 30, 9: 29.97, 10: 25, 11: 24, 13: 96, 15: 72, 16: 59.94}
        return self.gs.get("CustomFrameRate", [None])[0] or modes.get(self.gs.get("TimeMode", [0])[0], 30.0)

    def local_matrix(self, uid, over=None):
        """FBX node transform (Blender exporter subset: no pivots/offsets): T * Rpre * R * Rpost^-1 * S"""
        p = self.mprops[uid]
        t = over.get("Lcl Translation") if over and "Lcl Translation" in over else p.get("Lcl Translation", [0, 0, 0])
        r = over.get("Lcl Rotation") if over and "Lcl Rotation" in over else p.get("Lcl Rotation", [0, 0, 0])
        s = over.get("Lcl Scaling") if over and "Lcl Scaling" in over else p.get("Lcl Scaling", [1, 1, 1])
        rm = Euler([math.radians(x) for x in r], "XYZ").to_matrix().to_4x4()
        pre = p.get("PreRotation")
        if pre and any(abs(x) > 1e-9 for x in pre):
            rm = Euler([math.radians(x) for x in pre], "XYZ").to_matrix().to_4x4() @ rm
        post = p.get("PostRotation")
        if post and any(abs(x) > 1e-9 for x in post):
            rm = rm @ Euler([math.radians(x) for x in post], "XYZ").to_matrix().to_4x4().inverted()
        return Matrix.Translation(Vector(t[:3])) @ rm @ Matrix.Diagonal(Vector(list(s[:3]) + [1.0]))

    def stacks(self):
        return [u for u, n in self.objs.items() if n.name == "AnimationStack"]

    def stack_curves(self, stack):
        """{model uid: {'Lcl Translation': (default xyz, [(times, values)|None]*3), ...}}"""
        out = {}
        for layer in self.linked(stack, "AnimationLayer"):
            for cn in self.linked(layer, "AnimationCurveNode"):
                targets = [(pa, prop) for pa, typ, prop in self.parents_of.get(cn, []) if typ == "OP" and pa in self.models]
                if not targets:
                    continue
                model, prop = targets[0]
                dflt = props70(self.objs[cn])
                chans = []
                for ax in "XYZ":
                    cv = [u for u, typ, p in self.children_of.get(cn, []) if typ == "OP" and p == "d|" + ax]
                    if cv:
                        c = self.objs[cv[0]]
                        chans.append((c.find("KeyTime").props[0], c.find("KeyValueFloat").props[0].astype(np.float64)))
                    else:
                        chans.append(None)
                out.setdefault(model, {})[prop] = ([dflt.get("d|" + ax, [0.0])[0] for ax in "XYZ"], chans)
        return out


def sample_curve(times, vals, t):
    i = int(np.searchsorted(times, t))
    if i < len(times) and times[i] == t:
        return float(vals[i])
    if i <= 0:
        return float(vals[0])
    if i >= len(times):
        return float(vals[-1])
    a = (t - times[i - 1]) / float(times[i] - times[i - 1])
    return float(vals[i - 1] * (1 - a) + vals[i] * a)


# ============================================================================================ GLB reader
_GL_COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_GL_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class Glb:
    def __init__(self, path):
        data = open(path, "rb").read()
        magic, ver, length = struct.unpack_from("<4sII", data, 0)
        if magic != b"glTF":
            raise ValueError("not a GLB")
        self.version = ver
        off, self.json, self.bin = 12, None, b""
        while off < length:
            clen, ctype = struct.unpack_from("<II", data, off)
            off += 8
            if ctype == 0x4E4F534A:
                self.json = json.loads(data[off:off + clen].decode("utf-8"))
            elif ctype == 0x004E4942:
                self.bin = data[off:off + clen]
            off += clen
        self.size = len(data)

    def accessor(self, i):
        acc = self.json["accessors"][i]
        dt, n = _GL_COMP[acc["componentType"]], _GL_N[acc["type"]]
        count = acc["count"]
        if "bufferView" not in acc:
            arr = np.zeros((count, n), dt)
        else:
            bv = self.json["bufferViews"][acc["bufferView"]]
            off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            item = np.dtype(dt).itemsize * n
            stride = bv.get("byteStride", item)
            if stride == item:
                arr = np.frombuffer(self.bin, dtype=dt, count=count * n, offset=off).reshape(count, n)
            else:
                rows = [np.frombuffer(self.bin, dtype=dt, count=n, offset=off + k * stride) for k in range(count)]
                arr = np.array(rows)
        if "sparse" in acc:
            raise ValueError("sparse accessors not supported by this checker")
        arr = arr.astype(np.float64) if dt == np.float32 else arr
        if acc.get("normalized"):
            arr = arr.astype(np.float64) / float(np.iinfo(dt).max)
        return arr


def quat_wxyz(q_xyzw):
    return Quaternion((q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]))


def trs_matrix(t, r_xyzw, s):
    return Matrix.Translation(Vector(t)) @ quat_wxyz(r_xyzw).to_matrix().to_4x4() @ Matrix.Diagonal(Vector(list(s) + [1.0]))


def gl_sample(times, vals, t, interp, path):
    times = times[:, 0]
    if interp == "CUBICSPLINE":
        vals = vals.reshape(len(times), 3, -1)[:, 1, :]
    i = int(np.searchsorted(times, t - 1e-6))
    if i < len(times) and abs(times[i] - t) < 1e-5:
        return vals[i]
    if i <= 0:
        return vals[0]
    if i >= len(times):
        return vals[-1]
    if interp == "STEP":
        return vals[i - 1]
    a = (t - times[i - 1]) / (times[i] - times[i - 1])
    if path == "rotation":
        q = quat_wxyz(vals[i - 1]).slerp(quat_wxyz(vals[i]), a)
        return np.array([q.x, q.y, q.z, q.w])
    return vals[i - 1] * (1 - a) + vals[i] * a


# FBX / glTF (Y up, front +Z) -> Blender (Z up, front -Y): (x, y, z) -> (x, -z, y)
YUP_TO_BL = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


# ============================================================================================ Blender helpers
def action_fcurves(act):
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                yield from cb.fcurves


def armature_actions(arm):
    out = []
    for act in bpy.data.actions:
        fcs = list(action_fcurves(act))
        if not fcs or not act.slots:
            continue
        try:
            for fc in fcs:
                arm.path_resolve(fc.data_path + ("[%d]" % fc.array_index if fc.array_index else ""))
        except ValueError:
            continue
        out.append(act)
    return out


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)


def use_action(arm, act):
    ad = arm.animation_data or arm.animation_data_create()
    ad.use_nla = False
    ad.action = act
    if act is not None and act.slots:
        ad.action_slot = act.slots[0]
    reset_pose(arm)


def bone_samples(arm, names, lengths, frames):
    """{frame: {bone: (head, tail_point)}} in world space; tail_point = M @ (0, L_src, 0)"""
    sc = bpy.context.scene
    out = {}
    for f in frames:
        sc.frame_set(int(f))
        mw = arm.matrix_world
        d = {}
        for n in names:
            pb = arm.pose.bones.get(n)
            if pb is None:
                continue
            M = mw @ pb.matrix
            d[n] = (np.array(M.translation), np.array(M @ Vector((0.0, lengths[n], 0.0))))
        out[f] = d
    return out


def mesh_world_coords(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    e = obj.evaluated_get(dg)
    me = e.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(e.matrix_world)
    e.to_mesh_clear()
    return co @ M[:3, :3].T + M[:3, 3]


def tris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def weight_stats_vgroups(obj, bone_names):
    names = [g.name for g in obj.vertex_groups]
    cnt, sums = [], []
    for v in obj.data.vertices:
        ws = [g.weight for g in v.groups if g.weight > 0 and names[g.group] in bone_names]
        cnt.append(len(ws))
        sums.append(sum(ws))
    return np.array(cnt), np.array(sums)


def sample_frames(lo, hi, n=12):
    lo, hi = int(round(lo)), int(round(hi))
    step = max(1, (hi - lo) // n)
    fr = list(range(lo, hi + 1, step))
    if fr[-1] != hi:
        fr.append(hi)
    return fr


def compare(src_samp, dst_samp, frame_map, bones, key_bones):
    """max errors (heads / tail points) over all bones and over key bones"""
    worst_all, worst_key, where = 0.0, 0.0, None
    for f, fd in frame_map.items():
        s, d = src_samp[f], dst_samp[fd]
        for n in bones:
            if n not in s or n not in d:
                continue
            e = max(np.linalg.norm(s[n][0] - d[n][0]), np.linalg.norm(s[n][1] - d[n][1]))
            if e > worst_all:
                worst_all, where = e, (n, f)
            if n in key_bones:
                worst_key = max(worst_key, e)
    return worst_all, worst_key, where


def disconnect_bones(arm):
    """Blender ignores location channels of *connected* bones; the importers connect a bone whose head lies on its
    parent's tail (e.g. the hoof bones under the lower legs).  Unity/glTF engines apply those translations, so
    disconnect everything (rest pose unchanged) before comparing animation."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    n = 0
    for eb in arm.data.edit_bones:
        if eb.use_connect:
            eb.use_connect = False
            n += 1
    bpy.ops.object.mode_set(mode="OBJECT")
    return n


def find_armature():
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    return arms[0] if len(arms) == 1 else None


def lod_objects():
    lods = [o for o in bpy.data.objects if o.type == "MESH" and LOD_RE.search(o.name)]
    return sorted(lods, key=lambda o: int(LOD_RE.search(o.name).group(1)))


def bbox(pts):
    return pts.min(0), pts.max(0)


# ============================================================================================ source
def load_source(a, manifest):
    bpy.ops.wm.open_mainfile(filepath=a.src)
    sc = bpy.context.scene
    arm = bpy.data.objects.get("CalfRig") or find_armature()
    lods = [o for o in lod_objects() if any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers) or o.parent == arm]
    S = {"fps": sc.render.fps / sc.render.fps_base, "arm": arm.name}
    S["bones_all"] = [b.name for b in arm.data.bones]
    S["lengths"] = {b.name: b.length for b in arm.data.bones}
    S["parent"] = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
    weighted = set()
    for o in lods:
        names = [g.name for g in o.vertex_groups]
        for v in o.data.vertices:
            for g in v.groups:
                if g.weight > 0:
                    weighted.add(names[g.group])
    S["weighted"] = weighted
    if manifest is not None:
        dropped = manifest.get("dropped_helper_bones", [])
    else:
        dropped = [b.name for b in arm.data.bones if b.name.startswith("PoleTarget") and not b.children and b.name not in weighted]
    S["dropped"] = dropped
    S["bones"] = [n for n in S["bones_all"] if n not in dropped]
    S["lods"] = {o.name: {"tris": tris(o.data), "verts": len(o.data.vertices),
                          "mats": [s.material.name if s.material else None for s in o.material_slots]} for o in lods}
    for name, info in S["lods"].items():   # exporter moves M_Calf_Body to the last slot (CalfFur shells)
        exp = manifest["lods"].get(name, {}).get("materials") if manifest is not None and "lods" in manifest else None
        if exp is None:
            exp = [m for m in info["mats"] if m != "M_Calf_Body"] + [m for m in info["mats"] if m == "M_Calf_Body"]
        info["export_mats"] = exp
    acts = armature_actions(arm)
    if manifest is not None:
        want = [t["name"] for t in manifest["takes"]]
        acts = [bpy.data.actions[n] for n in want if n in bpy.data.actions]
        S["missing_actions"] = [n for n in want if n not in bpy.data.actions]
    else:
        S["missing_actions"] = []
    S["actions"] = {act.name: (act.frame_range[0], act.frame_range[1]) for act in acts}
    key = [n if n in S["lengths"] else KEY_FALLBACK.get(n) for n in KEY_BONES]
    S["key_bones"] = [n for n in key if n and n in S["lengths"]]
    for o in bpy.data.objects:          # bone sampling without mesh evaluation
        if o.type == "MESH":
            o.hide_viewport = True
    use_action(arm, None)
    sc.frame_set(0)
    S["rest"] = bone_samples(arm, S["bones"], S["lengths"], [0])[0]
    S["samples"], S["mesh"] = {}, {}
    for name, (lo, hi) in S["actions"].items():
        use_action(arm, bpy.data.actions[name])
        S["samples"][name] = bone_samples(arm, S["bones"], S["lengths"], sample_frames(lo, hi, a.samples))
    lod0 = lods[0]
    lod0.hide_viewport = False
    use_action(arm, None)
    sc.frame_set(0)
    S["rest_coords"] = mesh_world_coords(lod0)
    S["lod0"] = lod0.name
    for name, (lo, hi) in S["actions"].items():
        use_action(arm, bpy.data.actions[name])
        fr = sorted({int(lo), int(round((lo + hi) / 2)), int(hi)})
        S["mesh"][name] = {}
        for f in fr:
            sc.frame_set(f)
            S["mesh"][name][f] = mesh_world_coords(lod0)
    S["tangents"] = {}
    for o in lods:
        me = o.data
        if any(len(p.vertices) > 4 for p in me.polygons) or "UVMap" not in me.uv_layers:
            continue
        me.calc_tangents(uvmap="UVMap")
        t = np.empty(len(me.loops) * 3)
        me.loops.foreach_get("tangent", t)
        sg = np.empty(len(me.loops))
        me.loops.foreach_get("bitangent_sign", sg)
        S["tangents"][o.name] = (t.reshape(-1, 3), sg)
        me.free_tangents()
    S["textures"] = {}
    for o in lods:
        for s in o.material_slots:
            m = s.material
            if m and m.node_tree:
                S["textures"][m.name] = sorted({os.path.basename(n.image.filepath or n.image.name)
                                                for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image})
    return S


# ============================================================================================ FBX raw checks
def check_fbx_raw(a, S, expect_tex):
    sec = "FBX raw"
    F = FbxScene(a.fbx)
    gs = F.gs
    axes = tuple(gs.get(k, [None])[0] for k in ("UpAxis", "UpAxisSign", "FrontAxis", "FrontAxisSign", "CoordAxis", "CoordAxisSign"))
    usf = gs.get("UnitScaleFactor", [1.0])[0]
    check(sec, "axis system", axes == (1, 1, 2, 1, 0, 1),
          "Up=%s%s Front=%s%s Coord=%s%s (want Y-up, +Z front, +X coord: Unity mirrors X only)" %
          (("XYZ"[axes[0]] if axes[0] is not None else "?"), "+" if axes[1] == 1 else "-",
           ("XYZ"[axes[2]] if axes[2] is not None else "?"), "+" if axes[3] == 1 else "-",
           ("XYZ"[axes[4]] if axes[4] is not None else "?"), "+" if axes[5] == 1 else "-"))
    unit = usf / 100.0          # meters per file unit
    check(sec, "units", abs(usf - 100.0) < 1e-6,
          "UnitScaleFactor=%g -> Unity 'Convert Units' file scale %.3g, 1 unit = %g m" % (usf, unit, unit))
    check(sec, "frame rate", abs(F.fps - S["fps"]) < 1e-3, "file %.3f fps, source %.3f fps" % (F.fps, S["fps"]))

    kinds = {}
    for u in F.models:
        kinds.setdefault(F.kind(u), []).append(F.name(u))
    extra = {k: v for k, v in kinds.items() if k not in ("Null", "LimbNode", "Mesh")}
    check(sec, "only calf nodes", not extra and len(kinds.get("Null", [])) == 1,
          "Null=%s Mesh=%s LimbNode=%d%s" % (kinds.get("Null"), sorted(kinds.get("Mesh", [])), len(kinds.get("LimbNode", [])),
                                           (" UNEXPECTED %s" % extra) if extra else ""))
    # transforms of the nodes above the skeleton (Unity: children of the model prefab root)
    tops = [u for u in F.models if F.kind(u) in ("Null", "Mesh")]
    bad = []
    for u in tops:
        L = F.local_matrix(u)
        if max(abs(x) for row in (L - Matrix.Identity(4)) for x in row) > 1e-5:
            loc, rot, sc_ = L.decompose()
            bad.append("%s rot=%s scale=%s" % (F.name(u), tuple(round(math.degrees(x), 3) for x in rot.to_euler()),
                                               tuple(round(x, 5) for x in sc_)))
    check(sec, "root/LOD node transforms identity", not bad,
          ("all of %s: T=0 R=0 S=1" % sorted(F.name(u) for u in tops)) if not bad else "; ".join(bad))

    # skeleton
    limbs = {F.name(u): u for u in F.models if F.kind(u) == "LimbNode"}
    exp = set(S["bones"])
    got = set(limbs)
    check(sec, "bones == source bones", got == exp,
          "%d joints (source %d, dropped helpers %s)%s" % (len(got), len(S["bones_all"]), S["dropped"] or "none",
                                                          "" if got == exp else " missing=%s extra=%s" % (sorted(exp - got), sorted(got - exp))))
    check(sec, "no leaf/end bones", not any(n.endswith("_end") for n in got), "")
    par_bad = []
    for n, u in limbs.items():
        pu = F.model_parent[u]
        pn = F.name(pu) if pu in limbs.values() else None
        sp = S["parent"].get(n)
        if pn != sp and not (sp is None and pu != 0 and F.kind(pu) == "Null"):
            par_bad.append("%s: %s != %s" % (n, pn, sp))
    check(sec, "bone hierarchy == source", not par_bad, "; ".join(par_bad[:5]))

    # geometry
    geo_of, model_of = {}, {}
    for u in F.models:
        if F.kind(u) == "Mesh":
            model_of[F.name(u)] = u
            g = F.linked(u, "Geometry")
            if g:
                geo_of[F.name(u)] = g[0]
    for lname, info in S["lods"].items():
        if lname not in geo_of:
            check(sec, "%s present" % lname, False, "missing in FBX")
            continue
        g = F.objs[geo_of[lname]]
        pvi = g.find("PolygonVertexIndex").props[0]
        ends = np.nonzero(pvi < 0)[0]
        sizes = np.diff(np.concatenate([[-1], ends]))
        ntri = int((sizes - 2).sum())
        nv = len(g.find("Vertices").props[0]) // 3
        layers = [c.name for c in g.children if c.name.startswith("LayerElement")]
        uvs = [fbx_name(c.find("Name").props[0]) for c in g.findall("LayerElementUV")]
        check(sec, "%s geometry" % lname, ntri == info["tris"] and nv == info["verts"],
              "%d tris (source %d), %d verts (source %d), polys %d (%s)" %
              (ntri, info["tris"], nv, info["verts"], len(sizes),
               ", ".join("%d-gon x%d" % (k, c) for k, c in zip(*np.unique(sizes, return_counts=True)))))
        morder = [F.name(m) for m in F.linked(model_of[lname], "Material")]
        check(sec, "%s material order" % lname, morder == info["export_mats"],
              "submeshes %s (expected %s; body last for the CalfFur shell materials)" % (morder, info["export_mats"]))
        check(sec, "%s layers" % lname, all(x in layers for x in ("LayerElementNormal", "LayerElementTangent",
                                                                     "LayerElementBinormal", "LayerElementUV")) and "UVMap" in uvs,
              "normals+tangents+binormals: %s, UV sets %s" % ("LayerElementTangent" in layers, uvs))
        te = g.find("LayerElementTangent")
        if te is not None and lname in S["tangents"]:
            tf = te.find("Tangents").props[0].reshape(-1, 3)
            ts, sg = S["tangents"][lname]
            if len(tf) == len(ts):
                tb = np.c_[ts[:, 0], ts[:, 2], -ts[:, 1]]           # Blender -> FBX axes
                cosang = np.clip((tf * tb).sum(1) / np.maximum(np.linalg.norm(tf, axis=1) * np.linalg.norm(tb, axis=1), 1e-12), -1, 1)
                ang = np.degrees(np.arccos(cosang))
                check(sec, "%s tangent basis" % lname, float(ang.max()) < 0.1,
                      "FBX tangents vs Blender MikkTSpace of the source quads (the normal-map bake basis): max %.4f deg over %d corners"
                      % (ang.max(), len(ang)))
            else:
                check(sec, "%s tangent basis" % lname, "INFO", "corner count differs (%d vs %d): mesh was re-triangulated" % (len(tf), len(ts)))
        # skin clusters
        skins = F.linked(geo_of[lname], "Deformer")
        cnt = np.zeros(nv, int)
        sums = np.zeros(nv)
        clusters = 0
        for sk in skins:
            for cl in F.linked(sk, "Deformer"):
                idx = F.objs[cl].find("Indexes")
                if idx is None:
                    continue
                clusters += 1
                ii = idx.props[0]
                ww = F.objs[cl].find("Weights").props[0]
                nz = ww > 0
                np.add.at(cnt, ii[nz], 1)
                np.add.at(sums, ii[nz], ww[nz])
        check(sec, "%s skin influences" % lname, cnt.max() <= 4 and cnt.min() >= 1,
              "max %d, min %d per vertex, %d non-empty clusters, histogram %s" % (cnt.max(), cnt.min(), clusters, np.bincount(cnt).tolist()))
        dev = np.abs(sums - 1).max()
        check(sec, "%s skin weight sums" % lname, dev <= 1e-3, "max |sum-1| = %.2e" % dev)

    # takes
    raw = {F.name(u): u for u in F.stacks()}
    stacks = dict(raw)
    for nm, u in raw.items():            # "CalfRig|Eating" (Blender's All-Actions naming) still gets its motion checked
        stacks.setdefault(nm.split("|")[-1], u)
    want = S["actions"]
    missing = [n for n in want if n not in stacks]
    check(sec, "takes present", not missing and len(raw) == len(want),
          "%d takes %s%s" % (len(raw), sorted(raw), (" missing %s" % missing) if missing else ""))
    badname = [n for n in want if n not in raw]
    check(sec, "take names == action names", not badname,
          "exact" if not badname else "not exact: %s" % [nm for nm in raw if nm not in want])
    fps = F.fps
    sp = {}
    for n, (lo, hi) in want.items():
        if n not in stacks:
            continue
        p = props70(F.objs[stacks[n]])
        t0, t1 = p.get("LocalStart", [0])[0], p.get("LocalStop", [0])[0]
        nf = (t1 - t0) / FBX_KTIME * fps
        ok = abs(nf - (hi - lo)) < 1e-3
        sp[n] = (t0, t1)
        check(sec, "take %s range" % n, ok, "frames %.3f-%.3f (%.3f s) vs source %g-%g" %
              (t0 / FBX_KTIME * fps, t1 / FBX_KTIME * fps, (t1 - t0) / FBX_KTIME, lo, hi))

    # take evaluation with FBX maths
    order = []
    seen = set()

    def visit(u):
        if u in seen:
            return
        pu = F.model_parent.get(u, 0)
        if pu in F.models:
            visit(pu)
        seen.add(u)
        order.append(u)
    for u in F.models:
        visit(u)
    conv = YUP_TO_BL @ Matrix.Diagonal(Vector((unit, unit, unit, 1.0)))

    def world_mats(curves, t):
        W = {}
        for u in order:
            over = None
            if curves is not None and u in curves:
                over = {}
                for prop, (dflt, chans) in curves[u].items():
                    over[prop] = [sample_curve(c[0], c[1], t) if c is not None else dflt[i] for i, c in enumerate(chans)]
            L = F.local_matrix(u, over)
            pu = F.model_parent.get(u, 0)
            W[u] = (W[pu] @ L) if pu in W else L
        return W

    lengths = S["lengths"]
    # rest (no animation)
    W = world_mats(None, 0)
    err_rest = 0.0
    for n in S["bones"]:
        if n in limbs:
            M = conv @ W[limbs[n]]
            err_rest = max(err_rest, (Vector(S["rest"][n][0]) - M.translation).length)
    check(sec, "rest skeleton vs source", err_rest <= a.tol_mm / 1000, "max joint position error %s" % mm(err_rest))
    worst = {}
    for n, (lo, hi) in want.items():
        if n not in stacks:
            continue
        curves = F.stack_curves(stacks[n])
        keyed = [F.name(u) for u in curves if u in limbs.values()]
        e_all = e_key = 0.0
        where = None
        for f, sd in S["samples"][n].items():
            t = sp[n][0] + int(round((f - lo) / fps * FBX_KTIME))
            W = world_mats(curves, t)
            for b in S["bones"]:
                if b not in limbs or b not in sd:
                    continue
                M = conv @ W[limbs[b]]
                e = max((Vector(sd[b][0]) - M.translation).length, (Vector(sd[b][1]) - M @ Vector((0, lengths[b], 0))).length)
                if e > e_all:
                    e_all, where = e, (b, f)
                if b in S["key_bones"]:
                    e_key = max(e_key, e)
        worst[n] = e_all
        rm = ""
        if "Root" in limbs:
            w0 = world_mats(curves, sp[n][0])[limbs["Root"]]
            w1 = world_mats(curves, sp[n][1])[limbs["Root"]]
            d = (w1.translation - w0.translation) * unit
            yaw = math.degrees((w0.to_3x3().inverted() @ w1.to_3x3()).to_euler("YXZ").y)
            rm = "; Root motion (Unity) dx %+.3f dz %+.3f m, yaw %+.1f deg" % (-d.x, d.z, -yaw)
        check(sec, "take %s motion (FBX maths)" % n, e_all <= a.tol_mm / 1000,
              "%d bones keyed; over %d frames: key bones max %s, all bones max %s%s%s" %
              (len(keyed), len(S["samples"][n]), mm(e_key), mm(e_all), (" at %s f%d" % where) if where and e_all > a.tol_mm / 1000 else "", rm))
    # facing in Unity space: FBX (x, y, z) -> Unity (-x, y, z) * unit
    W = world_mats(None, 0)

    def unity(n):
        p = W[limbs[n]].translation * unit
        return Vector((-p.x, p.y, p.z))
    if "Head" in limbs and "Tail7" in limbs:
        h, t = unity("Head"), unity("Tail7")
        lft = [unity(n) for n in limbs if n.endswith(".L") and not n.startswith("PoleTarget")]
        lx = sum(p.x for p in lft) / max(1, len(lft))
        check(sec, "facing (Unity space)", h.z > t.z and h.y > 0.3 and lx < 0,
              "Head (%.3f, %.3f, %.3f), Tail7 (%.3f, %.3f, %.3f): front = +Z, up = +Y; .L bones mean x %.3f (<0 = calf's left)" %
              (h.x, h.y, h.z, t.x, t.y, t.z, lx))
    # materials + textures
    mats = sorted(F.name(u) for u, n in F.objs.items() if n.name == "Material")
    want_mats = sorted({m for info in S["lods"].values() for m in info["mats"] if m})
    check(sec, "materials", mats == want_mats, "%s (source %s)" % (mats, want_mats))
    texs = []
    for u, n in F.objs.items():
        if n.name == "Texture":
            rel = n.find("RelativeFilename").props[0] if n.find("RelativeFilename") else ""
            mat_links = [(F.name(pa), prop) for pa, typ, prop in F.parents_of.get(u, []) if pa in F.objs and F.objs[pa].name == "Material"]
            path = os.path.normpath(os.path.join(os.path.dirname(a.fbx), rel.replace("\\", "/")))
            texs.append((rel, os.path.isfile(path), mat_links))
    if expect_tex:
        ok = bool(texs) and all(e for _, e, _ in texs) and all(rel.replace("\\", "/").startswith("Textures/") for rel, _, _ in texs)
        check(sec, "texture references", ok, "; ".join("%s%s -> %s" % (rel, "" if e else " (MISSING)", ",".join("%s.%s" % l for l in ml))
                                                     for rel, e, ml in texs) or "none")
    else:
        check(sec, "texture references", "INFO", "%d (no textures expected: %s)" % (len(texs), [t[0] for t in texs]))
    return F


# ============================================================================================ FBX re-import
def check_fbx_import(a, S, expect_tex):
    sec = "FBX->Bl"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = int(round(S["fps"]))
    sc.render.fps_base = 1.0
    bpy.ops.import_scene.fbx(filepath=a.fbx, use_anim=True, anim_offset=0.0, ignore_leaf_bones=False,
                             automatic_bone_orientation=False, primary_bone_axis="Y", secondary_bone_axis="X",
                             use_custom_normals=True, use_image_search=False)
    kinds = sorted((o.type, o.name) for o in bpy.data.objects)
    arm = find_armature()
    check(sec, "objects", arm is not None and not any(t in ("CAMERA", "LIGHT") for t, _ in kinds),
          ", ".join("%s:%s" % (n, t) for t, n in kinds))
    if arm is None:
        return
    got = [b.name for b in arm.data.bones]
    nconn = disconnect_bones(arm)
    check(sec, "bones == source bones", sorted(got) == sorted(S["bones"]), "%d bones (expected %d); %d connected by the "
          "importer (disconnected for the motion checks)" % (len(got), len(S["bones"]), nconn))
    for lname, info in S["lods"].items():
        o = bpy.data.objects.get(lname)
        if o is None:
            check(sec, "%s" % lname, False, "missing")
            continue
        cnt, sums = weight_stats_vgroups(o, set(got))
        check(sec, "%s tris / weights" % lname,
              tris(o.data) == info["tris"] and cnt.max() <= 4 and cnt.min() >= 1 and np.abs(sums - 1).max() <= 1e-3,
              "%d tris (source %d); influences max %d min %d; max |sum-1| %.1e; skinned by %s" %
              (tris(o.data), info["tris"], cnt.max(), cnt.min(), np.abs(sums - 1).max(),
               [m.object.name for m in o.modifiers if m.type == "ARMATURE"]))
        mats = [s.material.name if s.material else None for s in o.material_slots]
        check(sec, "%s materials" % lname, mats == info["export_mats"],
              "%s (source slots %s)" % (mats, info["mats"]))
    # actions (Blender's importer names them "<armature>|<take>")
    acts = {}
    for act in bpy.data.actions:
        take = act.name.split("|")[-1]
        if take in S["actions"]:
            acts[take] = act
    check(sec, "actions", sorted(acts) == sorted(S["actions"]),
          "%s" % ", ".join("%s [%g-%g]" % (act.name, *act.frame_range) for act in bpy.data.actions))
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_viewport = True
    use_action(arm, None)
    sc.frame_set(0)
    rest = bone_samples(arm, S["bones"], S["lengths"], [0])[0]
    e = max(max(np.linalg.norm(rest[n][0] - S["rest"][n][0]), np.linalg.norm(rest[n][1] - S["rest"][n][1])) for n in S["bones"] if n in rest)
    check(sec, "rest skeleton vs source", e <= a.tol_mm / 1000, "max error %s (joint heads + bone-axis points)" % mm(e))
    head, tail = rest["Head"][0], rest["Tail7"][0] if "Tail7" in rest else rest[S["bones"][-1]][0]
    check(sec, "facing", head[1] < tail[1] and head[2] > 0.3,
          "Head y=%.3f < Tail7 y=%.3f (Blender -Y front = Unity +Z), Head z=%.3f" % (head[1], tail[1], head[2]))
    for n, (lo, hi) in S["actions"].items():
        if n not in acts:
            continue
        act = acts[n]
        use_action(arm, act)
        off = act.frame_range[0] - 0.0
        fmap = {f: int(round(f - lo + off)) for f in S["samples"][n]}
        rng_ok = abs((act.frame_range[1] - act.frame_range[0]) - (hi - lo)) < 1e-3
        d = bone_samples(arm, S["bones"], S["lengths"], sorted(set(fmap.values())))
        e_all, e_key, where = compare(S["samples"][n], d, fmap, S["bones"], S["key_bones"])
        check(sec, "%s motion" % n, rng_ok and e_all <= a.tol_mm / 1000,
              "range %g-%g (source %g-%g); key bones %s max %s, all bones max %s over %d frames%s" %
              (act.frame_range[0], act.frame_range[1], lo, hi, "/".join(S["key_bones"]), mm(e_key), mm(e_all), len(fmap),
               (" (worst %s f%d)" % where) if where and e_all > a.tol_mm / 1000 else ""))
    # rest dimensions + skinned deformation vs source
    lod0 = bpy.data.objects.get(S["lod0"])
    if lod0 is not None:
        lod0.hide_viewport = False
        use_action(arm, None)
        sc.frame_set(0)
        co = mesh_world_coords(lod0)
        mn, mx = bbox(co)
        smn, smx = bbox(S["rest_coords"])
        dim, sdim = mx - mn, smx - smn
        ok = np.abs(mn - smn).max() < 0.002 and np.abs(mx - smx).max() < 0.002 and 0.8 < dim[2] < 1.4 and 1.4 < dim[1] < 2.0
        check(sec, "rest dimensions", ok, "L(y) %.3f m, H(z) %.3f m, W(x) %.3f m (source %.3f / %.3f / %.3f), ground z=%.4f" %
              (dim[1], dim[2], dim[0], sdim[1], sdim[2], sdim[0], mn[2]))
        if co.shape == S["rest_coords"].shape:
            er = np.linalg.norm(co - S["rest_coords"], axis=1).max()
            check(sec, "LOD0 rest vertices vs source", er <= a.tol_mm / 1000, "max %s" % mm(er))
            devs = []
            for n, frames in S["mesh"].items():
                if n not in acts:
                    continue
                act = acts[n]
                use_action(arm, act)
                lo = S["actions"][n][0]
                for f, sco in frames.items():
                    sc.frame_set(int(round(f - lo + act.frame_range[0])))
                    dco = mesh_world_coords(lod0)
                    d = np.linalg.norm(dco - sco, axis=1)
                    devs.append((d.max(), d.mean(), float(np.percentile(d, 99.9)), n, f))
            if devs:
                w = max(devs)
                status = True if w[0] <= 0.01 else "WARN"
                check(sec, "LOD0 skinned vertices vs source", status,
                      "worst frame %s f%d: max %s, 99.9%% %s, mean %s (4-influence limit + export precision; %d frames)" %
                      (w[3], w[4], mm(w[0]), mm(w[2]), mm(w[1]), len(devs)))
        else:
            check(sec, "LOD0 vertex count", False, "%d vs source %d" % (len(co), len(S["rest_coords"])))
    # materials / images
    imgs = []
    for m in bpy.data.materials:
        if m.node_tree:
            for nd in m.node_tree.nodes:
                if nd.type == "TEX_IMAGE" and nd.image:
                    p = bpy.path.abspath(nd.image.filepath)
                    imgs.append((m.name, os.path.basename(p), os.path.isfile(p)))
    if expect_tex:
        check(sec, "material images", bool(imgs) and all(x[2] for x in imgs),
              "; ".join("%s:%s%s" % (m, f, "" if e else "(MISSING)") for m, f, e in imgs))
    else:
        check(sec, "material images", "INFO", "%d images (none expected)" % len(imgs))


# ============================================================================================ GLB raw checks
def check_glb_raw(a, S, expect_tex):
    sec = "GLB raw"
    G = Glb(a.glb)
    J = G.json
    check(sec, "container", G.version == 2 and J.get("asset", {}).get("version") == "2.0",
          "glTF %s, %.2f MB, generator %s" % (J.get("asset", {}).get("version"), G.size / 1e6, J.get("asset", {}).get("generator")))
    nodes = J["nodes"]
    names = [n.get("name", "") for n in nodes]
    skins = J.get("skins", [])
    if not skins:
        check(sec, "skin", False, "no skin")
        return
    joints = [names[j] for j in skins[0]["joints"]]
    check(sec, "joints == source bones", sorted(joints) == sorted(S["bones"]),
          "%d joints (expected %d)%s" % (len(joints), len(S["bones"]),
                                          "" if sorted(joints) == sorted(S["bones"]) else " diff %s" % sorted(set(joints) ^ set(S["bones"]))))
    meshes = J.get("meshes", [])
    mesh_nodes = [i for i, n in enumerate(nodes) if "mesh" in n]
    check(sec, "meshes", len(meshes) == 1 and len(mesh_nodes) == 1,
          "%d mesh(es): %s" % (len(meshes), [nodes[i].get("name") for i in mesh_nodes]))
    ntri, wdev, maxinf, attrs = 0, 0.0, 0, set()
    for prim in meshes[0]["primitives"]:
        attrs |= set(prim["attributes"])
        if prim.get("mode", 4) != 4:
            continue
        ntri += J["accessors"][prim["indices"]]["count"] // 3
        if "WEIGHTS_0" in prim["attributes"]:
            w = G.accessor(prim["attributes"]["WEIGHTS_0"])
            wdev = max(wdev, float(np.abs(w.sum(1) - 1).max()))
            maxinf = max(maxinf, int((w > 0).sum(1).max()))
    lod0_tris = S["lods"][S["lod0"]]["tris"]
    check(sec, "LOD0 triangles", ntri == lod0_tris, "%d (source %d)" % (ntri, lod0_tris))
    check(sec, "vertex attributes", {"POSITION", "NORMAL", "TANGENT", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"} <= attrs and "JOINTS_1" not in attrs,
          sorted(attrs).__str__())
    check(sec, "skin weights", maxinf <= 4 and wdev <= 1e-3, "max influences %d, max |sum-1| %.1e" % (maxinf, wdev))
    # node world matrices (rest)
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i

    def local(i, over=None):
        n = nodes[i]
        if "matrix" in n:
            return Matrix([n["matrix"][k::4] for k in range(4)])
        t = n.get("translation", [0, 0, 0]); r = n.get("rotation", [0, 0, 0, 1]); s = n.get("scale", [1, 1, 1])
        if over and i in over:
            t = over[i].get("translation", t); r = over[i].get("rotation", r); s = over[i].get("scale", s)
        return trs_matrix(t, r, s)

    def world(over=None):
        W = {}

        def w(i):
            if i not in W:
                W[i] = (w(parent[i]) @ local(i, over)) if i in parent else local(i, over)
            return W[i]
        for i in range(len(nodes)):
            w(i)
        return W
    W = world()
    jidx = {names[j]: j for j in skins[0]["joints"]}
    e_rest = max((Vector(S["rest"][n][0]) - (YUP_TO_BL @ W[j]).translation).length for n, j in jidx.items() if n in S["rest"])
    check(sec, "rest skeleton vs source", e_rest <= a.tol_mm / 1000, "max joint error %s" % mm(e_rest))
    if "inverseBindMatrices" in skins[0]:
        ibm = G.accessor(skins[0]["inverseBindMatrices"])
        mesh_w = W[mesh_nodes[0]] if mesh_nodes else Matrix.Identity(4)
        e = 0.0
        for k, j in enumerate(skins[0]["joints"]):
            B = Matrix([ibm[k][c::4] for c in range(4)])
            D = mesh_w.inverted() @ W[j] @ B          # glTF joint matrix at rest: must be identity
            e = max(e, max(abs(D[r][c] - (1.0 if r == c else 0.0)) for r in range(4) for c in range(4)))
        check(sec, "inverse bind matrices", e < 1e-4, "rest joint matrices max |mesh^-1 @ joint @ IBM - I| = %.1e" % e)
    h = (YUP_TO_BL @ W[jidx["Head"]]).translation if "Head" in jidx else None
    t = (YUP_TO_BL @ W[jidx["Tail7"]]).translation if "Tail7" in jidx else None
    if h is not None and t is not None:
        gh, gt = W[jidx["Head"]].translation, W[jidx["Tail7"]].translation
        check(sec, "facing (glTF space)", gh.z > gt.z and gh.y > 0.3,
              "Head z=%.3f > Tail7 z=%.3f: front = glTF +Z (glTF convention), up = +Y" % (gh.z, gt.z))
    # animations
    anims = {an.get("name"): an for an in J.get("animations", [])}
    check(sec, "animations present", sorted(anims) == sorted(S["actions"]),
          "%s (source %s)" % (sorted(anims), sorted(S["actions"])))
    fps = S["fps"]
    for n, (lo, hi) in S["actions"].items():
        if n not in anims:
            continue
        an = anims[n]
        chans = []
        t0, t1 = 1e9, -1e9
        for ch in an["channels"]:
            smp = an["samplers"][ch["sampler"]]
            inp = G.accessor(smp["input"])
            out = G.accessor(smp["output"])
            t0, t1 = min(t0, inp.min()), max(t1, inp.max())
            chans.append((ch["target"].get("node"), ch["target"]["path"], inp, out, smp.get("interpolation", "LINEAR")))
        e_all = e_key = 0.0
        where = None
        for f, sd in S["samples"][n].items():
            tt = (f - lo) / fps
            over = {}
            for node, path, inp, out, interp in chans:
                if path in ("translation", "rotation", "scale"):
                    over.setdefault(node, {})[path] = list(gl_sample(inp, out, tt, interp, path))
            Wf = world(over)
            for b, j in jidx.items():
                if b not in sd:
                    continue
                M = YUP_TO_BL @ Wf[j]
                e = max((Vector(sd[b][0]) - M.translation).length, (Vector(sd[b][1]) - M @ Vector((0, S["lengths"][b], 0))).length)
                if e > e_all:
                    e_all, where = e, (b, f)
                if b in S["key_bones"]:
                    e_key = max(e_key, e)
        dur_ok = abs(t0) < 1e-6 and abs((t1 - t0) - (hi - lo) / fps) < 1e-4
        check(sec, "anim %s" % n, dur_ok and e_all <= a.tol_mm / 1000,
              "t %.4f-%.4f s (source %.4f s), %d channels; key bones max %s, all bones max %s%s" %
              (t0, t1, (hi - lo) / fps, len(chans), mm(e_key), mm(e_all), (" at %s f%d" % where) if e_all > a.tol_mm / 1000 else ""))
    mats = [m.get("name") for m in J.get("materials", [])]
    imgs = J.get("images", [])
    emb = [im for im in imgs if "bufferView" in im]
    texinfo = []
    for m in J.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        slots = [k for k in ("baseColorTexture", "metallicRoughnessTexture") if k in pbr] + \
                [k for k in ("normalTexture", "occlusionTexture", "emissiveTexture") if k in m]
        texinfo.append("%s:%s" % (m.get("name"), "+".join(s.replace("Texture", "") for s in slots) or "-"))
    want_mats = sorted({m for m in S["lods"][S["lod0"]]["mats"] if m})
    ok = sorted(mats) == want_mats and (len(emb) == len(imgs)) and (bool(imgs) if expect_tex else True)
    check(sec, "materials / images", ok, "%s; %d images (%d embedded, %s)" %
          (", ".join(texinfo), len(imgs), len(emb), sorted({im.get("mimeType") for im in imgs})))


# ============================================================================================ GLB re-import
def check_glb_import(a, S):
    sec = "GLB->Bl"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = int(round(S["fps"]))
    sc.render.fps_base = 1.0
    bpy.ops.import_scene.gltf(filepath=a.glb, bone_heuristic="BLENDER", disable_bone_shape=True)
    arm = find_armature()
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    check(sec, "objects", arm is not None and len(meshes) == 1,
          ", ".join("%s:%s" % (o.name, o.type) for o in bpy.data.objects))
    if arm is None:
        return
    got = sorted(b.name for b in arm.data.bones)
    nconn = disconnect_bones(arm)
    check(sec, "bones == source bones", got == sorted(S["bones"]), "%d bones; %d connected by the importer "
          "(disconnected for the motion checks)" % (len(got), nconn))
    acts = {}
    for act in bpy.data.actions:
        base = act.name
        for n in S["actions"]:
            if base == n or base.startswith(n + "_") or base.endswith("|" + n):
                acts.setdefault(n, act)
    check(sec, "actions", sorted(acts) == sorted(S["actions"]),
          ", ".join("%s [%g-%g]" % (x.name, *x.frame_range) for x in bpy.data.actions))
    for o in meshes:
        o.hide_viewport = True
    use_action(arm, None)
    sc.frame_set(0)
    rest = bone_samples(arm, S["bones"], S["lengths"], [0])[0]
    e = max(max(np.linalg.norm(rest[n][0] - S["rest"][n][0]), np.linalg.norm(rest[n][1] - S["rest"][n][1])) for n in S["bones"] if n in rest)
    check(sec, "rest skeleton vs source", e <= a.tol_mm / 1000, "max error %s" % mm(e))
    if "Head" in rest and "Tail7" in rest:
        check(sec, "facing", rest["Head"][0][1] < rest["Tail7"][0][1],
              "Head y=%.3f < Tail7 y=%.3f" % (rest["Head"][0][1], rest["Tail7"][0][1]))
    for n, (lo, hi) in S["actions"].items():
        if n not in acts:
            continue
        act = acts[n]
        use_action(arm, act)
        fmap = {f: int(round(f - lo + act.frame_range[0])) for f in S["samples"][n]}
        d = bone_samples(arm, S["bones"], S["lengths"], sorted(set(fmap.values())))
        e_all, e_key, where = compare(S["samples"][n], d, fmap, S["bones"], S["key_bones"])
        rng_ok = abs((act.frame_range[1] - act.frame_range[0]) - (hi - lo)) < 1e-3
        check(sec, "%s motion" % n, rng_ok and e_all <= a.tol_mm / 1000,
              "range %g-%g; key bones max %s, all bones max %s%s" % (act.frame_range[0], act.frame_range[1], mm(e_key), mm(e_all),
                                                                  (" (worst %s f%d)" % where) if where and e_all > a.tol_mm / 1000 else ""))
    m = meshes[0]
    m.hide_viewport = False
    use_action(arm, None)
    sc.frame_set(0)
    co = mesh_world_coords(m)
    mn, mx = bbox(co)
    smn, smx = bbox(S["rest_coords"])
    check(sec, "rest dimensions", np.abs(mn - smn).max() < 0.002 and np.abs(mx - smx).max() < 0.002,
          "L %.3f H %.3f W %.3f m (source %.3f / %.3f / %.3f)" % (mx[1] - mn[1], mx[2] - mn[2], mx[0] - mn[0],
                                                               smx[1] - smn[1], smx[2] - smn[2], smx[0] - smn[0]))


# ============================================================================================ Khronos validator
GLTF_VALIDATOR_JS = r"""
const validator = require('gltf-validator');
const fs = require('fs');
const path = require('path');
const file = process.argv[2];
const asset = new Uint8Array(fs.readFileSync(file));
validator.validateBytes(asset, {
    uri: path.basename(file), maxIssues: 1000,
    externalResourceFunction: (uri) => new Promise((resolve, reject) => {
        fs.readFile(path.resolve(path.dirname(file), decodeURIComponent(uri)), (err, data) => {
            if (err) { reject(err.toString()); return; }
            resolve(new Uint8Array(data));
        });
    })
}).then((report) => { process.stdout.write(JSON.stringify(report)); })
  .catch((error) => { console.error('Validation failed: ' + error); process.exit(2); });
"""


def run_gltf_validator(a):
    sec = "Khronos"
    node = shutil.which("node")
    if node is None:
        check(sec, "gltf-validator", "WARN", "node not found; skipped")
        return
    nd = os.path.abspath(a.node_dir)
    mod = os.path.join(nd, "node_modules", "gltf-validator")
    if not os.path.isdir(mod):
        log("installing gltf-validator into", nd)
        os.makedirs(nd, exist_ok=True)
        r = subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--silent", "--prefix", nd, "gltf-validator"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isdir(mod):
            check(sec, "gltf-validator", "WARN", "npm install failed: %s" % (r.stderr.strip()[-300:]))
            return
    js = os.path.join(nd, "validate_gltf.js")
    with open(js, "w") as fh:
        fh.write(GLTF_VALIDATOR_JS)
    r = subprocess.run([node, js, os.path.abspath(a.glb)], capture_output=True, text=True, cwd=nd)
    if r.returncode != 0:
        check(sec, "gltf-validator", False, "validator crashed: %s" % r.stderr.strip()[-300:])
        return
    rep = json.loads(r.stdout)
    iss = rep["issues"]
    ver = rep.get("validatorVersion")
    msgs = iss.get("messages", [])
    by = {}
    for m in msgs:
        by.setdefault(m["severity"], []).append("%s %s" % (m["code"], m.get("pointer", "")))
    detail = "v%s: %d errors, %d warnings, %d infos, %d hints" % (ver, iss["numErrors"], iss["numWarnings"], iss["numInfos"], iss["numHints"])
    check(sec, "gltf-validator", iss["numErrors"] == 0, detail)
    names = {0: "error", 1: "warning", 2: "info", 3: "hint"}
    for sev in sorted(by):
        codes = {}
        for s in by[sev]:
            c = s.split(" ")[0]
            codes[c] = codes.get(c, 0) + 1
        check(sec, "  %s codes" % names.get(sev, sev), "INFO" if sev >= 2 else ("WARN" if sev == 1 else False),
              ", ".join("%s x%d" % kv for kv in sorted(codes.items())))
    info = rep.get("info", {})
    check(sec, "  stats", "INFO", "%s draw calls, %s animations, %s materials, %s vertices, %s tris, maxInfluences %s" %
          (info.get("drawCallCount"), info.get("animationCount"), info.get("materialCount"),
           info.get("totalVertexCount"), info.get("totalTriangleCount"), info.get("maxInfluences")))


# ============================================================================================ main
def render(a, S):
    """contact sheets of the source, the FBX and the GLB (Blender imports) on the same pose, for a visual check"""
    os.makedirs(a.render_dir, exist_ok=True)
    rv = os.path.join(HERE, "render_views.py")
    name, (lo, hi) = next(iter(S["actions"].items())) if S["actions"] else (None, (0, 0))
    f = int(round((lo + hi) / 2))
    # render_views imports FBX takes as "<armature>|<take>" with Blender's default +1 frame offset; glTF from frame 0
    jobs = [("src", a.src, name, f), ("fbx", a.fbx, "%s|%s" % (S["arm"], name), f - int(lo) + 1),
            ("glb", a.glb, name, f - int(lo))]
    for tag, path, act, fr in jobs:
        out = os.path.join(a.render_dir, "export_%s.png" % tag)
        cmd = [sys.executable, rv, path, out, "--res", str(a.render_res), "--samples", "16",
               "--views", "side,front,threequarter,back,head,otherside"]
        if act:
            cmd += ["--action", act, "--frame", str(fr)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        bb = [l for l in r.stdout.splitlines() if l.startswith("BBOX")]
        check("render", tag, r.returncode == 0 and os.path.isfile(out),
              "%s (%s f%d) %s" % (out, act, fr, bb[0] if bb else r.stderr[-200:]))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fbx", required=True)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--manifest", default=None, help="default: <fbx dir>/<fbx name>_export_manifest.json if present")
    ap.add_argument("--tol-mm", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=12, help="sampled frames per action (plus first/last)")
    ap.add_argument("--json", default=None)
    ap.add_argument("--render-dir", default=None, help="also render source / FBX / GLB contact sheets here")
    ap.add_argument("--render-res", type=int, default=400)
    ap.add_argument("--no-gltf-validator", action="store_true")
    ap.add_argument("--node-dir", default=os.path.join(ROOT, "build", "node_tools"))
    a = ap.parse_args(argv)
    a.fbx, a.glb, a.src = (os.path.abspath(p) for p in (a.fbx, a.glb, a.src))
    mpath = a.manifest or os.path.join(os.path.dirname(a.fbx), os.path.splitext(os.path.basename(a.fbx))[0] + "_export_manifest.json")
    manifest = json.load(open(mpath)) if os.path.isfile(mpath) else None
    log("manifest:", mpath if manifest else "none (all rig actions expected, PoleTarget helpers expected dropped)")
    tex_dir = os.path.join(os.path.dirname(a.fbx), "Textures")
    expect_tex = bool(manifest and manifest.get("textures")) or (os.path.isdir(tex_dir) and bool(os.listdir(tex_dir)))

    S = load_source(a, manifest)
    check("source", "rig", True, "%s: %d bones (%d exported, dropped %s), fps %g" %
          (S["arm"], len(S["bones_all"]), len(S["bones"]), S["dropped"] or "none", S["fps"]))
    check("source", "LODs", "INFO", ", ".join("%s %d tris" % (k, v["tris"]) for k, v in S["lods"].items()))
    check("source", "actions", not S["missing_actions"], ", ".join("%s [%g-%g]" % (k, *v) for k, v in S["actions"].items()) +
          (" MISSING %s" % S["missing_actions"] if S["missing_actions"] else ""))
    if S["dropped"]:
        unsafe = [n for n in S["dropped"] if n in S["weighted"]]
        check("source", "dropped helpers unweighted", not unsafe, "%s%s" % (S["dropped"], " WEIGHTED: %s" % unsafe if unsafe else ""))
    check("source", "textures", "INFO", "expected: %s; source material images: %s" % (expect_tex, S["textures"]))

    check_fbx_raw(a, S, expect_tex)
    check_fbx_import(a, S, expect_tex)
    check_glb_raw(a, S, expect_tex)
    check_glb_import(a, S)
    if not a.no_gltf_validator:
        run_gltf_validator(a)
    if a.render_dir:
        render(a, S)

    n_fail = sum(r["status"] == "FAIL" for r in RESULTS)
    n_warn = sum(r["status"] == "WARN" for r in RESULTS)
    n_pass = sum(r["status"] == "PASS" for r in RESULTS)
    print("\nSUMMARY: %d PASS, %d FAIL, %d WARN  (%.1f s)" % (n_pass, n_fail, n_warn, time.time() - T0))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"fbx": a.fbx, "glb": a.glb, "src": a.src, "pass": n_pass, "fail": n_fail, "warn": n_warn,
                       "results": RESULTS}, fh, indent=1)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
