"""Side-by-side likeness check: each GiM reference (stills in `Rottweiler (male)/`, frames of its preview video) next to
our Rottweiler rendered in a matching pose and view.  Cycles CPU, textured.

  python3 tools/dog/dog_compare.py <stage_c|d.blend or .fbx/.glb> <out_dir> [--only name,name] [--res 420] [--samples 10]

Writes <out_dir>/<preset>.png (reference | ours) and <out_dir>/sheet.png (every pair).  The presets below give the
reference crop, the clip + frame to pose, and the camera direction (azimuth from the dog's nose toward its LEFT side,
elevation above the horizon, focal length); the camera distance is fitted so our dog fills the frame like the
reference (head-only presets frame the head).  Stills with a busy background use a hand-picked crop box; video frames
(plain studio background) are cropped automatically around the dark dog.
"""
import argparse, math, os, sys, tempfile
import numpy as np
import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF_DIR = os.path.join(ROOT, "Rottweiler (male)")
VIDEO = os.path.join(REF_DIR, "videoplayback (4).mp4")

# name: (source, crop box or None (auto), action, frame, azimuth deg, elevation deg, lens mm, framing 'body'|'head')
PRESETS = {
    "stand_32":   ("video:32.0", None, "Idle", 0, 58, 16, 55, "body"),
    "stand_55":   ("video:55.5", None, "Idle", 0, 62, 14, 55, "body"),
    "walk_12":    ("video:12.0", None, "Walk", 6, 55, 16, 55, "body"),
    "pant_21":    ("video:21.5", None, "Idle_Pant", 10, 38, 14, 55, "body"),
    "sniff_24":   ("video:24.5", None, "Idle_Sniff", 0, 60, 18, 55, "body"),
    "growl_36":   ("video:36.3", None, "Growl", 0, 64, 12, 55, "body"),
    "sit_45":     ("video:45.0", None, "Sit_Idle", 0, 42, 10, 55, "body"),
    "bark_57":    ("video:57.6", None, "Bark", 13, 62, 14, 55, "body"),
    "bow_58":     ("video:58.7", None, "PlayBow", 30, 40, 18, 55, "body"),
    "lying_head": ("a4763944-467c-40c2-bed7-808ac5753483.webp", (440, 80, 1120, 600), "Lying_Idle", 0, 48, 4, 85, "head"),
    "lying":      ("8c06f643-fafa-4b58-b295-c52af4079d24.webp", (220, 70, 1720, 1050), "Lying_Idle", 0, 46, 6, 60, "body"),
    "front_mouth": ("91ababf0-eed3-4e76-bd87-28df3bc015f9.webp", (1180, 180, 1700, 790), "Bark", 13, 32, 2, 50, "body"),
    "sit_photo":  ("843d64c3-4be3-4e28-b370-593ce0a2d1a4.webp", (870, 385, 1215, 850), "Sit_Idle", 0, 24, 8, 70, "body"),
    "jump_photo": ("53132155-92e9-4718-95e4-58cc850e98ae.webp", (300, 170, 1610, 930), "Jump", 22, -72, 4, 50, "body"),
}


def ref_image(src, box):
    from PIL import Image
    if src.startswith("video:"):
        import cv2
        t = float(src.split(":")[1])
        cap = cv2.VideoCapture(VIDEO)
        cap.set(1, int(round(t * 30)))
        ok, f = cap.read()
        if not ok:
            raise SystemExit(f"cannot read {VIDEO} at {t}s")
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(float)
        m = np.zeros_like(g, bool)
        m[120:1000, 250:1680] = g[120:1000, 250:1680] < 70          # the dark dog on the light studio background
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)).astype(bool)
        ys, xs = np.nonzero(m)
        x0, x1 = np.percentile(xs, [0.5, 99.5]); y0, y1 = np.percentile(ys, [0.5, 99.5])
        pad = 60
        box = (int(max(x0 - pad, 0)), int(max(y0 - pad, 0)), int(min(x1 + pad, 1919)), int(min(y1 + pad * 1.6, 1079)))
        return Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).crop(box)
    return Image.open(os.path.join(REF_DIR, src)).convert("RGB").crop(box)


def setup_scene(src):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(src)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=src)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=src)
    else:
        bpy.ops.wm.open_mainfile(filepath=src)
    sc = bpy.context.scene
    for o in list(sc.objects):
        if o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o)
    for o in sc.objects:
        if o.type == "MESH" and not o.name.endswith("_LOD0"):
            o.hide_render = True
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.60, 0.60, 0.72, 1)     # the GiM studio lavender
    bg.inputs[1].default_value = 0.9
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    g = bpy.data.materials.new("ground"); g.use_nodes = True
    g.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.55, 0.66, 1)
    g.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    bpy.context.object.data.materials.append(g)
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(40), math.radians(-10), math.radians(-35)))
    bpy.context.object.data.energy = 3.2
    bpy.context.object.data.angle = math.radians(12)
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"
    sc.cycles.use_denoising = True
    cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam


