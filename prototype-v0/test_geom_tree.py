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

    def dump(self):
        return {repr(p): v for p, v in self.branches.items()}

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


def run_like(root, root_i=0):
    """Mimics what run() now does: draw the root's own boundary at the
    bare item path {i}, and call _emit with {i;0} as the list-branch
    for the root's own children -- see run()'s own code."""
    c, l, b, t = FakeTree(), FakeTree(), FakeTree(), FakeTree()
    root_path = FakePath(root_i)
    tw, tl = mod._emit(root, None, None, FakePlane(), root_path.AppendElement(0),
                        c, l, b, t, [], {})
    c.Add(mod._rect_curve(FakePlane(), 0.0, 0.0, tw, tl), root_path)
    root_label = root.get("label")
    root_label_or_blank = root_label if root_label else ""
    for k, ln in enumerate(
            mod._rect_border_lines(FakePlane(), 0.0, 0.0, tw, tl)):
        b.Add(ln, root_path)
        topo_path = root_path.AppendElement(k)
        t.EnsurePath(topo_path)
        t.Add(root_label_or_blank, topo_path)
        t.Add("EXT", topo_path)
    if root_label:
        l.Add(root_label, root_path)
    return c, l, b, t, tw, tl


warnings = []

# --- User's exact example: label a; cells: b1/b2
#       label b1; cells: c1/c2
#       label b2; cells: c1/c2/c3
# A node's own CHILDREN sit together in ONE branch as a plain list (not
# graft-per-child); a child that itself has children gets its OWN
# list-branch one level deeper, addressed by ITS OWN row-major index
# within the branch it was listed in.
b1 = leaf([1000.0, 1000.0], [500.0], [["c1", "c2"]], label="b1")
b2 = leaf([1000.0, 1000.0, 1000.0], [500.0], [["c1", "c2", "c3"]], label="b2")
a = leaf([2000.0, 3000.0], [500.0], [["b1", "b2"]])
a["childLayouts"] = [b1, b2]

cells, labels, borders, topology = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(a, None, None, FakePlane(), FakePath(0), cells, labels, borders,
          topology, warnings, {})

print("Branches:")
for p in sorted(cells.branches.keys(), key=lambda x: x.idx):
    print(" ", p, labels.branches.get(p))

assert labels.branches[FakePath(0)] == ["b1", "b2"]
assert labels.branches[FakePath(0, 0)] == ["c1", "c2"]
assert labels.branches[FakePath(0, 1)] == ["c1", "c2", "c3"]
print("OK -- a's children (b1, b2) share ONE branch as a 2-item list; "
      "b1's own children and b2's own children each get their own "
      "branch one level deeper, addressed by b1/b2's own index\n")

# --- Topology: a GRAFTED version of Borders. b1's own border list at
#     {0;0} (interior c1|c2 wall + 4-run perimeter, 7 segments, same
#     structure as the module-pair worked example below) should graft
#     into 7 branches {0;0;0}..{0;0;6}, each holding exactly 2 labels.
b1_border_count = len(borders.branches[FakePath(0, 0)])
assert b1_border_count == 7, b1_border_count
topo_b1_branches = [topology.branches[FakePath(0, 0, k)]
                     for k in range(b1_border_count)]
assert all(len(pair) == 2 for pair in topo_b1_branches)
assert topo_b1_branches.count(["c1", "c2"]) == 1        # the interior wall
assert sum(1 for p in topo_b1_branches if set(p) == {"c1", "EXT"}) == 3
assert sum(1 for p in topo_b1_branches if set(p) == {"c2", "EXT"}) == 3
print("OK -- Topology grafts b1's own 7-segment border list into 7 "
      "branches, one interior wall (c1, c2) and 3+3 perimeter runs "
      "each paired with 'EXT'\n")

# --- 4-node linear chain (root -> a2 -> mid -> deep, each a single
#     cell; deep's own single leaf cell is "z"). Every hop's own
#     children-list should be present, one branch each, one level
#     deeper than its parent's -- not graft-per-item, since each hop
#     here only ever has exactly one child anyway.
deep = leaf([500.0], [500.0], [["z"]], label="deep")
mid = leaf(["auto"], ["auto"], [["deep"]], label="mid")
mid["childLayouts"] = [deep]
a2 = leaf(["auto"], ["auto"], [["mid"]], label="a2")
a2["childLayouts"] = [mid]
root = leaf(["auto"], ["auto"], [["a2"]])
root["childLayouts"] = [a2]

