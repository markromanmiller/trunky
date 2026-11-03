"""Code for the System "Classify calendar events": gives CalendarEvent items a time-budget Category.

run(row, view) gets one query row (?feed): a CalendarFeed. Each current CalendarEvent of that feed without a
theCategory gets the theCategory of the first CategoryRule it matches (agreed with Mark 2026-10-17). A rule
matches when every condition it has holds: theICalendarUID equal to the event's (a whole repeating series),
theTitlePattern (a case-insensitive Python regular expression) found in the event's theName, theCalendarFeed
equal to the event's feed. Rules with a theICalendarUID are tried first, then the rest, each group in order of
theName. An event that already has a category keeps it (a category set by hand wins), and an event no rule
matches stays untagged. A rule with an invalid pattern is skipped and named in the run's note.
"""
import re

COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
NAME = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6"
CAL_EVENT = "b7375bb0-3ed1-45fc-bcac-6eb20ebbb8d3"
FEED = "40d24795-9b2f-4ad1-92dd-e1acfaaaab3f"
ICAL_UID = "d75ad5d3-1a0f-4052-8518-831b5b10356c"
CATEGORY = "e316c25d-6439-4545-b5c8-4d2b0fd7103c"     # theCategory
RULE = "d7a1fc00-055d-4f5b-8071-3c242b2742e5"         # CategoryRule
PATTERN = "295185fa-ffe2-4c85-b534-61c673983b58"      # theTitlePattern


def items(view):
    """{entity: {attribute: [values]}} of the current statements."""
    out = {}
    for _, _, a, e, v, _ in view.current:
        out.setdefault(e, {}).setdefault(a, []).append(v)
    return out


def rules(by_item):
    """[(name, conditions, category)] in the order they are tried, plus the names of invalid rules."""
    out, bad = [], []
    for e, d in by_item.items():
        if RULE not in d.get(COMP, []) or not d.get(CATEGORY):
            continue
        name = (d.get(NAME) or [e])[0]
        try:
            pattern = re.compile(d[PATTERN][0], re.I) if d.get(PATTERN) else None
        except re.error:
            bad.append(name)
            continue
        uid, feed = (d.get(ICAL_UID) or [None])[0], (d.get(FEED) or [None])[0]
        if not (uid or pattern or feed):
            continue
        out.append((name, uid, pattern, feed, d[CATEGORY][0]))
    out.sort(key=lambda r: (r[1] is None, r[0]))
    return out, bad


def run(row, view):
    feed = row["feed"]
    by_item = items(view)
    rs, bad = rules(by_item)
    out, counts, untagged = [], {}, 0
    for e, d in by_item.items():
        if CAL_EVENT not in d.get(COMP, []) or feed not in d.get(FEED, []) or d.get(CATEGORY):
            continue
        title, uid = (d.get(NAME) or [""])[0], (d.get(ICAL_UID) or [""])[0]
        for name, r_uid, pattern, r_feed, category in rs:
            if (r_uid is None or r_uid == uid) and (pattern is None or pattern.search(title)) and \
                    (r_feed is None or r_feed == feed):
                out.append((CATEGORY, e, category, "uuid"))
                counts[name] = counts.get(name, 0) + 1
                break
        else:
            untagged += 1
    note = f"{len(out)} events tagged" + (f" ({', '.join(f'{n}: {c}' for n, c in sorted(counts.items()))})"
                                          if counts else "") + f"; {untagged} untagged"
    if bad:
        note += f"; skipped rules with an invalid pattern: {', '.join(bad)}"
    return {"statements": out, "note": note}
