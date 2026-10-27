#! python3
"""Typed wiring: wire two objects by typing the short names of an output and an input.

The box lists the sender's outputs and the receiver's inputs, numbered, with the pick
highlighted and shown as a dashed preview wire on the canvas (it starts at 1st output ->
1st input). With the text field empty, Left/Right choose a side, Up/Down step through it,
and Enter wires the highlighted pair. Space works like Enter (so names can't contain a
space: type the start of the name instead). Typing moves the highlight too.

Quickest: two digits, output number then input number. 11 wires the 1st output to the
1st input, 32 the 3rd output to the 2nd input; it wires on the second digit, no Enter.
(Not for components with more than 9 inputs or outputs: use names there.)

Or type  output-input  and press Enter, e.g.  C-Crv  or  tA-P.  Several at once:  A-B,C-D.
Names are matched in this order:
  1. exact short name (case-sensitive)
  2. exact short or full name, ignoring case
  3. start of a short or full name, if only one name starts that way
  4. a number: 2-1 = 2nd output to 1st input
An ambiguous name wires nothing and lists the options. Dashes inside names (Pts-[2]) work:
every dash is tried as the separator, and the split where both sides match is used.
When the receiver is a standalone param, the part after the dash is its new name:
C-Pts wires output C into it and names it Pts; just  Pts  only renames it.

When the box opens:
- On (toolbar right-click menu, or Shift + its number key): right after you place an object
  from the ribbon or the double-click search. The sender is the object you selected or
  placed most recently.
- A left-click on the toolbar button, its number key, or Ctrl+Shift+L, any time: with two objects selected,
  the left one sends; with one selected, it receives from the object selected or placed
  before it; otherwise the last two objects selected or placed.
Enter wires, Esc closes. Ctrl+Z undoes the wires.

The listener is installed by startup/gh_canvas_toolbar.py.
"""
import sys
import traceback

import Grasshopper
import Rhino
import System
import System.Drawing as SD
import System.Windows.Forms as WF
from System.Collections.Generic import List
from System.Drawing.Drawing2D import DashStyle
from Grasshopper.GUI.Canvas import GH_Painter, GH_WireDirection
from Grasshopper.Kernel import IGH_Component, IGH_Param
from Grasshopper.Kernel.Undo import GH_UndoRecord, IGH_UndoAction
from Grasshopper.Kernel.Undo.Actions import GH_WireAction

SETTING = "basshopper:TypedWiring"
NAME_SETTING = "basshopper:NameNewParams"  # Name new params: its prompt is folded into this box
BUTTON_NAME = "basshopper:Typed wiring"
STATE = "_basshopper_typed_wiring"  # sys attribute with the live handlers, so a reload can detach them
HOTKEY = WF.Keys.L  # with Ctrl+Shift; not used by Grasshopper

# Grasshopper methods that place a new object because the user asked for it.
PLACE_METHODS = ("InstantiateNewObject", "InsertComponent")

history = []  # (doc, object) placed or click-selected by the user, newest last
pending = []  # (doc, sender, receiver) waiting for the box, shown once Grasshopper is idle

try:
    MOUSE_BUTTON
except NameError:
    MOUSE_BUTTON = "left"


def log(msg):
    Rhino.RhinoApp.WriteLine("basshopper: typed wiring: " + str(msg))


def is_on():
    return bool(Grasshopper.Instances.Settings.GetValue(SETTING, False))


def naming_on():
    return bool(Grasshopper.Instances.Settings.GetValue(NAME_SETTING, False))


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
    button.ToolTipText = ("Typed wiring ({})\nWire two objects by typing names, e.g. C-Crv\n"
                          "Left-click or Ctrl+Shift+L: wire the selection / last two placed now\n"
                          "Right-click: On/Off menu (open the box after every placement)"
                          .format("on" if on else "off")) + key_hint(button)


def key_hint(button):
    # The toolbar loader stores the button's number key in Tag.
    hint = button.Tag
    return "\n" + hint if isinstance(hint, str) and hint else ""


def set_on(on):
    Grasshopper.Instances.Settings.SetValue(SETTING, on)
    update_button()
    log("on" if on else "off")


# ---------------------------------------------------------------- matching

def outputs(obj):
    if isinstance(obj, IGH_Component):
        return list(obj.Params.Output)
    if isinstance(obj, IGH_Param):
        return [obj]
    return []


