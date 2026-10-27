#! python3
"""Add a -[n] suffix to the name of each selected Grasshopper parameter,
where n is the branch depth of the data going through it.

    {0}       -> Points-[1]
    {0;1}     -> Points-[2]
    {0;1;2}   -> Points-[3]

Running it again updates the suffix instead of adding a second one.
Only stand-alone parameters (Point, Curve, Number, ...) are renamed;
components are skipped. Parameters without data are skipped too.

Run from Rhino 8 with Grasshopper open:
    _-ScriptEditor _Run "C:\\Users\\basdejong\\Git\\basshopper\\tools\\param_depth_suffix.py"
"""
import re

import Grasshopper
import Rhino

SUFFIX = re.compile(r"-\[\d+\]$")


def log(msg):
    Rhino.RhinoApp.WriteLine("Param depth: " + str(msg))


def concrete(obj):
    # pythonnet 3 wraps objects as their declared interface; unwrap to the real type.
    return getattr(obj, "__implementation__", obj)


def is_param(obj):
    # Stand-alone parameters carry data themselves; components have a Params collection.
    return hasattr(obj, "VolatileData") and not hasattr(obj, "Params")


def branch_depth(param):
    paths = list(param.VolatileData.Paths)
    if not paths:
        return None, False
    depths = {path.Length for path in paths}
    return max(depths), len(depths) > 1


def main():
    canvas = Grasshopper.Instances.ActiveCanvas
    doc = canvas.Document if canvas else None
    if doc is None:
        log("open a Grasshopper definition first")
        return

    selection = [concrete(obj) for obj in doc.SelectedObjects()]
    params = [obj for obj in selection if is_param(obj)]
    if not params:
        log("select one or more parameters first")
        return

    renamed = skipped = 0
    for param in params:
        depth, mixed = branch_depth(param)
        if depth is None:
            log("'{}' has no data, skipped".format(param.NickName))
            skipped += 1
            continue
        if mixed:
            log("'{}' has branches of different depths, using the deepest".format(param.NickName))

        base = SUFFIX.sub("", param.NickName)
        new_name = "{}-[{}]".format(base, depth)
        if new_name == param.NickName:
            continue
        try:
            doc.UndoUtil.RecordGenericObjectEvent("Param depth suffix", param)
        except Exception:
            pass
        param.NickName = new_name
        param.Attributes.ExpireLayout()
        renamed += 1

    log("renamed {}, skipped {}".format(renamed, skipped))


main()
