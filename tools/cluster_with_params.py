#! python3
"""Cluster the selected Grasshopper objects and keep the boundary parameters on
the outside too.

A pop-up asks for the cluster's name first: OK uses what you typed, Default keeps
Grasshopper's own name, Cancel stops without changing anything.

Select a group whose inputs and outputs already go through stand-alone parameters,
e.g. Points-[1] -> components -> Curves-[2]. Grasshopper's own Cluster command puts
those parameters inside the cluster. This tool runs that command and then:
  - names each cluster input/output after the parameter it leads to inside,
  - places a parameter of the same type and name just left of the cluster for each
    input, and just right of it for each output, and rewires through it.

Selected parameters with nothing wired into them become inputs too, and those with
nothing wired out of them become outputs. Panels, sliders, toggles, value lists and
other Params > Input / Util objects are never treated as boundaries. Exception: an
unwired input that holds its own (internalised) data is left inside, so that data
keeps working.

Inputs and outputs that don't go through a parameter are left as Grasshopper made them.
Ctrl+Z takes up to three steps: the outside parameters, the cluster, and the wires added
to unconnected parameters before clustering.

Run from Rhino 8 with Grasshopper open:
    _-ScriptEditor _Run "C:\\Users\\basdejong\\Git\\basshopper\\tools\\cluster_with_params.py"
"""
import Grasshopper
import Rhino
import System
from System.Collections.Generic import List
import System.Drawing as SD
import System.Windows.Forms as WF
from Grasshopper.Kernel import GH_ParamData
from Grasshopper.Kernel.Special import GH_Cluster, GH_ClusterInputHook, GH_ClusterOutputHook
from Grasshopper.Kernel.Undo import GH_UndoRecord, IGH_UndoAction
from Grasshopper.Kernel.Undo.Actions import GH_AddObjectAction, GH_WireAction

GAP = 30  # px between the cluster and the outside parameters


def log(msg):
    Rhino.RhinoApp.WriteLine("Cluster with params: " + str(msg))


def concrete(obj):
    # pythonnet 3 wraps objects as their declared interface; unwrap to the real type.
    return getattr(obj, "__implementation__", obj)


def is_param(obj):
    # Stand-alone parameters carry data themselves; components have a Params collection.
    return hasattr(obj, "VolatileData") and not hasattr(obj, "Params")


def is_boundary_candidate(obj):
    # Panels, sliders, toggles, value lists, relays etc. are params too, but never boundaries.
    if not is_param(obj):
        return False
    if obj.SubCategory in ("Input", "Util"):
        return False
    return not str(obj.GetType().Namespace).startswith("Grasshopper.Kernel.Special")


def guids(objs):
    return frozenset(o.InstanceGuid for o in objs)


def boundary_params(selection):
    """Selected parameters wired to something outside the selection, and the
    unconnected ones that should become inputs or outputs."""
    inside = guids(selection)

    def outside(objs):
        # A wire end can be a component's input/output; judge it by the object that owns it.
        return frozenset(o.InstanceGuid for o in objs
                         if o.Attributes.GetTopLevel.DocObject.InstanceGuid not in inside)

    inputs, outputs, loose_in, loose_out = [], [], [], []
    for obj in selection:
        if not is_boundary_candidate(obj):
            continue
        sources = outside(obj.Sources)
        recipients = outside(obj.Recipients)
        if sources:
            inputs.append((obj, sources))
        if recipients:
            outputs.append((obj, recipients))
        if obj.SourceCount == 0:
            if obj.DataType == GH_ParamData.local:
                log("'{}' holds its own data, left inside the cluster".format(obj.NickName))
            else:
                loose_in.append(obj)
        elif obj.Recipients.Count == 0:
            loose_out.append(obj)
    return inputs, outputs, loose_in, loose_out


