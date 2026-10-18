"""
Build the RhinoCode Python 3 GH components in this prototype folder --
each a <name>.spec.json + <name>.py pair, same convention as PMS's own
grasshopper/setup-scripts/rhino8/create-pms-components-py3.py, trimmed
down to build just this ad-hoc set instead of the whole release set so
it doesn't touch or get mixed into the real "PMS" user-objects folder.

RUN THIS IN RHINO 8, not from a terminal:
  1. Tools > Script > Edit (opens the Script Editor).
  2. Open this file; set the engine to Python 3 (RhinoCode).
  3. Click Run.

Writes <GH UserObjects>/PMS-Prototype/<Display Name>.ghuser for every
entry in COMPONENTS below. Restart Rhino (or run Grasshopper's "File >
Special Folders > User Object Folder" refresh) and they appear in the
GH palette under a "PMS-Prototype" tab. Re-run any time a .py or
.spec.json changes -- it just overwrites the same files.
"""

import os
import json
import uuid

import System

import Grasshopper as gh
import GH_IO.Serialization as _gh_io_ser
import Rhino.Geometry as rg

import RhinoCodePluginGH.Components as _rcgh_components
import RhinoCodePluginGH.Parameters as _rcgh_params

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
USER_OBJECT_SUBFOLDER = "PMS-Prototype"

# A fixed namespace for deriving each component's own stable GUID from
# its base filename (see _stable_component_guid) -- any fixed UUID
# works here, it's never compared against anything else, just used as
# a seed so uuid5's output is deterministic run-to-run.
_GUID_NAMESPACE = uuid.UUID("6c9b6f4a-2f0a-4b8e-9b0a-7a1f7e9d5c31")

# (base filename without extension, display name shown on the canvas).
# Add a row here for every new <base>.spec.json + <base>.py pair.
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
    # Same reasoning as list-access (see the docstring on
    # select_type_hint below): R8 RhinoCode's scalar converters try to
    # convert the WHOLE collection to a single value on any
    # multi-value access, not just list -- tree-access params hit the
    # identical collapse (a DataTree assigned to the output shows up
    # downstream as one flattened Python-repr'd blob instead of a
    # real branched tree). The worker code already builds real Rhino
    # geometry objects (rg.Line, rg.PolylineCurve, ...) directly, so
    # there's nothing for a converter to do here regardless -- leave
    # these on the default GooConverter, which passes a DataTree
    # through unchanged, same as it already does for plain lists.
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


def _stable_component_guid(base):
    """A GUID derived deterministically from the component's own base
    filename -- same input always gives the same GUID, so a rebuild
    doesn't orphan components already placed on canvas, but two
    DIFFERENT components can never collide. Needed because the
    RhinoCode Python3Component factory's own default ComponentGuid
    assignment isn't reliably unique across several components built
    in quick succession in one script run (suspected: a low-resolution
    time-based seed) -- symptom: an already-placed component silently
    getting its identity swapped for a DIFFERENT one built moments
    later in the same run, after the next rebuild. Wrapped in
    try/except at the call site since ComponentGuid may be read-only
    on some RhinoCode versions -- if so this is a no-op, not a crash."""
    return System.Guid(str(uuid.uuid5(_GUID_NAMESPACE, base)))


def create_component(spec, worker_code, display_name, base):
    comp, used_factory = _new_python3_component(display_name, worker_code)
    comp.Name = display_name
    comp.NickName = spec["nickname"]
    try:
        comp.ComponentGuid = _stable_component_guid(base)
    except Exception as e:
        print("    [warn] couldn't set a stable ComponentGuid on '{}': {} "
              "-- this component may still be vulnerable to the "
              "identity-swap bug this was meant to fix.".format(base, e))

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


def _user_object_folder():
    root = gh.Folders.DefaultUserObjectFolder
    out = os.path.join(root, USER_OBJECT_SUBFOLDER)
    if not os.path.isdir(out):
        os.makedirs(out)
    return out


def _save_as_user_object(comp):
    uo = gh.Kernel.GH_UserObject()
    uo.BaseGuid = comp.ComponentGuid
    uo.Description = gh.Kernel.GH_InstanceDescription(
        comp.Name, comp.NickName, comp.Description,
        USER_OBJECT_SUBFOLDER, "Prototype",
    )
    uo.Exposure = gh.Kernel.GH_Exposure.primary
    chunk = _gh_io_ser.GH_LooseChunk("UserObject")
    comp.Write(chunk)
    uo.Data = chunk.Serialize_Binary()
    uo.Path = os.path.join(_user_object_folder(), comp.Name + ".ghuser")
    ok = uo.SaveToFile()
    return ok, uo.Path


def main():
    stage = gh.Kernel.GH_Document()
    written = 0
    for base, display_name in COMPONENTS:
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

        comp = create_component(spec, worker_code, display_name, base)
        stage.AddObject(comp, False)
        ok, path = _save_as_user_object(comp)
        stage.RemoveObject(comp, False)

        if ok:
            written += 1
            print("[ok]   {}".format(path))
        else:
            print("[fail] {} -- SaveToFile returned False".format(display_name))

    print("\nWrote {} of {} component(s).".format(written, len(COMPONENTS)))
    if written:
        print("Restart Rhino (or refresh GH's user object folder) -- "
              "they'll show up under the 'PMS-Prototype' ribbon tab.")


main()