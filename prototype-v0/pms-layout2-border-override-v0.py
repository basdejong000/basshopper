"""PMS Layout 2 Border Override v0 -- PROTOTYPE border-override
authoring component for the "atomic cells" architecture (see
pms-layout-geom2-v0.py). Same Between/Offset grammar as the original
pms-layout-border-override-v0.py (pair/ring/EXT/global, base-label
matching, comma label/side lists) -- pure string parsing, unaffected
by how shapes are solved. See Geom2's own docstring for how Offset
actually applies to atomic cells (a local, per-cell adjacency check,
not the original's bounding-box approximation).

WallLayoutJSON is accepted and validated, CONSUMED by Geom2 (wall
cells). CellWidths is EITHER exactly ['auto'] (one column, filled from
the matched border's own actual length -- the simple, original case:
a solid wall body, no width-wise subdivision) OR a list with NO 'auto'
entry at all, containing at least one 'fr' track (e.g. ['400',
'1fr', '400'] -- two fixed 400mm frame pieces either side of a window
column that soaks up whatever length is left over) -- resolved by
Geom2 exactly like any other Layout2 grid, against the matched
border's own actual length. Mixing 'auto' with anything else, or a
list with no 'fr' and no 'auto' (nothing to guarantee the columns
still sum to the wall's own real length), is rejected.

WallHeight (optional, mm) is the wall's own HEIGHT, stored as
'wallHeight' on the override. The width axis always has a real total
(the matched border's own length); the height axis has none, so a
'1fr' in the wallLayout's CellLengths would resolve against nothing.
WallHeight is that total -- Geom2 resolves the wall's CellLengths
against it exactly like any other grid resolves against a given
height ('fr' rows share whatever the fixed rows leave over). Unset =
no total, same as before this input existed.

Pins --
  Inputs:  JSON, Between, Offset, WallLayoutJSON, WallHeight
  Outputs: JSON

Schema v0.1 | Component v0.3.0
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


SCHEMA_TYPE_VALUE = "BorderOverride2"
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


def _wall_cellwidths_ok(cw):
    """A wallLayout's own CellWidths is valid EITHER as exactly
    ['auto'] (the simple, single-column case Geom2 fills in wholesale)
    OR as a list with no 'auto' entry at all but at least one 'fr'
    track (so the columns are still guaranteed to sum to the wall's
    own actual matched length, via ordinary track resolution against
    that length as the total -- exactly like any other Layout2 grid).
    Anything else -- 'auto' mixed with other tracks, or an all-fixed
    list with no 'fr' to soak up the real length -- is rejected."""
    if cw == ["auto"]:
        return True
    if not isinstance(cw, list) or not cw:
        return False
    if any(t == "auto" for t in cw):
        return False
    return any(isinstance(t, string_types) and t.endswith("fr") for t in cw)


def _new_merged(base, *first_keys):
    result = OrderedDict()
    for k, v in first_keys:
        result[k] = v
    if base:
        for k, v in base.items():
            if k not in result:
                result[k] = v
    return result


def merge_override(inputs, base, warnings):
    merged = _new_merged(
        base,
        ("type", SCHEMA_TYPE_VALUE),
        ("schemaVersion", SCHEMA_VERSION_VALUE),
    )

    if "Between" in inputs:
        items = []
        for v in inputs.get("Between") or []:
            s = goo_value(v)
            if isinstance(s, string_types) and s.strip():
                items.append(s.strip())
        if items:
            merged["between"] = items
        else:
            merged.pop("between", None)

    if "Offset" in inputs:
        o = goo_value(inputs.get("Offset"))
        try:
            merged["offset"] = float(o)
        except (TypeError, ValueError):
            warnings.append(
                "Offset {!r} isn't a number -- ignored.".format(o))
            merged.pop("offset", None)

    if "WallLayoutJSON" in inputs:
        raw = inputs.get("WallLayoutJSON")
        if raw is not None and (
                not isinstance(raw, string_types) or raw.strip()):
            parsed = parse_json_str(goo_value(raw))
            if isinstance(parsed, dict):
                cw = parsed.get("cellWidths")
                if not _wall_cellwidths_ok(cw):
                    warnings.append(
                        "WallLayoutJSON's CellWidths must be exactly "
                        "['auto'], or a list with no 'auto' but at "
                        "least one 'fr' track to soak up the matched "
                        "border's own actual length -- got {!r}."
                        .format(cw))
                else:
                    merged["wallLayout"] = parsed
            elif parsed is None:
                warnings.append(
                    "WallLayoutJSON couldn't be parsed -- kept base "
                    "value.")
            else:
                warnings.append(
                    "WallLayoutJSON must be a JSON object -- kept "
                    "base value.")

    if "WallHeight" in inputs:
        h = goo_value(inputs.get("WallHeight"))
        try:
            hv = float(h)
        except (TypeError, ValueError):
            hv = None
        if hv is None or hv <= 0:
            warnings.append(
                "WallHeight {!r} isn't a positive number -- ignored."
                .format(h))
            merged.pop("wallHeight", None)
        else:
            merged["wallHeight"] = hv

    between = merged.get("between")
    if not isinstance(between, list) or not (2 <= len(between) <= 3):
        warnings.append(
            "Between is required -- a pair ['a','b'], a ring "
            "['a','*'], or the global ['*','*'], optionally followed "
            "by a side filter (Top/Bottom/Left/Right or T/B/L/R).")

    return merged


def run():
    component = ghenv.Component  # noqa: F821
    component.ClearRuntimeMessages()
    warnings = []
    g = globals()

    inputs = {
        "JSON": g.get("JSON"),
        "Between": g.get("Between"),
        "Offset": g.get("Offset"),
        "WallLayoutJSON": g.get("WallLayoutJSON"),
        "WallHeight": g.get("WallHeight"),
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
    merged = merge_override(merge_inputs, base, warnings)

    g["JSON"] = json.dumps(merged, indent=2)

    if warnings:
        component.AddRuntimeMessage(
            gh.Kernel.GH_RuntimeMessageLevel.Warning, "\n".join(warnings))


if _HAS_GH:
    run()