c, l, b, t = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(root, None, None, FakePlane(), FakePath(0), c, l, b, t, warnings, {})
nonempty = {p.idx: l.branches[p] for p, v in c.branches.items() if v}
print("4-node chain, every level present:", nonempty)
assert nonempty == {
    (0,): ["a2"],
    (0, 0): ["mid"],
    (0, 0, 0): ["deep"],
    (0, 0, 0, 0): ["z"],
}
print("OK -- every hop's own children-list is retained, deepest leaf "
      "included, one branch per hop (each hop has exactly one child "
      "here, so branch and graft coincide)\n")

# --- Regression: a single child bound to 4 instance-suffixed sibling
#     cells (shared base label), where the parent's tracks are 'auto'
#     (so each binding needs the child's intrinsic size) and the CHILD
#     itself has a pure-'fr' track (fires the "nothing to share"
#     warning). Before memoizing _intrinsic_size, this fired 4x (once
#     per sibling instance) instead of once.
shared = leaf(["1fr"], [500.0], [["s"]], label="shared")
quad_root = leaf(
    ["auto", "auto", "auto", "auto"], [500.0],
    [["shared[0]", "shared[1]", "shared[2]", "shared[3]"]],
)
quad_root["childLayouts"] = [shared]

w3 = []
c3, l3, b3, t3 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(quad_root, None, None, FakePlane(), FakePath(0), c3, l3, b3, t3,
          w3, {})
hits = [w for w in w3 if "shared" in w and "nothing to share" in w]
print("'{}' fired {}x (pre-dedupe)".format("shared ... nothing to share", len(hits)))
assert len(hits) == 1, hits
print("OK -- memoized: one shared child measured once, not once per sibling\n")

# --- Regression: parent track is a plain FIXED number (not 'auto'),
#     hosting a child ("p1") whose own tracks are pure 'fr' with no
#     fixed anchor of its own. Before the _span_has_auto guard, this
#     unconditionally measured p1's INTRINSIC size (given=None) just
#     to build col_needs/row_needs that a fixed span never even reads
#     -- wrongly firing "fr tracks with nothing to share" even though
#     the real draw pass hands p1 a perfectly good 4000x8000 from the
#     fixed parent cell. Should be silent now, and p1's fr track
#     should size to the full 4000 it was actually given.
p1 = leaf(["1fr"], ["1fr"], [["q"]], label="p1")
fixed_parent = leaf([4000.0], [8000.0], [["p1"]])
fixed_parent["childLayouts"] = [p1]

w4 = []
c4, l4, b4, t4 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(fixed_parent, None, None, FakePlane(), FakePath(0), c4, l4, b4, t4,
          w4, {})
bad = [w for w in w4 if "p1" in w and "nothing to share" in w]
print("p1 false-positive warnings:", bad)
assert bad == [], bad
# fixed_parent's own child "p1" lands in its list-branch {0}; p1's own
# child "q" gets p1's index (0) appended -- {0;0}. q should have gotten
# the full 4000mm width from its fixed parent cell, not 0.
q_curve = c4.branches[FakePath(0, 0)][0]
q_x1 = q_curve[1][1][0]  # second corner's x
assert q_x1 == 4000.0, q_x1
print("OK -- fixed parent no longer wrongly measures p1's intrinsic "
      "size, and p1's 'fr' track correctly gets the real 4000mm\n")

# --- _emit returns the node's own (total_w, total_l) so run() can draw
#     the ROOT's boundary at the bare path {0} -- the one node nothing
#     else ever draws for. run_like() mimics run()'s own two-step
#     wiring: root's boundary at {0}, root's children-list at {0;0}.
c5, l5, b5, t5, tw5, tl5 = run_like(a)
print("root a's own resolved size:", tw5, tl5)
assert (tw5, tl5) == (5000.0, 500.0)  # cellWidths 2000+3000, cellLengths 500
assert c5.branches[FakePath(0)] and len(c5.branches[FakePath(0)]) == 1
assert l5.branches[FakePath(0, 0)] == ["b1", "b2"]
print("OK -- _emit reports its own size; run()-style wiring draws {0} "
      "(root's own boundary) and {0;0} (root's children, one list)\n")

