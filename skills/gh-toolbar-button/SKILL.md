---
name: gh-toolbar-button
description: Add a button with a custom SVG icon to Grasshopper's canvas toolbar (the one with the preview and zoom buttons) that runs a basshopper Python script from the tools folder, with left/right-click actions, number-key shortcuts, On/Off listener tools and input boxes. Use when asked to put a tool script on the Grasshopper toolbar or ribbon, or to build a Grasshopper tool that reacts to pastes, placements or keys.
---

# Grasshopper toolbar button for a basshopper tool

Add a script in `tools/` as a button on Grasshopper's canvas toolbar. For the Rhino toolbar, see the `rhino-toolbar-button` skill. Both use the same script and icon.

## Ground rules from the user

- **Speed is important.** Use the loader and patterns below as-is. Don't re-explore the Grasshopper window or screenshot it unless something fails.
- **No recompute or refresh in tool scripts.** Scripts in `tools/` must not call `NewSolution`, `ExpireSolution(True)`, `ScheduleSolution`, `canvas.Refresh()`, `Instances.RedrawCanvas()` or `doc.Views.Redraw()`. Remove any you find in a script you're wiring up. Allowed: `Attributes.ExpireLayout()` after a rename, and `param.ExpireSolution(False)` after a new wire (marks it for the next solution, starts none). The one agreed exception: `canvas.Invalidate()` for Typed wiring's preview wire (a repaint, not a recompute).
- **The user tests in Grasshopper.** Don't build test definitions or run tools on the canvas. Hand it over with "click **Reload GH toolbar** in Rhino". Pure-Python logic (name matching etc.) can be tested offline with stub modules; see "Testing" below.
- **Commit to `main` and push only when asked.** Leave `examples/` and `random/` out.

## Steps

1. **Read the script** in `tools/` and apply the no-refresh rule above.
2. **Icon:** reuse `tools/icons/<script_name>.svg`. If there isn't one yet, design it following the icon rules in the `rhino-toolbar-button` skill.
3. **Register the tool:** append one tuple to `BUTTONS` in [startup/gh_canvas_toolbar.py](../../startup/gh_canvas_toolbar.py):
   ```python
   ("<Tool name>", "<Tool name>\n<what it does>\nLeft-click: ...\nRight-click: ...",
    "<script>.py", "<script>.svg"[, "<right-click script>.py"]),
   ```
   The optional 5th item is the right-click script; it may be the same file (see "Script globals").
   A tool that must listen all session (pastes, placements, keys) also goes in `LISTENERS` as `("<script>.py", "install_listener")`.
