"""Headless test of Geom's two SELECTOR inputs (Cells: label list,
Borders: Between-style selector, including the INT/EXT keywords and
multi-side/label-list grammar) against the SAME building / apartments
/ modules / rooms worked example used throughout the border-override
tests. These selectors used to live on a separate "Geom 2" component
(a self-contained duplicate of Geom's whole solve); this session
merged the two into one pms-layout-geom-v0.py, always outputting the
full Cells/Labels/Borders/Topology set with the selectors as purely
optional narrowing on top -- see that file's own module docstring."""
import importlib.util
import json
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


class Vec:
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z


class FakeXform:
    def __init__(self, dx, dy, dz):
        self.dx, self.dy, self.dz = dx, dy, dz


def _as_xyz(v):
    """Accept a plain (x, y, z) tuple or any Vec-like object with
    .X/.Y/.Z -- _emit constructs child planes from plane.XAxis/YAxis
    (already Vec-like), tests construct Plane((x, y, z)) directly."""
    if hasattr(v, "X"):
        return v.X, v.Y, v.Z
    return v


class FakePlane:
    WorldXY = None

    def __init__(self, origin=(0.0, 0.0, 0.0), xaxis=(1.0, 0.0, 0.0),
                 yaxis=(0.0, 1.0, 0.0)):
        self.Origin = Vec(*_as_xyz(origin))
        self.XAxis = Vec(*_as_xyz(xaxis))
        self.YAxis = Vec(*_as_xyz(yaxis))
        self.IsValid = True

    def PointAt(self, x, y, z):
        return (self.Origin.X + x, self.Origin.Y + y, self.Origin.Z + z)

    def Transform(self, xform):
        self.Origin = Vec(self.Origin.X + xform.dx, self.Origin.Y + xform.dy,
                           self.Origin.Z + xform.dz)
        return True


FakePlane.WorldXY = FakePlane((0.0, 0.0, 0.0))


class FakeTransformNS:
    @staticmethod
    def PlaneToPlane(p0, p1):
        return FakeXform(p1.Origin.X - p0.Origin.X, p1.Origin.Y - p0.Origin.Y,
                          p1.Origin.Z - p0.Origin.Z)


class FakeRG:
    Point3d = Vec
    Vector3d = Vec
    Plane = FakePlane
    Transform = FakeTransformNS

    @staticmethod
    def PolylineCurve(pts):
        return ("CURVE", tuple(pts))

    @staticmethod
    def Line(p0, p1):
        return ("LINE", p0, p1)


class _DataTreeFactory:
    def __getitem__(self, _t):
        return FakeTree


class FakeKernelData:
    GH_Path = staticmethod(lambda *a: FakePath(*a))


class _RuntimeLevel:
    Warning = "warning"
    Error = "error"


class FakeKernel:
    Data = FakeKernelData
    GH_RuntimeMessageLevel = _RuntimeLevel


class FakeGH:
    Kernel = FakeKernel
    DataTree = _DataTreeFactory()


class FakeComponent:
    def __init__(self):
        self.messages = []

    def ClearRuntimeMessages(self):
        self.messages = []

    def AddRuntimeMessage(self, level, text):
        self.messages.append((level, text))


class FakeEnv:
    def __init__(self):
        self.Component = FakeComponent()


