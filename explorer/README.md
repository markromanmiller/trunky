# Trunky Explorer

A browser for the current statements. The table view is built (2026-10-16); the other views are planned.

## To do: further views (Mark, 2026-10-16)
- Sets DAG: the set dependency graph from tools/set_dag.py (proposals/set-dependency-graph.md), interactive,
  with its findings (cycles, arrows into narrower sets, undefined UUIDs) shown on the graph.
- Statement graph: a force-directed (or similar) layout of items and their links, for understanding messier
  statement sets.
- System view: a node-based view of the ECS Systems, what each reads and writes and how they connect, for
  designing Systems. Parked 2026-10-17 on the question of how the System ontology maps to the ~/dataflow
  diagram conventions (dataflow-diagram-rules.md). Early generic sketches: static/mockups/system-view.html.

## Server
- `server.py` serves `static/` and `/api/data`: the sets the viewer can read and their current statements
  (tools/ecs/view.py `current()`: replacements, errata, removal times and empty values applied). It reloads
  when a set file changes. Only readable sets are sent: a set is readable when its aReaderGroup is everyone
  or a group the viewer is aMember of.
- Without the permissions set (a clone of the public repository), every set file present is readable and
  none is editable.
- The viewer is always the owner for now, because the page is served only on the tailnet. A login front
  door (Authelia) would set the viewer from its user header in `viewer()`.
- Runs as the user service `trunky-explorer.service` on 127.0.0.1:8850, published on the tailnet with
  `tailscale serve --bg --https=8443 http://127.0.0.1:8850` at https://<machine>.<tailnet>.ts.net:8443/
  (undo: `tailscale serve --https=8443 off`).

## Table view
Pick a set (or all readable sets) and a component; its items are the rows. Columns are the attributes those
items use, most used first; the first five show, and the rest appear as chips that add a column. Shown
columns are remembered per component in the browser. Clicking a name opens the item: its statements with
their sets, statements about each statement, and what refers to it. The URL hash (`#s=&c=&i=`) holds the
set, component and item, so views can be bookmarked. The search box filters the table and finds any item
by name or UUID prefix.

## Views by component and questions (2026-10-28)
A component can have its own view settings (`VIEWS` in static/index.html); others get `DEFAULT_VIEW`. The one
setting so far is `questions`: whether open Questions on the table's statements are highlighted from the start.
It is on for Commitment and off elsewhere, where a note above the table says how many items have open questions
and a button shows them (remembered per component). A highlighted cell is a statement whose handle carries
Question and whose theQuestionStatus is not answered; with questions on, columns holding one are shown unless
the viewer hid that column with its × (remembered per component as `hid:<component>`; its More chip stays
yellow). On a phone, where the item panel covers the table, a link from the panel to a component's table closes
the panel. Hovering (or tapping) the cell shows the question, who asked whom, the reply thread and a reply box.
A reply is POSTed to /api/reply (server.py `write_reply`): "aReply of <the Question or the reply it answers>"
plus "aToDo of <the Question>", in the Question's set, with provenance naming the viewer. The public instance
has no reply box and refuses the POST.

## Editing values (2026-11-02)
On the item panel, each value in a set the viewer may edit (the set's anEditorGroup) has a ✎. Saving
POSTs /api/edit {handle, text} (server.py `write_edit`), which appends the new statement and "aReplacement of
<old handle> is <new handle>" to the old statement's set, with the same provenance as replies. Nothing is
erased. A value replaced since the page loaded is refused, and so are empty or unchanged entries. Values the Paug sync tracks (GET /api/synced, from
state/paug-sync-base.json) show a warning: the edit stays in Trunky, the Obsidian note keeps its old value, and
the sync reports the difference as "Trunky -> vault (stage 3)".

The item panel also lists "Empty slots": required, desirable and optional slots of the item's components that
it has no value for. A text slot has an Add button (POST /api/add, server.py `write_add`), which writes the
value into the set holding that aComponent statement.

Entries are always text (no value-type checks, by design): an entry that is exactly {{<uuid>}} is stored as a
link to that item, and an entry starting with '{{ stores the rest as text, so '{{x}} stores {{x}}. The edit box
shows links as {{uuid}} and text starting with {{ with the ' in front, so saving unchanged round-trips. Saving
a number writes it as str.

## New items (2026-11-03)
Above the table, "+ New <component>" opens a name box and a set picker. Create POSTs /api/new (server.py
`write_new`), which makes a new UUID with "aComponent of <it> is <the table's component>" and theName, in the
chosen set, then the page opens the new item, whose required slots are listed under Empty slots. The suggested
set is the selected set if the viewer may edit it, else the one last used for that component (localStorage
`newset:<component>`), else the editable set holding most of that component's items.

On the item panel, "+ Component" (after the component chips) opens a search box. With nothing typed it
suggests the components most often found on items that share this item's components (for an Engagement, its
kinds); typing filters all components by name, and Enter takes the first. Choosing one POSTs /api/component
(server.py `write_component`), which writes aComponent to the set of one of the item's aComponent statements,
else its theName. The new component's slots then appear under Empty slots.

## Table editing, column order, and writes without reloading (2026-11-03)
- Columns: each header has ‹ › to move it (and can be dragged on a desktop); the order is saved per component
  with the column choice (`cols:<component>`).
- "Edit cells" beside "+ New" turns on edit mode: tapping a value cell opens a box per value (Save = /api/edit)
  or, for an empty cell, one box (Add = /api/add). Any visible column can take a value in an empty cell, since
  /api/add accepts any attribute some current statement uses, not only declared slots. Links and question
  panels yield to the editor while edit mode is on.
- Every write answers with the rows it appended; the page adds them to its copy (dropping what an aReplacement
  replaces) and redraws, instead of downloading all statements again.

## Public instance (2026-10-17 to 2026-10-31)

`https://trunky.dev.markromanmiller.com/` serves only the sets whose aReaderGroup is everyone
(`server.py 8851 --public`: anonymous viewer, no static files besides the page). It is the user service
`trunky-explorer-public.service`, behind the Caddy route `trunky.dev.markromanmiller.com` -> `localhost:8851`
in `~/union-station/caddy.json`. The timer `trunky-explorer-public-stop.timer` stops and disables the service on
2026-10-31 12:00; the Caddy route then returns 502 until it is removed.
