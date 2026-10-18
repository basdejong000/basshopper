"""PMS Geom 2 v0 -- PROTOTYPE solver for the "atomic cells"
architecture. Borders/Topology are permanently OUT of scope as a
general GH output -- wall cells consume adjacency internally instead,
lazily, only for nodes that actually carry a wallLayout-bearing
override (see WALL LAYOUTS below); see the session's own design
discussion. See pms-layout-geom-v0.py for the full original.

BORDER OVERRIDES -- back, via node['borderOverrides'] (one
pms-layout2-border-override-v0 document per entry, same `between`/
`offset` grammar as the original -- pure string parsing, unaffected by
any of this). What's genuinely NEW is how Offset actually APPLIES,
now that there's no merged, possibly-non-rectangular "space" for it to
reason about -- every unit is a raw grid cell, always a rectangle:
  - A cell's own side is a real, independently-offsettable boundary
    IFF its neighbour there is either off-grid (true EXT) or a
    DIFFERENT label. A SAME-label neighbour is an internal seam within
    one merged group and never moves independently -- no bounding box
    anywhere, just one direct, local comparison per side.
  - RING / EXT ring / EXT pair (INDEPENDENT): apply per matching cell,
    on every requested side that's a real boundary by the rule above
    -- computed in _cell_independent_deltas, applied directly to that
    cell's own rect in _emit (never to a merged bbox).
  - RING with anchor 'INT' -- the mirror of an EXT ring: every cell,
    any label, on every requested side whose neighbour is a DIFFERENT
    real label (never off-grid -- that's EXT's own job). Lets a single
    override target "every interior boundary" without naming every
    room pair explicitly, matching what 'INT' already means for the
    original Geom's own Borders selector -- but that selector doesn't
    exist on Geom2 at all, so 'INT' had NO effect here until now (it
    silently matched nothing, since nothing is ever literally labelled
    'INT'). Same rule applies to wallLayout's own Between grammar --
    see WALL LAYOUTS below and _wall_candidates.
  - PAIR of two real labels, at least one side plain (no bound child):
    SHARED -- resizes the ONE actual track between them, in
    _apply_shared_offsets, before _emit ever walks. Atomic cells are
    ALWAYS exactly one track wide/tall, so (unlike the original) there
    is no "span too wide to resize cleanly" case to warn about --
    ONLY ambiguity left is "does this pair touch along more than one
    boundary", which IS still warned and skipped (agreed scope limit).
  - PAIR of two real labels, BOTH host a child: INDEPENDENT -- each
    side grows toward the other by the FULL offset (not split),
    computed per-cell exactly like ring, track sizes untouched.
  - Union (see below) no longer cares whether a label's own cells
    carry an offset at all -- see below.

The one thing this prototype exists to validate: the solve never
merges same-label cells into one traced shape before drawing them --
every grid cell is always its own plain rectangle, always
unambiguous. "These cells are one logical space" becomes purely an
OUTPUT-ADDRESSING fact (same-FULL-label, 4-connected cells share one
branch, same flood-fill _merge_spaces already did -- '[k]' still means
what it always has, do-NOT-merge) instead of a geometric-merge fact
the solver has to reason about. An optional Union toggle collapses
each BARE-labelled branch's own cells into one shape at output time --
via a REAL geometric Boolean union (Rhino.Geometry.Curve.
CreateBooleanUnion), not a hand-rolled edge trace. That's a deliberate
v0.6.0 change: the earlier hand-rolled tracer needed cells to still
share exact coincident edges, so it had to bail out (warned, drawn as
separate rectangles instead) the moment ANY offset touched ANY cell in
a group -- even a harmless one, like an EXT-only offset that never
touches the group's own internal seams. A real Boolean union has no
such restriction: still touching -> one shape; grown into an overlap
-> one (larger) shape; genuinely pulled apart -> that many separate
curves, honestly, rather than either guessing at a combined outline or
refusing to draw anything (still warned+falls back to the raw cells if
the call itself returns nothing). Union deliberately SKIPS a
'[k]'-suffixed label even with several cells -- the suffix itself
already means "keep these separate on purpose", so Union never
overrides that.

TREE SHAPE -- one branch per SPACE, not per node, and it now matches
the original Geom's OWN Depth numbers exactly (no offset at all): {i}
= item i's own boundary (Depth 0, same as original), {i;j} = item i's
own j-th top-level space (row-major among its parent's spaces, Depth
1, same as original), holding that space's own cell(s) (N rectangles,
or 1 if Union and the label isn't '[k]'-suffixed). A space that hosts
a child recurses into THAT SAME branch, {i;j}.AppendElement(j2) for
the child's own j2-th top-level space (Depth 2, same as original) --
one segment deeper per level, exactly the cost the original Geom's
own flat-list recursion has. (Two earlier versions of this file each
inserted a redundant constant-0 "container" segment -- once at the
root, once at every child recursion -- before the real per-space
branching; both are gone now, which is what makes Depth match the
original exactly instead of being offset by a growing amount.)

This flat, no-offset guarantee now holds for WALLS too, not just
ordinary hosted children (see WALL LAYOUTS below) -- a wall recurses
DIRECTLY into its own matched host space's path, exactly like an
ordinary child does, so its own door/header/... content sits at the
SAME Depth a hosted child's own top-level spaces would: (its host
space's own Depth) + 1 -- e.g. a wall hosted by a Depth-1 space lands
its own content at Depth 2, same as any other hosted child there.

WALL LAYOUTS -- a border override may carry a 'wallLayout' document, a
child hosted on the border itself rather than on a cell. CellWidths is
EITHER exactly ['auto'] (one column, wholesale-replaced with the
matched border's own actual length -- a plain wall body, no width-wise
subdivision) OR a list with no 'auto' entry at all but at least one
'fr' track (e.g. ['400','1fr','400'] -- fixed frame pieces either side
of a window column that soaks up whatever length is left over) --
left AS AUTHORED and resolved via given_w=wall_len exactly like any
other Layout2 grid's own track resolution, no new solving logic needed
for this case at all (see _wall_cellwidths_ok/_place_walls). Any
hosted cell, on either CellWidths shape, may still carry its own
childLayouts entry -- width-wise window/door subdivision plus a
further-nested child (glazing, etc.) both work via the SAME general
_emit recursion every other Layout2 node already uses. Found lazily,
per matching wallLayout-carrying override, via a direct scan of cell
adjacency (no Borders/Topology pass at all): a cell's own side is a
candidate exactly where Offset's own rules already say a boundary is
real (pair: the reference label's side touching the other label, or
off-grid if the other side is 'EXT'; ring: the anchor's side touching
anything real, off-grid or a different label -- including a ring
anchored on 'INT', matching every interior boundary regardless of
which two specific labels it's between, same rule and reasoning as
Offset's own INT ring above). Adjacent candidates
along the same line merge into ONE run ONLY while the LITERAL label on
BOTH sides stays the same -- a multi-cell touch of the SAME room (e.g.
m[0] spanning 2 rows) becomes one wall, but a run still BREAKS at a
label change even when grid-adjacent (an EXT ring walking s1 | k | s2
side by side gets 3 separate walls, not 1) -- same rule as the
original Geom's own PERIMETER walk ('adjacent cells sharing a label
merge into one run, a label change breaks it'), and the exact behavior
the user explicitly chose to KEEP when JoinWalls was proposed and
declined for the original -- see _wall_candidates/_group_wall_runs. A
SYMMETRIC query (a base-label pair like ['m','m'], or a ring anchor
touching another cell that also matches its own anchor) still finds
each physical boundary exactly once, deduplicated -- and a base-label
anchor matching two DIFFERENT literal instances side by side (m[0]
next to m[1]) still gets 2 separate walls, per the label-break rule
above.

A DIVERGED interior boundary -- e.g. an INDEPENDENT offset that moves
a PAIR's two real sides apart (a gap) or into each other (an overlap),
same as a genuine door-clearance offset between two child-hosting
modules -- is NOT refused (unlike the original Geom, which deferred
this indefinitely as a Phase 1 limitation, and unlike TWO earlier
versions of this file, which first matched that deferral, then
collapsed it to a single MIDPOINT wall). It now gets TWO wall
instances instead, one per side's own actual edge -- see
_wall_run_placements/_place_walls -- essentially the original's own
never-built plan ("emit the wall's own cells twice... each instance's
own winding satisfies the outward-normal rule for its own respective
space"), made tractable here because atomic cells already know each
side's own exact rect independently at all times; there was never a
bbox-vs-bbox reconciliation to invent, just an over-strict validation
to relax. Between[0] (or the ring/INT anchor) is the LEADING side --
its own instance uses the wallLayout exactly AS AUTHORED, unmirrored
relative to this node's own inherited state. The OTHER side's own
instance gets an EXTRA mirror flip (XOR against this node's own
state) -- reversing its own CellWidths/CellLabels column order is
what keeps the SAME content aligned at the SAME physical spot on both
sides despite the mirrored winding each side's own correct outward
normal requires (see MIRROR below for why only the width axis ever
needs to flip). An EXT-anchored run (no real neighbour at all), or an
UNDIVERGED one (still exactly coincident), still gets exactly ONE
instance -- there's nothing to reconcile, unchanged from before either
way. Either side's own cells still disagreeing WITH THEMSELVES across
a multi-cell run (not just with each other) is still refused -- no
single straight line for either instance to anchor to in that case.

A wall's WIDTH always has a real total (the matched border's own
length), but its HEIGHT has none -- so a '1fr' in the wallLayout's
CellLengths would resolve to 0mm. An override's optional 'wallHeight'
(set via the border-override component's WallHeight input, mm) is that
total: it is passed as the wall's own given_h, and 'fr' rows share
whatever the fixed rows leave over, exactly like any other grid
resolving against a given height. Unset = unchanged (no total).

Plane/normal construction (_wall_plane_axes/_upright_plane_from) is
pure geometry, ported verbatim from the original -- it never depended
on Borders at all. A wall recurses DIRECTLY into its own matched HOST
space's own space_path -- exactly like an ordinary hosted child does,
NOT a sibling of it, and with NO separate wrapper segment of its own
either -- the host being whichever space the placement is actually
matched to (the reference side's own space for a single/primary
instance, the NEIGHBOUR's own space for a diverged run's second,
mirrored instance -- see above), found by looking up that side's own
literal label in `spaces`. Its own top-level content (door, frame,
window, ...) therefore lands at the SAME Depth an ordinary hosted
child's own top-level spaces would -- host's own Depth + 1, not +2.

Since a host space may take an ordinary child AND several wall
placements all at once, all sharing that ONE space_path, each gets its
own INDEX OFFSET within that path's numbering instead of colliding --
the host's own regular child (if any) always claims indices first
(0..N-1, N = however many top-level spaces it has), and wall content
picks up exactly where that leaves off (see _place_walls's own
`used_index_count`, built by _emit's per-space loop before any wall is
ever placed). This is a REAL disambiguation mechanism, not a "may
coincide, but never mixes because it's one level down" note like an
earlier version of this design had -- here everything genuinely shares
one flat index space at one depth, so the offsets have to be exact.

A wallLayout's own 'label' field (otherwise unused -- Geom2 never
matches a wall by label the way an ordinary hosted child is) groups
placements sharing that label onto the SAME starting offset, but only
when they also share the SAME host space (e.g. two opposite 'pf' walls
both matched to 'm[0]') -- their own recursive content then lands
together in the same sub-branch, same mechanism a bare multi-cell
space already uses to hold N rectangles in one branch (_emit's own
tree.Add just appends, nothing about it changes). Two 'pf' walls
matched to DIFFERENT hosts (one to 'm[0]', one to 'm[1]') are never
grouped, even from the same _place_walls call -- they don't even share
a parent branch any more. This is deliberately scoped to WITHIN one
node's own local set of walls -- it does NOT attempt to group walls
placed by a DIFFERENT node's own _place_walls call -- that would need
tree-wide state nothing else in this file has (see the session's own
design discussion on why this is a genuinely different, harder problem
than local grouping). An unlabeled wallLayout is unaffected -- always
its own fresh offset there, advanced by however many top-level spaces
its own content turns out to have, nothing to group by.

The 'Cells' input is an OPTIONAL SELECTOR narrowing the Cells (and, in
lockstep, Labels) output to just the requested label(s) -- applied
AFTER Depth filtering. Ported verbatim from the original Geom's own
selector of the same name (_filtered_cells_and_labels) -- pure tree
filtering, unaffected by anything about atomic cells. There's no
'Borders' selector here (unlike the original) since Borders/Topology
aren't a general output on Geom2 at all.

MIRROR -- a node's own 'mirror' field (set via pms-layout2-v0's Mirror
input) reverses ITS OWN CellWidths and each CellLabels row (WIDTH axis
only -- CellLengths/row order is never touched, see _resolve_node) and
CASCADES to every descendant automatically: a mirrored node's own
hosted children, AND its own walls, mirror too, with no per-node
opt-out (not asked for -- add one later if a real case needs it).
Effective state is computed once per node (mirror OR this node's own
field) and threaded through _emit's own recursion and _place_walls, so
"mirror one apartment node" mirrors the whole apartment into a
mirrored copy of itself, not just its own outermost grid. Children are
matched by LABEL, not position, so reversing column order never
breaks child hosting. Reversal happens on COPIES, never mutating the
original node, since the same JSON might be hosted elsewhere
unmirrored (e.g. a floor plan with one apartment type placed both
normally and mirrored). Only the WIDTH axis ever needs to flip because
a wall's own Y-axis (height) is always "parent's own up" regardless of
which edge it's anchored to -- only its X-axis (winding/width)
differs between two sides of a boundary -- see WALL LAYOUTS above.

WARNINGS output -- `warnings` entries prefixed with _REMARK_PREFIX
describe correct, intended behavior (e.g. a diverged boundary getting
two mirrored wall instances), not a problem -- they never go on the
component's own runtime-message balloon at all (an earlier version put
them there at Remark level; still unprompted, still in your face for
something that isn't wrong). They go out through this output instead,
as plain data -- inspect it with a Panel, filter it, count it, only
when you actually want to. Genuine problems (the rest of `warnings`)
still show up on the balloon as an orange Warning, unchanged.

Pins --
  Inputs:  JSON, Plane, Depth, Union, Cells
  Outputs: Cells, Labels, Warnings

Schema v0.1 | Component v0.17.0
"""