def inputs(obj):
    if isinstance(obj, IGH_Component):
        return list(obj.Params.Input)
    if isinstance(obj, IGH_Param) and obj.Attributes is not None and obj.Attributes.HasInputGrip:
        return [obj]
    return []


def short_names(params):
    return ", ".join(p.NickName for p in params) or "-"


def resolve(params, token):
    """Return (param, level) or (None, error). A lower level is a better match."""
    if token == "":
        if len(params) == 1:
            return params[0], 4
        return None, "give a name (options: {})".format(short_names(params))
    low = token.lower()
    tests = (
        lambda p: p.NickName == token,
        lambda p: p.NickName.lower() == low or p.Name.lower() == low,
        lambda p: p.NickName.lower().startswith(low) or p.Name.lower().startswith(low),
    )
    for level, test in enumerate(tests):
        found = [p for p in params if test(p)]
        if len(found) == 1:
            return found[0], level
        if len(found) > 1:
            return None, "'{}' is ambiguous: {}".format(token, short_names(found))
    if token.isdigit() and 1 <= int(token) <= len(params):
        return params[int(token) - 1], 3
    return None, "no '{}' (options: {})".format(token, short_names(params))


def is_floating(obj):
    # A standalone param that can receive a wire (sliders, toggles etc. can't).
    return isinstance(obj, IGH_Param) and bool(inputs(obj))


def plan_entry(entry, sender, receiver):
    """Return ('wire', out, in, None) / ('wire', out, param, name) / ('name', None, param, name),
    or raise ValueError with a message."""
    floating = is_floating(receiver)
    if sender is None or (floating and "-" not in entry):
        if not floating:
            raise ValueError("nothing to wire from")
        return ("name", None, receiver, entry)
    dashes = [i for i, ch in enumerate(entry) if ch == "-"]
    if not dashes:
        raise ValueError("'{}': use output-input, e.g. C-Crv".format(entry))
    found, errors = [], []
    for i in dashes:
        left, right = entry[:i].strip(), entry[i + 1:].strip()
        out, out_level = resolve(outputs(sender), left)
        if out is None:
            errors.append(out_level)
            continue
        if floating:
            found.append((out_level, out, receiver, right))
            continue
        inp, in_level = resolve(inputs(receiver), right)
        if inp is None:
            errors.append(in_level)
            continue
        found.append((out_level + in_level, out, inp, None))
    if not found:
        raise ValueError(errors[0])
    found.sort(key=lambda f: f[0])
    best = [f for f in found if f[0] == found[0][0]]
    if len(set((f[1].InstanceGuid, f[2].InstanceGuid, f[3]) for f in best)) > 1:
        raise ValueError("'{}' can be split more than one way".format(entry))
    _, out, inp, name = best[0]
    return ("wire", out, inp, name)


def quick_digits(text, sender, receiver):
    """Two digits = output index + input index (11 = 1st output to 1st input).
    Returns a plan, raises ValueError when out of range, or returns None when it isn't that."""
    if sender is None or len(text) != 2 or not text.isdigit():
        return None
    outs, ins = outputs(sender), inputs(receiver)
    if len(outs) > 9 or len(ins) > 9:
        return None  # two digits can't address these: use names
    o, i = int(text[0]), int(text[1])
    if not 1 <= o <= len(outs):
        raise ValueError("no output {} (1-{})".format(o, len(outs)))
    if not 1 <= i <= len(ins):
        raise ValueError("no input {} (1-{})".format(i, len(ins)))
    return ("wire", outs[o - 1], ins[i - 1], None)


def apply(doc, sender, receiver, text):
    """Wire/rename as typed. Returns an error message, or None when done."""
    entries = [e.strip() for e in text.split(",") if e.strip()]
    if not entries:
        return None
    try:
        plans = [plan_entry(e, sender, receiver) for e in entries]
    except ValueError as e:
        return str(e)
    execute(doc, plans)
    return None


