# ECS engine: design (2026-10-11)

Processes (first: the PCD Colloquium speaker flow, `-Inbox/PCD Colloquium Speaker Flow.canvas`) are
defined in Trunky as Systems, in the Entity-Component-System sense. Trunky already has entities (UUIDs)
and components (aComponent plus slot definitions); a System adds, removes and changes components on items
as defined in its instructions. Schema: set `ecs-system-schema` (60d68d71-cf77-4bbb-b91f-63a5480f1dbb,
private), written by `tools/add_ecs_system_schema.py`.

Data-flow diagram of the engine as built (2026-10-12): `tools/ecs/diagram/trunky-ecs.pdf` (source `trunky-ecs.tex`).

## System
- theActor: a Person UUID, 'Claude', 'Code', or a role string. External actors (e.g. a potential speaker)
  have no System; their actions arrive as data that a Code System imports.
- theInstructions: plain-language instructions for a person or AI; a function reference for Code.
- theQuery: SPARQL over the current statements. Each result row is one item to act on. A System excludes
  items it has already handled, usually by requiring that its output is still absent (idempotent).
  Time conditions (e.g. "3 weeks before each session") are written in the query with NOW(); there is no
  Clock actor.
- theSource (2026-10-19): the alternative to theQuery, for a System that imports from outside Trunky
  (a folder of notes, a feed). Its value is an item describing the source (e.g. an ObsidianVault with
  theFolderPath). Such a System runs once per source per evaluation, with the row {"source": <uuid>},
  and finds what is new by reading the source, which Trunky cannot list in advance. A System has exactly
  one of theQuery and theSource (check.py check 10). A query that only returns the System itself (or
  another fixed item) to get a single run is a sign the System should use theSource instead.
- theRunStatus: draft / active / paused. Only active Systems run.
- aWrittenAttribute: declared outputs, for drawing and checking.
- theProcess: the process entity; a process is the set of Systems that name it.
- theRunInterval: minimum time between evaluations, ISO 8601 duration. Absent: every pass.

Branches are the EnumeratedOptions of a single-valued attribute a System writes (e.g. theSpeakerStatus:
willing / unwilling / unclear), so exactly one branch is taken by construction. A branch that nothing
consumes yet is a legitimate end state (e.g. an unclear reply left in Mark's inbox).

## Pass
1. Build the current view once: drop replaced rows, errata'd statements/entities, "" values; apply
   permissions. Load into rdflib.
2. Evaluate every active System whose interval allows it; act on each result row.
   - Code: call the function.
   - Claude: create a Paug task (claude-go or claude-stop). Mark: create a `next` task.
3. If any Code System wrote statements, rebuild the view and evaluate again until a round writes nothing
   (cap: 10 rounds).

Last-evaluated time per System is kept in `state/ecs-engine.json` ("last_run"); theRunInterval is honoured
since 2026-10-16. A result may name the set for its statements ("set"), which new items need.

## Triggers
- systemd user timer, every minute.
- Later, once there is a single Trunky writer: a pass right after each write.

## Lock
Every Trunky writer takes `tools/trunky_lock.py` `write_lock()` (flock on `state/trunky-write.lock`), so
two passes, or a pass and a Paug sync, never run at the same time. A pass that finds the lock held exits
and the next timer tick tries again. `paug_sync.py` uses it since 2026-10-11.

## Later
- Per-group views, a Datalog query dialect evaluated in SQL, and verifying its compiler: parked design
  note `proposals/query-dialect-design.md` (2026-10-12).
- Modules: a System whose instructions are another process.
- The Paug sync's rules (vault -> Trunky, colour -> done, cold storage on P1D) can become Systems in the
  same engine.
