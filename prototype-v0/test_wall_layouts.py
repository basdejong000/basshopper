"""Headless test of WALL LAYOUTS -- an upright child hosted on a
border (see pms-layout-geom-v0.py's module docstring, WALL LAYOUTS
section): plane construction (origin, direction, outward-pointing
normal), CellWidths=['auto'] substitution with the matched border's
own actual length, and Phase-1's "diverged boundary -> warn and skip"
behaviour. Unlike the OTHER headless tests, this one needs a Plane
fake that actually RESPECTS XAxis/YAxis in PointAt (a true local-to-
world transform, not just translation) -- otherwise there's no way to
verify the wall's own geometry lands in the right WORLD position."""
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


class Vec:
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z

    def __repr__(self):
        return "Vec({:.3f}, {:.3f}, {:.3f})".format(self.X, self.Y, self.Z)


def _xyz(v):
    if hasattr(v, "X"):
        return v.X, v.Y, v.Z
    return v[0], v[1], v[2]


class FakePlane:
    """A TRUE local-to-world plane -- PointAt actually applies
    Origin + x*XAxis + y*YAxis + z*(XAxis x YAxis), unlike the
    translation-only fakes the other test files use (which are fine
    for THEIR purposes -- verifying Geom.Plane composition -- but
    can't verify that a wall's own geometry lands in the right WORLD
    position, which is the whole point of this test file)."""
    WorldXY = None

    def __init__(self, origin=(0.0, 0.0, 0.0), xaxis=(1.0, 0.0, 0.0),
                 yaxis=(0.0, 1.0, 0.0)):
        ox, oy, oz = _xyz(origin)
        xx, xy, xz = _xyz(xaxis)
        yx, yy, yz = _xyz(yaxis)
        self.Origin = Vec(ox, oy, oz)
        self.XAxis = Vec(xx, xy, xz)
        self.YAxis = Vec(yx, yy, yz)
        self.IsValid = True

    def PointAt(self, x, y, z):
        ox, oy, oz = _xyz(self.Origin)
        xx, xy, xz = _xyz(self.XAxis)
        yx, yy, yz = _xyz(self.YAxis)
        zx, zy, zz = (xy * yz - xz * yy, xz * yx - xx * yz, xx * yy - xy * yx)
        return (ox + x * xx + y * yx + z * zx,
                oy + x * xy + y * yy + z * zy,
                oz + x * xz + y * yz + z * zz)

    def Transform(self, xform):
        self.Origin = Vec(self.Origin.X + xform.dx, self.Origin.Y + xform.dy,
                           self.Origin.Z + xform.dz)
        return True


FakePlane.WorldXY = FakePlane((0.0, 0.0, 0.0))


class FakeXform:
    def __init__(self, dx, dy, dz):
        self.dx, self.dy, self.dz = dx, dy, dz


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


