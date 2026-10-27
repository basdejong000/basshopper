#! python3
"""Stack the selected objects vertically with a fixed gap, keeping their top-to-bottom order.

Left-click: align their left edges. Right-click: align their right edges.
The move can be undone with Ctrl+Z.
Ported from C:\\Scripts\\organize-selected-gh-nodes-l.py and -r.py.
"""
import Grasshopper
import Rhino
import System.Drawing as SD

SPACING = 0  # gap in px between the bottom of one object and the top of the next

try:
    MOUSE_BUTTON
except NameError:
    MOUSE_BUTTON = "left"  # run outside the toolbar


def log(msg):
    Rhino.RhinoApp.WriteLine("basshopper: organize nodes: " + str(msg))


def main(align_right):
    canvas = Grasshopper.Instances.ActiveCanvas
    doc = canvas.Document if canvas else None
    if doc is None:
        log("no Grasshopper document open")
        return
    selection = doc.SelectedObjects()  # .NET list, as the undo record wants
    if selection.Count == 0:
        log("nothing selected")
        return

    selected = sorted(selection, key=lambda o: o.Attributes.Bounds.Y)
    if align_right:
        edge = max(o.Attributes.Bounds.Right for o in selected)
    else:
        edge = min(o.Attributes.Bounds.Left for o in selected)
    y = selected[0].Attributes.Bounds.Y

    doc.UndoUtil.RecordPivotEvent("Organize nodes", selection)
    for obj in selected:
        bounds = obj.Attributes.Bounds
        dx = edge - (bounds.Right if align_right else bounds.Left)
        dy = y - bounds.Y
        pivot = obj.Attributes.Pivot
        obj.Attributes.Pivot = SD.PointF(pivot.X + dx, pivot.Y + dy)
        obj.Attributes.ExpireLayout()
        y += bounds.Height + SPACING
    log("stacked {} object(s), aligned {}".format(len(selected), "right" if align_right else "left"))


main(MOUSE_BUTTON == "right")
