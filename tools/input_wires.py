#! python3
"""Hide or show the incoming wires of the selected objects.

Left-click: hide. Right-click: show again.
For a component that's all its inputs; for a standalone param, its own input.
Ported from C:\\Scripts\\hide-lines.py and unhide-lines.py.
"""
import Grasshopper
import Rhino
from Grasshopper.Kernel import GH_ParamWireDisplay, IGH_Component, IGH_Param

try:
    MOUSE_BUTTON
except NameError:
    MOUSE_BUTTON = "left"  # run outside the toolbar


def log(msg):
    Rhino.RhinoApp.WriteLine("basshopper: input wires: " + str(msg))


def input_params(obj):
    if isinstance(obj, IGH_Param):
        return [obj]
    if isinstance(obj, IGH_Component):
        return list(obj.Params.Input)
    return []


def main(hide):
    canvas = Grasshopper.Instances.ActiveCanvas
    doc = canvas.Document if canvas else None
    if doc is None:
        log("no Grasshopper document open")
        return
    selected = list(doc.SelectedObjects())
    if not selected:
        log("nothing selected")
        return
    display = GH_ParamWireDisplay.hidden if hide else GH_ParamWireDisplay.default
    changed = 0
    for obj in selected:
        for param in input_params(obj):
            param.WireDisplay = display
            param.Attributes.ExpireLayout()
            changed += 1
    log("{} incoming wires on {} input(s)".format("hid" if hide else "showed", changed))


main(MOUSE_BUTTON != "right")
