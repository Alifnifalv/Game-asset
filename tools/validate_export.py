"""Validate the Unity/glTF export of the calf against the source .blend.

Usage
  python3 tools/validate_export.py --fbx Unity/Calf/Calf.fbx --glb Unity/Calf/Calf.glb --src build/stage_d.blend
          [--json report.json] [--render-dir DIR] [--tol-mm 1.0] [--no-gltf-validator] [--node-dir build/node_tools]
          [--samples 0] [--no-skin-frames] [--twist-limb-deg 15] [--skin-warn-mm 10] [--skin-fail-mm 60]

Prints one PASS / FAIL / WARN / INFO line per check (with the measured numbers) and exits 1 if any check FAILs.
Runs in about a minute (plus ~3 min with --render-dir): every check below looks at EVERY frame of every clip.

Checks
  source      bones, LOD triangle counts, rest bounding box, actions + frame ranges, bone world matrices on every frame
              (pose reset to rest, NLA off, one action at a time: unkeyed channels = rest pose).  Each bone is compared
              through three points: its head, its tail point M @ (0, L, 0) and an off-axis point M @ (OFF_AXIS, 0, 0),
              so a roll about the bone axis is caught as well as a wrong joint position.
  anim        twist continuity per clip: the twist of every bone about its own axis between consecutive frames (FAIL
              > --twist-limb-deg for leg/hoof bones: an IK roll flip keeps every joint in place but candy-wraps the
              forearm; WARN > --twist-warn-deg for any bone) and relative to its parent (FAIL > --twist-local-deg).
  FBX (raw)   the file is parsed directly (no Blender importer involved), i.e. what Unity's FBX SDK reads:
              axis system + UnitScaleFactor, transforms of the nodes above the skeleton (Unity root scale / rotation),
              only calf nodes (no camera / light), skeleton joints == source bones (minus dropped helpers), no leaf
              bones, per-LOD triangle counts, normals / tangents / binormals / UV layers, skin clusters (influences <=
              4, weight sums, joints without weights), takes (names, LocalStart/Stop -> frame ranges), and every take
              evaluated with FBX transform maths (T * Rpre * R(XYZ) * S) on every frame -> bone points compared with the
              source; the Root curve per take on every frame in Unity space (travel, yaw, height, pitch/roll); facing;
              materials and texture file references.
  skin        the shipped skins evaluated with the engines' own maths on EVERY frame of every clip (FBX: cluster
              TransformLink bind + take curves, every LOD; GLB: joints + inverse bind matrices, LOD0) against the
              Blender source mesh (all influences, what the clip QA and previews show): the effect of the 4-influence
              limit.  PASS <= --skin-warn-mm, WARN <= --skin-fail-mm, FAIL above (broken weights or bones).
  FBX (Blender re-import into a fresh scene)  bones, LOD objects + triangle counts, vertex-group influences and
              sums, rest dimensions, facing, actions + frame ranges, bone points per frame vs source, LOD0 skinned
              vertices on 3 frames per clip (importer cross-check), materials + images.
  GLB (raw)   JSON + BIN parsed directly: skin joints, attributes (JOINTS_0/WEIGHTS_0 only, weight sums), triangle
              count, animations (names, durations), glTF-native evaluation of every animation on every frame vs source,
              inverse bind matrices vs rest pose, materials (single-sided) / embedded images (sizes, decoded VRAM).
  GLB (Blender re-import)  bones, dimensions, facing, actions, bone points per frame vs source.
  Khronos glTF-Validator  (npm package gltf-validator, installed on first use into --node-dir) errors / warnings.
  render      (--render-dir) contact sheets of the source, FBX and GLB on the same pose; their bounding boxes must agree.
"""
import argparse, json, math, os, re, shutil, struct, subprocess, sys, time, zlib

import numpy as np
import bpy
from mathutils import Matrix, Vector, Euler, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import asset_profile as AP
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

    def model_order(self):
        """model uids, parents before children"""
        if getattr(self, "_order", None) is None:
            order, seen = [], set()

            def visit(u):
                if u in seen:
                    return
                pu = self.model_parent.get(u, 0)
                if pu in self.models:
                    visit(pu)
                seen.add(u)
                order.append(u)
            for u in self.models:
                visit(u)
            self._order = order
        return self._order

    def local_all(self, uid, over, T):
        """local_matrix() for T samples at once: over = {prop: (T, 3) array}; returns (T, 4, 4) numpy"""
        p = self.mprops[uid]

        def get(prop, dflt):
            if over is not None and prop in over:
                return np.asarray(over[prop], np.float64)
            return np.tile(np.array(list(p.get(prop, dflt))[:3], np.float64), (T, 1))
        t, r, s = get("Lcl Translation", [0, 0, 0]), get("Lcl Rotation", [0, 0, 0]), get("Lcl Scaling", [1, 1, 1])
        R = np_euler_xyz(r)
        pre = p.get("PreRotation")
        if pre and any(abs(x) > 1e-9 for x in pre):
            R = np_euler_xyz(np.array([list(pre)[:3]]))[0] @ R
        post = p.get("PostRotation")
        if post and any(abs(x) > 1e-9 for x in post):
            R = R @ np_euler_xyz(np.array([list(post)[:3]]))[0].T
        M = np.zeros((T, 4, 4))
        M[:, :3, :3] = R * s[:, None, :]
        M[:, :3, 3] = t
        M[:, 3, 3] = 1.0
        return M

    def world_all(self, curves, times):
        """{model uid: (T, 4, 4)} world matrices at FBX times `times` (KTime) with linear key interpolation (the curves
        carry one key per frame, so the sampled frames are exact keys)"""
        times = np.asarray(times, np.float64)
        T = len(times)
        W = {}
        for u in self.model_order():
            over = None
            if curves is not None and u in curves:
                over = {}
                for prop, (dflt, chans) in curves[u].items():
                    over[prop] = np.stack([np.interp(times, c[0].astype(np.float64), c[1]) if c is not None
                                           else np.full(T, float(dflt[i])) for i, c in enumerate(chans)], 1)
            L = self.local_all(u, over, T)
            pu = self.model_parent.get(u, 0)
            W[u] = (W[pu] @ L) if pu in W else L
        return W

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