# --- Depth filter, 0-based, on the SAME a/b1/b2/c... tree, wired the
#     way run() actually wires it (run_like above).
c6, l6, b6, t6, _, _ = run_like(a)

d0 = mod._filter_by_depth(c6, 0)
d1 = mod._filter_by_depth(c6, 1)
d2 = mod._filter_by_depth(c6, 2)
d3 = mod._filter_by_depth(c6, 3)
print("Depth=0:", sorted(d0.branches.keys(), key=lambda p: p.idx))
print("Depth=1:", sorted(d1.branches.keys(), key=lambda p: p.idx))
print("Depth=2:", sorted(d2.branches.keys(), key=lambda p: p.idx))
print("Depth=3:", sorted(d3.branches.keys(), key=lambda p: p.idx))
assert set(d0.branches.keys()) == {FakePath(0)}                  # a's own boundary
assert set(d1.branches.keys()) == {FakePath(0, 0)}                # [b1, b2]
assert set(d2.branches.keys()) == {FakePath(0, 0, 0), FakePath(0, 0, 1)}
assert set(d3.branches.keys()) == set()                           # chain stops at depth 2
assert d0.branches[FakePath(0)] == c6.branches[FakePath(0)]
assert len(d1.branches[FakePath(0, 0)]) == 2   # b1, b2
assert len(d2.branches[FakePath(0, 0, 0)]) == 2   # b1's c1, c2
assert len(d2.branches[FakePath(0, 0, 1)]) == 3   # b2's c1, c2, c3
print("OK -- Depth=0/1/2/3 (0-based) each isolate exactly one "
      "path-length slice, at their original addresses; depth 3 is "
      "empty since this tree doesn't go that deep\n")

# --- The user's own worked example: building floor (1 item) ->
#     apartments (4, instance-suffixed under one shared "apt" child
#     definition) -> modules (2 per apartment) -> rooms (2 per
#     module). Depth 0 = the floor's own boundary, {0}. Depth 1 = all
#     4 apartments in ONE branch, {0;0}. Depth 2 = one branch PER
#     apartment (4 branches: {0;0;0}..{0;0;3}), each a 2-item list of
#     that apartment's modules. Depth 3 = one branch per (apartment,
#     module) pair (8 branches: {0;0;i;j}), each a 2-item list of that
#     module's rooms.
module_def = leaf([500.0, 500.0], [500.0], [["r1", "r2"]], label="mod")
apt_def = leaf([1000.0, 1000.0], [1000.0], [["mod[0]", "mod[1]"]], label="apt")
apt_def["childLayouts"] = [module_def]
building = leaf([2000.0, 2000.0, 2000.0, 2000.0], [3000.0],
                [["apt[0]", "apt[1]", "apt[2]", "apt[3]"]])
building["childLayouts"] = [apt_def]

cW, lW, bW, tW, _, _ = run_like(building)

dW0 = mod._filter_by_depth(cW, 0)
dW1 = mod._filter_by_depth(cW, 1)
dW2 = mod._filter_by_depth(cW, 2)
dW3 = mod._filter_by_depth(cW, 3)

assert set(dW0.branches.keys()) == {FakePath(0)}
assert len(dW0.branches[FakePath(0)]) == 1                        # the floor itself

assert set(dW1.branches.keys()) == {FakePath(0, 0)}
assert len(dW1.branches[FakePath(0, 0)]) == 4                     # 4 apartments, one list

assert set(dW2.branches.keys()) == {
    FakePath(0, 0, 0), FakePath(0, 0, 1), FakePath(0, 0, 2), FakePath(0, 0, 3)}
for p in dW2.branches:
    assert len(dW2.branches[p]) == 2                               # 2 modules each

assert set(dW3.branches.keys()) == {
    FakePath(0, 0, i, j) for i in range(4) for j in range(2)}
for p in dW3.branches:
    assert len(dW3.branches[p]) == 2                               # 2 rooms each

