"""Headless test of pms-layout2-border-override-v0.py's OWN merge/
validation logic -- same pattern as test_layout_border_override.py for
the original (which is what caught a real 'Between is required' false
positive that never had test coverage before). Separate from
test_geom2.py, which only tests Geom2's CONSUMPTION of an already-
built override document."""
import importlib.util
import json
import os
import sys

spec = importlib.util.spec_from_file_location(
    "border_override2",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "pms-layout2-border-override-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["border_override2"] = mod
spec.loader.exec_module(mod)


def merge(between=None, offset=None, wall_layout=None, wall_height=None):
    inputs = {}
    if between is not None:
        inputs["Between"] = between
    if offset is not None:
        inputs["Offset"] = offset
    if wall_layout is not None:
        inputs["WallLayoutJSON"] = wall_layout
    if wall_height is not None:
        inputs["WallHeight"] = wall_height
    warnings = []
    merged = mod.merge_override(inputs, {}, warnings)
    return merged, warnings


# --- Plain pair (2 items): valid, no warning.
merged, warnings = merge(between=["m[0]", "m[1]"], offset=-200.0)
assert merged["between"] == ["m[0]", "m[1]"], merged
assert merged["offset"] == -200.0, merged
assert warnings == [], warnings
print("OK -- a plain pair (2 items) merges cleanly, no warning\n")

# --- Pair + side filter (3 items): valid, no warning.
merged, warnings = merge(between=["m[0]", "EXT", "L"], offset=-200.0)
assert merged["between"] == ["m[0]", "EXT", "L"], merged
assert merged["offset"] == -200.0, merged
assert warnings == [], warnings
print("OK -- pair + side filter (3 items) merges cleanly, no warning\n")

# --- Ring (2 items, one '*'): valid, no warning at THIS layer.
merged, warnings = merge(between=["m[0]", "*"])
assert merged["between"] == ["m[0]", "*"], merged
assert warnings == [], warnings
print("OK -- a ring selector merges cleanly\n")

# --- Global (['*','*']): valid at this layer, no warning here (Geom2
#     is the one that warns it has no effect).
merged, warnings = merge(between=["*", "*"])
assert merged["between"] == ["*", "*"], merged
print("OK -- the global selector merges cleanly\n")

# --- Missing Between entirely: warns.
merged, warnings = merge(offset=50.0)
assert any("Between is required" in w for w in warnings), warnings
print("OK -- no Between at all still warns clearly\n")

# --- Non-numeric Offset: warns, offset key dropped.
merged, warnings = merge(between=["m[0]", "m[1]"], offset="not a number")
assert "offset" not in merged, merged
assert any("isn't a number" in w for w in warnings), warnings
print("OK -- a non-numeric Offset warns and is dropped, doesn't crash\n")

# --- WallLayoutJSON with CellWidths=['auto'] (the required placeholder,
#     not yet consumed by Geom2 but still validated the same way):
#     merges cleanly, no warning.
door = {"cellWidths": ["auto"], "cellLengths": [2100.0, 600.0],
        "cellLabels": [["frame", "door", "frame"],
                        ["header", "header", "header"]]}
merged, warnings = merge(between=["m[0]", "m[1]"], wall_layout=json.dumps(door))
assert merged.get("wallLayout", {}).get("cellWidths") == ["auto"], merged
assert warnings == [], warnings
print("OK -- WallLayoutJSON with CellWidths=['auto'] merges cleanly\n")

# --- WallLayoutJSON with a literal width -- rejected, not silently
#     accepted, same as the original.
bad_width = {"cellWidths": [4000.0], "cellLengths": [2700.0],
             "cellLabels": [["glass"]]}
merged, warnings = merge(between=["m[0]", "m[1]"], wall_layout=json.dumps(bad_width))
assert "wallLayout" not in merged, merged
assert any("must be exactly ['auto']" in w for w in warnings), warnings
print("OK -- a literal CellWidths on a wall layout warns and is "
      "rejected, not silently accepted\n")

# --- WallLayoutJSON with a relaxed, mixed CellWidths (fixed frame
#     pieces + one 'fr' column for a window) -- merges cleanly, no
#     warning, since there's no 'auto' at all and at least one 'fr' to
#     soak up the wall's own real matched length.
window = {"cellWidths": [400.0, "1fr", 400.0], "cellLengths": [900.0],
          "cellLabels": [["frame", "window", "frame"]]}
merged, warnings = merge(between=["m[0]", "m[1]"], wall_layout=json.dumps(window))
assert merged.get("wallLayout", {}).get("cellWidths") == [400.0, "1fr", 400.0], merged
assert warnings == [], warnings
print("OK -- a relaxed CellWidths (fixed frame pieces + one 'fr' "
      "window column, no 'auto' at all) merges cleanly\n")

# --- WallLayoutJSON mixing 'auto' with another track -- rejected,
#     since 'auto' only has a defined meaning as the SOLE entry.
mixed_auto = {"cellWidths": ["auto", "1fr"], "cellLengths": [900.0],
              "cellLabels": [["a", "b"]]}
merged, warnings = merge(between=["m[0]", "m[1]"], wall_layout=json.dumps(mixed_auto))
assert "wallLayout" not in merged, merged
assert any("must be exactly ['auto']" in w for w in warnings), warnings
print("OK -- 'auto' mixed with another track is rejected, not silently "
      "accepted\n")

# --- WallHeight: a positive number is stored as 'wallHeight'.
merged, warnings = merge(between=["m[0]", "m[1]"], wall_height=2600)
assert merged["wallHeight"] == 2600.0, merged
assert warnings == [], warnings
print("OK -- WallHeight is stored as wallHeight\n")

# --- WallHeight: junk / non-positive is ignored with a warning.
for bad in ("abc", 0, -5):
    merged, warnings = merge(between=["m[0]", "m[1]"], wall_height=bad)
    assert "wallHeight" not in merged, (bad, merged)
    assert any("WallHeight" in w for w in warnings), (bad, warnings)
print("OK -- a non-numeric or non-positive WallHeight is ignored, warned\n")

print("ALL OK")