def execute(doc, plans):
    actions = List[IGH_UndoAction]()
    done = []
    for kind, out, inp, name in plans:
        if kind == "wire" and not any(s.InstanceGuid == out.InstanceGuid for s in inp.Sources):
            actions.Add(GH_WireAction(inp))
            inp.AddSource(out)
            inp.ExpireSolution(False)  # marks it for the next solution; doesn't start one
            done.append("{} -> {}".format(out.NickName, inp.NickName if name is None else "param"))
        if name:
            inp.NickName = name
            inp.Attributes.ExpireLayout()
            done.append("named '{}'".format(name))
    if actions.Count:
        doc.UndoServer.PushUndoRecord(GH_UndoRecord("Typed wiring", actions))
    if done:
        log(", ".join(done))


# ---------------------------------------------------------------- box

def on_screen(form, point):
    # Keep the whole box inside the screen Grasshopper is on: a box off-screen blocks everything.
    area = WF.Screen.FromControl(Grasshopper.Instances.DocumentEditor).WorkingArea
    x = max(area.Left, min(point.X, area.Right - form.Width))
    y = max(area.Top, min(point.Y, area.Bottom - form.Height))
    return SD.Point(x, y)


def screen_point(obj):
    try:
        canvas = Grasshopper.Instances.ActiveCanvas
        bounds = obj.Attributes.Bounds
        p = canvas.Viewport.ProjectPoint(SD.PointF(bounds.Left, bounds.Bottom))
        return canvas.PointToScreen(SD.Point(int(p.X), int(p.Y) + 8))
    except Exception:
        return WF.Cursor.Position