4. **Reload:** the user clicks **Reload GH toolbar** (a Rhino Standard-toolbar button that reruns the loader). If the Rhino MCP is connected (`list_slots` shows the user's Rhino), one `run_python` call also works:
   ```python
   import Rhino
   Rhino.RhinoApp.RunScript(r'_-ScriptEditor _Run "C:\Users\basdejong\Git\basshopper\startup\gh_canvas_toolbar.py"', False)
   ```
   Don't auto-spawn a separate Rhino for this; ask first.
5. **Report:** the button's place and number key (below), its left/right actions, and what wasn't verified.

## How the loader works

- It adds `ToolStripButton`s to the `CanvasToolbar` control of `Grasshopper.Instances.DocumentEditor` (icons rendered from the SVG with `Rhino.UI.DrawingUtilities.BitmapFromSvg`), after a separator. Each item is named `basshopper:<name>`, so a rerun replaces them: it doubles as a reload.
- A click runs the tool in-process with `exec`: faster than the Script Editor, and always the file on disk. Errors go to the command line as `basshopper: <file> failed: ...`.
- `Click` is left-button only. The right-click script runs from `MouseUp` with `MouseButtons.Right`.
- **Number keys follow `BUTTONS` order:** button n gets key n (1-9, then 0 for the 10th). Plain digit = left-click action, Shift+digit = right-click action. The handler sits on the editor's `KeyDown` (it has `KeyPreview`), and ignores keys while a text field has focus (panel, rename, search, zoom box: follow `ActiveControl` down and skip `TextBoxBase`/`ComboBox`), and with Ctrl/Alt. Grasshopper itself uses Ctrl+1/2/3, Ctrl+(Shift+)letters and Ctrl+(Shift+)arrows; plain and Shift+digits are free.
- `button.Tag` holds the key hint ("Key: 5 / Shift+5 (right-click)"); tools that rewrite their own tooltip append it.
- **Grasshopper doesn't save these buttons.** The loader runs once per Rhino session from Rhino's startup commands (Options > General > Command lists):
  `_-ScriptEditor _Run "C:\Users\basdejong\Git\basshopper\startup\gh_canvas_toolbar.py"`
  If Grasshopper isn't open yet, it waits for `Instances.CanvasCreated` and the next Rhino idle.

### Script globals

`run_tool` executes the script with `__name__ == "__main__"` plus:
- `MOUSE_BUTTON`: `"left"` or `"right"` (Shift+digit counts as right),
- `TRIGGER`: `"click"` or `"key"`.

Read them with `globals().get(...)` or a `try/except NameError` default, so the script also runs outside the toolbar.

## Patterns

### On/Off tools (listeners)

Paste link, Name new params and Typed wiring follow one template; copy it from [tools/paste_link_params.py](../../tools/paste_link_params.py):
- The setting lives in `Grasshopper.Instances.Settings` (`"basshopper:<Name>"`), so it survives restarts. The button shows `Checked` when on, and its tooltip says "(on)/(off)" plus the key hint.
- `install_listener()` attaches `ObjectsAdded` to every document and to new ones (`DocumentServer.DocumentAdded/Removed`). It keeps the live handlers in a `sys` attribute (`_basshopper_<tool>`) so a reload can detach the old ones first. Expose functions other tools need in that dict (e.g. Name new params' `name_param`).
- Mapping: left-click = On/Off menu (`ContextMenuStrip` under the button); right-click / plain key / Shift+key = flip on/off. A tool with a real action (Typed wiring) uses left-click/plain key for the action and right-click/Shift+key for on/off.

### Telling what added an object

`ObjectsAdded` fires synchronously inside the call that added the object, so inspect `System.Diagnostics.StackTrace(False)` method names:
- **Paste** (Ctrl+V, paste in place/center): a frame named `MnuPaste*`. The pasted copies get new IDs (`MutateAllIds`) but keep wires to outside sources. The clipboard still holds the originals' IDs in the same order: `io = GH_DocumentIO(); io.Paste(GH_ClipboardType.System); io.Document.Objects`. Grasshopper recomputes right after the paste, so rewiring inside the handler needs no solution.
- **User placement** (ribbon click/drag, double-click search): `InstantiateNewObject` or `InsertComponent` (+ `Menu_ExtractParameterClicked` for Extract parameter).
- Anything else (undo/redo, Alt-drag copies, dropped files, scripts) has neither, and should be ignored.
- Show boxes from a one-shot `Rhino.RhinoApp.Idle` handler, not inside `ObjectsAdded`, so the drag or placement finishes first.
- The click that drops a ribbon item or opens the search deselects everything, so at placement time the earlier selection is gone. Remember clicked selections from the canvas `MouseUp` event.

### Which objects count as a "param"

`is_param_object`: an `IGH_Param` with `Attributes.HasInputGrip`, whose type isn't in the `Grasshopper.Kernel.Special` namespace. That excludes panels, sliders, toggles, value lists and the like, which are `IGH_Param` too. Default name check: `NickName == Name`, or equal to `Instances.ComponentServer.EmitObject(ComponentGuid).NickName`.

### Boxes (WinForms forms)

- Show them with `ShowDialog(Grasshopper.Instances.DocumentEditor)`, `FixedToolWindow`, positioned near the object (`canvas.Viewport.ProjectPoint` → `canvas.PointToScreen`).
- **Always clamp the position to `Screen.FromControl(editor).WorkingArea`** (`on_screen()` in the tools). A modal box that opens off-screen blocks Rhino and looks like a hang. When the user reports a hang, list Rhino's windows (Win32 `EnumWindows`) to find a hidden box before anything else.
- Keys: handle the text box's `KeyDown`, set `e.Handled` and `e.SuppressKeyPress`. Typed wiring: two digits wire instantly from `TextChanged`, Space = Enter, arrows pick while the field is empty. Output params: a `CheckedListBox` with form `KeyPreview`, digits tick rows.
- Keep an error label in the box and leave it open on bad input, instead of closing.

### Wires, new params, undo

- Wire: `actions.Add(GH_WireAction(target))` before `target.AddSource(source)`, then `target.ExpireSolution(False)`.
- New param of an output's type: `concrete(ComponentServer.EmitObject(output.ComponentGuid))`, `CreateAttributes()`, place it (pivot at 0, `PerformLayout`, then offset), `doc.AddObject(p, False)`, `GH_AddObjectAction(p)`.
- One undo step: `doc.UndoServer.PushUndoRecord(GH_UndoRecord("<name>", actions))` with `actions = List[IGH_UndoAction]()`.
- Pivot moves: `doc.UndoUtil.RecordPivotEvent(name, doc.SelectedObjects())`. Pass the .NET list, not a Python list.
- Preview drawing: subscribe to `canvas.CanvasPostPaintWires(canvas)`, draw on `canvas.Graphics` (already in canvas coordinates) with `GH_Painter.ConnectionPath(a, b, GH_WireDirection.right, GH_WireDirection.left)`, `canvas.Invalidate()` to repaint, and unsubscribe in `finally`.

## pythonnet pitfalls (Rhino 8 CPython)

- **Never compare .NET objects with `is`.** Each access returns a new Python wrapper, so `doc is other_doc` is always False. Compare IDs (`DocumentID`, `InstanceGuid`) or use `==`. This bug made Typed wiring's memory look empty.
- Objects returned as an interface (`EmitObject`, `SelectedObjects()` items) may be wrapped as that interface: unwrap with `getattr(obj, "__implementation__", obj)` before using type-specific members.
- `isinstance(obj, IGH_Param)` / `IGH_Component` works on interfaces, also with a tuple.
- Import sub-namespaces explicitly (`from System.Drawing.Drawing2D import DashStyle`); don't rely on `SD.Drawing2D`.
- Event handlers: keep the Python function object to `-=` it later; wrap `-=` in try/except.

## Looking into Grasshopper itself

The Rhino MCP is often not connected to the user's Rhino. To learn how Grasshopper does something, reflect over `C:\Program Files\Rhino 8\Plug-ins\Grasshopper\Grasshopper.dll` from Windows PowerShell 5.1:
- Load it with an `AssemblyResolve` handler that looks in `C:\Program Files\Rhino 8\System`, the Grasshopper folder and `System\netfx`.
- List the methods a method calls by scanning its IL for `call`/`callvirt`/`newobj` tokens (`ResolveMember`).
- Menu shortcuts: scan `GH_DocumentEditor.InitializeComponent` for `ldc.i4` before `set_ShortcutKeys`.

## Testing

Matching and parsing logic can run under plain Python. Stub `Grasshopper`, `Rhino` and `System*` with `types.ModuleType` entries in `sys.modules`, define fake `IGH_Param`/`IGH_Component` classes, and `exec` the part of the tool above its UI section. Keep such tests in the scratchpad, not the repo. Always finish with a syntax check (`ast.parse`) of every edited script.

## Tool map (current)

| Key | Button | Plain / left-click | Shift / right-click |
|---|---|---|---|
| 1 | Param depth suffix | add `-[n]` suffix | – |
| 2 | Cluster with params | cluster + outside params | – |
| 3 | Paste link | key: on/off · click: menu | on/off |
| 4 | Name new params | key: on/off · click: menu | on/off |
| 5 | Input wires | hide incoming wires | show them |
| 6 | Organize nodes | stack, align left | align right |
| 7 | Typed wiring | wire now (also Ctrl+Shift+L) | key: on/off · click: menu |
| 8 | Output params | tick list → params for outputs | – |

Tools that need a name from the user call Name new params' box when that tool is on (`sys._basshopper_name_new_params["name_param"]`). When Typed wiring is on, Name new params leaves naming of placed params to Typed wiring, which asks after wiring if the name is still default.
