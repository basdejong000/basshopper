#! python3
"""Add basshopper tool buttons to Grasshopper's canvas toolbar (the one with the
preview and zoom buttons).

Grasshopper doesn't save these buttons, so this has to run once per Rhino session.
Add it to Rhino's startup commands (Options > General > Command lists):
    _-ScriptEditor _Run "C:\\Users\\basdejong\\Git\\basshopper\\startup\\gh_canvas_toolbar.py"

If Grasshopper isn't open yet, the buttons are added as soon as it opens.
Running it again replaces the buttons, so it doubles as a reload.

Number keys follow the button order: 1 = the first button's left-click, Shift+1 its
right-click (when it has one), ... 9, then 0 for the 10th. They only work while the canvas
has focus, never while you type text (panels, renaming, search).
"""
import os
import sys

import Grasshopper
import Rhino
import System
import System.Windows.Forms as WF

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = "basshopper:"

# (button name, tooltip, script in tools/, icon in tools/icons/[, right-click script in tools/])
# A script can read MOUSE_BUTTON ("left" or "right"), so one file can serve both clicks.
BUTTONS = [
    ("Param depth suffix",
     "Param depth suffix\nAdd a -[n] branch-depth suffix to the selected parameters",
     "param_depth_suffix.py", "param_depth_suffix.svg"),
    ("Cluster with params",
     "Cluster with params\nCluster the selection and repeat its boundary parameters outside the cluster",
     "cluster_with_params.py", "cluster_with_params.svg"),
    ("Paste link",
     "Paste link\nWire pasted parameters to the parameter they were copied from\n"
     "Left-click: On/Off menu\nRight-click: switch on/off",
     "paste_link_params.py", "paste_link_params.svg", "paste_link_params.py"),
    ("Name new params",
     "Name new params\nAsk for a name when you place a param with its default name\n"
     "Left-click: On/Off menu\nRight-click: switch on/off",
     "name_new_params.py", "name_new_params.svg", "name_new_params.py"),
    ("Input wires",
     "Input wires\nLeft-click: hide the incoming wires of the selection\nRight-click: show them again",
     "input_wires.py", "input_wires.svg", "input_wires.py"),
    ("Organize nodes",
     "Organize nodes\nStack the selection vertically, keeping its order\nLeft-click: align left\nRight-click: align right",
     "organize_nodes.py", "organize_nodes.svg", "organize_nodes.py"),
    ("Typed wiring",
     "Typed wiring\nWire two objects by typing names, e.g. C-Crv\n"
     "Left-click or Ctrl+Shift+L: wire the selection / last two placed now\n"
     "Right-click: On/Off menu (open the box after every placement)",
     "typed_wiring.py", "typed_wiring.svg", "typed_wiring.py"),
    ("Output params",
     "Output params\nMake params for outputs of the selected component(s)\n"
     "Digits tick outputs, Enter/Space makes them",
     "output_params.py", "output_params.svg"),
]

# Tools with a listener that has to run all session, not only on a click: (script, function).
LISTENERS = [
    ("paste_link_params.py", "install_listener"),
    ("name_new_params.py", "install_listener"),
    ("typed_wiring.py", "install_listener"),
]


KEY_LABELS = "1234567890"  # button n gets KEY_LABELS[n]; buttons after the 10th get no key
DIGIT_KEYS = [getattr(WF.Keys, "D" + c) for c in KEY_LABELS]
NUMPAD_KEYS = [getattr(WF.Keys, "NumPad" + c) for c in KEY_LABELS]
HOTKEY_STATE = "_basshopper_hotkeys"  # sys attribute with the live key handler, so a reload can detach it


def log(msg):
    Rhino.RhinoApp.WriteLine("basshopper: " + str(msg))


def run_tool(path, mouse_button="left", trigger="click"):
    # Execute the tool in-process: faster than the Script Editor, and always the file as it is now.
    # TRIGGER tells the tool whether a click or a number key ran it (toggles flip on a key).
    try:
        with open(path, encoding="utf-8") as f:
            code = compile(f.read(), path, "exec")
        exec(code, {"__name__": "__main__", "__file__": path,
                    "MOUSE_BUTTON": mouse_button, "TRIGGER": trigger})
    except Exception as e:
        log("{} failed: {}".format(os.path.basename(path), e))


def key_hint(index, has_right):
    if index >= len(KEY_LABELS):
        return ""
    key = KEY_LABELS[index]
    return "Key: {}{}".format(key, " / Shift+{} (right-click)".format(key) if has_right else "")