def glb_world_all(G, an, times):
    """(N, T, 4, 4) world matrices of every glTF node at `times` (s) of animation `an` (None = rest).  LINEAR samplers
    are interpolated component-wise (quaternions re-normalised; exact on the keys, and the exporter samples every
    frame), STEP holds, CUBICSPLINE uses the key values."""
    J = G.json
    nodes = J["nodes"]
    N, T = len(nodes), len(times)
    times = np.asarray(times, np.float64)
    trs = []
    for n in nodes:
        trs.append({"translation": np.tile(np.array(n.get("translation", [0, 0, 0]), np.float64), (T, 1)),
                    "rotation": np.tile(np.array(n.get("rotation", [0, 0, 0, 1]), np.float64), (T, 1)),
                    "scale": np.tile(np.array(n.get("scale", [1, 1, 1]), np.float64), (T, 1))})
    for ch in (an or {}).get("channels", []):
        node, path = ch["target"].get("node"), ch["target"]["path"]
        if node is None or path not in ("translation", "rotation", "scale"):
            continue
        smp = an["samplers"][ch["sampler"]]
        inp = G.accessor(smp["input"])[:, 0]
        out = G.accessor(smp["output"])
        interp = smp.get("interpolation", "LINEAR")
        if interp == "CUBICSPLINE":
            out = out.reshape(len(inp), 3, -1)[:, 1, :]
        if interp == "STEP":
            k = np.clip(np.searchsorted(inp, times + 1e-6, "right") - 1, 0, len(inp) - 1)
            val = out[k]
        else:
            val = np.stack([np.interp(times, inp, out[:, c]) for c in range(out.shape[1])], 1)
        trs[node][path] = val
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    W = [None] * N

    def w(i):
        if W[i] is None:
            n = nodes[i]
            if "matrix" in n:
                L = np.tile(np.array(n["matrix"], np.float64).reshape(4, 4).T, (T, 1, 1))
            else:
                L = np.zeros((T, 4, 4))
                L[:, :3, :3] = np_quat_to_mat(trs[i]["rotation"]) * trs[i]["scale"][:, None, :]
                L[:, :3, 3] = trs[i]["translation"]
                L[:, 3, 3] = 1.0
            W[i] = (w(parent[i]) @ L) if i in parent else L
        return W[i]
    for i in range(N):
        w(i)
    return np.array(W)


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
YUP_TO_BL_NP = np.array(YUP_TO_BL)
OFF_AXIS = 0.05       # m: third comparison point per bone, M @ (OFF_AXIS, 0, 0); heads and tails lie on the bone axis
                      # and cannot see a roll about it (a 1 mm tolerance here = 1.1 deg of roll)
LIMB_RE = re.compile(r"(Leg|^FF)")      # leg chain + hoof bones: the tight twist gate (candy-wrapped forearms/shins)
# clips entered from and/or left to the standing Idle (Unity/Calf/Editor/CalfSetup.cs one-shots and chains)
STANDING_ENDS = {"TurnLeft90": "both", "TurnRight90": "both", "Leap": "both", "HeadShake": "both", "Call": "both",
                 "Idle_LookAround": "both", "Graze_Start": "start", "Graze_End": "end", "LieDown": "start",
                 "GetUp": "end", "Death": "start"}
TAIL_TIP = "Tail7"
SIZE_WINDOW = ((0.8, 1.4), (1.4, 2.0))      # plausible (height, length) at FINAL_SCALE 1
if AP.IS_DOG:     # the Rottweiler rig (tools/dog/): paw bones, a 6-bone tail, its own clip set and size
    KEY_BONES = ["Head", "FrontToe.L", "FrontToe.R", "HindToe.L", "HindToe.R", "Tail6"]
    KEY_FALLBACK = {}
    LIMB_RE = re.compile(r"(Arm|Forearm|Front|Thigh|Shin|Hind)")
    STANDING_ENDS = {"Bark": "both", "Attack": "both", "PlayBow": "both", "Jump": "both", "Sit_Start": "start",
                     "Sit_End": "end", "Lie_Start": "start", "Lie_End": "end", "Death": "start"}
    TAIL_TIP = "Tail6"
    SIZE_WINDOW = ((0.75, 1.0), (1.0, 1.4))  # withers 0.66 m (head 0.89 m), 1.18 m nose to hanging tail


# ============================================================================================ numpy transform helpers
def np_euler_xyz(deg):
    """(T, 3) Euler XYZ degrees (FBX / Blender 'XYZ': X applied first) -> (T, 3, 3) = Rz @ Ry @ Rx"""
    r = np.radians(np.asarray(deg, np.float64))
    cx, cy, cz = np.cos(r[:, 0]), np.cos(r[:, 1]), np.cos(r[:, 2])
    sx, sy, sz = np.sin(r[:, 0]), np.sin(r[:, 1]), np.sin(r[:, 2])
    R = np.empty((len(r), 3, 3))
    R[:, 0, 0] = cy * cz; R[:, 0, 1] = sx * sy * cz - cx * sz; R[:, 0, 2] = cx * sy * cz + sx * sz
    R[:, 1, 0] = cy * sz; R[:, 1, 1] = sx * sy * sz + cx * cz; R[:, 1, 2] = cx * sy * sz - sx * cz
    R[:, 2, 0] = -sy;     R[:, 2, 1] = sx * cy;                R[:, 2, 2] = cx * cy
    return R


