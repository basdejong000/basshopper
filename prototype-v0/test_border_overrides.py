"""Headless test of border overrides (Between/wallType/Offset) applied
by pms-layout-geom-v0.py: the SHARED (track-shifting) mechanism, the
INDEPENDENT (per-child, non-rippling) mechanism, and wallType=='none'
suppression, kept aligned with Topology."""
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

    def PointAt(self, x, y, z):
        return (self.ox + x, self.oy + y, z)


spec = importlib.util.spec_from_file_location(
    "geom",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms-layout-geom-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["geom"] = mod
spec.loader.exec_module(mod)


class FakeRG:
    Plane = FakePlane

    @staticmethod
    def PolylineCurve(pts):
        return ("CURVE", tuple(pts))

    @staticmethod
    def Line(p0, p1):
        return ("LINE", p0, p1)


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


def run_emit(node):
    c, l, b, t = FakeTree(), FakeTree(), FakeTree(), FakeTree()
    mod._emit(node, None, None, FakePlane(), FakePath(0), c, l, b, t, [], {})
    return c, l, b, t


# --- 1) SHARED, plain-plain: two rooms, b1 | b2, each 1000mm, Offset
#     100 toward Between[1]=b2 -- b1 (the 'before' track) grows to
#     1100, b2 shrinks to 900. Total unchanged (2000).
two_rooms = leaf([1000.0, 1000.0], [500.0], [["b1", "b2"]])
two_rooms["borderOverrides"] = [{"between": ["b1", "b2"], "offset": 100.0}]
c1, l1, b1t, t1 = run_emit(two_rooms)
assert l1.branches[FakePath(0)] == ["b1", "b2"]
b1_curve, b2_curve = c1.branches[FakePath(0)]
assert x_range(b1_curve) == (0.0, 1100.0), x_range(b1_curve)
assert x_range(b2_curve) == (1100.0, 2000.0), x_range(b2_curve)
print("OK -- SHARED: two plain rooms, Offset 100 toward Between[1] "
      "grows b1 to 1100, shrinks b2 to 900, total unchanged\n")

# --- 2) SHARED, mixed pair (mullion): 'frame' (plain) | 'window'
#     (hosts a child, 1fr glass). Offset 100 toward Between[1]=window
#     -- frame grows to 1100, window's OWN cell shrinks to 900, and
#     its CHILD (glass, 1fr) inherits that reduced 900 as its given_w,
#     cascading automatically -- nothing authored for the child.
glass = leaf(["1fr"], ["1fr"], [["glass"]], label="window")
mullion = leaf([1000.0, 1000.0], [500.0], [["frame", "window"]])
mullion["childLayouts"] = [glass]
mullion["borderOverrides"] = [{"between": ["frame", "window"], "offset": 100.0}]
c2, l2, b2t, t2 = run_emit(mullion)
frame_curve, window_curve = c2.branches[FakePath(0)]
assert x_range(frame_curve) == (0.0, 1100.0), x_range(frame_curve)
assert x_range(window_curve) == (1100.0, 2000.0), x_range(window_curve)
glass_curve = c2.branches[FakePath(0, 1)][0]   # window is index 1 -> its own list-branch {0;1}
assert x_range(glass_curve) == (1100.0, 2000.0), x_range(glass_curve)
print("OK -- SHARED mixed pair: frame (plain) grows to 1100, window's "
      "own cell shrinks to 900 (1100-2000), and its child 'glass' "
      "(1fr) cascades to that same reduced width automatically\n")

# --- 3) INDEPENDENT, both children (sliding door): panelA | panelB,
#     each its own 1fr child. Offset 50 -- doors' OWN track SIZES for
#     panelA/panelB are unchanged (no rippling into a sibling's size),
#     but BOTH the parent's own drawn cell shape AND the child's given
#     frame reflect the SAME offset -- panelA's own cell now reads
#     0-1050, matching its child; panelB's own cell reads 950-2000,
#     matching its child. The two levels agree. The single INTERIOR
#     border segment between panelA/panelB DUPLICATES into TWO once
#     they've diverged like this -- one at x=1050 (panelA's own east
#     edge, matching its Cells shape exactly) and one at x=950
#     (panelB's own west edge) -- rather than freezing at the stale
#     original x=1000, which would match NEITHER cell any more. BOTH
#     still report the same [panelA, panelB] Topology pair.
glassA = leaf(["1fr"], ["1fr"], [["glassA"]], label="panelA")
glassB = leaf(["1fr"], ["1fr"], [["glassB"]], label="panelB")
doors = leaf([1000.0, 1000.0], [500.0], [["panelA", "panelB"]])
doors["childLayouts"] = [glassA, glassB]
doors["borderOverrides"] = [{"between": ["panelA", "panelB"], "offset": 50.0}]
c3, l3, b3t, t3 = run_emit(doors)
panelA_curve, panelB_curve = c3.branches[FakePath(0)]
assert x_range(panelA_curve) == (0.0, 1050.0), x_range(panelA_curve)
assert x_range(panelB_curve) == (950.0, 2000.0), x_range(panelB_curve)
glassA_curve = c3.branches[FakePath(0, 0)][0]
glassB_curve = c3.branches[FakePath(0, 1)][0]
assert x_range(glassA_curve) == (0.0, 1050.0), x_range(glassA_curve)
assert x_range(glassB_curve) == (950.0, 2000.0), x_range(glassB_curve)
def _is_interior_vertical(ln):
    return ln[1][0] == ln[2][0] and 0.0 < ln[1][0] < 2000.0


interior_xs = sorted(ln[1][0] for ln in b3t.branches[FakePath(0)]
                      if _is_interior_vertical(ln))
assert interior_xs == [950.0, 1050.0], interior_xs
assert len(b3t.branches[FakePath(0)]) == 8, b3t.branches[FakePath(0)]   # 7 + 1 duplicate
interior_pairs = [set(t3.branches[FakePath(0, k)])
                  for k, ln in enumerate(b3t.branches[FakePath(0)])
                  if _is_interior_vertical(ln)]
assert interior_pairs == [{"panelA", "panelB"}, {"panelA", "panelB"}], interior_pairs
print("OK -- INDEPENDENT both-children: doors' own panelA/panelB cell "
      "shapes now agree with their children (0-1050 / 950-2000, a "
      "950-1050 overlap at BOTH depths), and the interior wall DUPLICATES "
      "into two segments (x=950, x=1050) matching each cell's own edge, "
      "both still reporting the same [panelA, panelB] Topology pair\n")

# --- 4) INDEPENDENT, EXT (perimeter): 'mycell' (hosts a child) sits
#     in the MIDDLE row of a 3-row, 2-column grid, so it touches ONLY
#     the west edge (_perimeter_side needs exactly one matching side --
#     a cell spanning the full height would also touch north AND
#     south, which is deliberately left unhandled/ambiguous, see
#     _perimeter_side). Between=['mycell','EXT'], Offset 50 -- mycell's
#     OWN cell now shrinks to (-50, 1000) too, matching its child, AND
#     its west BORDER segment moves to x=-50 to match -- not just the
#     child one level deeper.
glass2 = leaf(["1fr"], ["1fr"], [["glass2"]], label="mycell")
two_cols = leaf(
    [1000.0, 1000.0], [500.0, 500.0, 500.0],
    [["top", "otherT"], ["mycell", "otherM"], ["bottom", "otherB"]])
two_cols["childLayouts"] = [glass2]
two_cols["borderOverrides"] = [{"between": ["mycell", "EXT"], "offset": 50.0}]
c4, l4, b4t, t4 = run_emit(two_cols)
mycell_curve = [crv for crv, lbl in zip(c4.branches[FakePath(0)],
                                         l4.branches[FakePath(0)])
                 if lbl == "mycell"][0]
assert x_range(mycell_curve) == (-50.0, 1000.0), x_range(mycell_curve)
glass2_curve = c4.branches[FakePath(0, 2)][0]   # 'mycell' is row-major index 2
assert x_range(glass2_curve) == (-50.0, 1000.0), x_range(glass2_curve)
mycell_west_wall = [ln for ln in b4t.branches[FakePath(0)]
                     if ln[1][0] == ln[2][0] and ln[1][0] == -50.0]
assert len(mycell_west_wall) == 1, b4t.branches[FakePath(0)]
print("OK -- INDEPENDENT EXT: mycell's own cell AND its west border "
      "segment both shift to x=-50, matching its child -- consistent "
      "at every Depth, not just one level deeper\n")

# --- 5) Ring/global selectors have no effect (Offset -- the only
#     thing an override document carries now -- only ever acts on a
#     pair) and are warned rather than silently ignored. Cells/Borders
#     come out completely unaffected.
container = leaf([1000.0, 1000.0], [500.0], [["p", "q"]])
container["borderOverrides"] = [{"between": ["*", "*"], "offset": 50.0}]
c5, l5, b5t, t5 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w5 = []
mod._emit(container, None, None, FakePlane(), FakePath(0), c5, l5, b5t,
          t5, w5, {})
assert l5.branches[FakePath(0)] == ["p", "q"]
assert len(b5t.branches[FakePath(0)]) == 7   # unchanged: 2 cols x 1 row -> full perimeter + 1 interior
assert any("has no effect" in w for w in w5), w5
print("OK -- a global selector with Offset has no effect (only a "
      "pair can be moved) and is warned rather than silently "
      "ignored -- Cells/Borders unaffected\n")

# --- 6) A CORNER cell (touches both North and West) with an EXT
#     override and NO side filter -- applies to BOTH touching sides at
#     once (unfiltered = every touching side, matching the old wall-
#     override system's own "unfiltered ring = every wall" default),
#     not an ambiguous failure.
corner_child = leaf(["1fr"], ["1fr"], [["cc"]], label="corner")
grid2x2 = leaf([1000.0, 1000.0], [1000.0, 1000.0],
               [["corner", "x"], ["y", "z"]])
grid2x2["childLayouts"] = [corner_child]
grid2x2["borderOverrides"] = [{"between": ["corner", "EXT"], "offset": 50.0}]
c6, l6, b6t, t6 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w6 = []
mod._emit(grid2x2, None, None, FakePlane(), FakePath(0), c6, l6, b6t, t6,
          w6, {})
cc_curve = c6.branches[FakePath(0, 0)][0]   # corner's OWN child cell, one level deeper
assert x_range(cc_curve) == (-50.0, 1000.0), x_range(cc_curve)   # west extends
assert y_range(cc_curve) == (1000.0, 2050.0), y_range(cc_curve)  # north ALSO extends
assert w6 == [], w6
print("OK -- a corner cell with no side filter extends on BOTH "
      "touching sides at once (west and north), no warning\n")

# --- 7) Same corner cell, this time WITH a side filter -- Between =
#     ['corner', 'EXT', 'Left'] (old wall-override vocabulary: Top/
#     Bottom/Left/Right, mapped internally onto this system's own
#     N/S/E/W -- 'Left' = West, column 0) resolves the ambiguity: only
#     the west edge (x0) shifts, north (y1) is untouched. Short form
#     ('L') works identically -- see SIDE_CODES.
corner_child2 = leaf(["1fr"], ["1fr"], [["cc2"]], label="corner")
grid2x2b = leaf([1000.0, 1000.0], [1000.0, 1000.0],
                [["corner", "x"], ["y", "z"]])
grid2x2b["childLayouts"] = [corner_child2]
grid2x2b["borderOverrides"] = [
    {"between": ["corner", "EXT", "Left"], "offset": 50.0}]
c7, l7, b7t, t7 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w7 = []
mod._emit(grid2x2b, None, None, FakePlane(), FakePath(0), c7, l7, b7t, t7,
          w7, {})
cc2_curve = c7.branches[FakePath(0, 0)][0]   # corner's OWN child cell, one level deeper
assert x_range(cc2_curve) == (-50.0, 1000.0), x_range(cc2_curve)
assert y_range(cc2_curve) == (1000.0, 2000.0), y_range(cc2_curve)
corner_own_curve = [crv for crv, lbl in zip(c7.branches[FakePath(0)],
                                             l7.branches[FakePath(0)])
                     if lbl == "corner"][0]
assert x_range(corner_own_curve) == (-50.0, 1000.0), x_range(corner_own_curve)
assert y_range(corner_own_curve) == (1000.0, 2000.0), y_range(corner_own_curve)
assert w7 == [], w7
print("OK -- 'Left' side filter resolves the corner ambiguity -- only "
      "the west edge extends, north is untouched\n")

# --- 7b) '*' as the 3rd item is an explicit wildcard ("any side"),
#     same as omitting it entirely -- NOT an unrecognized/invalid
#     token. Reusing test 4's 3-row shape so 'mycell' touches only
#     West (unambiguous), '*' should resolve automatically with NO
#     warning, same result as no side filter at all.
glass2b = leaf(["1fr"], ["1fr"], [["glass2b"]], label="mycell")
two_cols_b = leaf(
    [1000.0, 1000.0], [500.0, 500.0, 500.0],
    [["top", "otherT"], ["mycell", "otherM"], ["bottom", "otherB"]])
two_cols_b["childLayouts"] = [glass2b]
two_cols_b["borderOverrides"] = [
    {"between": ["mycell", "EXT", "*"], "offset": 50.0}]
c7b, l7b, b7bt, t7b = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w7b = []
mod._emit(two_cols_b, None, None, FakePlane(), FakePath(0), c7b, l7b, b7bt,
          t7b, w7b, {})
glass2b_curve = c7b.branches[FakePath(0, 2)][0]   # 'mycell' is row-major index 2
assert x_range(glass2b_curve) == (-50.0, 1000.0), x_range(glass2b_curve)
assert w7b == [], w7b
print("OK -- '*' as the side filter is an explicit wildcard, resolves "
      "automatically with no warning (same as omitting it)\n")

# --- 8) PLAIN cells, no children at all (the reported bug): label 'a'
#     with cells m1, m2 -- each 4000 wide, 8000 tall, NEITHER hosting
#     a child. Between=['m1','EXT'], Offset=-200 with NO side filter:
#     m1 is a single-row leftmost cell, touching THREE grid edges
#     (west, north, south) -- unfiltered means ALL THREE shrink at
#     once (200mm inset each), no warning, no side filter needed --
#     exactly the "window glass pane insets from its frame on every
#     side" case, just with 3 sides instead of 4.
a_plain = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
a_plain["borderOverrides"] = [{"between": ["m1", "EXT"], "offset": -200.0}]
c8, l8, b8t, t8 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w8 = []
mod._emit(a_plain, None, None, FakePlane(), FakePath(0), c8, l8, b8t, t8,
          w8, {})
m1_curve = c8.branches[FakePath(0)][0]
assert x_range(m1_curve) == (200.0, 4000.0), x_range(m1_curve)   # west only (no east edge here)
assert y_range(m1_curve) == (200.0, 7800.0), y_range(m1_curve)   # north AND south both inset
assert w8 == [], w8
print("OK -- a plain cell (no children) touching 3 grid edges shrinks "
      "on all 3 at once with an unfiltered EXT override, no warning\n")

# --- 9) Same plain cells, this time with an explicit side ('Left') --
#     m1's own drawn cell shrinks 200mm from its west edge, with NO
#     child involved at all. m2 (untouched by this override) stays put.
a_plain2 = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
a_plain2["borderOverrides"] = [
    {"between": ["m1", "EXT", "Left"], "offset": -200.0}]
c9, l9, b9t, t9 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w9 = []
mod._emit(a_plain2, None, None, FakePlane(), FakePath(0), c9, l9, b9t, t9,
          w9, {})
m1_curve2, m2_curve2 = c9.branches[FakePath(0)]
assert x_range(m1_curve2) == (200.0, 4000.0), x_range(m1_curve2)
assert x_range(m2_curve2) == (4000.0, 8000.0), x_range(m2_curve2)
print("OK -- with an explicit side, a PLAIN cell's own drawn boundary "
      "shrinks directly -- no bound child required\n")

# --- 9b) THE motivating case: a window's glass pane, ONE cell filling
#     its ENTIRE frame (so it touches all 4 grid edges), hosting its
#     own child (the actual glass geometry). ONE override, no side
#     filter, Offset=-25 -- glass insets 25mm from the frame on EVERY
#     side at once (a 50mm total reveal), both the cell's own shape
#     and its child agree.
glass_content = leaf(["1fr"], ["1fr"], [["pane"]], label="glass")
frame = leaf([1000.0], [1000.0], [["glass"]])
frame["childLayouts"] = [glass_content]
frame["borderOverrides"] = [{"between": ["glass", "EXT"], "offset": -25.0}]
c9b, l9b, b9bt, t9b = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w9b = []
mod._emit(frame, None, None, FakePlane(), FakePath(0), c9b, l9b, b9bt, t9b,
          w9b, {})
glass_own_curve = c9b.branches[FakePath(0)][0]
pane_curve = c9b.branches[FakePath(0, 0)][0]
for curve in (glass_own_curve, pane_curve):
    assert x_range(curve) == (25.0, 975.0), x_range(curve)
    assert y_range(curve) == (25.0, 975.0), y_range(curve)
assert w9b == [], w9b
print("OK -- the window-pane case: one override, no side filter, "
      "insets a cell touching all 4 grid edges on all 4 sides at "
      "once -- no need to specify each side individually\n")

# --- 10) The user's ACTUAL scenario: label 'a' with cells m1, m2 --
#     each 4000 wide, 8000 tall, and THIS time each DOES host its own
#     child. Between=['m1','EXT','Left'], Offset=-200 -- m1's own cell
#     at 'a's level shrinks (200-4000), its west BORDER segment moves
#     to x=200 to match, AND its child inherits the same reduced
#     frame -- all three agree, not just the child one level deeper.
room1 = leaf(["1fr"], ["1fr"], [["room1"]], label="m1")
room2 = leaf(["1fr"], ["1fr"], [["room2"]], label="m2")
a_with_children = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
a_with_children["childLayouts"] = [room1, room2]
a_with_children["borderOverrides"] = [
    {"between": ["m1", "EXT", "Left"], "offset": -200.0}]
c10, l10, b10t, t10 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w10 = []
mod._emit(a_with_children, None, None, FakePlane(), FakePath(0), c10, l10,
          b10t, t10, w10, {})
m1_own, m2_own = c10.branches[FakePath(0)]
assert x_range(m1_own) == (200.0, 4000.0), x_range(m1_own)
assert x_range(m2_own) == (4000.0, 8000.0), x_range(m2_own)
room1_curve = c10.branches[FakePath(0, 0)][0]
assert x_range(room1_curve) == (200.0, 4000.0), x_range(room1_curve)
m1_west_wall = [ln for ln in b10t.branches[FakePath(0)]
                if ln[1][0] == ln[2][0] and ln[1][0] == 200.0]
assert len(m1_west_wall) == 1, b10t.branches[FakePath(0)]
print("OK -- m1's own cell, its west border segment, AND its child's "
      "geometry all agree on the shrunk boundary -- exactly the "
      "reported scenario\n")

# --- 11) RING, sibling-to-sibling: 'a' with cells m1, m2 (2 cols x 1
#     row, each 4000x8000, each hosting its own child, like #10) --
#     but Between=['m1','*'], Offset=-200, NO side filter. m1 touches
#     west/north/south (EXT) AND east (m2, a real sibling, not EXT).
#     RING is always independent, so ALL FOUR of m1's sides shrink at
#     once -- including the one facing m2 -- while m2 (and its own
#     child) stay COMPLETELY untouched: no track resize, no shape
#     change. The border between m1/m2 DUPLICATES into two segments --
#     m1's own east edge (x=3800, spanning its now-shorter y=200-7800,
#     since m1 shrank on ITS north/south sides too) and m2's own west
#     edge (x=4000, unchanged, spanning the FULL original y=0-8000,
#     since m2 was never targeted at all) -- rather than freezing at
#     the stale original x=4000 for both. Same rule as the both-
#     children case in #3, just reached via a ring instead of a pair.
room1b = leaf(["1fr"], ["1fr"], [["room1b"]], label="m1")
room2b = leaf(["1fr"], ["1fr"], [["room2b"]], label="m2")
a_ring = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
a_ring["childLayouts"] = [room1b, room2b]
a_ring["borderOverrides"] = [{"between": ["m1", "*"], "offset": -200.0}]
c11, l11, b11t, t11 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w11 = []
mod._emit(a_ring, None, None, FakePlane(), FakePath(0), c11, l11, b11t, t11,
          w11, {})
m1_r_own, m2_r_own = c11.branches[FakePath(0)]
assert x_range(m1_r_own) == (200.0, 3800.0), x_range(m1_r_own)
assert y_range(m1_r_own) == (200.0, 7800.0), y_range(m1_r_own)
assert x_range(m2_r_own) == (4000.0, 8000.0), x_range(m2_r_own)
assert y_range(m2_r_own) == (0.0, 8000.0), y_range(m2_r_own)
room1b_curve = c11.branches[FakePath(0, 0)][0]
room2b_curve = c11.branches[FakePath(0, 1)][0]
assert x_range(room1b_curve) == (200.0, 3800.0), x_range(room1b_curve)
assert x_range(room2b_curve) == (4000.0, 8000.0), x_range(room2b_curve)
interior_segs_r = [ln for k, ln in enumerate(b11t.branches[FakePath(0)])
                    if set(t11.branches[FakePath(0, k)]) == {"m1", "m2"}]
assert len(interior_segs_r) == 2, interior_segs_r
m1_edge_r = [ln for ln in interior_segs_r if ln[1][0] == 3800.0][0]
m2_edge_r = [ln for ln in interior_segs_r if ln[1][0] == 4000.0][0]
assert sorted((m1_edge_r[1][1], m1_edge_r[2][1])) == [200.0, 7800.0], m1_edge_r
assert sorted((m2_edge_r[1][1], m2_edge_r[2][1])) == [0.0, 8000.0], m2_edge_r
m1_west_r = [ln for ln in b11t.branches[FakePath(0)]
             if ln[1][0] == ln[2][0] and ln[1][0] == 200.0]
assert len(m1_west_r) == 1, b11t.branches[FakePath(0)]
# The west PERIMETER run's own LENGTH (not just its position) must
# also trim to m1's new, shorter north/south extent (200-7800) -- m1
# is offset on ALL 4 sides here, so its west run should get shorter
# too, not stay at the full original 0-8000 span while only shifting
# sideways (a real bug: only the position was ever being adjusted,
# the length was silently left stale).
assert sorted((m1_west_r[0][1][1], m1_west_r[0][2][1])) == [200.0, 7800.0], m1_west_r
assert w11 == [], w11
print("OK -- RING m1/'*': ALL FOUR of m1's sides shrink independently, "
      "including the one facing sibling m2 -- m2 and its own child stay "
      "completely untouched, the shared border duplicates into m1's own "
      "edge (x=3800, shorter) and m2's own unchanged edge (x=4000, full "
      "length), and m1's west PERIMETER run is also trimmed to its new, "
      "shorter length (y=200-7800), not just shifted sideways\n")

# --- 11b) Same ring, but WITH an explicit side filter (['m1','*',
#     'Left']) -- narrows to just m1's west side (the true EXT edge);
#     north/south/east (including the m2-facing side) stay put.
a_ring2 = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
a_ring2["borderOverrides"] = [
    {"between": ["m1", "*", "Left"], "offset": -200.0}]
c11b, l11b, b11bt, t11b = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w11b = []
mod._emit(a_ring2, None, None, FakePlane(), FakePath(0), c11b, l11b, b11bt,
          t11b, w11b, {})
m1_rs, m2_rs = c11b.branches[FakePath(0)]
assert x_range(m1_rs) == (200.0, 4000.0), x_range(m1_rs)
assert y_range(m1_rs) == (0.0, 8000.0), y_range(m1_rs)
assert x_range(m2_rs) == (4000.0, 8000.0), x_range(m2_rs)
print("OK -- RING with an explicit side filter narrows to just that "
      "one side of the anchor space, same as it does for EXT\n")

# --- 12) LABEL LIST: 'm1,m2' as a single between item (no brackets --
#     that's the new bit; the old wall-override system needed
#     '[m1,m2]') expands to one RING override PER label -- both m1 AND
#     m2 independently shrink on every side they have, INCLUDING the
#     side they share with each other, each completely oblivious to
#     the other's shift (both anchors, neither is "the sibling" here).
room1c = leaf(["1fr"], ["1fr"], [["room1c"]], label="m1")
room2c = leaf(["1fr"], ["1fr"], [["room2c"]], label="m2")
a_list = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
a_list["childLayouts"] = [room1c, room2c]
a_list["borderOverrides"] = [{"between": ["m1,m2", "*"], "offset": -200.0}]
c12, l12, b12t, t12 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w12 = []
mod._emit(a_list, None, None, FakePlane(), FakePath(0), c12, l12, b12t, t12,
          w12, {})
m1_list, m2_list = c12.branches[FakePath(0)]
assert x_range(m1_list) == (200.0, 3800.0), x_range(m1_list)
assert x_range(m2_list) == (4200.0, 7800.0), x_range(m2_list)
room1c_curve = c12.branches[FakePath(0, 0)][0]
room2c_curve = c12.branches[FakePath(0, 1)][0]
assert x_range(room1c_curve) == (200.0, 3800.0), x_range(room1c_curve)
assert x_range(room2c_curve) == (4200.0, 7800.0), x_range(room2c_curve)
assert w12 == [], w12
# BOTH sides of this interior boundary diverge independently here (not
# a pair mechanism's mirrored move -- two SEPARATE ring overrides, one
# per label) -- m1's own edge lands at x=3800, m2's own edge at x=4200,
# a genuine 400mm GAP between them, matching their Cells shapes exactly.
interior_segs_12 = [ln for k, ln in enumerate(b12t.branches[FakePath(0)])
                     if set(t12.branches[FakePath(0, k)]) == {"m1", "m2"}]
assert len(interior_segs_12) == 2, interior_segs_12
m1_edge_12 = [ln for ln in interior_segs_12 if ln[1][0] == 3800.0][0]
m2_edge_12 = [ln for ln in interior_segs_12 if ln[1][0] == 4200.0][0]
assert sorted((m1_edge_12[1][1], m1_edge_12[2][1])) == [200.0, 7800.0], m1_edge_12
assert sorted((m2_edge_12[1][1], m2_edge_12[2][1])) == [200.0, 7800.0], m2_edge_12
print("OK -- LABEL LIST 'm1,m2' (no brackets) expands to a ring per "
      "label -- both m1 and m2 independently shrink on every side, "
      "each unaware of the other's shift, AND the interior border "
      "duplicates to match: m1's own edge at x=3800, m2's own edge at "
      "x=4200, a real 400mm gap between them, exactly like Cells\n")

# --- 12b) LABEL LIST on a PAIR's Between[0]: 'm1,m2' vs 'EXT' with a
#     'Left' filter -- expands to TWO pair overrides (['m1','EXT','L'],
#     ['m2','EXT','L']), each independently shrinking that space's own
#     west edge. m2 doesn't touch the west grid edge at all here, so
#     its own entry is silently skipped (no side filter given means
#     nothing to warn about -- wait, filter IS given: 'Left' -- so it
#     warns, same as any EXT+explicit-side mismatch would).
a_list2 = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
a_list2["borderOverrides"] = [
    {"between": ["m1,m2", "EXT", "Left"], "offset": -200.0}]
c12b, l12b, b12bt, t12b = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w12b = []
mod._emit(a_list2, None, None, FakePlane(), FakePath(0), c12b, l12b, b12bt,
          t12b, w12b, {})
m1_list2, m2_list2 = c12b.branches[FakePath(0)]
assert x_range(m1_list2) == (200.0, 4000.0), x_range(m1_list2)
assert x_range(m2_list2) == (4000.0, 8000.0), x_range(m2_list2)
assert any("doesn't touch the Left side" in w or "doesn't touch the L side" in w
           or "doesn't touch the" in w for w in w12b), w12b
print("OK -- a label list on a PAIR side ('m1,m2' vs 'EXT') expands "
      "to one pair override per label -- m1's west edge shrinks, m2 "
      "(which doesn't touch the west edge) is warned and skipped\n")

# --- 13) MULTI-SIDE filter: 'm1' / '*' (ring) / 'L,R' -- the reported
#     gap. m1 sits in a 2-col, 1-row grid (touches EXT on west, north,
#     AND south, plus sibling m2 on east). 'L,R' (no brackets, same
#     bare-comma vocabulary as a label list) narrows the ring to west
#     AND east only -- north/south (untouched by the filter) don't
#     move, even though m1 touches EXT there too.
a_multiside = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
a_multiside["borderOverrides"] = [
    {"between": ["m1", "*", "L,R"], "offset": -200.0}]
c13, l13, b13t, t13 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w13 = []
mod._emit(a_multiside, None, None, FakePlane(), FakePath(0), c13, l13, b13t,
          t13, w13, {})
m1_ms, m2_ms = c13.branches[FakePath(0)]
assert x_range(m1_ms) == (200.0, 3800.0), x_range(m1_ms)
assert y_range(m1_ms) == (0.0, 8000.0), y_range(m1_ms)   # N/S untouched
assert x_range(m2_ms) == (4000.0, 8000.0), x_range(m2_ms)
assert w13 == [], w13
print("OK -- multi-side filter 'L,R' (comma-separated, no brackets) "
      "narrows a ring to west+east only, leaving north/south (also "
      "touching EXT) untouched\n")

# --- 13b) Same multi-side filter grammar on an EXT match (not a
#     ring): a plain corner cell, 'T,L' -- only north+west move, the
#     corner's OTHER two sides (which it doesn't even touch) are
#     simply not part of the request, no warning.
corner_ms = leaf([1000.0, 1000.0], [1000.0, 1000.0],
                  [["corner", "x"], ["y", "z"]], label="g")
corner_ms["borderOverrides"] = [
    {"between": ["corner", "EXT", "T,L"], "offset": 50.0}]
c13b, l13b, b13bt, t13b = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w13b = []
mod._emit(corner_ms, None, None, FakePlane(), FakePath(0), c13b, l13b,
          b13bt, t13b, w13b, {})
corner_curve = c13b.branches[FakePath(0)][0]
assert x_range(corner_curve) == (-50.0, 1000.0), x_range(corner_curve)
assert y_range(corner_curve) == (1000.0, 2050.0), y_range(corner_curve)
assert w13b == [], w13b
print("OK -- multi-side filter also works on an EXT match, not just "
      "a ring -- 'T,L' extends north and west together\n")

# --- 14) EXT-anchored RING: ['EXT','*','L,R'] used to be a silent
#     no-op -- 'EXT' isn't a real space, so the ring's own literal-
#     label match (against sp['label']) never found anything, and
#     nothing warned either. Now it applies to EVERY space touching
#     the grid's own perimeter, each independently on just the
#     side(s) it actually touches. 1-row, 3-col grid: 'a' (west
#     column, touches West only), 'b' (middle, touches neither West
#     nor East), 'c' (east column, touches East only) -- 'L,R' filter
#     -> a's west edge and c's east edge each push out 100mm, b
#     (matching neither requested side) is untouched, no warning.
row3 = leaf([1000.0, 1000.0, 1000.0], [500.0], [["a", "b", "c"]])
row3["borderOverrides"] = [{"between": ["EXT", "*", "L,R"], "offset": 100.0}]
c14, l14, b14t, t14 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w14 = []
mod._emit(row3, None, None, FakePlane(), FakePath(0), c14, l14, b14t, t14,
          w14, {})
a_curve, b_curve, c_curve = c14.branches[FakePath(0)]
assert x_range(a_curve) == (-100.0, 1000.0), x_range(a_curve)
assert x_range(b_curve) == (1000.0, 2000.0), x_range(b_curve)
assert x_range(c_curve) == (2000.0, 3100.0), x_range(c_curve)
assert w14 == [], w14
print("OK -- EXT-anchored ring (['EXT','*','L,R'], order-insensitive "
      "with the '*') independently pushes out every space touching "
      "the requested side of the grid's own perimeter -- a's west "
      "edge and c's east edge both move, b (touching neither) is "
      "left alone, no warning\n")

# --- 14b) Same EXT ring, unfiltered ('*' or omitted 3rd item) -- 'a'
#     (a corner, touching West AND -- since this is a 1-row grid --
#     also North and South) moves on ALL of ITS OWN touching sides,
#     while 'b' (touching only N/S) moves on just those two, matching
#     the per-space "every side IT has" rule, not a fixed global set.
row3b = leaf([1000.0, 1000.0, 1000.0], [500.0], [["a", "b", "c"]])
row3b["borderOverrides"] = [{"between": ["*", "EXT"], "offset": 10.0}]
c14b, l14b, b14bt, t14b = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w14b = []
mod._emit(row3b, None, None, FakePlane(), FakePath(0), c14b, l14b, b14bt,
           t14b, w14b, {})
a_curve_b, b_curve_b, c_curve_b = c14b.branches[FakePath(0)]
assert x_range(a_curve_b) == (-10.0, 1000.0), x_range(a_curve_b)
assert y_range(a_curve_b) == (-10.0, 510.0), y_range(a_curve_b)
assert x_range(b_curve_b) == (1000.0, 2000.0), x_range(b_curve_b)
assert y_range(b_curve_b) == (-10.0, 510.0), y_range(b_curve_b)
assert x_range(c_curve_b) == (2000.0, 3010.0), x_range(c_curve_b)
assert w14b == [], w14b
print("OK -- unfiltered EXT ring ('*' first, 'EXT' second -- order "
      "doesn't matter) moves each space on every perimeter side IT "
      "individually has -- a's corner gets both W and N/S, b (no "
      "east/west edge) gets just N/S\n")

# --- 15) NON-RECTANGULAR merge + INDEPENDENT offset -- used to warn
#     ('...ignored for its own outline') and freeze at the un-offset
#     shape. 2x2 grid, 'el' occupies (0,0),(0,1),(1,0) -- an L missing
#     the (1,1) corner ('x') -- with an EXT ring filtered to West.
#     el's own west boundary is TWO separate grid edges (the (0,0) and
#     (1,0) cells' own west sides) that happen to be collinear, so
#     this also exercises the 'straight-through point' case in
#     _shift_outline_edges (the point where those two edges meet,
#     mid-run, isn't a real corner and must not get double-shifted).
#     Only the whole west run should move to x=-100; every other point
#     (north side, the inner notch corner, the east side) stays put.
l_grid = leaf([1000.0, 1000.0], [1000.0, 1000.0],
              [["el", "el"], ["el", "x"]])
l_grid["borderOverrides"] = [{"between": ["el", "EXT", "L"], "offset": 100.0}]
c15, l15, b15t, t15 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w15 = []
mod._emit(l_grid, None, None, FakePlane(), FakePath(0), c15, l15, b15t,
           t15, w15, {})
el_curve = [crv for crv, lbl in zip(c15.branches[FakePath(0)],
                                     l15.branches[FakePath(0)])
            if lbl == "el"][0]
el_points = set((p[0], p[1]) for p in el_curve[1])   # drop z, dedup the closing repeat
assert w15 == [], w15
assert el_points == {
    (1000.0, 2000.0), (-100.0, 2000.0), (-100.0, 1000.0), (-100.0, 0.0),
    (1000.0, 0.0), (1000.0, 1000.0), (2000.0, 1000.0), (2000.0, 2000.0),
}, el_points
print("OK -- a non-rectangular (L-shaped) merge now correctly shifts "
      "on an INDEPENDENT offset instead of warning and freezing: only "
      "the west-facing run moves to x=-100 (both of its underlying "
      "grid edges, meeting at a mid-run 'straight-through' point that "
      "isn't double-shifted), north/east/the inner notch corner all "
      "stay exactly where they were\n")

# --- 16) The reported bug: an EXT override on a non-rectangular merge
#     must NOT drag along an edge that's really facing a SIBLING, just
#     because it happens to share the requested direction. 4-row,
#     2-col grid:
#       s1,s1
#       k, s1
#       k, s2
#       s2,s2
#     s1 = {(0,0),(0,1),(1,1)}, s2 = {(2,1),(3,0),(3,1)} -- both
#     upside-down/right-side-up L's -- k = {(1,0),(2,0)}, a plain
#     rectangle. s1 and s2 both touch the grid's true West edge (row 0
#     / row 3) AND both have a SEPARATE west-tagged edge against k
#     (row 1 for s1, row 2 for s2) purely because k doesn't fill that
#     column there. An EXT override on s1+s2, filtered to Left, must
#     only push out the TRUE west edges -- the edges against k stay
#     exactly coincident with k's own (untouched) east side, so k's
#     boundary and s1/s2's stay joined with no gap.
grid_sk = leaf([1000.0, 1000.0], [1000.0, 1000.0, 1000.0, 1000.0],
               [["s1", "s1"], ["k", "s1"], ["k", "s2"], ["s2", "s2"]])
grid_sk["borderOverrides"] = [
    {"between": ["s1,s2", "EXT", "L"], "offset": 100.0}]
c16, l16, b16t, t16 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w16 = []
mod._emit(grid_sk, None, None, FakePlane(), FakePath(0), c16, l16, b16t,
           t16, w16, {})
by_label = dict(zip(l16.branches[FakePath(0)], c16.branches[FakePath(0)]))
s1_pts = set((p[0], p[1]) for p in by_label["s1"][1])
s2_pts = set((p[0], p[1]) for p in by_label["s2"][1])
k_curve = by_label["k"]
assert w16 == [], w16
assert x_range(k_curve) == (0.0, 1000.0), x_range(k_curve)
assert y_range(k_curve) == (1000.0, 3000.0), y_range(k_curve)
assert s1_pts == {
    (-100.0, 4000.0), (-100.0, 3000.0), (1000.0, 3000.0),
    (1000.0, 2000.0), (2000.0, 2000.0), (2000.0, 3000.0),
    (2000.0, 4000.0), (1000.0, 4000.0),
}, s1_pts
assert s2_pts == {
    (2000.0, 1000.0), (2000.0, 2000.0), (1000.0, 2000.0),
    (1000.0, 1000.0), (-100.0, 1000.0), (-100.0, 0.0),
    (1000.0, 0.0), (2000.0, 0.0),
}, s2_pts
print("OK -- the reported bug: an EXT override on s1/s2 (each a non-"
      "rectangular merge with its own real west edge AND a separate "
      "west-tagged edge against k) only pushes out the TRUE west "
      "edges (s1's row 0, s2's row 3) to x=-100 -- the edges each "
      "shares with k (s1's row 1, s2's row 2, both at x=1000) stay "
      "exactly where k's own untouched boundary is, so nothing gaps\n")

# --- 17) The SAME s1/k/s2 setup (test 16), but checking BORDERS
#     rather than Cells: a live-user-reported follow-on bug -- s1/s2's
#     RESTRICTED (EXT-only) west delta was leaking into their INTERIOR
#     boundary against k, via _own_side_of_interior's own bbox-edge
#     check (built only for the rectangular case, so it silently
#     defaulted to 'this must be my west edge' for a boundary that
#     isn't on EITHER of s1's/s2's true bbox edges at all). That wrong
#     shift made k's own (correctly untouched) edge and s1's/s2's own
#     (wrongly shifted) edge disagree, which the DUPLICATE INTERIOR
#     SEGMENTS mechanism then dutifully drew as TWO lines instead of
#     one -- an unnecessary duplicate, and at the WRONG position
#     (x=900) besides. Fixed: exactly one line each, still at x=1000,
#     matching k's own untouched boundary and s1's/s2's own (correctly
#     unmoved) Cells edge from test 16.
def _is_vertical(ln):
    return ln[1][0] == ln[2][0]


def _y_range(ln):
    ys = sorted((ln[1][1], ln[2][1]))
    return tuple(ys)


x1000_lines = [ln for ln in b16t.branches[FakePath(0)]
               if _is_vertical(ln) and ln[1][0] == 1000.0]
x900_lines = [ln for ln in b16t.branches[FakePath(0)]
              if _is_vertical(ln) and ln[1][0] == 900.0]
assert x900_lines == [], x900_lines
assert len(x1000_lines) == 2, x1000_lines
assert sorted(_y_range(ln) for ln in x1000_lines) == [
    (1000.0, 2000.0), (2000.0, 3000.0)], \
    sorted(_y_range(ln) for ln in x1000_lines)
print("OK -- the s1-vs-k and s2-vs-k INTERIOR boundaries are no "
      "longer wrongly dragged by s1's/s2's own RESTRICTED west delta "
      "(which only ever legitimately applies to their TRUE west edge, "
      "not this one) -- exactly one line each, still at x=1000, no "
      "phantom duplicate and no wrong position\n")

# --- 18) The FIRST fix attempt for test 17 (zeroing a space's entire
#     RESTRICTED delta before it ever reached _own_side_of_interior)
#     was too blunt -- it also suppressed a LEGITIMATE perpendicular
#     length-trim for the ordinary RECTANGULAR case, no non-rectangular
#     merge involved at all. Plain 2x2 grid, 'corner' (touches North
#     AND West) with an UNFILTERED EXT offset -50 (shrink): corner's
#     own east edge (shared with 'x') and south edge (shared with 'y')
#     must each still TRIM to match corner's own shrunk shape -- the
#     duplicate-interior-segments mechanism should draw corner's own
#     (trimmed) edge alongside its neighbour's own (unchanged) edge,
#     exactly like test 11's ring case already does, EXT or not.
corner2 = leaf(["1fr"], ["1fr"], [["cc3"]], label="corner")
grid_trim = leaf([1000.0, 1000.0], [1000.0, 1000.0],
                  [["corner", "x"], ["y", "z"]])
grid_trim["childLayouts"] = [corner2]
grid_trim["borderOverrides"] = [
    {"between": ["corner", "EXT"], "offset": -50.0}]
c18, l18, b18t, t18 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w18 = []
mod._emit(grid_trim, None, None, FakePlane(), FakePath(0), c18, l18, b18t,
           t18, w18, {})


def _x_of(ln):
    return ln[1][0] if ln[1][0] == ln[2][0] else None


def _y_of(ln):
    return ln[1][1] if ln[1][1] == ln[2][1] else None


ew_lines = [ln for ln in b18t.branches[FakePath(0)]
            if _x_of(ln) == 1000.0 and min(ln[1][1], ln[2][1]) >= 1000.0]
ns_lines = [ln for ln in b18t.branches[FakePath(0)]
            if _y_of(ln) == 1000.0 and min(ln[1][0], ln[2][0]) < 1000.0]
assert w18 == [], w18
assert sorted(_y_range(ln) for ln in ew_lines) == [
    (1000.0, 1950.0), (1000.0, 2000.0)], sorted(_y_range(ln) for ln in ew_lines)


def _x_range(ln):
    return tuple(sorted((ln[1][0], ln[2][0])))


assert sorted(_x_range(ln) for ln in ns_lines) == [
    (0.0, 1000.0), (50.0, 1000.0)], sorted(_x_range(ln) for ln in ns_lines)
print("OK -- an unfiltered EXT offset on a plain rectangular corner "
      "cell still correctly TRIMS both its interior boundaries: "
      "corner's own east edge shortens to y=1000-1950 (alongside x's "
      "own unchanged y=1000-2000), corner's own south edge shortens "
      "to x=50-1000 (alongside y's own unchanged x=0-1000) -- no "
      "regression from the restricted-delta fix above\n")

print("ALL OK")
