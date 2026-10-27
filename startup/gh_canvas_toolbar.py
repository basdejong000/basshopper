#! python3
"""Add basshopper tool buttons to Grasshopper's canvas toolbar (the one with the
preview and zoom buttons).

Grasshopper doesn't save these buttons, so this has to run once per Rhino session.
Add it to Rhino's startup commands (Options > General > Command lists):
    _-ScriptEditor _Run "C:\\Users\\basdejong\\Git\\basshopper\\startup\\gh_canvas_toolbar.py"

If Grasshopper isn't open yet, the buttons are added as soon as it opens.
Running it again replaces the buttons, so it doubles as a reload.
"""
import os

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
     "Paste link\nWire pasted parameters to the parameter they were copied from (On/Off)",
     "paste_link_params.py", "paste_link_params.svg"),
    ("Name new params",
     "Name new params\nAsk for a name when you place a param with its default name (On/Off)",
     "name_new_params.py", "name_new_params.svg"),
    ("Input wires",
     "Input wires\nLeft-click: hide the incoming wires of the selection\nRight-click: show them again",
     "input_wires.py", "input_wires.svg", "input_wires.py"),
    ("Organize nodes",
     "Organize nodes\nStack the selection vertically, keeping its order\nLeft-click: align left\nRight-click: align right",
     "organize_nodes.py", "organize_nodes.svg", "organize_nodes.py"),
]

# Tools with a listener that has to run all session, not only on a click: (script, function).
LISTENERS = [
    ("paste_link_params.py", "install_listener"),
    ("name_new_params.py", "install_listener"),
]


def log(msg):
    Rhino.RhinoApp.WriteLine("basshopper: " + str(msg))


def run_tool(path, mouse_button="left"):
    # Execute the tool in-process: faster than the Script Editor, and always the file as it is now.
    try:
        with open(path, encoding="utf-8") as f:
            code = compile(f.read(), path, "exec")
        exec(code, {"__name__": "__main__", "__file__": path, "MOUSE_BUTTON": mouse_button})
    except Exception as e:
        log("{} failed: {}".format(os.path.basename(path), e))


def make_button(name, tooltip, script, icon, size, right_script=None):
    script_path = os.path.join(REPO, "tools", script)
    button = WF.ToolStripButton()
    button.Name = TAG + name
    button.ToolTipText = tooltip
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
    for name, tooltip, script, icon, *right in BUTTONS:
        toolbar.Items.Add(make_button(name, tooltip, script, icon, toolbar.ImageScalingSize, *right))
    log("{} button(s) added to the Grasshopper toolbar".format(len(BUTTONS)))
    for script, function in LISTENERS:
        install_listener(script, function)
    return True


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
