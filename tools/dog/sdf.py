"""Signed distance primitives (numpy) for the procedural Rottweiler body.

Every primitive is a small object with
  .aabb()        -> (lo, hi) world bounds of the region where it can change the field (its surface + blend radius)
  .dist(P)       -> signed distance of the points P (N, 3) (approximate for ellipsoids: a bound, good near the surface)
and the build-time attributes
  .k             smooth-union (or smooth-subtraction) radius with the field accumulated so far (meters)
  .op            'add' (smooth union) or 'sub' (smooth subtraction)
  .bones         bone name, or a list of bone names (a chain: the weight is split along the chain, see anatomy.py)
  .tag           free label (region name, used by the texture and weight code)

Grid evaluation (Field.add) only touches the voxel block inside the primitive's AABB, so a 2 mm grid of the whole dog
(~60 M voxels) builds in about a minute.
"""
import numpy as np


def _v(x):
    return np.asarray(x, dtype=np.float64)


def smin(a, b, k):
    """Polynomial smooth minimum (iq). k = blend radius."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(k - np.abs(a - b), 0.0, None) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def frame_from(axis_y, up=(0, 0, 1)):
    """Orthonormal rotation matrix whose local +Y is axis_y and local +Z is as close to `up` as possible."""
    y = _v(axis_y); y = y / np.linalg.norm(y)
    u = _v(up)
    if abs(np.dot(u, y)) > 0.99:
        u = _v((1, 0, 0))
    x = np.cross(y, u); x /= np.linalg.norm(x)
    z = np.cross(x, y)
    return np.stack([x, y, z], axis=1)        # columns = local axes in world


class Prim:
    op = "add"
    k = 0.0
    bones = None
    tag = ""
    pad = 0.0

    def setup(self, k=0.0, op="add", bones=None, tag=""):
        self.k, self.op, self.bones, self.tag = k, op, bones, tag
        return self


class Sphere(Prim):
    def __init__(self, c, r, **kw):
        self.c, self.r = _v(c), float(r); self.setup(**kw)

    def aabb(self):
        e = self.r + self.k
        return self.c - e, self.c + e

    def dist(self, P):
        return np.linalg.norm(P - self.c, axis=-1) - self.r


class Ellipsoid(Prim):
    """Ellipsoid with semi-axes r (local x, y, z) and rotation R (columns = local axes in world)."""
    def __init__(self, c, r, R=None, **kw):
        self.c, self.r = _v(c), _v(r)
        self.R = np.eye(3) if R is None else _v(R)
        self.setup(**kw)

    def aabb(self):
        ext = np.abs(self.R) @ self.r + self.k
        return self.c - ext, self.c + ext

    def dist(self, P):
        q = (P - self.c) @ self.R                  # to local
        k0 = np.linalg.norm(q / self.r, axis=-1)
        k1 = np.linalg.norm(q / (self.r * self.r), axis=-1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)


def ellipsoid_seg(a, b, rx, rz, up=(0, 0, 1), extra=0.0, **kw):
    """Ellipsoid spanning the segment a-b (its y semi-axis = half the length + extra), cross-section rx by rz."""
    a, b = _v(a), _v(b)
    R = frame_from(b - a, up)
    return Ellipsoid((a + b) / 2, (rx, np.linalg.norm(b - a) / 2 + extra, rz), R, **kw)


class RoundCone(Prim):
    """Two spheres (a, ra) and (b, rb) joined by their tangent cone (iq's exact round cone)."""
    def __init__(self, a, b, ra, rb, **kw):
        self.a, self.b, self.ra, self.rb = _v(a), _v(b), float(ra), float(rb)
        self.setup(**kw)

    def aabb(self):
        e = max(self.ra, self.rb) + self.k
        return np.minimum(self.a, self.b) - e, np.maximum(self.a, self.b) + e

    def dist(self, P):
        a, b, r1, r2 = self.a, self.b, self.ra, self.rb
        ba = b - a
        l2 = float(ba @ ba); rr = r1 - r2; a2 = l2 - rr * rr; il2 = 1.0 / l2
        pa = P - a
        y = pa @ ba
        z = y - l2
        xv = pa * l2 - y[:, None] * ba
        x2 = np.einsum("ij,ij->i", xv, xv)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        d = np.empty(len(P))
        m1 = np.sign(z) * a2 * z2 > k
        m2 = (~m1) & (np.sign(y) * a2 * y2 < k)
        m3 = ~(m1 | m2)
        d[m1] = np.sqrt(x2[m1] + z2[m1]) * il2 - r2
        d[m2] = np.sqrt(x2[m2] + y2[m2]) * il2 - r1
        d[m3] = (np.sqrt(x2[m3] * a2 * il2) + y[m3] * rr) * il2 - r1
        return d


class RoundBox(Prim):
    """Box with half extents h (local), corner radius rad, rotation R."""
    def __init__(self, c, h, rad, R=None, **kw):
        self.c, self.h, self.rad = _v(c), _v(h), float(rad)
        self.R = np.eye(3) if R is None else _v(R)
        self.setup(**kw)

    def aabb(self):
        ext = np.abs(self.R) @ (self.h + self.rad) + self.k
        return self.c - ext, self.c + ext

    def dist(self, P):
        q = np.abs((P - self.c) @ self.R) - self.h
        return np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(q.max(axis=-1), 0) - self.rad


class Field:
    """A regular grid holding the running SDF value."""
    def __init__(self, lo, hi, h):
        self.lo = _v(lo); self.h = float(h)
        self.shape = tuple(int(np.ceil((hi[i] - lo[i]) / h)) + 1 for i in range(3))
        self.d = np.full(self.shape, 1.0, dtype=np.float32)

    def _block(self, lo, hi):
        i0 = np.clip(np.floor((lo - self.lo) / self.h).astype(int), 0, np.array(self.shape) - 1)
        i1 = np.clip(np.ceil((hi - self.lo) / self.h).astype(int) + 1, 0, np.array(self.shape))
        return i0, i1

    def add(self, prim):
        lo, hi = prim.aabb()
        if prim.op == "sub":            # a subtraction can only change voxels inside its own region
            lo, hi = lo - prim.k, hi + prim.k
        i0, i1 = self._block(lo, hi)
        if np.any(i1 <= i0):
            return
        xs = [self.lo[a] + self.h * np.arange(i0[a], i1[a]) for a in range(3)]
        X, Y, Z = np.meshgrid(*xs, indexing="ij")
        P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
        dp = prim.dist(P).reshape(X.shape)
        sl = tuple(slice(i0[a], i1[a]) for a in range(3))
        cur = self.d[sl].astype(np.float64)
        if prim.op == "add":
            self.d[sl] = smin(cur, dp, prim.k)
        elif prim.op == "sub":
            self.d[sl] = smax(cur, -dp, prim.k)
        elif prim.op == "inter":
            self.d[sl] = smax(cur, dp, prim.k)

    def mesh(self, level=0.0):
        """Marching cubes -> (verts world, faces) with outward winding."""
        from skimage.measure import marching_cubes
        d = self.d.copy()
        d[0, :, :] = d[-1, :, :] = d[:, 0, :] = d[:, -1, :] = d[:, :, 0] = d[:, :, -1] = 1.0   # watertight
        v, f, _n, _ = marching_cubes(d, level=level, spacing=(self.h,) * 3)
        v = v + self.lo
        return v, f          # outward winding for "inside = negative" (checked: positive volume)


def eval_prims(prims, P):
    """Composite field at arbitrary points (same composition order as Field)."""
    d = np.full(len(P), 1.0)
    for p in prims:
        dp = p.dist(P)
        if p.op == "add":
            d = smin(d, dp, p.k)
        elif p.op == "sub":
            d = smax(d, -dp, p.k)
        else:
            d = smax(d, dp, p.k)
    return d