import json

try:
    import Rhino.Geometry as rg
    import Grasshopper as gh
    _HAS_RHINO = True
except ImportError:
    rg = None
    gh = None
    _HAS_RHINO = False

try:
    string_types = (str, unicode)  # noqa: F821 (py2 / IronPython 2)
except NameError:
    string_types = (str,)

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict


# A message in `warnings` prefixed with this is informational, not a
# problem -- "this happened, here's why, nothing to fix" (e.g. a
# diverged boundary correctly getting two mirrored wall instances
# instead of being refused). run() strips the prefix and emits these
# as GH_RuntimeMessageLevel.Remark (grey) instead of .Warning (orange)
# -- a message describing intended, correct behavior shouldn't carry
# the same "you probably need to look at this" visual weight as an
# actual problem (a skipped wall, a clipped grid, ...). Everything
# else in `warnings` -- the majority -- stays a genuine Warning.
_REMARK_PREFIX = "REMARK: "


# -----------------------------------------------------------------
# Goo / JSON / plane plumbing -- identical to pms-layout-geom-v0.py.
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


def _plane_from_dict(d):
    if not isinstance(d, dict):
        return None
    try:
        ox, oy, oz = d["origin"]
        xx, xy, xz = d["xAxis"]
        yx, yy, yz = d["yAxis"]
    except (KeyError, TypeError, ValueError):
        return None
    return rg.Plane(rg.Point3d(ox, oy, oz), rg.Vector3d(xx, xy, xz),
                     rg.Vector3d(yx, yy, yz))


# -----------------------------------------------------------------
# Label matching -- identical to pms-layout-geom-v0.py.
# -----------------------------------------------------------------

def _base_label(label):
    if not isinstance(label, string_types):
        return label
    i = label.rfind("[")
    if i > 0 and label.endswith("]"):
        return label[:i]
    return label


def _matches_label(label, wanted):
    if not isinstance(label, string_types):
        return False
    return label in wanted or _base_label(label) in wanted


# -----------------------------------------------------------------
# BORDER OVERRIDES -- Between grammar parsing is identical to
# pms-layout-geom-v0.py (pure string parsing, independent of how
# shapes are represented). What's NEW here is HOW a delta gets applied
# -- see ADJACENCY / OFFSET below: no bounding box anywhere, every
# check is a direct, local comparison between one grid cell and its
# immediate neighbour.
# -----------------------------------------------------------------

SIDE_CODES = {
    "t": "N", "top": "N",
    "b": "S", "bottom": "S",
    "l": "W", "left": "W",
    "r": "E", "right": "E",
}


def _parse_between(items, warnings):
    if not items:
        return None
    side = None
    if len(items) > 2:
        raw_side = items[2]
        raw = raw_side.strip() if isinstance(raw_side, string_types) else ""
        if raw in ("", "*"):
            side = None
        else:
            codes = set()
            bad = []
            for tok in raw.split(","):
                tok = tok.strip()
                if not tok:
                    continue
                code = SIDE_CODES.get(tok.lower())
                if code is None:
                    bad.append(tok)
                else:
                    codes.add(code)
            if bad or not codes:
                warnings.append(
                    "side {!r} not recognized -- use Top/Bottom/Left/"
                    "Right (or T/B/L/R), a comma-separated list of "
                    "them, or '*' for any -- ignored.".format(raw_side))
                side = None
            else:
                side = codes
        if len(items) > 3:
            warnings.append(
                "between {!r} has extra items past the side filter "
                "-- ignored.".format(items))
    if len(items) < 2:
        warnings.append(
            "between {!r} needs two labels (or '*') -- ignored."
            .format(items))
        return None
    a, b = items[0], items[1]
    if a == "*" and b == "*":
        return ("global", None, None, side)
    if a == "*" or b == "*":
        return ("ring", (b if a == "*" else a), None, side)
    return ("pair", a, b, side)


def _split_labels(ref):
    if not isinstance(ref, string_types) or ref in ("*", "EXT", "INT") or "," not in ref:
        return [ref]
    labs = [t.strip() for t in ref.split(",") if t.strip()]
    return labs if labs else [ref]


