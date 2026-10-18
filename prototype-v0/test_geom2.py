"""Headless test of pms-layout-geom2-v0.py -- the "atomic cells"
prototype (Cells/Labels only -- Borders/Topology are out for now, see
the module docstring). Validates the s1/k/s2 worked example: every
grid cell its own rectangle, grouped into a branch per space (not
merged into one traced shape), with Union=True collapsing each branch
to one outline."""
import importlib.util
import os
import sys


class FakePath:
    def __init__(self, *idx):
        self.idx = tuple(idx)

    def AppendElement(self, i):
        return FakePath(*(self.idx + (i,)))

    @property
    def Length(self):
        return len(self.idx)

    def __repr__(self):
        return "{" + ";".join(str(i) for i in self.idx) + "}"

    def __eq__(self, other):
        return isinstance(other, FakePath) and self.idx == other.idx

    def __hash__(self):
        return hash(self.idx)


class _Countable(list):
    @property
    def Count(self):
        return len(self)


class FakeTree:
    def __init__(self):
        self.branches = {}

    def Add(self, item, path):
        self.branches.setdefault(path, []).append(item)

    def EnsurePath(self, path):
        self.branches.setdefault(path, [])

    def Branch(self, path):
        return self.branches.get(path)

    @property
    def Paths(self):
        return _Countable(self.branches.keys())

    @property
    def Branches(self):
        return _Countable(self.branches.values())


class FakePlane:
    XAxis = (1, 0, 0)
    YAxis = (0, 1, 0)

    def __init__(self, origin=(0.0, 0.0, 0.0), xaxis=None, yaxis=None):
        self.ox, self.oy = origin[0], origin[1]
        self.origin = origin
        self.xaxis = xaxis
        self.yaxis = yaxis

    def PointAt(self, x, y, z):
        return (self.ox + x, self.oy + y, z)


class FakePoint3d(tuple):
    def __new__(cls, x, y, z):
        return super(FakePoint3d, cls).__new__(cls, (x, y, z))

    X = property(lambda self: self[0])
    Y = property(lambda self: self[1])
    Z = property(lambda self: self[2])


class FakeVector3d(FakePoint3d):
    pass