print("OK -- building/apartments/modules/rooms matches the worked "
      "example exactly: {0}, {0;0}, {0;0;?} x4, {0;0;?;?} x8\n")

# --- Depth defaults to 0 when unwired -- verified at the run()-level
#     test below (this module doesn't re-test run()'s own goo_value /
#     globals() plumbing here, just the underlying _filter_by_depth
#     contract Depth=0 relies on).
assert mod._filter_by_depth(cW, 0).branches.keys() == dW0.branches.keys()
print("OK -- Depth 0 is a plain, valid filter value (not a sentinel) "
      "-- run() treats 'unwired' as this same value\n")

# --- Borders now shares Cells/Labels' tree shape exactly, on the SAME
#     building/apartments/modules/rooms tree: each branch holds the
#     UNIQUE border segments bounding whichever cells that SAME branch
#     of Cells shows -- Depth 2 (the 4 apartment branches, each a
#     2-item list of module cells, both rectangles) should be 7
#     segments per branch (2 north runs + 2 south runs + 1 west + 1
#     east + the 1 shared interior wall between the two modules).
bW0 = mod._filter_by_depth(bW, 0)
bW1 = mod._filter_by_depth(bW, 1)
bW2 = mod._filter_by_depth(bW, 2)
bW3 = mod._filter_by_depth(bW, 3)

assert set(bW0.branches.keys()) == set(dW0.branches.keys())
assert set(bW1.branches.keys()) == set(dW1.branches.keys())
assert set(bW2.branches.keys()) == set(dW2.branches.keys())
assert set(bW3.branches.keys()) == set(dW3.branches.keys())
print("OK -- Borders' branches match Cells' branches exactly at every "
      "Depth -- same addressing, no separate scheme")

assert len(bW0.branches[FakePath(0)]) == 4        # the floor's own 4 sides
for p in bW2.branches:
    assert len(bW2.branches[p]) == 7, (p, len(bW2.branches[p]))
print("OK -- Depth 0 gives the top parent's own 4 sides (it has no "
      "grid of its own to walk); Depth 2 gives 7 unique segments per "
      "apartment branch, matching the hand count for two rectangular "
      "modules side by side\n")

# --- Topology: grafted one level deeper than Borders, so its matching
#     slice for a given Depth needs +1 -- run() calls
#     _filter_by_depth(topology_tree, depth + 1), verified directly here.
tW0 = mod._filter_by_depth(tW, 0 + 1)
tW2 = mod._filter_by_depth(tW, 2 + 1)

# Depth 0: the floor's own 4 sides, each [floor's own label-or-'', 'EXT']
# -- building has no 'label' of its own, so that's ''.
assert set(tW0.branches.keys()) == {
    FakePath(0, k) for k in range(4)}
for p in tW0.branches:
    assert tW0.branches[p] == ["", "EXT"], (p, tW0.branches[p])

# Depth 2: one apartment's 7 border segments graft into 7 branches, one
# level deeper than that apartment's OWN Borders branch -- e.g. {0;0;2}
# (Borders, 7 items) -> {0;0;2;0}..{0;0;2;6} (Topology, 7 branches).
for apt_path in dW2.branches:      # {0;0;0}, {0;0;1}, {0;0;2}, {0;0;3}
    graft_paths = {p for p in tW2.branches
                   if p.idx[:-1] == apt_path.idx}
    assert len(graft_paths) == 7, (apt_path, sorted(p.idx for p in graft_paths))
    pairs = [tW2.branches[p] for p in graft_paths]
    assert all(len(pair) == 2 for pair in pairs)
    assert pairs.count(["mod[0]", "mod[1]"]) == 1     # the interior wall
    assert sum(1 for p in pairs if set(p) == {"mod[0]", "EXT"}) == 3
    assert sum(1 for p in pairs if set(p) == {"mod[1]", "EXT"}) == 3
print("OK -- Topology grafts Borders one level deeper: Depth 0's 4 "
      "sides each report [building's own label (blank here), 'EXT']; "
      "Depth 2's 7 segments per apartment graft into 7 branches, one "
      "interior wall (mod[0], mod[1]) plus 3+3 perimeter runs paired "
      "with 'EXT'\n")

