"""Headless test of pms-layout-border-override-v0.py's OWN merge/
validation logic -- separate from test_border_overrides.py, which only
tests Geom's CONSUMPTION of an already-built override document. This
is what would have caught the 'Between is required' false-positive
on a valid 3-item (pair + side filter) input before it ever reached a
live Rhino session."""
import importlib.util
import json
import os
import sys

spec = importlib.util.spec_from_file_location(
    "border_override",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms-layout-border-override-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["border_override"] = mod
spec.loader.exec_module(mod)


def merge(between=None, offset=None, wall_layout=None):
    inputs = {}
    if between is not None:
        inputs["Between"] = between
    if offset is not None:
        inputs["Offset"] = offset
    if wall_layout is not None:
        inputs["WallLayoutJSON"] = wall_layout
    warnings = []
    merged = mod.merge_override(inputs, {}, warnings)
    return merged, warnings


# --- Plain pair (2 items): valid, no warning.
merged, warnings = merge(between=["m1", "m2"], offset=-200.0)
assert merged["between"] == ["m1", "m2"], merged
assert merged["offset"] == -200.0, merged
assert warnings == [], warnings
print("OK -- a plain pair (2 items) merges cleanly, no warning\n")

# --- Pair + side filter (3 items) -- the exact regression: this used
#     to fire 'Between is required' even though it's a fully valid
#     input, because merge_override's own length check hadn't been
#     updated when the side filter was added to Geom's own parsing.
merged, warnings = merge(between=["m1", "EXT", "L"], offset=-200.0)
assert merged["between"] == ["m1", "EXT", "L"], merged
assert merged["offset"] == -200.0, merged
assert warnings == [], warnings
print("OK -- pair + side filter (3 items) merges cleanly, no false "
      "'Between is required' warning\n")

# --- Ring (2 items, one '*'): valid, no warning at THIS layer (Geom
#     applies it -- always independent, see pms-layout-geom-v0.py).
merged, warnings = merge(between=["m1", "*"])
assert merged["between"] == ["m1", "*"], merged
assert warnings == [], warnings
print("OK -- a ring selector merges cleanly (Geom applies it as an "
      "independent shift on the anchor space, not this component)\n")

# --- Global (['*','*']): valid at THIS layer, no warning (Geom is the
#     one that later warns it has no effect -- no single space to
#     anchor an Offset to).
merged, warnings = merge(between=["*", "*"])
assert merged["between"] == ["*", "*"], merged
print("OK -- the global selector merges cleanly\n")

# --- Missing Between entirely: warns.
merged, warnings = merge(offset=50.0)
assert any("Between is required" in w for w in warnings), warnings
print("OK -- no Between at all still warns clearly\n")

# --- Non-numeric Offset: warns, offset key dropped.
merged, warnings = merge(between=["m1", "m2"], offset="not a number")
assert "offset" not in merged, merged
assert any("isn't a number" in w for w in warnings), warnings
print("OK -- a non-numeric Offset warns and is dropped, doesn't crash\n")

# --- WallLayoutJSON with CellWidths=['auto'] (the required placeholder):
#     merges cleanly, no warning.
door = {"cellWidths": ["auto"], "cellLengths": [2100.0, 600.0],
        "cellLabels": [["frame", "door", "frame"],
                        ["header", "header", "header"]]}
merged, warnings = merge(between=["m1", "m2"], wall_layout=json.dumps(door))
assert merged.get("wallLayout", {}).get("cellWidths") == ["auto"], merged
assert warnings == [], warnings
print("OK -- WallLayoutJSON with CellWidths=['auto'] merges cleanly\n")

# --- WallLayoutJSON with a LITERAL width instead of 'auto' -- the
#     width was never the author's to set (Geom fills it in from the
#     matched border's own length) -- warned, and NOT merged in (the
#     base/previous wallLayout, if any, is kept instead).
bad_width = {"cellWidths": [4000.0], "cellLengths": [2700.0],
             "cellLabels": [["glass"]]}
merged, warnings = merge(between=["m1", "m2"], wall_layout=json.dumps(bad_width))
assert "wallLayout" not in merged, merged
assert any("must be exactly ['auto']" in w for w in warnings), warnings
print("OK -- a literal CellWidths on a wall layout warns and is "
      "rejected, not silently accepted\n")

# --- WallLayoutJSON with CellWidths missing entirely -- same rejection,
#     since None != ['auto'] either.
no_width = {"cellLengths": [2700.0], "cellLabels": [["glass"]]}
merged, warnings = merge(between=["m1", "m2"], wall_layout=json.dumps(no_width))
assert "wallLayout" not in merged, merged
assert any("must be exactly ['auto']" in w for w in warnings), warnings
print("OK -- a wall layout with no CellWidths at all is rejected the "
      "same way\n")

print("ALL OK")