def prewire(doc, loose_in, loose_out, inputs, outputs):
    """Give unconnected parameters an outside parameter, so the Cluster command
    makes an input/output for them. Returns {inner param guid: outside param}."""
    actions = List[IGH_UndoAction]()
    made = {}

    def add(param):
        outer = new_param_like(param)
        doc.AddObject(outer, False)
        actions.Add(GH_AddObjectAction(outer))
        actions.Add(GH_WireAction(param))
        made[param.InstanceGuid] = outer
        return outer, param.Attributes.Bounds

    for param in loose_in:
        outer, box = add(param)
        place(outer, right_edge=box.Left - GAP, center_y=box.Top + box.Height / 2.0)
        param.AddSource(outer)
        inputs.append((param, frozenset([outer.InstanceGuid])))
    for param in loose_out:
        outer, box = add(param)
        place(outer, left_edge=box.Right + GAP, center_y=box.Top + box.Height / 2.0)
        outer.AddSource(param)
        outputs.append((param, frozenset([outer.InstanceGuid])))
    if actions.Count:
        doc.UndoServer.PushUndoRecord(GH_UndoRecord("Cluster params: wire loose params", actions))
    return made


def run_cluster_command(editor):
    flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic
    method = editor.GetType().GetMethod("MnuClusterSelectionClick", flags)
    method.Invoke(editor, System.Array[System.Object]([None, System.EventArgs.Empty]))


def take_match(candidates, key):
    """Pop the boundary parameter whose outside wires match `key`."""
    for i, (param, wires) in enumerate(candidates):
        if wires == key:
            return candidates.pop(i)[0]
    return None


def rename_hooks(cluster, names):
    """Name the hooks inside the cluster after the parameter they connect to."""
    inner = cluster.Document("")
    if inner is None:
        return
    for obj in inner.Objects:
        hook = concrete(obj)
        if isinstance(hook, GH_ClusterInputHook):
            ends = list(hook.Recipients)
        elif isinstance(hook, GH_ClusterOutputHook):
            ends = list(hook.Sources)
        else:
            continue
        for end in ends:
            if end.NickName in names:
                hook.NickName = end.NickName
                hook.Name = end.NickName
                break


def place(param, right_edge=None, left_edge=None, center_y=0.0):
    """Put a parameter's box against the given edge, centred on center_y."""
    attrs = param.Attributes
    attrs.Pivot = System.Drawing.PointF(0, 0)
    attrs.ExpireLayout()
    attrs.PerformLayout()
    box = attrs.Bounds
    x = (right_edge - box.Width) if right_edge is not None else left_edge
    attrs.Pivot = System.Drawing.PointF(x - box.Left, center_y - (box.Top + box.Height / 2.0))
    attrs.ExpireLayout()
    attrs.PerformLayout()


def new_param_like(template):
    param = concrete(Grasshopper.Instances.ComponentServer.EmitObject(template.ComponentGuid))
    param.CreateAttributes()
    param.NickName = template.NickName
    param.Name = template.Name
    return param


def ask_name(owner):
    """Pop-up for the cluster name. Returns the name, "" for default, or None to cancel."""
    form = WF.Form()
    form.Text = "Cluster with params"
    form.FormBorderStyle = WF.FormBorderStyle.FixedDialog
    form.StartPosition = WF.FormStartPosition.CenterParent
    form.MinimizeBox = form.MaximizeBox = form.ShowInTaskbar = False
    form.AutoScaleMode = WF.AutoScaleMode.Dpi
    form.ClientSize = SD.Size(320, 96)

    label = WF.Label()
    label.Text = "Cluster name:"
    label.Location = SD.Point(12, 12)
    label.AutoSize = True
    box = WF.TextBox()
    box.Location = SD.Point(12, 32)
    box.Width = 296

    def button(text, x, result):
        b = WF.Button()
        b.Text = text
        b.Location = SD.Point(x, 62)
        b.Width = 92
        b.DialogResult = result
        form.Controls.Add(b)
        return b

    ok = button("OK", 12, WF.DialogResult.OK)
    default = button("Default", 114, WF.DialogResult.Ignore)
    cancel = button("Cancel", 216, WF.DialogResult.Cancel)
    form.Controls.Add(label)
    form.Controls.Add(box)
    form.AcceptButton = ok  # Enter
    form.CancelButton = cancel  # Esc
    form.ActiveControl = box

    result = form.ShowDialog(owner)
    name = box.Text.strip()
    form.Dispose()
    if result == WF.DialogResult.OK:
        return name  # empty means default too
    if result == WF.DialogResult.Ignore:
        return ""
    return None