def np_quat_to_mat(q):
    """(T, 4) quaternions (x, y, z, w; glTF order, normalised here) -> (T, 3, 3)"""
    q = np.asarray(q, np.float64)
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    R = np.empty((len(q), 3, 3))
    R[:, 0, 0] = 1 - 2 * (y * y + z * z); R[:, 0, 1] = 2 * (x * y - z * w); R[:, 0, 2] = 2 * (x * z + y * w)
    R[:, 1, 0] = 2 * (x * y + z * w); R[:, 1, 1] = 1 - 2 * (x * x + z * z); R[:, 1, 2] = 2 * (y * z - x * w)
    R[:, 2, 0] = 2 * (x * z - y * w); R[:, 2, 1] = 2 * (y * z + x * w); R[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return R


def np_mat_to_quat(R):
    """(..., 3, 3) rotation matrices -> (..., 4) quaternions (w, x, y, z), w >= 0 (Shepperd, robust at 180 deg)"""
    R = np.asarray(R, np.float64)
    m00, m11, m22 = R[..., 0, 0], R[..., 1, 1], R[..., 2, 2]
    tr = m00 + m11 + m22
    cands = np.stack([tr, m00, m11, m22], -1)
    k = np.argmax(cands, -1)
    q = np.zeros(R.shape[:-2] + (4,))
    s = np.sqrt(np.maximum(1.0 + 2.0 * np.take_along_axis(cands, k[..., None], -1)[..., 0] - tr, 1e-18)) * 2.0
    # s = 4 * |largest component|
    w0 = k == 0
    q[w0] = np.stack([0.25 * s[w0], (R[w0][:, 2, 1] - R[w0][:, 1, 2]) / s[w0], (R[w0][:, 0, 2] - R[w0][:, 2, 0]) / s[w0],
                      (R[w0][:, 1, 0] - R[w0][:, 0, 1]) / s[w0]], -1)
    w1 = k == 1
    q[w1] = np.stack([(R[w1][:, 2, 1] - R[w1][:, 1, 2]) / s[w1], 0.25 * s[w1], (R[w1][:, 0, 1] + R[w1][:, 1, 0]) / s[w1],
                      (R[w1][:, 0, 2] + R[w1][:, 2, 0]) / s[w1]], -1)
    w2 = k == 2
    q[w2] = np.stack([(R[w2][:, 0, 2] - R[w2][:, 2, 0]) / s[w2], (R[w2][:, 0, 1] + R[w2][:, 1, 0]) / s[w2], 0.25 * s[w2],
                      (R[w2][:, 1, 2] + R[w2][:, 2, 1]) / s[w2]], -1)
    w3 = k == 3
    q[w3] = np.stack([(R[w3][:, 1, 0] - R[w3][:, 0, 1]) / s[w3], (R[w3][:, 0, 2] + R[w3][:, 2, 0]) / s[w3],
                      (R[w3][:, 1, 2] + R[w3][:, 2, 1]) / s[w3], 0.25 * s[w3]], -1)
    q *= np.where(q[..., :1] < 0, -1.0, 1.0)
    return q


def np_twist_y(R):
    """signed twist (deg) about the local Y axis of rotations R (..., 3, 3) (swing-twist decomposition)"""
    q = np_mat_to_quat(R)
    return (np.degrees(2.0 * np.arctan2(q[..., 2], q[..., 0])) + 180.0) % 360.0 - 180.0


def np_rot_angle(R):
    q = np_mat_to_quat(R)
    return np.degrees(2.0 * np.arccos(np.clip(q[..., 0], -1.0, 1.0)))


def np_normalise3(M):
    """rotation part of (..., 4, 4) matrices with the column scale removed"""
    R = M[..., :3, :3]
    return R / np.maximum(np.linalg.norm(R, axis=-2, keepdims=True), 1e-12)


def bone_points(M, length):
    """world matrix (4x4, numpy) -> (head, tail point M @ (0, L, 0), off-axis point M @ (OFF_AXIS, 0, 0))"""
    h = M[:3, 3]
    return (h.copy(), M[:3, 1] * length + h, M[:3, 0] * OFF_AXIS + h)


def point_err(sp, dp):
    return max(float(np.linalg.norm(np.asarray(s) - np.asarray(d))) for s, d in zip(sp, dp))


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


def bone_mats(arm, names, frames):
    """(F, B, 4, 4) world matrices of the pose bones `names` (NaN for a missing bone) on `frames`"""
    sc = bpy.context.scene
    pbs = [arm.pose.bones.get(n) for n in names]
    out = np.full((len(frames), len(names), 4, 4), np.nan)
    for i, f in enumerate(frames):
        sc.frame_set(int(f))
        mw = arm.matrix_world
        for j, pb in enumerate(pbs):
            if pb is not None:
                out[i, j] = np.array(mw @ pb.matrix)
    return out


def bone_samples(arm, names, lengths, frames, mats=None):
    """{frame: {bone: (head, tail point, off-axis point)}} in world space: tail point = M @ (0, L_src, 0), off-axis
    point = M @ (OFF_AXIS, 0, 0) (sees a roll about the bone axis)"""
    M = bone_mats(arm, names, frames) if mats is None else mats
    out = {}
    for i, f in enumerate(frames):
        out[f] = {n: bone_points(M[i, j], lengths[n]) for j, n in enumerate(names) if not np.isnan(M[i, j, 0, 0])}
    return out


def twist_report(M, names, parent, rest):
    """per-frame twist continuity of an action: M (F, B, 4, 4) world matrices on consecutive frames.
    pop[f, b]   = twist (deg) about bone b's own Y axis between frames f and f+1 (a flip shows as ~180)
    local[f, b] = twist of bone b relative to its rest attachment on its parent (candy-wrap territory near 180)
    rot[f, b]   = total local rotation angle (deg) relative to the rest attachment"""
    R = np_normalise3(M)
    pop = np.abs(np_twist_y(np.einsum("fbji,fbjk->fbik", R[:-1], R[1:]))) if len(M) > 1 else np.zeros((0, len(names)))
    idx = {n: j for j, n in enumerate(names)}
    local = np.zeros((len(M), len(names)))
    rot = np.zeros((len(M), len(names)))
    ends = np.tile(np.eye(3), (2, len(names), 1, 1))      # local rotations on the first and last frame
    for j, n in enumerate(names):
        p = parent.get(n)
        if p in idx:
            att = rest[p]
            base = np.einsum("fij,jk->fik", M[:, idx[p]], np.linalg.inv(att) @ rest[n])     # rest attachment, posed
            L = np.einsum("fji,fjk->fik", np_normalise3(base), R[:, j])
        else:           # a root joint (Root: the root-motion node, yaws in the turns): its twist is not a skin issue
            L = np.einsum("ji,fjk->fik", np_normalise3(rest[n][None])[0], R[:, j])
            rot[:, j] = np_rot_angle(L)
            continue
        local[:, j] = np.abs(np_twist_y(L))
        rot[:, j] = np_rot_angle(L)
        ends[0, j], ends[1, j] = L[0], L[-1]
    return pop, local, rot, ends


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


def sample_frames(lo, hi, n=0):
    """n <= 0: every frame; else about n evenly spaced frames plus the last"""
    lo, hi = int(round(lo)), int(round(hi))
    step = max(1, (hi - lo) // n) if n and n > 0 else 1
    fr = list(range(lo, hi + 1, step))
    if fr[-1] != hi:
        fr.append(hi)
    return fr


def compare(src_samp, dst_samp, frame_map, bones, key_bones):
    """max errors (heads / tail points / off-axis points) over all bones and over key bones"""
    worst_all, worst_key, where = 0.0, 0.0, None
    for f, fd in frame_map.items():
        s, d = src_samp[f], dst_samp[fd]
        for n in bones:
            if n not in s or n not in d:
                continue
            e = point_err(s[n], d[n])
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


def _is_body(mat_name):
    """the body material: M_Calf_Body (calf) or M_Cow_Body (adult cow, renamed by tools/scale_asset.py)"""
    return re.fullmatch(r"M_[A-Za-z]+_Body", mat_name or "") is not None


def bbox(pts):
    return pts.min(0), pts.max(0)


# ============================================================================================ source
def load_source(a, manifest):
    bpy.ops.wm.open_mainfile(filepath=a.src)
    sc = bpy.context.scene
    arm = (bpy.data.objects.get("CalfRig") or bpy.data.objects.get("CowRig") or bpy.data.objects.get(AP.NAME + "Rig")
           or find_armature())
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
            exp = [m for m in info["mats"] if not _is_body(m)] + [m for m in info["mats"] if _is_body(m)]
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
    S["rest_mats"] = {b.name: np.array(arm.matrix_world @ b.matrix_local) for b in arm.data.bones}
    S["samples"], S["mesh"], S["twist"] = {}, {}, {}
    for name, (lo, hi) in S["actions"].items():
        use_action(arm, bpy.data.actions[name])
        fr = sample_frames(lo, hi, a.samples)
        M = bone_mats(arm, S["bones"], fr)
        S["samples"][name] = bone_samples(arm, S["bones"], S["lengths"], fr, mats=M)
        allf = list(range(int(round(lo)), int(round(hi)) + 1))
        Mt = M if fr == allf else bone_mats(arm, S["bones"], allf)
        S["twist"][name] = (allf, twist_report(Mt, S["bones"], S["parent"], S["rest_mats"]))
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


def check_twist(a, S):
    """Twist continuity of every clip (source = the exported takes, which the motion checks compare with heads, tails
    and off-axis points).  A bone that rolls ~180 deg about its own axis between two frames keeps its joint positions
    but candy-wraps its skin (the IK roll flip of an ill-conditioned pole).
      FAIL  a leg/hoof bone (LIMB_RE) twists > --twist-limb-deg between consecutive frames, or any bone
            > --twist-fail-deg, or any bone's twist relative to its parent exceeds --twist-local-deg
      WARN  any bone twists > --twist-warn-deg between consecutive frames"""
    sec = "anim"
    names = S["bones"]
    limb = np.array([bool(LIMB_RE.search(n)) for n in names])
    S["rot_max"] = {}
    for clip, (frames, (pop, local, rot, _)) in S["twist"].items():
        for j, n in enumerate(names):
            i = int(rot[:, j].argmax())
            if rot[i, j] > S["rot_max"].get(n, (-1.0,))[0]:
                S["rot_max"][n] = (float(rot[i, j]), clip, frames[i])
        top = []
        if pop.size:
            order = np.argsort(-pop.max(0))
            for j in order[:3]:
                i = int(pop[:, j].argmax())
                top.append("%s %.1f f%d->%d" % (names[j], pop[i, j], frames[i], frames[i + 1]))
        limb_pop = float(pop[:, limb].max()) if pop.size and limb.any() else 0.0
        any_pop = float(pop.max()) if pop.size else 0.0
        jl = int(local.max(0).argmax())
        il = int(local[:, jl].argmax())
        loc = float(local[il, jl])
        fail = limb_pop > a.twist_limb_deg or any_pop > a.twist_fail_deg or loc > a.twist_local_deg
        status = False if fail else ("WARN" if any_pop > a.twist_warn_deg else True)
        check(sec, "%s twist continuity" % clip, status,
              "max per-frame twist about the bone's own axis: legs/hooves %.1f deg (limit %g), all bones %.1f deg "
              "(warn %g, fail %g); top %s; max twist vs parent %.1f deg (%s f%d, limit %g)" %
              (limb_pop, a.twist_limb_deg, any_pop, a.twist_warn_deg, a.twist_fail_deg, "; ".join(top) or "-",
               loc, names[jl], frames[il], a.twist_local_deg))
    # one-shot boundaries: clips that CalfSetup.cs enters from / leaves to the standing Idle with a short cross-fade
    # should start / end on the standing pose (local joint rotations vs Idle f0; Root excluded, it carries the motion)
    ref = S["twist"].get(a.boundary_ref)
    if ref is None:
        return
    Lref = ref[1][3][0]
    for clip, ends_want in STANDING_ENDS.items():
        if clip not in S["twist"]:
            continue
        E = S["twist"][clip][1][3]
        parts, worst = [], 0.0
        for k, tag in ((0, "start"), (1, "end")):
            if ends_want not in (tag, "both"):
                continue
            ang = np_rot_angle(np.einsum("bji,bjk->bik", E[k], Lref))
            j = int(ang.argmax())
            worst = max(worst, float(ang[j]))
            parts.append("%s %.1f deg (%s)" % (tag, ang[j], names[j]))
        check(sec, "%s boundary vs %s f0" % (clip, a.boundary_ref), "WARN" if worst > a.boundary_warn_deg else True,
              "%s: max local joint rotation difference %s (warn > %g: the Animator cross-fades this into / out of %s)" %
              ("start and end" if ends_want == "both" else ends_want, ", ".join(parts), a.boundary_warn_deg, a.boundary_ref))


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
        cl_data, empty = [], []
        for sk in skins:
            for cl in F.linked(sk, "Deformer"):
                node = F.objs[cl]
                bone = [pa for pa, typ, prop in F.children_of.get(cl, []) if pa in F.models]
                idx = node.find("Indexes")
                if idx is None:
                    if bone:
                        empty.append(F.name(bone[0]))
                    continue
                clusters += 1
                ii = idx.props[0]
                ww = F.objs[cl].find("Weights").props[0]
                nz = ww > 0
                np.add.at(cnt, ii[nz], 1)
                np.add.at(sums, ii[nz], ww[nz])
                if bone and nz.any():
                    # FBX SDK semantics: bind = TransformLink^-1 @ (mesh global at bind); the mesh global is taken from
                    # the mesh node (Blender stores the cluster "Transform" already in bone space, TL^-1 @ mesh, in the
                    # file, see export_fbx_bin.py; the SDK reports it as the mesh global)
                    TL = np.array(node.find("TransformLink").props[0], np.float64).reshape(4, 4).T  # column-major
                    Wm = np.array(F.local_matrix(model_of[lname]))
                    pu = F.model_parent.get(model_of[lname], 0)
                    while pu in F.models:
                        Wm = np.array(F.local_matrix(pu)) @ Wm
                        pu = F.model_parent.get(pu, 0)
                    cl_data.append((bone[0], ii[nz], ww[nz].astype(np.float64), np.linalg.inv(TL) @ Wm))
                elif bone:
                    empty.append(F.name(bone[0]))
        check(sec, "%s skin influences" % lname, cnt.max() <= 4 and cnt.min() >= 1,
              "max %d, min %d per vertex, %d non-empty clusters, histogram %s" % (cnt.max(), cnt.min(), clusters, np.bincount(cnt).tolist()))
        dev = np.abs(sums - 1).max()
        check(sec, "%s skin weight sums" % lname, dev <= 1e-3, "max |sum-1| = %.2e" % dev)
        # deforming joints without any weight: Root is expected (root-motion node); an animated chain joint without
        # weights (e.g. Tail5 inherited from cow.glb) only moves its children, its own segment cannot follow it
        rot = S.get("rot_max", {})
        odd = sorted(n for n in set(empty) | {n for n in S["bones"] if n in limbs and n not in
                                               {F.name(c[0]) for c in cl_data} and n not in S["dropped"]}
                     if n != "Root")
        anim = [n for n in odd if rot.get(n, (0.0,))[0] > 1.0]
        check(sec, "%s unweighted joints" % lname, "WARN" if anim else True,
              "joints without weights (besides Root): %s%s" % (odd or "none", "; animated: " + ", ".join(
                  "%s up to %.1f deg (%s f%d)" % (n, rot[n][0], rot[n][1], rot[n][2]) for n in anim) if anim else ""))
        # FBX skin (what Unity computes): v = sum_k w_k * W_bone(t) @ TransformLink^-1 @ Transform @ v_mesh
        if cl_data:
            idx4 = np.zeros((nv, 4), np.int64)
            w4 = np.zeros((nv, 4))
            slot = np.zeros(nv, np.int64)
            for k, (_, ii, ww, _) in enumerate(cl_data):
                keep = slot[ii] < 4
                idx4[ii[keep], slot[ii[keep]]] = k
                w4[ii[keep], slot[ii[keep]]] = ww[keep]
                slot[ii[keep]] += 1
            F.skin = getattr(F, "skin", {})
            F.skin[lname] = {"verts": g.find("Vertices").props[0].reshape(-1, 3).astype(np.float64),
                             "bones": [c[0] for c in cl_data], "bind": np.array([c[3] for c in cl_data]),
                             "idx": idx4, "w": w4}

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

    # take evaluation with FBX maths, every sampled frame (default: every frame), 3 points per bone (head, tail,
    # off-axis: a roll about the bone axis is caught too)
    conv = YUP_TO_BL @ Matrix.Diagonal(Vector((unit, unit, unit, 1.0)))
    conv_np = np.array(conv)
    F.conv = conv_np

    def world_mats(curves, t):
        W = {}
        for u in F.model_order():
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
            M = np.array(conv @ W[limbs[n]])
            err_rest = max(err_rest, point_err(S["rest"][n], bone_points(M, lengths[n])))
    check(sec, "rest skeleton vs source", err_rest <= a.tol_mm / 1000,
          "max error %s (joint heads, bone-axis and off-axis points)" % mm(err_rest))
    F.take_times = {}
    for n, (lo, hi) in want.items():
        if n not in stacks:
            continue
        curves = F.stack_curves(stacks[n])
        keyed = [F.name(u) for u in curves if u in limbs.values()]
        frames = sorted(S["samples"][n])
        times = sp[n][0] + np.round((np.array(frames, np.float64) - lo) / fps * FBX_KTIME)
        F.take_times[n] = (stacks[n], sp[n][0], lo)
        Wt = F.world_all(curves, times)
        e_all = e_key = 0.0
        where = None
        for i, f in enumerate(frames):
            sd = S["samples"][n][f]
            for b in S["bones"]:
                if b not in limbs or b not in sd:
                    continue
                e = point_err(sd[b], bone_points(conv_np @ Wt[limbs[b]][i], lengths[b]))
                if e > e_all:
                    e_all, where = e, (b, f)
                if b in S["key_bones"]:
                    e_key = max(e_key, e)
        check(sec, "take %s motion (FBX maths)" % n, e_all <= a.tol_mm / 1000,
              "%d bones keyed; over %d frames: key bones max %s, all bones max %s (heads, tails, off-axis points)%s" %
              (len(keyed), len(frames), mm(e_key), mm(e_all), (" at %s f%d" % where) if where and e_all > a.tol_mm / 1000 else ""))
        if "Root" in limbs:
            # root motion as Unity reads it, every sampled frame: FBX (x, y, z) -> Unity (-x, y, z); rotations mirrored
            Rw = Wt[limbs["Root"]]
            pos = Rw[:, :3, 3] * unit
            pos = (pos - pos[0]) * np.array([-1.0, 1.0, 1.0])
            Mx = np.diag([-1.0, 1.0, 1.0])
            R0 = np_normalise3(Rw[:1])[0]
            Rrel = Mx @ np.einsum("fij,kj->fik", np_normalise3(Rw), R0) @ Mx       # world-frame delta vs frame 0
            fwd, up = Rrel[:, :, 2], Rrel[:, :, 1]
            yaw = np.degrees(np.unwrap(np.arctan2(fwd[:, 0], fwd[:, 2])))
            tilt = np.degrees(np.arccos(np.clip(up[:, 1], -1.0, 1.0)))
            flat = np.abs(pos[:, 1]).max() <= 0.001 and tilt.max() <= 0.05
            check(sec, "take %s root motion" % n, True if flat else "WARN",
                  "Unity space over %d frames: x %+.3f..%+.3f m, z %+.3f..%+.3f m (end %+.3f, %+.3f), height |y| max %.1f mm, "
                  "yaw %+.1f..%+.1f deg (end %+.1f), pitch/roll max %.2f deg%s" %
                  (len(frames), pos[:, 0].min(), pos[:, 0].max(), pos[:, 2].min(), pos[:, 2].max(), pos[-1, 0], pos[-1, 2],
                   np.abs(pos[:, 1]).max() * 1000, yaw.min(), yaw.max(), yaw[-1], tilt.max(),
                   "" if flat else " (the Root was designed to stay on the ground plane and upright)"))
    # facing in Unity space: FBX (x, y, z) -> Unity (-x, y, z) * unit
    W = world_mats(None, 0)

    def unity(n):
        p = W[limbs[n]].translation * unit
        return Vector((-p.x, p.y, p.z))
    if "Head" in limbs and TAIL_TIP in limbs:
        h, t = unity("Head"), unity(TAIL_TIP)
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


# ============================================================================================ skin, every frame
def skin_np(Mb, idx, w, vh):
    """linear blend skinning: Mb (B, 4, 4) skinning matrices, idx/w (V, 4) influences, vh (V, 4) homogeneous"""
    out = np.zeros((len(vh), 3))
    for k in range(idx.shape[1]):
        if not w[:, k].any():
            continue
        out += w[:, k, None] * np.einsum("vij,vj->vi", Mb[idx[:, k], :3, :], vh)
    return out


def check_skin_frames(a, S, F, G):
    """Skinned-vertex deviation of the shipped skins from the Blender source (all influences, what every clip QA and
    review render shows) on EVERY frame of every clip, with the engines' own maths:
      FBX  v = sum_k w_k * W_bone(t) @ TransformLink^-1 @ Transform @ v   (clusters + take curves, as Unity's FBX SDK)
      GLB  v = sum_k w_k * W_joint(t) @ IBM @ v                            (glTF 2.0 skinning; LOD0 only)
    The deviation is the effect of the 4-influence limit (plus export precision)."""
    sec = "skin"
    fbx_lods = [n for n in S["lods"] if F is not None and n in getattr(F, "skin", {})]
    use_glb = G is not None and G.mesh_node is not None and G.json.get("skins")
    if not fbx_lods and not use_glb:
        return
    t_start = time.time()
    bpy.ops.wm.open_mainfile(filepath=a.src)
    sc = bpy.context.scene
    arm = bpy.data.objects[S["arm"]]
    objs = {n: bpy.data.objects[n] for n in S["lods"]}
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_viewport = o.name not in objs
    use_action(arm, None)
    sc.frame_set(0)
    rest = {n: mesh_world_coords(o) for n, o in objs.items()}
    conv = getattr(F, "conv", np.array(YUP_TO_BL)) if F is not None else None
    prep = {}
    for n in fbx_lods:
        sk = F.skin[n]
        vh = np.c_[sk["verts"], np.ones(len(sk["verts"]))]
        if len(vh) != len(rest[n]):
            check(sec, "%s FBX vertices" % n, False, "%d FBX vertices vs %d source vertices" % (len(vh), len(rest[n])))
            continue
        W0 = F.world_all(None, [0.0])
        Mb = np.array([W0[u][0] for u in sk["bones"]]) @ sk["bind"]
        Xb = skin_np(Mb, sk["idx"], sk["w"], vh) @ conv[:3, :3].T + conv[:3, 3]
        e_bind = float(np.linalg.norm(Xb - rest[n], axis=1).max())
        prep[n] = (vh, e_bind)
    gprep = None
    if use_glb:
        J = G.json
        skin = J["skins"][0]
        joints = skin["joints"]
        ibm = G.accessor(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
        P, Jn, Wg = [], [], []
        for prim in J["meshes"][J["nodes"][G.mesh_node]["mesh"]]["primitives"]:
            at = prim["attributes"]
            if not {"POSITION", "JOINTS_0", "WEIGHTS_0"} <= set(at):
                continue
            P.append(G.accessor(at["POSITION"]))
            Jn.append(G.accessor(at["JOINTS_0"]).astype(np.int64))
            Wg.append(G.accessor(at["WEIGHTS_0"]))
        if P:
            from mathutils.kdtree import KDTree
            vh_g = np.c_[np.concatenate(P), np.ones(sum(len(p) for p in P))]
            jn, wg = np.concatenate(Jn), np.concatenate(Wg)
            W0 = glb_world_all(G, None, [0.0])
            Xr = skin_np(W0[joints, 0] @ ibm, jn, wg, vh_g) @ YUP_TO_BL_NP[:3, :3].T
            src0 = rest[S["lod0"]]
            kd = KDTree(len(src0))
            for i, co in enumerate(src0):
                kd.insert(co, i)
            kd.balance()
            vmap = np.empty(len(Xr), np.int64)
            dmap = np.empty(len(Xr))
            for i, co in enumerate(Xr):
                _, vmap[i], dmap[i] = kd.find(co)
            gprep = (vh_g, jn, wg, ibm, joints, vmap, float(dmap.max()))
    fps = S["fps"]
    res = {n: [] for n in prep}
    gres = []
    nfr = 0
    for clip, (lo, hi) in S["actions"].items():
        frames = list(range(int(round(lo)), int(round(hi)) + 1))
        fr = np.array(frames, np.float64)
        use_action(arm, bpy.data.actions[clip])
        Mf = {}
        if prep and clip in getattr(F, "take_times", {}):
            stack, t0, lo_ = F.take_times[clip]
            Wt = F.world_all(F.stack_curves(stack), t0 + np.round((fr - lo_) / F.fps * FBX_KTIME))
            for n in prep:
                sk = F.skin[n]
                Mf[n] = np.stack([Wt[u] for u in sk["bones"]], 1) @ sk["bind"][None]       # (T, B, 4, 4)
        Mg = None
        if gprep is not None and clip in G.anims:
            vh_g, jn, wg, ibm, joints, vmap, _ = gprep
            Mg = glb_world_all(G, G.anims[clip], (fr - lo) / fps)[joints].transpose(1, 0, 2, 3) @ ibm[None]
        for i, f in enumerate(frames):
            sc.frame_set(f)
            nfr += 1
            src = {}
            for n in Mf:
                src[n] = mesh_world_coords(objs[n])
                sk = F.skin[n]
                X = skin_np(Mf[n][i], sk["idx"], sk["w"], prep[n][0]) @ conv[:3, :3].T + conv[:3, 3]
                d = np.linalg.norm(X - src[n], axis=1)
                v = int(d.argmax())
                res[n].append((float(d[v]), clip, f, v, float(np.percentile(d, 99.9)), float(d.mean())))
            if Mg is not None:
                s0 = src.get(S["lod0"])
                if s0 is None:
                    s0 = mesh_world_coords(objs[S["lod0"]])
                X = skin_np(Mg[i], jn, wg, vh_g) @ YUP_TO_BL_NP[:3, :3].T
                d = np.linalg.norm(X - s0[vmap], axis=1)
                v = int(d.argmax())
                gres.append((float(d[v]), clip, f, int(vmap[v]), float(np.percentile(d, 99.9)), float(d.mean())))
    log("skin deviation over %d frames in %.1f s" % (nfr, time.time() - t_start))

    def report(name, rows, extra, rest_err, rest_coords):
        if not rows:
            return
        w = max(rows)
        per = {}
        for r in rows:
            per[r[1]] = max(per.get(r[1], 0.0), r[0])
        top = sorted(per.items(), key=lambda kv: -kv[1])
        p = rest_coords[w[3]]
        status = True if w[0] <= a.skin_warn_mm / 1000 else ("WARN" if w[0] <= a.skin_fail_mm / 1000 else False)
        if rest_err > a.tol_mm / 1000:
            status = False
        check(sec, name, status,
              "every frame (%d): worst %s f%d max %s at v%d (rest %.3f, %.3f, %.3f), 99.9%% %s, mean %s; per-clip max %s; "
              "rest pose %s%s (pass <= %g mm, warn <= %g mm)" %
              (len(rows), w[1], w[2], mm(w[0]), w[3], p[0], p[1], p[2], mm(w[4]), mm(w[5]),
               ", ".join("%s %.1f" % (c, e * 1000) for c, e in top[:8]), mm(rest_err), extra, a.skin_warn_mm, a.skin_fail_mm))
    for n in prep:
        report("%s FBX skin vs source" % n, res[n], "", prep[n][1], rest[n])
    if gprep is not None:
        report("%s GLB skin vs source" % S["lod0"], gres, " (GLB vertex -> source vertex map max %s)" % mm(gprep[6]),
               gprep[6], rest[S["lod0"]])
    S["skin_worst"] = {n: max(r) if r else None for n, r in list(res.items()) + [("glb", gres)]}


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
    e = max(point_err(rest[n], S["rest"][n]) for n in S["bones"] if n in rest)
    check(sec, "rest skeleton vs source", e <= a.tol_mm / 1000, "max error %s (joint heads, bone-axis and off-axis points)" % mm(e))
    head, tail = rest["Head"][0], rest[TAIL_TIP][0] if TAIL_TIP in rest else rest[S["bones"][-1]][0]
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
              "range %g-%g (source %g-%g); key bones %s max %s, all bones max %s over %d frames (heads, tails, off-axis points)%s" %
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
        k = AP.FINAL_SCALE      # plausible size window: calf 0.8-1.4 m high, 1.4-2.0 m long; the adult cow x1.42
        (h0, h1), (l0, l1) = SIZE_WINDOW
        ok = np.abs(mn - smn).max() < 0.002 and np.abs(mx - smx).max() < 0.002 and h0 * k < dim[2] < h1 * k \
            and l0 * k < dim[1] < l1 * k
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
                # the every-frame deviation (with Unity's own FBX skinning maths) is the [skin] check; this one is the
                # Blender-importer cross-check on 3 frames per clip, so it only fails on a gross error
                status = True if w[0] <= a.skin_warn_mm / 1000 else ("INFO" if w[0] <= a.skin_fail_mm / 1000 else False)
                check(sec, "LOD0 skinned vertices vs source", status,
                      "Blender FBX importer, first/mid/last frame of each clip (%d frames): worst %s f%d max %s, 99.9%% %s, "
                      "mean %s (4-influence limit + export precision; every frame: see [skin])" %
                      (len(devs), w[3], w[4], mm(w[0]), mm(w[2]), mm(w[1])))
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
        return None
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
    e_rest = max(point_err(S["rest"][n], bone_points(YUP_TO_BL_NP @ np.array(W[j]), S["lengths"][n]))
                 for n, j in jidx.items() if n in S["rest"])
    check(sec, "rest skeleton vs source", e_rest <= a.tol_mm / 1000,
          "max error %s (joint heads, bone-axis and off-axis points)" % mm(e_rest))
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
    t = (YUP_TO_BL @ W[jidx[TAIL_TIP]]).translation if TAIL_TIP in jidx else None
    if h is not None and t is not None:
        gh, gt = W[jidx["Head"]].translation, W[jidx[TAIL_TIP]].translation
        check(sec, "facing (glTF space)", gh.z > gt.z and gh.y > 0.3,
              "Head z=%.3f > Tail7 z=%.3f: front = glTF +Z (glTF convention), up = +Y" % (gh.z, gt.z))
    # animations
    anims = {an.get("name"): an for an in J.get("animations", [])}
    check(sec, "animations present", sorted(anims) == sorted(S["actions"]),
          "%s (source %s)" % (sorted(anims), sorted(S["actions"])))
    fps = S["fps"]
    G.anims, G.jidx, G.mesh_node = anims, jidx, (mesh_nodes[0] if mesh_nodes else None)
    for n, (lo, hi) in S["actions"].items():
        if n not in anims:
            continue
        an = anims[n]
        t0, t1 = 1e9, -1e9
        for ch in an["channels"]:
            inp = G.accessor(an["samplers"][ch["sampler"]]["input"])
            t0, t1 = min(t0, inp.min()), max(t1, inp.max())
        frames = sorted(S["samples"][n])
        Wt = glb_world_all(G, an, (np.array(frames, np.float64) - lo) / fps)
        e_all = e_key = 0.0
        where = None
        for i, f in enumerate(frames):
            sd = S["samples"][n][f]
            for b, j in jidx.items():
                if b not in sd:
                    continue
                e = point_err(sd[b], bone_points(YUP_TO_BL_NP @ Wt[j, i], S["lengths"][b]))
                if e > e_all:
                    e_all, where = e, (b, f)
                if b in S["key_bones"]:
                    e_key = max(e_key, e)
        dur_ok = abs(t0) < 1e-6 and abs((t1 - t0) - (hi - lo) / fps) < 1e-4
        check(sec, "anim %s" % n, dur_ok and e_all <= a.tol_mm / 1000,
              "t %.4f-%.4f s (source %.4f s), %d channels; over %d frames: key bones max %s, all bones max %s "
              "(heads, tails, off-axis points)%s" %
              (t0, t1, (hi - lo) / fps, len(an["channels"]), len(frames), mm(e_key), mm(e_all),
               (" at %s f%d" % where) if e_all > a.tol_mm / 1000 else ""))
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
    ds = [m.get("name") for m in J.get("materials", []) if m.get("doubleSided")]
    check(sec, "materials single-sided", "WARN" if ds else True,
          ("doubleSided=true on %s: glTF engines disable backface culling for the closed body" % ds) if ds else
          "doubleSided false on every material (closed meshes, backface culling)")
    sizes, vram, total = [], 0.0, 0
    for im in imgs:
        if "bufferView" not in im:
            continue
        bv = J["bufferViews"][im["bufferView"]]
        raw = G.bin[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        total += bv["byteLength"]
        wh = struct.unpack(">II", raw[16:24]) if raw[:8] == b"\x89PNG\r\n\x1a\n" else None
        if wh is None and raw[:2] == b"\xff\xd8":           # JPEG: scan for the SOF marker
            k = 2
            while k < len(raw) - 9:
                mk, ln = raw[k + 1], struct.unpack(">H", raw[k + 2:k + 4])[0]
                if mk in (0xC0, 0xC1, 0xC2):
                    wh = struct.unpack(">HH", raw[k + 5:k + 9])[::-1]
                    break
                k += 2 + ln
        if wh:
            vram += wh[0] * wh[1] * 4 * 4 / 3.0 / 1e6          # RGBA8 + mips: what a PNG/JPEG decodes to at runtime
        sizes.append("%s %s %.1f MB" % (im.get("name"), "%dx%d" % tuple(wh) if wh else "?", bv["byteLength"] / 1e6))
    if imgs:
        check(sec, "texture memory", "WARN" if vram > a.glb_vram_warn_mb else True,
              "%s; %.1f MB of %.1f MB file; decoded uncompressed (PNG/JPEG in glTFast) ~%.0f MB VRAM with mips (warn > %g)" %
              ("; ".join(sizes), total / 1e6, G.size / 1e6, vram, a.glb_vram_warn_mb))
    return G


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
    e = max(point_err(rest[n], S["rest"][n]) for n in S["bones"] if n in rest)
    check(sec, "rest skeleton vs source", e <= a.tol_mm / 1000, "max error %s (joint heads, bone-axis and off-axis points)" % mm(e))
    if "Head" in rest and TAIL_TIP in rest:
        check(sec, "facing", rest["Head"][0][1] < rest[TAIL_TIP][0][1],
              "Head y=%.3f < %s y=%.3f" % (rest["Head"][0][1], TAIL_TIP, rest[TAIL_TIP][0][1]))
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
              "range %g-%g; key bones max %s, all bones max %s over %d frames (heads, tails, off-axis points)%s" % (act.frame_range[0], act.frame_range[1], mm(e_key), mm(e_all), len(fmap),
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
    """contact sheets of the source, the FBX and the GLB (Blender imports) on the same pose, for a visual check; the
    three BBOX lines printed by render_views.py must agree (same pose)"""
    os.makedirs(a.render_dir, exist_ok=True)
    rv = os.path.join(HERE, "render_views.py")
    name, (lo, hi) = next(iter(S["actions"].items())) if S["actions"] else (None, (0, 0))
    fps = int(round(S["fps"]))
    rv_fps = "--fps" in open(rv).read()          # render_views.py can set the scene rate before importing
    # Otherwise the glTF importer lays the 30 fps samples onto the factory scene's 24 fps timeline (frame = t * 24):
    # pick a frame whose time is an exact 24 fps frame too (a multiple of 5 frames at 30 fps).
    step = 1 if rv_fps else fps // math.gcd(fps, 24)
    rel = int(round((hi - lo) / 2.0 / step)) * step
    f = int(lo) + rel
    glb_frame = rel if rv_fps else rel * 24 // fps
    # render_views imports FBX takes as "<armature>|<take>" with Blender's default +1 frame offset (the FBX importer
    # sets the scene to the file's 30 fps itself)
    jobs = [("src", a.src, name, f), ("fbx", a.fbx, "%s|%s" % (S["arm"], name), rel + 1), ("glb", a.glb, name, glb_frame)]
    boxes = {}
    for tag, path, act, fr in jobs:
        out = os.path.join(a.render_dir, "export_%s.png" % tag)
        cmd = [sys.executable, rv, path, out, "--res", str(a.render_res), "--samples", "12",
               "--views", "side,front,threequarter,back,head,otherside"]
        if act:
            cmd += ["--action", act, "--frame", str(fr)]
        if rv_fps:
            cmd += ["--fps", str(fps)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        bb = [l for l in r.stdout.splitlines() if l.startswith("BBOX")]
        if bb:
            nums = [float(x) for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", bb[0])]
            if len(nums) == 6:
                boxes[tag] = np.array(nums)
        check("render", tag, r.returncode == 0 and os.path.isfile(out),
              "%s (%s f%d) %s" % (out, act, fr, bb[0] if bb else r.stderr[-200:]))
    if "src" in boxes and len(boxes) > 1:
        d = {t: float(np.abs(b - boxes["src"]).max()) for t, b in boxes.items() if t != "src"}
        w = max(d.values())
        check("render", "same pose (BBOX)", True if w <= 0.005 else ("WARN" if w <= 0.015 else False),
              "%s f%d: bounding box vs source %s (the 4-influence skin may move the extremes a few mm)" %
              (name, f, ", ".join("%s %.1f mm" % (t, e * 1000) for t, e in sorted(d.items()))))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fbx", required=True)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--manifest", default=None, help="default: <fbx dir>/<fbx name>_export_manifest.json if present")
    ap.add_argument("--tol-mm", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=0,
                    help="sampled frames per action for the bone checks (plus first/last); 0 = every frame (default)")
    ap.add_argument("--twist-limb-deg", type=float, default=15.0,
                    help="FAIL: max twist of a leg/hoof bone about its own axis between consecutive frames")
    ap.add_argument("--twist-warn-deg", type=float, default=35.0, help="WARN: the same for any bone")
    ap.add_argument("--twist-fail-deg", type=float, default=90.0, help="FAIL: the same for any bone")
    ap.add_argument("--twist-local-deg", type=float, default=90.0,
                    help="FAIL: max twist of any bone relative to its parent (candy-wrap)")
    ap.add_argument("--boundary-ref", default="Idle", help="standing reference clip (its f0) for the one-shot boundary check")
    ap.add_argument("--boundary-warn-deg", type=float, default=10.0,
                    help="WARN when a one-shot clip's start/end joint rotations differ more than this from the reference")
    ap.add_argument("--skin-warn-mm", type=float, default=10.0,
                    help="skinned-vertex deviation from the source above this is a WARN")
    ap.add_argument("--skin-fail-mm", type=float, default=60.0,
                    help="skinned-vertex deviation from the source above this is a FAIL (broken weights / bones)")
    ap.add_argument("--no-skin-frames", action="store_true",
                    help="skip the every-frame skinned-vertex check (the slowest check, ~1-3 min)")
    ap.add_argument("--glb-vram-warn-mb", type=float, default=100.0,
                    help="WARN when the GLB's embedded images decode to more than this (RGBA8 + mips)")
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

    check_twist(a, S)
    F = check_fbx_raw(a, S, expect_tex)
    G = check_glb_raw(a, S, expect_tex)
    if not a.no_skin_frames:
        check_skin_frames(a, S, F, G)
    check_fbx_import(a, S, expect_tex)
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