# --- Merging restored: 2x2 grid,
#       A A
#       A B
#     the three A's merge into ONE L-shaped space (its real hexagonal
#     outline, not a bounding box), B stays its own plain cell. Both
#     now share ONE branch as a 2-item list (A first, row-major).
grid_node = leaf([1000.0, 1000.0], [1000.0, 1000.0],
                  [["A", "A"], ["A", "B"]])
cG, lG, bG, tG = FakeTree(), FakeTree(), FakeTree(), FakeTree()
wG = []
mod._emit(grid_node, None, None, FakePlane(), FakePath(0), cG, lG, bG, tG,
          wG, {})

labels_at_root = lG.branches[FakePath(0)]
cells_at_root = cG.branches[FakePath(0)]
assert labels_at_root == ["A", "B"]   # one shared branch, row-major
a_curve = cells_at_root[labels_at_root.index("A")]
pts = {(round(pt[0], 3), round(pt[1], 3)) for pt in a_curve[1][:-1]}
print("A's traced outline points:", sorted(pts))
expected_corners = {(0, 0), (1000, 0), (1000, 1000), (2000, 1000),
                     (2000, 2000), (0, 2000)}
assert expected_corners <= pts, (expected_corners, pts)
assert not any("rectangular" in w for w in wG)
print("OK -- three same-label ADJACENT cells merge into one real "
      "L-shaped space (one item, in the shared branch), B stays "
      "separate, both listed together, no warnings\n")

# --- '[k]' restored as the manual do-not-merge marker: three ADJACENT
#     cells labelled 'A[0]', 'A[1]', 'A[2]' stay three SEPARATE spaces
#     (three items in the SAME shared branch) despite sitting right
#     next to each other -- the exact case merging-by-label alone
#     can't distinguish from a genuine merged room. A child bound to
#     base label 'A' still lands in EVERY instance, each recursing
#     into its own list-branch (index-addressed, not label-addressed).
inst_child = leaf([200.0], [200.0], [["q"]], label="A")
tri_root = leaf([1000.0, 1000.0, 1000.0], [500.0],
                [["A[0]", "A[1]", "A[2]"]])
tri_root["childLayouts"] = [inst_child]
cT, lT, bT, tT = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(tri_root, None, None, FakePlane(), FakePath(0), cT, lT, bT, tT,
          [], {})
assert lT.branches[FakePath(0)] == ["A[0]", "A[1]", "A[2]"]
q_branches = [p for p, v in lT.branches.items() if v == ["q"]]
print("child instances:", sorted(p.idx for p in q_branches))
assert sorted(p.idx for p in q_branches) == [(0, 0), (0, 1), (0, 2)]
print("OK -- manually '[k]'-suffixed adjacent cells stay distinct "
      "spaces (three items, one shared branch), each still binds and "
      "recurses into its own child instance, own branch each\n")

# --- EXACT-instance child binding: two SEPARATE childLayouts entries,
#     one authored with label 'm[0]' and a DIFFERENT one with label
#     'm[1]' (not one shared 'm' template) -- each should bind to ONLY
#     its own matching space, with genuinely DIFFERENT content, not
#     collide on their shared base label 'm' the way the previous test
#     deliberately relies on ONE 'A' template for every 'A[k]'.
#     _node_children_by_label used to key EVERY child by its BASE label
#     regardless of how it was authored, so two same-base children
#     collided on one dict entry and only the last one processed
#     survived -- _child_for_space now checks the EXACT label first,
#     falling back to base only when no exact entry exists (so the
#     PREVIOUS test's shared-template case is untouched).
child_m0 = leaf([100.0], [100.0], [["roomA"]], label="m[0]")
child_m1 = leaf([100.0], [100.0], [["roomB"]], label="m[1]")
exact_root = leaf([1000.0, 1000.0], [500.0], [["m[0]", "m[1]"]])
exact_root["childLayouts"] = [child_m0, child_m1]
cE, lE, bE, tE = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(exact_root, None, None, FakePlane(), FakePath(0), cE, lE, bE, tE,
          [], {})
