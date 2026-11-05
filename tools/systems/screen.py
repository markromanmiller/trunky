"""Code for the System "Screen candidates": ask a review's screening calls about one candidate paper.

run(row, view) gets (?review, ?paper). The review's aScreeningCall statements name JevNoulCall items,
each carrying theInstructions, theTrueCriterion, theFalseCriterion and theModel. Calls this paper has
no score for yet are asked together, one Jev request per model, on the paper's title and abstract
(the theInputSection the current calls specify). Each probability is written as
"<call> of <paper> is <noul>", three decimals, matching the scores already stored.
"""
import json, os, urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ecs"))
from view import conf  # noqa: E402

SCREENING_CALL = "8cc3ae39-fc1b-47bf-b011-21bce347343a"   # aScreeningCall
NAME = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6"
ABSTRACT = "8da56a78-03af-4a22-b119-e052f686e3fb"
INSTRUCTIONS = "8a9ec1f7-11cd-46cb-bb38-cdbec00b08e1"
TRUE_CRIT = "838f7a5b-b5c1-4bac-9cee-7d6700b2d757"
FALSE_CRIT = "ddbd60f4-d69e-4c9b-8bbb-d93ac984b1c7"
MODEL = "bedaf236-bd15-4093-ad71-be3b9acae25f"
ENV = Path(conf("env_file", Path.home() / ".config" / "trunky.env"))   # secrets, as NAME=value lines
URL = "https://openrouter.ai/api/alpha/decisions"


def api_key():
    for line in ENV.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"OPENROUTER_API_KEY missing from {ENV}")


def ask(model, questions, state):
    req = urllib.request.Request(URL, data=json.dumps({"model": model, "questions": questions, "state": state}).encode(),
                                 headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    if "answers" not in body:
        raise RuntimeError(f"Jev returned no answers: {str(body)[:300]}")
    return body


def run(row, view):
    review, paper = row["review"], row["paper"]
    one = lambda e, a: (view.values(e, a) or [None])[0]
    calls = [c for c in view.values(review, SCREENING_CALL) if not view.values(paper, c)]
    title, abstract = one(paper, NAME), one(paper, ABSTRACT)
    state = f"Title: {title}\n\nAbstract: {abstract or '(no abstract available)'}"
    by_model = {}
    for c in calls:
        by_model.setdefault(one(c, MODEL), {})[c] = {
            "type": "noul", "instructions": one(c, INSTRUCTIONS),
            "criteria": {"true": one(c, TRUE_CRIT), "false": one(c, FALSE_CRIT)}}
    out, cost = [], 0.0
    for model, questions in by_model.items():
        body = ask(model, questions, state)
        cost += (body.get("usage") or {}).get("cost") or 0
        out += [(c, paper, f"{body['answers'][c]['noul']:.3f}", "str") for c in questions]
    return {"statements": out,
            "note": f"{len(out)} screening call(s) asked via Jev on title and abstract (cost ${cost:.5f})"}