def main():
    canvas = Grasshopper.Instances.ActiveCanvas
    doc = canvas.Document if canvas else None
    editor = Grasshopper.Instances.DocumentEditor
    if doc is None or editor is None:
        log("open a Grasshopper definition first")
        return

    selection = [concrete(obj) for obj in doc.SelectedObjects()]
    if not selection:
        log("select the objects to cluster first")
        return
    name = ask_name(editor)
    if name is None:
        log("cancelled")
        return

    inputs, outputs, loose_in, loose_out = boundary_params(selection)
    names = {p.NickName for p, _ in inputs + outputs} | {p.NickName for p in loose_in + loose_out}
    made = prewire(doc, loose_in, loose_out, inputs, outputs)

    before = guids(doc.Objects)
    run_cluster_command(editor)
    clusters = [concrete(o) for o in doc.Objects if o.InstanceGuid not in before]
    clusters = [o for o in clusters if isinstance(o, GH_Cluster)]
    if not clusters:
        log("Grasshopper didn't create a cluster")
        return
    cluster = clusters[0]

    # Match first and rename, so the cluster box has its final size before placing.
    in_pairs, out_pairs = [], []
    for cin in cluster.Params.Input:
        template = take_match(inputs, guids(cin.Sources))
        if template is not None:
            cin.NickName = cin.Name = template.NickName
            in_pairs.append((cin, template))
    for cout in cluster.Params.Output:
        template = take_match(outputs, guids(cout.Recipients))
        if template is not None:
            cout.NickName = cout.Name = template.NickName
            out_pairs.append((cout, template))
    rename_hooks(cluster, names)
    if name:
        cluster.NickName = name
    cluster.Attributes.ExpireLayout()
    cluster.Attributes.PerformLayout()
    bounds = cluster.Attributes.Bounds

    actions = List[IGH_UndoAction]()
    for cin, template in in_pairs:
        if template.InstanceGuid in made:
            # Already wired in before clustering; only move it next to the cluster.
            place(made[template.InstanceGuid], right_edge=bounds.Left - GAP, center_y=cin.Attributes.InputGrip.Y)
            continue
        outer = new_param_like(template)
        place(outer, right_edge=bounds.Left - GAP, center_y=cin.Attributes.InputGrip.Y)
        sources = list(cin.Sources)
        actions.Add(GH_WireAction(cin))
        doc.AddObject(outer, False)
        actions.Add(GH_AddObjectAction(outer))
        for src in sources:
            outer.AddSource(src)
        cin.RemoveAllSources()
        cin.AddSource(outer)
        outer.ExpireSolution(False)

    for cout, template in out_pairs:
        if template.InstanceGuid in made:
            place(made[template.InstanceGuid], left_edge=bounds.Right + GAP, center_y=cout.Attributes.OutputGrip.Y)
            continue
        outer = new_param_like(template)
        place(outer, left_edge=bounds.Right + GAP, center_y=cout.Attributes.OutputGrip.Y)
        recipients = list(cout.Recipients)
        doc.AddObject(outer, False)
        actions.Add(GH_AddObjectAction(outer))
        outer.AddSource(cout)
        for rec in recipients:
            actions.Add(GH_WireAction(rec))
            rec.ReplaceSource(cout, outer)
        outer.ExpireSolution(False)

    if actions.Count:
        doc.UndoServer.PushUndoRecord(GH_UndoRecord("Cluster params", actions))
    log("cluster created, {} outside parameter(s) added".format(len(in_pairs) + len(out_pairs)))


main()