def _node_overrides(node, warnings):
    """Parses node['borderOverrides'] into (mode, a, b, side, offset)
    tuples, mode in ('ring', 'pair') -- 'global' is warned and dropped
    here (no single anchor), exactly like the original. Label lists on
    either side (or a ring's anchor) are expanded via _split_labels
    before anything downstream ever sees them."""
    out = []
    for od in (node.get("borderOverrides") or []):
        if not isinstance(od, dict):
            continue
        between = od.get("between")
        parsed = _parse_between(between if isinstance(between, list) else [],
                                 warnings)
        if parsed is None:
            continue
        mode, a, b, side = parsed
        offset = od.get("offset")
        try:
            offset = float(offset) if offset is not None else None
        except (TypeError, ValueError):
            warnings.append(
                "borderOverrides: offset {!r} isn't a number -- ignored."
                .format(offset))
            offset = None
        if offset is None:
            continue
        if mode == "global":
            warnings.append(
                "borderOverrides: 'global' selector has no effect -- "
                "Offset needs a specific space to anchor to (a pair "
                "or a ring).")
            continue
        if mode == "ring":
            for aa in _split_labels(a):
                out.append(("ring", aa, None, side, offset))
        else:
            for aa in _split_labels(a):
                for bb in _split_labels(b):
                    out.append(("pair", aa, bb, side, offset))
    return out


# -----------------------------------------------------------------
# ADJACENCY -- the one thing that actually needed re-deriving for
# atomic cells (see the session's own design discussion). A cell's own
# side is a real, independently-offsettable boundary IFF its neighbour
# there is either off-grid (true EXT) or a DIFFERENT label -- a SAME-
# label neighbour is an internal seam within one merged group and
# never moves on its own (it moves WITH the group, i.e. not at all
# under an independent offset -- only Union, at output time, ever
# collapses it visually). No bounding box anywhere: every check below
# is a direct comparison between one cell and the single neighbour
# next to it.
# -----------------------------------------------------------------

_DIR_DELTA = {"N": (-1, 0), "S": (1, 0), "W": (0, -1), "E": (0, 1)}


def _neighbor_rc(r, c, side, nrows, ncols):
    dr, dc = _DIR_DELTA[side]
    nr, nc = r + dr, c + dc
    if 0 <= nr < nrows and 0 <= nc < ncols:
        return nr, nc
    return None


def _apply_delta(deltas, r, c, side, offset):
    dx0, dy0, dx1, dy1 = deltas.get((r, c), (0.0, 0.0, 0.0, 0.0))
    if side == "W":
        dx0 -= offset
    elif side == "E":
        dx1 += offset
    elif side == "S":
        dy0 -= offset
    elif side == "N":
        dy1 += offset
    deltas[(r, c)] = (dx0, dy0, dx1, dy1)


def _cell_independent_deltas(labels_grid, children_by_label, nrows, ncols,
                              overrides, name, warnings):
    """Returns {(r,c): (dx0,dy0,dx1,dy1)} -- INDEPENDENT offsets only
    (ring, EXT-pair/EXT-ring, both-children pair). SHARED (track-
    resizing) pair offsets are handled separately, in
    _apply_shared_offsets, before tracks are even sized -- they never
    reach here. Global was already dropped by _node_overrides."""
    deltas = {}
    for (mode, a, b, side, offset) in overrides:
        if mode == "ring":
            if a == "EXT":
                # Every cell, any label, whose neighbour on a
                # requested side is truly off-grid.
                for r in range(nrows):
                    for c in range(ncols):
                        sides = side if side is not None else ("N", "S", "E", "W")
                        for s in sides:
                            if _neighbor_rc(r, c, s, nrows, ncols) is None:
                                _apply_delta(deltas, r, c, s, offset)
                continue
            if a == "INT":
                # Mirror of EXT -- every cell, any label, on every
                # requested side whose neighbour is a DIFFERENT real
                # label (never off-grid -- that's EXT's own job).
                for r in range(nrows):
                    for c in range(ncols):
                        label = labels_grid[r][c]
                        sides = side if side is not None else ("N", "S", "E", "W")
                        for s in sides:
                            nb = _neighbor_rc(r, c, s, nrows, ncols)
                            if nb is not None and labels_grid[nb[0]][nb[1]] != label:
                                _apply_delta(deltas, r, c, s, offset)
                continue
            # A real anchor: EVERY matching cell, on every requested
            # side that's a real boundary (off-grid OR different
            # label) -- ring doesn't care which of the two it is.
            for r in range(nrows):
                for c in range(ncols):
                    if not _matches_label(labels_grid[r][c], [a]):
                        continue
                    sides = side if side is not None else ("N", "S", "E", "W")
                    for s in sides:
                        nb = _neighbor_rc(r, c, s, nrows, ncols)
                        if nb is None or labels_grid[nb[0]][nb[1]] != labels_grid[r][c]:
                            _apply_delta(deltas, r, c, s, offset)
            continue

        # PAIR.
        for r in range(nrows):
            for c in range(ncols):
                label = labels_grid[r][c]
                i_am_a = _matches_label(label, [a])
                i_am_b = _matches_label(label, [b])
                if not (i_am_a or i_am_b):
                    continue
                other = b if i_am_a else a
                if other == "EXT":
                    sides = side if side is not None else ("N", "S", "E", "W")
                    touched = False
                    for s in sides:
                        if _neighbor_rc(r, c, s, nrows, ncols) is None:
                            _apply_delta(deltas, r, c, s, offset)
                            touched = True
                    if not touched and side is not None:
                        warnings.append(
                            "{}: border override {!r} -- {!r} at ({},{}) "
                            "doesn't touch that side -- Offset skipped."
                            .format(name, [a, b], label, r, c))
                    continue
                # Both real labels: only the INDEPENDENT (both host
                # children) case reaches here -- SHARED already
                # happened earlier, in _apply_shared_offsets, and never
                # touches deltas at all.
                if _child_for_space(children_by_label, label) is None:
                    continue
                for s in ("N", "S", "E", "W") if side is None else side:
                    nb = _neighbor_rc(r, c, s, nrows, ncols)
                    if nb is None:
                        continue
                    nb_label = labels_grid[nb[0]][nb[1]]
                    if not _matches_label(nb_label, [other]):
                        continue
                    if _child_for_space(children_by_label, nb_label) is None:
                        continue
                    _apply_delta(deltas, r, c, s, offset)
    return deltas


def _apply_shared_offsets(labels_grid, children_by_label, col_starts,
                           col_sizes, row_starts, row_sizes, overrides,
                           name, warnings):
    """SHARED (track-resizing) PAIR offsets -- two real labels, at
    least one side with no bound child. Resolved BEFORE any per-cell
    independent delta, directly against col_starts/col_sizes (or the
    row equivalents), exactly like the original Geom's own
    _apply_shared_offsets -- just simpler here, since an atomic cell
    is ALWAYS exactly one track wide/tall, so there's no "is this span
    too wide to resize cleanly" question to ask at all. Scope limit
    (agreed): only resolved when the two labels touch along EXACTLY
    ONE boundary -- more than one is ambiguous (which track?), warned
    and skipped rather than guessed at."""
    nrows, ncols = len(row_sizes), len(col_sizes)

    def cell_label(r, c):
        return labels_grid[r][c]

    for (mode, a, b, side, offset) in overrides:
        if mode != "pair" or a == "EXT" or b == "EXT":
            continue
        matches = []
        for r in range(nrows):
            for c in range(ncols):
                label = cell_label(r, c)
                if not _matches_label(label, [a]):
                    continue
                for s in ("E", "S"):   # only scan two directions -- each
                    nb = _neighbor_rc(r, c, s, nrows, ncols)  # boundary is
                    if nb is None:                             # found once,
                        continue                                # not twice
                    nb_label = cell_label(*nb)
                    if _matches_label(nb_label, [b]):
                        matches.append((r, c, s, nb))
        if not matches:
            continue
        if len(matches) > 1:
            warnings.append(
                "{}: border override {!r} touches more than one boundary "
                "-- ambiguous which track to resize, skipped."
                .format(name, [a, b]))
            continue
        r, c, s, (nr, nc) = matches[0]
        a_has_child = _child_for_space(children_by_label, cell_label(r, c)) is not None
        b_has_child = _child_for_space(children_by_label, cell_label(nr, nc)) is not None
        if a_has_child and b_has_child:
            continue   # INDEPENDENT -- handled per-cell instead
        if s == "E":
            # a is west of b; resize column c (a's own) vs column nc (b's).
            col_sizes[c] += offset
            col_sizes[nc] -= offset
        else:
            # s == "S": a is north of b (row r above row nr, since row
            # 0 = North); resize row r (a's own) vs row nr (b's).
            row_sizes[r] += offset
            row_sizes[nr] -= offset
        # Re-accumulate starts for the whole axis -- a single track's
        # size changed, every start after it needs to shift too.
        if s == "E":
            acc = 0.0
            for i in range(ncols):
                col_starts[i] = acc
                acc += col_sizes[i]
        else:
            acc = 0.0
            for i in range(nrows):
                row_starts[i] = acc
                acc += row_sizes[i]


# -----------------------------------------------------------------
# Track solving -- identical to pms-layout-geom-v0.py.
# -----------------------------------------------------------------

def _clip_labels_grid(labels_grid, n_cols, n_rows, name, warnings):
    nrows = len(labels_grid)
    ncols = len(labels_grid[0]) if nrows else 0
    if nrows != n_rows or ncols != n_cols:
        warnings.append(
            "{}: CellLabels is {} rows x {} cols but CellWidths/"
            "CellLengths give {} cols x {} rows -- clipped/padded to "
            "match.".format(name, nrows, ncols, n_cols, n_rows))
    out = []
    for r in range(n_rows):
        row = labels_grid[r] if r < nrows else []
        row = list(row[:n_cols]) + [""] * max(0, n_cols - len(row))
        out.append(row)
    return out


