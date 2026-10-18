"""
Replace already-PLACED "Layout (WIP)" / "Geom (WIP)" instances on the
CURRENTLY ACTIVE Grasshopper canvas with a freshly-rebuilt version from
the .py + .spec.json pair next to this script -- same rebuild as
build-pms-layout-v0.py, but swapped IN PLACE on canvas instead of only
written to the UserObjects folder, so you don't have to delete and
re-place components (and rewire them) by hand every time the worker
code changes.

SAVE YOUR CANVAS FIRST -- THIS EDITS THE LIVE DOCUMENT. For every
placed instance whose Name matches one of COMPONENTS' OLD names below,
it rebuilds the component from the current source (as the given NEW
display name -- normally the same name, but see the RENAME entries
below), then carries over: the OLD instance's canvas position, every
input's wired sources AND persistent (typed/panel) values, and every
downstream connection reading from one of its outputs -- all matched
by PIN NAME. A pin whose name changed (or was removed) between the old
and new version can't be reconnected automatically; you get a printed
warning naming it instead of losing the wire silently. Read the output
after running.

COMPONENTS entries: a 2-tuple (base, name) is an ordinary same-name
refresh (rebuild base's current .py/.spec.json, swap into any placed
instance named `name`, name unchanged). A 3-tuple (base, old_name,
new_name) is a RENAME -- matches a placed instance named `old_name`,
rebuilds `base` under `new_name` instead. Use this when a component's
own display name changed (e.g. after merging two components into one,
or a v-bump) but you still want the OLD placed instance's wiring
carried over rather than deleted and re-placed by hand. A rename entry
does NOT also match `new_name` -- if you already have separately-
placed instances under both the old and new names, only the one under
`old_name` gets touched by that entry; give the other its own COMPONENTS
row (matching itself) if it also needs a refresh in the same run.

RUN THIS IN RHINO 8, in the Script Editor (Python 3 / RhinoCode
engine), with the canvas holding the placed components open and ACTIVE
-- see build-pms-layout-v0.py for the plain rebuild-to-disk-only
version (no canvas editing, always safe to re-run).
"""

import os
import json

import Grasshopper as gh
import Rhino.Geometry as rg

import RhinoCodePluginGH.Components as _rcgh_components
import RhinoCodePluginGH.Parameters as _rcgh_params

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# (base filename without extension, display Name to match on canvas) --
# or (base, old canvas Name, new display Name) for a RENAME. See the
# module docstring above.
#
# Geom and Geom 2 are SEPARATE, PARALLEL components (the "atomic
# cells" prototype, built alongside the original rather than replacing
# it -- see the session's own design discussion) -- NOT merged. An
# earlier version of this list carried a stale rename entry from a
# different, since-abandoned merge plan ("Geom 2 (WIP)" -> "Geom
# (WIP)") that silently replaced every placed Geom 2 instance with the
# ORIGINAL Geom's own code on every run -- that's why Geom 2 kept
# reverting. Removed. This list must otherwise be kept in sync with
# build-pms-layout-v0.py's own COMPONENTS list by hand (they're
# separate files with separate purposes -- this one edits the live
# canvas, that one only writes user-object files) -- an entry missing
# here means a placed instance of that component silently does NOT
# get refreshed by this script at all (no error, no warning -- it's
# just not in `pairs`, so main()'s own loop never matches it).
COMPONENTS = [
    ("pms-layout-v0", "Layout (WIP)"),
    ("pms-layout-geom-v0", "Geom (WIP)"),
    ("pms-layout-border-override-v0", "Layout Border Override (WIP)"),
    ("pms-layout2-v0", "Layout 2 (WIP)"),
    ("pms-layout-geom2-v0", "Geom 2 (WIP)"),
    ("pms-layout2-border-override-v0", "Layout 2 Border Override (WIP)"),
]

HINT_TARGET_TYPES = {
    "string": __import__("System").String,
    "number": __import__("System").Double,
    "integer": __import__("System").Int32,
    "boolean": __import__("System").Boolean,
    "plane": rg.Plane,
    "point": rg.Point3d,
    "vector": rg.Vector3d,
    "line": rg.Line,
    "curve": rg.Curve,
    "circle": rg.Circle,
    "box": rg.Box,
    "brep": rg.Brep,
    "mesh": rg.Mesh,
}


def access_for(s):
    if s == "list":
        return gh.Kernel.GH_ParamAccess.list
    if s == "tree":
        return gh.Kernel.GH_ParamAccess.tree
    return gh.Kernel.GH_ParamAccess.item