spec = importlib.util.spec_from_file_location(
    "geom2",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms-layout-geom2-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["geom2"] = mod
spec.loader.exec_module(mod)


def _fake_boolean_union(curves, tolerance):
    """Stand-in for Rhino's own Curve.CreateBooleanUnion, headlessly --
    NOT a claim that it replicates Rhino's real polygon-clipping engine
    exactly, just good enough to prove the INPUT (which cells, with
    which deltas) is right and that simple rectilinear cases (still
    touching, grown into an overlap, pulled apart into a real gap) all
    come out correctly. Rasterizes each input rectangle onto the grid
    formed by every input's own edge coordinates, flood-fills connected
    covered cells into components (this is what makes a genuine gap
    correctly come back as separate curves, and an overlap correctly
    merge), traces each component's own outline the same way the
    original hand-rolled _region_outline (removed from the real
    component -- this logic only lives here, as a test fake) used to."""
    rects = []
    for crv in curves:
        xs_ = [p[0] for p in crv[1]]
        ys_ = [p[1] for p in crv[1]]
        rects.append((min(xs_), min(ys_), max(xs_), max(ys_)))
    xs = sorted(set(v for r in rects for v in (r[0], r[2])))
    ys = sorted(set(v for r in rects for v in (r[1], r[3])))

    covered = set()
    for (x0, y0, x1, y1) in rects:
        xi0, xi1 = xs.index(x0), xs.index(x1)
        yi0, yi1 = ys.index(y0), ys.index(y1)
        for xi in range(xi0, xi1):
            for yi in range(yi0, yi1):
                covered.add((xi, yi))

    seen = set()
    components = []
    for cell in covered:
        if cell in seen:
            continue
        comp = set()
        stack = [cell]
        seen.add(cell)
        while stack:
            cx, cy = stack.pop()
            comp.add((cx, cy))
            for nb in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if nb in covered and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        components.append(comp)

    out = []
    for comp in components:
        start_map = {}
        for (xi, yi) in comp:
            x0, x1 = xs[xi], xs[xi + 1]
            y0, y1 = ys[yi], ys[yi + 1]
            if (xi, yi - 1) not in comp:
                start_map[(x0, y0)] = (x1, y0)
            if (xi + 1, yi) not in comp:
                start_map[(x1, y0)] = (x1, y1)
            if (xi, yi + 1) not in comp:
                start_map[(x1, y1)] = (x0, y1)
            if (xi - 1, yi) not in comp:
                start_map[(x0, y1)] = (x0, y0)
        loops = []
        visited = set()
        cap = len(start_map) + 1
        for start in start_map:
            if start in visited:
                continue
            loop = [start]
            visited.add(start)
            cur = start_map[start]
            for _ in range(cap):
                if cur == start:
                    break
                if cur in visited or cur not in start_map:
                    break
                loop.append(cur)
                visited.add(cur)
                cur = start_map[cur]
            loops.append(loop)
        loops.sort(key=len, reverse=True)
        points = loops[0]
        world = [(px, py, 0.0) for (px, py) in points] + [(points[0][0], points[0][1], 0.0)]
        out.append(("CURVE", tuple(world)))
    return out


class FakeRG:
    Plane = FakePlane

    @staticmethod
    def PolylineCurve(pts):
        return ("CURVE", tuple(pts))

    @staticmethod
    def Line(p0, p1):
        return ("LINE", p0, p1)

    class Curve:
        CreateBooleanUnion = staticmethod(_fake_boolean_union)

    Point3d = FakePoint3d
    Vector3d = FakeVector3d


mod.rg = FakeRG
mod._HAS_RHINO = True


class _DataTreeFactory:
    def __getitem__(self, _t):
        return FakeTree


class FakeGH:
    DataTree = _DataTreeFactory()


mod.gh = FakeGH()


def leaf(cw, cl, labels, label=None):
    d = {"cellWidths": cw, "cellLengths": cl, "cellLabels": labels}
    if label:
        d["label"] = label
    return d


def x_range(curve):
    xs = [p[0] for p in curve[1]]
    return min(xs), max(xs)


def y_range(curve):
    ys = [p[1] for p in curve[1]]
    return min(ys), max(ys)


def run_emit(node, union=False):
    c, l = FakeTree(), FakeTree()
    w = []
    mod._emit(node, None, None, FakePlane(), FakePath(0), c, l, w, {}, union)
    return c, l, w


# --- 1) s1/k/s2, Union=False (default): each space gets its OWN
#     branch, holding one rectangle PER GRID CELL -- s1 (3 cells) ->
#     3 items in branch {0;0}, k (2 cells, already rectangular) -> 2
#     items in {0;1}, s2 (3 cells) -> 3 items in {0;2}. No non-
#     rectangular tracing anywhere -- every single item is a plain
#     grid-cell rectangle.
grid_sk = leaf([1000.0, 1000.0], [1000.0, 1000.0, 1000.0, 1000.0],
               [["s1", "s1"], ["k", "s1"], ["k", "s2"], ["s2", "s2"]])
c1, l1, w1 = run_emit(grid_sk, union=False)
assert w1 == [], w1
assert len(c1.branches[FakePath(0, 0)]) == 3, c1.branches[FakePath(0, 0)]
assert l1.branches[FakePath(0, 0)] == ["s1", "s1", "s1"], l1.branches[FakePath(0, 0)]
assert len(c1.branches[FakePath(0, 1)]) == 2, c1.branches[FakePath(0, 1)]
assert l1.branches[FakePath(0, 1)] == ["k", "k"], l1.branches[FakePath(0, 1)]
assert len(c1.branches[FakePath(0, 2)]) == 3, c1.branches[FakePath(0, 2)]
assert l1.branches[FakePath(0, 2)] == ["s2", "s2", "s2"], l1.branches[FakePath(0, 2)]
s1_cell_ranges = sorted((x_range(c), y_range(c)) for c in c1.branches[FakePath(0, 0)])
assert s1_cell_ranges == [
    ((0.0, 1000.0), (3000.0, 4000.0)),
    ((1000.0, 2000.0), (2000.0, 3000.0)),
    ((1000.0, 2000.0), (3000.0, 4000.0)),
], s1_cell_ranges
print("OK -- Union=False: s1/k/s2 each land in their own branch, "
      "holding one plain rectangle per grid cell (3/2/3) -- no traced "
      "non-rectangular shape anywhere, every item trivially rectangular\n")

# --- 2) s1/k/s2, Union=True: each branch collapses to ONE traced
#     outline -- k (already rectangular, 2 cells) still becomes 1
#     item; s1/s2 (genuinely L-shaped) also become exactly 1 item
#     each, via a REAL geometric Boolean union (Curve.CreateBooleanUnion
#     in the real component, _fake_boolean_union here) rather than a
#     hand-rolled edge trace.
c2, l2, w2 = run_emit(grid_sk, union=True)
assert w2 == [], w2
assert len(c2.branches[FakePath(0, 0)]) == 1, c2.branches[FakePath(0, 0)]
assert len(c2.branches[FakePath(0, 1)]) == 1, c2.branches[FakePath(0, 1)]
assert len(c2.branches[FakePath(0, 2)]) == 1, c2.branches[FakePath(0, 2)]
s1_union_pts = set((p[0], p[1]) for p in c2.branches[FakePath(0, 0)][0][1])
assert s1_union_pts == {
    (0.0, 3000.0), (0.0, 4000.0), (1000.0, 2000.0), (1000.0, 3000.0),
    (2000.0, 2000.0), (2000.0, 3000.0), (2000.0, 4000.0), (1000.0, 4000.0),
}, s1_union_pts
k_union_range = (x_range(c2.branches[FakePath(0, 1)][0]),
                  y_range(c2.branches[FakePath(0, 1)][0]))
assert k_union_range == ((0.0, 1000.0), (1000.0, 3000.0)), k_union_range
print("OK -- Union=True: each branch collapses to exactly ONE traced "
      "outline -- s1's own L-shape comes back correctly, k's 2 cells "
      "union into one plain rectangle\n")

# --- 3) NESTED child hosting, 2 levels deep -- confirms recursion
#     costs exactly ONE path segment per level (matching the original
#     Geom's own flat-list recursion cost), not two. A prior version
#     inserted an extra constant-0 "child container" segment before
#     each child's own per-space branching, which DOUBLED the cost per
#     level -- a0 at depth2, b0 at depth4, c0 at depth6 -- diverging
#     further from the original Geom's own Depth numbers the deeper a
#     hierarchy nested, instead of a flat, constant +1 offset.
level2 = leaf(["1fr"], ["1fr"], [["c0"]], label="b0")
level1 = leaf(["1fr"], ["1fr"], [["b0"]], label="a0")
level1["childLayouts"] = [level2]
level0 = leaf([1000.0], [1000.0], [["a0"]])
level0["childLayouts"] = [level1]
c3, l3, w3 = run_emit(level0, union=False)
assert w3 == [], w3
assert l3.branches.get(FakePath(0, 0)) == ["a0"], l3.branches.get(FakePath(0, 0))
assert l3.branches.get(FakePath(0, 0, 0)) == ["b0"], l3.branches.get(FakePath(0, 0, 0))
assert l3.branches.get(FakePath(0, 0, 0, 0)) == ["c0"], l3.branches.get(FakePath(0, 0, 0, 0))
print("OK -- nested child hosting costs exactly one path segment per "
      "level: a0 at {0;0}, its child's own b0 at {0;0;0}, b0's "
      "child's own c0 at {0;0;0;0} -- a flat, constant offset from "
      "the original Geom's own Depth numbers at every level, not a "
      "compounding one\n")

# --- 4) Union SKIPS a '[k]'-suffixed label, even with several cells --
#     only a BARE label's own multi-cell group collapses. 2x4 grid:
#     'mod[0]' (indexed) spans (0,0),(0,1),(1,1) -- an L-shape, exactly
#     like s1 -- 'g' (bare) spans a plain 2x2 block, 'x' is a single
#     cell. Union=True should leave mod[0] as 3 raw rectangles but
#     collapse g to 1.
grid_idx = leaf([1000.0, 1000.0, 1000.0, 1000.0], [1000.0, 1000.0],
                [["mod[0]", "mod[0]", "g", "g"], ["x", "mod[0]", "g", "g"]])
c4, l4, w4 = run_emit(grid_idx, union=True)
assert w4 == [], w4
mod0_branch = [p for p in c4.Paths if l4.branches[p] and l4.branches[p][0] == "mod[0]"][0]
g_branch = [p for p in c4.Paths if l4.branches[p] and l4.branches[p][0] == "g"][0]
assert len(c4.branches[mod0_branch]) == 3, c4.branches[mod0_branch]
assert len(c4.branches[g_branch]) == 1, c4.branches[g_branch]
assert (x_range(c4.branches[g_branch][0]), y_range(c4.branches[g_branch][0])) == (
    (2000.0, 4000.0), (0.0, 2000.0)), c4.branches[g_branch]
print("OK -- Union=True leaves 'mod[0]' (a '[k]'-suffixed, L-shaped "
      "space) as 3 separate raw rectangles, while still collapsing "
      "the bare 'g' block to 1 traced rectangle -- the suffix itself "
      "means 'keep separate on purpose', Union never overrides it\n")

# --- 5) Depth now matches the ORIGINAL Geom exactly -- Depth 0 is the
#     root's own overall boundary, Depth 1 is its top-level spaces, no
#     offset at either level. Mirrors what run() itself does: the
#     root's own boundary curve sits AT root_path ({0}), top-level
#     spaces are emitted with root_path passed straight through (not
#     root_path.AppendElement(0)) so they land at root_path.AppendElement(j)
#     ({0;j}) -- Depth 1, matching the original -- not {0;0;j} (Depth 2).
root_path = FakePath(0)
c5, l5, w5 = run_emit(grid_sk)   # same s1/k/s2 grid as test 1
c5.Add(("CURVE", ((0.0, 0.0, 0.0), (2000.0, 0.0, 0.0), (2000.0, 4000.0, 0.0),
                   (0.0, 4000.0, 0.0), (0.0, 0.0, 0.0))), root_path)
depth0 = [p for p in c5.Paths if p.Length == 1]
depth1 = [p for p in c5.Paths if p.Length == 2]
assert depth0 == [FakePath(0)], depth0
assert sorted(p.idx for p in depth1) == [(0, 0), (0, 1), (0, 2)], depth1
print("OK -- Depth 0 is the root's own overall boundary ({0}), Depth "
      "1 is its top-level spaces ({0;0}/{0;1}/{0;2} for s1/k/s2) -- "
      "matching the original Geom's own Depth numbers exactly, no "
      "offset (an earlier version inserted a redundant constant-0 "
      "segment at the root too, pushing top-level spaces to Depth 2 "
      "instead)\n")


def cell_range(cells_tree, labels_tree, branch, label, x0, x1, y0, y1):
    for crv, lbl in zip(cells_tree.branches[branch], labels_tree.branches[branch]):
        if lbl == label and x_range(crv) == (x0, x1) and y_range(crv) == (y0, y1):
            return True
    return False


# --- 6) BORDER OVERRIDES are back. EXT ring (['*','EXT','L'], offset
#     100) on s1/k/s2: EVERY cell in column 0 (the grid's true west
#     edge) shifts west, regardless of label -- (0,0)[s1], (1,0)[k],
#     (2,0)[k], (3,0)[s2]. No bounding box anywhere -- each cell's own
#     west neighbour is checked directly (off-grid, since c=0), so
#     there's no way for this to reach into k's territory the way the
#     original bug did.
grid_sk2 = leaf([1000.0, 1000.0], [1000.0, 1000.0, 1000.0, 1000.0],
                [["s1", "s1"], ["k", "s1"], ["k", "s2"], ["s2", "s2"]])
grid_sk2["borderOverrides"] = [{"between": ["*", "EXT", "L"], "offset": 100.0}]
c6, l6, w6 = run_emit(grid_sk2, union=False)
assert w6 == [], w6
s1_branch = FakePath(0, 0)
k_branch = FakePath(0, 1)
s2_branch = FakePath(0, 2)
assert cell_range(c6, l6, s1_branch, "s1", -100.0, 1000.0, 3000.0, 4000.0)
assert cell_range(c6, l6, s1_branch, "s1", 1000.0, 2000.0, 3000.0, 4000.0)
assert cell_range(c6, l6, s1_branch, "s1", 1000.0, 2000.0, 2000.0, 3000.0)
assert cell_range(c6, l6, k_branch, "k", -100.0, 1000.0, 2000.0, 3000.0)
assert cell_range(c6, l6, k_branch, "k", -100.0, 1000.0, 1000.0, 2000.0)
assert cell_range(c6, l6, s2_branch, "s2", 1000.0, 2000.0, 1000.0, 2000.0)
assert cell_range(c6, l6, s2_branch, "s2", -100.0, 1000.0, 0.0, 1000.0)
assert cell_range(c6, l6, s2_branch, "s2", 1000.0, 2000.0, 0.0, 1000.0)
print("OK -- EXT ring on s1/k/s2 shifts every column-0 cell west by "
      "100, regardless of label -- s1's (0,0), k's own 2 cells, and "
      "s2's (3,0) -- while every column-1 cell (s1's other 2 cells, "
      "s2's other 2 cells) stays exactly where it was\n")

# --- 7) Plain ring on s1 ALONE (['s1','*','L']): only cells actually
#     LABELLED s1 are candidates, and even then only where the west
#     side is a REAL boundary. (0,0)'s west neighbour is off-grid --
#     shifts. (1,1)'s west neighbour is k -- a DIFFERENT label -- also
#     shifts, independently, k never touched. (0,1)'s west neighbour
#     is (0,0) -- the SAME label, an internal seam within s1's own
#     merged shape -- correctly left alone (shifting it would tear s1
#     apart internally). This is the exact m[0]/m[1] case from the
#     design discussion, just inside a non-rectangular merge instead
#     of two separate labels.
grid_sk3 = leaf([1000.0, 1000.0], [1000.0, 1000.0, 1000.0, 1000.0],
                [["s1", "s1"], ["k", "s1"], ["k", "s2"], ["s2", "s2"]])
grid_sk3["borderOverrides"] = [{"between": ["s1", "*", "L"], "offset": 100.0}]
c7, l7, w7 = run_emit(grid_sk3, union=False)
assert w7 == [], w7
s1_branch7 = FakePath(0, 0)
k_branch7 = FakePath(0, 1)
assert cell_range(c7, l7, s1_branch7, "s1", -100.0, 1000.0, 3000.0, 4000.0)  # (0,0)
assert cell_range(c7, l7, s1_branch7, "s1", 1000.0, 2000.0, 3000.0, 4000.0)  # (0,1) untouched
assert cell_range(c7, l7, s1_branch7, "s1", 900.0, 2000.0, 2000.0, 3000.0)   # (1,1) shifted
assert cell_range(c7, l7, k_branch7, "k", 0.0, 1000.0, 2000.0, 3000.0)       # k untouched
assert cell_range(c7, l7, k_branch7, "k", 0.0, 1000.0, 1000.0, 2000.0)
print("OK -- a plain ring on s1 alone shifts (0,0) [true west edge] "
      "and (1,1) [west neighbour is k, a different label] "
      "independently, but leaves (0,1) alone [west neighbour is (0,0), "
      "the SAME label -- an internal seam, not a real boundary] -- k "
      "itself is never touched, matching ring's own 'independent, "
      "sibling never moves' rule\n")

# --- 8) SHARED pair -- two plain (no child) atomic labels sharing a
#     track resize the ONE track between them, exactly like the
#     original: m[0] grows, m[1] shrinks by the same amount, total
#     unchanged. Atomic cells are ALWAYS exactly one track wide, so
#     there's no "span too wide to resize" ambiguity to warn about.
grid_mm = leaf([1000.0, 1000.0], [2000.0], [["m[0]", "m[1]"]])
grid_mm["borderOverrides"] = [{"between": ["m[0]", "m[1]"], "offset": 100.0}]
c8, l8, w8 = run_emit(grid_mm, union=False)
assert w8 == [], w8
assert cell_range(c8, l8, FakePath(0, 0), "m[0]", 0.0, 1100.0, 0.0, 2000.0)
assert cell_range(c8, l8, FakePath(0, 1), "m[1]", 1100.0, 2000.0, 0.0, 2000.0)
print("OK -- SHARED pair: m[0]'s own track grows to 1100, m[1]'s "
      "shrinks to 900 (starting at x=1100), total span unchanged -- "
      "resolved directly against col_sizes/col_starts, before any "
      "per-cell independent delta is ever computed\n")

# --- 9) INDEPENDENT pair -- both sides host a child: each grows
#     toward the other by the FULL offset (not split), track sizes
#     untouched. Mirrors the original's own sliding-door-panel case.
roomA = leaf(["1fr"], ["1fr"], [["ra"]], label="m[0]")
roomB = leaf(["1fr"], ["1fr"], [["rb"]], label="m[1]")
grid_ind = leaf([1000.0, 1000.0], [2000.0], [["m[0]", "m[1]"]])
grid_ind["childLayouts"] = [roomA, roomB]
grid_ind["borderOverrides"] = [{"between": ["m[0]", "m[1]"], "offset": 50.0}]
c9, l9, w9 = run_emit(grid_ind, union=False)
assert w9 == [], w9
assert cell_range(c9, l9, FakePath(0, 0), "m[0]", 0.0, 1050.0, 0.0, 2000.0)
assert cell_range(c9, l9, FakePath(0, 1), "m[1]", 950.0, 2000.0, 0.0, 2000.0)
print("OK -- INDEPENDENT pair (both host a child): m[0] grows east to "
      "1050, m[1] grows west to 950 -- each by the FULL 50mm offset, "
      "not split -- track sizes (1000/1000) stay untouched, this was "
      "never a SHARED resize\n")

# --- 10) The bug that motivated switching to a REAL Boolean union:
#     with the old hand-rolled tracer, ANY offset touching ANY cell in
#     a group made it bail with a "Union is skipped for this instance"
#     warning -- even here, where the EXT ring only ever moves each
#     cell's own TRUE external edge and every group's internal seams
#     stay exactly coincident, so every one of s1/k/s2 is still
#     perfectly unionizable. Same grid + override as test 6, but with
#     Union=True this time: every branch must still collapse to
#     exactly 1 shape, with NO warning at all.
c10, l10, w10 = run_emit(grid_sk2, union=True)
assert w10 == [], w10
assert len(c10.branches[FakePath(0, 0)]) == 1, c10.branches[FakePath(0, 0)]
assert len(c10.branches[FakePath(0, 1)]) == 1, c10.branches[FakePath(0, 1)]
assert len(c10.branches[FakePath(0, 2)]) == 1, c10.branches[FakePath(0, 2)]
k_union_range10 = (x_range(c10.branches[FakePath(0, 1)][0]),
                    y_range(c10.branches[FakePath(0, 1)][0]))
assert k_union_range10 == ((-100.0, 1000.0), (1000.0, 3000.0)), k_union_range10
print("OK -- after an EXT-ring offset that only ever moves TRUE "
      "external edges, s1/k/s2 all still union into exactly ONE shape "
      "each with zero warnings -- the old tracer's own "
      "'any offset in the group -> bail' overreach is gone, because a "
      "real Boolean union doesn't need coincident edges to begin with\n")

# --- 11) A genuine gap. NOTE: a bare label's own group is formed by
#     flood-fill over CONTIGUOUS same-label cells (_merge_spaces, one
#     space/branch per connected region -- unchanged from the original
#     Geom), and a same-label neighbour's shared edge is structurally
#     guaranteed to never move independently (test 7) -- so a real
#     component run can never actually pull one already-grouped space
#     apart into a disjoint result. That still leaves the union CALL
#     itself needing to handle "more than one curve came back" (e.g. a
#     real BRep kernel occasionally splitting an exactly-touching pair
#     on floating-point tolerance) -- exercised directly against the
#     fake here, at the helper level, rather than through run_emit.
disjoint = mod.rg.Curve.CreateBooleanUnion([
    ("CURVE", ((0.0, 0.0, 0.0), (1000.0, 0.0, 0.0), (1000.0, 1000.0, 0.0), (0.0, 1000.0, 0.0))),
    ("CURVE", ((2000.0, 0.0, 0.0), (3000.0, 0.0, 0.0), (3000.0, 1000.0, 0.0), (2000.0, 1000.0, 0.0))),
], 0.01)
assert len(disjoint) == 2, disjoint
disjoint_ranges = sorted(x_range(c) for c in disjoint)
assert disjoint_ranges == [(0.0, 1000.0), (2000.0, 3000.0)], disjoint_ranges
overlap = mod.rg.Curve.CreateBooleanUnion([
    ("CURVE", ((0.0, 0.0, 0.0), (1000.0, 0.0, 0.0), (1000.0, 1000.0, 0.0), (0.0, 1000.0, 0.0))),
    ("CURVE", ((500.0, 0.0, 0.0), (1500.0, 0.0, 0.0), (1500.0, 1000.0, 0.0), (500.0, 1000.0, 0.0))),
], 0.01)
assert len(overlap) == 1, overlap
assert x_range(overlap[0]) == (0.0, 1500.0), overlap
print("OK -- the union call itself still does the right thing for two "
      "genuinely separate rectangles (2 curves back, unchanged extents) "
      "and for two overlapping ones (1 merged curve) -- the case this "
      "guards is unreachable through a real component run today (see "
      "note above), but the call must still behave honestly if it ever "
      "comes up\n")

# --- 12) WALL CELLS are back. A 2-row touch between m[0] and m[1]
#     (each spanning both rows) must merge into ONE wall run spanning
#     the FULL 2000mm height, not two separate 1000mm walls -- the
#     genuinely new bit this needed, since Geom2 has no Borders/
#     Topology pass to lean on any more (see the module docstring's
#     WALL LAYOUTS section): candidates are found by direct cell
#     adjacency, then grouped into runs by hand.
wall_doc = {"cellWidths": ["auto"], "cellLengths": [1500.0, 500.0],
            "cellLabels": [["door"], ["header"]]}
grid_wall = leaf([1000.0, 1000.0], [1000.0, 1000.0],
                  [["m[0]", "m[1]"], ["m[0]", "m[1]"]])
grid_wall["borderOverrides"] = [
    {"between": ["m[0]", "m[1]"], "wallLayout": wall_doc}]
c12, l12, w12 = run_emit(grid_wall, union=False)
assert w12 == [], w12
# Nested DIRECTLY under m[0]'s own space (host label = Between[0]) --
# same depth an ordinary hosted child's own top-level spaces would
# use, no separate wrapper segment for "the wall itself": m[0]'s own
# space_path ({0;0}), then the wall's own door/header content directly
# at {0;0;0}/{0;0;1} (index 0/1, continuing m[0]'s own index sequence
# -- empty here since m[0] hosts no ordinary child of its own).
assert l12.branches.get(FakePath(0, 0, 0)) == ["door"], l12.branches.get(FakePath(0, 0, 0))
assert l12.branches.get(FakePath(0, 0, 1)) == ["header"], l12.branches.get(FakePath(0, 0, 1))
depth3 = [p for p in c12.Paths if p.Length == 3]
assert len(depth3) == 2, depth3  # door + header, from ONE wall -- not 4, from two
door_extent = x_range(c12.branches[FakePath(0, 0, 0)][0])
header_extent = x_range(c12.branches[FakePath(0, 0, 1)][0])
assert door_extent[1] - door_extent[0] == 2000.0, door_extent
assert header_extent[1] - header_extent[0] == 2000.0, header_extent
print("OK -- a 2-row touch between m[0] and m[1] merges into ONE wall "
      "run of the FULL 2000mm length (door + header, each spanning the "
      "whole run), not two separate 1000mm walls -- found by direct "
      "cell-adjacency scanning + run-grouping, no Borders tree "
      "involved at all -- and lands at the SAME depth an ordinary "
      "hosted child would, directly under m[0]'s own space\n")

# --- 13) A DIVERGED boundary is no longer refused, and no longer
#     collapsed to one midpoint wall either -- it now gets TWO
#     instances, one per side's own actual edge (m[0] -> x=1050, m[1]
#     -> x=950, same INDEPENDENT overlap as test 9), the SECOND
#     (Between[1] = m[1], the non-leading side) built with an EXTRA
#     mirror flip relative to this node's own state -- Between[0] is
#     always the leading, as-authored side. wall_doc's own content
#     here (door/header, single COLUMN) has nothing to visibly mirror
#     -- the width axis has only 1 entry -- so this test only proves
#     TWO instances land correctly; test 22 below proves the mirroring
#     itself with an asymmetric (multi-column) wallLayout. Each
#     instance nests DIRECTLY under its OWN matched host space (m[0]'s
#     own for the reference, m[1]'s own for the mirrored neighbour),
#     same depth an ordinary hosted child would use -- continuing that
#     host's own index sequence: roomA/roomB (each host's REGULAR
#     hosted child) claims index 0 first, so the wall's own door/header
#     content picks up at index 1/2, right after it, never colliding.
roomA13 = leaf(["1fr"], ["1fr"], [["ra"]], label="m[0]")
roomB13 = leaf(["1fr"], ["1fr"], [["rb"]], label="m[1]")
grid_div = leaf([1000.0, 1000.0], [2000.0], [["m[0]", "m[1]"]])
grid_div["childLayouts"] = [roomA13, roomB13]
grid_div["borderOverrides"] = [
    {"between": ["m[0]", "m[1]"], "offset": 50.0, "wallLayout": wall_doc}]
c13, l13, w13 = run_emit(grid_div, union=False)
assert any("diverged" in w and "TWO instances" in w for w in w13), w13
assert l13.branches.get(FakePath(0, 0, 0)) == ["ra"], l13.branches.get(FakePath(0, 0, 0))
assert l13.branches.get(FakePath(0, 0, 1)) == ["door"], l13.branches.get(FakePath(0, 0, 1))
assert l13.branches.get(FakePath(0, 0, 2)) == ["header"], l13.branches.get(FakePath(0, 0, 2))
assert l13.branches.get(FakePath(0, 1, 0)) == ["rb"], l13.branches.get(FakePath(0, 1, 0))
assert l13.branches.get(FakePath(0, 1, 1)) == ["door"], l13.branches.get(FakePath(0, 1, 1))
assert l13.branches.get(FakePath(0, 1, 2)) == ["header"], l13.branches.get(FakePath(0, 1, 2))
door_ref13 = x_range(c13.branches[FakePath(0, 0, 1)][0])
door_nb13 = x_range(c13.branches[FakePath(0, 1, 1)][0])
assert door_ref13[1] - door_ref13[0] == 2000.0, door_ref13
assert door_nb13[1] - door_nb13[0] == 2000.0, door_nb13
print("OK -- a diverged interior boundary (INDEPENDENT offset, m[0]/"
      "m[1] overlap by 100mm) places TWO wall instances, one nested "
      "directly under each side's own matched host space, instead of "
      "refusing or collapsing to a midpoint -- each host's own hosted "
      "child (roomA/roomB) keeps index 0, the wall's own content "
      "continues right after it (index 1/2), no collision\n")

# --- 14) RING mode's own candidate-finding is a separate code path
#     from PAIR's -- an EXT ring on the s1/k/s2 grid's west side
#     (['EXT','*','L']) touches column 0 in every one of its 4 rows
#     (s1, k, k, s2). Grid-adjacency ALONE would merge all 4 into one
#     wall -- but a run also breaks on a LABEL CHANGE (same rule as the
#     original Geom's own PERIMETER walk: 'adjacent cells sharing a
#     label merge into one run, a label change breaks it' -- the exact
#     behavior the user explicitly chose to KEEP by declining JoinWalls
#     for the original, see the session's own design discussion), so
#     this must come out as THREE separate walls -- s1 alone (1000mm),
#     k's own 2-row merge (2000mm, same label both rows), s2 alone
#     (1000mm) -- not one 4000mm wall spanning all three rooms.
grid_wall_ring = leaf([1000.0, 1000.0], [1000.0, 1000.0, 1000.0, 1000.0],
                       [["s1", "s1"], ["k", "s1"], ["k", "s2"], ["s2", "s2"]])
grid_wall_ring["borderOverrides"] = [
    {"between": ["EXT", "*", "L"], "wallLayout": wall_doc}]
c14, l14, w14 = run_emit(grid_wall_ring, union=False)
assert w14 == [], w14
# Each of the 3 walls nests DIRECTLY under its own matched host space
# ({0;0}=s1, {0;1}=k, {0;2}=s2), same depth an ordinary hosted child
# would use -- none of these hosts has a regular child of its own, so
# each wall's own door/header content starts right at index 0.
depth3_14 = [p for p in c14.Paths if p.Length == 3]
assert len(depth3_14) == 6, depth3_14  # 3 walls x (door + header), not 2 from one
s1_wall = x_range(c14.branches[FakePath(0, 0, 0)][0])
k_wall = x_range(c14.branches[FakePath(0, 1, 0)][0])
s2_wall = x_range(c14.branches[FakePath(0, 2, 0)][0])
assert s1_wall[1] - s1_wall[0] == 1000.0, s1_wall
assert k_wall[1] - k_wall[0] == 2000.0, k_wall
assert s2_wall[1] - s2_wall[0] == 1000.0, s2_wall
print("OK -- an EXT ring wall along s1/k/s2's west side splits at every "
      "LABEL change (s1 | k | s2 -- 1000/2000/1000mm), not just grid "
      "gaps -- k's own 2-row touch still merges into ONE wall since "
      "it's the SAME label both rows -- RING mode's own candidate-"
      "finding is exercised, not just PAIR's -- each wall nests "
      "directly under its own matched host space (s1/k/s2 respectively)\n")

# --- 15) The 'Cells' SELECTOR is back -- ported verbatim from the
#     original Geom (_filtered_cells_and_labels), wired into run() to
#     apply AFTER Depth filtering. Tested directly against test 1's
#     own s1/k/s2 result (run() itself needs a live ghenv, same as
#     every other test here never exercises it -- see the worker-
#     function-only testing convention used throughout this file).
c15, l15 = mod._filtered_cells_and_labels(c1, l1, ["s1"])
assert sorted(p.idx for p in c15.Paths if c15.branches[p]) == [(0, 0)], \
    [p for p in c15.Paths if c15.branches[p]]
assert len(c15.branches[FakePath(0, 0)]) == 3, c15.branches[FakePath(0, 0)]
assert l15.branches[FakePath(0, 0)] == ["s1", "s1", "s1"], l15.branches[FakePath(0, 0)]
assert not c15.branches.get(FakePath(0, 1)), c15.branches.get(FakePath(0, 1))
assert not c15.branches.get(FakePath(0, 2)), c15.branches.get(FakePath(0, 2))
# base-label matching: a '[k]'-suffixed instance matches its own base too.
c15b, l15b = mod._filtered_cells_and_labels(c4, l4, ["mod"])
mod0_kept = [p for p in c15b.Paths if c15b.branches[p]]
assert len(mod0_kept) == 1 and len(c15b.branches[mod0_kept[0]]) == 3, mod0_kept
print("OK -- the Cells selector narrows Cells/Labels to just the "
      "requested label(s), kept in lockstep, applied same as the "
      "original Geom's own selector -- including base-label matching "
      "('mod' selects every 'mod[0]'/'mod[1]' cell)\n")

# --- 16) Relaxed CellWidths: a wallLayout no longer has to be a single
#     ['auto'] column -- frame(400)/window(1fr)/frame(400), no 'auto'
#     at all, resolves against the wall's own actual matched length
#     (3000mm here) exactly like any other Layout2 grid -- the 'fr'
#     column soaks up whatever's left (3000 - 400 - 400 = 2200), using
#     the SAME track-resolution _resolve_tracks already had, no new
#     solving logic. The 'window' cell also hosts its own child
#     ('glass') -- proving a hosted child works on a WIDTH-wise
#     subdivided wall cell, not just the old single-column case.
window_wall = {"cellWidths": [400.0, "1fr", 400.0], "cellLengths": [3125.0],
               "cellLabels": [["frame", "window", "frame"]],
               "childLayouts": [{"label": "window", "cellWidths": ["1fr"],
                                  "cellLengths": ["1fr"],
                                  "cellLabels": [["glass"]]}]}
grid_window = leaf([1000.0, 1000.0], [3000.0], [["m[0]", "m[1]"]])
grid_window["borderOverrides"] = [
    {"between": ["m[0]", "m[1]"], "wallLayout": window_wall}]
c16, l16, w16 = run_emit(grid_window, union=False)
assert w16 == [], w16
# Nested DIRECTLY under m[0]'s own host space ({0;0}) -- frame/window/
# frame land at index 0/1/2, same depth an ordinary hosted child's own
# top-level spaces would use. The window cell's own 'glass' child then
# recurses one level deeper still, exactly like any other nested child.
assert l16.branches.get(FakePath(0, 0, 0)) == ["frame"], l16.branches.get(FakePath(0, 0, 0))
assert l16.branches.get(FakePath(0, 0, 1)) == ["window"], l16.branches.get(FakePath(0, 0, 1))
assert l16.branches.get(FakePath(0, 0, 2)) == ["frame"], l16.branches.get(FakePath(0, 0, 2))
assert l16.branches.get(FakePath(0, 0, 1, 0)) == ["glass"], l16.branches.get(FakePath(0, 0, 1, 0))
frame0 = x_range(c16.branches[FakePath(0, 0, 0)][0])
window_cell = x_range(c16.branches[FakePath(0, 0, 1)][0])
frame2 = x_range(c16.branches[FakePath(0, 0, 2)][0])
glass = x_range(c16.branches[FakePath(0, 0, 1, 0)][0])
assert frame0[1] - frame0[0] == 400.0, frame0
assert window_cell[1] - window_cell[0] == 2200.0, window_cell
assert frame2[1] - frame2[0] == 400.0, frame2
assert glass[1] - glass[0] == 2200.0, glass
print("OK -- a relaxed CellWidths (frame/window/frame, no 'auto', one "
      "'fr' column) resolves the window column to 2200mm (3000mm "
      "matched length minus 2x400mm frames), and the window cell's own "
      "hosted child ('glass') works exactly like on any other Layout2 "
      "node -- width-wise window/door subdivision no longer needs the "
      "single-'auto'-column special case\n")

# --- 17) INT ring for OFFSET -- the mirror of EXT ring: every cell,
#     any label, shifts independently on every side touching a
#     DIFFERENT real label (never off-grid, never a same-label
#     internal seam). On s1/k/s2: (0,1) [s1] has NO interior touches
#     at all (its N/E sides are true perimeter, its S/W sides touch
#     the SAME label) -- completely untouched. (1,0) [k] touches a
#     DIFFERENT label on BOTH its N side (s1) and E side (s1) --
#     both interior, both shift, independently.
grid_int = leaf([1000.0, 1000.0], [1000.0, 1000.0, 1000.0, 1000.0],
                [["s1", "s1"], ["k", "s1"], ["k", "s2"], ["s2", "s2"]])
grid_int["borderOverrides"] = [{"between": ["*", "INT"], "offset": 100.0}]
c17, l17, w17 = run_emit(grid_int, union=False)
assert w17 == [], w17
s1_branch17, k_branch17 = FakePath(0, 0), FakePath(0, 1)
assert cell_range(c17, l17, s1_branch17, "s1", 1000.0, 2000.0, 3000.0, 4000.0)  # (0,1) untouched
assert cell_range(c17, l17, k_branch17, "k", 0.0, 1100.0, 2000.0, 3100.0)  # (1,0): N+E both shift
print("OK -- an INT ring (offset) shifts every cell's own side that "
      "touches a DIFFERENT real label -- (0,1)'s all-perimeter-or-"
      "same-label sides stay untouched, (1,0)'s two genuinely "
      "interior sides (N and E, different labels each) both shift "
      "independently -- 'INT' finally does something on Geom2, "
      "matching what it already means for the original Geom's own "
      "Borders selector\n")

# --- 18) INT ring for WALLS -- places one wall per DISTINCT interior
#     boundary on s1/k/s2 (5 of them: s1|k, k|s1, s1|s2, k|s2, k|s2 --
#     see the comment in the code for the full trace), none merging
#     into each other despite two pairs sharing the same physical
#     line, because they're between DIFFERENT room pairs (the same
#     label-break rule from test 14, just exercised for INT instead of
#     EXT). Spot-checks one: s1's own south side against k, at y=3000,
#     spanning x=[0,1000] (wall_len=1000).
grid_int_wall = leaf([1000.0, 1000.0], [1000.0, 1000.0, 1000.0, 1000.0],
                      [["s1", "s1"], ["k", "s1"], ["k", "s2"], ["s2", "s2"]])
grid_int_wall["borderOverrides"] = [{"between": ["*", "INT"], "wallLayout": wall_doc}]
c18, l18, w18 = run_emit(grid_int_wall, union=False)
assert w18 == [], w18
# Each wall nests DIRECTLY under its own matched host space: s1 hosts
# 2 (s1|k, s1|s2) at index 0/1 -> door/header land at 0,1 then 2,3;
# k hosts all 3 (k|s1, and both k|s2 boundaries) at index 0/1/2 ->
# door/header at 0,1 then 2,3 then 4,5; s2 hosts none of its own
# (it's always the neighbour/matched side, never the reference).
depth3_18 = [p for p in c18.Paths if p.Length == 3]
assert len(depth3_18) == 10, depth3_18  # 5 walls x (door + header)
s1_k_wall = x_range(c18.branches[FakePath(0, 0, 0)][0])
assert s1_k_wall[1] - s1_k_wall[0] == 1000.0, s1_k_wall
print("OK -- an INT ring wallLayout places one wall per distinct "
      "interior boundary on s1/k/s2 (5 total, correctly NOT merging "
      "the two k|s2 boundaries that happen to share a physical line, "
      "since they're between different room pairs) -- RING mode's "
      "INT branch is exercised for walls too, not just offset -- each "
      "wall nests directly under its own matched host space\n")

# --- 19) MIRROR flips column (WIDTH) order only -- row (HEIGHT) order
#     is untouched. 2x2 grid, mirror=True: cellWidths [1000,2000] ->
#     [2000,1000], so 'a'/'b' (row0) and 'c'/'d' (row1) swap which
#     column they're in, but row0 stays on TOP and row1 stays on
#     BOTTOM (same y-ranges either mirror is on or not).
grid_mirror = leaf([1000.0, 2000.0], [500.0, 700.0],
                    [["a", "b"], ["c", "d"]])
grid_mirror["mirror"] = True
c19, l19, w19 = run_emit(grid_mirror, union=False)
assert w19 == [], w19
assert cell_range(c19, l19, FakePath(0, 1), "a", 2000.0, 3000.0, 700.0, 1200.0)
assert cell_range(c19, l19, FakePath(0, 0), "b", 0.0, 2000.0, 700.0, 1200.0)
assert cell_range(c19, l19, FakePath(0, 3), "c", 2000.0, 3000.0, 0.0, 700.0)
assert cell_range(c19, l19, FakePath(0, 2), "d", 0.0, 2000.0, 0.0, 700.0)
print("OK -- Mirror flips CellWidths/CellLabels column order (a/b and "
      "c/d swap sides) while row order (a/b on top, c/d on bottom) "
      "stays exactly as authored -- width axis only, as intended\n")

# --- 20) MIRROR CASCADES to a hosted child automatically -- an
#     apartment node with mirror=True hosts a 'mod' child that has NO
#     'mirror' field of its own, yet its own columns still flip ('x'/
#     'y' swap sides) -- proving a whole apartment mirrors into a
#     mirrored copy of itself, not just its own outermost grid, with
#     no per-node opt-out needed.
module20 = leaf([100.0, 300.0], [500.0], [["x", "y"]], label="mod")
apt20 = leaf([1000.0, 2000.0], [500.0], [["mod", "other"]])
apt20["mirror"] = True
apt20["childLayouts"] = [module20]
c20, l20, w20 = run_emit(apt20, union=False)
assert w20 == [], w20
# apt20 itself mirrors: cellWidths [1000,2000] -> [2000,1000], labels
# ["mod","other"] -> ["other","mod"] -- 'mod' is now space index 1.
assert l20.branches.get(FakePath(0, 1)) == ["mod"], l20.branches.get(FakePath(0, 1))
# module20's own cellWidths [100,300] -> [300,100], labels ["x","y"]
# -> ["y","x"] -- inherited, never set on module20 itself.
assert l20.branches.get(FakePath(0, 1, 0)) == ["y"], l20.branches.get(FakePath(0, 1, 0))
assert l20.branches.get(FakePath(0, 1, 1)) == ["x"], l20.branches.get(FakePath(0, 1, 1))
y20 = x_range(c20.branches[FakePath(0, 1, 0)][0])
x20 = x_range(c20.branches[FakePath(0, 1, 1)][0])
assert y20[1] - y20[0] == 300.0, y20
assert x20[1] - x20[0] == 100.0, x20
print("OK -- Mirror cascades to a hosted child automatically -- "
      "'mod' (apt20's own child) mirrors its own x/y columns too, "
      "despite having no 'mirror' field of its own -- inherited from "
      "its parent, matching 'a whole apartment mirrors into a "
      "mirrored copy of itself'\n")

# --- 21) MIRROR cascades to a hosted WALL too, not just an ordinary
#     hosted child -- a mirrored apartment's own asymmetric wallLayout
#     (frame(400)/window(1fr), NOT symmetric) flips which side the
#     frame ends up on. m0/m1's own track sizes are equal (1000/1000),
#     so the wall's own overall position/length is untouched by the
#     mirror (isolating the effect to the wall's own internal order).
grid21 = leaf([1000.0, 1000.0], [2000.0], [["m0", "m1"]])
grid21["mirror"] = True
grid21["borderOverrides"] = [
    {"between": ["m0", "m1"],
     "wallLayout": {"cellWidths": [400.0, "1fr"], "cellLengths": [2000.0],
                     "cellLabels": [["frame", "window"]]}}]
c21, l21, w21 = run_emit(grid21, union=False)
assert w21 == [], w21
# Host = m0 (Between[0], the reference side) -- mirror also reorders
# the node's own space list, so m0's own space now sits at column
# index 1 ({0;1}), with m1 at {0;0}; the wall nests DIRECTLY under
# that, at {0;1;...} (m0 hosts no regular child, so window/frame get
# index 0/1 with no offset needed).
assert l21.branches.get(FakePath(0, 1, 0)) == ["window"], l21.branches.get(FakePath(0, 1, 0))
assert l21.branches.get(FakePath(0, 1, 1)) == ["frame"], l21.branches.get(FakePath(0, 1, 1))
window21 = x_range(c21.branches[FakePath(0, 1, 0)][0])
frame21 = x_range(c21.branches[FakePath(0, 1, 1)][0])
assert frame21[1] - frame21[0] == 400.0, frame21
assert frame21[0] > window21[0], (frame21, window21)  # frame now on the FAR side
print("OK -- Mirror cascades to a hosted wall too -- an asymmetric "
      "frame/window wallLayout flips which side the frame lands on, "
      "same cascading rule as any other hosted child\n")

# --- 22) The SAME wallLayout content lands at the SAME physical spot
#     on BOTH sides of a diverged boundary, because the neighbour's
#     own instance gets an EXTRA mirror flip -- an asymmetric
#     frame(400)/window(1fr) wallLayout. A tiny offset (1mm) forces
#     the boundary through the two-instance path. Between[0]=m0 is
#     the leading side (frame first, as-authored); Between[1]=m1 is
#     mirrored (frame LAST) -- proving 'the first Between item leads'.
roomA22 = leaf(["1fr"], ["1fr"], [["ra"]], label="m0")
roomB22 = leaf(["1fr"], ["1fr"], [["rb"]], label="m1")
grid22 = leaf([1000.0, 1000.0], [2000.0], [["m0", "m1"]])
grid22["childLayouts"] = [roomA22, roomB22]
grid22["borderOverrides"] = [
    {"between": ["m0", "m1"], "offset": 1.0,
     "wallLayout": {"cellWidths": [400.0, "1fr"], "cellLengths": [2000.0],
                     "cellLabels": [["frame", "window"]]}}]
c22, l22, w22 = run_emit(grid22, union=False)
assert any("diverged" in w and "TWO instances" in w for w in w22), w22
# Between[0]=m0's own instance: as-authored, frame FIRST (lower x).
# m0's own child ('ra') claims index 0 at {0;0;0}; the wall's own
# content (frame/window) continues right after it, at index 1/2 --
# same depth as 'ra', no wrapper segment, no collision.
assert l22.branches.get(FakePath(0, 0, 0)) == ["ra"], l22.branches.get(FakePath(0, 0, 0))
assert l22.branches.get(FakePath(0, 0, 1)) == ["frame"], l22.branches.get(FakePath(0, 0, 1))
assert l22.branches.get(FakePath(0, 0, 2)) == ["window"], l22.branches.get(FakePath(0, 0, 2))
# Between[1]=m1's own instance: mirrored, frame LAST (higher x).
assert l22.branches.get(FakePath(0, 1, 0)) == ["rb"], l22.branches.get(FakePath(0, 1, 0))
assert l22.branches.get(FakePath(0, 1, 1)) == ["window"], l22.branches.get(FakePath(0, 1, 1))
assert l22.branches.get(FakePath(0, 1, 2)) == ["frame"], l22.branches.get(FakePath(0, 1, 2))
frame_ref22 = x_range(c22.branches[FakePath(0, 0, 1)][0])
frame_nb22 = x_range(c22.branches[FakePath(0, 1, 2)][0])
assert frame_ref22[1] - frame_ref22[0] == 400.0, frame_ref22
assert frame_nb22[1] - frame_nb22[0] == 400.0, frame_nb22
print("OK -- the neighbour's own wall instance (Between[1] = m1) is "
      "built mirrored relative to the reference instance (Between[0] "
      "= m0, as-authored) -- frame/window swap sides between the two, "
      "keeping the same physical door position visible correctly "
      "from both rooms despite the opposite winding each side's own "
      "outward normal needs\n")

# --- 23) _split_warnings correctly classifies a remark EVEN when it's
#     been wrapped by run()'s own "item {i}: {w}" prefix (multi-item
#     JSON input) -- a real, live bug: `startswith` missed every
#     remark once "item 2: " landed in front of it, so it fell through
#     to the runtime-message balloon (raw, unstripped 'REMARK: ' text
#     and all) instead of the Warnings output, which stayed empty.
wrapped = "item 2: " + mod._REMARK_PREFIX + "diverged, placed as TWO instances"
real23, remarks23 = mod._split_warnings(
    ["item 0: a genuine problem", wrapped, "another genuine problem"])
assert real23 == ["item 0: a genuine problem", "another genuine problem"], real23
assert remarks23 == ["item 2: diverged, placed as TWO instances"], remarks23
print("OK -- _split_warnings correctly classifies a remark as a "
      "remark even after run()'s own multi-item 'item {i}: ' wrapping "
      "has pushed the prefix away from the very start -- the exact "
      "live bug this test locks in against\n")

# --- 24) Two OPPOSITE walls from the SAME node, sharing the SAME
#     wallLayout label ('pf'), land in ONE branch instead of two -- a
#     single EXT ring with a T,B side filter on a 1x2 's1' grid places
#     one wall on the north row's own N side and one on the south
#     row's own S side (different edge codes, never merge as a RUN),
#     but since both come from the SAME wallLayout document (same
#     label, same host space), they now reuse the same index
#     -- their own 'frame' cells land together as 2 items in ONE
#     branch, not 2 separate branches, matching how a bare multi-cell
#     space already holds N rectangles in one branch.
pf_wall = {"label": "pf", "cellWidths": ["auto"], "cellLengths": [500.0],
           "cellLabels": [["frame"]]}
grid24 = leaf([1000.0], [1000.0, 1000.0], [["s1"], ["s1"]])
grid24["borderOverrides"] = [
    {"between": ["*", "EXT", "T,B"], "wallLayout": pf_wall}]
c24, l24, w24 = run_emit(grid24, union=False)
assert w24 == [], w24
# Nested DIRECTLY under s1's own host space ({0;0}), same depth an
# ordinary hosted child would use -- both placements share (host,
# label), so both land at the SAME index (0).
assert l24.branches.get(FakePath(0, 0, 0)) == ["frame", "frame"], l24.branches.get(FakePath(0, 0, 0))
frame_items = c24.branches[FakePath(0, 0, 0)]
assert len(frame_items) == 2, frame_items
ranges24 = sorted((x_range(c), y_range(c)) for c in frame_items)
assert ranges24[0] != ranges24[1], ranges24  # genuinely two different positions
print("OK -- two opposite walls (north + south) sharing the SAME "
      "wallLayout label ('pf') land in ONE branch, as 2 distinct "
      "items at 2 different positions, instead of 2 separate "
      "branches -- grouped by wall_doc's own label, scoped to this "
      "one node's own _place_walls call\n")

# --- 25) An UNLABELED wallLayout keeps today's behavior exactly --
#     each placement still gets its OWN fresh wall_k, nothing to
#     group by. Same setup as test 24, minus the 'label' field.
pf_wall_unlabeled = {"cellWidths": ["auto"], "cellLengths": [500.0],
                      "cellLabels": [["frame"]]}
grid25 = leaf([1000.0], [1000.0, 1000.0], [["s1"], ["s1"]])
grid25["borderOverrides"] = [
    {"between": ["*", "EXT", "T,B"], "wallLayout": pf_wall_unlabeled}]
c25, l25, w25 = run_emit(grid25, union=False)
assert w25 == [], w25
# Nested DIRECTLY under s1's own host space ({0;0}); the two walls (no
# label to group by) still get separate, non-colliding indices, 0 and 1.
assert l25.branches.get(FakePath(0, 0, 0)) == ["frame"], l25.branches.get(FakePath(0, 0, 0))
assert l25.branches.get(FakePath(0, 0, 1)) == ["frame"], l25.branches.get(FakePath(0, 0, 1))
print("OK -- an UNLABELED wallLayout is unaffected -- each placement "
      "still gets its own fresh index, exactly like before this "
      "feature existed\n")

# --- 26) WallHeight: a wall has a real WIDTH total (the matched
#     border's length) but no HEIGHT total, so a '1fr' in its
#     CellLengths used to resolve to 0mm (with a warning). An override's
#     'wallHeight' is now passed as the wall's own given_h: CellLengths
#     [900, '1fr', 300] against wallHeight 2600 -> 900 / 1400 / 300.
#     Without it: unchanged (the 'fr' row collapses, warned).
tall_wall = {"cellWidths": ["auto"], "cellLengths": [900.0, "1fr", 300.0],
             "cellLabels": [["a"], ["b"], ["c"]]}
grid26 = leaf([1000.0, 1000.0], [1000.0, 1000.0],
              [["m[0]", "m[1]"], ["m[0]", "m[1]"]])
grid26["borderOverrides"] = [
    {"between": ["m[0]", "m[1]"], "wallLayout": tall_wall,
     "wallHeight": 2600.0}]
c26, l26, w26 = run_emit(grid26, union=False)
assert w26 == [], w26
heights26 = [y_range(c26.branches[FakePath(0, 0, i)][0]) for i in range(3)]
assert [round(h[1] - h[0], 6) for h in heights26] == [900.0, 1400.0, 300.0], heights26

grid26b = leaf([1000.0, 1000.0], [1000.0, 1000.0],
               [["m[0]", "m[1]"], ["m[0]", "m[1]"]])
grid26b["borderOverrides"] = [
    {"between": ["m[0]", "m[1]"], "wallLayout": tall_wall}]
c26b, l26b, w26b = run_emit(grid26b, union=False)
assert any("nothing to share" in w for w in w26b), w26b
mid = y_range(c26b.branches[FakePath(0, 0, 1)][0])
assert mid[1] - mid[0] == 0.0, mid

grid26c = leaf([1000.0, 1000.0], [1000.0, 1000.0],
               [["m[0]", "m[1]"], ["m[0]", "m[1]"]])
grid26c["borderOverrides"] = [
    {"between": ["m[0]", "m[1]"], "wallLayout": tall_wall,
     "wallHeight": "tall"}]
c26c, l26c, w26c = run_emit(grid26c, union=False)
assert any("wallHeight" in w and "positive" in w for w in w26c), w26c
print("OK -- wallHeight is the total a wall's CellLengths 'fr' rows "
      "resolve against (900/1400/300 for [900,'1fr',300] at 2600); "
      "unset keeps the old no-total behavior; junk is ignored, warned\n")

print("ALL OK")
