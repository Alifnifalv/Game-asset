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