def select_type_hint(param, type_hint_key):
    if not type_hint_key:
        return
    target = HINT_TARGET_TYPES.get(type_hint_key)
    if target is None:
        return
    try:
        param.TypeHints.Select(target)
    except Exception:
        pass


def _set_doc(obj, text):
    text = text or ""
    try:
        obj.Description = text
    except Exception:
        pass
    for attr in ("ToolTip", "Tooltip"):
        if hasattr(obj, attr):
            try:
                setattr(obj, attr, text)
                break
            except Exception:
                pass


def _maybe_select_type_hint(p, spec_entry):
    # Same reasoning as build-pms-layout-v0.py: skip for any
    # multi-value access (list / tree) -- R8's scalar converters
    # collapse those instead of passing them through untouched.
    if spec_entry.get("access") in ("list", "tree"):
        return
    select_type_hint(p, spec_entry.get("typeHint"))


def make_param(spec_entry):
    p = _rcgh_params.ScriptVariableParam()
    p.Name = spec_entry["name"]
    p.NickName = spec_entry["name"]
    p.Optional = spec_entry.get("optional", False)
    p.Access = access_for(spec_entry.get("access", "item"))
    _maybe_select_type_hint(p, spec_entry)
    _set_doc(p, spec_entry.get("description", ""))
    return p


def _extract_docstring(worker_code):
    import re
    m = re.match(r'^\s*(?:[rRuUbB]{0,2})?("""|\'\'\')([\s\S]*?)\1', worker_code)
    return m.group(2).strip() if m else ""


def _new_python3_component(title, source):
    create = getattr(_rcgh_components.Python3Component, "Create", None)
    if create is not None:
        return create(title, source, None, True), True
    return _rcgh_components.Python3Component(), False


def _set_component_code(comp, worker_code):
    code_param = getattr(comp, "CodeInputParam", None)
    if code_param is not None:
        from Grasshopper.Kernel.Types import GH_String
        code_param.PersistentData.Clear()
        code_param.PersistentData.Append(GH_String(worker_code))
        for method_name in ("HideCodeInputParameter", "HideCodeInput",
                             "RemoveCodeInputParameter", "RemoveCodeInput"):
            method = getattr(comp, method_name, None)
            if method is None:
                continue
            try:
                method()
                break
            except Exception:
                pass
        return
    try:
        comp.Code.Text = worker_code
        return
    except AttributeError:
        pass
    for attr in ("ScriptSource", "Source", "Script", "Code"):
        try:
            setattr(comp, attr, worker_code)
            return
        except Exception:
            continue
    raise RuntimeError("Couldn't set script body on {}".format(type(comp).__name__))


def create_component(spec, worker_code, display_name):
    comp, used_factory = _new_python3_component(display_name, worker_code)
    comp.Name = display_name
    comp.NickName = spec["nickname"]

    while comp.Params.Input.Count > 0:
        comp.Params.UnregisterInputParameter(comp.Params.Input[0], True)
    while comp.Params.Output.Count > 0:
        comp.Params.UnregisterOutputParameter(comp.Params.Output[0], True)

    for ispec in spec["inputs"]:
        comp.Params.RegisterInputParam(make_param(ispec))
    for ospec in spec["outputs"]:
        comp.Params.RegisterOutputParam(make_param(ospec))

    comp.Params.OnParametersChanged()

    if not used_factory:
        _set_component_code(comp, worker_code)

    _set_doc(comp, _extract_docstring(worker_code))
    return comp


# -----------------------------------------------------------------
# Canvas swap -- the part build-pms-layout-v0.py doesn't do.
# -----------------------------------------------------------------

def _active_document():
    canvas = gh.Instances.ActiveCanvas
    if canvas is None or canvas.Document is None:
        return None
    return canvas.Document


def _find_param_by_name(params, name):
    for p in params:
        if p.Name == name:
            return p
    return None