def open_box(doc, sender, receiver):
    """The box: two numbered socket lists with a highlighted pick, a text field, and a
    preview wire on the canvas. Keys:
      two digits   wire right away (32 = 3rd output to 2nd input)
      arrows       (empty field) Left/Right pick a side, Up/Down step through its sockets
      Enter/Space  empty field: wire the highlighted pair; else wire/rename as typed
      Esc          close
    Typing also moves the highlight, so the preview shows what Enter will do."""
    outs = outputs(sender) if sender is not None else []
    ins = inputs(receiver) if sender is not None else []
    pick = [0, 0]   # highlighted output / input index; starts at 1st output -> 1st input
    side = [0]      # 0 = outputs, 1 = inputs (the side the arrows move)
    shown = [None]  # (output, input) the preview wire currently shows

    form = WF.Form()
    form.Text = "Typed wiring"
    form.FormBorderStyle = WF.FormBorderStyle.FixedToolWindow
    form.ShowInTaskbar = False
    form.StartPosition = WF.FormStartPosition.Manual
    form.AutoScaleMode = WF.AutoScaleMode.Font

    controls, lists, heads = [], [], []
    y = 6
    if sender is not None:
        rows = min(max(len(outs), len(ins), 1), 9)
        for n, (title, params) in enumerate((("From " + sender.NickName, outs), ("To " + receiver.NickName, ins))):
            head = WF.Label()
            head.Text = title
            head.SetBounds(8 + n * 176, y, 168, 16)
            lst = WF.ListBox()
            lst.TabStop = False
            lst.IntegralHeight = False
            for k, p in enumerate(params, 1):
                lst.Items.Add("{}  {}".format(k, p.NickName))
            lst.SetBounds(8 + n * 176, y + 18, 168, lst.ItemHeight * rows + 6)
            heads.append(head)
            lists.append(lst)
            controls += [head, lst]
        y = lists[0].Bottom + 8
    else:
        head = WF.Label()
        head.Text = "Name for {}".format(receiver.NickName)
        head.SetBounds(8, y, 344, 16)
        controls.append(head)
        y += 22
    box = WF.TextBox()
    box.SetBounds(8, y, 344, 22)
    error = WF.Label()
    error.ForeColor = SD.Color.Firebrick
    error.SetBounds(8, y + 24, 344, 16)
    ok = WF.Button()
    ok.Text = "Wire" if sender is not None else "Name"
    ok.SetBounds(196, y + 44, 75, 24)
    cancel = WF.Button()
    cancel.Text = "Skip"
    cancel.DialogResult = WF.DialogResult.Cancel
    cancel.SetBounds(277, y + 44, 75, 24)
    controls += [box, error, ok, cancel]
    form.ClientSize = SD.Size(360, y + 76)

    # -- highlight + preview

    canvas = Grasshopper.Instances.ActiveCanvas
    fonts = [SD.Font(form.Font, SD.FontStyle.Regular), SD.Font(form.Font, SD.FontStyle.Bold)]

    def show(out_i, in_i):
        if not lists:
            return
        for n, lst in enumerate(lists):
            lst.SelectedIndex = (out_i, in_i)[n] if lst.Items.Count else -1
            heads[n].Font = fonts[1 if side[0] == n else 0]
        pair = (outs[out_i], ins[in_i]) if outs and ins else None
        if pair != shown[0]:
            shown[0] = pair
            if canvas is not None:
                canvas.Invalidate()  # repaint only (draws the preview), no recompute

    def highlight_from_text():
        """What the typed text points at, else the arrow pick."""
        text = box.Text.split(",")[-1].strip()
        out_i, in_i = pick
        if not text or not outs:
            return out_i, in_i
        if text.isdigit() and len(text) == 1:
            n = int(text) - 1
            return (n if n < len(outs) else out_i), in_i
        try:
            if "-" in text:
                kind, out, inp, _ = plan_entry(text, sender, receiver)
                if kind == "wire":
                    return outs.index(out), (ins.index(inp) if inp in ins else in_i)
            else:
                out, _ = resolve(outs, text)
                if out is not None:
                    return outs.index(out), in_i
        except ValueError:
            pass
        return out_i, in_i

    def paint(c):
        pair = shown[0]
        if pair is None:
            return
        try:
            a, b = pair[0].Attributes.OutputGrip, pair[1].Attributes.InputGrip
            pen = SD.Pen(SD.Color.FromArgb(230, 31, 111, 235), 4.0)
            pen.DashStyle = DashStyle.Dash
            try:
                path = GH_Painter.ConnectionPath(a, b, GH_WireDirection.right, GH_WireDirection.left)
                c.Graphics.DrawPath(pen, path)
                path.Dispose()
            except Exception:
                c.Graphics.DrawLine(pen, a, b)
            pen.Dispose()
        except Exception:
            pass

    # -- events

    def on_ok(s, e):
        try:
            if not box.Text.strip():
                if outs and ins:
                    execute(doc, [("wire", outs[pick[0]], ins[pick[1]], None)])
                form.DialogResult = WF.DialogResult.OK
                return
            message = apply(doc, sender, receiver, box.Text)
        except Exception:
            log(traceback.format_exc())
            message = "failed, see the command line"
        if message:
            error.Text = message
            box.SelectAll()
            box.Focus()
        else:
            form.DialogResult = WF.DialogResult.OK

    def on_text_changed(s, e):
        # Two digits wire straight away, no Enter needed.
        try:
            plan = quick_digits(box.Text.strip(), sender, receiver)
        except ValueError as err:
            error.Text = str(err)
            show(*highlight_from_text())
            return
        error.Text = ""
        if plan is None:
            show(*highlight_from_text())
            return
        try:
            execute(doc, [plan])
        except Exception:
            log(traceback.format_exc())
            error.Text = "failed, see the command line"
            return
        form.DialogResult = WF.DialogResult.OK

    def on_key_down(s, e):
        key = e.KeyCode
        if key == WF.Keys.Space:
            # Space works like Enter (so it never types a space)
            e.Handled = True
            e.SuppressKeyPress = True
            on_ok(None, None)
            return
        if box.Text or not lists:
            return  # while typing, the arrows edit the text
        if key == WF.Keys.Left:
            side[0] = 0
        elif key == WF.Keys.Right:
            side[0] = 1
        elif key == WF.Keys.Up or key == WF.Keys.Down:
            count = len(outs) if side[0] == 0 else len(ins)
            if count:
                step = -1 if key == WF.Keys.Up else 1
                pick[side[0]] = (pick[side[0]] + step) % count
        else:
            return
        e.Handled = True
        e.SuppressKeyPress = True
        show(*pick)

    def on_list_click(n):
        def handler(s, e):
            if lists[n].SelectedIndex >= 0:
                side[0] = n
                pick[n] = lists[n].SelectedIndex
                box.Text = ""
                show(*pick)
            box.Focus()
        return handler

    ok.Click += on_ok
    box.TextChanged += on_text_changed
    box.KeyDown += on_key_down
    for n, lst in enumerate(lists):
        lst.MouseClick += on_list_click(n)
    for control in controls:
        form.Controls.Add(control)
    form.AcceptButton = ok
    form.CancelButton = cancel
    form.Location = on_screen(form, screen_point(receiver))
    form.Shown += lambda s, e: show(*pick)
    if canvas is not None:
        canvas.CanvasPostPaintWires += paint
    try:
        form.ShowDialog(Grasshopper.Instances.DocumentEditor)
    finally:
        if canvas is not None:
            canvas.CanvasPostPaintWires -= paint
            canvas.Invalidate()  # remove the preview
        for font in fonts:
            font.Dispose()
        form.Dispose()


