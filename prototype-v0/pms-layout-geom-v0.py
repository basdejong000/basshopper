"""PMS Layout Geom v0 -- solves a LIST of Layout JSON trees (each the
OUTERMOST pms-layout-v0 instance's JSON output for one independent
root -- a floor plan, a wall, whatever; each already recursively
embeds every nested level via childLayouts) and draws them: Cells (one
closed curve per merged SPACE -- a plain rectangle, or the traced
outline for an L / T / U-shaped merge, see CELLS below), Labels (one
string per space, parallel to Cells), Borders (lines -- interior grid
lines wherever the label changes, plus the 4 perimeter sides, segmented
per run instead of always whole-edge -- see BORDERS below) and Topology
(which space(s) each border touches -- see TOPOLOGY below). Every item
gets its own outer branch index -- item i's whole tree sits under
{i;...} -- so one Geom call can solve one lone floor plan or a whole
list of walls at once. Two optional SELECTOR inputs (Cells, Borders --
see SELECTORS below) further filter what actually reaches the four
outputs, without changing how anything solves.

PLANE -- for EACH item, independently: its own JSON's 'plane' field
(baked in by Layout's Boundary input, when that item is a wall or
anything else placed via a real-world boundary) or WorldXY if it has
none, then carried through PlaneToPlane(WorldXY, Geom.Plane). Geom.
Plane is therefore a TRANSFORM applied to whatever plane each item
already has, not a replacement for it: unwired (WorldXY, the default)
is the identity transform, so a lone item with no baked-in plane still
resolves at WorldXY exactly as before, and an item that DOES carry its
own plane keeps it untouched. Wire something into Geom.Plane and every
item -- however many, however differently placed via their own JSON --
gets repositioned together as one rigid unit, without disturbing their
placement relative to each other (moving a whole building's worth of
walls at once, say, without needing to touch any of their individual
planes).

SOLVING (moved here from the old all-in-one Layout component,
unchanged): 'auto' tracks size from a nested child's own INTRINSIC size
(computed with nothing externally imposed, recursively); 'fr' tracks
share the leftover of whatever total THIS node ends up with (0 at the
root, since nothing imposes a bigger total than its own tracks sum to);
'minmax(...)' isn't resolved yet (0mm, warned). A CellLabels grid whose
row/column count doesn't match CellWidths/CellLengths is clipped/padded
to fit (warned, not silently wrong).

CELLS: contiguous same-FULL-label cells (4-connected, row/column
neighbours) MERGE into one space, same as _borders always compared
labels for -- this is what makes cells and borders agree with each
other. The merge need not be a rectangle: L / T / U shapes trace their
real rectilinear outline (_region_outline walks each cell's edges that
border a DIFFERENT label and chains them into the boundary loop). '[k]'
is the do-NOT-merge marker, typed by hand: 'A1,A1' merges into one
space, but 'A1[0],A1[1]' stays two, even sitting right next to each
other -- e.g. two apartments that happen to share a party wall. Cells
that AREN'T adjacent never merge regardless of label (flood fill only
ever grows into touching neighbours), so two apartments on opposite
sides of a corridor, both plainly labelled 'a', are automatically two
separate spaces with no suffix needed at all -- '[k]' is only for the
adjacent-but-distinct case. Child-binding checks the EXACT label
first, falling back to the BASE label (_base_label strips '[...]') --
a child authored with label 'A1' lands in EVERY 'A1[k]' instance that
doesn't have its own more specific entry (the common case: one shared
template reused across repeated instances), but TWO children authored
with EXACT instance labels ('A1[0]' and a DIFFERENT 'A1[1]') each bind
to only their own instance instead of colliding on the same base-label
slot -- lets same-base siblings (e.g. two prefab modules sharing a
'mod' family label) host genuinely different children, not just
repeated copies of one template (see _node_children_by_label /
_child_for_space). An INDEPENDENT border offset (a ring, an EXT pair,
an EXT ring, or a both-children pair -- see BORDER OVERRIDES below)
applies to a non-rectangular merge too: every S/E/N/W-facing edge of
its traced outline shifts by that side's own delta, same as a plain
rectangle's matching side would, regardless of how many separate runs
of that direction the shape happens to have (an L or U shape's west
side, say) -- see _shift_outline_edges. Two things a non-rectangular
merge still can't do: a HOLE in the shape (two separate boundary loops
trace out -- only the outer one is drawn, warned) and hosting a CHILD
with its exact shape (a child needs a rectangular frame to solve
against, so it's placed on the merge's BOUNDING BOX instead, warned).

CELLS / LABELS TREE SHAPE:
  - A node's OWN CHILDREN sit together in ONE branch, as a plain list
    (row-major order: left-to-right, top-to-bottom, by each space's
    first/top-left-most cell) -- NOT one branch per space. A leaf
    space with no bound child is simply an item in that list.
  - A space WITH a bound child ALSO recurses into it: that child's own
    children (if it has any) get their own list-branch one level
    deeper, addressed by appending the PARENT space's row-major index
    -- from the branch the parent space itself was listed in -- not a
    per-child graft.
  - The ROOT is the one exception: nothing lists it, so its own
    overall boundary is drawn once, directly, at its bare item path
    {i}. Since {i} is already taken by that, the root's own CHILDREN
    (its first depth of cells) get the next branch down, {i;0} -- a
    constant 0, since there's only ever one root to be "the parent" of
    that list.
  - Worked example: label a (cells b1, b2), b1 (cells c1, c2), b2
    (cells c1, c2, c3). a's own boundary -> {0} (drawn once, by
    run()). a's children (b1, b2) -> ONE branch, {0;0}, a 2-item list.
    b1's children (c1, c2) -> {0;0;0} (0 = b1's row-major index within
    {0;0}'s list), a 2-item list. b2's children (c1, c2, c3) ->
    {0;0;1} (1 = b2's index), a 3-item list. If b1 or b2 had NO
    children, that whole branch simply wouldn't exist -- branch count
    at a given depth equals however many items one level up actually
    had a bound child, not the total space count at that depth.

DEPTH -- optional, a pure FILTER over the tree above, not a re-solve
(everything is always computed regardless of Depth; this only decides
what makes it to the output). Depth is 0-BASED and IS THE DEFAULT: no
Depth wired means Depth 0 (just the top parent's own boundary, {i}) --
"show every depth at once" was the old default and had no real use
case, so that mode is gone; Depth always filters now. 0 -> {i} (path
length 1), 1 -> {i;0} (length 2, the root's own children as one
list), 2 -> {i;0;j} (length 3, one branch per depth-1 item that had a
bound child), 3 -> {i;0;j;k} (length 4), etc -- path LENGTH = Depth +
1. Out of range (< 0, or deeper than the tree goes anywhere) warns and
falls back to Depth 0. You can always get a different combination
yourself downstream with ordinary GH tree tools (Path Mapper, Graft, a
branch-length filter, or referencing the exact branch by address) --
Depth exists purely as a convenience for "everything at one specific
level," not a substitute for GH's own tree tools. SELECTORS (below)
run AFTER Depth -- only candidates already inside the chosen Depth
slice can ever be selected.

BORDERS -- shares Cells/Labels' tree shape EXACTLY: a node's own
border computation (its interior divisions and its own perimeter,
each already split into per-run segments -- see below) lands in the
SAME branch as that node's own children cells, so the SAME Depth value
that selects a set of Cells also selects exactly the UNIQUE border
segments bounding them -- no separate addressing scheme, no
duplicates (each branch is one node's own single grid computation, not
a merge of several). The one exception is Depth 0: the top parent has
no grid of its own to walk (it's one un-subdivided shape), so its
"borders" are simply its own 4 sides, added directly by run() instead
of by _emit()/_borders() -- NOT yet subject to borderOverrides (see
below), which only apply within a node's own _emit()/_borders() walk.

BORDER OVERRIDES -- optional, node.get('borderOverrides'): a list of
pms-layout-border-override-v0 documents ({between, offset?}, see that
component's own docstring for the full `between` grammar -- pair /
ring / global / 'EXT'). `offset` is the only thing a document carries
-- suppressing a border entirely ("no wall here") is a pure display
decision with no geometric consequence, so it's deliberately NOT part
of this data model; do it downstream instead (this component's own
Borders selector below, or a plain Cull Pattern keyed on Topology).
Offset acts on a PAIR or a RING (global is warned and skipped -- there's
no single space for it to anchor to). Two independent things a PAIR
override with a real `offset` can do, decided by what's on each side of
it (never authored explicitly -- Geom infers it from whether each
matched space has a bound child):
  - SHARED (at least one side is a PLAIN cell, no bound child): the
    ONE track boundary between the two spaces shifts by `offset` mm
    (positive = toward Between[1]'s side) -- one track grows, its
    neighbour shrinks by the same amount, inside _resolve_node, before
    _emit even starts walking. If the OTHER side hosts a child, that
    child's own given rectangle is computed from these SAME (already-
    shifted) tracks later on, so it just inherits the new size --
    nothing extra to author for that (a mullion moving along with its
    window frame, say). Only handles two spaces that are each exactly
    one track wide/tall along the shared axis (the common case) --
    anything wider is skipped with a warning (_find_track_boundary).
  - INDEPENDENT (a PLAIN cell with no bound child at all against
    'EXT', OR BOTH sides host their own bound child -- e.g. two
    sliding-door panels, each its own nested Layout -- OR one side is
    'EXT' and the other hosts a child): the parent's own TRACK SIZES
    are untouched, but everything that's actually DRAWN for the
    matched space moves together, at every Depth: its own cell shape
    in Cells, its own matching perimeter segment in Borders (see
    below), and -- if it has one -- its child's given rectangle one
    level deeper, ALL get the same delta (_dumb_offset_for_space,
    called once per space in _emit). So looking at the space's own
    Depth already shows the shift; you don't have to recurse into its
    child to see it. EACH matched side independently extends toward
    the other (or outward, for 'EXT') by the FULL `offset`, so a
    single override with offset = half your frame thickness gives two
    panels a total overlap equal to the full thickness. A NEGATIVE
    offset does the reverse (both pull apart), which is a route to a
    real gap between two fixed-width children -- but note that a
    FIXED (non-fr/auto) child track ignores given_w entirely, so only
    the side whose ORIGIN moves visibly shifts; see the
    LayoutBorderOverride docstring for the worked example and its
    asymmetry caveat. The interior border segment between two
    independently-offset spaces (the BOTH-hosting-a-child case) now
    DUPLICATES into each space's own edge once they diverge -- see
    DUPLICATE INTERIOR SEGMENTS below.
  - RING (`between = [label, '*']`, e.g. `['m1', '*']`): ALWAYS
    independent, no matter what's actually adjacent on each chosen
    side -- EXT, a plain sibling, or a sibling that itself hosts a
    child. Only the anchor space (`label`) moves -- its own Cells
    shape and, if it has one, its child's given rectangle -- exactly
    like the EXT case above, just without requiring the other side to
    specifically BE 'EXT'. The sibling on the other side of the
    border, if any, is NEVER touched -- no track resize, no shape
    change -- so `['m1', '*']` with a negative offset shrinks m1 in
    from every side it has (including the one it shares with m2) while
    m2 stays exactly as sized. This is what makes ring simpler than a
    pair to resolve: there's no "which mechanism does the other side
    need" question, so no adjacency lookup either. `_apply_shared_offsets`
    never touches ring entries (its `b` is always None, so the
    plain-cell/child-hosting lookup naturally finds nothing and skips
    it) -- see `_dumb_offset_for_space`'s ring branch for the actual
    per-side deltas.
  - EXT RING (`between = ['EXT', '*']` or `['*', 'EXT']` -- order
    doesn't matter, `_parse_between` isn't picky about which slot the
    '*' sits in): unlike every other ring, 'EXT' isn't a real space to
    anchor to -- this instead applies to EVERY space in the node that
    touches the grid's own perimeter, each shifted independently, same
    mechanism as the EXT-PAIR case above just run once per matching
    space instead of once for a single named one (`_dumb_offset_for_space`
    checks `a == 'EXT'` before the literal label match, so no space
    literally needs to be labelled 'EXT' -- nothing ever is). A side
    filter narrows to spaces touching THAT side specifically (checked
    per space via `_space_touches_side`); unfiltered, each space moves
    on every perimeter side it individually has (`_perimeter_sides`).
    A space that doesn't touch the requested side at all is silently
    skipped, no warning -- that's the ordinary case for most spaces in
    a multi-cell grid, not a mistake. This is the one-override way to
    push out (or pull in) an entire outer edge of cells at once --
    `['EXT', '*', 'L,R']` grows every cell touching the grid's own
    left or right edge outward on that side, without having to list
    every outer cell's label by hand.
DUPLICATE INTERIOR SEGMENTS -- a PERIMETER segment moves WITH its one
touching space (see above) -- both its POSITION (which grid edge) and
its LENGTH along that edge, via `_own_side_of_interior`, so a space
offset on its PERPENDICULAR sides too (e.g. an unfiltered ring
shrinking every side) gets a correspondingly shorter/longer perimeter
run, not one that's merely shifted sideways while staying its
original, now-mismatched length. An INTERIOR segment sits between TWO
spaces, and an independent
offset (both-children pair, or a ring against a real sibling) can move
either or both of them without moving the other. Freezing the segment
at its pre-offset position would then match NEITHER cell any more.
Instead, once EITHER touching space has moved (has an entry in
`space_deltas`), that ONE original segment is replaced by ONE PER
DIVERGED SPACE, each drawn along THAT space's own actual edge --
exactly matching what Cells already draws for it -- via
`_own_side_of_interior`. Both still report the SAME [label0, label1]
Topology pair (there are just two of them now, not a relabelling) --
so a selector querying `Borders=[label0, label1]` on a diverged pair
now gets 2 results instead of 1. If BOTH spaces moved (independently,
via two SEPARATE ring overrides -- a pair's own two sides always move
in mirrored lockstep, see below) their new edges can be anywhere
relative to each other: overlapping (both grew toward each other),
gapped (both shrank apart), or one of each. If neither space actually
moved on ITS OWN side of this SPECIFIC boundary (space_deltas has no
entry for either, or its relevant delta component happens to be
exactly 0), the two recomputed edges come out IDENTICAL and only ONE
segment is emitted -- the ordinary, overwhelmingly common case is
completely unaffected. A SHARED (track-resize) boundary never reaches
this at all -- it never touches `space_deltas`, the two tracks already
agree by construction, before `_emit` even starts walking. For a non-
rectangular merge, `_own_side_of_interior`'s own bbox-edge check
(built to find WHICH of a space's 2 relevant edges this boundary's own
LINE POSITION sits on) can genuinely find NEITHER -- this interior
boundary is against a real SIBLING, not the space's own true bbox edge
in that direction at all (e.g. the s1/k/s2 worked example in
`test_border_overrides.py`, an EXT-restricted delta on a different
part of the same merge). When that happens, the LINE POSITION simply
stays put -- this space has no legitimate claim on a position it was
never really at -- but the RANGE (perpendicular) trim STILL applies
unconditionally regardless, exactly as it always has: an earlier
version of this fix zeroed the delta's components entirely in that
case, which also wrongly suppressed a LEGITIMATE range trim for the
ordinary rectangular case (a plain corner cell with an unfiltered EXT
offset touching two sides at once, say) -- see `_own_side_of_interior`
's own docstring for the corrected, narrower fix. Note a
both-children PAIR's own mirrored-move formula means its two edges
only ever move symmetrically about the original centre (so the
"duplicate" segments are the overlap/gap's own two boundaries) --
whereas TWO SEPARATE ring overrides on the same pair (one per
label, via a label list or two authored overrides) can move each side
independently, by different amounts, in either direction, same as any
other ring.
LABEL LISTS -- either label side of a PAIR, or a RING's anchor, may
itself be a comma-separated list ('m1,m2') instead of one label --
`_split_labels`/`_node_overrides` expand it into one entry per label
(a full cross product when BOTH pair sides are lists) BEFORE the pair/
ring mechanisms above ever run, so `_apply_shared_offsets` and
`_dumb_offset_for_space` each only ever see already-expanded, single-
label entries. `['m1,m2', '*']` (no brackets -- unlike the old wall-
override system's `['[m1,m2]', '*']`, a between item here is already
its own list slot) becomes two independent ring overrides, one per
label -- both m1 and m2 shrink/grow on every side they each have,
including the one they share with each other, neither aware the other
moved too.
An optional 3rd `between` item -- Top/Bottom/Left/Right (or short T/B/
L/R), case-insensitive, mapped onto this module's own N/S/E/W (row 0 =
North, column 0 = West) -- NARROWS an 'EXT' or ring match to just that
one side. SEVERAL sides can be named at once, same bare-comma
vocabulary as a label list -- 'Top,Left' or 'T,L' (no brackets) --
narrowing to exactly that subset instead of one side or all of them;
any unrecognized token in the list drops the WHOLE filter (warned,
falls back to unfiltered) rather than applying a partial match.
Without a filter at all (blank, or '*'), EVERY side the matched space
has moves at once: for 'EXT' that means every side actually touching
the grid's own edge (_perimeter_sides) -- a single cell filling its
whole grid (a window's glass pane against its frame) insets on all 4
sides from ONE override; a plain corner gets both of its touching
sides. For a RING, it's simpler still: every one of the space's 4
sides, full stop -- there's no grid-edge check to make, since ring
doesn't care whether a side faces EXT or a sibling. This matches the
old wall-override system's own "unfiltered ring = every wall touching
this space" default -- there's no "ambiguous, add a filter" failure
mode any more, only an explicit filter narrows anything down. No indexed
form ('T0', 'Top1') -- not needed yet, since every match here (a
single space, EXT or ring) only ever has at most one segment per
side.

TOPOLOGY -- a GRAFTED version of Borders: border k within some Borders
branch B (0-based, same order _borders() returned it in) gets its OWN
branch, B.AppendElement(k), holding exactly 2 items -- the label of
every space that border touches. An interior wall touches 2 spaces
(both its labels); a perimeter run touches 1, paired with the literal
string 'EXT' (the edge of THIS node's own grid -- not necessarily the
true building exterior, since a node's own borders never look past its
own parent/child boundary; a nested node's own perimeter is 'EXT' from
ITS point of view even though it's actually an interior wall one level
up). The root's own 4 sides at Depth 0 are the one case with no real
grid to read a space index from, so all 4 report the same pair: the
root's own label (or '' if it has none) and 'EXT'. Because Topology is
grafted one level DEEPER than Borders, Depth's usual path-length rule
needs +1 to land on the matching slice -- run() does this once, calling
_filter_by_depth(topology_tree, depth + 1) rather than depth (this also
means Topology's raw branch addresses at Depth N happen to coincide
with Cells/Borders/Labels' addresses at Depth N+1 -- harmless, since
they're different output trees, but worth knowing if you ever compare
raw branch paths ACROSS outputs instead of using each output's own
Depth-filtered result).

The PERIMETER itself is no longer always 4 whole-edge lines: each side
is walked cell-by-cell and split into runs the exact same way interior
lines already were -- adjacent cells sharing a label merge into one
run, a label change breaks it (this naturally agrees with CELLS'
merging now that both are back to comparing the same raw labels). Want
one continuous edge across several different rooms anyway? Wrap them in
an intermediate child container -- the parent then only ever sees that
one wrapper cell, so its own line (interior or perimeter) comes out
as a single run; the real subdivision becomes the child's own private
concern, one level deeper, per the "a node's _borders() never looks
across a parent/child boundary" rule that already held before this.

WALL LAYOUTS -- a border override (see BORDER OVERRIDES above) may
carry a 'wallLayout' document: a nested Layout JSON, same schema as
any other Layout, describing that border's own UPRIGHT elevation --
studs, openings, panels -- authored the same way any floor-plan grid
is. Rides ALONGSIDE the flat 2D border line this component already
draws for the floor plan's own topology -- doesn't replace it. Created
FRESH the moment an override carries one; there's no separate "wall
cell" sitting in some grid beforehand waiting for a plane. Structurally
a child of the BORDER, not of either space it sits between (a wall is
a relationship between two spaces, owned by neither) -- but its OWN
output still splits into Cells/Labels (its own frame/door/header
cells) and Borders/Topology (its own internal subdivisions) exactly
like any other node's does, at path.AppendElement(k) for an ordinary,
un-reserved counter k (see _node_wall_layouts / _emit's own WALL
LAYOUTS block) -- NO disjoint-numbering scheme (no negative indices,
no offset ranges): it may share a branch address with some CELL's own
child at the same node, and that's fine, since label-based selectors
(Cells=['w'], say) already disambiguate by content, not by branch
position, the same way they always have.

Meaningful for a PAIR (a real space, or 'EXT', on each side -- the
same mode Offset's own EXT/both-hosting-a-child mechanics already use)
OR a RING (a single real anchor, or 'EXT' itself as the anchor,
against '*') -- only GLOBAL (['*','*']) still has no border-owning-
child concept to hang a wall layout on (warned, skipped -- see
_node_wall_layouts; there's no single anchor, and "every border in the
node" is a much bigger default than anyone's asked for yet). Both PAIR
and RING can already match MORE than one boundary without any special
handling: a PAIR matches via ordinary same-BASE-label equivalence
(Between=['m','m'] hits every m[i]-vs-m[j] interior boundary, one wall
each -- useful for "every module-to-module party wall," no ring
needed when the boundary is always between two of the SAME base
label), while a RING matches every border touching its one anchor
regardless of the OTHER side's label (Between=['a','*'] walls every
border touching space 'a', whatever's across it; Between=['EXT','*']
walls the WHOLE perimeter of the node, useful one level up where the
children don't all share one base label to pair against each other).
The optional 3rd Between item (Top/Bottom/Left/Right or T/B/L/R, same
vocabulary as Offset's own side filter) narrows WHICH of a multi-match
entry's boundaries actually get a wall -- checked against that
specific boundary's own edge relative to the reference space (a PAIR's
Between[0], a RING's anchor, or whichever side isn't 'EXT' when there
is no other candidate), the SAME `edge` value _wall_plane_axes already
computes for the plane itself (see _space_edge_at) -- so
['m','EXT','T,B'] places a wall on each module's own North/South EXT
edge but correctly skips an END module's West/East EXT edge, and
['EXT','*','T,B'] does the same one level up without needing to name
every child. An unfiltered multi-match entry places a wall on EVERY
boundary it matches, no exceptions. CellWidths on the wallLayout
document MUST be
exactly ['auto'] -- a placeholder, ENFORCED both by
LayoutBorderOverride at authoring time and defensively again here --
this component overwrites it with the matched border's own actual
length (post-Offset) before recursing; the width was never the
author's to set. CellLengths is authored NORMALLY -- the wall's real
HEIGHT, since nothing about a floor plan carries that information.

The wall's own PLANE is computed automatically, never authored --
attaching a wallLayout at all is already the signal it needs to stand
upright. X-axis along the matched border's own direction, Y-axis the
PARENT's own up (its XAxis cross YAxis -- world Z in the common
unwired-Geom.Plane case, but correctly follows the parent's own
orientation if the whole tree has been rotated), origin/direction
derived from Between[0]'s own edge specifically -- its FIRST corner in
that space's own CCW polygon traversal (_rect_curve's fixed point
order) is the origin, its SECOND is the direction target (see
_wall_plane_axes / _space_edge_at). This isn't arbitrary: combined
with that Y-axis, it ALWAYS produces an outward-pointing plane normal
(X cross Y) -- verified for all 4 possible edges -- pointing AWAY from
Between[0]'s own space, exactly like a Rhino box's own faces point
away from its volume, and matching PMS-R7's own existing, documented
wall convention (pms-generate-assemblies.py's _wall_geom: "this normal
points OUT of the plan, hence their stacks grow outward from the cell
face").

PHASE 1 LIMITATION -- a DIVERGED interior boundary (see DUPLICATE
INTERIOR SEGMENTS above -- an independent offset moved one or both
touching spaces apart) currently WARNS AND SKIPS wall-layout placement
entirely, rather than guessing at the geometry. The eventual plan
(not yet built): emit the wall layout's own cells TWICE for a diverged
boundary -- once per side, same authored content/coordinates (so a
door lands at the same physical spot either way) but through two
DIFFERENT planes, each independently satisfying the outward-normal
rule for its own respective space -- so each instance's own winding,
once baked into GH geometry, tells a downstream extrusion step which
way to build outward with zero Topology cross-referencing needed. A
non-diverged boundary (nothing offset it, or offset moved it without
splitting it -- see the PERIMETER-vs-INTERIOR distinction there) is
entirely unaffected by this limitation; only genuinely split
boundaries hit it.

SELECTORS -- two OPTIONAL inputs, both applied AFTER Depth and AFTER
borderOverrides, to all FOUR outputs at once -- filtering which
already-solved Cells/Labels/Borders/Topology entries actually reach the
component, without changing how anything solved. Unwired means "no
filtering" for that selector, same as not having it at all. Labels
stays in lockstep with Cells (same kept indices), and Topology stays in
lockstep with Borders (each surviving border's own topology entry moves
to its NEW index in the filtered Borders list) -- see
_filtered_cells_and_labels / _filtered_borders_and_topology.

  Cells input: a list of labels. A Cells-tree item is kept if its OWN
  label -- OR that label's BASE (suffix stripped, '[k]') -- is in the
  list. So ['mod'] keeps every 'mod[0]', 'mod[1]', ... instance; an
  explicit ['mod[0]'] keeps only that one. Any item may ALSO be a
  comma-separated LIST of labels ('a,b', no brackets -- same
  _split_labels grammar borderOverrides' own label lists use) to match
  several at once with one entry. (See _matches_label / _split_labels.)

  Borders input: the SAME grammar as borderOverrides' own `Between` --
  [a, b] (pair, order-insensitive, base-label match on each side --
  either side may ALSO be a comma-separated label list, expanded the
  same way as Cells above), [label, '*'] (ring -- every border
  touching that label, either side), ['*', '*'] (global -- every
  border). 'EXT' works as a literal label value on either side,
  matching a perimeter run the same way Topology already reports it --
  so ['EXT', '*'] (ring form) is the whole perimeter, regardless of
  which space each run belongs to. 'INT' is the mirror-image literal,
  usable the SAME ring way -- ['INT', '*'] -- meaning every INTERIOR
  border (an interior wall touches two real spaces, NEITHER labelled
  'EXT'): the way to select "everything except the perimeter" without
  naming every interior space explicitly. Unlike EXT, INT never appears
  as an actual Topology label -- it's a keyword recognised only in this
  one ring position (_border_matches special-cases mode=='ring' and
  a=='INT' to mean "'EXT' not in pair" before falling through to
  ordinary label matching), so ['INT', 'INT'] or 'INT' as one side of
  an ordinary pair do NOT get this treatment, they'd just look for a
  literal (non-existent) 'INT' label like any other pair/ring anchor.

  A third item (Top/Bottom/Left/Right or T/B/L/R, comma-separated for
  several at once -- same grammar and same bare-comma vocabulary as
  borderOverrides' own side filter) NARROWS the match to a specific
  grid edge, and now actually DOES something (previously parsed but
  ignored): a segment's own N/S/E/W is computed once at solve time,
  in _emit, from the node's own LOCAL grid coordinates (correct even
  under an arbitrarily rotated Geom.Plane, and unaffected by any
  borderOverrides shift already applied to that segment's drawn
  position) -- see _filtered_borders_and_topology. Side filtering only
  ever narrows a match that CAN land on a perimeter run to begin with:
  an EXT-anchored pair/ring, or a ring on a real label. Two cases where
  a side filter has no useful meaning are handled explicitly rather
  than silently returning nothing: combined with 'INT' (an interior
  segment never touches just one grid edge) it's dropped with a
  warning; combined with a PLAIN pair of two real spaces (neither EXT
  -- the shared/independent-both-children Offset mechanisms' own
  territory, which never references side either) it's simply BYPASSED,
  matching regardless of side, mirroring borderOverrides' own
  precedent exactly. (See _parse_between / _border_matches /
  _filtered_borders_and_topology.)

Pins --
  Inputs:  JSON (list), Plane, Depth, Cells (list), Borders (list)
  Outputs: Cells, Labels, Borders, Topology

v0 prototype -- not wired into the component build pipeline (no
.doc.md yet). Paste into a GHPython component and set up the pins
above -- see pms-layout-geom-v0.spec.json for the exact pin config.

Component v1.4.7 -- fixed a follow-on bug from v1.4.3's non-
rectangular RESTRICTED-edge fix: that fix only ever reached the CELLS
outline (_shift_outline_edges); the separate BORDERS/interior-segment
code (_own_side_of_interior) never learned about `restricted` at all,
so an EXT-flavoured delta could still wrongly drag a non-rectangular
space's INTERIOR boundary against a real sibling -- its own bbox-edge
check, built only for the rectangular case, has no way to recognize a
boundary that isn't on EITHER of the space's 2 bbox edges for that
axis, and silently defaulted to treating it as one anyway. This made
an untouched interior boundary look diverged and get needlessly
DUPLICATED, at the wrong position besides. FIRST fix attempt (briefly
in v1.4.6, since corrected) zeroed a space's entire RESTRICTED delta
before it reached _own_side_of_interior at all -- too blunt, since it
ALSO suppressed legitimate perpendicular length-trimming for the
ordinary RECTANGULAR case (no merge involved), a live regression a
user caught immediately ("borders are not trimmed when making
offsets"). Corrected: _own_side_of_interior itself now explicitly
handles the case where NEITHER of a space's 2 relevant bbox edges
matches an interior boundary's own line position (only possible for a
non-rectangular merge) -- the LINE POSITION then simply stays put, but
the RANGE (perpendicular) trim still applies unconditionally, exactly
as it always did. See that function's own docstring and the s1/k/s2 +
plain-corner-cell worked examples in test_border_overrides.py.

Component v1.4.5 -- wall layouts now accept a RING match (['a','*'],
or 'EXT' itself as the anchor for the whole perimeter), not just a
PAIR -- needed one level up from a repeated-label pair (Between=
['m','m']): where the children don't all share one base label to pair
against each other, a ring is the only way to say "every border
touching this one anchor" or "every border in this node" without
naming each child. Reuses _border_matches (already built for the
Borders selector, ring-EXT included) for matching, and the same side-
filter mechanism from v1.4.4. Only GLOBAL is still unsupported.

Component v1.4.4 -- fixed a wall-layout side filter that was silently
IGNORED (the wall-matching loop discarded it, `_wside`): the optional
3rd Between item on a wallLayout-carrying override now actually
narrows which boundary(ies) get a wall, reusing the `edge` value
already computed for the plane itself (_space_edge_at) -- matters
most for a same-base-label pair (['m','m'], already multi-matching
every m-to-m boundary via the SAME base-label equivalence every other
Between already uses) or an 'EXT' pair on a space touching the grid's
edge on more than one side -- previously EVERY matching boundary got
a wall regardless of the filter.

Component v1.4.3 -- fixed a follow-on bug from v1.4.2: an EXT-
flavoured offset (EXT pair or EXT ring) on a non-rectangular merge
was shifting EVERY edge in the requested direction, including ones
that were really facing a SIBLING space rather than the grid's own
perimeter (same S/E/N/W tag, different thing behind it) -- opening a
gap between the offset space and its untouched neighbour. Now only
edges that are ACTUALLY against the grid's own edge move under an
EXT match; a plain RING still moves every matching-direction edge
regardless of what's beyond it, unchanged -- see
_dumb_offset_for_space's `restricted` and _shift_outline_edges'
own docstring for the s1/k/s2 worked example this was found on.

Component v1.4.2 -- an INDEPENDENT border offset (ring, EXT pair, EXT
ring, or both-children pair) applied to a non-rectangular merge (an L
/ T / U-shaped space) used to warn and freeze at the un-offset
outline -- now shifts the traced outline for real, edge by edge, on
just the requested side(s) -- see _shift_outline_edges and the
CELLS section's own note on this above.

Component v1.4.1 -- fixed a silent no-op: a ring anchored at 'EXT'
(['EXT','*'] or ['*','EXT']) used to match nothing at all (no real
space is ever labelled 'EXT') and now correctly offsets every space
touching the grid's own perimeter, independently, on the requested
side(s) -- see BORDER OVERRIDES' new EXT RING bullet below.

Component v1.4.0 -- this replaces the old two-component split (a plain
Geom + an ADVANCED-SELECTION Geom 2 sibling that duplicated its whole
solve): ALL of it now lives in one component, always outputting the
full Cells/Labels/Borders/Topology set, with the two selectors as
purely optional narrowing on top -- unwired, it behaves exactly like
the old plain Geom did.
"""

