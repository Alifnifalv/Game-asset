"""Raven stage B: assemble the raven in Blender from stage A's arrays.

  python3 tools/raven/raven_stage_b.py [--in build/raven/stage_a.npz] [--out build/raven/stage_b.blend]

Creates
  RavenRig          armature (raven_anatomy.bone_table(); every bone deforms, none connected). Rolls: bones with an
                    `up` vector get their local Z along it (wing bones and feathers: the dorsal wing normal, so the fan
                    fold is a rotation about local Z; toes and eyes: world up); the others use dir x world X (local X ~
                    -X world for sagittal bones: flexion = rotation about local X, as the dog).
  Raven_LOD0/1/2    meshes parented to the rig (Armature modifier), vertex groups (<= 4 influences), UVMap, smooth
                    shading, face attribute `part` (raven_stage_a.PART), materials [0] M_Raven_Body,
                    [1] M_Raven_Feather, [2] M_Raven_Eye (placeholders; the texture stage replaces them).
Scene: 30 fps, meters.
"""
import argparse, os, sys
import numpy as np
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("ASSET", "raven")
import asset_profile as AP        # noqa: E402

NAME = "Raven"
MATS = (("M_Raven_Body", (0.04, 0.04, 0.045, 1)), ("M_Raven_Feather", (0.03, 0.03, 0.036, 1)),
        ("M_Raven_Eye", (0.07, 0.05, 0.04, 1)))


def roll_vector(head, tail, up):
    d = (tail - head).normalized()
    if up is not None and np.all(np.isfinite(up)):
        z = Vector(up)
        z = z - d * z.dot(d)
        if z.length > 1e-4:
            return z.normalized()
    z = d.cross(Vector((1, 0, 0)))
    if z.length < 1e-4:
        z = d.cross(Vector((0, 1, 0)))
    return z.normalized()


def build_armature(D):
    arm_d = bpy.data.armatures.new(NAME + "Rig")
    arm = bpy.data.objects.new(NAME + "Rig", arm_d)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    names = [str(b) for b in D["bones"]]
    for i, n in enumerate(names):
        eb = arm_d.edit_bones.new(n)
        eb.head = Vector(D["heads"][i]); eb.tail = Vector(D["tails"][i])
        eb.align_roll(roll_vector(eb.head, eb.tail, D["ups"][i]))
        eb.use_deform = True
    for i, n in enumerate(names):
        par = str(D["parents"][i])
        if par:
            eb = arm_d.edit_bones[n]
            eb.parent = arm_d.edit_bones[par]
            eb.use_connect = False          # never connected (tools/export_unity.py rig axis bake)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm_d.display_type = "STICK"
    return arm, names


def build_lod(D, lod, arm, names, mats):
    v, f, uv = D[f"v{lod}"], D[f"f{lod}"], D[f"uv{lod}"]
    me = bpy.data.meshes.new(f"{NAME}_LOD{lod}")
    me.from_pydata(v.tolist(), [], f.tolist())
    me.update()
    lay = me.uv_layers.new(name="UVMap")
    lay.data.foreach_set("uv", uv.reshape(-1).astype(np.float32))
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", D[f"mat{lod}"].astype(np.int32))
    me.polygons.foreach_set("use_smooth", np.ones(len(f), dtype=bool))
    at = me.attributes.new("part", "INT", "FACE")
    at.data.foreach_set("value", D[f"part{lod}"].astype(np.int32))
    ob = bpy.data.objects.new(f"{NAME}_LOD{lod}", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = arm
    mod = ob.modifiers.new("Armature", "ARMATURE"); mod.object = arm
    wi, ww = D[f"wi{lod}"], D[f"ww{lod}"]
    groups = [ob.vertex_groups.new(name=n) for n in names]
    # vertex groups in bulk: one add() per (bone, weight) bucket
    for b in range(len(names)):
        for k in range(4):
            sel = np.nonzero((wi[:, k] == b) & (ww[:, k] > 0))[0]
            if len(sel) == 0:
                continue
            w = ww[sel, k]
            for val in np.unique(np.round(w, 5)):
                idx = sel[np.round(w, 5) == val]
                groups[b].add(idx.tolist(), float(val), "REPLACE")
    return ob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(AP.BUILD, "stage_a.npz"))
    ap.add_argument("--out", default=os.path.join(AP.BUILD, "stage_b.blend"))
    a = ap.parse_args()
    D = dict(np.load(a.inp, allow_pickle=False))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 30; sc.render.fps_base = 1
    sc.unit_settings.system = "METRIC"; sc.unit_settings.scale_length = 1.0
    arm, names = build_armature(D)
    mats = []
    for mname, col in MATS:
        m = bpy.data.materials.new(mname); m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = col
        mats.append(m)
    bad = 0
    for lod in (0, 1, 2):
        ob = build_lod(D, lod, arm, names, mats)
        me = ob.data
        me.calc_tangents(uvmap="UVMap")
        t = np.empty(len(me.loops) * 3); me.loops.foreach_get("tangent", t)
        short = int((np.linalg.norm(t.reshape(-1, 3), axis=1) < 0.5).sum())
        bad += short
        print(f"[stage_b] {ob.name}: {len(me.vertices)} verts, {sum(len(p.vertices) - 2 for p in me.polygons)} tris, "
              f"degenerate tangents {short}")
    if bad:
        raise SystemExit(f"[stage_b] {bad} degenerate tangents (UV fold-overs): fix stage A")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("[stage_b] bones", len(names), "wrote", a.out)


if __name__ == "__main__":
    main()
