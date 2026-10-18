"""PMS Layout 2 v0 -- PROTOTYPE authoring component for the "atomic
cells" architecture (see project memory / this session's design
discussion). Same schema as pms-layout-v0.py (CellWidths/CellLengths/
CellLabels/ChildLayouts, GridLayoutJSON grammar, BorderOverridesJSON --
one pms-layout2-border-override-v0 JSON document per entry, same
pattern as ChildrenJSON).

Mirror -- an optional boolean, stored as node['mirror']. Consumed by
Geom2 (this component itself doesn't solve anything): mirrors this
node's own CellWidths/CellLabels column order (the WIDTH axis only --
CellLengths/row order never flips) and CASCADES to every descendant
automatically (a mirrored node's own hosted children, and its own
walls, all mirror too, with no per-node opt-out) -- so mirroring one
apartment node mirrors the whole apartment into a mirrored copy of
itself, not just its own outermost grid. See pms-layout-geom2-v0.py's
own docstring for the full mechanism and why only the width axis ever
needs to flip.

Pins --
  Inputs:  JSON, Label, Mirror, Boundary, CellWidths, CellLengths,
           CellLabels, ChildrenJSON, BorderOverridesJSON
  Outputs: JSON

Schema v0.2 | Component v0.3.0
"""

import json

try:
    import Grasshopper as gh
    _HAS_GH = True
except ImportError:
    gh = None
    _HAS_GH = False

try:
    string_types = (str, unicode)  # noqa: F821 (py2 / IronPython 2)
except NameError:
    string_types = (str,)

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict


SCHEMA_TYPE_VALUE = "Layout2"
SCHEMA_VERSION_VALUE = "0.1"


def goo_value(goo):
    if goo is None:
        return None
    if hasattr(goo, "ScriptVariable"):
        try:
            return goo.ScriptVariable()
        except Exception:
            pass
    if hasattr(goo, "Value"):
        try:
            return goo.Value
        except Exception:
            pass
    return goo


def parse_json_str(s):
    if s is None:
        return None
    if isinstance(s, (dict, list)):
        return s
    if not isinstance(s, string_types):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return json.loads(s, object_pairs_hook=OrderedDict)
    except ValueError:
        return None


def _present(v):
    if v is None:
        return False
    if isinstance(v, string_types):
        return bool(v.strip())
    if isinstance(v, list):
        return bool(v)
    return True


def _new_merged(base, *first_keys):
    result = OrderedDict()
    for k, v in first_keys:
        result[k] = v
    if base:
        for k, v in base.items():
            if k not in result:
                result[k] = v
    return result


def _vec3(v):
    try:
        return [float(v.X), float(v.Y), float(v.Z)]
    except AttributeError:
        pass
    try:
        return [float(v[0]), float(v[1]), float(v[2])]
    except (TypeError, IndexError, ValueError):
        return None


def _boundary_from_input(raw, warnings):
    val = goo_value(raw)
    if val is None:
        return None
    try:
        plane = val.Plane
        width = float(val.Width)
        length = float(val.Height)
    except (AttributeError, TypeError, ValueError):
        warnings.append(
            "Boundary ({}) isn't usable -- wire a Rectangle3d (plane + "
            "width + height).".format(type(val).__name__))
        return None
    origin = _vec3(getattr(plane, "Origin", None))
    xaxis = _vec3(getattr(plane, "XAxis", None))
    yaxis = _vec3(getattr(plane, "YAxis", None))
    if origin is None or xaxis is None or yaxis is None:
        warnings.append("Boundary's Plane couldn't be read -- ignored.")
        return None
    return {
        "plane": {"origin": origin, "xAxis": xaxis, "yAxis": yaxis},
        "width": width,
        "length": length,
    }


def _canon_track_atom(raw):
    if isinstance(raw, string_types):
        s = raw.strip().lower()
        if not s:
            return None, "empty"
        if s == "auto" or s.startswith("minmax("):
            return s, None
        if s.endswith("fr"):
            head = s[:-2].strip()
            try:
                factor = float(head) if head else 1.0
            except ValueError:
                return None, "{!r} is not a number, 'auto' or 'Nfr'".format(raw)
            if factor < 0:
                return None, "{!r} fr factor must be >= 0".format(raw)
            return ("{}fr".format(int(factor) if factor == int(factor) else factor),
                    None)
    try:
        fv = float(raw)
    except (TypeError, ValueError):
        return None, "{!r} is not a number, 'auto' or 'Nfr'".format(raw)
    if fv <= 0:
        return None, "{!r} must be positive".format(raw)
    return fv, None


def _tracks_list(raw, name, warnings):
    if raw is None:
        return None
    out = []
    for i, v in enumerate(raw):
        canon, err = _canon_track_atom(goo_value(v))
        if err is not None:
            warnings.append("{}[{}] {} -- skipped.".format(name, i, err))
            continue
        out.append(canon)
    return out if out else None


def _spaces_str_to_grid(spaces_str, warnings):
    if not isinstance(spaces_str, string_types):
        return None
    rows = []
    for line in spaces_str.splitlines():
        if not line.strip():
            continue
        cells = [c.strip() for c in line.split(",")]
        while cells and not cells[-1]:
            cells.pop()
        if cells:
            rows.append(cells)
    if not rows:
        return None
    ncols = max(len(r) for r in rows)
    for i, r in enumerate(rows):
        if len(r) != ncols:
            warnings.append(
                "CellLabels row {} has {} cells, expected {} -- padded."
                .format(i, len(r), ncols))
            r.extend([""] * (ncols - len(r)))
    return rows