spec = importlib.util.spec_from_file_location(
    "geom_walls",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms-layout-geom-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["geom_walls"] = mod
spec.loader.exec_module(mod)

mod.rg = FakeRG
mod._HAS_RHINO = True
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


def z_range(curve):
    zs = [p[2] for p in curve[1]]
    return min(zs), max(zs)


def run_emit(node, plane=None):
    c, l, b, t = FakeTree(), FakeTree(), FakeTree(), FakeTree()
    mod._emit(node, None, None, plane or FakePlane(), FakePath(0), c, l, b, t,
              [], {})
    return c, l, b, t


# --- 1) The worked example: apartment 'a', modules m1/m2 side by
#     side, a wall layout on the border between them, NO offset (plain
#     boundary, no divergence). m1 = (0,0)-(4000,8000), m2 =
#     (4000,0)-(8000,8000) in local coords -- the shared boundary is
#     VERTICAL, at x=4000, spanning the FULL y=0-8000. m1's own EAST
#     edge is this boundary (rect_of(m1).x1 == 4000), so per
#     _wall_plane_axes: origin = SOUTH end (4000,0), direction toward
#     the NORTH end (4000,8000) -- wall X-axis = world +Y, wall Y-axis
#     = parent's own up (world +Z here, WorldXY parent). Normal =
#     X x Y = (+Y) x (+Z) = +X -- pointing AWAY from m1 (which sits on
#     the -X side of x=4000), matching PMS-R7's own outward convention.
room1 = leaf(["1fr"], ["1fr"], [["room1"]], label="m1")
room2 = leaf(["1fr"], ["1fr"], [["room2"]], label="m2")
apt = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
apt["childLayouts"] = [room1, room2]
wall = {"cellWidths": ["auto"], "cellLengths": [2700.0],
        "cellLabels": [["wallface"]]}
apt["borderOverrides"] = [{"between": ["m1", "m2"], "wallLayout": wall}]
c1, l1, b1t, t1 = run_emit(apt)

# The wall's own branch is {0;WALL_K} -- wall_k starts at 0, same
# ordinary counter cell-hosted children use (no disjoint-numbering
# trick -- see the module docstring). m1 is cell index 0, so the wall
# (the only thing hosted at THIS boundary) lands at index 0 TOO --
# sharing that branch address with m1's own child ('room1') rather
# than colliding is exactly what we agreed: disambiguated by label,
# not by branch position (see the WALL LAYOUTS output-addressing
# discussion) -- confirmed here by finding BOTH labels in one branch.
assert l1.branches[FakePath(0, 0)] == ["room1", "wallface"], \
    l1.branches.get(FakePath(0, 0))
wall_curve = [crv for crv, lbl in zip(c1.branches[FakePath(0, 0)],
                                       l1.branches[FakePath(0, 0)])
              if lbl == "wallface"][0]
assert x_range(wall_curve) == (4000.0, 4000.0), x_range(wall_curve)
assert y_range(wall_curve) == (0.0, 8000.0), y_range(wall_curve)
assert z_range(wall_curve) == (0.0, 2700.0), z_range(wall_curve)
print("OK -- wall layout on the plain m1/m2 boundary lands as a "
      "vertical rectangle at x=4000, spanning the full y=0-8000 "
      "(the border's own length) and z=0-2700 (its authored height)\n")

# --- 2) The plane's own normal points OUTWARD from m1 (away from it,
#     toward m2's side) -- same convention PMS-R7 already uses
#     (pms-generate-assemblies.py's _wall_geom: normals point out of
#     the plan). Verified via the actual constructed plane: XAxis
#     should be world +Y (along the boundary, south->north), YAxis
#     world +Z (up), giving normal = XAxis x YAxis = +X (away from m1,
#     which sits on the -X side of this boundary).
wall_plane = mod._upright_plane_from(FakePlane(), (4000.0, 0.0), (4000.0, 8000.0))
assert (wall_plane.XAxis.X, wall_plane.XAxis.Y, wall_plane.XAxis.Z) == (0.0, 1.0, 0.0), \
    wall_plane.XAxis
assert (wall_plane.YAxis.X, wall_plane.YAxis.Y, wall_plane.YAxis.Z) == (0.0, 0.0, 1.0), \
    wall_plane.YAxis
nx = wall_plane.XAxis.Y * wall_plane.YAxis.Z - wall_plane.XAxis.Z * wall_plane.YAxis.Y
ny = wall_plane.XAxis.Z * wall_plane.YAxis.X - wall_plane.XAxis.X * wall_plane.YAxis.Z
nz = wall_plane.XAxis.X * wall_plane.YAxis.Y - wall_plane.XAxis.Y * wall_plane.YAxis.X
assert (nx, ny, nz) == (1.0, 0.0, 0.0), (nx, ny, nz)
print("OK -- the wall's own plane normal (XAxis x YAxis) points "
      "+X -- away from m1, which sits on the -X side of the shared "
      "boundary -- matching PMS-R7's own outward-normal convention\n")

# --- 3) CellWidths=['auto'] gets substituted with the border's own
#     actual length -- 8000.0 here, matching the boundary's full span
#     (unaffected by anything, since this override carries no Offset).
#     Confirmed indirectly by test 1's own y-range already (8000mm
#     wide once mapped through the wall's own plane), but check it
#     explicitly against the wall's own resolved document too via a
#     second cell to make the width-substitution mechanism obvious.
wall2 = {"cellWidths": ["auto"], "cellLengths": [1000.0, 1000.0],
         "cellLabels": [["a"], ["b"]]}
apt2 = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
apt2["borderOverrides"] = [{"between": ["m1", "m2"], "wallLayout": wall2}]
c2, l2, b2t, t2 = run_emit(apt2)
a_curve = [crv for crv, lbl in zip(c2.branches[FakePath(0, 0)],
                                    l2.branches[FakePath(0, 0)])
           if lbl == "a"][0]
b_curve = [crv for crv, lbl in zip(c2.branches[FakePath(0, 0)],
                                    l2.branches[FakePath(0, 0)])
           if lbl == "b"][0]
assert y_range(a_curve) == (0.0, 8000.0), y_range(a_curve)  # full width, both rows
assert y_range(b_curve) == (0.0, 8000.0), y_range(b_curve)
# row 0 ('a') is the HIGHER side (same "row 0 = the higher-coordinate
# end" convention a floor plan's own row 0 = North already uses --
# here the wall's own local Y means height, not north, but the same
# rule applies), row 1 ('b') the lower.
assert z_range(a_curve) == (1000.0, 2000.0), z_range(a_curve)
assert z_range(b_curve) == (0.0, 1000.0), z_range(b_curve)
print("OK -- CellWidths=['auto'] is substituted with the border's own "
      "actual length (8000mm), and CellLengths (authored normally) "
      "correctly stacks as the wall's own height\n")

# --- 4) A DIVERGED boundary (independent offset moved one side) warns
#     and SKIPS wall-layout placement -- Phase 1 doesn't guess at the
#     mirrored two-instance geometry yet.
room1r = leaf(["1fr"], ["1fr"], [["room1r"]], label="m1")
room2r = leaf(["1fr"], ["1fr"], [["room2r"]], label="m2")
apt3 = leaf([4000.0, 4000.0], [8000.0], [["m1", "m2"]], label="a")
apt3["childLayouts"] = [room1r, room2r]
apt3["borderOverrides"] = [
    {"between": ["m1", "*"], "offset": -200.0},
    {"between": ["m1", "m2"], "wallLayout": dict(wall)},
]
c3, l3, b3t, t3 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w3 = []
mod._emit(apt3, None, None, FakePlane(), FakePath(0), c3, l3, b3t, t3, w3, {})
assert FakePath(0, 0) not in c3.branches or not any(
    lbl == "wallface" for lbl in l3.branches.get(FakePath(0, 0), [])), \
    l3.branches.get(FakePath(0, 0))
assert any("diverged" in w for w in w3), w3
print("OK -- a diverged boundary (m1 independently offset via a "
      "ring) warns and skips wall-layout placement instead of "
      "guessing at the mirrored geometry\n")

# --- 5) SIDE FILTER on a wall-layout match -- used to be silently
#     ignored (the loop discarded it as `_wside`), so an EXT override
#     like ['m','EXT','T,B'] would ALSO place a wall on any OTHER
#     side that module happened to touch EXT on, not just Top/Bottom.
#     1x3 grid, m[0]/m[1]/m[2] side by side: every module touches
#     BOTH North and South (the grid is one row tall), m[0] ALSO
#     touches West, m[2] ALSO touches East. An EXT override filtered
#     to 'T,B' (-> N/S) should place exactly 6 walls (each module's
#     own N and S) and SKIP m[0]'s West / m[2]'s East entirely.
#     A SEPARATE override, Between=['m','m','L,R'] (same base label on
#     BOTH sides -- matches via base-label equivalence, no ring
#     needed), should place exactly 2 walls, one per interior m-to-m
#     boundary (m[0]|m[1] and m[1]|m[2]), both genuinely W/E-facing so
#     the L,R filter doesn't exclude either.
row3m = leaf([2000.0, 2000.0, 2000.0], [3000.0],
             [["m[0]", "m[1]", "m[2]"]])
ext_wall = {"cellWidths": ["auto"], "cellLengths": [500.0],
            "cellLabels": [["extwall"]]}
int_wall = {"cellWidths": ["auto"], "cellLengths": [500.0],
            "cellLabels": [["intwall"]]}
row3m["borderOverrides"] = [
    {"between": ["m", "EXT", "T,B"], "wallLayout": ext_wall},
    {"between": ["m", "m", "L,R"], "wallLayout": int_wall},
]
c5, l5, b5t, t5 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w5 = []
mod._emit(row3m, None, None, FakePlane(), FakePath(0), c5, l5, b5t, t5,
          w5, {})
ext_count = sum(l5.branches[p].count("extwall") for p in l5.Paths
                if p.Length == 2 and p.idx[0] == 0)
int_count = sum(l5.branches[p].count("intwall") for p in l5.Paths
                if p.Length == 2 and p.idx[0] == 0)
assert w5 == [], w5
assert ext_count == 6, ext_count
assert int_count == 2, int_count
print("OK -- side filtering now actually applies to wall-layout "
      "matches: an EXT override filtered to Top/Bottom places exactly "
      "6 walls (each of the 3 modules' own North+South), correctly "
      "skipping m[0]'s West and m[2]'s East even though both ALSO "
      "touch EXT; a same-base pair ['m','m'] (no ring needed) matches "
      "BOTH interior m-to-m boundaries at once, 2 more walls\n")

# --- 6) RING support -- used to warn and skip entirely ("'ring'
#     selector has no border-owning-child concept yet"). Same 1x3 grid
#     as test 5, but with DISTINCT labels p/q/r (no shared base) --
#     the case a same-base PAIR genuinely can't reach, needed one
#     level up in a real plan where the children don't all share one
#     repeated label.
row3d = leaf([2000.0, 2000.0, 2000.0], [3000.0], [["p", "q", "r"]])
ring_wall = {"cellWidths": ["auto"], "cellLengths": [500.0],
             "cellLabels": [["ringwall"]]}
row3d["borderOverrides"] = [{"between": ["p", "*", "T,B"],
                              "wallLayout": ring_wall}]
c6, l6, b6t, t6 = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w6 = []
mod._emit(row3d, None, None, FakePlane(), FakePath(0), c6, l6, b6t, t6,
          w6, {})
ring_count = sum(l6.branches[p].count("ringwall") for p in l6.Paths
                  if p.Length == 2 and p.idx[0] == 0)
assert w6 == [], w6
assert ring_count == 2, ring_count
print("OK -- a RING anchor (['p','*','T,B']) now places a wall layout "
      "too: exactly 2 walls (p's own North and South), correctly "
      "skipping p's West even though it also touches EXT -- no matter "
      "what's across each matched border (a sibling or EXT), same as "
      "a ring already behaves for Offset\n")

# --- 6b) An EXT ring (['EXT','*']) is the one anchor that isn't a
#     real space -- walls the WHOLE perimeter of the node at once,
#     the case that actually motivated this: one level up, where p/q/
#     r-style children don't share a common base label to pair
#     against each other, ['EXT','*'] is the only way to say "every
#     child's own exterior wall" without naming each one.
row3e = leaf([2000.0, 2000.0, 2000.0], [3000.0], [["p", "q", "r"]])
extring_wall = {"cellWidths": ["auto"], "cellLengths": [500.0],
                 "cellLabels": [["extringwall"]]}
row3e["borderOverrides"] = [{"between": ["EXT", "*", "T,B"],
                              "wallLayout": extring_wall}]
c6b, l6b, b6bt, t6b = FakeTree(), FakeTree(), FakeTree(), FakeTree()
w6b = []
mod._emit(row3e, None, None, FakePlane(), FakePath(0), c6b, l6b, b6bt,
          t6b, w6b, {})
extring_count = sum(l6b.branches[p].count("extringwall") for p in l6b.Paths
                     if p.Length == 2 and p.idx[0] == 0)
assert w6b == [], w6b
assert extring_count == 6, extring_count
print("OK -- an EXT ring (['EXT','*','T,B']) walls the WHOLE "
      "perimeter of the node at once -- all 3 children's own "
      "North+South (6 walls), correctly skipping p's West and r's "
      "East, without naming p/q/r individually or needing them to "
      "share a base label\n")

print("ALL OK")