def _resolve_tracks(tracks, total, auto_demand, name, warnings):
    sizes = []
    fr = []
    fixed_sum = 0.0
    for i, t in enumerate(tracks):
        if isinstance(t, (int, float)):
            v = float(t)
            sizes.append(v)
            fixed_sum += v
        elif isinstance(t, string_types) and t == "auto":
            v = auto_demand[i] if auto_demand else 0.0
            sizes.append(v)
            fixed_sum += v
        elif isinstance(t, string_types) and t.endswith("fr"):
            try:
                f = float(t[:-2])
            except ValueError:
                f = 1.0
            sizes.append(0.0)
            fr.append((i, f))
        else:
            warnings.append(
                "{}[{}] {!r} -- 'minmax' isn't resolved yet, treated "
                "as 0mm.".format(name, i, t))
            sizes.append(0.0)
    if fr:
        fr_sum = sum(f for _, f in fr)
        if total is None:
            warnings.append(
                "{} has 'fr' tracks with nothing to share -- resolve "
                "to 0mm.".format(name))
            leftover = 0.0
        else:
            leftover = max(0.0, total - fixed_sum)
        for i, f in fr:
            sizes[i] = (leftover * f / fr_sum) if fr_sum > 0 else 0.0
    starts = []
    acc = 0.0
    for s in sizes:
        starts.append(acc)
        acc += s
    return starts, sizes, acc


def _span_has_auto(tracks, lo, hi):
    return any(isinstance(tracks[i], string_types) and tracks[i] == "auto"
               for i in range(lo, hi + 1))


def _distribute_auto_demand(tracks, spans_and_needs):
    n = len(tracks)
    demand = [0.0] * n
    for lo, hi, needed in spans_and_needs:
        auto_idx = [i for i in range(lo, hi + 1)
                    if isinstance(tracks[i], string_types)
                    and tracks[i] == "auto"]
        if not auto_idx:
            continue
        fixed_sum = sum(tracks[i] for i in range(lo, hi + 1)
                         if isinstance(tracks[i], (int, float)))
        shortfall = max(0.0, needed - fixed_sum)
        share = shortfall / len(auto_idx)
        for i in auto_idx:
            demand[i] = max(demand[i], share)
    return demand


# -----------------------------------------------------------------
# Grouping -- SAME flood-fill as pms-layout-geom-v0.py's _merge_spaces,
# reused here purely for ADDRESSING (which cells share a branch) and
# for border suppression -- never for tracing a combined shape to draw
# (that's what this prototype is testing the removal of).
# -----------------------------------------------------------------

def _merge_spaces(labels_grid, warnings):
    nrows = len(labels_grid)
    ncols = len(labels_grid[0]) if nrows else 0
    seen = [[False] * ncols for _ in range(nrows)]
    spaces = []
    for r in range(nrows):
        for c in range(ncols):
            if seen[r][c]:
                continue
            label = labels_grid[r][c]
            stack = [(r, c)]
            seen[r][c] = True
            cells = [(r, c)]
            while stack:
                cr, cc = stack.pop()
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = cr + dr, cc + dc
                    if (0 <= nr < nrows and 0 <= nc < ncols
                            and not seen[nr][nc]
                            and labels_grid[nr][nc] == label):
                        seen[nr][nc] = True
                        cells.append((nr, nc))
                        stack.append((nr, nc))
            rs = [p[0] for p in cells]
            cs = [p[1] for p in cells]
            r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
            spaces.append({"label": label, "r0": r0, "r1": r1,
                            "c0": c0, "c1": c1, "cells": cells})
    return spaces


def _node_children_by_label(node):
    children_by_label = {}
    for ch in (node.get("childLayouts") or []):
        clabel = ch.get("label")
        if isinstance(clabel, string_types) and clabel:
            children_by_label[clabel] = ch
    return children_by_label


def _child_for_space(children_by_label, label):
    child = children_by_label.get(label)
    if child is not None:
        return child
    return children_by_label.get(_base_label(label))


def _resolve_node(node, given_w, given_h, warnings, intrinsic_memo, mirror=False):
    """Same as pms-layout-geom-v0.py's _resolve_node, PLUS border
    overrides -- SHARED (track-resizing) pair offsets are applied here,
    directly to col_starts/col_sizes/row_starts/row_sizes, before this
    function ever returns (so total_w/total_l already reflect them).
    INDEPENDENT offsets (ring, EXT, both-children pair) are computed
    but NOT applied here -- they never touch track sizes, only what
    _emit later draws for each cell -- returned as `cell_deltas`,
    {(r,c): (dx0,dy0,dx1,dy1)}, for _emit to apply itself.

    `mirror` is the INHERITED mirror state from this node's own parent
    (False at the root) -- effective_mirror = mirror OR this node's
    own 'mirror' field, so a mirrored node's own descendants ALWAYS
    mirror too (cascades all the way down, e.g. a whole apartment
    mirrored into a mirrored copy of itself), with no per-node opt-out
    (not asked for; add one later if a real case needs it). When
    effective, CellWidths and each CellLabels row are reversed (WIDTH
    axis only -- CellLengths/row order is NEVER touched, since a
    wall's own Y-axis, height, never flips between the two sides of a
    boundary, only its X-axis/width does -- see WALL LAYOUTS) on
    COPIES, never mutating the original node -- the same JSON might be
    hosted elsewhere unmirrored. Children are matched by LABEL, not
    position, so reversing column order never breaks child hosting.
    Returns (col_starts, col_sizes, total_w, row_starts, row_sizes,
    total_l, spaces, children_by_label, labels_grid, cell_deltas,
    effective_mirror)."""
    col_tracks = node.get("cellWidths") or ["1fr"]
    row_tracks = node.get("cellLengths") or ["1fr"]
    labels_grid = node.get("cellLabels") or [[""]]
    name = node.get("label") or "<root>"
    labels_grid = _clip_labels_grid(
        labels_grid, len(col_tracks), len(row_tracks), name, warnings)

    effective_mirror = mirror or bool(node.get("mirror"))
    if effective_mirror:
        col_tracks = list(reversed(col_tracks))
        labels_grid = [list(reversed(row)) for row in labels_grid]

    children_by_label = _node_children_by_label(node)
    spaces = _merge_spaces(labels_grid, warnings)

    col_needs, row_needs = [], []
    for sp in spaces:
        child = _child_for_space(children_by_label, sp["label"])
        if child is None:
            continue
        need_w = _span_has_auto(col_tracks, sp["c0"], sp["c1"])
        need_l = _span_has_auto(row_tracks, sp["r0"], sp["r1"])
        if not (need_w or need_l):
            continue
        w, l = _intrinsic_size(child, warnings, intrinsic_memo)
        if need_w:
            col_needs.append((sp["c0"], sp["c1"], w))
        if need_l:
            row_needs.append((sp["r0"], sp["r1"], l))

    col_auto = _distribute_auto_demand(col_tracks, col_needs)
    row_auto = _distribute_auto_demand(row_tracks, row_needs)

    col_starts, col_sizes, total_w = _resolve_tracks(
        col_tracks, given_w, col_auto, "{} CellWidths".format(name), warnings)
    row_starts, row_sizes, total_l = _resolve_tracks(
        row_tracks, given_h, row_auto, "{} CellLengths".format(name), warnings)

    overrides = _node_overrides(node, warnings)
    cell_deltas = {}
    if overrides:
        # Zero-sum by construction (one track grows exactly as much as
        # its neighbour shrinks) -- total_w/total_l never need
        # recomputing after this.
        _apply_shared_offsets(labels_grid, children_by_label, col_starts,
                               col_sizes, row_starts, row_sizes, overrides,
                               name, warnings)
        cell_deltas = _cell_independent_deltas(
            labels_grid, children_by_label, len(row_sizes), len(col_sizes),
            overrides, name, warnings)

    return (col_starts, col_sizes, total_w, row_starts, row_sizes, total_l,
            spaces, children_by_label, labels_grid, cell_deltas,
            effective_mirror)


def _intrinsic_size(node, warnings, memo):
    # Mirroring only ever reorders tracks (a bijection) -- the SUM
    # (total_w/total_l) a hosted parent actually needs from this child
    # is identical either way, so this never needs to know the child's
    # own eventual mirror state, and stays safely memoized by node id
    # alone regardless of where (mirrored or not) it's hosted.
    key = id(node)
    if key in memo:
        return memo[key]
    _, _, total_w, _, _, total_l, _, _, _, _, _ = _resolve_node(
        node, None, None, warnings, memo)
    memo[key] = (total_w, total_l)
    return total_w, total_l


def _polygon_curve(plane, points):
    closed = list(points) + [points[0]]
    world = [plane.PointAt(px, py, 0.0) for px, py in closed]
    return rg.PolylineCurve(world)


