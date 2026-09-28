"""Skin-weight utilities (numpy, no operators: vertex_group_smooth() fails its poll in headless bpy)."""
import numpy as np


def get_weights(ob):
    """dense (n_verts, n_groups) weight matrix"""
    n, G = len(ob.data.vertices), len(ob.vertex_groups)
    W = np.zeros((n, G), np.float64)
    for v in ob.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return W


def set_weights(ob, W, eps=1e-4):
    for vg in ob.vertex_groups:
        vg.remove(list(range(len(ob.data.vertices))))
    for gi, vg in enumerate(ob.vertex_groups):
        col = W[:, gi]
        idx = np.flatnonzero(col > eps)
        # add in batches of equal weight is not possible; per-vertex add is fine at this size
        for i in idx:
            vg.add([int(i)], float(col[i]), "REPLACE")


def smooth_groups(ob, names, factor=0.5, iterations=4, mask=None):
    """Laplacian smoothing of the given groups over mesh edges, then per-vertex renormalisation.
    Only vertices where `mask` (bool array) is True are changed (default: vertices touching any of the groups)."""
    me = ob.data
    W = get_weights(ob)
    gids = [ob.vertex_groups[n].index for n in names if n in ob.vertex_groups]
    e = np.array([ed.vertices[:] for ed in me.edges], np.int64)
    n = len(me.vertices)
    deg = np.bincount(e.ravel(), minlength=n).astype(np.float64)
    if mask is None:
        mask = W[:, gids].sum(1) > 1e-4
    for _ in range(iterations):
        S = W[:, gids]
        acc = np.zeros_like(S)
        np.add.at(acc, e[:, 0], S[e[:, 1]]); np.add.at(acc, e[:, 1], S[e[:, 0]])
        avg = acc / np.maximum(deg, 1)[:, None]
        S2 = S + factor * (avg - S)
        S[mask] = S2[mask]
        W[:, gids] = S
    # renormalise: the smoothed groups keep their share, the others fill the rest proportionally
    tot = W.sum(1, keepdims=True)
    W = W / np.maximum(tot, 1e-12)
    set_weights(ob, W)
    return W


def limit_total(ob, limit=4):
    """keep the `limit` largest influences per vertex, renormalise"""
    W = get_weights(ob)
    if W.shape[1] > limit:
        kth = np.argsort(-W, axis=1)[:, limit:]
        np.put_along_axis(W, kth, 0.0, axis=1)
    W = W / np.maximum(W.sum(1, keepdims=True), 1e-12)
    set_weights(ob, W)
    return W


def resplit_chain(ob, segments, names, blend=0.6, min_chain=1e-4):
    """Re-distribute the weight a bone chain carries (e.g. the tail, Tail1..Tail7) over its bones by position along
    the chain, so every link owns its own segment.  Needed when a source rig leaves a link without a vertex group
    (cow.glb has no Tail5 group: Tail5 then only moves its children, its own 8 cm segment is skinned to Tail4/Tail6).

    segments  [(head, tail)] of `names`, in order, in the mesh object's space (e.g. ob.matrix_world.inverted() @
              arm.matrix_world @ bone.head_local)
    blend     cross-fade width around each joint, as a fraction of the shorter adjacent segment (0.6: the two bones
              share the 30% of each segment next to their joint)
    Each vertex keeps its total chain weight (the sum over `names`) and its other groups; that total is re-split
    between the bone whose segment the vertex projects onto and, near a joint, the neighbour (linear cross-fade).
    Missing groups are created.  Returns the number of vertices changed."""
    me = ob.data
    for n in names:
        if n not in ob.vertex_groups:
            ob.vertex_groups.new(name=n)
    gid = [ob.vertex_groups[n].index for n in names]
    A = np.array([np.array(h, np.float64) for h, _ in segments])
    B = np.array([np.array(t, np.float64) for _, t in segments])
    L = np.linalg.norm(B - A, axis=1)
    k = len(names)
    changed = 0
    per_group = {g: ([], []) for g in gid}
    touched = []
    for v in me.vertices:
        chain = {g.group: g.weight for g in v.groups if g.group in gid and g.weight > 0}
        wt = sum(chain.values())
        if wt <= min_chain:
            continue
        p = np.array(v.co, np.float64)
        d = B - A
        t = np.clip(((p - A) * d).sum(1) / np.maximum((d * d).sum(1), 1e-12), 0.0, 1.0)
        dist = np.linalg.norm(A + d * t[:, None] - p, axis=1)
        j = int(dist.argmin())
        u = j + float(t[j])                     # chain parameter: bone j spans [j, j + 1]
        w = np.zeros(k)
        w[j] = 1.0
        for jj in (j, j + 1):                   # joint jj (u = jj) between bone jj - 1 and bone jj
            if 0 < jj < k:
                sd = (u - jj) * (L[jj - 1] if u < jj else L[jj])      # signed distance along the chain (m)
                half = 0.5 * blend * min(L[jj - 1], L[jj])
                if abs(sd) < half:
                    s = 0.5 + sd / (2.0 * half)                    # 0 -> all bone jj - 1, 1 -> all bone jj
                    w[:] = 0.0
                    w[jj - 1], w[jj] = 1.0 - s, s
        touched.append(v.index)
        for i, g in enumerate(gid):
            if w[i] > 0:
                per_group[g][0].append(v.index)
                per_group[g][1].append(float(w[i] * wt))
        changed += 1
    for g in gid:
        ob.vertex_groups[g].remove(touched)
    for g, (idx, ws) in per_group.items():
        vg = ob.vertex_groups[g]
        for i, wv in zip(idx, ws):
            vg.add([i], wv, "REPLACE")
    return changed
