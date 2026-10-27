#! python3
"""Name new params: when you place a param that still has its default name (Data, Circle,
Int, ...), a small box asks for a name. Cancel, Esc or an empty name keeps the default.

- Only params from the Params tab: not components, panels, sliders or other special objects.
- Only when you place one yourself: from the ribbon (click or drag), the double-click
  search, or "Extract parameter". Paste, Alt-drag copies, undo/redo, dropped files and
  scripts never prompt, so this doesn't get in the way of Paste link.

Clicking the canvas toolbar button runs this file and opens an On/Off menu.
The listener itself is installed by startup/gh_canvas_toolbar.py.
The On/Off choice is saved in Grasshopper's settings, so it survives a restart.
"""
import sys
import traceback

import Grasshopper
import Rhino
import System
import System.Drawing as SD
import System.Windows.Forms as WF
from Grasshopper.Kernel import IGH_Param

SETTING = "basshopper:NameNewParams"
BUTTON_NAME = "basshopper:Name new params"
STATE = "_basshopper_name_new_params"  # sys attribute with the live handlers, so a reload can detach them

# Grasshopper methods that place a new object because the user asked for it.
PLACE_METHODS = ("InstantiateNewObject", "InsertComponent", "Menu_ExtractParameterClicked")

pending = []  # params waiting for the name box, shown once Grasshopper is idle


def log(msg):
    Rhino.RhinoApp.WriteLine("basshopper: name new params: " + str(msg))


def is_on():
    return bool(Grasshopper.Instances.Settings.GetValue(SETTING, False))


def find_button():
    editor = Grasshopper.Instances.DocumentEditor
    found = editor.Controls.Find("CanvasToolbar", True) if editor else None
    if not found:
        return None
    for item in found[0].Items:
        if item.Name == BUTTON_NAME:
            return item
    return None


def update_button():
    button = find_button()
    if button is None:
        return
    on = is_on()
    button.Checked = on
    button.ToolTipText = ("Name new params ({})\nAsk for a name when you place a param with its default name"
                          .format("on" if on else "off"))


def set_on(on):
    Grasshopper.Instances.Settings.SetValue(SETTING, on)
    update_button()
    log("on" if on else "off")


# ---------------------------------------------------------------- listener

def is_param_object(obj):
    # A param from the Params tab. Panels, sliders, toggles, value lists and other
    # Kernel.Special objects are params too, but are skipped.
    if not isinstance(obj, IGH_Param) or obj.Attributes is None or not obj.Attributes.HasInputGrip:
        return False
    namespace = obj.GetType().Namespace or ""
    return not namespace.startswith("Grasshopper.Kernel.Special")


def placed_by_user():
    for frame in System.Diagnostics.StackTrace(False).GetFrames():
        method = frame.GetMethod()
        if method is not None and method.Name in PLACE_METHODS:
            return True
    return False


def has_default_name(param):
    if param.NickName == param.Name:
        return True
    fresh = Grasshopper.Instances.ComponentServer.EmitObject(param.ComponentGuid)
    return fresh is not None and param.NickName == fresh.NickName


def on_objects_added(sender, args):
    try:
        if not is_on() or not placed_by_user():
            return
        params = [o for o in args.Objects if is_param_object(o)]
        if not params:
            return
        if not pending:
            Rhino.RhinoApp.Idle += on_idle
        pending.extend((args.Document, p) for p in params)
    except Exception:
        log(traceback.format_exc())


def on_idle(sender, args):
    # Wait until the placement (e.g. a drag from the ribbon) is finished before showing a box.
    Rhino.RhinoApp.Idle -= on_idle
    queue = list(pending)
    del pending[:]
    for doc, param in queue:
        try:
            if doc.FindObject(param.InstanceGuid, True) is None or not has_default_name(param):
                continue  # deleted, or named already (e.g. by a script)
            name = ask_name(param)
            if name:
                param.NickName = name
                param.Attributes.ExpireLayout()
        except Exception:
            log(traceback.format_exc())


def screen_point(param):
    # Just below the new param on screen, or at the mouse if that fails.
    try:
        canvas = Grasshopper.Instances.ActiveCanvas
        bounds = param.Attributes.Bounds
        p = canvas.Viewport.ProjectPoint(SD.PointF(bounds.Left, bounds.Bottom))
        return canvas.PointToScreen(SD.Point(int(p.X), int(p.Y) + 8))
    except Exception:
        return WF.Cursor.Position


def ask_name(param):
    form = WF.Form()
    form.Text = "Name " + param.Name
    form.FormBorderStyle = WF.FormBorderStyle.FixedToolWindow
    form.ShowInTaskbar = False
    form.StartPosition = WF.FormStartPosition.Manual
    form.AutoScaleMode = WF.AutoScaleMode.Font
    form.ClientSize = SD.Size(260, 64)

    box = WF.TextBox()
    box.SetBounds(8, 8, 244, 22)
    ok = WF.Button()
    ok.Text = "OK"
    ok.DialogResult = WF.DialogResult.OK
    ok.SetBounds(96, 34, 75, 24)
    cancel = WF.Button()
    cancel.Text = "Default"
    cancel.DialogResult = WF.DialogResult.Cancel
    cancel.SetBounds(177, 34, 75, 24)
    for control in (box, ok, cancel):
        form.Controls.Add(control)
    form.AcceptButton = ok
    form.CancelButton = cancel
    form.Location = screen_point(param)

    result = form.ShowDialog(Grasshopper.Instances.DocumentEditor)
    name = box.Text.strip()
    form.Dispose()
    return name if result == WF.DialogResult.OK else ""


def attach(doc):
    detach(doc, on_objects_added)
    doc.ObjectsAdded += on_objects_added


def detach(doc, handler):
    try:
        doc.ObjectsAdded -= handler
    except Exception:
        pass


def on_document_added(sender, doc):
    attach(doc)


def on_document_removed(sender, doc):
    detach(doc, on_objects_added)


def documents():
    server = Grasshopper.Instances.DocumentServer
    return [server[i] for i in range(server.DocumentCount)]


def install_listener():
    server = Grasshopper.Instances.DocumentServer
    old = getattr(sys, STATE, None)
    if old:
        for doc in documents():
            detach(doc, old["objects_added"])
        try:
            server.DocumentAdded -= old["document_added"]
            server.DocumentRemoved -= old["document_removed"]
        except Exception:
            pass
    server.DocumentAdded += on_document_added
    server.DocumentRemoved += on_document_removed
    for doc in documents():
        attach(doc)
    setattr(sys, STATE, {"objects_added": on_objects_added,
                         "document_added": on_document_added,
                         "document_removed": on_document_removed})
    update_button()
    log("listener installed ({})".format("on" if is_on() else "off"))


# ---------------------------------------------------------------- button

def show_menu():
    if getattr(sys, STATE, None) is None:
        install_listener()  # e.g. the toolbar was loaded by an older loader
    menu = WF.ContextMenuStrip()
    on = is_on()
    for label, value in (("On", True), ("Off", False)):
        item = WF.ToolStripMenuItem(label)
        item.Checked = on == value
        item.Click += (lambda v: lambda s, e: set_on(v))(value)
        menu.Items.Add(item)
    button = find_button()
    if button is not None and button.Owner is not None:
        menu.Show(button.Owner, SD.Point(button.Bounds.Left, button.Bounds.Bottom))
    else:
        menu.Show(WF.Cursor.Position)


if __name__ == "__main__":
    show_menu()
