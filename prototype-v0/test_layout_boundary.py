import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location(
    "layout",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms-layout-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["layout"] = mod
spec.loader.exec_module(mod)


class FakeVec3:
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z


class FakePlane:
    def __init__(self, origin, xaxis, yaxis):
        self.Origin = FakeVec3(*origin)
        self.XAxis = FakeVec3(*xaxis)
        self.YAxis = FakeVec3(*yaxis)


class FakeRectangle3d:
    def __init__(self, plane, width, height):
        self.Plane = plane
        self.Width = width
        self.Height = height


warnings = []

# --- Boundary alone: plane baked into JSON, width/height seed
#     default single-track CellWidths/CellLengths.
plane = FakePlane((1000.0, 2000.0, 3000.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
boundary = FakeRectangle3d(plane, 4000.0, 2700.0)
inputs = {"Boundary": boundary}
merged = mod.merge_layout(inputs, {}, warnings)
print("merged:", merged)
assert merged["plane"]["origin"] == [1000.0, 2000.0, 3000.0]
assert merged["plane"]["xAxis"] == [1.0, 0.0, 0.0]
assert merged["plane"]["yAxis"] == [0.0, 0.0, 1.0]
assert merged["cellWidths"] == [4000.0]
assert merged["cellLengths"] == [2700.0]
# 'CellLabels is required' is expected here (none was authored in
# this test) -- unrelated to Boundary; just confirm no Boundary-
# specific warning fired.
assert not any("Boundary" in w for w in warnings), warnings
print("OK -- Boundary bakes plane into the JSON and seeds default "
      "single-track extents\n")

# --- Explicit CellWidths/CellLengths win over Boundary's defaults.
warnings2 = []
inputs2 = {
    "Boundary": boundary,
    "CellWidths": ["auto", 900.0, "auto"],
    "CellLengths": [2700.0],
}
merged2 = mod.merge_layout(inputs2, {}, warnings2)
print("merged2 cellWidths:", merged2["cellWidths"])
assert merged2["cellWidths"] == ["auto", 900.0, "auto"]
assert merged2["plane"]["origin"] == [1000.0, 2000.0, 3000.0]
print("OK -- explicit CellWidths overrides Boundary's default, plane "
      "still comes through\n")

# --- No Boundary at all: no 'plane' key, unchanged from before.
warnings3 = []
inputs3 = {"CellWidths": [1000.0], "CellLengths": [1000.0],
           "CellLabels": "x"}
merged3 = mod.merge_layout(inputs3, {}, warnings3)
assert "plane" not in merged3
print("OK -- no Boundary wired -> no 'plane' field at all, unchanged\n")

# --- Junk wired into Boundary: warns clearly, doesn't crash, no
#     'plane' field added.
warnings4 = []
merged4 = mod.merge_layout({"Boundary": "not a rectangle"}, {}, warnings4)
assert "plane" not in merged4
assert any("Rectangle3d" in w for w in warnings4)
print("OK -- junk Boundary warns clearly instead of crashing\n")

print("ALL OK")
