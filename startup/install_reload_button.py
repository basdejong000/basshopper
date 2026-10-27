#! python3
"""One-off: put a "Reload GH toolbar" button on Rhino's Standard toolbar.
The button runs startup/gh_canvas_toolbar.py, which (re)adds the basshopper
buttons to the Grasshopper canvas toolbar.

Run once from Rhino 8:
    _-ScriptEditor _Run "C:\\Users\\basdejong\\Git\\basshopper\\startup\\install_reload_button.py"
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

exec(open(os.path.join(REPO, "skills", "rhino-toolbar-button", "install_toolbar_button.py"),
          encoding="utf-8").read())
install_button(
    script_path=os.path.join(REPO, "startup", "gh_canvas_toolbar.py"),
    svg_path=os.path.join(REPO, "startup", "icons", "gh_canvas_toolbar.svg"),
    name="Reload GH toolbar",
    help_text="Reload the basshopper buttons on the Grasshopper canvas toolbar",
    toolbar="Standard",
)