import json

try:
    import Grasshopper as gh
    _HAS_GH = True
except ImportError:
    gh = None
    _HAS_GH = False

try:
    import Rhino.Geometry as rg
    _HAS_RHINO = True
except ImportError:
    rg = None
    _HAS_RHINO = False

try:
    string_types = (str, unicode)  # noqa: F821 (py2 / IronPython 2)
except NameError:
    string_types = (str,)

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict


# -----------------------------------------------------------------
# Goo / JSON plumbing.
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
    return True


def _plane_from_dict(d):
    """rg.Plane from a Layout JSON's own 'plane' field (baked in by
    Boundary on the outermost instance) -- {origin, xAxis, yAxis},
    each [x, y, z]. None if missing or malformed (WorldXY is the
    caller's fallback, not this function's job)."""
    if not isinstance(d, dict):
        return None
    try:
        o = d.get("origin") or [0.0, 0.0, 0.0]
        x = d.get("xAxis") or [1.0, 0.0, 0.0]
        y = d.get("yAxis") or [0.0, 1.0, 0.0]
        plane = rg.Plane(
            rg.Point3d(float(o[0]), float(o[1]), float(o[2])),
            rg.Vector3d(float(x[0]), float(x[1]), float(x[2])),
            rg.Vector3d(float(y[0]), float(y[1]), float(y[2])),
        )
    except (TypeError, ValueError, IndexError):
        return None
    return plane if plane.IsValid else None


