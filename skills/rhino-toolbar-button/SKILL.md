---
name: rhino-toolbar-button
description: Add a left-click button with a custom SVG icon to a Rhino 8 toolbar (e.g. "Standard") that runs a basshopper Python script from the tools folder. Use when asked to put a tool script on a Rhino toolbar or ribbon, or to design or update a toolbar icon for one.
---

# Rhino toolbar button for a basshopper tool

Wire a script in `tools/` to a Rhino 8 toolbar button with a matching icon, through the Rhino MCP.

## Ground rules from the user

- **Speed is important.** Use the installer and steps below as-is. Don't re-explore Rhino's toolbar internals, read old session transcripts or screenshot the toolbar unless something fails.
- **No recompute or refresh in tool scripts.** Scripts in `tools/` must not call `NewSolution`, `ExpireSolution(True)`, `ScheduleSolution`, `canvas.Refresh()`, `Instances.RedrawCanvas()` or `doc.Views.Redraw()`. Remove any you find in the script you're wiring up. `Attributes.ExpireLayout()` after a rename is fine: it only marks the box for resizing at the next redraw and doesn't redraw anything itself.
- **The user tests in Grasshopper.** Don't build test definitions or run the tool on the canvas. Install the button and hand it over.

## Steps

1. **Read the script** in `tools/` and apply the no-refresh rule above.
2. **Design the icon** as `tools/icons/<script_name>.svg` (see "Icon rules"). If one exists, check it against the rules and redesign it if it falls short.
3. **Render-check the icon** with one `run_python` call (below) and look at the PNG. Fix it and render again if needed; that's usually one round.
4. **Install** with one `run_python` call:
   ```python
   exec(open(r"C:\Users\basdejong\Git\basshopper\skills\rhino-toolbar-button\install_toolbar_button.py", encoding="utf-8").read())
   install_button(
       script_path=r"C:\Users\basdejong\Git\basshopper\tools\<script>.py",
       svg_path=r"C:\Users\basdejong\Git\basshopper\tools\icons\<script>.svg",
       name="<Tool name>",                # tooltip and button text
       help_text="<one line: what it does>",
       toolbar="Standard",                # default
   )
   ```
   It is idempotent. If a button on that toolbar already runs the script, it only swaps the icon. The first time it touches the workspace file each day, it writes a `.bak-YYYYMMDD` copy next to it.
5. **Report** to the user: the button is at the end of the toolbar, the button command, and that a changed icon only shows after a Rhino restart.

## Icon rules

- `viewBox="0 0 32 32"`, plain shapes only: `path`, `rect`, `circle`, `polyline`. No `<text>`: draw letters and digits as paths.
- **Fill the square.** Rhino shows buttons at about 24 px, and a wide, flat drawing looks tiny next to Rhino's own icons. Use roughly y 5–27 and keep everything inside x/y 1–31, or round caps get clipped.
- Strokes of 1.6–2.3 px; anything thinner disappears at 16 px.
- House style: a light grey capsule (`#E6E6E6`, outline `#2B2B2B`) for Grasshopper objects, with the meaning in blue (`#1F6FEB`). The filled capsule keeps it readable in dark mode, so one SVG serves both themes.
- Show what the tool does (e.g. `[2]` on a parameter capsule fed by a forked wire = "branch-depth suffix"), not a generic symbol.

Render check (16, 24, 32 and 128 px, on light and dark backgrounds, scaled up for inspection):
```python
import Rhino, System
svg = open(r"<svg path>", encoding="utf-8").read()
sheet = System.Drawing.Bitmap(560, 280); g = System.Drawing.Graphics.FromImage(sheet)
g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.NearestNeighbor
for row, bg in enumerate((System.Drawing.Color.FromArgb(240,240,240), System.Drawing.Color.FromArgb(45,45,48))):
    g.FillRectangle(System.Drawing.SolidBrush(bg), 0, row*140, 560, 140)
    for i, s in enumerate((16, 24, 32, 128)):
        g.DrawImage(Rhino.UI.DrawingUtilities.BitmapFromSvg(svg, s, s), System.Drawing.Rectangle(i*140+6, row*140+6, 128, 128))
sheet.Save(r"<scratchpad>\icon_check.png")
```

## What was learned the hard way (don't redo it)

- **Where toolbars live:** Rhino 8's Standard toolbar is in the built-in workspace `default.rui`, which is embedded in `Rhino.UI.dll` (file id `c7da84fc-2991-4824-832a-4f2509bd0ede`). Your changes are stored as a diff in `%AppData%\McNeel\Rhinoceros\8.0\settings\Scheme__Default\Rhino.UI.Resources.rui.default_c7da84fc-….xml`. Rhino rewrites that file when it closes, so **don't hand-edit it**; go through the live model like the installer does.
- **The live model** is `Rhino.UI.Internal.TabPanels.ToolBarFileController` (internal, so reached through reflection). `MacrosController.AddNewMacro(MacroViewModel)` creates the macro *and* its SVG icon. `ToolBarController.NewItem(macro)` appends the button. `WriteXmlDiffFile()` saves.
- **Dead ends:** RhinoCommon's `Rhino.UI.ToolbarFile` is read-only, and `Toolbars.RuiFileCollection` (Toolbars.dll) is empty in Rhino 8.
- **Icon cache:** after an icon changes, the toolbar keeps showing the cached image until Rhino restarts. The saved data is correct.
- **Button command:** `! _-ScriptEditor _Run "<full path>"`. This runs `#! python3` scripts. The path is absolute, so moving the repo breaks the button.
- **pythonnet:** create internal types with `ConstructorInfo.Invoke`, because `Activator.CreateInstance` picks the wrong overload.
- **Screenshots (only if needed):** VS Code usually covers Rhino, so `CopyFromScreen` captures the wrong window. Use `PrintWindow(RhinoApp.MainWindowHandle(), hdc, 2)` instead.

For the Grasshopper canvas toolbar, see the separate `gh-toolbar-button` skill.
