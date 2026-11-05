# SYSARCH — Trunky v0.7

Trunky v0.7 is an append-only statement store kept as plain files: every fact is one row,
`handle, attribute, entity, value, value_type`, read as *`handle` says `attribute` of `entity` is `value`*,
and the rows are split into **statement sets**, one CSV file per set. Around the files sit a few Python
programs: a view that computes the current statements, a checker, an engine that runs **Systems**
(automations defined as statements), and a browser explorer that can also append statements. Nothing is ever updated or deleted; every change is a new row. v0.6 (the git history
before this version) kept the same rows in one SQLite table behind an HTTP API.

## Statement sets

- `sets/<set uuid>.csv`: one file per set, with a header row and the five columns above. `value_type` is
  `uuid` for a reference to an item and otherwise a literal type (`str`, `int`, `float`).
- **registry** (`1282694a…`): what each set is: a StatementSet item per set, with theName and theIntention.
- **permissions** (`748ce9b6…`): groups (`owner`, `everyone`, …) with `aMember`, and `aReaderGroup` /
  `anEditorGroup` on each set.
- A set is the unit of sharing: this repository includes only the sets whose aReaderGroup is `everyone`.
  registry and permissions stay local, since they name every set, private ones included. `.gitignore` is an
  allowlist, so any other set stays local until added on purpose. Without the permissions set, the explorer
  shows every set file present.
- Which set a statement belongs in is a judgment about who should read it; `hold` exists for statements whose
  home isn't decided yet.

## The current view

`tools/ecs/view.py` loads every set file and computes the **current** statements: all rows minus those named
by an `aReplacement` (the old handle or item is the entity), those named by `anErratum`, those whose
`theRemovalTime` has passed, and rows with an empty value. It also builds an RDF graph (rdflib) of the current
statements, one triple `<urn:uuid:entity> <urn:uuid:attribute> value` per row, so Systems can select rows with
SPARQL. Everything that reads Trunky goes through this view.

## Writing

Any writer appends rows to a set's file while holding the lock in `tools/trunky_lock.py` (an flock on
`state/trunky-write.lock`), so the engine, the sync and one-off scripts never interleave rows. By convention
each batch carries provenance: a ProvenanceInfo item with `aNote` (who and why) and `theRecordedTime`, linked
from each new statement by `theProvenance`. To change a value, write the new statement and
`aReplacement of <old handle> is <new handle>`; to retract one with no successor, `anErratum`.

## Checks

`tools/check.py` reports problems without fixing them (exit status 1 on any ERROR): definitions less visible
than their uses, statements about statements more visible than what they describe, registry completeness,
unresolved UUID references, missing required slots, items with several names, provenance coverage, and
Systems with both or neither kind of input. Slot declarations (`aRequiredSlot`, `aDesirableSlot`,
`anOptionalSlot` of a component) are only ever checked here, never at write time.
`tools/set_dag.py` draws which sets depend on which (A → B when A uses an item B defines) and lists cycles.

## The ECS engine and Systems

Items carry components (`aComponent of <item> is <component>`), and a **System** is an item that acts on
items: its statements give its input (`theQuery`, SPARQL over the current view, run once per result row; or
`theSource`, something outside Trunky that it reads as a whole), its actor (`Code` or `Claude`),
`theInstructions` (for Code, `path/to/file.py:function`), `theRunStatus` (draft, active, paused) and
`theRunInterval` (an ISO 8601 duration).

`tools/ecs/engine.py` runs one pass: build the view, evaluate each active System that is due, act on each
row, write the results (each with provenance naming the System) to the home set of the entity they describe,
and repeat while a round wrote something (at most 10 rounds). On the owner's machine a systemd timer runs a
pass every minute. A failing System files a task for the owner and backs off (1, 4, 16, … minutes, up to a
day). Claude Systems (`tools/ecs/claude_actor.py`) hand each item to a headless Claude run; Claude proposes,
and code checks its output and writes only what passes. `tools/set_run_status.py` switches a System between
draft, active and paused.

The Systems' code is in `tools/systems/`: fetching paper metadata from a DOI, screening candidate papers for a
review, and mirroring calendar feeds and classifying their events. The System items themselves live in the sets they work
on, most of which are private, so a fresh clone has the code but none of the owner's Systems.

## The explorer

`explorer/server.py` (Python standard library) serves `explorer/static/index.html`, a single page with no
build step. It sends a viewer the current statements of the sets they may read, and the page shows tables of
items by component, item pages (statements, references, empty slots, statements about statements), and open
Questions highlighted on Commitment-like views. It also appends statements: replies to questions, edits
(the new value plus an aReplacement), values for empty slots, new items with a component, and extra
components. Every write is checked against the set's anEditorGroup and carries provenance. With `--public` it
serves only the sets everyone may read and accepts no writes. Details in `explorer/README.md`.

## Configuration and secrets

- `trunky.conf` (local; `trunky.conf.example` lists the settings): `owner`, the person item the explorer
  acts as (without it the explorer is read-only); `published`, exported files that `check.py` verifies against
  the sets (`tools/export.py` writes them); `tasks_dir`, where the engine files notes; `env_file`; `claude`.
- Secrets (API keys, private calendar feed URLs) are read at run time from `env_file`, outside the
  repository; Systems name the variable they need, never the value.
- Runtime state (engine timings, sync bases, the write lock) is in `state/`, which is not committed.

## Dependencies

Python 3.11+, with `rdflib` (the view's SPARQL), `python-dateutil` (calendar recurrence) and `PyYAML` (note
front matter); see `requirements.txt`. The explorer server needs only the standard library plus the view.

## Known gaps

- No login: the explorer treats every request as the owner's (see INTENT.md).
- No protocol for exchanging statements between instances; sharing is publishing set files.
- `check.py` assumes the owner's full instance: on a clone with only the public sets, the missing registry,
  the published export path and references into private sets are reported as problems.
- The explorer sends all readable statements in one response (several MB for a full instance), which is slow
  over cellular; loading per view is planned.