def _base_label(label):
    """Strip a trailing '[k]' do-not-merge suffix: 'A1[0]' -> 'A1'.
    Cells merge / border on the FULL label; children bind on the base."""
    if not isinstance(label, string_types):
        return label
    i = label.rfind("[")
    if i > 0 and label.endswith("]"):
        return label[:i]
    return label


# -----------------------------------------------------------------
# BORDER OVERRIDES -- matching (shared with the Borders SELECTOR input
# further below, which reuses _matches_label and _parse_between
# defined here rather than its own) and the two solve-time mechanisms.
# See the module docstring's BORDER OVERRIDES section.
# -----------------------------------------------------------------

def _matches_label(label, wanted):
    """label matches an entry in `wanted` if either the FULL label or
    its BASE (suffix stripped) is in the list -- 'mod' matches every
    'mod[k]' instance, an explicit 'mod[0]' matches just that one."""
    if not isinstance(label, string_types):
        return False
    return label in wanted or _base_label(label) in wanted


SIDE_CODES = {
    "t": "N", "top": "N",
    "b": "S", "bottom": "S",
    "l": "W", "left": "W",
    "r": "E", "right": "E",
}


def _parse_between(items, warnings):
    """items: the raw 'between' list from a border-override document,
    OR from the Borders selector input further below (same grammar).
    Returns (mode, a, b, side) -- 'pair' (a, b both real labels),
    'ring' (a is the anchor, b is None), 'global' (a, b both None) --
    or None (unusable, warned). `side` is None (unfiltered -- every
    side the matched space has, see _dumb_offset_for_space) or a SET
    of 1+ of 'N'/'S'/'E'/'W', from an optional 3rd item --
    Top/Bottom/Left/Right or short T/B/L/R, case-insensitive, matching
    the old wall-override component's own naming (mapped onto this
    system's own N/S/E/W vocabulary -- row 0 = North, column 0 = West,
    same as CellLabels). SEVERAL sides narrow to exactly that subset --
    comma-separated, 'Top,Left' or 'T,L' -- same bare-comma vocabulary
    as a label list (_split_labels), no brackets needed. Any
    unrecognized token in the list drops the WHOLE filter (warned,
    falls back to unfiltered) rather than silently applying a partial
    match. '*' (or leaving the 3rd item blank/unwired) also means "no
    particular side" -- same as omitting it entirely, deliberately, no
    warning. No indexed form ('T0', 'Top1', for picking one of SEVERAL
    segments on the same side) -- not needed yet, since every match
    this component makes (a single space, or 'EXT') only
    ever has at most one segment per side to begin with."""
    if not items:
        return None
    side = None
    if len(items) > 2:
        raw_side = items[2]
        raw = raw_side.strip() if isinstance(raw_side, string_types) else ""
        if raw in ("", "*"):
            side = None    # explicit wildcard/blank -- not an error
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
                    "them (no brackets needed), or '*' for any -- "
                    "ignored.".format(raw_side))
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


def _parse_override(od, warnings):
    """od: one already-parsed dict from node['borderOverrides'].
    Returns (mode, a, b, side, offset) or None (unusable, warned by
    _parse_between)."""
    between = od.get("between")
    parsed = _parse_between(between if isinstance(between, list) else [],
                             warnings)
    if parsed is None:
        return None
    mode, a, b, side = parsed
    offset = od.get("offset")
    try:
        offset = float(offset) if offset is not None else None
    except (TypeError, ValueError):
        warnings.append(
            "borderOverrides: offset {!r} isn't a number -- ignored."
            .format(offset))
        offset = None
    return (mode, a, b, side, offset)


def _split_labels(ref):
    """A between item can itself be a comma-separated LIST of labels
    ('m1,m2') -- the override expands to one entry per label (a full
    cross product when both sides of a pair are lists), matching the
    old wall-override system's own label-list vocabulary -- just
    without needing to bracket it ('[m1,m2]'): a between item is
    already its own list element here, so the brackets that grammar
    used to mark "this one slot is actually several" would be pure
    noise. '*' and 'EXT' are never split, even if a comma sneaks into
    one by mistake -- they're keywords, not label lists."""
    if not isinstance(ref, string_types) or ref in ("*", "EXT") or "," not in ref:
        return [ref]
    labs = [t.strip() for t in ref.split(",") if t.strip()]
    return labs if labs else [ref]


def _node_overrides(node, warnings):
    """Offset acts on a PAIR (see _apply_shared_offsets /
    _dumb_offset_for_space -- shared or independent depending on what's
    on each side) or a RING (always independent -- see
    _dumb_offset_for_space's ring branch: the anchor space's own
    geometry moves on the chosen side(s), regardless of what's actually
    adjacent there -- EXT or a specific sibling, plain or child-
    hosting -- which is never itself touched). GLOBAL has no effect --
    there's no single space to anchor the shift to -- warned here once,
    rather than silently doing nothing, so an override doesn't look
    like it's being ignored by accident. Either label side of a PAIR,
    or a RING's anchor, may itself be a comma-separated list
    (_split_labels) -- expanded into one (mode, a, b, side, offset)
    entry per label (per combination, for a pair) BEFORE the pair/ring
    mechanisms ever see it, so _apply_shared_offsets and
    _dumb_offset_for_space each just handle plain single-label entries
    as always, unaware any expansion happened."""
    out = []
    for od in (node.get("borderOverrides") or []):
        if not isinstance(od, dict):
            continue
        parsed = _parse_override(od, warnings)
        if parsed is None:
            continue
        mode, a, b, side, offset = parsed
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