def _rect_curve(plane, x0, y0, x1, y1):
    return _polygon_curve(plane, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


# -----------------------------------------------------------------
# WALL LAYOUTS -- an upright child hosted on a border rather than a
# cell (node['borderOverrides'][i]['wallLayout'], a nested Layout2 doc
# with CellWidths == ['auto']). Structural position, plane convention,
# and the outward-normal guarantee are all UNCHANGED from the original
# (pms-layout-geom-v0.py's own WALL LAYOUTS section) -- _wall_plane_
# axes/_upright_plane_from are pure geometry (edge code + segment
# endpoints in, a plane out) and never depended on Borders/Topology at
# all, so they're ported verbatim. What's genuinely NEW, because
# Borders/Topology are permanently out of scope for Geom2, is HOW a
# matching boundary is found: no per-node borders pass to filter --
# a direct, LAZY scan of cell adjacency, done only for nodes that
# actually carry a wallLayout-bearing override, exactly like offsets
# already do for deltas. A cell's own side is a candidate IFF the
# override's own rule says so (pair: ref label's side touching the
# other label, or off-grid if the other side is 'EXT'; ring: the
# anchor's side touching anything real -- off-grid or a different
# label -- same "doesn't care what's beyond" rule Offset's ring uses);
# adjacent candidates along the same line merge into ONE run (a
# multi-cell touch, e.g. two modules each 2 rows tall, becomes ONE
# wall, not two) -- same "adjacent cells sharing a label merge into
# one run" idea the original's own PERIMETER logic used, just derived
# from raw grid adjacency instead of a traced boundary. PHASE 1
# LIMITATION carries over unchanged: a run whose own cells have
# diverged (no longer share one straight, coincident edge -- e.g. an
# INDEPENDENT offset that grew both sides toward each other) is warned
# and skipped rather than guessed at, matching the original's own
# deferred scope for a diverged boundary.
# -----------------------------------------------------------------

def _xyz(v):
    """(x, y, z) from a Point3d/Vector3d-like object (.X/.Y/.Z) or a
    plain (x, y, z) tuple -- real Rhino types always expose .X/.Y/.Z;
    the headless test harness's PointAt returns plain tuples."""
    if hasattr(v, "X"):
        return v.X, v.Y, v.Z
    return v[0], v[1], v[2]


def _cross(a, b):
    ax, ay, az = a
    bx, by, bz = b
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)


def _wall_plane_axes(edge, seg):
    """Given which edge a (possibly offset) segment represents,
    relative to its owning (reference) space, and that segment's own 2
    endpoints -- returns (origin_xy, second_xy), the FIRST corner and
    the SECOND, per that space's own CCW polygon traversal (_rect_
    curve's fixed point order, (x0,y0)->(x1,y0)->(x1,y1)->(x0,y1)) for
    that specific edge: S: west -> east. E: south -> north. N: east ->
    west. W: north -> south. Combined with a wall Y-axis of parent-up,
    X = (origin -> second) ALWAYS gives an outward-pointing plane
    normal (X cross Y) -- verified for all 4 edges, matches PMS-R7's
    own wall convention. Identical to the original Geom's own function
    of the same name -- pure geometry, no bbox/space lookup at all."""
    x0, y0, x1, y1 = seg
    if edge in ("S", "N"):
        west, east = ((x0, y0), (x1, y1)) if x0 <= x1 else ((x1, y1), (x0, y0))
        return (west, east) if edge == "S" else (east, west)
    south, north = ((x0, y0), (x1, y1)) if y0 <= y1 else ((x1, y1), (x0, y0))
    return (south, north) if edge == "E" else (north, south)


def _upright_plane_from(parent_plane, origin_xy, second_xy):
    """The wall's own plane: origin at origin_xy (parent-local 2D),
    X-axis toward second_xy (the border's own direction), Y-axis the
    PARENT's own up (its XAxis cross YAxis). See _wall_plane_axes for
    why this always gives an outward-pointing normal. Identical to the
    original Geom's own function of the same name."""
    ox, oy = origin_xy
    sx, sy = second_xy
    dx, dy = sx - ox, sy - oy
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0.0:
        dx, dy, length = 1.0, 0.0, 1.0
    ux, uy = dx / length, dy / length
    px = _xyz(parent_plane.XAxis)
    py = _xyz(parent_plane.YAxis)
    x_axis = (ux * px[0] + uy * py[0],
              ux * px[1] + uy * py[1],
              ux * px[2] + uy * py[2])
    y_axis = _cross(px, py)
    ox_w, oy_w, oz_w = _xyz(parent_plane.PointAt(ox, oy, 0.0))
    return rg.Plane(
        rg.Point3d(ox_w, oy_w, oz_w),
        rg.Vector3d(*x_axis),
        rg.Vector3d(*y_axis),
    )


def _wall_cellwidths_ok(cw):
    """A wallLayout's own CellWidths is valid EITHER as exactly
    ['auto'] (the simple, single-column case -- Geom2 fills it in
    wholesale from the matched border's own actual length) OR as a
    list with no 'auto' entry at all but at least one 'fr' track (e.g.
    ['400','1fr','400'] -- fixed frame pieces either side of a window
    column that soaks up whatever length is left over, resolved
    against the matched border's own actual length exactly like any
    other Layout2 grid's own track resolution). Mixing 'auto' with
    anything else, or an all-fixed list with no 'fr' to guarantee the
    columns still sum to the wall's own real length, is rejected.
    Identical rule to pms-layout2-border-override-v0.py's own
    validation of the same name -- kept in both files on purpose (no
    shared imports between components in this prototype)."""
    if cw == ["auto"]:
        return True
    if not isinstance(cw, list) or not cw:
        return False
    if any(t == "auto" for t in cw):
        return False
    return any(isinstance(t, string_types) and t.endswith("fr") for t in cw)


def _node_wall_layouts(node, warnings):
    """PAIR and RING overrides that carry a 'wallLayout' document.
    Returns a list of (mode, a, b, side, wall_layout, wall_height)
    tuples (wall_height is the override's optional 'wallHeight', mm,
    or None -- the total the wall's own CellLengths resolve against) -- GLOBAL
    has no border-owning-child concept to hang a wall layout on
    (warned, skipped -- no single anchor). Either label side (or a
    ring's anchor) may itself be a comma-separated list, expanded via
    _split_labels. Identical to the original Geom's own function of
    the same name (pure grammar, independent of how boundaries are
    found)."""
    out = []
    for od in (node.get("borderOverrides") or []):
        if not isinstance(od, dict):
            continue
        wall_layout = od.get("wallLayout")
        if not isinstance(wall_layout, dict):
            continue
        wall_height = od.get("wallHeight")
        if wall_height is not None:
            try:
                wall_height = float(wall_height)
            except (TypeError, ValueError):
                wall_height = None
            if wall_height is None or wall_height <= 0:
                warnings.append(
                    "wallLayout: wallHeight {!r} isn't a positive number "
                    "-- ignored.".format(od.get("wallHeight")))
                wall_height = None
        if not _wall_cellwidths_ok(wall_layout.get("cellWidths")):
            warnings.append(
                "wallLayout: CellWidths must be exactly ['auto'], or a "
                "list with no 'auto' but at least one 'fr' track -- "
                "got {!r} -- skipped.".format(wall_layout.get("cellWidths")))
            continue
        between = od.get("between")
        parsed = _parse_between(between if isinstance(between, list) else [],
                                 warnings)
        if parsed is None:
            continue
        mode, a, b, side = parsed
        if mode == "global":
            warnings.append(
                "wallLayout: 'global' selector has no border-owning-"
                "child concept yet -- needs a specific anchor (a pair "
                "or a ring) -- skipped.")
            continue
        if mode == "ring":
            for aa in _split_labels(a):
                out.append((mode, aa, None, side, wall_layout, wall_height))
        else:
            for aa in _split_labels(a):
                for bb in _split_labels(b):
                    out.append((mode, aa, bb, side, wall_layout, wall_height))
    return out


def _wall_candidates(labels_grid, nrows, ncols, mode, a, b, side):
    """(r, c, edge, nb, ref_label, nb_label) tuples -- one per candidate
    cell-side matching this wall_layouts entry's own rule, deduplicated
    so a SYMMETRIC query (e.g. a base-label pair like ['m','m'], or a
    ring anchor that touches another cell also matching its own
    anchor) still finds each PHYSICAL boundary exactly once --
    whichever of the two touching cells is reached first in raster
    order (row, then column) becomes the reference; the mirror
    encounter from the other side is skipped via the `seen` set,
    deterministic regardless of `side`'s own iteration order. `nb` is
    None for an off-grid (EXT) match, and `nb_label` is then None too.
    ref_label/nb_label are each cell's own LITERAL label (not the
    query's own possibly-base-label anchor) -- _group_wall_runs uses
    them to break a run wherever the actual label on either side
    changes, same as the original Geom's own PERIMETER walk ('adjacent
    cells sharing a label merge into one run, a label change breaks
    it') -- a base-label anchor like 'm' can still match several
    DIFFERENT literal instances (m[0], m[1], ...) side by side, and
    those must stay separate walls, not merge just because they're
    grid-adjacent."""
    ALL_SIDES = ("N", "S", "E", "W")
    sides = side if side is not None else ALL_SIDES

    def label_at(r, c):
        return labels_grid[r][c]

    candidates = []
    seen = set()

    if mode == "ring":
        if a == "EXT":
            # Every cell, on every requested side that's truly off-grid.
            for r in range(nrows):
                for c in range(ncols):
                    label = label_at(r, c)
                    if not label:
                        continue
                    for s in sides:
                        if _neighbor_rc(r, c, s, nrows, ncols) is None:
                            candidates.append((r, c, s, None, label, None))
            return candidates
        if a == "INT":
            # Mirror of EXT -- every labelled cell, on every requested
            # side whose neighbour is a DIFFERENT real label (never
            # off-grid -- that's EXT's own job, and never the SAME
            # label -- that's an internal seam, not a real boundary).
            for r in range(nrows):
                for c in range(ncols):
                    label = label_at(r, c)
                    if not label:
                        continue
                    for s in sides:
                        nb = _neighbor_rc(r, c, s, nrows, ncols)
                        if nb is None:
                            continue
                        nb_label = label_at(*nb)
                        if nb_label == label:
                            continue
                        key = frozenset(((r, c), nb))
                        if key in seen:
                            continue
                        seen.add(key)
                        candidates.append((r, c, s, nb, label, nb_label))
            return candidates
        for r in range(nrows):
            for c in range(ncols):
                label = label_at(r, c)
                if not _matches_label(label, [a]):
                    continue
                for s in sides:
                    nb = _neighbor_rc(r, c, s, nrows, ncols)
                    nb_label = label_at(*nb) if nb is not None else None
                    if nb is not None and nb_label == label:
                        continue  # same-label internal seam, not real
                    key = (r, c, s) if nb is None else frozenset(((r, c), nb))
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append((r, c, s, nb, label, nb_label))
        return candidates

    # pair
    if a == "EXT" and b == "EXT":
        return candidates
    ref_is_a = a != "EXT"
    ref_label = a if ref_is_a else b
    other_label = b if ref_is_a else a
    for r in range(nrows):
        for c in range(ncols):
            label = label_at(r, c)
            if not _matches_label(label, [ref_label]):
                continue
            for s in sides:
                nb = _neighbor_rc(r, c, s, nrows, ncols)
                if other_label == "EXT":
                    if nb is None:
                        candidates.append((r, c, s, None, label, None))
                    continue
                if nb is None:
                    continue
                nb_label = label_at(*nb)
                if not _matches_label(nb_label, [other_label]):
                    continue
                key = frozenset(((r, c), nb))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((r, c, s, nb, label, nb_label))
    return candidates


