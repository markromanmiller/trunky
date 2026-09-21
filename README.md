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

## How to start?

Clone the repository, install `requirements.txt`, apply `starter.sql` (`sqlite3 lignin.db < starter.sql`) to seed the bootstrap vocabulary `llms.txt` refers to, and run `python3 api_server.py`. Point your own coding agent at `llms.txt` in this repo, it's written for exactly this: an agent-facing guide to the domain model and conventions, so it can start making the same kind of raw `/statements` API calls I do, on your own local copy of the data.