def _node_wall_layouts(node, warnings):
    """PAIR and RING overrides that carry a 'wallLayout' document --
    see the module docstring's WALL LAYOUTS section. Returns a list of
    (mode, a, b, side, wall_layout) tuples -- GLOBAL still has no
    border-owning-child concept to hang a wall layout on (warned,
    skipped; there's no single anchor, and "every border in the node"
    is a much bigger, unasked-for default). Either label side (or a
    RING's anchor) may itself be a comma-separated list, expanded via
    _split_labels -- same grammar _node_overrides already uses for
    Offset, just for a different field on the same override document.
    Note a PAIR already matches MORE THAN ONE boundary when both sides
    share a base label ('m','m' matches every m[i]-vs-m[j] interior
    boundary via base-label equivalence, same as any other pair) --
    RING goes further, matching every border touching ONE anchor
    regardless of the OTHER side's label (a real space, OR 'EXT' as
    the anchor itself, meaning every perimeter border in the node --
    see _border_matches, which already treats 'EXT' as ordinary
    matchable topology content, no special-casing needed here). Either
    way, `side` (an optional 3rd Between item, Top/Bottom/Left/Right
    or T/B/L/R) is used by _emit's wall-matching block (see the `edge`
    value there, from _space_edge_at) to narrow WHICH of a multi-match
    entry's boundaries actually get a wall, exactly like it already
    narrows a ring/EXT match for Offset."""
    out = []
    for od in (node.get("borderOverrides") or []):
        if not isinstance(od, dict):
            continue
        wall_layout = od.get("wallLayout")
        if not isinstance(wall_layout, dict):
            continue
        if wall_layout.get("cellWidths") != ["auto"]:
            warnings.append(
                "wallLayout: CellWidths must be exactly ['auto'] -- "
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
                out.append((mode, aa, None, side, wall_layout))
        else:
            for aa in _split_labels(a):
                for bb in _split_labels(b):
                    out.append((mode, aa, bb, side, wall_layout))
    return out


def _find_space(spaces, label):
    """First space whose full/base label matches `label` -- None for
    'EXT' / '*' (not an actual space) or no match."""
    if label in ("EXT", "*"):
        return None
    for sp in spaces:
        if _matches_label(sp["label"], [label]):
            return sp
    return None


def _find_track_boundary(sp_a, sp_b):
    """Two spaces that are each exactly one track wide/tall along the
    shared axis, sitting directly next to each other. Returns
    ('col'|'row', idx, sp_a_is_before) -- idx is the track index of
    whichever space sits AFTER the boundary (idx - 1 is the 'before'
    track). None if they don't meet this simple shape (a wider span,
    or not actually adjacent this way) -- the only shape this v0
    supports; anything else is skipped by the caller, with a warning."""
    if sp_a["r0"] == sp_a["r1"] == sp_b["r0"] == sp_b["r1"]:
        if sp_a["c1"] + 1 == sp_b["c0"]:
            return ("col", sp_b["c0"], True)
        if sp_b["c1"] + 1 == sp_a["c0"]:
            return ("col", sp_a["c0"], False)
    if sp_a["c0"] == sp_a["c1"] == sp_b["c0"] == sp_b["c1"]:
        if sp_a["r1"] + 1 == sp_b["r0"]:
            return ("row", sp_b["r0"], True)
        if sp_b["r1"] + 1 == sp_a["r0"]:
            return ("row", sp_a["r0"], False)
    return None


def _apply_shared_offsets(spaces, children_by_label, col_starts, col_sizes,
                           row_starts, row_sizes, overrides, name, warnings):
    """PAIR overrides with a real Offset, where AT LEAST ONE matched
    space is a plain leaf (no bound child): the ONE shared track
    boundary between them shifts by Offset mm (positive = toward
    Between[1]'s side) -- one track grows, its neighbour shrinks by
    the same amount, so the total is unchanged. If the OTHER side
    hosts a child, nothing extra needs to happen here: that child's
    own given rectangle is computed from these SAME (now-shifted)
    col_sizes/row_sizes later in _emit, so it just inherits the new
    size -- see the module docstring. Mutates col_sizes/row_sizes IN
    PLACE, then recomputes starts (a pure prefix sum) to match.

    A pair where BOTH sides host a child is the OTHER mechanism
    (independent, non-rippling -- see _dumb_offset_for_space in
    _emit) and is deliberately skipped here. `overrides` may also
    hold RING entries (always independent, never a shared-track
    resize) -- a ring's `b` is None, so _find_space(spaces, None)
    naturally returns None and it's skipped below like any other
    non-pair case; global entries never reach here at all
    (_node_overrides already dropped them, Offset can't act on
    them)."""
    touched = False
    for (_mode, a, b, _side, offset) in overrides:
        if offset is None:
            continue
        sp_a, sp_b = _find_space(spaces, a), _find_space(spaces, b)
        if sp_a is None or sp_b is None:
            continue    # EXT/ring/no matching space -- not this case
        a_has_child = _child_for_space(children_by_label, sp_a["label"]) is not None
        b_has_child = _child_for_space(children_by_label, sp_b["label"]) is not None
        if a_has_child and b_has_child:
            continue    # both host children -- the independent mechanism instead
        rel = _find_track_boundary(sp_a, sp_b)
        if rel is None:
            warnings.append(
                "{}: border override {!r} doesn't sit between two "
                "simple, single-track-wide/tall adjacent cells -- "
                "Offset skipped.".format(name, [a, b]))
            continue
        axis, idx, a_is_before = rel
        # a_is_before: a (Between[0]) is the lower-index ('before')
        # track. Positive Offset moves toward Between[1] (=b): if a is
        # before, that's toward the higher index, so 'before' grows
        # and 'after' shrinks; if a is after, it's the reverse.
        delta = offset if a_is_before else -offset
        sizes = col_sizes if axis == "col" else row_sizes
        lo, hi = idx - 1, idx
        new_lo, new_hi = sizes[lo] + delta, sizes[hi] - delta
        if new_lo < 0 or new_hi < 0:
            warnings.append(
                "{}: border override {!r} Offset {} would push a "
                "track negative -- skipped.".format(name, [a, b], offset))
            continue
        sizes[lo], sizes[hi] = new_lo, new_hi
        touched = True

    if touched:
        def _restart(starts, sizes):
            acc = 0.0
            for i, s in enumerate(sizes):
                starts[i] = acc
                acc += s
        _restart(col_starts, col_sizes)
        _restart(row_starts, row_sizes)


def _perimeter_sides(sp, ncols, nrows):
    """Every side of sp that touches the grid's own edge -- 0 to 4 of
    them: a plain interior cell has none; a true corner has two; a
    single cell filling the whole grid (a window's glass pane against
    its frame, say) has all four. No side filter given (blank or '*',
    see _parse_between) means "every one of these" -- matching the old
    wall-override system's own "unfiltered ring = every wall touching
    this space" default, just applied per-side instead of per-wall."""
    sides = []
    if sp["c0"] == 0:
        sides.append("W")
    if sp["c1"] == ncols - 1:
        sides.append("E")
    if sp["r0"] == 0:
        sides.append("N")
    if sp["r1"] == nrows - 1:
        sides.append("S")
    return sides


def _space_touches_side(sp, side, ncols, nrows):
    if side == "W":
        return sp["c0"] == 0
    if side == "E":
        return sp["c1"] == ncols - 1
    if side == "N":
        return sp["r0"] == 0
    if side == "S":
        return sp["r1"] == nrows - 1
    return False


def _dumb_offset_for_space(sp, spaces, children_by_label, overrides,
                            ncols, nrows, name, warnings):
    """Returns (dx0, dy0, dx1, dy1, restricted) -- deltas to ADD to
    sp's own rect (from rect_of), never touching the parent's own
    track sizes: one non-zero delta per side that matches an
    INDEPENDENT (non-rippling) override, for BOTH consumers in _emit
    -- sp's own drawn cell shape in Cells (applied to every space,
    whether or not it has a bound child) AND, if it has one, the
    CHILD's own given frame (the two are the same delta; a hosted
    child just inherits it). `restricted` is a set of S/E/N/W
    directions that came from an EXT-flavoured match (an EXT pair or
    an EXT ring, NOT a plain ring against a real anchor) -- for a
    RECTANGULAR space this is irrelevant (there's only ever one edge
    per direction), but for a NON-rectangular merge it tells
    _shift_outline_edges to only move that direction's edges that are
    ACTUALLY against the grid's own perimeter, leaving any edge in the
    same direction that's really facing a sibling space untouched --
    see the module docstring's BORDER OVERRIDES section and
    _shift_outline_edges' own docstring for the s1/k/s2-shaped worked
    example this exists for. A plain ring keeps its own documented
    'doesn't care what's beyond' behaviour -- its directions are
    never added to `restricted` (and are removed from it if some
    OTHER override on this same space already had) --
      - sp <-> EXT: extends outward, Offset applied in full, on EVERY
        side sp touches the grid's own edge on, regardless of whether
        sp has a bound child. An explicit side filter (Top/Bottom/
        Left/Right or T/B/L/R, see _parse_between) narrows this to
        just that one side -- warned and skipped if sp doesn't
        actually touch it. No filter (blank or '*'): every touching
        side moves -- a single cell filling its whole grid (a glass
        pane against its frame) gets all four; a plain corner gets
        two; there's no "ambiguous, add a filter" case any more, only
        an explicit filter narrows anything down.
      - sp <-> another space that ALSO hosts a bound child: each side
        independently extends toward the other by the FULL Offset (not
        split) -- a single override handles both children, since this
        function runs once per space and finds the SAME override from
        each side's own point of view. Requires sp ITSELF to have a
        bound child too -- a plain sp paired with a child-hosting
        space is the SHARED mechanism's territory instead
        (_apply_shared_offsets, already applied inside _resolve_node);
        skipped here to avoid double-applying the same override.
    Only handles simple, single-track-wide/tall adjacency (see
    _find_track_boundary) -- anything else is silently skipped (no
    warning here; _apply_shared_offsets already warned once per
    override for the shapes it can't handle, no need to double up).
    `overrides` may hold PAIR entries (handled below) or RING entries
    (handled first, see that branch) -- global never reaches here
    (_node_overrides already dropped it)."""
    dx0 = dy0 = dx1 = dy1 = 0.0
    restricted = set()
    my_label = sp["label"]
    sp_has_child = _child_for_space(children_by_label, my_label) is not None
    for (mode, a, b, side, offset) in overrides:
        if offset is None:
            continue

        if mode == "ring":
            # RING (Between=[label,'*']) is ALWAYS independent, even
            # against a sibling that's a REAL space, not just EXT: only
            # THIS space (the anchor) moves -- its own Cells shape and,
            # if it has one, its child's given frame -- the neighbour
            # on the other side of every chosen edge is NEVER touched,
            # regardless of whether that neighbour is plain or hosts a
            # child of its own. That's what makes ring simpler than a
            # pair: there's no "which mechanism does the other side
            # need" question to answer, so no adjacency lookup either --
            # unlike EXT, a side doesn't need to actually touch the
            # grid's own edge to be valid here, every side of a space is
            # fair game since we don't care what's beyond it.
            #
            # EXT is the one anchor that ISN'T a real space -- ['EXT','*']
            # (or ['*','EXT'], _parse_between doesn't care which slot the
            # '*' is in) means EVERY space that touches the grid's own
            # perimeter, each shifted independently on just the side(s)
            # IT actually touches -- never a literal label match, since
            # no space is ever named 'EXT'. A side filter narrows to
            # spaces touching THAT side specifically; unfiltered, each
            # space moves on every perimeter side it has (mirroring the
            # EXT-PAIR per-space unfiltered case above, just run once per
            # space instead of once for a single named one). A space
            # that doesn't touch the perimeter at all, or not on the
            # filtered side, is silently skipped -- unlike a single
            # wrongly-filtered EXT-pair anchor, not touching a given
            # side here is the ordinary case for most spaces, not a
            # mistake worth warning about.
            if a == "EXT":
                if side is not None:
                    chosen_sides = [s for s in side
                                     if _space_touches_side(sp, s, ncols, nrows)]
                else:
                    chosen_sides = _perimeter_sides(sp, ncols, nrows)
                for chosen_side in chosen_sides:
                    restricted.add(chosen_side)
                    if chosen_side == "W":
                        dx0 -= offset
                    elif chosen_side == "E":
                        dx1 += offset
                    elif chosen_side == "S":
                        dy0 -= offset
                    elif chosen_side == "N":
                        dy1 += offset
                continue
            if not _matches_label(my_label, [a]):
                continue
            chosen_sides = side if side is not None else ("W", "E", "N", "S")
            for chosen_side in chosen_sides:
                restricted.discard(chosen_side)
                if chosen_side == "W":
                    dx0 -= offset
                elif chosen_side == "E":
                    dx1 += offset
                elif chosen_side == "S":
                    dy0 -= offset
                elif chosen_side == "N":
                    dy1 += offset
            continue

        i_am_a = _matches_label(my_label, [a])
        i_am_b = _matches_label(my_label, [b])
        if not (i_am_a or i_am_b):
            continue
        other = b if i_am_a else a
        if other == "EXT":
            if side is not None:
                chosen_sides = [s for s in side
                                if _space_touches_side(sp, s, ncols, nrows)]
                if not chosen_sides:
                    warnings.append(
                        "{}: border override {!r} -- {!r} doesn't "
                        "touch the {} side{} -- Offset skipped."
                        .format(name, [a, b, ",".join(sorted(side))],
                                my_label, "/".join(sorted(side)),
                                "" if len(side) == 1 else "s"))
                    continue
            else:
                chosen_sides = _perimeter_sides(sp, ncols, nrows)
                if not chosen_sides:
                    warnings.append(
                        "{}: border override {!r} -- {!r} doesn't "
                        "touch the grid's own edge at all -- Offset "
                        "skipped.".format(name, [a, b], my_label))
                    continue
            for chosen_side in chosen_sides:
                restricted.add(chosen_side)
                if chosen_side == "W":
                    dx0 -= offset
                elif chosen_side == "E":
                    dx1 += offset
                elif chosen_side == "S":
                    dy0 -= offset
                elif chosen_side == "N":
                    dy1 += offset
            continue
        if not sp_has_child:
            continue    # sp itself is plain -- the SHARED mechanism instead
        other_sp = _find_space(spaces, other)
        if other_sp is None:
            continue
        if _child_for_space(children_by_label, other_sp["label"]) is None:
            continue    # other side is plain -- the SHARED mechanism instead
        rel = _find_track_boundary(sp, other_sp)
        if rel is None:
            continue
        axis, _idx, sp_is_before = rel
        if axis == "col":
            if sp_is_before:
                dx1 += offset
            else:
                dx0 -= offset
        else:
            if sp_is_before:
                dy0 -= offset
            else:
                dy1 += offset
    return dx0, dy0, dx1, dy1, restricted


def _own_side_of_interior(lx0, ly0, lx1, ly1, rx0, ry0, rx1, ry1, delta):
    """One space's OWN edge along an INTERIOR boundary originally at
    (lx0,ly0)-(lx1,ly1) -- shifted by that space's own independent-
    offset `delta` (dx0,dy0,dx1,dy1 from space_deltas, or None/all-
    zero if this space was never targeted, in which case the ORIGINAL
    segment comes back unchanged). (rx0,ry0,rx1,ry1) is that SAME
    space's own rect (rect_of(sp)), used only to work out WHICH of its
    4 edges originally sat at this boundary:
      - a VERTICAL boundary (lx0==lx1): the space whose own east edge
        (rx1) equals lx0 contributes its dx1 for the shared LINE
        POSITION; the space whose own west edge (rx0) equals lx0
        instead contributes dx0. NEITHER matching (only possible for a
        non-rectangular merge -- this boundary sits on an edge that's
        genuinely against a SIBLING, not the space's own true bbox
        edge in this direction at all, e.g. the s1/k/s2 worked example
        in test_border_overrides.py) leaves the LINE POSITION
        untouched -- this space has no legitimate claim on a position
        it was never really at. EITHER WAY (matched or not), the two
        RANGE endpoints (ly0, ly1) STILL each pick up that SAME
        space's own dy0 (whichever of the two is numerically SMALLER
        -- the south end) / dy1 (the LARGER -- north), unconditionally
        -- so a space that's ALSO independently offset on its
        perpendicular sides (e.g. an unfiltered ring, or an unfiltered
        EXT match touching several sides at once, shrinking every side
        together) still draws a correspondingly SHORTER edge here too,
        even on a boundary whose LINE POSITION didn't move at all.
        Picked by VALUE, not by which one happens to be called ly0 vs
        ly1 -- _borders() doesn't guarantee a consistent scan
        direction, ly0 is NOT always the smaller of the two.
      - a HORIZONTAL boundary (ly0==ly1): the mirror image -- dy1 or
        dy0 (or neither) picks the LINE POSITION, dx0 (smaller/west)
        and dx1 (larger/east) unconditionally shift the (lx0, lx1)
        range endpoints, again by value.
    Called once per touching space on a diverged interior boundary --
    see _emit's border-emission loop and the module docstring's own
    DUPLICATE INTERIOR SEGMENTS section for why there can now be TWO
    of these instead of one. NOTE: an earlier version of this fix
    zeroed a RESTRICTED (EXT-only) delta's components entirely before
    they ever reached this function -- wrong, because it also
    suppressed the RANGE trim above for the ordinary rectangular case
    (e.g. a plain corner cell with an unfiltered EXT offset touching
    two sides at once), which was never actually broken. The neither-
    edge-matches check here is the correct, narrower fix -- it only
    ever affects the LINE POSITION, never the range trim."""
    if not delta:
        return (lx0, ly0, lx1, ly1)
    dx0, dy0, dx1, dy1 = delta
    if not (dx0 or dy0 or dx1 or dy1):
        return (lx0, ly0, lx1, ly1)
    if lx0 == lx1:
        if rx1 == lx0:
            x = lx0 + dx1
        elif rx0 == lx0:
            x = lx0 + dx0
        else:
            x = lx0
        if ly0 <= ly1:
            return (x, ly0 + dy0, x, ly1 + dy1)
        return (x, ly0 + dy1, x, ly1 + dy0)
    if ry1 == ly0:
        y = ly0 + dy1
    elif ry0 == ly0:
        y = ly0 + dy0
    else:
        y = ly0
    if lx0 <= lx1:
        return (lx0 + dx0, y, lx1 + dx1, y)
    return (lx0 + dx1, y, lx1 + dx0, y)


# -----------------------------------------------------------------
# WALL LAYOUTS -- an upright child hosted on a border rather than a
# cell. See the module docstring's WALL LAYOUTS section and
# _node_wall_layouts above (which finds/parses the overrides that
# carry one); this section is the GEOMETRY -- which edge of the
# matched space a border sits on, and the plane that follows from it.
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


def _space_edge_at(rx0, ry0, rx1, ry1, lx0, ly0, lx1, ly1):
    """Which edge (N/S/E/W) of a space's own rect (rx0,ry0,rx1,ry1) an
    ORIGINAL boundary at (lx0,ly0)-(lx1,ly1) sits on -- None if it
    touches none of the rect's 4 sides (shouldn't happen for a real
    match; defensive only). Same 'which side matches' check
    _own_side_of_interior already makes internally, just returning the
    side CODE instead of using it to pick a delta."""
    if lx0 == lx1:
        if rx1 == lx0:
            return "E"
        if rx0 == lx0:
            return "W"
    elif ly0 == ly1:
        if ry1 == ly0:
            return "N"
        if ry0 == ly0:
            return "S"
    return None


def _wall_plane_axes(edge, seg):
    """Given which edge a (possibly offset) segment represents,
    relative to its owning space, and that segment's own 2 endpoints
    (order unspecified -- _own_side_of_interior's own output isn't
    guaranteed to match any particular winding) -- returns (origin_xy,
    second_xy), the FIRST corner and the SECOND, per that space's own
    CCW polygon traversal (_rect_curve's fixed point order,
    (x0,y0)->(x1,y0)->(x1,y1)->(x0,y1)) for that specific edge:
      S: west -> east.   E: south -> north.
      N: east -> west.   W: north -> south.
    Combined with a wall Y-axis of parent-up, X = (origin -> second)
    ALWAYS gives an outward-pointing plane normal (X cross Y) --
    verified for all 4 edges, matches PMS-R7's own wall convention
    (pms-generate-assemblies.py's _wall_geom: normals point OUT of the
    plan) -- see the module docstring's WALL LAYOUTS section."""
    x0, y0, x1, y1 = seg
    if edge in ("S", "N"):
        west, east = ((x0, y0), (x1, y1)) if x0 <= x1 else ((x1, y1), (x0, y0))
        return (west, east) if edge == "S" else (east, west)
    south, north = ((x0, y0), (x1, y1)) if y0 <= y1 else ((x1, y1), (x0, y0))
    return (south, north) if edge == "E" else (north, south)


def _upright_plane_from(parent_plane, origin_xy, second_xy):
    """The wall's own plane: origin at origin_xy (parent-local 2D),
    X-axis toward second_xy (the border's own direction, in the
    parent's own local frame), Y-axis the PARENT's own up (its XAxis
    cross YAxis -- world Z in the common unwired-Geom.Plane case, but
    correctly follows the parent's own orientation if the whole tree
    has been rotated). See _wall_plane_axes for why this always gives
    an outward-pointing normal, given how it picks origin vs second
    per edge."""
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


# -----------------------------------------------------------------
# SOLVE -- track sizing, cell rectangles, label merging, borders.
# Unchanged from the old all-in-one Layout component.
# -----------------------------------------------------------------

def _clip_labels_grid(labels_grid, n_cols, n_rows, name, warnings):
    """Force labels_grid to exactly n_rows x n_cols so every row/col
    index used downstream is guaranteed valid against col_tracks /
    row_tracks -- a CellLabels grid authored with a different cell
    count than CellWidths/CellLengths would otherwise crash the solver
    with a raw IndexError instead of degrading; this clips/pads it and
    warns instead. Extra rows/cols are dropped; missing ones are
    padded with ''."""
    nrows = len(labels_grid)
    ncols = len(labels_grid[0]) if nrows else 0
    if nrows != n_rows or ncols != n_cols:
        warnings.append(
            "{}: CellLabels is {} rows x {} cols but CellWidths/"
            "CellLengths give {} cols x {} rows -- clipped/padded to "
            "match. Fix the counts to control which cells that "
            "affects.".format(name, nrows, ncols, n_cols, n_rows))
    out = []
    for r in range(n_rows):
        row = labels_grid[r] if r < nrows else []
        row = list(row[:n_cols]) + [""] * max(0, n_cols - len(row))
        out.append(row)
    return out


def _resolve_tracks(tracks, total, auto_demand, name, warnings):
    """tracks: canonical atoms (float mm, 'Nfr', 'auto', or an
    unsupported 'minmax(...)'). total: the mm this axis is given by
    the parent, or None (root -- nothing external constrains it).
    auto_demand: one number per track, the mm an 'auto' entry there
    should take (from _distribute_auto_demand); 0 where nothing
    demands anything. Returns (starts, sizes, resolved_total)."""
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
                "{} has 'fr' tracks with nothing to share -- this node "
                "has no externally-imposed size (it's the root, or "
                "every track on this axis is 'fr'/'auto' with no fixed "
                "anchor), so they resolve to 0mm.".format(name))
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
    """tracks: this axis's raw canonical atoms. spans_and_needs: a
    list of (lo, hi, needed_mm) -- one per space that hosts a child,
    needed_mm = that child's own INTRINSIC size along this axis
    (_intrinsic_size). Returns one number per track: the mm an 'auto'
    track at that index should grow to. Only the 'auto' tracks inside
    a span absorb its shortfall (evenly), after the span's fixed
    tracks are counted -- 'fr' / 'minmax' siblings in the span
    contribute 0, same as they do to intrinsic sizing everywhere
    else. Multiple children touching the same track (nested spans
    sharing a track) take the max, never the sum."""
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