# ---------------------------------------------------------------- choosing sender/receiver

def alive(doc, obj):
    return obj is not None and doc.FindObject(obj.InstanceGuid, True) is not None


def remember(doc, obj):
    # Keep the objects you placed or selected, newest last, without repeats.
    history[:] = [(d, o) for d, o in history if o.InstanceGuid != obj.InstanceGuid]
    history.append((doc, obj))
    del history[:-20]


def last_placed(doc, exclude=None):
    """The object placed or selected most recently (other than `exclude`)."""
    for d, obj in reversed(history):
        # Compare by ID: each access hands Python a new wrapper, so `is` never matches.
        if d.DocumentID == doc.DocumentID and alive(doc, obj) \
                and (exclude is None or obj.InstanceGuid != exclude.InstanceGuid):
            return obj
    return None


def on_canvas_mouse_up(sender, args):
    # Remember a clicked selection: the click that opens the search or drops a ribbon item
    # deselects everything, so at placement time the selection is often already gone.
    try:
        doc = sender.Document
        if doc is None:
            return
        selected = doc.SelectedObjects()
        if selected.Count == 1 and isinstance(selected[0], (IGH_Component, IGH_Param)):
            remember(doc, selected[0])
            debug("remembered click on " + selected[0].NickName)
    except Exception:
        log(traceback.format_exc())


def open_for_selection():
    canvas = Grasshopper.Instances.ActiveCanvas
    doc = canvas.Document if canvas else None
    if doc is None:
        return
    selected = list(doc.SelectedObjects())
    if len(selected) == 2:
        sender, receiver = sorted(selected, key=lambda o: o.Attributes.Bounds.Left)
    elif len(selected) == 1:
        receiver = selected[0]
        sender = last_placed(doc, exclude=receiver)
    else:
        receiver = last_placed(doc)
        sender = last_placed(doc, exclude=receiver) if receiver else None
    if receiver is None or sender is None:
        log("select two objects (the left one sends), or place two first")
        return
    open_box(doc, sender, receiver)


def is_param_object(obj):
    if not isinstance(obj, IGH_Param) or obj.Attributes is None or not obj.Attributes.HasInputGrip:
        return False
    return not (obj.GetType().Namespace or "").startswith("Grasshopper.Kernel.Special")


def has_default_name(param):
    if param.NickName == param.Name:
        return True
    fresh = Grasshopper.Instances.ComponentServer.EmitObject(param.ComponentGuid)
    return fresh is not None and param.NickName == fresh.NickName


# ---------------------------------------------------------------- listener

def placed_by_user():
    for frame in System.Diagnostics.StackTrace(False).GetFrames():
        method = frame.GetMethod()
        if method is not None and method.Name in PLACE_METHODS:
            return True
    return False


DEBUG = False  # True: log every step on the command line


def debug(msg):
    if DEBUG:
        log("debug: " + msg)


def on_objects_added(sender, args):
    try:
        objects = list(args.Objects)
        debug("{} object(s) added: {}".format(len(objects), ", ".join(o.Name for o in objects)))
        if not placed_by_user():
            names = [f.GetMethod().Name for f in System.Diagnostics.StackTrace(False).GetFrames()
                     if f.GetMethod() is not None and f.GetMethod().DeclaringType is not None
                     and (f.GetMethod().DeclaringType.Namespace or "").startswith("Grasshopper")]
            debug("not a placement; Grasshopper calls: " + ", ".join(names[:12]))
            return
        doc = args.Document
        added = [o for o in objects if isinstance(o, (IGH_Component, IGH_Param))]
        debug("placement; {} component/param(s); typed wiring {}".format(len(added), "on" if is_on() else "off"))
        if len(added) != 1:
            return
        receiver = added[0]
        # Sender: the one object selected while placing, else the one placed or selected last.
        selected = [o for o in doc.SelectedObjects() if o.InstanceGuid != receiver.InstanceGuid]
        source = selected[0] if len(selected) == 1 else last_placed(doc, exclude=receiver)
        debug("selected at placement: {}; sender: {}; remembered: {}".format(
            len(selected), source.NickName if source else "none", len(history)))
        remember(doc, receiver)
        if not is_on():
            return
        wants_name = naming_on() and is_param_object(receiver) and has_default_name(receiver)
        if source is None and not wants_name:
            log("no object to wire from yet: select or place one first")
            return
        if not pending:
            Rhino.RhinoApp.Idle += on_idle
        pending.append((doc, source, receiver))
    except Exception:
        log(traceback.format_exc())


