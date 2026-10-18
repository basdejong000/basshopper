"""PMS Layout Border Override v0 -- a per-border override document for
ONE Layout node's own grid. Bidirectional like every other ...JSON
component here: Create (wire field inputs), Explode (wire only JSON),
Update (wire both). Its JSON output feeds one item of Layout's
BorderOverridesJSON list input -- authored on the SAME node whose own
grid the border sits in (no dot-notation into nested layouts is
needed: Geom's recursion already scopes each override to its own
node, see pms-layout-geom-v0.py).

BETWEEN -- required. A list of 1-3 items, same grammar as the old PMS
wall-override component's `Between`: [a, b] a PAIR of labels (order-
insensitive matching downstream, but ORDER controls Offset's
direction -- see below); [label, '*'] a RING, every border touching
that label; ['*', '*'] GLOBAL, every border in the node. 'EXT' is a
valid label value on either side of a pair/ring, meaning the node's
own perimeter (the edge of its own grid, not necessarily the true
building exterior). Matching uses BASE labels too ('mod' matches every
'mod[k]' instance). GLOBAL only exists for forward compatibility with
that same grammar -- Offset (the only thing this document carries)
never acts on it (no single space to anchor a shift to; Geom warns and
skips it). RING, unlike global, DOES have an effect -- see OFFSET
below. Either label side of a PAIR, or a RING's anchor, may ALSO be a
comma-separated LIST of labels -- 'm1,m2' -- to address several cells
in one override: Geom expands it into one entry per label (a full
cross product when BOTH sides of a pair are lists) before resolving
anything. No brackets needed ('[m1,m2]', the old wall-override
system's own bracket-list syntax) -- a between item is already its
own list slot here, so wrapping it again would be pure noise; '*' and
'EXT' are never treated as a list even if a comma sneaks into one by
mistake. Optional 3rd item: a SIDE FILTER, same naming as the old
system -- Top/Bottom/Left/Right (or short T/B/L/R), case-insensitive.
For an 'EXT' pair or a RING, this NARROWS which side(s) of the matched
space the Offset applies to. SEVERAL sides can be given at once, same
bare-comma vocabulary as the label list above -- 'Top,Left' or 'T,L'
(no brackets) -- narrowing to exactly that subset rather than one side
or all of them; an unrecognized token anywhere in the list drops the
WHOLE filter (warned) rather than applying part of it. Leave the
filter out entirely (blank, or '*', an explicit wildcard, same thing)
and it applies to EVERY side the space has at once -- a single cell
filling its whole grid (a window's glass pane against its frame) gets
inset on all 4 sides from ONE override, no need to spell out each
side; a plain corner gets both of its touching sides; a RING match
(which doesn't care whether a side faces EXT or a sibling) always
gets all 4. This matches the old wall-override system's own
"unfiltered ring = every wall touching this space" default. No
indexed form ('T0', 'Top1') -- not applicable here yet,
since a pair/EXT/ring match is always a single space with at most one
segment per side.

OFFSET -- optional, a distance in mm. Meaningful for a PAIR or a RING
(global offsets are ignored, warned -- there's no single space to
anchor a shift to). Moves the border, NOT a wall thickness (nothing
in this system has thickness yet -- pure line segments). Suppressing a
border entirely ("no wall here") is deliberately NOT this component's
job -- it's a pure display decision with no geometric consequence, so
it belongs downstream (Geom's own Borders selector input, or a plain
Cull Pattern keyed on Topology), not baked into the authored data model.
What actually happens depends on the mode, and (for a pair) what's on
each side of it, decided by Geom at solve time (see its own
docstring's BORDER OVERRIDES section for the full mechanism):
  - RING (a single anchor space against '*'): ALWAYS independent, no
    matter what's actually adjacent on each chosen side -- EXT, a
    plain sibling, or a sibling that itself hosts a child. Only the
    anchor space moves -- its own drawn cell shape, and its child's
    given frame if it has one -- on every side it has (or just the
    filtered one). The sibling on the other side of any given border,
    if there is one, is NEVER touched: no track resize, no shape
    change. This is what makes a ring simpler than a pair to reason
    about -- there's no "what's on the other side, and which
    mechanism does IT need" question, the anchor always just moves
    its own geometry.
  - RING with 'EXT' as the anchor (['EXT','*'] or ['*','EXT'], order
    doesn't matter): the one ring that ISN'T a single named space --
    applies to EVERY space in the node that touches the grid's own
    perimeter, each one shifted independently on just the side(s) IT
    actually touches (same per-space mechanism as the 'EXT' pair
    below, just for every matching space at once instead of one named
    one). A side filter narrows to spaces touching that side
    specifically; unfiltered, each space moves on every perimeter side
    it individually has. A space that doesn't touch a requested side
    is silently skipped -- normal for most spaces in a multi-cell
    grid, not a mistake. This is the one-override way to push out (or
    pull in) a whole outer edge of cells -- e.g. ['EXT','*','L,R']
    grows every cell touching the grid's own left or right edge
    outward, without listing each outer cell's label by hand.
  - PAIR of two real spaces, at least one PLAIN (no bound child): the
    ONE shared track boundary between them shifts by Offset mm,
    positive = toward Between[1]'s side -- one cell grows, its
    neighbour shrinks by the same amount. If the OTHER side hosts a
    child, that child's own assigned frame shifts along with it
    (nothing special to author for that -- it just inherits its
    parent cell's new size).
  - Either side is 'EXT': that space's OWN boundary against the edge
    of the grid moves by Offset mm (positive = outward), REGARDLESS of
    whether it has a bound child. Its own drawn shape in Cells AND its
    own matching wall segment in Borders both shift together -- so the
    change already reads correctly at the space's OWN Depth, not just
    one level deeper. If it also has a child, the child's own assigned
    frame gets the SAME shift, so all three (cell, wall, child) agree.
    Needs a side filter (see BETWEEN above) when the space touches
    more than one grid edge.
  - PAIR of two real spaces, BOTH hosting their own bound child (e.g.
    two sliding door panels, each its own nested Layout): NEITHER
    side's own TRACK size (its slice of the parent's grid) changes --
    but both spaces' own drawn cell shapes in Cells DO move (matching
    their children), so at the parent's own Depth you already see the
    two cells overlapping, not just their children one level deeper.
    The INTERIOR wall segment between them, in Borders, DUPLICATES into
    each space's own edge (matching Cells exactly) rather than freezing
    at its now-stale original position -- once two children can
    overlap there's no longer a SINGLE "wall position" to draw, so
    Geom draws both (see its own docstring's DUPLICATE INTERIOR
    SEGMENTS section). EACH child's own
    assigned frame independently extends toward the other by the FULL
    Offset amount (not split), so a single Offset = half your frame
    thickness gives the two panels a total overlap equal to the frame
    thickness. Order doesn't matter here, both always grow toward
    each other. A
    NEGATIVE Offset pulls them apart instead of together -- a route to
    a real gap, but ONLY if each child's own track is 'fr' or 'auto'
    (something that actually responds to a smaller given width). A
    FIXED-mm child track ignores given_w entirely, so it never
    shrinks -- only the side whose ORIGIN moved (the 'after' space)
    visibly shifts, while the 'before' space stays exactly where it
    was; you still get a gap, but asymmetrically, and the two
    children's combined span grows past what an 'auto' PARENT cell
    would have sized itself to fit (auto sizing measures each child's
    own intrinsic size before any Offset is ever applied, so it can't
    account for this). For a real, predictable gap, prefer authoring
    an actual spacer column/row between the two cells instead.
In every case above except the first PAIR bullet (a real shared
boundary with a plain cell on at least one side), the parent's own
track sizes stay untouched -- only the specific space's own drawn
shape, or its child's given frame, moves. A RING never touches track
sizes at all, by definition.

WALL LAYOUT -- optional, a nested Layout JSON document (same schema as
any other Layout node) describing that border's own UPRIGHT elevation
-- studs, openings, panels -- authored the SAME way any floor-plan grid
is: CellWidths/CellLengths/CellLabels/ChildLayouts, nothing new there.
Rides ALONGSIDE the flat 2D border line Geom already draws for the
floor plan's own topology -- doesn't replace it. Created fresh the
moment this override carries one; there's no separate "wall cell"
that exists beforehand waiting for a plane.

Two required conventions, both enforced here (not just documented):
  - CellWidths MUST be exactly ["auto"] -- a placeholder, not a real
    value. Geom overwrites it with the matched border's own actual
    length at solve time (whatever that border currently measures,
    after any Offset). The width was never the author's to set --
    anything else here is an ERROR, not a warning.
  - CellLengths is authored NORMALLY, by you -- it's the wall's own
    real HEIGHT. Nothing imposes this; a floor plan carries no notion
    of wall height at all.

The wall's own PLANE (X-axis along the border's own direction, Y-axis
world-up, normal pointing OUT of the matched space -- same convention
PMS-R7 already uses for wall stacks) is computed AUTOMATICALLY by Geom
from the matched border itself -- attaching a wall layout at all is
already the signal it needs to stand upright; there's no separate
field for that. Meaningful for a PAIR (a real space, or EXT, on each
side -- same mode Offset's own EXT/both-hosting-a-child mechanisms
already use) OR a RING (a single real anchor, or EXT itself as the
anchor, against '*') -- only GLOBAL still has no border-owning-child
concept for Geom to hang a wall layout on (no single anchor, and
"every border in the node" is a much bigger default than asked for),
warned and skipped if given one.

Both a PAIR and a RING can already match MORE than one boundary. A
PAIR does it via the SAME base-label equivalence every other Between
already uses: Between=['m','m'] (identical base label on both sides)
hits every m[i]-vs-m[j] interior boundary in the node at once, one
wall each -- the way to put a wall on a REPEATED shared border (a
party wall between adjacent modules, say) without hard-coding every
specific instance pair. A RING goes further -- Between=['a','*'] walls
every border touching space 'a' regardless of what's across it, and
Between=['EXT','*'] walls the WHOLE perimeter of the node -- useful
one level up where the children don't all share one base label to
pair against each other, so there's no single repeated label to hand
a PAIR. Either way, Between's optional 3rd item -- the same Top/
Bottom/Left/Right (or T/B/L/R) side filter used everywhere else in
this document -- genuinely narrows WHICH of a multi-match entry's
boundaries actually get a wall, checked against that boundary's own
edge relative to the reference space (a PAIR's Between[0], a RING's
anchor, or whichever side isn't 'EXT' when there's no other
candidate): ['m','EXT','T,B'] places a wall on each module's own
North/South EXT edge but skips an end module's West/East EXT edge;
['EXT','*','T,B'] does the same one level up without naming every
child. Leave the filter out and EVERY boundary the entry matches gets
a wall.

Pins --
  Inputs:  JSON, Between, Offset, WallLayoutJSON
  Outputs: JSON

v0 prototype -- not wired into the component build pipeline (no
.doc.md yet). Paste into a GHPython component and set up the pins
above -- see pms-layout-border-override-v0.spec.json for the exact
pin config.

Schema v0.2 | Component v0.10.0
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


SCHEMA_TYPE_VALUE = "BorderOverride"
SCHEMA_VERSION_VALUE = "0.1"


# -----------------------------------------------------------------
# Goo / JSON plumbing -- identical to pms-layout-v0.py.
# -----------------------------------------------------------------

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


# -----------------------------------------------------------------
# MERGE -- build/update one border-override document.
# -----------------------------------------------------------------

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
                if cw != ["auto"]:
                    warnings.append(
                        "WallLayoutJSON's CellWidths must be exactly "
                        "['auto'] -- Geom fills this in from the "
                        "matched border's own length, it's never "
                        "authored directly -- got {!r}.".format(cw))
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

    between = merged.get("between")
    if not isinstance(between, list) or not (2 <= len(between) <= 3):
        warnings.append(
            "Between is required -- a pair ['a','b'], a ring "
            "['a','*'], or the global ['*','*'], optionally followed "
            "by a side filter (Top/Bottom/Left/Right or T/B/L/R).")

    return merged


# -----------------------------------------------------------------
# Main.
# -----------------------------------------------------------------

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