def _merge_spaces(labels_grid, warnings):
    """4-connected flood fill on the FULL label (suffix included --
    '[k]' is the do-NOT-merge marker, typed by hand, see the module
    docstring). Returns [{label, r0, c0, r1, c1, cells}, ...] IN
    ROW-MAJOR ORDER OF EACH SPACE'S FIRST (top-left-most) CELL. r0/c0/
    r1/c1 are the BOUNDING BOX (used for auto-track spans and for
    placing a bound child, which needs a rectangular frame); 'cells'
    is the full connected (r, c) set, used by _region_outline to trace
    the actual shape -- which need not be a rectangle; L / T / U
    shapes are fine, see _emit."""
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
                            "c0": c0, "c1": c1, "cells": set(cells)})
    return spaces


def _is_rectangular(sp):
    return len(sp["cells"]) == (sp["r1"] - sp["r0"] + 1) * (sp["c1"] - sp["c0"] + 1)


def _region_outline(cells, col_starts, col_sizes, row_starts, row_sizes,
                     total_l, ncols=None, nrows=None):
    """Traces the rectilinear outer boundary of a connected set of
    grid cells as a list of (x, y) points (CCW, first point NOT
    repeated at the end) -- works for any orthogonal shape (L / T / U
    / ...), not just a rectangle: a cell contributes an edge only on
    the sides where its neighbour is OUTSIDE the region, and those
    edges chain end-to-end into the boundary loop. Returns (points,
    edge_dirs, edge_ext, had_multiple_loops) -- edge_dirs[k] is the
    S/E/N/W direction (same vocabulary as SIDE_CODES/_dumb_offset_
    for_space) of the edge points[k] -> points[(k+1) % len(points)];
    edge_ext[k] (only meaningful if ncols/nrows are given) is True
    when that edge is against the GRID'S OWN outer edge (its neighbour
    cell coordinate falls outside 0<=r<nrows / 0<=c<ncols entirely),
    False when it's really an INTERIOR boundary against a different
    space that just happens to sit in the same direction (e.g. a
    non-rectangular space's own edge facing a sibling one row over,
    same W/E/N/S tag as its true perimeter edge elsewhere) -- lets a
    caller (_shift_outline_edges) shift only the edges facing a
    requested side instead of the whole outline, and for an EXT-
    flavoured override, only the ones that are ACTUALLY against the
    perimeter, not a same-direction edge that's really against a
    sibling (see _shift_outline_edges' own docstring for the worked
    example this exists for). Omit ncols/nrows (or pass None) if the
    caller only needs edge_dirs -- edge_ext then comes back all False,
    harmless as long as the caller never treats a direction as
    'restricted' (see _dumb_offset_for_space). Note a straight run
    spanning several grid cells produces SEVERAL same-direction edges
    in a row (a "straight-through" point with no real corner there),
    not one merged edge -- _shift_outline_edges already accounts for
    this. had_multiple_loops means a hole or a single-point pinch in
    the shape; only the longest loop is returned, the caller decides
    whether to warn. (None, None, None, False) if the region is empty
    or degenerate."""
    start_map = {}
    dir_map = {}
    ext_map = {}
    for (r, c) in cells:
        x0 = col_starts[c]
        x1 = col_starts[c] + col_sizes[c]
        y1 = total_l - row_starts[r]
        y0 = y1 - row_sizes[r]
        if (r + 1, c) not in cells:
            start_map[(x0, y0)] = (x1, y0)          # south
            dir_map[(x0, y0)] = "S"
            ext_map[(x0, y0)] = nrows is not None and r + 1 >= nrows
        if (r, c + 1) not in cells:
            start_map[(x1, y0)] = (x1, y1)          # east
            dir_map[(x1, y0)] = "E"
            ext_map[(x1, y0)] = ncols is not None and c + 1 >= ncols
        if (r - 1, c) not in cells:
            start_map[(x1, y1)] = (x0, y1)          # north
            dir_map[(x1, y1)] = "N"
            ext_map[(x1, y1)] = r - 1 < 0
        if (r, c - 1) not in cells:
            start_map[(x0, y1)] = (x0, y0)          # west
            dir_map[(x0, y1)] = "W"
            ext_map[(x0, y1)] = c - 1 < 0

    loops = []
    visited = set()
    cap = len(start_map) + 1
    for start in start_map:
        if start in visited:
            continue
        loop = [start]
        visited.add(start)
        cur = start_map[start]
        closed = False
        for _ in range(cap):
            if cur == start:
                closed = True
                break
            if cur in visited or cur not in start_map:
                break
            loop.append(cur)
            visited.add(cur)
            cur = start_map[cur]
        if closed and len(loop) >= 3:
            loops.append(loop)

    if not loops:
        return None, None, None, False
    loops.sort(key=len, reverse=True)
    best = loops[0]
    edge_dirs = [dir_map[p] for p in best]
    edge_ext = [ext_map[p] for p in best]
    return best, edge_dirs, edge_ext, len(loops) > 1