def on_idle(sender, args):
    # Wait until the placement (e.g. a drag from the ribbon) is finished before showing the box.
    Rhino.RhinoApp.Idle -= on_idle
    queue = list(pending)
    del pending[:]
    debug("idle: opening {} box(es)".format(len(queue)))
    for doc, source, receiver in queue:
        try:
            if not alive(doc, receiver):
                continue
            source = source if alive(doc, source) else None
            open_box(doc, source, receiver)
            # Wiring with digits/arrows closes the box before you could name the new param,
            # so ask for the name next (only if it still has its default name).
            if source is not None and alive(doc, receiver) and naming_on() \
                    and is_param_object(receiver) and has_default_name(receiver):
                open_box(doc, None, receiver)
        except Exception:
            log(traceback.format_exc())


def on_key_down(sender, args):
    try:
        if args.KeyCode == HOTKEY and args.Control and args.Shift and not args.Alt:
            args.Handled = True
            args.SuppressKeyPress = True
            open_for_selection()
    except Exception:
        log(traceback.format_exc())


def key_target():
    # The editor sees keys first when it previews them; otherwise the canvas gets them.
    editor = Grasshopper.Instances.DocumentEditor
    if editor is not None and editor.KeyPreview:
        return editor
    return Grasshopper.Instances.ActiveCanvas


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
        try:
            if old["key_target"] is not None:
                old["key_target"].KeyDown -= old["key_down"]
        except Exception:
            pass
        try:
            if old.get("canvas") is not None:
                old["canvas"].MouseUp -= old["mouse_up"]
        except Exception:
            pass
    server.DocumentAdded += on_document_added
    server.DocumentRemoved += on_document_removed
    for doc in documents():
        attach(doc)
    target = key_target()
    if target is not None:
        target.KeyDown += on_key_down
    canvas = Grasshopper.Instances.ActiveCanvas
    if canvas is not None:
        canvas.MouseUp += on_canvas_mouse_up
    setattr(sys, STATE, {"objects_added": on_objects_added,
                         "document_added": on_document_added,
                         "document_removed": on_document_removed,
                         "key_down": on_key_down,
                         "key_target": target,
                         "mouse_up": on_canvas_mouse_up,
                         "canvas": canvas,
                         "open_for_selection": open_for_selection})
    update_button()
    log("listener installed ({}, Ctrl+Shift+L)".format("on" if is_on() else "off"))


# ---------------------------------------------------------------- button

def show_menu():
    menu = WF.ContextMenuStrip()
    on = is_on()
    for label, value in (("On: open after placing", True), ("Off", False)):
        item = WF.ToolStripMenuItem(label)
        item.Checked = on == value
        item.Click += (lambda v: lambda s, e: set_on(v))(value)
        menu.Items.Add(item)
    menu.Items.Add(WF.ToolStripSeparator())
    wire_now = WF.ToolStripMenuItem("Wire now")
    wire_now.ShortcutKeyDisplayString = "Ctrl+Shift+L"
    wire_now.Click += lambda s, e: getattr(sys, STATE)["open_for_selection"]()
    menu.Items.Add(wire_now)
    button = find_button()
    if button is not None and button.Owner is not None:
        menu.Show(button.Owner, SD.Point(button.Bounds.Left, button.Bounds.Bottom))
    else:
        menu.Show(WF.Cursor.Position)


if __name__ == "__main__":
    if getattr(sys, STATE, None) is None:
        install_listener()  # e.g. the toolbar was loaded by an older loader
    key = globals().get("TRIGGER") == "key"
    if MOUSE_BUTTON != "right":
        getattr(sys, STATE)["open_for_selection"]()  # left-click / plain key: wire now
    elif key:
        set_on(not is_on())  # Shift+key: just flip it
    else:
        show_menu()  # right-click: On/Off menu