def make_button(name, tooltip, script, icon, size, right_script=None, hint=""):
    script_path = os.path.join(REPO, "tools", script)
    button = WF.ToolStripButton()
    button.Name = TAG + name
    button.Tag = hint  # toggle tools rewrite their tooltip and append this
    button.ToolTipText = tooltip + ("\n" + hint if hint else "")
    button.DisplayStyle = WF.ToolStripItemDisplayStyle.Image
    with open(os.path.join(REPO, "tools", "icons", icon), encoding="utf-8") as f:
        button.Image = Rhino.UI.DrawingUtilities.BitmapFromSvg(f.read(), size.Width, size.Height)
    button.Click += lambda sender, args: run_tool(script_path)  # Click is left-button only
    if right_script:
        right_path = os.path.join(REPO, "tools", right_script)

        def on_mouse_up(sender, args):
            if args.Button == WF.MouseButtons.Right:
                run_tool(right_path, "right")

        button.MouseUp += on_mouse_up
    return button


def install():
    editor = Grasshopper.Instances.DocumentEditor
    toolbar = editor.Controls.Find("CanvasToolbar", True) if editor else None
    if not toolbar:
        return False
    toolbar = toolbar[0]
    for item in [i for i in toolbar.Items if (i.Name or "").startswith(TAG)]:
        toolbar.Items.Remove(item)
    toolbar.Items.Add(WF.ToolStripSeparator())
    toolbar.Items[toolbar.Items.Count - 1].Name = TAG + "separator"
    actions = []  # per button: (left-click script path, right-click script path or None)
    for index, (name, tooltip, script, icon, *right) in enumerate(BUTTONS):
        right_script = right[0] if right else None
        hint = key_hint(index, bool(right_script))
        toolbar.Items.Add(make_button(name, tooltip, script, icon, toolbar.ImageScalingSize,
                                      right_script, hint))
        actions.append((os.path.join(REPO, "tools", script),
                        os.path.join(REPO, "tools", right_script) if right_script else None))
    log("{} button(s) added to the Grasshopper toolbar".format(len(BUTTONS)))
    install_hotkeys(actions)
    for script, function in LISTENERS:
        install_listener(script, function)
    return True


def typing_in_text():
    # Follow the focus down from the editor; text fields (panel/rename/zoom box) keep their keys.
    control = Grasshopper.Instances.DocumentEditor
    while isinstance(control, WF.ContainerControl) and control.ActiveControl is not None:
        control = control.ActiveControl
    return isinstance(control, (WF.TextBoxBase, WF.ComboBox))


def install_hotkeys(actions):
    editor = Grasshopper.Instances.DocumentEditor
    canvas = Grasshopper.Instances.ActiveCanvas
    # The editor sees keys first when it previews them; otherwise the canvas gets them.
    target = editor if editor is not None and editor.KeyPreview else canvas
    old = getattr(sys, HOTKEY_STATE, None)
    if old:
        try:
            old["target"].KeyDown -= old["handler"]
        except Exception:
            pass
    if target is None:
        return

    def on_key_down(sender, e):
        try:
            if e.Control or e.Alt or typing_in_text():
                return
            if e.KeyCode in DIGIT_KEYS:
                index = DIGIT_KEYS.index(e.KeyCode)
            elif e.KeyCode in NUMPAD_KEYS and not e.Shift:
                index = NUMPAD_KEYS.index(e.KeyCode)
            else:
                return
            if index >= len(actions):
                return
            path = actions[index][1] if e.Shift else actions[index][0]
            if path is None:
                return
            e.Handled = True
            e.SuppressKeyPress = True
            run_tool(path, "right" if e.Shift else "left", "key")
        except Exception as ex:
            log("hotkey failed: {}".format(ex))

    target.KeyDown += on_key_down
    setattr(sys, HOTKEY_STATE, {"target": target, "handler": on_key_down})


def install_listener(script, function):
    path = os.path.join(REPO, "tools", script)
    try:
        with open(path, encoding="utf-8") as f:
            code = compile(f.read(), path, "exec")
        namespace = {"__name__": "basshopper_listener", "__file__": path}
        exec(code, namespace)
        namespace[function]()
    except Exception as e:
        log("{} listener failed: {}".format(script, e))


def on_idle(sender, args):
    # The canvas exists before the editor finishes building its toolbar; wait until Rhino is idle.
    Rhino.RhinoApp.Idle -= on_idle
    install()


def on_canvas_created(canvas):
    Grasshopper.Instances.CanvasCreated -= on_canvas_created
    Rhino.RhinoApp.Idle += on_idle


if not install():
    Grasshopper.Instances.CanvasCreated += on_canvas_created
    log("buttons will be added when Grasshopper opens")