spec = importlib.util.spec_from_file_location(
    "geom_selectors",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms-layout-geom-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["geom_selectors"] = mod
spec.loader.exec_module(mod)

mod.rg = FakeRG
mod._HAS_RHINO = True
mod.gh = FakeGH()
mod.ghenv = FakeEnv()


def leaf(cw, cl, labels, label=None):
    d = {"cellWidths": cw, "cellLengths": cl, "cellLabels": labels}
    if label:
        d["label"] = label
    return d


# Building floor (1 item) -> apartments (4, instance-suffixed) ->
# modules (2 per apartment, "mod[0]"/"mod[1]") -> rooms (2 per module)
# -- same tree as pms-layout-geom-v0.py's own worked-example tests.
module_def = leaf([500.0, 500.0], [500.0], [["r1", "r2"]], label="mod")
apt_def = leaf([1000.0, 1000.0], [1000.0], [["mod[0]", "mod[1]"]], label="apt")
apt_def["childLayouts"] = [module_def]
building = leaf([2000.0, 2000.0, 2000.0, 2000.0], [3000.0],
                [["apt[0]", "apt[1]", "apt[2]", "apt[3]"]])
building["childLayouts"] = [apt_def]

mod.JSON = [json.dumps(building)]
mod.Plane = None

# --- No selectors wired: Cells/Labels/Borders/Topology at Depth 2
#     should match the fully unfiltered output -- 4 branches, 2 cells
#     (and 2 labels, parallel) and 7 border segments each.
mod.Depth = 2
mod.Cells = None
mod.Borders = None
mod.run()
print("No selectors -- Cells branches:", sorted(mod.Cells.branches.keys(), key=lambda p: p.idx))
assert len(mod.Cells.branches) == 4
for p, items in mod.Cells.branches.items():
    assert len(items) == 2
    assert len(mod.Labels.branches[p]) == 2
for p, items in mod.Borders.branches.items():
    assert len(items) == 7
assert mod.Labels is not None and mod.Topology is not None
print("OK -- unwired selectors pass everything through unchanged, "
      "including Labels/Topology (reintroduced this session -- they'd "
      "been dropped entirely on the old separate Geom 2 component)\n")

# --- Cells selector: base label 'mod' should keep BOTH mod[0] and
#     mod[1] in every apartment branch (8 cells total, unchanged from
#     the unfiltered case, since 'mod' is EVERY cell at this depth).
#     NOTE: mod.Cells/mod.Borders double as BOTH input and output (same
#     pin names, like every other ...JSON component here) -- run()
#     OVERWRITES them with its output at the end, so each call below
#     explicitly resets BOTH before running, not just the one under
#     test, or the next call would iterate over a leftover FakeTree.
mod.Cells = ["mod"]
mod.Borders = None
mod.run()
total_cells = sum(len(v) for v in mod.Cells.branches.values())
assert total_cells == 8, total_cells
print("OK -- Cells=['mod'] (base label) matches every 'mod[k]' "
      "instance -- 8 cells across 4 branches\n")

# --- Cells selector: exact instance label 'mod[0]' should keep only
#     ONE cell per apartment branch (4 total) -- and Labels should stay
#     PARALLEL to that narrowed Cells output (same kept indices), not
#     just pass through the original unfiltered set.
mod.Cells = ["mod[0]"]
mod.Borders = None
mod.run()
total_cells = sum(len(v) for v in mod.Cells.branches.values())
assert total_cells == 4, total_cells
for p, items in mod.Cells.branches.items():
    assert len(items) == 1
    assert mod.Labels.branches[p] == ["mod[0]"], mod.Labels.branches[p]
print("OK -- Cells=['mod[0]'] (exact instance) keeps just that one "
      "cell per branch -- 4 total, and Labels stays parallel to the "
      "NARROWED Cells output, not the original unfiltered one\n")

# --- Borders selector: pair ['mod[0]','mod[1]'] should keep exactly
#     the ONE interior wall per apartment branch (4 total) -- and
#     Topology should stay parallel, reporting the SAME 2 labels for
#     that one kept border, re-addressed to index 0 in each branch.
mod.Cells = None
mod.Borders = ["mod[0]", "mod[1]"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 4, total_borders
for p, items in mod.Borders.branches.items():
    assert len(items) == 1
    pair = set(mod.Topology.branches[p.AppendElement(0)])
    assert pair == {"mod[0]", "mod[1]"}, pair
print("OK -- Borders=['mod[0]','mod[1]'] (pair) keeps the one shared "
      "interior wall per apartment -- 4 total, Topology re-addressed "
      "to the new index 0 and still reporting {mod[0], mod[1]}\n")

# --- Borders selector: ring ['mod[0]','*'] should keep every border
#     touching mod[0] -- the interior wall PLUS 3 perimeter runs (per
#     the earlier hand count: north, south, west) = 4 per branch, 16
#     total.
mod.Cells = None
mod.Borders = ["mod[0]", "*"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 16, total_borders
print("OK -- Borders=['mod[0]','*'] (ring) keeps every border "
      "touching mod[0] -- 4 per apartment, 16 total\n")

# --- Borders selector: global ['*','*'] should keep everything --
#     same as unwired, 7 per branch, 28 total.
mod.Cells = None
mod.Borders = ["*", "*"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 28, total_borders
print("OK -- Borders=['*','*'] (global) keeps every border -- 28 "
      "total, same as unfiltered\n")

# --- Borders selector: 'EXT' as a literal label -- ['mod[1]','EXT']
#     should keep mod[1]'s 3 perimeter runs (north, south, east) per
#     apartment, 12 total, and exclude the interior wall (which
#     touches mod[0], not EXT).
mod.Cells = None
mod.Borders = ["mod[1]", "EXT"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 12, total_borders
print("OK -- Borders=['mod[1]','EXT'] keeps mod[1]'s 3 perimeter "
      "runs per apartment -- 12 total\n")

# --- Selectors combine: Cells=['mod[0]'] AND Borders=['mod[0]','*']
#     both apply at once, independently, each to its own output (and
#     Labels/Topology ride along with each, respectively).
mod.Cells = ["mod[0]"]
mod.Borders = ["mod[0]", "*"]
mod.run()
assert sum(len(v) for v in mod.Cells.branches.values()) == 4
assert sum(len(v) for v in mod.Borders.branches.values()) == 16
assert sum(len(v) for v in mod.Labels.branches.values()) == 4
assert sum(len(v) for v in mod.Topology.branches.values()) == 16 * 2
print("OK -- Cells and Borders selectors apply independently, both at "
      "once, to their own respective outputs (Labels/Topology "
      "included)\n")


def x_range(curve):
    xs = [p[0] for p in curve[1]]
    return min(xs), max(xs)


# --- borderOverrides applies here regardless of the selectors (the
#     SAME solve/emit code Geom always used -- the selectors are a
#     pure narrowing pass afterward, see the module docstring).
#     apt_def's own module grid is SHARED across all 4 apartments
#     (bound via base label "apt"), so adding an override there
#     affects EVERY apartment at once. NOTE: module_def (base label
#     "mod") is bound to BOTH mod[0] and mod[1] here (both match the
#     base label), so this is the INDEPENDENT (both-children)
#     mechanism, not the SHARED one -- offset 100 makes each extend
#     toward the other by the FULL amount: mod[0] grows to (0,1100),
#     mod[1] grows to (900,2000), a 200mm overlap.
apt_def["borderOverrides"] = [{"between": ["mod[0]", "mod[1]"], "offset": 100.0}]
mod.JSON = [json.dumps(building)]   # re-serialize -- mod.JSON above was a
                                     # snapshot taken before this mutation
mod.Cells = None
mod.Borders = None
mod.Depth = 2
mod.run()
for path, curves in mod.Cells.branches.items():
    mod0_curve, mod1_curve = curves
    mod0_lo, mod0_hi = x_range(mod0_curve)
    mod1_lo, mod1_hi = x_range(mod1_curve)
    # Absolute coordinates differ per apartment (each sits at a
    # different offset along the building), so check WIDTH and the
    # overlap between them rather than fixed absolute numbers.
    assert mod0_hi - mod0_lo == 1100.0, (path, mod0_lo, mod0_hi)
    assert mod1_hi - mod1_lo == 1100.0, (path, mod1_lo, mod1_hi)
    assert mod0_hi - mod1_lo == 200.0, (path, mod0_hi, mod1_lo)
print("OK -- borderOverrides applies here just like it always did: "
      "mod[0]/mod[1] overlap by 200mm in every apartment\n")

# --- RING mode: ['mod[0]','*'], Offset 100 grows ONLY mod[0] (width
#     1000 -> 1200, extending equally on both the EXT west side AND
#     the side facing mod[1]) while mod[1] stays COMPLETELY untouched
#     -- the "independent, sibling never moves" rule.
apt_def["borderOverrides"] = [{"between": ["mod[0]", "*"], "offset": 100.0}]
mod.JSON = [json.dumps(building)]
mod.Cells = None
mod.Borders = None
mod.Depth = 2
mod.run()
for path, curves in mod.Cells.branches.items():
    mod0_curve, mod1_curve = curves
    mod0_lo, mod0_hi = x_range(mod0_curve)
    mod1_lo, mod1_hi = x_range(mod1_curve)
    assert mod0_hi - mod0_lo == 1200.0, (path, mod0_lo, mod0_hi)
    assert mod1_hi - mod1_lo == 1000.0, (path, mod1_lo, mod1_hi)
print("OK -- RING mode: mod[0] grows on every side (including the one "
      "facing mod[1]) while mod[1] stays completely untouched\n")

# --- MULTI-SIDE filter (comma list, no brackets): ['mod[0]','*','L,R']
#     narrows the ring to west+east only -- mod[0] still grows on both
#     (200mm total, same as the unfiltered ring test above, since W/E
#     were the only sides that mattered there anyway) but this
#     confirms the multi-side parsing itself works.
apt_def["borderOverrides"] = [
    {"between": ["mod[0]", "*", "L,R"], "offset": 100.0}]
mod.JSON = [json.dumps(building)]
mod.Cells = None
mod.Borders = None
mod.Depth = 2
mod.run()
for path, curves in mod.Cells.branches.items():
    mod0_curve, mod1_curve = curves
    mod0_lo, mod0_hi = x_range(mod0_curve)
    mod1_lo, mod1_hi = x_range(mod1_curve)
    assert mod0_hi - mod0_lo == 1200.0, (path, mod0_lo, mod0_hi)
    assert mod1_hi - mod1_lo == 1000.0, (path, mod1_lo, mod1_hi)
print("OK -- multi-side filter 'L,R' (comma, no brackets) parses and "
      "applies\n")

# --- Borders=['INT','*'] (ring form, mirroring the already-working
#     ['EXT','*'] for "the whole perimeter") selects every INTERIOR
#     border -- neither side EXT -- without having to name r1/r2
#     explicitly. At Depth 3 (r1/r2 level, one level inside each of
#     the 8 mod[k] instances -- 4 apartments x 2 mods each, since
#     module_def is bound to base label 'mod' and matches BOTH), each
#     mod's own little 2-cell grid has exactly 7 border segments (6
#     perimeter runs since r1/r2 have different labels + 1 interior
#     wall between them) -- so INT should keep exactly 1 per branch,
#     8 total, and EXT (the complement) the other 6 per branch, 48
#     total; together they account for all 56 (8 x 7).
mod.Cells = None
mod.Borders = ["INT", "*"]
mod.Depth = 3
mod.run()
assert len(mod.Borders.branches) == 8, mod.Borders.branches.keys()
for p, items in mod.Borders.branches.items():
    assert len(items) == 1, (p, items)
int_total = sum(len(v) for v in mod.Borders.branches.values())
assert int_total == 8, int_total
print("OK -- Borders=['INT','*'] selects exactly the interior wall in "
      "each mod's own r1/r2 grid -- 1 per branch, 8 total\n")

mod.Cells = None
mod.Borders = ["EXT", "*"]
mod.run()
ext_total = sum(len(v) for v in mod.Borders.branches.values())
assert ext_total == 48, ext_total
assert int_total + ext_total == 56, (int_total, ext_total)
print("OK -- INT and EXT (the complementary ring keywords) partition "
      "every border with no overlap and no gap: 8 + 48 = 56\n")

# =====================================================================
# Borders selector now matches borderOverrides' own Between grammar in
# full: label lists (comma, no brackets) on either side, AND a working
# side filter (single or comma-list of sides) -- previously parsed but
# never applied. Cells selector also gained comma label lists. Back to
# the apartment level (Depth 2, mod[0]/mod[1]) for these.
# =====================================================================
mod.Depth = 2

# --- Cells selector: a comma label list in ONE item, 'mod[0],mod[1]',
#     matches EITHER -- same result as unfiltered (8 total) here since
#     there are only 2 distinct cells per branch, but this still proves
#     the comma actually splits (if it didn't, the literal string
#     'mod[0],mod[1]' would match neither real label, giving 0).
mod.Cells = ["mod[0],mod[1]"]
mod.Borders = None
mod.run()
total_cells = sum(len(v) for v in mod.Cells.branches.values())
assert total_cells == 8, total_cells
print("OK -- Cells=['mod[0],mod[1]'] (comma list, no brackets) matches "
      "either label -- 8 total, proving the split actually happened\n")

# --- Cells selector: a bogus label alongside a real one in the SAME
#     list, 'bogus,mod[0]' -- only the real one contributes, 4 total,
#     confirming the list isn't just matching everything by accident.
mod.Cells = ["bogus,mod[0]"]
mod.Borders = None
mod.run()
total_cells = sum(len(v) for v in mod.Cells.branches.values())
assert total_cells == 4, total_cells
print("OK -- Cells=['bogus,mod[0]'] only matches the real label in the "
      "list -- 4 total, not 8\n")

# --- Borders selector: a comma label list as Between[0], 'mod[0],
#     mod[1]', paired against 'EXT' -- matches EVERY perimeter run
#     touching EITHER mod[0] OR mod[1] (6 of the 7 per branch, all but
#     the 1 shared interior wall) -- 24 total.
mod.Cells = None
mod.Borders = ["mod[0],mod[1]", "EXT"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 24, total_borders
print("OK -- Borders=['mod[0],mod[1]','EXT'] (label list vs EXT) keeps "
      "every perimeter run touching either -- 24 total (all but the "
      "shared interior wall)\n")

# --- Borders selector SIDE FILTER, ring form on a REAL anchor:
#     ['mod[0]','*','Left'] -- mod[0] touches N/S/W (3 perimeter runs);
#     narrowing to Left (W) keeps just 1 per branch, 4 total. (Input
#     vocabulary is Top/Bottom/Left/Right or T/B/L/R -- N/S/E/W are
#     only the INTERNAL codes, never typed directly.)
mod.Cells = None
mod.Borders = ["mod[0]", "*", "Left"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 4, total_borders
print("OK -- Borders=['mod[0]','*','Left'] (ring + side filter) keeps "
      "just mod[0]'s west perimeter run -- 4 total\n")

# --- Borders selector SIDE FILTER, EXT-pair form with a MULTI-side
#     list: ['mod[1]','EXT','Top,Bottom'] -- mod[1] touches N/S/E;
#     narrowing to Top,Bottom (N,S) keeps 2 of its 3 perimeter runs
#     (excludes east) -- 8 total.
mod.Cells = None
mod.Borders = ["mod[1]", "EXT", "Top,Bottom"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 8, total_borders
print("OK -- Borders=['mod[1]','EXT','Top,Bottom'] (EXT-pair + "
      "multi-side filter) keeps north+south, excludes east -- 8 "
      "total\n")

# --- Borders selector: a PLAIN pair of two real spaces (neither EXT)
#     with a side filter given -- ['mod[0]','mod[1]','Left'] --
#     borderOverrides never references `side` for this exact case (it
#     only matters for the SHARED/independent-both-children mechanism's
#     own EXT/ring paths), so the filter is BYPASSED here, not applied:
#     still finds the one shared interior wall per apartment (4 total),
#     NOT silently zero (an interior segment's own stored side is
#     always None, so a naive "side must match" check would exclude
#     everything -- this confirms the bypass fix works). Clears the
#     leftover ring override from the multi-side-filter test above
#     first -- otherwise mod[0]'s own independent offset would DIVERGE
#     this same interior boundary (see the DUPLICATE INTERIOR SEGMENTS
#     mechanism), doubling the count to 8 and testing the wrong thing.
apt_def["borderOverrides"] = []
mod.JSON = [json.dumps(building)]
mod.Cells = None
mod.Borders = ["mod[0]", "mod[1]", "Left"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 4, total_borders
print("OK -- a plain two-real-space pair BYPASSES an irrelevant side "
      "filter (matches borderOverrides' own precedent) instead of "
      "silently excluding everything -- still 4 total\n")

# --- Borders selector: INT + a side filter -- ['INT','*','Left'] --
#     has no clean meaning (an interior segment's side is always None,
#     so "which side" doesn't apply to it the way it does a perimeter
#     run) -- warned and the filter dropped, still selecting every
#     interior wall (same 8 total as the unfiltered INT test above),
#     at Depth 3 where that scenario lives.
mod.Depth = 3
mod.Cells = None
mod.Borders = ["INT", "*", "Left"]
mod.run()
total_borders = sum(len(v) for v in mod.Borders.branches.values())
assert total_borders == 8, total_borders
assert any("no effect on an INT match" in text
           for _level, text in mod.ghenv.Component.messages), \
    mod.ghenv.Component.messages
print("OK -- Borders=['INT','*','Left'] warns that a side filter has "
      "no effect on INT, and drops it rather than silently returning "
      "nothing -- still 8 total\n")
mod.Depth = 2

print("ALL OK")