def _cell_edge_coord(rect, edge):
    x0, y0, x1, y1 = rect
    return {"E": x1, "W": x0, "N": y1, "S": y0}[edge]


def _neighbor_edge_coord(rect, edge):
    # The coordinate on the NEIGHBOUR side that should coincide with
    # this cell's own `edge` coordinate, for the two to still be
    # touching along a single straight line.
    x0, y0, x1, y1 = rect
    return {"E": x0, "W": x1, "N": y0, "S": y1}[edge]


def _group_wall_runs(candidates):
    """Groups candidates sharing the same line (edge direction + the
    axis index that stays constant along it) into maximal RUNS of
    consecutive cells -- a multi-cell touch (e.g. two modules each 2
    rows tall) becomes ONE run. A run breaks on a GAP (non-adjacent
    index) OR on a LABEL CHANGE on either side (ref or neighbour) --
    same as the original Geom's own PERIMETER walk: 'adjacent cells
    sharing a label merge into one run, a label change breaks it'.
    This is what keeps a floor-plan-wide EXT-ring wall split per ROOM
    (s1 | k | s2) instead of merging the whole side into one wall
    regardless of what's behind it -- the exact behavior the user
    explicitly chose to KEEP when JoinWalls was proposed and declined
    for the original (see the session's own design discussion) --
    while still letting a genuinely multi-cell SAME room (e.g. m[0]
    spanning 2 rows) merge into one wall. Returns a list of (edge, run)
    where run is a list of (r, c, nb), sorted along the run's own
    varying axis."""
    groups = {}
    for (r, c, edge, nb, ref_lbl, nb_lbl) in candidates:
        if edge in ("E", "W"):
            key, var = (edge, c), r
        else:
            key, var = (edge, r), c
        groups.setdefault(key, []).append((var, r, c, nb, ref_lbl, nb_lbl))
    runs = []
    for (edge, _fixed), items in groups.items():
        items.sort(key=lambda t: t[0])
        prev_var, prev_labels = items[0][0], (items[0][4], items[0][5])
        run = [items[0][1:4]]
        for item in items[1:]:
            labels = (item[4], item[5])
            if item[0] == prev_var + 1 and labels == prev_labels:
                run.append(item[1:4])
            else:
                runs.append((edge, run))
                run = [item[1:4]]
            prev_var, prev_labels = item[0], labels
        runs.append((edge, run))
    return runs


_OPPOSITE_EDGE = {"E": "W", "W": "E", "N": "S", "S": "N"}


def _wall_run_placements(edge, run, rect_of_cell, ab_desc, name, warnings):
    """One (seg, edge, extra_mirror) placement per wall instance this
    run needs. While the reference side's own cells agree with each
    other (own_coords) AND (if there's a real neighbour) the
    neighbour's own cells ALSO agree with each other (nb_coords) --
    both required for a single straight line to even be well-defined
    -- either side's own cells disagreeing WITH THEMSELVES is refused,
    warned (returns []).

    An EXT-anchored run (no real neighbour) or an undiverged one
    (still coincident) needs only ONE instance, at the reference
    side's own edge, extra_mirror=False (this node's own inherited
    mirror state applies, unchanged from before).

    A DIVERGED interior run (an INDEPENDENT offset moved the two sides
    apart -- a gap -- or into each other -- an overlap) needs TWO: one
    at the reference side's (Between[0], or the ring/INT anchor) own
    edge, unmirrored relative to this node's own state -- the FIRST
    Between item is the LEADING, as-authored side -- and one at the
    neighbour's own edge, on the OPPOSITE edge code (its own side of
    the same physical boundary), extra_mirror=True (XOR-flipped
    relative to the reference instance, composing with whatever this
    node's own inherited mirror state already is) -- see MIRROR in the
    module docstring for why reversing the width axis is exactly what
    keeps the SAME wallLayout content aligned at the SAME physical
    spot on both sides despite the mirrored winding each side's own
    correct outward normal requires. Same length-axis span (ys/xs) is
    shared by both instances -- only the fixed (perpendicular)
    coordinate and the edge/mirror differ."""
    own_coords = set()
    nb_coords = set()
    for (r, c, nb) in run:
        rect = rect_of_cell(r, c)
        own_coords.add(_cell_edge_coord(rect, edge))
        if nb is not None:
            nb_coords.add(_neighbor_edge_coord(rect_of_cell(*nb), edge))
    if len(own_coords) > 1:
        warnings.append(
            "{}: wall layout on border {!r} couldn't be placed -- this "
            "run's own cells no longer share one straight edge with "
            "EACH OTHER -- not supported, skipped."
            .format(name, ab_desc))
        return []
    if len(nb_coords) > 1:
        warnings.append(
            "{}: wall layout on border {!r} couldn't be placed -- its "
            "own neighbour's cells no longer share one straight edge "
            "with EACH OTHER -- not supported, skipped."
            .format(name, ab_desc))
        return []
    fixed = own_coords.pop()
    if edge in ("E", "W"):
        ys = [v for (r, c, _nb) in run for v in rect_of_cell(r, c)[1::2]]
        seg_ref = (fixed, min(ys), fixed, max(ys))
    else:
        xs = [v for (r, c, _nb) in run for v in rect_of_cell(r, c)[0::2]]
        seg_ref = (min(xs), fixed, max(xs), fixed)
    placements = [(seg_ref, edge, False)]
    if nb_coords:
        nb_fixed = nb_coords.pop()
        if nb_fixed != fixed:
            warnings.append(
                _REMARK_PREFIX +
                "{}: wall layout on border {!r} -- this boundary has "
                "diverged (an independent offset moved each side on "
                "its own) -- placed as TWO instances, one per side's "
                "own actual edge, the second (neighbour's own side) "
                "mirrored so the same content stays aligned despite "
                "the winding each side's own outward normal needs."
                .format(name, ab_desc))
            # opp_edge always shares the same E/W-vs-N/S axis as edge
            # (opposites never cross axes), so the same ys/xs span
            # already computed above still applies here unchanged.
            opp_edge = _OPPOSITE_EDGE[edge]
            if edge in ("E", "W"):
                seg_nb = (nb_fixed, min(ys), nb_fixed, max(ys))
            else:
                seg_nb = (min(xs), nb_fixed, max(xs), nb_fixed)
            placements.append((seg_nb, opp_edge, True))
    return placements