def pose(action, frame):
    sc = bpy.context.scene
    arm = next((o for o in sc.objects if o.type == "ARMATURE"), None)
    if arm is None:
        return None
    act = bpy.data.actions.get(action) or next((a for a in bpy.data.actions if a.name.endswith("|" + action)), None)
    if act is None:
        raise SystemExit(f"no action {action}")
    ad = arm.animation_data_create(); ad.action = act
    if act.slots:
        ad.action_slot = act.slots[0]
    sc.frame_set(frame)
    return arm


def posed_vertices():
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and o.name.endswith("_LOD0"):
            e = o.evaluated_get(dg); me = e.to_mesh()
            co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co)
            mw = np.array(e.matrix_world)
            out.append(co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
            e.to_mesh_clear()
    return np.concatenate(out)


def fit_camera(cam, pts, az, el, lens, aspect, fill=0.86):
    """camera on the (azimuth, elevation) ray through the points' centre, re-centred and moved in/out until the
    points' projected box fills `fill` of the frame on its tighter axis (Blender's own projection)"""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    cam.data.type = "PERSP"; cam.data.lens = lens; cam.data.sensor_fit = "AUTO"
    sub = pts[:: max(1, len(pts) // 2500)]
    c = (pts.min(0) + pts.max(0)) / 2
    a, e = math.radians(az), math.radians(el)
    d = np.array([math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)])   # nose = -Y, left = +X
    dist = 3.0
    for _ in range(10):
        cam.location = Vector(c + d * dist)
        cam.rotation_euler = Vector(-d).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        uv = np.array([world_to_camera_view(sc, cam, Vector(p))[:2] for p in sub])
        lo, hi = uv.min(0), uv.max(0)
        ext = max(hi[0] - lo[0], hi[1] - lo[1])
        # re-centre: shift the target along the camera's right / up axes by the box centre offset
        R = np.array(cam.matrix_world)[:3, :3]
        half_w = dist * 36.0 / (2 * lens) * (1 if aspect >= 1 else aspect)      # half frame width at the target
        half_h = half_w / aspect
        off = (lo + hi) / 2 - 0.5
        c = c + R[:, 0] * off[0] * 2 * half_w + R[:, 1] * off[1] * 2 * half_h
        dist *= ext / fill
    cam.location = Vector(c + d * dist)
    cam.rotation_euler = Vector(-d).to_track_quat("-Z", "Y").to_euler()


def head_points(arm, pts):
    h = arm.matrix_world @ arm.pose.bones["Head"].head
    n = arm.matrix_world @ arm.pose.bones["Nose"].tail
    mid = (h + n) / 2
    r = (n - h).length * 0.85
    sel = np.linalg.norm(pts - np.array(mid), axis=1) < r
    return pts[sel] if sel.sum() > 50 else pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out_dir")
    ap.add_argument("--only", default=None)
    ap.add_argument("--res", type=int, default=420)
    ap.add_argument("--samples", type=int, default=10)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    os.makedirs(a.out_dir, exist_ok=True)
    from PIL import Image, ImageDraw
    names = [n for n in PRESETS if not a.only or n in a.only.split(",")]
    sc, cam = setup_scene(os.path.abspath(a.src))
    sc.cycles.samples = a.samples
    pairs = []
    tmp = tempfile.mkdtemp()
    for name in names:
        src, box, action, frame, az, el, lens, framing = PRESETS[name]
        ref = ref_image(src, box)
        aspect = ref.width / ref.height
        H = a.res; W = int(round(H * aspect))
        sc.render.resolution_x, sc.render.resolution_y = W, H
        arm = pose(action, frame)
        pts = posed_vertices()
        if framing == "head" and arm is not None:
            pts = head_points(arm, pts)
        fit_camera(cam, pts, az, el, lens, aspect, fill=0.86 if framing == "body" else 0.9)
        p = os.path.join(tmp, name + ".png"); sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        ours = Image.open(p).convert("RGB")
        refs = ref.resize((W, H))
        pair = Image.new("RGB", (2 * W + 6, H), (255, 255, 255))
        pair.paste(refs, (0, 0)); pair.paste(ours, (W + 6, 0))
        d = ImageDraw.Draw(pair)
        d.text((6, 6), f"GiM {src.split('/')[-1][:18]}", fill=(255, 255, 0))
        d.text((W + 12, 6), f"ours {action} f{frame}", fill=(255, 255, 0))
        pair.save(os.path.join(a.out_dir, name + ".png"))
        pairs.append(pair)
        print("WROTE", name)
    # sheet
    Hs = 300
    rows, row, wsum = [], [], 0
    for im in pairs:
        im = im.resize((int(im.width * Hs / im.height), Hs))
        if wsum + im.width > 1900 and row:
            rows.append(row); row, wsum = [], 0
        row.append(im); wsum += im.width
    if row:
        rows.append(row)
    Wt = max(sum(i.width for i in r) for r in rows)
    sheet = Image.new("RGB", (Wt, Hs * len(rows)), (255, 255, 255))
    for ri, r in enumerate(rows):
        x = 0
        for im in r:
            sheet.paste(im, (x, ri * Hs)); x += im.width
    sheet.save(os.path.join(a.out_dir, "sheet.png"))
    print("WROTE sheet")


if __name__ == "__main__":
    main()
