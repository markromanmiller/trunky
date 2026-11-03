*Written 2026-09-14, based on an interview. Updated 2026-11-03 for v0.7, where the store became one CSV file per statement set.*

## Linguistic statements instead of a formal ontology

The system uses natural-language `theIntention` strings to ground its own schema rather than a formally typed predicate/object distinction (RDF/OWL-style). This isn't a rejection of rigor for its own sake — it's a match to the actual conditions the system is meant to operate under: small data, ontologies that change as understanding improves. Under those conditions, forcing every concept to have one singular, formally agreed meaning is disproportionately expensive — the amount of upfront specification work needed to make a term unambiguous doesn't pay for itself when the term itself is still likely to be revised. A natural-language `theIntention` is cheap to write, cheap to revise, and an LLM can work with the resulting ambiguity well enough that a human (or agent) doesn't need to resolve it fully before using the data. The tradeoff — some genuine ambiguity in how a concept could be reinterpreted — is accepted deliberately, not overlooked.

## Why slot declarations are advisory, not enforced

`aRequiredSlot`/`aDesirableSlot`/`anOptionalSlot` describe a component's expected shape, but nothing checks them before a write is accepted — `tools/check.py` exists as a separate, opt-in pass instead (in v0.6, `validate.py`). This is a deliberate split of responsibility: enforcement is a reader's job, not a writer's. The store's only real obligation is to never refuse a true statement. Pushing shape validation into the write path would mean the store itself has to decide whether an incomplete entity is invalid — but incompleteness isn't the same as falsehood, and a component's declared shape is itself just more data that can be wrong or incomplete at any given moment. Keeping validation downstream and optional means the schema can evolve (new required slots added later, existing entities temporarily out of sync with them) without the store ever being in a position to reject something true just because it doesn't yet look complete.

## Why chain-walking instead of timestamps

No row in the store carries a timestamp; recency of a fact is only ever recoverable by following an `aReplacement` chain forward. (In v0.7 a write's provenance may say when it was recorded, `theRecordedTime`, and `theRemovalTime` can retire a statement at a given time; both are statements about statements, and neither decides which of two values is current.) This is a deliberate substitution, not an omission: wall-clock time can be wrong or misleading in ways that don't matter to the actual question being asked, which is "what superseded what." A timestamp records when something was *written*, which can diverge from backdated entries, batch imports, or clock skew across sources — none of which change what the correct current answer is. The replacement chain instead records the thing that's actually load-bearing: the causal/logical sequence of which fact replaced which. Time-of-write was judged less honest than that chain for the purpose the store needs it for, so it was left out entirely rather than added as "yet another attribute" alongside it.

## Why every identifier is a full UUID

Attributes, entities, and values in this store are minted as UUIDs specifically to allow decentralized minting without coordination. Because any client — a script, an agent, a human at the explorer — can create a new concept at any time, and because the model requires that any UUID be usable interchangeably as an attribute, an entity, or a value, there's no room for a centrally-issued sequential ID scheme: two independent writers minting IDs at the same time must never collide, and nothing in the architecture wants a shared counter or registry standing in the way of that. A UUID space sidesteps the coordination problem entirely, at the cost of the identifiers being opaque and unwieldy compared to sequential IDs.

## Why the semantic index runs locally (v0.6)

*v0.7 has no semantic index yet; this is why v0.6's was local, and would apply again.*


`vectors.db` is built with a local `sentence-transformers` model (`all-MiniLM-L6-v2`, CPU) rather than a hosted embeddings API, for two compounding reasons: keeping `theIntention` text from leaving the machine at all (even to an embeddings-only endpoint), and avoiding a live network dependency and per-call billing for a component that's meant to "just work" offline. Both considerations independently pointed at the same answer, so neither had to dominate — a hosted API was never seriously in the running once either concern was in view.

## Why one flat shape, not one table per component

The entire store is one shape of row (in v0.6 a single `statements` table; in v0.7 the same rows split across files by statement set) rather than a normalized schema with one table per component (a `people` table, an `assignments` table, etc.). This was never really a live decision between alternatives — the additive-only, self-describing goals implied a single uniform table from the very start of the design (see `concept.md` in v0.6), and a per-component relational design wasn't seriously evaluated as a competing option. The flat shape is the direct consequence of wanting every fact, including facts about the schema itself, to be expressible the same way.

## Why one CSV file per statement set (v0.7)

v0.7 moved from one SQLite database to plain CSV files, one per statement set. The motivation is sharing: a set is the unit that gets published or kept private, and as a file it can be committed to git or left out on its own. This repository holds the sets anyone may read; the private ones (students, calendar, tasks) stay on the owner's machine, beside the same code. Which sets are readable by whom is recorded as statements too (`aReaderGroup`, `anEditorGroup`), so the public/private split lives in the data rather than in the storage layer.

## Why values carry no type checks

Each row has a `value_type` (a UUID reference, or a literal string or number), but nothing checks that an attribute's values are all of one type. Value-type safety is not something this system cares about by default: in practice some uses of an attribute hold text and others hold references, and that is allowed. The explorer reflects this: every value is entered as text, and an entry written as `{{<uuid>}}` is stored as a reference to that item.

## Why access control is data, but login is not built yet

v0.6's `api_server.py` did no authentication of its own; it assumed a reverse proxy (Caddy) enforced HTTP Basic Auth, which was simply the least work that covered one person being the only user. v0.7 records who may read and edit each statement set as statements (groups with `aMember`, and `aReaderGroup`/`anEditorGroup` on each set), and the explorer only sends the sets a viewer may read and refuses writes outside the sets they may edit. What is still missing is identity: the explorer treats every request as the owner's, which is true while it is reached only over the owner's private network, and serves a read-only public view otherwise. Per-user login (magic link or WebAuthn, then sessions) is still the planned next step, and the permissions it would enforce are already in place.