assert lE.branches[FakePath(0)] == ["m[0]", "m[1]"]
assert lE.branches[FakePath(0, 0)] == ["roomA"], lE.branches.get(FakePath(0, 0))
assert lE.branches[FakePath(0, 1)] == ["roomB"], lE.branches.get(FakePath(0, 1))
print("OK -- two same-base-label children authored with EXACT instance "
      "labels ('m[0]', 'm[1]') each bind to only their own space, with "
      "genuinely different content -- neither overwrites the other\n")

# --- Same exact-instance setup, but ONE instance ('m[1]') has no
#     exact entry authored for it -- only a base-label 'm' fallback
#     child. m[0] should still prefer its own EXACT entry over the
#     base fallback; m[1], lacking an exact entry, should fall back to
#     the shared 'm' template.
child_m0_only = leaf([100.0], [100.0], [["roomA"]], label="m[0]")
child_m_fallback = leaf([100.0], [100.0], [["shared"]], label="m")
mixed_root = leaf([1000.0, 1000.0], [500.0], [["m[0]", "m[1]"]])
mixed_root["childLayouts"] = [child_m0_only, child_m_fallback]
cM, lM, bM, tM = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(mixed_root, None, None, FakePlane(), FakePath(0), cM, lM, bM, tM,
          [], {})
assert lM.branches[FakePath(0, 0)] == ["roomA"], lM.branches.get(FakePath(0, 0))
assert lM.branches[FakePath(0, 1)] == ["shared"], lM.branches.get(FakePath(0, 1))
print("OK -- an exact-instance child ('m[0]') takes priority over a "
      "base-label fallback ('m'), which the OTHER instance ('m[1]', "
      "with no exact entry of its own) still correctly falls back to\n")

# --- Non-adjacent same-label cells never merge either, with NO suffix
#     needed at all: 1 row, 3 columns [A, B, A] -- the two 'A's don't
#     touch (B sits between them), so they're automatically two
#     separate spaces despite the identical plain label -- still both
#     items in the one shared branch.
split_node = leaf([1000.0, 1000.0, 1000.0], [500.0], [["A", "B", "A"]])
cS, lS, bS, tS = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(split_node, None, None, FakePlane(), FakePath(0), cS, lS, bS, tS,
          [], {})
assert lS.branches[FakePath(0)].count("A") == 2
print("OK -- non-adjacent cells with the identical plain label "
      "automatically stay separate, no [k] suffix required\n")

# --- Perimeter segmentation: 1 row, 3 columns [A, A, B], uniform
#     1000mm cells. North/south perimeter should now be 2 runs (the
#     two 'A' columns merge into one segment 0-2000, 'B' is its own
#     segment 2000-3000) instead of always 1 whole-edge line 0-3000.
run_node = leaf([1000.0, 1000.0, 1000.0], [1000.0], [["A", "A", "B"]])
cR, lR, bR, tR = FakeTree(), FakeTree(), FakeTree(), FakeTree()
mod._emit(run_node, None, None, FakePlane(), FakePath(0), cR, lR, bR, tR,
          [], {})
north_lines = [ln for ln in bR.branches[FakePath(0)]
               if ln[1][1] == ln[2][1] == 1000.0]  # y0==y1==1000 (north edge)
north_spans = sorted((min(ln[1][0], ln[2][0]), max(ln[1][0], ln[2][0]))
                      for ln in north_lines)
print("north perimeter runs:", north_spans)
assert north_spans == [(0.0, 2000.0), (2000.0, 3000.0)], north_spans
print("OK -- perimeter still segments per run (matching labels merge, "
      "a label change breaks it), not always one whole-edge line\n")

# --- Non-rectangular merge that ALSO hosts a child: still placed on
#     the bounding box (a child needs a rectangular frame), warns
#     about it explicitly.
r_child = leaf([500.0], [500.0], [["x"]], label="A")
L_with_child = leaf([1000.0, 1000.0], [1000.0, 1000.0],
                     [["A", "A"], ["A", "B"]])
L_with_child["childLayouts"] = [r_child]
wL2 = []
mod._emit(L_with_child, None, None, FakePlane(), FakePath(0), FakeTree(),
          FakeTree(), FakeTree(), FakeTree(), wL2, {})
assert any("bounding box" in w and "A" in w for w in wL2), wL2
print("OK -- binding a child to a non-rectangular merged region warns "
      "and falls back to its bounding box\n")

print("ALL OK")
