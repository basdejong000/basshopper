import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location(
    "pms_layout_v0",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms-layout-v0.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules["pms_layout_v0"] = mod
spec.loader.exec_module(mod)

warnings = []

# 1) 'auto' column sized from a nested child's own intrinsic width.
child = {
    "label": "child",
    "cellWidths": [2000.0],
    "cellLengths": [1000.0],
    "cellLabels": [["x"]],
}
root = {
    "cellWidths": ["auto", "1fr"],
    "cellLengths": [3000.0],
    "cellLabels": [["child", "B"]],
    "childLayouts": [child],
}
res = mod._resolve_node(root, None, None, warnings)
(col_starts, col_sizes, total_w, row_starts, row_sizes, total_l,
 spaces, children, labels_grid) = res
print("auto column sizes:", col_sizes, "total_w:", total_w)
assert col_sizes[0] == 2000.0, "auto column should equal child's intrinsic width (2000)"
assert col_sizes[1] == 0.0, "root has no imposed total, so 'fr' has nothing to share -> 0"
assert total_w == 2000.0

# 2) 'auto' column with nothing in it resolves to 0mm, no crash.
root2 = {
    "cellWidths": ["auto", 500.0],
    "cellLengths": [1000.0],
    "cellLabels": [["empty", "B"]],
}
res2 = mod._resolve_node(root2, None, None, warnings)
print("empty-auto column sizes:", res2[1])
assert res2[1][0] == 0.0

# 3) 'auto' spanning 2 columns, one fixed + one auto in the span, child
#    needs more than the fixed one alone provides -> shortfall goes to
#    the auto track only.
child2 = {"cellWidths": [3000.0], "cellLengths": [500.0], "cellLabels": [["y"]], "label": "c2"}
root3 = {
    "cellWidths": [800.0, "auto"],
    "cellLengths": [500.0],
    "cellLabels": [["c2", "c2"]],
    "childLayouts": [child2],
}
res3 = mod._resolve_node(root3, None, None, warnings)
print("mixed span col sizes:", res3[1])
assert res3[1][0] == 800.0
assert res3[1][1] == 2200.0  # 3000 needed - 800 fixed = 2200 shortfall onto the auto track

# 4) Nested-of-nested: grandchild auto propagates up two levels.
grandchild = {"cellWidths": [500.0], "cellLengths": [500.0], "cellLabels": [["g"]], "label": "gc"}
mid = {
    "cellWidths": ["auto"],
    "cellLengths": [500.0],
    "cellLabels": [["gc"]],
    "childLayouts": [grandchild],
    "label": "mid",
}
top = {
    "cellWidths": ["auto"],
    "cellLengths": [500.0],
    "cellLabels": [["mid"]],
    "childLayouts": [mid],
}
res4 = mod._resolve_node(top, None, None, warnings)
print("two-level auto propagation, total_w:", res4[2])
assert res4[2] == 500.0

# 5) Reproduces the reported crash: a 1x1 root (CellWidths=["1fr"],
#    CellLengths=["1fr"]) whose CellLabels grid has an extra column
#    (2 cols instead of 1) hosting a fixed-size child. Used to raise
#    IndexError in _distribute_auto_demand; should now just warn and
#    clip instead of crashing.
crash_child = {"cellWidths": [4000.0], "cellLengths": [8000.0],
               "cellLabels": [["x"]], "label": "deep"}
crash_root = {
    "cellWidths": ["1fr"],
    "cellLengths": ["1fr"],
    "cellLabels": [["deep", "extra"]],   # 2 cols but only 1 track
    "childLayouts": [crash_child],
}
w2 = []
res5 = mod._resolve_node(crash_root, None, None, w2)
print("mismatched-grid col sizes:", res5[1], "warnings:", w2)
assert any("clipped/padded" in x for x in w2)

print("ALL OK")
print("warnings collected during the run:", warnings)