def _swap_one(doc, old_comp, spec, worker_code, display_name, warnings):
    old_inputs = list(old_comp.Params.Input)
    old_outputs = list(old_comp.Params.Output)
    pivot = old_comp.Attributes.Pivot

    # EVERYTHING about the old component's wiring has to be captured
    # BEFORE doc.RemoveObject -- removing an object disconnects its OWN
    # wires as part of removal (both its incoming Sources and its role
    # as a Source for anything downstream), so reading .Sources /
    # .PersistentData off old_in AFTER removal finds nothing left to
    # carry over. This bit the input side silently: the loop ran, found
    # empty Sources, and reconnected zero wires with no error raised.
    input_snapshots = []
    for old_in in old_inputs:
        sources = list(old_in.Sources)
        persistent = old_in.PersistentData if not old_in.PersistentData.IsEmpty else None
        input_snapshots.append((old_in.Name, sources, persistent))

    # Every downstream param reading from one of THIS component's
    # outputs -- collected by scanning the whole document BEFORE
    # anything is torn down (nothing else tells you this directly).
    # This side was already correct -- it never read anything off
    # old_comp AFTER removal.
    downstream = {op.Name: [] for op in old_outputs}
    for obj in doc.Objects:
        candidate_params = []
        if hasattr(obj, "Params"):
            candidate_params.extend(obj.Params.Input)
        elif hasattr(obj, "Sources"):
            candidate_params.append(obj)
        for tp in candidate_params:
            for op in old_outputs:
                try:
                    if op in list(tp.Sources):
                        downstream[op.Name].append(tp)
                except Exception:
                    pass

    new_comp = create_component(spec, worker_code, display_name)

    doc.RemoveObject(old_comp, False)
    doc.AddObject(new_comp, False)
    try:
        new_comp.Attributes.Pivot = pivot
        new_comp.Attributes.ExpireLayout()
    except Exception:
        warnings.append("{}: couldn't restore canvas position."
                         .format(display_name))

    for old_name, sources, persistent in input_snapshots:
        new_in = _find_param_by_name(new_comp.Params.Input, old_name)
        had_data = bool(sources) or persistent is not None
        if new_in is None:
            if had_data:
                warnings.append(
                    "{}: input '{}' no longer exists on the new version "
                    "-- its wiring/value was NOT carried over."
                    .format(display_name, old_name))
            continue
        for src in sources:
            try:
                new_in.AddSource(src)
            except Exception:
                warnings.append(
                    "{}: couldn't reconnect a source into input '{}'."
                    .format(display_name, old_name))
        if persistent is not None:
            try:
                new_in.PersistentData.Clear()
                new_in.PersistentData.AppendRange(persistent)
            except Exception:
                warnings.append(
                    "{}: couldn't carry over the typed/panel value on "
                    "input '{}'.".format(display_name, old_name))

    for old_out in old_outputs:
        new_out = _find_param_by_name(new_comp.Params.Output, old_out.Name)
        consumers = downstream.get(old_out.Name, [])
        if new_out is None:
            if consumers:
                warnings.append(
                    "{}: output '{}' no longer exists on the new version "
                    "-- {} downstream connection(s) were NOT carried over."
                    .format(display_name, old_out.Name, len(consumers)))
            continue
        for tp in consumers:
            try:
                tp.AddSource(new_out)
            except Exception:
                warnings.append(
                    "{}: couldn't reconnect a downstream consumer of "
                    "output '{}'.".format(display_name, old_out.Name))

    new_comp.Params.OnParametersChanged()
    try:
        new_comp.ExpireSolution(False)
    except Exception:
        pass
    return new_comp


def main():
    doc = _active_document()
    if doc is None:
        print("No active Grasshopper document -- open the canvas that "
              "holds the placed components first, then re-run.")
        return

    pairs = {}
    for entry in COMPONENTS:
        if len(entry) == 3:
            base, old_name, new_name = entry
        else:
            base, old_name = entry
            new_name = old_name
        spec_path = os.path.join(THIS_DIR, base + ".spec.json")
        worker_path = os.path.join(THIS_DIR, base + ".py")
        if not os.path.isfile(spec_path) or not os.path.isfile(worker_path):
            print("[skip] missing spec/worker for '{}':\n  {}\n  {}"
                  .format(base, spec_path, worker_path))
            continue
        with open(spec_path) as f:
            spec = json.load(f)
        with open(worker_path) as f:
            worker_code = f.read()
        pairs[old_name] = (spec, worker_code, new_name)

    if not pairs:
        print("Nothing to swap -- no spec/worker pairs found.")
        return

    warnings = []
    swapped = 0
    for obj in list(doc.Objects):
        name = getattr(obj, "Name", None)
        if name not in pairs:
            continue
        spec, worker_code, new_name = pairs[name]
        _swap_one(doc, obj, spec, worker_code, new_name, warnings)
        swapped += 1
        if new_name != name:
            print("[swapped] {} -> {}".format(name, new_name))
        else:
            print("[swapped] {}".format(name))

    doc.NewSolution(False)

    print("\nSwapped {} placed instance(s).".format(swapped))
    if swapped == 0:
        print("Nothing on the active canvas matched {} -- is the right "
              "document active?".format(sorted(pairs.keys())))
    if warnings:
        print("\nWarnings -- check these pins by hand:")
        for w in warnings:
            print("  - " + w)


main()