def _place_walls(node, name, labels_grid, nrows, ncols, rect_of_cell, plane,
                  path, spaces, used_index_count, cells_tree, labels_tree,
                  warnings, intrinsic_memo, union, mirror):
    """Finds every wallLayout-carrying override on this node, places
    one wall (a recursive _emit call) per matched, non-diverged run --
    TWO for a run that's genuinely diverged (see _wall_run_placements),
    the second one XOR-mirrored relative to this node's own inherited
    state so the SAME wallLayout content stays aligned on both sides
    despite the opposite winding each side's own correct outward
    normal needs.

    Each placement's own HOST is whichever space it's actually matched
    to -- the reference side's own space for the primary instance, the
    NEIGHBOUR's own space for a diverged run's second (mirrored)
    instance -- found by looking up that side's own literal label
    (already known per candidate/run) in `spaces` (already computed by
    _resolve_node). The wall recurses DIRECTLY into that host's own
    space_path -- exactly like an ordinary hosted child does -- so its
    OWN top-level content (door, frame, ...) lands at the SAME DEPTH a
    hosted child's own top-level spaces would, one segment under the
    host, not two. There's no separate wrapper segment for "the wall
    itself" at all.

    Since more than one wall placement (or an ordinary hosted child)
    can share ONE host, each gets its own INDEX OFFSET within that
    host's own numbering instead of colliding: `used_index_count`
    (built by _emit's own per-space loop, BEFORE this function ever
    runs) tells us how many indices the host's own regular child, if
    any, already claimed at index 0..N-1 -- wall content picks up
    exactly where that leaves off, via `_emit`'s own `index_offset`
    parameter. Every placement whose own wallLayout document shares
    the SAME 'label' AND the SAME host space (e.g. two opposite 'pf'
    walls both matched to 'm[0]') reuses the SAME offset, instead of
    each claiming its own -- their own recursive content (frame, door,
    ...) then lands together in the same sub-branch, same mechanism a
    bare multi-cell space already uses to hold N rectangles in one
    branch. Two 'pf' walls matched to DIFFERENT hosts (one to 'm[0]',
    one to 'm[1]') are never grouped together -- they're not even
    siblings any more, let alone candidates for the same branch. This
    is deliberately scoped to WITHIN one _place_walls call (one node's
    own local scope) -- it does NOT attempt to group walls placed by a
    DIFFERENT node's own _place_walls call -- that would need
    tree-wide state nothing else in this file has, a fundamentally
    different (and NOT built) problem. An unlabeled wallLayout still
    nests under its own host, just always gets its own fresh offset
    there (advanced by however many top-level spaces its own content
    turns out to have), nothing to group by.

    (Every candidate's own label always matches a real space, since
    _merge_spaces already grouped the WHOLE grid -- the lookup is
    defensive, not expected to ever miss, but falls back to nesting
    under this NODE's own path instead, warned, rather than crashing,
    if it somehow does -- own index sequence, independent of any real
    space's.)

    `wall_height` (the override's optional 'wallHeight') is passed as
    the wall's own given_h, so 'fr' rows in its CellLengths have a
    total to share -- without it the wall has no height total and an
    'fr' row resolves to 0mm. None = unchanged from before it existed.

    `mirror` is this NODE's own effective mirror state (already
    resolved by _emit) -- a mirrored apartment's own walls mirror too,
    same cascading rule as any other hosted child."""
    label_to_space_index = {}
    for i, sp in enumerate(spaces):
        if sp["label"] and sp["label"] not in label_to_space_index:
            label_to_space_index[sp["label"]] = i

    _FALLBACK_HOST_KEY = object()
    next_offset_by_host = dict(used_index_count)
    offset_by_host_and_label = {}

    def _host_path_and_key(host_label):
        idx = label_to_space_index.get(host_label)
        if idx is None:
            warnings.append(
                "{}: wall layout's own host label {!r} doesn't match "
                "any space on this node -- nesting under this node's "
                "own path instead, not the host's.".format(name, host_label))
            return path, _FALLBACK_HOST_KEY
        return path.AppendElement(idx), idx

    for (mode, a, b, side, wall_doc, wall_height) in _node_wall_layouts(node, warnings):
        candidates = _wall_candidates(labels_grid, nrows, ncols, mode, a, b, side)
        ab_desc = [a, b if mode == "pair" else "*"]
        wall_label = wall_doc.get("label")
        has_wall_label = isinstance(wall_label, string_types) and bool(wall_label)
        for (edge, run) in _group_wall_runs(candidates):
            ref_label = labels_grid[run[0][0]][run[0][1]]
            nb_label = None
            for (r, c, nb) in run:
                if nb is not None:
                    nb_label = labels_grid[nb[0]][nb[1]]
                    break
            placements = _wall_run_placements(
                edge, run, rect_of_cell, ab_desc, name, warnings)
            for (seg, seg_edge, extra_mirror) in placements:
                origin_xy, second_xy = _wall_plane_axes(seg_edge, seg)
                wall_plane = _upright_plane_from(plane, origin_xy, second_xy)
                wall_len = ((second_xy[0] - origin_xy[0]) ** 2
                            + (second_xy[1] - origin_xy[1]) ** 2) ** 0.5
                wall_doc_resolved = dict(wall_doc)
                if wall_doc_resolved.get("cellWidths") == ["auto"]:
                    # The simple, single-column case -- wholesale-replace
                    # the placeholder with the matched length directly.
                    wall_doc_resolved["cellWidths"] = [wall_len]
                # else: a relaxed, mixed CellWidths (fixed + 'fr' tracks,
                # no 'auto') is left AS AUTHORED -- given_w=wall_len below
                # already makes _resolve_tracks' own 'fr' handling soak up
                # whatever's left after the fixed tracks, exactly like any
                # other Layout2 grid resolves against a given total. No
                # new solving logic needed for this case at all.
                host_label = nb_label if extra_mirror else ref_label
                host_path, host_key = _host_path_and_key(host_label)
                group_key = (host_key, wall_label) if has_wall_label else None
                effective_mirror = (mirror != extra_mirror)
                if group_key is not None and group_key in offset_by_host_and_label:
                    this_offset = offset_by_host_and_label[group_key]
                    _emit(wall_doc_resolved, wall_len, wall_height, wall_plane,
                          host_path, cells_tree, labels_tree, warnings,
                          intrinsic_memo, union, effective_mirror, this_offset)
                else:
                    this_offset = next_offset_by_host.get(host_key, 0)
                    _, _, wall_space_count = _emit(
                        wall_doc_resolved, wall_len, wall_height, wall_plane,
                        host_path, cells_tree, labels_tree, warnings,
                        intrinsic_memo, union, effective_mirror, this_offset)
                    next_offset_by_host[host_key] = this_offset + wall_space_count
                    if group_key is not None:
                        offset_by_host_and_label[group_key] = this_offset


# -----------------------------------------------------------------
# EMIT -- the actual tree-shape change. See the module docstring.
# Borders/Topology are OUT for now (back to basics -- see the module
# docstring) -- Cells/Labels addressing only.
# -----------------------------------------------------------------

def _emit(node, given_w, given_h, plane, path, cells_tree, labels_tree,
           warnings, intrinsic_memo, union, mirror=False, index_offset=0):
    """... `index_offset` shifts every one of THIS node's own top-level
    space indices (path.AppendElement(i + index_offset) instead of
    just i) -- 0 for every ordinary call (root, child recursion), only
    ever nonzero when _place_walls recurses a wallLayout directly into
    its own matched host space's path, continuing that host's own
    already-used index range instead of colliding with it (see
    _place_walls). Returns (total_w, total_l, len(spaces)) -- the 3rd
    value lets a caller reserve exactly this many indices before
    handing out any more at the SAME path (used by both the ordinary
    child-recursion call site below and by _place_walls)."""
    (col_starts, col_sizes, total_w, row_starts, row_sizes, total_l,
     spaces, children_by_label, labels_grid, cell_deltas,
     effective_mirror) = _resolve_node(
        node, given_w, given_h, warnings, intrinsic_memo, mirror)

    def rect_of_cell(r, c):
        x0 = col_starts[c]
        x1 = col_starts[c] + col_sizes[c]
        y1 = total_l - row_starts[r]
        y0 = y1 - row_sizes[r]
        dx0, dy0, dx1, dy1 = cell_deltas.get((r, c), (0.0, 0.0, 0.0, 0.0))
        return x0 + dx0, y0 + dy0, x1 + dx1, y1 + dy1

    def rect_of_space(sp):
        x0 = col_starts[sp["c0"]]
        x1 = col_starts[sp["c1"]] + col_sizes[sp["c1"]]
        y1 = total_l - row_starts[sp["r0"]]
        y0 = total_l - row_starts[sp["r1"]] - row_sizes[sp["r1"]]
        # A space can span several cells (a bare, merged label) -- its
        # own OUTER edges pick up whichever of ITS OWN boundary cells'
        # deltas apply there (the cell that actually SITS on that
        # edge). Simplified vs. a fully general non-rectangular offset:
        # assumes the boundary cells touching one edge agree, which
        # holds for every case actually in scope right now (single-
        # cell indexed labels, or a whole bare group offset uniformly
        # via one ring/EXT match) -- good enough for this prototype
        # pass, revisit only if a real case needs more.
        dx0 = dy0 = dx1 = dy1 = 0.0
        for (r, c) in sp["cells"]:
            d = cell_deltas.get((r, c))
            if not d:
                continue
            cdx0, cdy0, cdx1, cdy1 = d
            if c == sp["c0"] and cdx0:
                dx0 = cdx0
            if c == sp["c1"] and cdx1:
                dx1 = cdx1
            if r == sp["r0"] and cdy1:
                dy1 = cdy1
            if r == sp["r1"] and cdy0:
                dy0 = cdy0
        return x0 + dx0, y0 + dy0, x1 + dx1, y1 + dy1

    name = node.get("label") or "<root>"
    used_index_count = {}

    for i, sp in enumerate(spaces):
        space_path = path.AppendElement(i + index_offset)
        cells_tree.EnsurePath(space_path)
        labels_tree.EnsurePath(space_path)

        if sp["label"]:
            # Union only ever collapses a BARE (non-'[k]'-suffixed)
            # label's own multi-cell group -- '[k]' on a label is the
            # do-NOT-merge marker (see _merge_spaces / the original
            # Geom's own docstring): it signals a deliberately distinct
            # instance, not "these pieces should draw as one shape", so
            # Union leaves it as N separate rectangles regardless of
            # the toggle's own state.
            indexed = _base_label(sp["label"]) != sp["label"]
            if union and not indexed and len(sp["cells"]) > 1:
                # A REAL geometric union, not a hand-rolled edge trace
                # -- deliberately, see the module docstring. Handles
                # whatever an independent offset has done to this
                # group's own cells correctly, by construction: still
                # touching -> one shape; grown into an overlap -> one
                # (larger) shape; pulled apart into a real gap -> that
                # many SEPARATE curves, honestly, rather than either
                # guessing at a combined outline or refusing to draw
                # anything. No non-rectangular-edge-tracing logic
                # lives in this component at all any more.
                cell_curves = [
                    _rect_curve(plane, *rect_of_cell(r, c))
                    for (r, c) in sorted(sp["cells"])]
                unioned = rg.Curve.CreateBooleanUnion(cell_curves, 0.01)
                if not unioned:
                    warnings.append(
                        "label {!r}: Union failed to combine its own "
                        "cells -- drawn as separate rectangles instead."
                        .format(sp["label"]))
                    unioned = cell_curves
                for crv in unioned:
                    cells_tree.Add(crv, space_path)
                    labels_tree.Add(sp["label"], space_path)
            else:
                for (r, c) in sorted(sp["cells"]):
                    cells_tree.Add(_rect_curve(plane, *rect_of_cell(r, c)),
                                    space_path)
                    labels_tree.Add(sp["label"], space_path)

        child = _child_for_space(children_by_label, sp["label"])
        if child is not None:
            # Reuse space_path directly (NOT space_path.AppendElement(0))
            # -- sp's own item(s) already sit AT space_path; the child's
            # own top-level spaces then land at space_path.AppendElement(j2)
            # inside the recursive call below, exactly one segment deeper,
            # never colliding with sp's own item(s). An earlier version
            # inserted an extra constant-0 "child container" segment here,
            # which DOUBLED the path cost per recursion level (one segment
            # for the container, one more for the child's own per-space
            # branching) instead of costing one segment like the original
            # Geom's flat-list recursion does -- compounding with nesting
            # depth instead of staying a flat, constant offset.
            x0, y0, x1, y1 = rect_of_space(sp)
            child_plane = rg.Plane(
                plane.PointAt(x0, y0, 0.0), plane.XAxis, plane.YAxis)
            _, _, child_space_count = _emit(
                child, x1 - x0, y1 - y0, child_plane, space_path,
                cells_tree, labels_tree, warnings, intrinsic_memo, union,
                effective_mirror)
            # A wall hosted at this SAME space (see _place_walls, called
            # below once every space's own child has already claimed its
            # indices) continues numbering from here -- never starting
            # back at 0 and colliding with the child's own top-level
            # spaces, which already live at space_path.AppendElement(0..).
            used_index_count[i] = child_space_count

    _place_walls(node, name, labels_grid, len(row_sizes), len(col_sizes),
                 rect_of_cell, plane, path, spaces, used_index_count,
                 cells_tree, labels_tree, warnings, intrinsic_memo, union,
                 effective_mirror)

    return total_w, total_l, len(spaces)


