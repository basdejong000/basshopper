#! python3
"""Add (or update) a left-click button on a Rhino 8 toolbar that runs a Python script.

Run inside Rhino 8 (e.g. through the Rhino MCP run_python tool):

    exec(open(r"C:\\Users\\basdejong\\Git\\basshopper\\skills\\rhino-toolbar-button\\install_toolbar_button.py", encoding="utf-8").read())
    install_button(
        script_path=r"C:\\Users\\basdejong\\Git\\basshopper\\tools\\my_tool.py",
        svg_path=r"C:\\Users\\basdejong\\Git\\basshopper\\tools\\icons\\my_tool.svg",
        name="My tool",
        help_text="What it does, one line",
    )

Uses Rhino 8's own (internal) toolbar model, Rhino.UI.Internal.TabPanels, so Rhino
writes the change to the workspace file itself. If a button on the toolbar already
runs script_path, only its icon is replaced, so running this twice is safe.
"""
import datetime
import os
import shutil

import System
from System.Reflection import BindingFlags

DEFAULT_WORKSPACE = "c7da84fc-2991-4824-832a-4f2509bd0ede"  # Rhino 8 built-in default.rui
_F = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static
_ASM = [a for a in System.AppDomain.CurrentDomain.GetAssemblies() if a.GetName().Name == "Rhino.UI"][0]


def _type(name):
    return _ASM.GetType("Rhino.UI.Internal.TabPanels." + name)


def _prop(obj, name):
    t = obj.GetType()
    while t is not None:
        p = t.GetProperty(name, _F | BindingFlags.DeclaredOnly)
        if p:
            return p
        t = t.BaseType
    raise AttributeError(name)


def _get(obj, name):
    return _prop(obj, name).GetValue(obj)


def _set(obj, name, value):
    _prop(obj, name).SetValue(obj, value)


def _matches(params, args):
    return all(p.ParameterType.IsInstanceOfType(a) for p, a in zip(params, args))


def _call(obj, name, *args, static_type=None):
    t = static_type or obj.GetType()
    methods = [m for m in t.GetMethods(_F) if m.Name == name and len(m.GetParameters()) == len(args)]
    if len(methods) > 1:
        methods = [m for m in methods if _matches(m.GetParameters(), args)]
    return methods[0].Invoke(None if static_type else obj, list(args))


def _new(type_name, *args):
    # pythonnet picks the wrong Activator.CreateInstance overload; invoke the constructor directly.
    ctors = [c for c in _type(type_name).GetConstructors(_F)
             if len(c.GetParameters()) == len(args) and _matches(c.GetParameters(), args)]
    return ctors[0].Invoke(list(args))


def _find_button(toolbar, script_path):
    items = _get(toolbar, "Collection")
    for i in range(items.Count):
        ref = _get(items[i], "LeftMacro")
        if ref is None:
            continue
        try:
            macro = _get(ref, "Macro")
        except Exception:
            continue
        if macro is not None and script_path.lower() in str(_get(macro, "Script") or "").lower():
            return macro
    return None


def _backup(path):
    if not os.path.exists(path):
        return
    backup = "{}.bak-{:%Y%m%d}".format(path, datetime.date.today())
    if not os.path.exists(backup):
        shutil.copy2(path, backup)


def install_button(script_path, svg_path, name, help_text="", button_text=None,
                   toolbar="Standard", workspace=DEFAULT_WORKSPACE):
    svg = open(svg_path, encoding="utf-8").read()
    files = _call(None, "FromFileId", System.Guid(workspace), static_type=_type("ToolBarFileController"))
    tb = _call(files, "ToolBarFromName", toolbar)
    if tb is None:
        raise ValueError("toolbar not found: " + toolbar)
    _backup(_get(files, "FileName"))

    macro = _find_button(tb, script_path)
    if macro is not None:
        icon = _call(_get(files, "Icons"), "GetItem", _get(macro, "BitmapId"))
        _set(icon, "LightSvg", svg)
        _set(icon, "DarkSvg", svg)
        _set(icon, "Modified", True)
        result = "icon updated (the toolbar shows it after a Rhino restart)"
    else:
        file_vm = _new("ToolBarFileViewModel", System.String("default"), files)
        vm = _new("MacroViewModel", file_vm)
        _set(vm, "Text", name)
        _set(vm, "Script", '! _-ScriptEditor _Run "{}"'.format(script_path))
        _set(vm, "ToolTip", name)
        _set(vm, "HelpText", help_text)
        _set(vm, "ButtonText", button_text or name)
        _set(vm, "MenuText", name)
        _set(vm, "LightSvg", svg)
        _set(vm, "DarkSvg", svg)
        _set(vm, "SvgName", os.path.splitext(os.path.basename(svg_path))[0])
        _set(vm, "IsImageModified", True)
        macro = _call(_get(files, "Macros"), "AddNewMacro", vm)
        _call(tb, "NewItem", macro)
        result = "button added at the end of the {} toolbar".format(toolbar)

    _call(tb, "RaiseChangedEvent")
    _call(files, "WriteXmlDiffFile")
    print("{}: {}".format(name, result))