def _shift_outline_edges(points, edge_dirs, edge_ext, dx0, dy0, dx1, dy1,
                          restricted):
    """The non-rectangular generalization of a rectangle's own 4-
    corner offset shift (x0+dx0, y0+dy0, x1+dx1, y1+dy1): every edge
    in a traced outline (see _region_outline) moves by whichever of
    dx0/dx1/dy0/dy1 matches ITS OWN S/E/N/W direction tag -- UNLESS
    that direction is in `restricted` (an EXT-flavoured override --
    see _dumb_offset_for_space) AND this particular edge isn't
    actually against the grid's own perimeter (edge_ext[k] is False),
    in which case it's left untouched: an EXT match only ever meant
    to push out the space's TRUE outer boundary, never a same-
    direction edge that's really facing a sibling. A plain RING's
    directions are never restricted, so it keeps its own documented
    'doesn't care what's beyond' behaviour -- every matching-direction
    edge moves regardless of what's on the other side.
    Worked example this exists for: cellLabels
    s1,s1 / k,s1 / k,s2 / s2,s2 -- s1 = {(0,0),(0,1),(1,1)}, an
    upside-down L whose west side has TWO edges tagged 'W': row 0's
    (x=0, the grid's true left edge) and row 1's (x=1000, s1's own
    edge against k). An EXT override filtered to Left touches ONLY
    row 0's edge (edge_ext True); row 1's edge against k (edge_ext
    False) stays exactly where it was, so k's own boundary and s1's
    stay coincident there -- no gap, no overlap.
    A vertex sits between exactly two edges (the one ending there, the
    one starting there) -- an ordinary CORNER has one horizontal (S/N)
    and one vertical (E/W) neighbour, so it picks up at most one
    x-delta and one y-delta, exactly like a rectangle's own corner; a
    STRAIGHT-THROUGH point (see _region_outline) has two neighbours of
    the SAME direction, so membership ('in', not a sum) is used to
    avoid double-applying that one delta twice. Where an EXT-
    restricted edge is inactive, the vertex simply doesn't pick up
    that delta from it -- if its OTHER neighbour edge still supplies
    one, the two now-different-length edges meeting at that vertex
    naturally re-join with no gap (see the worked example above)."""
    def active_dir(idx):
        d = edge_dirs[idx]
        if d in restricted and not edge_ext[idx]:
            return None
        return d

    out = []
    for i, (x, y) in enumerate(points):
        dirs = (active_dir(i - 1), active_dir(i))
        sx = dx0 if "W" in dirs else (dx1 if "E" in dirs else 0.0)
        sy = dy0 if "S" in dirs else (dy1 if "N" in dirs else 0.0)
        out.append((x + sx, y + sy))
    return out


def _cell_space_index(spaces):
    """(r, c) -> index into `spaces` (the SAME index _emit uses to
    build that space's Cells branch, path.AppendElement(i)) -- lets
    _borders report, for each line, which space(s) it belongs to."""
    lookup = {}
    for i, sp in enumerate(spaces):
        for rc in sp["cells"]:
            lookup[rc] = i
    return lookup


def _perimeter_runs(labels, indices, start_bound, end_bound):
    """labels: per-cell label strings along one scan axis, in scan
    order. indices: per-cell SPACE index (see _cell_space_index) along
    the same axis, same order -- constant within one run by
    construction (a run only continues while the label stays the
    same, and same-label adjacent cells are always one merged space).
    start_bound(i) / end_bound(i): the two boundary mm values of cell
    i along that axis, in SCAN order (not necessarily numerically
    ascending -- the caller decides). Returns a list of
    (v0, v1, space_index) tuples, one per merged run of consecutive
    SAME-label cells -- exactly the same merge-adjacent-matching-
    labels rule the interior lines already use, just anchored on the
    outer edge instead of a neighbouring row/column. A label change
    breaks the run; two adjacent 'A' cells (even un-merged
    'A[0]'/'A[1]' spaces) still share one perimeter segment, same as
    they'd share one interior wall against a THIRD label."""
    runs = []
    run_label = None
    run_start_i = None
    n = len(labels)
    for i in range(n + 1):
        label = labels[i] if i < n else None
        if label != run_label:
            if run_label is not None:
                runs.append((start_bound(run_start_i), end_bound(i - 1),
                             indices[run_start_i]))
            run_label, run_start_i = label, i
    return runs


def _borders(labels_grid, col_starts, col_sizes, row_starts, row_sizes,
             total_l, cell_space_index):
    """Returns a list of (x0, y0, x1, y1, space_indices) -- the same
    lines as before, each now also carrying the space index/indices
    (into THIS node's own `spaces`, i.e. the same index Cells uses to
    build that space's own branch) it touches: one index for a
    perimeter segment (its interior side only), one or two for an
    interior segment (both sides -- always two distinct spaces in
    practice, since a run only continues while the label stays the
    same and same-label adjacent cells are already one merged space).
    A cell with no space at all (shouldn't happen, defensive only)
    contributes nothing to space_indices rather than crashing."""
    nrows = len(labels_grid)
    ncols = len(labels_grid[0]) if nrows else 0

    def row_y(r):
        y1 = total_l - row_starts[r]
        return y1 - row_sizes[r], y1

    def col_x(c):
        return col_starts[c], col_starts[c] + col_sizes[c]

    def idx_at(r, c):
        return cell_space_index.get((r, c))

    def sides(*rc_pairs):
        return tuple(sorted({idx_at(r, c) for (r, c) in rc_pairs
                              if idx_at(r, c) is not None}))

    segs = []

    for c in range(1, ncols):
        run_pair, run_r0 = None, None
        for r in range(nrows + 1):
            pair = None
            if r < nrows:
                left, right = labels_grid[r][c - 1], labels_grid[r][c]
                pair = None if left == right else (left, right)
            if pair != run_pair:
                if run_pair is not None:
                    y0, _ = row_y(r - 1)
                    _, y1 = row_y(run_r0)
                    x, _ = col_x(c)
                    idxs = sides((run_r0, c - 1), (run_r0, c))
                    segs.append((x, y0, x, y1, idxs))
                run_pair, run_r0 = pair, r

    for r in range(1, nrows):
        run_pair, run_c0 = None, None
        for c in range(ncols + 1):
            pair = None
            if c < ncols:
                top, bottom = labels_grid[r - 1][c], labels_grid[r][c]
                pair = None if top == bottom else (top, bottom)
            if pair != run_pair:
                if run_pair is not None:
                    x0, _ = col_x(run_c0)
                    _, x1 = col_x(c - 1)
                    y = row_y(r)[1]
                    idxs = sides((r - 1, run_c0), (r, run_c0))
                    segs.append((x0, y, x1, y, idxs))
                run_pair, run_c0 = pair, c

    total_w = (col_starts[-1] + col_sizes[-1]) if ncols else 0.0

    def col_lo(c):
        return col_x(c)[0]

    def col_hi(c):
        return col_x(c)[1]

    def row_lo(r):     # scan order (r=0 -> north): entering edge = north (high y)
        return row_y(r)[1]

    def row_hi(r):      # scan order: leaving edge = south (low y)
        return row_y(r)[0]

    def as_idxs(space_index):
        return () if space_index is None else (space_index,)

    if ncols:
        north_labels = [labels_grid[0][c] for c in range(ncols)]
        north_idx = [idx_at(0, c) for c in range(ncols)]
        for (x0, x1, si) in _perimeter_runs(north_labels, north_idx, col_lo, col_hi):
            segs.append((x0, total_l, x1, total_l, as_idxs(si)))

        south_labels = [labels_grid[nrows - 1][c] for c in range(ncols)]
        south_idx = [idx_at(nrows - 1, c) for c in range(ncols)]
        for (x0, x1, si) in _perimeter_runs(south_labels, south_idx, col_lo, col_hi):
            segs.append((x0, 0.0, x1, 0.0, as_idxs(si)))

    if nrows:
        west_labels = [labels_grid[r][0] for r in range(nrows)]
        west_idx = [idx_at(r, 0) for r in range(nrows)]
        for (y0, y1, si) in _perimeter_runs(west_labels, west_idx, row_lo, row_hi):
            segs.append((0.0, y0, 0.0, y1, as_idxs(si)))

        east_labels = [labels_grid[r][ncols - 1] for r in range(nrows)]
        east_idx = [idx_at(r, ncols - 1) for r in range(nrows)]
        for (y0, y1, si) in _perimeter_runs(east_labels, east_idx, row_lo, row_hi):
            segs.append((total_w, y0, total_w, y1, as_idxs(si)))

    return segs


def _border_labels(spaces, idxs):
    """Two labels for one border segment (see _borders' `idxs`): the
    label of every space it touches, 'EXT' filling in for the side
    with no space (a perimeter run -- the edge of THIS node's own
    grid, not necessarily the true building exterior, since a node's
    own borders never look past its own parent/child boundary)."""
    labels = [spaces[i]["label"] for i in idxs]
    while len(labels) < 2:
        labels.append("EXT")
    return labels[:2]


def _node_children_by_label(node):
    """label -> child dict, keyed by the child's OWN literal label AS
    GIVEN -- not forced down to its base. A base label ('mod') still
    binds to every 'mod[k]' instance exactly as before, via the BASE-
    LABEL FALLBACK in _child_for_space below; an EXACT instance label
    ('mod[0]') now binds to just that one instance instead, taking
    priority over any base-label sibling. This is what lets mod[0] and
    mod[1] each host their OWN distinct child even though they share a
    base label, instead of one silently overwriting the other -- the
    old behaviour stored EVERY child under its base label regardless
    of whether it was authored with an exact or base label itself, so
    two same-base children (e.g. one 'mod[0]', one 'mod[1]') collided
    on the same dict key and only the last one processed survived."""
    children_by_label = {}
    for ch in (node.get("childLayouts") or []):
        clabel = ch.get("label")
        if isinstance(clabel, string_types) and clabel:
            children_by_label[clabel] = ch
    return children_by_label


def _child_for_space(children_by_label, label):
    """The child bound to a space's own `label` -- an EXACT match
    first (a child authored specifically for THIS instance, e.g.
    'mod[0]'), falling back to the BASE label (a child shared across
    every same-base instance that doesn't have its own exact entry,
    e.g. 'mod') -- see _node_children_by_label."""
    child = children_by_label.get(label)
    if child is not None:
        return child
    return children_by_label.get(_base_label(label))


def _resolve_node(node, given_w, given_h, warnings, intrinsic_memo):
    """Resolve one node's own tracks into cell rectangles. given_w /
    given_h: the mm this node is given by its parent cell, or None at
    the root. intrinsic_memo: passed straight through to
    _intrinsic_size for any 'auto'-hosted child -- see there for why
    this matters. Returns (col_starts, col_sizes, total_w, row_starts,
    row_sizes, total_l, spaces, children_by_label, labels_grid) --
    labels_grid is the CLIPPED grid (guaranteed to match the track
    counts)."""
    col_tracks = node.get("cellWidths") or ["1fr"]
    row_tracks = node.get("cellLengths") or ["1fr"]
    labels_grid = node.get("cellLabels") or [[""]]
    name = node.get("label") or "<root>"
    labels_grid = _clip_labels_grid(
        labels_grid, len(col_tracks), len(row_tracks), name, warnings)

    children_by_label = _node_children_by_label(node)
    spaces = _merge_spaces(labels_grid, warnings)

    col_needs, row_needs = [], []
    for sp in spaces:
        child = _child_for_space(children_by_label, sp["label"])
        if child is None:
            continue
        # Only measure a child's intrinsic size when its span actually
        # contains an 'auto' track to feed -- a fixed/fr span never
        # reads col_needs/row_needs (_distribute_auto_demand finds no
        # 'auto' index there), so measuring anyway is both wasted work
        # AND wrongly resolves the child with given=None (intrinsic,
        # unconstrained), which can warn about the child's own 'fr'
        # tracks having nothing to share EVEN WHEN the real draw pass
        # would hand it a perfectly good fixed size from this span.
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
    if overrides:
        # Zero-sum by construction (one track grows exactly as much as
        # its neighbour shrinks), so total_w/total_l never need
        # recomputing here.
        _apply_shared_offsets(spaces, children_by_label, col_starts,
                               col_sizes, row_starts, row_sizes, overrides,
                               name, warnings)

    return (col_starts, col_sizes, total_w, row_starts, row_sizes, total_l,
            spaces, children_by_label, labels_grid, overrides)


def _intrinsic_size(node, warnings, memo):
    """This node's own (width, length) with nothing externally
    imposed -- 'fr' tracks contribute 0, 'auto' tracks size from any
    nested child's own intrinsic size, recursively. MEMOIZED by node
    identity: intrinsic sizing always resolves with given=None, so the
    result never changes -- without this cache, a node several levels
    deep gets its whole subtree re-solved from scratch once per
    ancestor whose 'auto' track needs to measure it (and once per
    instance when a label like 'a[0]'..'a[3]' shares one child), which
    blows up combinatorially with depth and re-fires every warning
    that many times over."""
    key = id(node)
    if key in memo:
        return memo[key]
    _, _, total_w, _, _, total_l, _, _, _, _ = _resolve_node(
        node, None, None, warnings, memo)
    memo[key] = (total_w, total_l)
    return total_w, total_l