def _filter_by_depth(tree, depth):
    out = gh.DataTree[object]()
    target_length = depth + 1
    for i in range(tree.Paths.Count):
        path = tree.Paths[i]
        if path.Length == target_length:
            for item in tree.Branches[i]:
                out.Add(item, path)
    return out


def _filtered_cells_and_labels(cells_tree, labels_tree, wanted):
    """OPTIONAL SELECTOR (the 'Cells' input) -- keep only cells_tree
    items whose PARALLEL labels_tree entry (same path, same index --
    see _emit, they're always added in lockstep) matches `wanted`, and
    return a MATCHING, equally filtered labels_tree alongside it, kept
    in lockstep so Labels stays parallel to Cells once Cells itself is
    being narrowed. A path with no labels_tree entry at all (a
    hosted-child container branch that holds no item of its own) never
    matches. Identical to the original Geom's own function of the same
    name -- pure tree filtering, independent of how the tree got
    built."""
    cells_out = gh.DataTree[object]()
    labels_out = gh.DataTree[object]()
    for i in range(cells_tree.Paths.Count):
        path = cells_tree.Paths[i]
        items = cells_tree.Branches[i]
        lbls = labels_tree.Branch(path) or []
        cells_out.EnsurePath(path)
        labels_out.EnsurePath(path)
        for j, item in enumerate(items):
            lbl = lbls[j] if j < len(lbls) else None
            if isinstance(lbl, string_types) and _matches_label(lbl, wanted):
                cells_out.Add(item, path)
                labels_out.Add(lbl, path)
    return cells_out, labels_out


def _split_warnings(warnings):
    """Separates genuine problems from informational notes
    (_REMARK_PREFIX) -- returns (real_warnings, remarks), remarks with
    the prefix stripped. Checked as `in`, not `startswith`: when more
    than one item is fed into the (list-access) JSON input, run()
    wraps each item's own warnings as "item {i}: {w}" BEFORE this
    runs, which pushes _REMARK_PREFIX away from the very start --
    `startswith` silently missed every remark in that case (real bug,
    caught live: a remark fell through to the runtime-message balloon,
    raw, unstripped prefix and all, and the Warnings output stayed
    empty), `in` doesn't care where the prefix landed."""
    remarks = [w.replace(_REMARK_PREFIX, "", 1) for w in warnings if _REMARK_PREFIX in w]
    real_warnings = [w for w in warnings if _REMARK_PREFIX not in w]
    return real_warnings, remarks


# -----------------------------------------------------------------
# Main.
# -----------------------------------------------------------------

def run():
    component = ghenv.Component  # noqa: F821
    component.ClearRuntimeMessages()
    warnings = []
    g = globals()

    if not _HAS_RHINO:
        component.AddRuntimeMessage(
            gh.Kernel.GH_RuntimeMessageLevel.Error,
            "Rhino.Geometry is not available -- this component needs Rhino.")
        return

    json_list = [j for j in (g.get("JSON") or []) if _present(j)]
    if not json_list:
        g["Cells"] = None
        g["Labels"] = None
        g["Warnings"] = None
        return

    plane_in = goo_value(g.get("Plane"))
    geom_plane = plane_in if isinstance(plane_in, rg.Plane) else rg.Plane.WorldXY
    xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, geom_plane)

    union = bool(goo_value(g.get("Union")))

    cells_tree = gh.DataTree[object]()
    labels_tree = gh.DataTree[object]()
    many = len(json_list) > 1

    for i, json_in in enumerate(json_list):
        item_warnings = []
        root = parse_json_str(goo_value(json_in))
        if not isinstance(root, dict):
            item_warnings.append("JSON couldn't be parsed as a JSON object.")
            for w in item_warnings:
                warnings.append("item {}: {}".format(i, w) if many else w)
            continue

        item_plane = _plane_from_dict(root.get("plane")) or rg.Plane.WorldXY
        item_plane.Transform(xform)

        root_path = gh.Kernel.Data.GH_Path(i)
        intrinsic_memo = {}
        # root_path directly, NOT root_path.AppendElement(0) -- same
        # fix as _emit's own child recursion (see there): root_path
        # itself only ever holds the root's own overall boundary curve
        # (added below), a DIFFERENT branch from root_path.AppendElement(j)
        # (a top-level space), so there's no collision reusing it here.
        # An earlier version inserted an extra constant-0 "children"
        # segment before top-level spaces got their own per-space
        # branch, pushing them to Depth 2 instead of Depth 1 -- the
        # SAME redundant-container bug the child-recursion fix already
        # addressed one level down, just not yet applied at the root.
        total_w, total_l, _ = _emit(
            root, None, None, item_plane, root_path,
            cells_tree, labels_tree, item_warnings, intrinsic_memo, union)

        cells_tree.Add(
            _rect_curve(item_plane, 0.0, 0.0, total_w, total_l), root_path)
        root_label = root.get("label")
        if isinstance(root_label, string_types) and root_label:
            labels_tree.Add(root_label, root_path)

        for w in item_warnings:
            warnings.append("item {}: {}".format(i, w) if many else w)

    depth_in = goo_value(g.get("Depth"))
    try:
        depth = int(depth_in) if depth_in is not None else 0
    except (TypeError, ValueError):
        warnings.append("Depth {!r} isn't an integer -- showing depth 0."
                         .format(depth_in))
        depth = 0
    if depth < 0:
        warnings.append("Depth {} must be >= 0 -- showing depth 0."
                         .format(depth))
        depth = 0

    max_depth = max((p.Length for p in cells_tree.Paths), default=1) - 1
    if depth > max_depth:
        warnings.append(
            "Depth {} is deeper than this tree goes (max {}) -- nothing "
            "to show at that depth.".format(depth, max_depth))

    cells_tree = _filter_by_depth(cells_tree, depth)
    labels_tree = _filter_by_depth(labels_tree, depth)

    # Selector runs AFTER Depth filtering -- only candidates already
    # inside the chosen Depth slice can ever be selected. Its own
    # label(s) may be a comma-separated LIST ('a,b', no brackets),
    # same _split_labels grammar borderOverrides uses.
    cells_wanted_raw = [goo_value(v) for v in (g.get("Cells") or [])]
    cells_wanted = []
    for v in cells_wanted_raw:
        if isinstance(v, string_types) and v:
            cells_wanted.extend(_split_labels(v))
    if cells_wanted:
        cells_tree, labels_tree = _filtered_cells_and_labels(
            cells_tree, labels_tree, cells_wanted)

    g["Cells"] = cells_tree
    g["Labels"] = labels_tree

    # Informational notes (_REMARK_PREFIX) describe correct, intended
    # behavior, not a problem -- they don't belong on the component's
    # own runtime-message balloon at all (even Remark-level still pops
    # up unprompted). They go out through the 'Warnings' output
    # instead, as plain data you can inspect (a Panel, a filter, a
    # count) only when you actually want to -- never in your face.
    # Genuine problems stay on the balloon, at Warning level, same as
    # always.
    real_warnings, remarks = _split_warnings(warnings)
    if real_warnings:
        component.AddRuntimeMessage(
            gh.Kernel.GH_RuntimeMessageLevel.Warning, "\n".join(real_warnings))
    g["Warnings"] = remarks


if _HAS_RHINO:
    run()