def _merge_json_list(inputs, key, base_key, merged, warnings):
    if key not in inputs:
        return
    out = []
    for i, item in enumerate(inputs.get(key) or []):
        s = goo_value(item)
        if s is None:
            continue
        if isinstance(s, dict):
            out.append(s)
            continue
        parsed = parse_json_str(s)
        if isinstance(parsed, dict):
            out.append(parsed)
        else:
            warnings.append(
                "{}[{}] couldn't be parsed as a JSON object -- skipped."
                .format(key, i))
    merged[base_key] = out


def _merge_bool_field(inputs, key, base_key, merged, warnings):
    if key not in inputs:
        return
    merged[base_key] = bool(goo_value(inputs.get(key)))


def _merge_string_field(inputs, key, base_key, merged, warnings):
    if key not in inputs:
        return
    v = goo_value(inputs.get(key))
    if v is None:
        return
    if not isinstance(v, string_types):
        warnings.append("{} must be a string -- kept base value.".format(key))
        return
    s = v.strip()
    if s:
        merged[base_key] = s
    else:
        merged.pop(base_key, None)


def merge_layout(inputs, base, warnings):
    merged = _new_merged(
        base,
        ("type", SCHEMA_TYPE_VALUE),
        ("schemaVersion", SCHEMA_VERSION_VALUE),
    )
    _merge_string_field(inputs, "Label", "label", merged, warnings)
    _merge_bool_field(inputs, "Mirror", "mirror", merged, warnings)

    boundary = None
    if "Boundary" in inputs:
        boundary = _boundary_from_input(inputs.get("Boundary"), warnings)
        if boundary is not None:
            merged["plane"] = boundary["plane"]

    if "CellWidths" in inputs:
        w = _tracks_list(inputs.get("CellWidths"), "CellWidths", warnings)
        if w is not None:
            merged["cellWidths"] = w
    if "CellLengths" in inputs:
        h = _tracks_list(inputs.get("CellLengths"), "CellLengths", warnings)
        if h is not None:
            merged["cellLengths"] = h
    if "CellLabels" in inputs:
        grid = _spaces_str_to_grid(goo_value(inputs.get("CellLabels")), warnings)
        if grid is not None:
            merged["cellLabels"] = grid

    _merge_json_list(inputs, "ChildrenJSON", "childLayouts", merged, warnings)
    _merge_json_list(inputs, "BorderOverridesJSON", "borderOverrides", merged,
                      warnings)

    if boundary is not None:
        if not merged.get("cellWidths"):
            merged["cellWidths"] = [boundary["width"]]
        if not merged.get("cellLengths"):
            merged["cellLengths"] = [boundary["length"]]

    widths = merged.get("cellWidths")
    lengths = merged.get("cellLengths")
    labels = merged.get("cellLabels")
    if not isinstance(widths, list) or not widths:
        warnings.append("CellWidths is required.")
    if not isinstance(lengths, list) or not lengths:
        warnings.append("CellLengths is required.")
    if not isinstance(labels, list) or not labels:
        warnings.append("CellLabels is required.")
    if isinstance(widths, list) and isinstance(labels, list):
        for i, row in enumerate(labels):
            if len(row) != len(widths):
                warnings.append(
                    "CellLabels row {} has {} cells, CellWidths has {}."
                    .format(i, len(row), len(widths)))
                break
    if isinstance(lengths, list) and isinstance(labels, list):
        if len(labels) != len(lengths):
            warnings.append(
                "CellLabels has {} rows, CellLengths has {}."
                .format(len(labels), len(lengths)))

    return merged


def run():
    component = ghenv.Component  # noqa: F821
    component.ClearRuntimeMessages()
    warnings = []
    g = globals()

    inputs = {
        "JSON": g.get("JSON"),
        "Label": g.get("Label"),
        "Mirror": g.get("Mirror"),
        "Boundary": g.get("Boundary"),
        "CellWidths": g.get("CellWidths"),
        "CellLengths": g.get("CellLengths"),
        "CellLabels": g.get("CellLabels"),
        "ChildrenJSON": g.get("ChildrenJSON"),
        "BorderOverridesJSON": g.get("BorderOverridesJSON"),
    }

    base = {}
    json_in = g.get("JSON")
    if _present(json_in):
        parsed = parse_json_str(goo_value(json_in))
        if isinstance(parsed, dict):
            base = parsed
        else:
            component.AddRuntimeMessage(
                gh.Kernel.GH_RuntimeMessageLevel.Error,
                "JSON input couldn't be parsed as a JSON object.")
            return

    merge_inputs = {k: v for k, v in inputs.items() if _present(v)}
    merged = merge_layout(merge_inputs, base, warnings)

    g["JSON"] = json.dumps(merged, indent=2)

    if warnings:
        component.AddRuntimeMessage(
            gh.Kernel.GH_RuntimeMessageLevel.Warning, "\n".join(warnings))


if _HAS_GH:
    run()
