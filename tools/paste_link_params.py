#! python3
"""Paste link: a pasted parameter is wired to the parameter it was copied from,
instead of keeping that parameter's input wires.

- Only params from the Params tab: not components, panels, sliders or other special objects.
- Only when the paste is params alone (one or several); a mixed paste is left as it is.
- Each pasted param links to its own original, even if it was wired to another pasted param.
- Pasting into another file leaves the copy alone (the original isn't there).

Clicking the canvas toolbar button runs this file and opens an On/Off menu.
The listener itself is installed by startup/gh_canvas_toolbar.py.
The On/Off choice is saved in Grasshopper's settings, so it survives a restart.
"""
import sys
import traceback

import Grasshopper
import Rhino
import System
import System.Windows.Forms as WF
from Grasshopper.Kernel import GH_ClipboardType, GH_DocumentIO, IGH_Param
from Grasshopper.Kernel.Special import GH_Group

SETTING = "basshopper:PasteLink"
BUTTON_NAME = "basshopper:Paste link"
STATE = "_basshopper_paste_link"  # sys attribute with the live handlers, so a reload can detach them


def log(msg):
    Rhino.RhinoApp.WriteLine("basshopper: paste link: " + str(msg))


def is_on():
    return bool(Grasshopper.Instances.Settings.GetValue(SETTING, True))


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
    button.ToolTipText = ("Paste link ({})\nWire pasted parameters to the parameter they were copied from"
                          .format("on" if on else "off")) + key_hint(button)


def key_hint(button):
    # The toolbar loader stores the button's number key in Tag.
    hint = button.Tag
    return "\n" + hint if isinstance(hint, str) and hint else ""


def set_on(on):
    Grasshopper.Instances.Settings.SetValue(SETTING, on)
    update_button()
    log("on" if on else "off")


# ---------------------------------------------------------------- listener

def called_from_paste():
    # Ctrl+V and the Edit menu both run GH_DocumentEditor.MnuPaste*Click (Paste, Paste in place,
    # Paste in center). Anything else that adds objects (toolbar drag, undo, open file) doesn't.
    for frame in System.Diagnostics.StackTrace(False).GetFrames():
        method = frame.GetMethod()
        if method is not None and method.Name.startswith("MnuPaste"):
            return True
    return False


def is_param_object(obj):
    # A param from the Params tab: a standalone parameter with an input grip. Panels, sliders,
    # toggles, value lists and other Kernel.Special objects are params too, but are skipped.
    if not isinstance(obj, IGH_Param) or obj.Attributes is None or not obj.Attributes.HasInputGrip:
        return False
    namespace = obj.GetType().Namespace or ""
    return not namespace.startswith("Grasshopper.Kernel.Special")


def link_pasted(doc, pasted):
    # Read the clipboard the same way Grasshopper's paste does. Those objects still carry the
    # original IDs, in the same order as the pasted copies (which got new IDs).
    io = GH_DocumentIO()
    if not io.Paste(GH_ClipboardType.System) or io.Document is None:
        return
    originals = list(io.Document.Objects)
    if len(originals) != len(pasted):
        return
    # Only a paste of params alone (one, or several): anything else in it, and nothing is linked.
    # Group frames around the params don't count.
    pairs = [(c, s) for c, s in zip(pasted, originals) if not isinstance(c, GH_Group)]
    if not pairs or not all(is_param_object(c) and c.ComponentGuid == s.ComponentGuid for c, s in pairs):
        return
    # Each param links to its own original, even if it was wired to another pasted param.
    links = []
    for copy, source in pairs:
        original = doc.FindObject(source.InstanceGuid, True)
        if original is None or not is_param_object(original):
            continue
        links.append((copy, original))
    for copy, original in links:
        copy.RemoveAllSources()
        copy.AddSource(original)
    linked = len(links)
    # No solution needed: Grasshopper's paste recomputes right after adding the objects.
    if linked:
        log("linked {} pasted parameter(s)".format(linked))


def on_objects_added(sender, args):
    try:
        if is_on() and called_from_paste():
            link_pasted(args.Document, list(args.Objects))
    except Exception:
        log(traceback.format_exc())


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
        menu.Show(button.Owner, System.Drawing.Point(button.Bounds.Left, button.Bounds.Bottom))
    else:
        menu.Show(WF.Cursor.Position)


if __name__ == "__main__":
    if globals().get("TRIGGER") == "key":
        if getattr(sys, STATE, None) is None:
            install_listener()
        set_on(not is_on())  # number key: just flip it
    else:
        show_menu()
