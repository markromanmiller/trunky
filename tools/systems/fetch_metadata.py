"""Code for the System "Fetch paper metadata": fill in a paper's details from its DOI.

run(row, view) gets one query row (?paper, ?doi) and returns the statements to write. Sources:
OpenAlex first (abstract, authors in order, venue, date, OpenAlex id); Semantic Scholar for the abstract
when OpenAlex has none; Crossref for venue or date when both are missing. Only attributes the paper
lacks are written. Authors get an OrderedList (theAuthorOrder) whose wrappers hold the anAuthor
statements by handle, as in the ISMAR program set. theOpenAlexID is always written (theExplicitAbsence when OpenAlex has no record),
which is what the System's query checks, so each paper is looked up once.
"""
import json, urllib.parse, urllib.request, uuid

AUTHOR = "b6d0e1e4-7472-47df-935d-ecdecef92345"
VENUE = "0edf762a-9a26-4849-8002-bc071fb74d9c"
DATE = "d610fcca-8f7f-48bd-a14c-fa744e5de8a6"
ABSTRACT = "8da56a78-03af-4a22-b119-e052f686e3fb"
OPENALEX_ID = "5fab6903-91fa-46a3-8322-6f7ec954f4bb"
ABSENT = "00000000-0000-0000-0000-000000000000"
COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
AUTHOR_ORDER = "e224355b-f867-4812-859b-bbbe8b911d9b"
ORDERED_LIST = "07113780-565e-452c-880f-e3bbc90b2453"
ORDERED_ITEM = "33a57005-dc0b-463e-b4e6-251938b846c7"
FIRST = "bf93f20a-bbb3-4655-b832-ad8d2b07e897"
NEXT = "78587753-20ed-4d00-8ca4-a94f65b551a0"
LAST = "e58bb5bc-fa24-4cd8-99db-a43fc12f600a"
MEMBER = "5b5201fb-6b2e-4486-b73c-194022bae390"
UA = {"User-Agent": "trunky-ecs/0.1"}


def get_json(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def openalex(doi):
    w = get_json(f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}")
    if not w:
        return None
    abstract = None
    if w.get("abstract_inverted_index"):
        pos = {i: word for word, idx in w["abstract_inverted_index"].items() for i in idx}
        abstract = " ".join(pos[i] for i in sorted(pos))
    src = (w.get("primary_location") or {}).get("source") or {}
    return {"id": w["id"].rsplit("/", 1)[-1], "abstract": abstract, "venue": src.get("display_name"),
            "date": w.get("publication_date"),
            "authors": [a["author"]["display_name"] for a in w.get("authorships", [])]}


def semantic_scholar_abstract(doi):
    p = get_json(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}?fields=abstract")
    return (p or {}).get("abstract")


def crossref(doi):
    m = (get_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}") or {}).get("message") or {}
    parts = (m.get("issued") or {}).get("date-parts") or [[]]
    date = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(parts[0])) or None
    return {"venue": (m.get("container-title") or [None])[0], "date": date}


def author_statements(paper, names):
    """anAuthor statements (with handles) plus the OrderedList giving their byline order."""
    new = lambda: str(uuid.uuid4())
    handles = [new() for _ in names]
    out = [(AUTHOR, paper, n, "str", h) for n, h in zip(names, handles)]
    lst, wrappers = new(), [new() for _ in names]
    out += [(AUTHOR_ORDER, paper, lst, "uuid"), (COMP, lst, ORDERED_LIST, "uuid"),
            (FIRST, lst, wrappers[0], "uuid"), (LAST, lst, wrappers[-1], "uuid")]
    for i, (w, h) in enumerate(zip(wrappers, handles)):
        out += [(COMP, w, ORDERED_ITEM, "uuid"), (MEMBER, w, h, "uuid")]
        if i + 1 < len(wrappers):
            out.append((NEXT, w, wrappers[i + 1], "uuid"))
    return out


def run(row, view):
    paper, doi = row["paper"], row["doi"]
    has = lambda a: bool(view.values(paper, a))
    out, sources = [], []
    oa = openalex(doi)
    if oa:
        sources.append(f"OpenAlex {oa['id']}")
        out.append((OPENALEX_ID, paper, oa["id"], "str"))
    else:
        out.append((OPENALEX_ID, paper, ABSENT, "uuid"))
        oa = {"abstract": None, "venue": None, "date": None, "authors": []}
    if not has(ABSTRACT) and not oa["abstract"]:
        oa["abstract"] = semantic_scholar_abstract(doi)
        if oa["abstract"]:
            sources.append("Semantic Scholar (abstract)")
    if not (oa["venue"] or has(VENUE)) or not (oa["date"] or has(DATE)):
        cr = crossref(doi)
        oa["venue"], oa["date"] = oa["venue"] or cr["venue"], oa["date"] or cr["date"]
        sources.append("Crossref")
    if not has(AUTHOR) and oa["authors"]:
        out += author_statements(paper, oa["authors"])
    for attr, val in ((VENUE, oa["venue"]), (DATE, oa["date"]), (ABSTRACT, oa["abstract"])):
        if val and not has(attr):
            out.append((attr, paper, val, "str"))
    return {"statements": out, "note": f"DOI {doi} looked up in " + (", ".join(sources) or "nothing found")}
