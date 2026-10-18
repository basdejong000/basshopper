"""Headless test of run()'s NEW list-of-items + plane-as-transform
behaviour. Only translation is modeled (no rotation) -- enough to
verify the COMPOSITION logic (identity default, per-item baked-in
plane, Geom.Plane applied on top of each) without a full 3D transform
engine."""
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
    .X/.Y/.Z -- _plane_from_dict constructs Plane(Point3d, Vector3d,
    Vector3d), tests construct Plane((x, y, z)) directly."""
    if hasattr(v, "X"):
        return v.X, v.Y, v.Z
    return v


class FakePlane:
    """Doubles as the 'rg.Plane' TYPE (so isinstance(...) works) and
    as an instance. Only translation is modeled in Transform -- no
    rotation math needed for these tests."""
    WorldXY = None  # set below, after the class exists

    def __init__(self, origin=(0.0, 0.0, 0.0), xaxis=(1.0, 0.0, 0.0),
                 yaxis=(0.0, 1.0, 0.0)):
        ox, oy, oz = _as_xyz(origin)
        xx, xy, xz = _as_xyz(xaxis)
        yx, yy, yz = _as_xyz(yaxis)
        self.Origin = Vec(ox, oy, oz)
        self.XAxis = Vec(xx, xy, xz)
        self.YAxis = Vec(yx, yy, yz)
        self.IsValid = True

    def PointAt(self, x, y, z):
        return (self.Origin.X + x, self.Origin.Y + y, self.Origin.Z + z)

    def Transform(self, xform):
        self.Origin = Vec(self.Origin.X + xform.dx, self.Origin.Y + xform.dy,
                           self.Origin.Z + xform.dz)
        return True


FakePlane.WorldXY = FakePlane((0.0, 0.0, 0.0))


class FakeTransformNS:
    def __init__(self, dx, dy, dz):
        self.dx, self.dy, self.dz = dx, dy, dz

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


class _GHPath:
    def __init__(self, *a):
        self._p = FakePath(*a)

    def __new__(cls, *a):
        return FakePath(*a)


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
    "geom",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms-layout-geom-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["geom"] = mod
spec.loader.exec_module(mod)

mod.rg = FakeRG
mod._HAS_RHINO = True
mod.gh = FakeGH()
mod.ghenv = FakeEnv()


def leaf(cw, cl, labels, label=None, plane=None):
    d = {"cellWidths": cw, "cellLengths": cl, "cellLabels": labels}
    if label:
        d["label"] = label
    if plane:
        d["plane"] = {"origin": list(plane), "xAxis": [1.0, 0.0, 0.0],
                       "yAxis": [0.0, 1.0, 0.0]}
    return d


# --- Single item, no baked-in plane, Geom.Plane unwired -> resolves
#     at WorldXY. Depth unwired now DEFAULTS to Depth 0 (the item's own
#     root boundary, {0}) -- "show everything" is no longer a mode, so
#     the plane-composition check reads off {0}, not the "x" cell's
#     own branch (which only appears at Depth 1 now).
node_a = leaf([1000.0], [1000.0], [["x"]])
mod.JSON = [json.dumps(node_a)]
mod.Plane = None
mod.Depth = None
# Cells/Borders now double as selector INPUTS too (see
# pms-layout-geom-v0.py's SELECTORS section) -- run() overwrites them
# with its OUTPUT at the end, same as every other ...JSON component
# here, so each run() call below explicitly resets both first; leaving
# a previous call's output FakeTree sitting in mod.Cells would
# otherwise be read back in as a (bogus) selector list next time.
mod.Cells = None
mod.Borders = None
mod.run()
print("single item, no plane anywhere, Depth unwired:",
      [(p.idx, c[0][1][0]) for p, c in mod.Cells.branches.items() if c])
assert set(mod.Cells.branches.keys()) == {FakePath(0)}
assert mod.Cells.branches[FakePath(0)][0][1][0] == (0.0, 0.0, 0.0)
print("OK -- single item with no baked-in plane and Geom.Plane unwired "
      "still resolves at WorldXY; Depth unwired shows only the item's "
      "own boundary (Depth 0), not every level at once\n")

# --- Same item, Depth explicitly wired to 1 -- now the "x" cell's own
#     list-branch, {0;0}, is what comes through.
mod.Depth = 1
mod.Cells = None
mod.Borders = None
mod.run()
assert set(mod.Cells.branches.keys()) == {FakePath(0, 0)}
assert mod.Cells.branches[FakePath(0, 0)][0][1][0] == (0.0, 0.0, 0.0)
print("OK -- Depth=1 surfaces the item's own children list, {0;0}\n")

# --- Topology wired end-to-end through run(): a single un-subdivided
#     cell "x" (no interior walls) has a 4-run perimeter, all touching
#     'x' and 'EXT' -- graft branches at {0;0;0}..{0;0;3}.
print("Topology at Depth=1:", sorted(mod.Topology.branches.keys(), key=lambda p: p.idx))
assert set(mod.Topology.branches.keys()) == {FakePath(0, 0, k) for k in range(4)}
for p, pair in mod.Topology.branches.items():
    assert set(pair) == {"x", "EXT"}, (p, pair)
print("OK -- run() wires Topology end-to-end: single-cell 'x' reports "
      "['x','EXT'] on all 4 of its perimeter runs\n")
mod.Depth = None

# --- Two items: item 0 has no baked-in plane, item 1 has one at
#     (500, 0, 0). Geom.Plane wired to (1000, 2000, 0) -- should
#     compose: item 0 -> (1000,2000,0), item 1 -> (1500,2000,0)
#     (its own 500 offset PLUS the geom transform, not replaced).
#     Checked via each item's own Depth-0 boundary rectangle.
node_b0 = leaf([100.0], [100.0], [["p"]])
node_b1 = leaf([100.0], [100.0], [["q"]], plane=(500.0, 0.0, 0.0))
mod.JSON = [json.dumps(node_b0), json.dumps(node_b1)]
mod.Plane = FakePlane((1000.0, 2000.0, 0.0))
mod.Cells = None
mod.Borders = None
mod.run()
item0_origin = mod.Cells.branches[FakePath(0)][0][1][0]
item1_origin = mod.Cells.branches[FakePath(1)][0][1][0]
print("item0 origin:", item0_origin, "| item1 origin:", item1_origin)
assert item0_origin == (1000.0, 2000.0, 0.0)
assert item1_origin == (1500.0, 2000.0, 0.0)
print("OK -- Geom.Plane composes with each item's own plane (or "
      "WorldXY) rather than replacing it, per item\n")

# --- Item ordering / addressing: item 1's own tree (its root boundary
#     at bare {1}, its one cell at {1;0}) sits entirely separate from
#     item 0's ({0}, {0;0}) -- never mixed together. Checked at Depth 0
#     (already run() above -> {0}, {1}) and again at Depth 1.
assert set(mod.Cells.branches.keys()) == {FakePath(0), FakePath(1)}
mod.Depth = 1
mod.Cells = None
mod.Borders = None
mod.run()
print("non-empty branches at Depth=1:", sorted(mod.Cells.branches.keys(), key=lambda p: p.idx))
assert set(mod.Cells.branches.keys()) == {FakePath(0, 0), FakePath(1, 0)}
mod.Depth = None
print("OK -- each item gets its own outer branch index at every depth, "
      "never mixed together\n")

print("ALL OK")
