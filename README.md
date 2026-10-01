# Trunky

Trunky is a language-based relational data model consisting of a set of statements with interpretation 
`{statement-id}: {attribute} of {entity} is {value}`. The rest is data and social convention.

## Why another data format?
Trunky is built to be a synthesis of *algebraic* and *linguistic* perspectives on knowledge.

On the *algebraic* side, relational databases are quite nice because they are machine-readable and easy to query on modern hardware. You can get answers to well-formed questions like "a list of all the employes who live in Trenton and know Spanish,"[^bush] or "What needs to move in my weekly meeting schedule for this one-off appointment on Tuesday at 1:45PM?" or "What publicly released datasets have sub-session psychological labels as well as motion capture data?" The cost is determining the schemata and collecting all answers up front. And furthermore, this work is never completed as needs change and new distinctions need making.[^shipman]

[^bush]: Vannevar Bush, ["As We May Think"](https://archive.org/details/Vannevar_Bush_As_We_May_Think_Atlantic_Monthly_1945-07), *The Atlantic*, July 1945.
[^shipman]: Frank M. Shipman & Catherine C. Marshall, ["Formality Considered Harmful: Experiences, Emerging Themes, and Directions on the Use of Formal Representations in Interactive Systems"](https://link.springer.com/article/10.1023/A:1008716330212), *Computer Supported Cooperative Work* 8 (1999): 333–352.

Unstructured data - largely, text - foregoes this kind of pre-processing and postpones giving up the productive ambiguity a schema would force you to resolve, in favor of string searches, word embeddings, or (in recent years) direct ingestion of documents by large language models. The costs then are querying (if using an LLM to parse for every answer) and the algebraic guarantees. Agents also are playing a game of telephone when writing for each other.

Trunky was created to be the missing data model that interpolates along this spectrum. It has just enough constraints to meaningfully support *relational structures*, the general algebraic form of databases, but avoids any other constraints on language as much as possible. 

A solid analog for Trunky is [gradual typing](https://en.wikipedia.org/wiki/Gradual_typing) but for statements (claims, knowledge, data).

A short collection of benefits are:
- Metadata is just more rows of the same type as data.
- Comments on data or statements are just more rows.
- Authorship is just more rows.
- Validation is just more rows.
- Different users (and different agents) can operate with overlapping dataset and share a few, most, or all items.
- Data and its formalization can be done gradually, iteratively, and divergently.

## An example

The first domain I wanted something like Trunky was for describing and searching for research papers. Suppose I have a simple fact I want to record: a paper had a sample size of 24 participants. Using the statement format, it’s reasonable to write that fact:

`theSampleSize` of `thisPaper` is 24

This is fairly good at capturing what I mean, but there are minor modifications to make it a real Trunky statement. In Trunky, *items* (the generalization of statement, attribute, entity, and non-literal values) are unique identifiers and *nothing else.* Therefore, our two items, i.e. this `theSampleSize` idea and the `thisPaper` we were discussing, actually have UUIDs. The statement itself has one as well. The Trunky statement is then

`{db410166-51f4-4703-89d0-dd471978c8fb}`: `{bb2bcedd-f505-4701-8fa9-104409361b8f}` of `{2dcc3e3c-62ac-4626-bd8d-a940f78ec17f}` is 24

### Names and Intentions

While this statement format is technically correct, it is rather unusable. Specifically, interpretation is impossible because the identifier is completely opaque. The way we were able to interpret it before was by its *name*-  so let’s add that piece of information as a statement, in roughly the shape `theName` of `thisPaper` is “thisPaper”:

`{ea0c1ada-9057-427b-a077-4ce075954b60}`: `{acf5cebb-8d80-45ad-9a1f-a3dd48682ef6}` of `{2dcc3e3c-62ac-4626-bd8d-a940f78ec17f}` is thisPaper

At first, it seems like this doesn’t solve our problem. We still have two unnamed items, same as before. However, *items can have any role,* which means it’s not inappropriate to write:

`{bae3d3d2-1f4a-4204-9d0b-eb3a459efc2d}`: `{acf5cebb-8d80-45ad-9a1f-a3dd48682ef6}` of `{acf5cebb-8d80-45ad-9a1f-a3dd48682ef6}` is theName

For this and following statements, I’ll be using a readable shorthand leveraging naming while still indicating items don’t (and shouldn’t) have universally canonical names.[^shorthand] The same statement written above is:

[^shorthand]: The UUID for this notation in the database is `9c447925-9580-4a26-a8d5-68e08001a836`.

`{bae3}`: `{acf5:theName}` of `{acf5:theName}` is theName

Simply having a name is not usually sufficient to express the kind of relationship two things have with each other.[^lossy] A helpful complement is what I called `theIntention`, a short text description of what I had in mind when creating the attribute. This enters the statement set as:

`{d1d4}`: `{acf5:theName}` of `{9ca3:theIntention}` is "theIntention"
`{953f}`: `{9ca3:theIntention}` of `{9ca3:theIntention}` is "This string represents instructions, intentions, or interpretations in natural language. It grounds the structure to reality."

Rounding it out, I also provide theIntention of theName.

`{fd11}`: `{9ca3:theIntention}` of `{acf5:theName}` is "Display this as a human-readable name to the user instead of the UUID in most situations"

Now, we return to our original statement providing one level of interpretation of what the statement means using the name and the intention.

`{db41}`: `{bb2b:theSampleSize}` of `{2dcc:thisPaper}` is 24
`{c4d5}`: `{acf5:theName}` of `{bb2b:theSampleSize}` is "theSampleSize"
`{aa73}`: `{9ca3:theIntention}` of `{bb2b:theSampleSize}` is "The number of people in a research paper's reported sample."
### Relational Structures

Great! Now we have a fact. However, these facts are a little bit more useful if they can be applied in the same way to many kinds of things. This is the "relational" aspect of Trunky, being as expressive as a relational database. The ontological commitments of Trunky lend better towards an entity-component type architecture (e.g., the database row itself is referring to the intension (the obejct being represented) rather than the extension (the database row). However, it is still easily possible to develop an architecture that is mean to take the extensional approach, and I would encourage anyone to make one if they find it useful.

In the context of my literature review[^context], all papers I was looking at had a sample size. Let's say I define an item called aRequiredSlot, so that:

[^context]:  The particular I believe I first felt the need for Trunky doing a literature review for the work that became Mark Roman Miller, ["Multiclass AUC for Comparison of Identification Effectiveness Across Classification Set Sizes"](https://doi.org/10.1109/WoWMoM60985.2024.00028), *2024 IEEE 25th International Symposium on a World of Wireless, Mobile and Multimedia Networks (WoWMoM)*, 2024, and Mark Roman Miller et al., ["Effect of Duration and Delay on the Identifiability of VR Motion"](https://arxiv.org/abs/2407.18380), same venue, 2024, which focuses on how effect various ML approaches are across various participant groups - it's intuitively easier for a model to score a certain accuracy choosing among 10 entries than among 10,000.

`{7fa4}`: `{acf5:theName}` of `{2476:aRequiredSlot}` is "aRequiredSlot"
`{e2b6}`: `{9ca3:theIntention}` of `{2476:aRequiredSlot}` is "Declares that entities carrying a given component must have at least one statement using the given attribute, for validation purposes."
`{fcc8}`: `{2476:aRequiredSlot}` of `{fa93:Paper}` is `{bb2b:theSampleSize}`

Great. It's not hard to imagine the code the finds all requredSlots of ResearchPaper, finds all items, and then filters for both. Completely doable, even if slightly inefficient.

### Statements are just that - statements.

However, there is another problem here. I'm now stating that all research papers have sample sizes. That isn't true - not all research papers have a sample. Furthermore, theIntention said it's the "number of people", but not all samples are people.

A common response may be to work a little harder to polish and select the correct name or definition to address this issue. This is how we've been trained if we use regular databases.

The principled difference with Trunky is to take on the linguistic fact that this is not an exceptional circumstance of a poorly designed ontology, but rather is the common circumstance of natural language being used *effectively*. It worked for me in the context I was working in: if somebody asked me what the rose of my table are, I would’ve said "research papers" or perhaps "publications," and if somebody asked “And what was that 24 there?” a natural phrase I would use to respond could be "Oh, the, uh, the sample size." If I later correct myself and say "Well, not the sample size, technically, it's the number of people they were identifying among", that would be too precise for most in-person situations - valuable only if my conversation partner remained confused after I said "sample size."

The solution then is *not* to determine the correct name before publishing it, but rather to *allow repair* just as simply as in-person conversations can correct names or misunderstandings with simply another sentence or two. In fact, the second person, the person who wants to use this ResearchPaper component to work beyond it, is in a *better* position to describe how I'm using it because my usage is not invisible like a tool, it is explicitly out there like a fact to be read.

Trunky is not built with a single idea of truth but rather a grammar that can be machine readable. If you download this collection of data, and you are frustrated with my name choice, you can rename it for yourself locally. You can also push your change upward and request that I include your alternative name in my set of data, if it's good. Alternatively, someone else can look at the most common renaming for these kinds of papers and use that one by default.

## Performing Repair

Three ways a schema commonly turns out to be wrong, none of which need a migration.

**The name was wrong.** `theSampleSize` reads badly. Rename it, and say which of the two naming statements now stands:

`{227e}`: `{acf5:theName}` of `{c001:theParticipantCount}` is "theParticipantCount"
`{2e3a}`: `{acf5:theName}` of `{8f9d:aReplacement}` is "aReplacement"
`{f58b}`: `{8f9d:aReplacement}` of `{c4d5}` is `{227e}`

`{8f9d:aReplacement}` points from one naming statement's *handle* to another — not from the item. Every existing reference to `{bb2b:theSampleSize}` still resolves, and the old name stays recoverable as something it used to be called.

**The question was wrong.** `theSampleSize` turns out to have quietly conflated two different numbers — participants recruited, and participants whose data survived exclusion. Old rows recorded whichever one got typed first. Fix: add the real attribute, flag the old rows as ambiguous, and migrate one paper at a time as you revisit it — the database ends up honestly mixed, not uniformly rewritten:

- `{acf5:theName}` of `{a0a1:theAnalyzedCount}` is "theAnalyzedCount"
- `{29a2:aNote}` of `{c001:theParticipantCount}` is "Used inconsistently before this note; values may be recruited or analyzed counts and should be rechecked against the source."
- `{a0a1:theAnalyzedCount}` of `{2017:Author2017}` is 51
- `{8f9d:aReplacement}` of `{10ea}` is `{10eb}` — where `{10ea}` is the handle of the original "24" line and `{10eb}` the handle of this new "51" line

A relational migration only offers one option here: rewrite every row in one commit. This gives you four — add the attribute and leave every row alone; migrate some rows and leave the rest visibly unmigrated; migrate all of them; or retract the old statements outright — without forcing a choice among them.

**The entity was wrong.** Partway through, it turns out sample size was never really a property of a *paper* — papers can report multiple studies, and the number belongs to the study, not the paper. In a relational schema this is the migration that's hard to even start (a new table, a foreign key, every existing row split and backfilled in one commit). Here it's just an addition — a new `Study` component, a specific study entity, and the old count replaced by a new statement about the *right* entity:

- `{acf5:theName}` of `{5714:Study}` is "Study"
- `{acf5:theName}` of `{201a:Author2017Study1}` is "Author et al. 2017, Study 1"
- `{a0a1:theAnalyzedCount}` of `{201a:Author2017Study1}` is 51
- `{8f9d:aReplacement}` of `{10eb}` is `{10ec}` — where `{10ec}` is the handle of this new line, attached to the study rather than the paper

Papers with only one study can be left unmigrated indefinitely, since the distinction doesn't matter for them yet. The realization and the response are separable, and the response can stop halfway without anything being broken.


## What Trunky doesn’t do

If you're looking for something that has one of these properties, you're probably better off looking somewhere else. 
### Intentional trade-offs

Design means I need to deprioritize something else. Here's what fell by the wayside intentionally in order to attain the other desiderata.

**Size.** Every cell carries its own handle plus the attribute and entity UUIDs it belongs to, stored in full and repeated on every row that uses them. A rectangular table gets row and column identity for free from position alone, so a Trunky cell costs roughly three extra UUIDs and a type tag that a spreadsheet cell never needs. Compared to a rectangular format, each cell value carries an extra 3 IDs (its own handle plus the entity and attribute it belongs to), and if it also has provenance, that's a full additional statement made of 4 more IDs. In the current implementation and data, that's about 108 extra bytes per cell without provenance and 252 bytes with it, against string values that average around 150 bytes, so a typical cell runs roughly 1.7 to 2.7 times the size of the value alone.

**Speed.** Querying probably requires 2x-6x more self-joins, depending on the query, because data needs to be re-joined and filtered.

**Write-time integrity.** Required, desirable, and optional slots are checked by a separate script when someone chooses to run it, not by the write path itself. Nothing like a NOT NULL constraint or a foreign key exists at the storage layer, and since a new item is always permitted at the data model level, there isn't any way to disambiguate between an intentionally-new and an unintentionally-new attribute.

### Impossible things 

I want to be clear about what Trunky can't do due to logical impossibilities. It is in part to temper misunderstood claims, but it is more importantly showing where Trunky's philosophical roots are.

**Single source of truth / universal meaning.** RDF and OWL invest heavily in logically precise meaning because the payoff is supposed to be automated reasoning, but in practice `owl:sameAs` gets used however seems locally convenient, producing real logical contradictions instead of the clean inference chains the formalism promises. Trunky doesn't try to close that gap between the formal promise and the messy practice, it just admits the gap exists rather than pretending precision alone can buy you a single shared meaning.

**Self-interpret.** Trunky is merely *self-descriptive*: `theIntention` of `theIntention` is a real row, so the system can talk about its own vocabulary the same way it talks about anything else. That is different from being self-interpreting: a description sitting in the data still has to be read and understood *by someone* before it *means* anything at all.

**Resolve conflicts.** Letting anyone add a statement means you'll end up with several different, disagreeing statements about the same thing from different people. Whatever resolves that disagreement- a person, a script, a vote- isn't some neutral judge standing outside the system, it's just one more claim, written the same way as the ones it's arbitrating between.

### Not Implemented Yet

Stuff I haven't gotten around to yet mainly.

**Authentication.** Nothing in the data model or the API stops anyone from writing to it. Any access control on the current deployment is external to Trunky, not part of the data model itself.

**Sharing.** There's no protocol for sharing data yet, even though sharing is central to what I intend this project to eventually support.

**Maturity.** The idea itself is something I've been developing for three years or more, but this specific implementation only dates back to August 2026.

## Comparisons

Why not use…

**Markdown files with links?** YAML frontmatter already gets you most of the way there, it's just key-value pairs. But a link between two files carries no attribute of its own, so there's nowhere to say anything about the relationship itself, and no way to attach a note to one specific fact the way a statement's own handle lets you attach one here.

**A regular database?** A relational database only has one schema active at a time, and adding a column or splitting a table means a migration touching every row that already exists. Trunky isn't different storage underneath, `trunky.db` is SQLite too, the difference is entirely in what gets enforced at write time versus left as data to be checked later.

**Agents plus a SQL database whose schema can modify?** In short, I haven't figured out how to let agents adapt schemata correctly. I'm just assuming how I'm thinking about something is basically impossible to be explicit enough about to an agent - at that point, I may as well just define the schemata myself.

**Agents plus a SQL database with a fixed schema?** Pointing an agent at a rigid schema means it has to translate whatever it understood into someone else's predefined columns, and that translation step is exactly where mismatches and silent corruption creep in.

**JSON?** A bare JSON object doesn't say what any of its own keys mean, that has to live somewhere else entirely. It's also tied to a tree shape, so a reference between two sibling objects has to be bolted on as an ID string with no standard meaning, and there's no way to attach a statement to one specific key-value pair.

**RDF?** RDF treats every triple as a flat, asserted truth, with no room to mark a statement as contested, held by only one party, or true at one time and not another. Its mechanism for talking about a triple as a thing in its own right, reification, is semantically inert and was dropped from the RDF 1.1 specification entirely, and `owl:sameAs` is symmetric and transitive, so anyone who links into a published dataset can have their identity claims propagate into it whether the original author wanted that or not.[^halpin]

**Datomic?** Datomic is the closest existing system to this shape. A datom is exactly an entity, attribute, and value, plus a transaction id and a flag for whether it was asserted or retracted.[^datomic] An individual datom has no identity of its own though, only the transaction that produced it does, every transaction in Datomic is its own entity, so a note can be attached to who made a change but not to one specific fact. And a datom is still either asserted or retracted, true or not true, with no room for a claim to be held by only one party or contested rather than settled.

[^halpin]: Harry Halpin, Patrick J. Hayes, James P. McCusker, Deborah L. McGuinness, and Henry S. Thompson, ["When owl:sameAs Isn't the Same: An Analysis of Identity in Linked Data"](https://link.springer.com/chapter/10.1007/978-3-642-17746-0_20), *Proceedings of the 9th International Semantic Web Conference* (2010).
[^datomic]: ["Datom" and "Retract"](https://docs.datomic.com/javadoc/datomic/Datom.html), Datomic documentation.

## How to start?

Clone the repository, install `requirements.txt`, apply `starter.sql` (`sqlite3 lignin.db < starter.sql`) to seed the bootstrap vocabulary `llms.txt` refers to, and run `python3 api_server.py`. Point your own coding agent at `llms.txt` in this repo, it's written for exactly this: an agent-facing guide to the domain model and conventions, so it can start making the same kind of raw `/statements` API calls I do, on your own local copy of the data.

TODO:
- A filterable explorer view (columns, search, by-component browsing) aimed at a less technical audience than "read `llms.txt` and call the API yourself."
- A lightweight web starter kit for viewing and making minor edits to spreadsheet-like data, for contributors who want to add to a shared dataset (e.g. the VR-motion-data literature review) without running their own agent.
