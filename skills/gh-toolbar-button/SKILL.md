---
name: gh-toolbar-button
description: Add a button with a custom SVG icon to Grasshopper's canvas toolbar (the one with the preview and zoom buttons) that runs a basshopper Python script from the tools folder. Use when asked to put a tool script on the Grasshopper toolbar or ribbon.
---

# Grasshopper toolbar button for a basshopper tool

Add a script in `tools/` as a button on Grasshopper's canvas toolbar, through the Rhino MCP. For the Rhino toolbar, see the `rhino-toolbar-button` skill. Both use the same script and icon.

## Ground rules from the user

- **Speed is important.** Use the loader and steps below as-is. Don't re-explore the Grasshopper window or screenshot it unless something fails.
- **No recompute or refresh in tool scripts.** Scripts in `tools/` must not call `NewSolution`, `ExpireSolution(True)`, `ScheduleSolution`, `canvas.Refresh()`, `Instances.RedrawCanvas()` or `doc.Views.Redraw()`. Remove any you find in the script you're wiring up. `Attributes.ExpireLayout()` after a rename is fine: it only marks the box for resizing at the next redraw.
- **The user tests in Grasshopper.** Don't build test definitions or run the tool on the canvas. Add the button and hand it over.

## Steps

1. **Read the script** in `tools/` and apply the no-refresh rule above.
2. **Icon:** reuse `tools/icons/<script_name>.svg`. If there isn't one yet, design and render-check it following the icon rules in the `rhino-toolbar-button` skill.
3. **Register the tool:** append one tuple to `BUTTONS` in [startup/gh_canvas_toolbar.py](../../startup/gh_canvas_toolbar.py):
   ```python
   ("<Tool name>", "<Tool name>\n<one line: what it does>", "<script>.py", "<script>.svg"),
   ```
4. **Reload** with one `run_python` call (works with Grasshopper open or closed):
   ```python
   import Rhino
   Rhino.RhinoApp.RunScript(r'_-ScriptEditor _Run "C:\Users\basdejong\Git\basshopper\startup\gh_canvas_toolbar.py"', False)
   ```
   Expect `basshopper: N button(s) added to the Grasshopper toolbar` in the output.
5. **Report** to the user: the button sits after the basshopper separator on the canvas toolbar. Mention the startup command below if it isn't set up yet.

## How the loader works

- It adds `ToolStripButton`s to the `CanvasToolbar` control of `Grasshopper.Instances.DocumentEditor` (24 px icons, rendered from the SVG with `Rhino.UI.DrawingUtilities.BitmapFromSvg`), after a separator.
- Each item is named `basshopper:<name>`, so a rerun removes and re-adds them: it's safe to repeat and doubles as a reload.
- A click runs the tool in-process with `exec`. That's faster than the Script Editor and always uses the current file on disk. Errors go to the Rhino command line as `basshopper: <file> failed: ...`.
- **Grasshopper doesn't save these buttons.** The loader has to run once per Rhino session, through Rhino's startup commands (Options > General > Command lists). RhinoCommon has no API for those, so the user sets this once by hand:
  `_-ScriptEditor _Run "C:\Users\basdejong\Git\basshopper\startup\gh_canvas_toolbar.py"`
- If Grasshopper isn't open yet, the loader waits for `Grasshopper.Instances.CanvasCreated` and the next Rhino idle, because the toolbar is built after the canvas.
- Screenshots (only if needed): use `PrintWindow` on `DocumentEditor.Handle`, since VS Code usually covers the window.