# -----------------------------------------------------------------
# TREE SHAPE -- the emission walk. See the module docstring.
# -----------------------------------------------------------------

def _polygon_curve(plane, points):
    closed = list(points) + [points[0]]
    world = [plane.PointAt(px, py, 0.0) for px, py in closed]
    return rg.PolylineCurve(world)


def _rect_curve(plane, x0, y0, x1, y1):
    return _polygon_curve(plane, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _rect_border_lines(plane, x0, y0, x1, y1):
    """The 4 sides of a plain rectangle as Lines -- used ONLY for the
    root's own boundary at Depth 0 (run()'s job), which has no grid of
    its own for _borders() to walk: it's one un-subdivided shape, so
    its 'unique border segments' are simply its 4 edges."""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    lines = []
    for k in range(4):
        p0 = plane.PointAt(corners[k][0], corners[k][1], 0.0)
        p1 = plane.PointAt(corners[(k + 1) % 4][0], corners[(k + 1) % 4][1], 0.0)
        lines.append(rg.Line(p0, p1))
    return lines


def _emit(node, given_w, given_h, plane, path, cells_tree,
          labels_tree, borders_tree, topology_tree, warnings,
          intrinsic_memo, sides_tree=None):
    """`path` is the LIST BRANCH `node`'s own children are collected
    into -- EVERY merged space of `node` is one ITEM in that SAME
    branch (a proper list, row-major order), not one branch per space.
    A space WITH a bound child additionally recurses into it, passing
    path.AppendElement(that space's row-major index) as the CHILD's
    own `path` -- the branch the child's OWN children (if it has any)
    get listed in, one level deeper. Nothing is discarded: every
    level of the chain is in the tree at once, each as its own list.

    The ROOT is the one exception: nothing lists it, so its own
    overall boundary is drawn once, directly, at its bare item path
    {i} (run()'s job, not this function's -- see its return value
    below). Since {i} is already taken by that, the root's own
    CHILDREN (this function's first-ever call) get the next branch
    down, {i;0} -- see run().

    Border lines are collected into `borders_tree` at this SAME `path`
    -- i.e. a node's own border computation (its interior divisions
    and its own per-run-segmented perimeter, see _borders()) lands in
    the EXACT SAME branch as the cells it belongs to, so Borders now
    shares Cells' tree shape exactly and Depth filters it the same
    way. Every segment in a branch is already unique by construction
    -- one node's own single grid computation, not a merge of several.

    `topology_tree` is a GRAFTED version of that same border list:
    border k within THIS branch (path.AppendElement(k), 0-based, same
    order _borders() returned it in) holds exactly 2 items -- the
    label of every space that border touches, 'EXT' filling in for a
    perimeter run (see _border_labels()). One graft level deeper than
    Borders itself, so Depth needs +1 to reach the matching slice.
    Labels and Topology are ALWAYS built here, whether or not the two
    selector inputs (see the module docstring's SELECTORS section) end
    up narrowing them further downstream in run().

    BORDER OVERRIDES (node.get('borderOverrides'), see _node_overrides
    and the module docstring's own BORDER OVERRIDES section): the
    SHARED (track-shifting) mechanism already happened inside
    _resolve_node, before col_starts/col_sizes/row_starts/row_sizes
    ever reach here -- nothing extra to do for it in this function.
    The INDEPENDENT mechanism is computed once per space here, via
    _dumb_offset_for_space, and applied to THREE things consistently:
    the space's own drawn cell shape, its matching perimeter segment
    in Borders, and (if it has one) its child's given rectangle.

    Returns (total_w, total_l) -- this node's OWN overall size -- so
    the caller can draw ITS boundary too: every node's rectangle is
    normally drawn by whichever node contains it as a cell, but the
    true root has no container, so run() uses this return value to
    draw the root's own boundary once, at the bare path it was never
    otherwise given.

    `sides_tree` is OPTIONAL (default None, and every existing direct
    caller -- tests included -- keeps working unchanged if they never
    pass it): a PARALLEL list to borders_tree (same path, same index,
    like labels_tree is to cells_tree -- not grafted like
    topology_tree) recording each segment's own N/S/E/W side, only
    ever set for a PERIMETER run (an INTERIOR segment's side is always
    None -- it touches two spaces, there's no single edge to name).
    Computed once here, from the node's own LOCAL grid coordinates
    BEFORE the plane transform (so it's correct even under an
    arbitrarily rotated Geom.Plane) and BEFORE any border-override
    shift is applied to lx0/ly0/lx1/ly1 (so it reflects the segment's
    original grid-edge position, not its already-offset one). Used
    only internally by run()'s Borders selector side filter -- never
    exposed as a component output, same "computed but not always
    consumed" pattern Labels/Topology used when only the selectors
    needed them."""
    (col_starts, col_sizes, total_w, row_starts, row_sizes, total_l,
     spaces, children_by_label, labels_grid, overrides) = _resolve_node(
        node, given_w, given_h, warnings, intrinsic_memo)

    def rect_of(sp):
        x0 = col_starts[sp["c0"]]
        x1 = col_starts[sp["c1"]] + col_sizes[sp["c1"]]
        y1 = total_l - row_starts[sp["r0"]]
        y0 = total_l - row_starts[sp["r1"]] - row_sizes[sp["r1"]]
        return x0, y0, x1, y1

    cells_tree.EnsurePath(path)
    labels_tree.EnsurePath(path)

    name = node.get("label") or "<root>"
    space_deltas = {}   # space index -> (dx0, dy0, dx1, dy1), for the
                         # border-segment pass below -- see there.
    wall_layouts = _node_wall_layouts(node, warnings)
    wall_k = 0   # ordinary counter for wall-hosted branches -- no
                 # disjoint-numbering trick, same convention cell-
                 # hosted children already use (see the module
                 # docstring's WALL LAYOUTS / output-addressing note).

    for i, sp in enumerate(spaces):
        child = _child_for_space(children_by_label, sp["label"])

        dx0 = dy0 = dx1 = dy1 = 0.0
        restricted = set()
        if overrides:
            dx0, dy0, dx1, dy1, restricted = _dumb_offset_for_space(
                sp, spaces, children_by_label, overrides,
                len(col_sizes), len(row_sizes), name, warnings)
        has_offset = bool(dx0 or dy0 or dx1 or dy1)
        if has_offset:
            space_deltas[i] = (dx0, dy0, dx1, dy1)

        if sp["label"]:
            if has_offset and _is_rectangular(sp):
                x0, y0, x1, y1 = rect_of(sp)
                points = [(x0 + dx0, y0 + dy0), (x1 + dx1, y0 + dy0),
                          (x1 + dx1, y1 + dy1), (x0 + dx0, y1 + dy1)]
            else:
                points, edge_dirs, edge_ext, multi_loop = _region_outline(
                    sp["cells"], col_starts, col_sizes, row_starts,
                    row_sizes, total_l, len(col_sizes), len(row_sizes))
                if points is None:
                    x0, y0, x1, y1 = rect_of(sp)
                    if has_offset:
                        x0, y0, x1, y1 = (x0 + dx0, y0 + dy0,
                                           x1 + dx1, y1 + dy1)
                    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                else:
                    if multi_loop:
                        warnings.append(
                            "label {!r} traces to more than one boundary "
                            "loop (a hole, or a single-point pinch) -- "
                            "only the outer boundary is drawn."
                            .format(sp["label"]))
                    if has_offset:
                        points = _shift_outline_edges(
                            points, edge_dirs, edge_ext,
                            dx0, dy0, dx1, dy1, restricted)
            cells_tree.Add(_polygon_curve(plane, points), path)
            labels_tree.Add(sp["label"], path)

        if child is not None:
            if not _is_rectangular(sp):
                warnings.append(
                    "label {!r} hosts a child but isn't a rectangular "
                    "block -- the child is placed using its bounding "
                    "box, not its exact shape (a child needs a "
                    "rectangular frame to solve against).".format(sp["label"]))
            x0, y0, x1, y1 = rect_of(sp)
            x0, y0, x1, y1 = x0 + dx0, y0 + dy0, x1 + dx1, y1 + dy1
            child_plane = rg.Plane(
                plane.PointAt(x0, y0, 0.0), plane.XAxis, plane.YAxis)
            _emit(child, x1 - x0, y1 - y0, child_plane, path.AppendElement(i),
                  cells_tree, labels_tree, borders_tree, topology_tree,
                  warnings, intrinsic_memo, sides_tree=sides_tree)

    borders_tree.EnsurePath(path)
    if sides_tree is not None:
        sides_tree.EnsurePath(path)
    space_index = _cell_space_index(spaces)
    out_k = 0
    for lx0, ly0, lx1, ly1, idxs in _borders(
            labels_grid, col_starts, col_sizes, row_starts, row_sizes,
            total_l, space_index):
        side_code = None
        if len(idxs) == 1:
            # Side is always relative to THIS node's own grid edge
            # (same concept _perimeter_sides uses for borderOverrides),
            # determined from the ORIGINAL local coordinates -- before
            # _own_side_of_interior (below) moves lx0/ly0/lx1/ly1 off
            # the exact 0.0/total_w/total_l edge value.
            if lx0 == lx1:
                if lx0 == 0.0:
                    side_code = "W"
                elif lx0 == total_w:
                    side_code = "E"
            elif ly0 == ly1:
                if ly0 == 0.0:
                    side_code = "S"
                elif ly0 == total_l:
                    side_code = "N"
            # A PERIMETER segment only ever has ONE touching space, so
            # there's no "duplicate vs dedupe" decision to make here --
            # just its own edge, trimmed on BOTH the constant axis
            # (position, e.g. the west edge moving inward) AND the
            # range axis (length, e.g. that same west run getting
            # SHORTER too if this space is ALSO offset on its north/
            # south sides) -- the exact same _own_side_of_interior
            # logic the duplicate-interior case below uses, since a
            # space's own edge is a space's own edge either way.
            # Previously only the constant axis was ever adjusted here,
            # leaving a still full-length (untrimmed) run whenever the
            # SAME space was also offset perpendicular to it.
            rx0, ry0, rx1, ry1 = rect_of(spaces[idxs[0]])
            segs = [_own_side_of_interior(
                lx0, ly0, lx1, ly1, rx0, ry0, rx1, ry1,
                space_deltas.get(idxs[0]))]
        else:
            # len(idxs) == 2 -- an INTERIOR segment. Normally both
            # touching spaces' edges still coincide exactly (nothing
            # moved either of them apart), so this stays ONE line,
            # unchanged. Once an INDEPENDENT offset (a ring, or a
            # both-children pair) has actually moved either space's
            # own touching edge, the two no longer agree -- rather
            # than freeze the line at its now-stale original position
            # (which then matches NEITHER cell, see the module
            # docstring's DUPLICATE INTERIOR SEGMENTS section), each
            # space's OWN edge is drawn separately. BOTH still report
            # the SAME [label0, label1] Topology pair below -- there
            # are just two of them now, not a relabelling; a SHARED
            # (track-resize) boundary never reaches this branch at all
            # since it never touches space_deltas (d0 and d1 both
            # None), the tracks themselves already agree by
            # construction.
            i0, i1 = idxs
            d0 = space_deltas.get(i0)
            d1 = space_deltas.get(i1)
            if not d0 and not d1:
                segs = [(lx0, ly0, lx1, ly1)]
            else:
                rx0_0, ry0_0, rx1_0, ry1_0 = rect_of(spaces[i0])
                rx0_1, ry0_1, rx1_1, ry1_1 = rect_of(spaces[i1])
                seg0 = _own_side_of_interior(
                    lx0, ly0, lx1, ly1, rx0_0, ry0_0, rx1_0, ry1_0, d0)
                seg1 = _own_side_of_interior(
                    lx0, ly0, lx1, ly1, rx0_1, ry0_1, rx1_1, ry1_1, d1)
                segs = [seg0] if seg0 == seg1 else [seg0, seg1]

        # WALL LAYOUTS -- does any wallLayout-carrying override match
        # THIS boundary's own topology? See _node_wall_layouts and the
        # module docstring's WALL LAYOUTS section. Phase 1: only a
        # single, non-diverged segment can host one -- a DIVERGED
        # boundary (len(segs) == 2, see DUPLICATE INTERIOR SEGMENTS)
        # is warned and skipped rather than guessed at with a mirrored
        # pair of instances (that's a deliberate, separate follow-up).
        if wall_layouts:
            pair = _border_labels(spaces, idxs)
            for (_wmode, wa, wb, wside, wall_doc) in wall_layouts:
                if not _border_matches(pair, _wmode, wa, wb):
                    continue
                if len(segs) != 1:
                    warnings.append(
                        "{}: wall layout on border {!r} couldn't be "
                        "placed -- this boundary has diverged into {} "
                        "separate edges (see DUPLICATE INTERIOR "
                        "SEGMENTS) -- not supported yet, skipped."
                        .format(name, [wa, wb if _wmode == "pair" else "*"],
                                len(segs)))
                    continue
                # ref_label picks which of this boundary's (at most 2)
                # real spaces the wall's own plane is built from -- for
                # a PAIR, that's deliberately Between[0] (wa) unless IT
                # is 'EXT', in which case the other side must be the
                # real one; a RING's anchor (wa) already IS that real
                # space UNLESS it's an EXT ring, which has no single
                # authored anchor at all, so falls back to whichever of
                # THIS specific boundary's own topology labels isn't
                # 'EXT' -- same fallback the PAIR branch uses, just
                # read from `pair` instead of a `wb` that doesn't exist
                # here.
                if wa != "EXT":
                    ref_label = wa
                elif _wmode == "pair":
                    ref_label = wb
                else:
                    ref_label = pair[0] if pair[0] != "EXT" else pair[1]
                ref_sp = None
                for idx in idxs:
                    if _matches_label(spaces[idx]["label"], [ref_label]):
                        ref_sp = spaces[idx]
                        break
                if ref_sp is None:
                    continue
                rx0, ry0, rx1, ry1 = rect_of(ref_sp)
                edge = _space_edge_at(rx0, ry0, rx1, ry1, lx0, ly0, lx1, ly1)
                if edge is None:
                    continue
                if wside is not None and edge not in wside:
                    continue
                origin_xy, second_xy = _wall_plane_axes(edge, segs[0])
                wall_plane = _upright_plane_from(plane, origin_xy, second_xy)
                wall_len = ((second_xy[0] - origin_xy[0]) ** 2
                            + (second_xy[1] - origin_xy[1]) ** 2) ** 0.5
                wall_doc_resolved = dict(wall_doc)
                wall_doc_resolved["cellWidths"] = [wall_len]
                wall_path = path.AppendElement(wall_k)
                _emit(wall_doc_resolved, wall_len, None, wall_plane,
                      wall_path, cells_tree, labels_tree, borders_tree,
                      topology_tree, warnings, intrinsic_memo,
                      sides_tree=sides_tree)
                wall_k += 1

        for sx0, sy0, sx1, sy1 in segs:
            p0 = plane.PointAt(sx0, sy0, 0.0)
            p1 = plane.PointAt(sx1, sy1, 0.0)
            borders_tree.Add(rg.Line(p0, p1), path)
            if sides_tree is not None:
                sides_tree.Add(side_code, path)
            topo_path = path.AppendElement(out_k)
            topology_tree.EnsurePath(topo_path)
            for lbl in _border_labels(spaces, idxs):
                topology_tree.Add(lbl, topo_path)
            out_k += 1

    return total_w, total_l


def _filter_by_depth(tree, depth):
    """Depth is 0-based; keep only branches whose path length equals
    depth + 1."""
    out = gh.DataTree[object]()
    target_length = depth + 1
    for i in range(tree.Paths.Count):
        path = tree.Paths[i]
        if path.Length == target_length:
            for item in tree.Branches[i]:
                out.Add(item, path)
    return out


# -----------------------------------------------------------------
# SELECTORS -- the two new inputs. See the module docstring.
# _matches_label / _parse_between are shared with the BORDER OVERRIDES
# section above, not redefined here.
# -----------------------------------------------------------------

def _border_matches(pair, mode, a, b):
    """pair: the 2 topology labels for one border segment ('EXT' is
    just another label value here, matches like any other). mode/a/b:
    from _parse_between -- same grammar borderOverrides' own Between
    uses, including comma-separated LABEL LISTS ('m1,m2', no brackets)
    on either side, expanded via _split_labels; _matches_label already
    checks membership against a whole wanted-list (full or base
    label), so a label list just works here with no extra branching.
    Pair matching is order-insensitive, with base-label equivalence on
    each side (see _matches_label).

    'INT' in ring position (['INT', '*']) is a special keyword, NOT a
    real label -- Topology never actually emits 'INT' -- meaning "an
    interior border": both sides are real spaces, neither is 'EXT'.
    It's the mirror of ['EXT', '*'] (every border touching EXT, i.e.
    the whole perimeter regardless of label) and exists because there
    was previously no way to select "everything EXCEPT the perimeter"
    without naming every interior space explicitly. Checked against
    the RAW `a` (before any label-list split) so a real space named
    literally 'INT' (should one ever exist) can't collide with it
    silently -- ['INT','INT']  would fall through to a normal (never-
    matching) pair instead."""
    if mode == "ring" and a == "INT":
        return "EXT" not in pair
    if mode == "global":
        return True
    a_list = _split_labels(a)
    if mode == "ring":
        return _matches_label(pair[0], a_list) or _matches_label(pair[1], a_list)
    b_list = _split_labels(b)
    return ((_matches_label(pair[0], a_list) and _matches_label(pair[1], b_list)) or
            (_matches_label(pair[0], b_list) and _matches_label(pair[1], a_list)))


def _filtered_cells_and_labels(cells_tree, labels_tree, wanted):
    """Keep only cells_tree items whose PARALLEL labels_tree entry (at
    the same path, same index -- see _emit, they're always added in
    lockstep) matches `wanted` -- and return a MATCHING, equally
    filtered labels_tree alongside it, kept in lockstep (same path,
    same kept order) so Labels stays parallel to Cells even once
    Cells itself is being narrowed by this selector, exactly like it
    already does when nothing is filtered at all. A path with no
    labels_tree entry at all (the root's own boundary at Depth 0, when
    it has no 'label' of its own) never matches -- you can't select-
    by-label something with no label."""
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


def _filtered_borders_and_topology(borders_tree, topology_tree, sides_tree,
                                    mode, a, b, side, warnings):
    """Keep only borders_tree items whose matching topology_tree entry
    (the GRAFTED branch path.AppendElement(k), see _emit) satisfies
    _border_matches, AND (if a side filter is given) whose matching
    sides_tree entry (a PARALLEL list, same path/index as borders_tree
    -- see _emit) is one of the requested sides -- and return a
    MATCHING, equally filtered topology_tree alongside it. Topology is
    GRAFTED (one sub-branch per border, not a parallel item list like
    Labels/Cells), so a kept border's own topology entry has to be
    RE-INDEXED to the position it now sits at in the OUTPUT borders
    list (new_k), not its original index (k) -- some earlier borders
    at the same path may have been dropped, which would otherwise
    leave gaps / wrong addresses.

    A segment's own side (N/S/E/W) is only ever set for a PERIMETER
    run (touches exactly one space) -- an INTERIOR segment's side is
    always None, computed once in _emit from the node's own LOCAL grid
    coordinates (rotation-safe, since it happens before the plane
    transform), exactly the same grid-edge concept borderOverrides'
    own side filter already uses (_perimeter_sides). This means side
    filtering naturally only ever narrows an EXT-anchored or real-
    label-ring match (the only matches that can ever land on a
    perimeter segment to begin with) -- no per-mode special-casing
    needed for THOSE, EXCEPT:
      - 'INT': an INT match is BY DEFINITION only ever interior
        segments (side always None), so a side filter combined with
        INT would silently keep nothing -- warned and the filter
        dropped instead (INT+side has no borderOverrides precedent to
        mirror, unlike EXT/ring, so failing loud beats a silently
        empty result).
      - a PLAIN PAIR where NEITHER side is 'EXT' (both real spaces --
        the shared/both-children Offset mechanisms' own territory):
        borderOverrides itself NEVER references `side` for this case
        (_dumb_offset_for_space's pair branch only reads `side` inside
        its `other == 'EXT'` check), so a side filter here is simply
        BYPASSED (matches regardless of side), not applied -- applying
        it naively would silently exclude EVERY match, since an
        interior segment's own stored side is always None and can
        never be 'in' a requested set."""
    effective_side = side
    if mode == "ring" and a == "INT" and side is not None:
        warnings.append(
            "Borders selector: a side filter has no effect on an INT "
            "match -- an interior border isn't 'on' any single grid "
            "edge -- ignored.")
        effective_side = None
    elif (mode == "pair" and side is not None
          and "EXT" not in _split_labels(a) and "EXT" not in _split_labels(b)):
        effective_side = None
    borders_out = gh.DataTree[object]()
    topology_out = gh.DataTree[object]()
    for i in range(borders_tree.Paths.Count):
        path = borders_tree.Paths[i]
        items = borders_tree.Branches[i]
        seg_sides = sides_tree.Branch(path) or []
        borders_out.EnsurePath(path)
        new_k = 0
        for k, item in enumerate(items):
            pair = topology_tree.Branch(path.AppendElement(k)) or []
            if len(pair) != 2 or not _border_matches(pair, mode, a, b):
                continue
            if effective_side is not None:
                seg_side = seg_sides[k] if k < len(seg_sides) else None
                if seg_side not in effective_side:
                    continue
            borders_out.Add(item, path)
            topo_path = path.AppendElement(new_k)
            topology_out.EnsurePath(topo_path)
            for lbl in pair:
                topology_out.Add(lbl, topo_path)
            new_k += 1
    return borders_out, topology_out


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
        g["Borders"] = None
        g["Topology"] = None
        return

    # Geom.Plane is a TRANSFORM, not a replacement: each item's own
    # plane (its JSON's 'plane' field if Boundary set one, else
    # WorldXY) is carried through PlaneToPlane(WorldXY, Geom.Plane).
    # Unwired (WorldXY, the default) is the identity transform, so an
    # item keeps exactly the plane it already has -- a single item
    # with no baked-in plane still resolves at WorldXY, unchanged from
    # before. Wired, it repositions every item together as one rigid
    # unit without disturbing their placement relative to each other.
    plane_in = goo_value(g.get("Plane"))
    geom_plane = plane_in if isinstance(plane_in, rg.Plane) else rg.Plane.WorldXY
    xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, geom_plane)

    cells_tree = gh.DataTree[object]()
    labels_tree = gh.DataTree[object]()
    borders_tree = gh.DataTree[object]()
    topology_tree = gh.DataTree[object]()
    sides_tree = gh.DataTree[object]()   # internal only -- Borders selector's side filter, never a component output
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
        total_w, total_l = _emit(
            root, None, None, item_plane, root_path.AppendElement(0),
            cells_tree, labels_tree, borders_tree, topology_tree,
            item_warnings, intrinsic_memo, sides_tree=sides_tree)

        cells_tree.Add(
            _rect_curve(item_plane, 0.0, 0.0, total_w, total_l), root_path)
        root_label = root.get("label")
        root_label_or_blank = (
            root_label if isinstance(root_label, string_types) and root_label
            else "")
        # _rect_border_lines' own corner order (x0,y0)->(x1,y0)->
        # (x1,y1)->(x0,y1)->back is fixed, so its 4 segments are always
        # S, E, N, W in that order -- see its own docstring.
        for k, (ln, side_code) in enumerate(zip(
                _rect_border_lines(item_plane, 0.0, 0.0, total_w, total_l),
                ("S", "E", "N", "W"))):
            borders_tree.Add(ln, root_path)
            sides_tree.Add(side_code, root_path)
            topo_path = root_path.AppendElement(k)
            topology_tree.EnsurePath(topo_path)
            topology_tree.Add(root_label_or_blank, topo_path)
            topology_tree.Add("EXT", topo_path)
        if isinstance(root_label, string_types) and root_label:
            labels_tree.Add(root_label, root_path)

        for w in item_warnings:
            warnings.append("item {}: {}".format(i, w) if many else w)

    depth_in = goo_value(g.get("Depth"))
    try:
        depth = int(depth_in) if depth_in is not None else 0
    except (TypeError, ValueError):
        warnings.append("Depth {!r} isn't an integer -- showing depth 0 "
                         "(the top parent).".format(depth_in))
        depth = 0
    if depth < 0:
        warnings.append(
            "Depth {} must be >= 0 (0 = the top parent's own boundary) "
            "-- showing depth 0 instead.".format(depth))
        depth = 0

    max_depth = max((p.Length for p in cells_tree.Paths), default=1) - 1
    if depth > max_depth:
        warnings.append(
            "Depth {} is deeper than this tree goes (max {}) -- nothing "
            "to show at that depth.".format(depth, max_depth))

    cells_tree = _filter_by_depth(cells_tree, depth)
    labels_tree = _filter_by_depth(labels_tree, depth)
    borders_tree = _filter_by_depth(borders_tree, depth)
    topology_tree = _filter_by_depth(topology_tree, depth + 1)
    sides_tree = _filter_by_depth(sides_tree, depth)   # parallel to borders_tree, not grafted -- same depth, no +1

    # Selectors run AFTER Depth filtering -- only candidates already
    # inside the chosen Depth slice can ever be selected. Labels/
    # Topology are kept in lockstep with Cells/Borders throughout (see
    # _filtered_cells_and_labels / _filtered_borders_and_topology).
    # Either selector's own label(s) may be a comma-separated LIST
    # ('a,b', no brackets) -- same _split_labels grammar borderOverrides
    # uses -- expanded here for Cells; _border_matches does its own
    # expansion internally for Borders.
    cells_wanted_raw = [goo_value(v) for v in (g.get("Cells") or [])]
    cells_wanted = []
    for v in cells_wanted_raw:
        if isinstance(v, string_types) and v:
            cells_wanted.extend(_split_labels(v))
    if cells_wanted:
        cells_tree, labels_tree = _filtered_cells_and_labels(
            cells_tree, labels_tree, cells_wanted)

    between_in = [goo_value(v) for v in (g.get("Borders") or [])]
    between = _parse_between(between_in, warnings)
    if between is not None:
        mode, a, b, side = between
        borders_tree, topology_tree = _filtered_borders_and_topology(
            borders_tree, topology_tree, sides_tree, mode, a, b, side, warnings)

    g["Cells"] = cells_tree
    g["Labels"] = labels_tree
    g["Borders"] = borders_tree
    g["Topology"] = topology_tree

    if warnings:
        seen = set()
        unique = []
        for w in warnings:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        component.AddRuntimeMessage(
            gh.Kernel.GH_RuntimeMessageLevel.Warning, "\n".join(unique))


if _HAS_GH:
    run()
