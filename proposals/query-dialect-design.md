# Query dialect, SQL backend, and per-group views: design note (2026-10-12)

Status: parked. Mark, 2026-10-12: looks good at a first scan, but the details have not been considered.
Nothing here is built.

## Where things stand
- Each System's theQuery is raw SPARQL with full `<urn:uuid:...>` IRIs. `tools/ecs/view.py` loads every set
  CSV, drops replaced / errata'd / removed / ""-valued rows in Python, builds an rdflib graph
  (`<entity> <attribute> value`; the handle is not kept), and rdflib parses and evaluates the query.
- The engine runs as the owner: permissions filter nothing. Every System sees every set.
- Permissions exist as data and are enforced elsewhere: each set has aReaderGroup statements (2026-10-12:
  21 sets; 16,493 statements readable by everyone, 12,248 owner only, 446 iit-faculty). `tools/check.py`
  checks visibility closure and that the published file holds only public rows; `tools/export.py` refuses
  non-public sets.
- `tools/bench_duckdb.py` (2026-10-10) benchmarked DuckDB 1.5.3 over the set CSVs; nothing uses it yet.
  DuckDB is not in the engine's `.venv`.

## 1. Per-group views
- `View(groups)` loads only the sets whose readers include one of the groups (or everyone).
- A System gets one new attribute naming the group it reads as; absent means owner.
- The engine builds one view per group in use, not one per System.
- Meta-statements follow the reader: a view applies only the aReplacement, anErratum and theRemovalTime
  statements it can itself read. A public view may therefore show a row that is corrected privately; that
  is what an outside reader would see.
- No write-down: a System must not write into a set readable by more groups than the narrowest set it
  read from. `check.py` can enforce this from aWrittenAttribute and the target set.

## 2. Statements about statements
- Trunky handles correspond to reifiers in RDF 1.2 / SPARQL 1.2 (`:s :p :o ~ :h {| ... |}`).
- The current view discards handles, so queries cannot reach meta-statements. Under the SQL backend this
  goes away: the handle is a column.

## 3. Query language: Datomic-style Datalog with a handle position
- Data pattern: `[entity attribute value handle]`; trailing positions may be omitted. Variables start
  with `?`; `_` is a wildcard; shared variables join.
- Keep: `:find`, `:where`, `:in`; data patterns; `not` / `not-join`; `or` / `or-join`; comparison
  predicates and now; aggregates; rules (incl. recursive). Drop: `pull`, return maps, multiple `$`
  sources.
- Identifiers (decided, Mark 2026-10-12): every reference is either a full UUID or `{xxxx:name}`
  (first four hex characters plus the name). No bare names. On 2026-10-12 all 1,291 named items had a
  unique (prefix, name) pair; the compiler must still reject a reference that matches more than one item.
- Example (prefixes illustrative):
  ```
  [:find ?s ?t
   :where [?s {xxxx:theRunStatus} "active" ?h]
          [?h {xxxx:aProvenance} ?p]
          [?p {xxxx:theRecordedTime} ?t]]
  ```
- Motivation: models already write Datomic/DataScript/XTDB queries well, so a one-page dialect card plus
  examples in context should suffice; each System's theQuery becomes an example. Pair with a parser that
  gives clear errors so a model can retry.

## 4. Evaluation in SQL (decided direction, Mark 2026-10-12)
- Backend: DuckDB over the set CSVs (`read_csv('sets/*.csv', filename=true)` tags each row with its set),
  rebuilt each pass; the CSVs stay the only source of truth.
- Pipeline: parse -> resolve identifiers -> desugar to a core language -> generate SQL -> run in DuckDB.
- Each data pattern is one alias of `statements(handle, attribute, entity, value, value_type)`; shared
  variables become join conditions. Example:
  ```sql
  SELECT DISTINCT s1.entity
  FROM statements s1 JOIN statements s2 ON s2.entity = s1.handle
  WHERE s1.attribute = '<uuid>' AND s1.value = 'active' AND s2.attribute = '<uuid>';
  ```
- The current-view filtering (replacement, erratum, removal time, permissions) is written as rules in the
  dialect, replacing the Python filtering in `view.py`.

## 5. Verifying the compiler (layers, cheapest first)
1. Make it verifiable: a small core language; a fixed SQL output subset (`SELECT DISTINCT`, joins,
   `NOT EXISTS`, `UNION`, `WITH RECURSIVE`; no `NOT IN`, outer joins or NULLs) so bag semantics and
   three-valued logic cannot diverge from Datalog's set semantics.
2. A specification: a small reference interpreter for the core language; identifier resolution as a
   separate step with its own properties (no names survive; exactly one match or rejection).
3. Checking short of proof: property-based differential testing (Hypothesis: random small tables and
   queries, compiled SQL in DuckDB vs. the reference interpreter); translation validation of each System's
   query (research tools: Cosette / HoTTSQL, QED, SQLSolver, VeriEQL).
4. Full proof, if warranted: core semantics and compiler in Lean 4 or Coq/Rocq, proving compiled-SQL
   semantics equal Datalog semantics for all queries and tables (prior work: Datacert; Benzaken and
   Contejean's Coq SQL semantics; CompCert as the model). Trusted base: parser, DuckDB, and the match
   between the formal SQL semantics and DuckDB's behaviour (kept honest by the layer-3 tests).

Suggested starting point when resumed: layers 1-3 together with per-group views.
