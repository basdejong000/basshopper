#! python3
"""Output params: make standalone params for outputs of the selected component(s).

A box lists the outputs, numbered, with a tick box each. Outputs that aren't wired to
anything yet are ticked already.
  digits 1-9     tick / untick that row
  A              tick all, or untick all when everything is ticked
  Up/Down        move;  Right ticks, Left unticks the highlighted row
  click          tick / untick
  Enter/Space    make the params
  Esc            close
Each new param has the output's type and its default name, sits to the right of the
component level with the output, and is wired from it. Ctrl+Z undoes it in one step.
When Name new params is on, its name box follows for each new param.
"""
import sys
import traceback

import Grasshopper
import Rhino
import System
import System.Drawing as SD
import System.Windows.Forms as WF
from System.Collections.Generic import List
from Grasshopper.Kernel import IGH_Component, IGH_Param
from Grasshopper.Kernel.Undo import GH_UndoRecord, IGH_UndoAction
from Grasshopper.Kernel.Undo.Actions import GH_AddObjectAction

GAP = 40  # px between the component and the new params
NAME_STATE = "_basshopper_name_new_params"  # Name new params' live functions
NAME_SETTING = "basshopper:NameNewParams"

DIGITS = {getattr(WF.Keys, "D" + str(n)): n for n in range(1, 10)}
DIGITS.update({getattr(WF.Keys, "NumPad" + str(n)): n for n in range(1, 10)})


def log(msg):
    Rhino.RhinoApp.WriteLine("basshopper: output params: " + str(msg))


def concrete(obj):
    # pythonnet 3 can wrap objects as their declared interface; unwrap to the real type.
    return getattr(obj, "__implementation__", obj)


def on_screen(form, point):
    # Keep the whole box inside the screen Grasshopper is on: a box off-screen blocks everything.
    area = WF.Screen.FromControl(Grasshopper.Instances.DocumentEditor).WorkingArea
    x = max(area.Left, min(point.X, area.Right - form.Width))
    y = max(area.Top, min(point.Y, area.Bottom - form.Height))
    return SD.Point(x, y)


def pick_outputs(rows, several):
    """Show the tick list. Returns the chosen (component, output) rows, or [] when closed."""
    form = WF.Form()
    form.Text = "Output params"
    form.FormBorderStyle = WF.FormBorderStyle.FixedToolWindow
    form.ShowInTaskbar = False
    form.StartPosition = WF.FormStartPosition.Manual
    form.AutoScaleMode = WF.AutoScaleMode.Font
    form.KeyPreview = True

    head = WF.Label()
    head.Text = "Digits tick, Enter/Space makes the params"
    head.SetBounds(8, 6, 304, 16)
    lst = WF.CheckedListBox()
    lst.CheckOnClick = True
    lst.IntegralHeight = False
    for n, (comp, out) in enumerate(rows, 1):
        label = "{}  {}{}  ({})".format(n if n <= 9 else " ", comp.NickName + ": " if several else "",
                                        out.NickName, out.TypeName)
        lst.Items.Add(label, out.Recipients.Count == 0)
    lst.SetBounds(8, 24, 304, lst.ItemHeight * min(len(rows), 14) + 6)
    y = lst.Bottom + 8
    ok = WF.Button()
    ok.Text = "Make"
    ok.DialogResult = WF.DialogResult.OK
    ok.SetBounds(156, y, 75, 24)
    cancel = WF.Button()
    cancel.Text = "Close"
    cancel.DialogResult = WF.DialogResult.Cancel
    cancel.SetBounds(237, y, 75, 24)
    form.ClientSize = SD.Size(320, y + 32)
    for control in (head, lst, ok, cancel):
        form.Controls.Add(control)
    form.AcceptButton = ok
    form.CancelButton = cancel
    if lst.Items.Count:
        lst.SelectedIndex = 0

    def toggle(i, value=None):
        if 0 <= i < lst.Items.Count:
            lst.SetItemChecked(i, (not lst.GetItemChecked(i)) if value is None else value)
            lst.SelectedIndex = i

    def on_key_down(s, e):
        key = e.KeyCode
        if key == WF.Keys.Space or key == WF.Keys.Enter:
            form.DialogResult = WF.DialogResult.OK
        elif key in DIGITS:
            toggle(DIGITS[key] - 1)
        elif key == WF.Keys.A:
            everything = all(lst.GetItemChecked(i) for i in range(lst.Items.Count))
            for i in range(lst.Items.Count):
                lst.SetItemChecked(i, not everything)
        elif key == WF.Keys.Right:
            toggle(lst.SelectedIndex, True)
        elif key == WF.Keys.Left:
            toggle(lst.SelectedIndex, False)
        else:
            return  # Up/Down, Esc: the list and form handle these
        e.Handled = True
        e.SuppressKeyPress = True  # also stops the list's own Space toggle

    form.KeyDown += on_key_down
    try:
        form.Location = on_screen(form, WF.Cursor.Position)
        result = form.ShowDialog(Grasshopper.Instances.DocumentEditor)
        chosen = [rows[i] for i in range(lst.Items.Count) if lst.GetItemChecked(i)]
    finally:
        form.Dispose()
    return chosen if result == WF.DialogResult.OK else []


def place(param, left_edge, center_y):
    """Put a param's box with its left edge at left_edge, centred on center_y."""
    attrs = param.Attributes
    attrs.Pivot = SD.PointF(0, 0)
    attrs.ExpireLayout()
    attrs.PerformLayout()
    box = attrs.Bounds
    attrs.Pivot = SD.PointF(left_edge - box.Left, center_y - (box.Top + box.Height / 2.0))
    attrs.ExpireLayout()
    attrs.PerformLayout()


def make_params(doc, chosen):
    actions = List[IGH_UndoAction]()
    made = []
    for comp, out in chosen:
        param = concrete(Grasshopper.Instances.ComponentServer.EmitObject(out.ComponentGuid))
        if param is None or not isinstance(param, IGH_Param):
            log("no param type for '{}'".format(out.NickName))
            continue
        param.CreateAttributes()
        place(param, comp.Attributes.Bounds.Right + GAP, out.Attributes.OutputGrip.Y)
        doc.AddObject(param, False)
        actions.Add(GH_AddObjectAction(param))
        param.AddSource(out)
        param.ExpireSolution(False)  # marks it for the next solution; doesn't start one
        made.append(param)
    if actions.Count:
        doc.UndoServer.PushUndoRecord(GH_UndoRecord("Output params", actions))
    return made


def ask_names(made):
    # Name new params' box, one after another, when that tool is on.
    if not Grasshopper.Instances.Settings.GetValue(NAME_SETTING, False):
        return
    state = getattr(sys, NAME_STATE, None)
    name_param = state.get("name_param") if state else None
    if name_param is None:
        return
    for param in made:
        name_param(param)


def main():
    canvas = Grasshopper.Instances.ActiveCanvas
    doc = canvas.Document if canvas else None
    if doc is None:
        log("no Grasshopper document open")
        return
    comps = [concrete(o) for o in doc.SelectedObjects()]
    comps = [c for c in comps if isinstance(c, IGH_Component) and c.Params.Output.Count]
    if not comps:
        log("select a component first")
        return
    comps.sort(key=lambda c: (c.Attributes.Bounds.Top, c.Attributes.Bounds.Left))
    rows = [(c, concrete(out)) for c in comps for out in c.Params.Output]
    chosen = pick_outputs(rows, len(comps) > 1)
    if not chosen:
        return
    made = make_params(doc, chosen)
    log("made {} param(s)".format(len(made)))
    ask_names(made)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(traceback.format_exc())
