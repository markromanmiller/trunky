"""Code for the System "Pull calendar feeds": mirror an iCalendar feed into CalendarEvent items.

run(row, view) gets one query row (?feed, ?secret): a CalendarFeed item and the name of the variable in
~/.config/trunky-ecs.env that holds its URL (the URL itself is never stored in Trunky). It fetches the
feed, expands repeating series (RRULE, EXDATE, and edited occurrences via RECURRENCE-ID), and compares
the result with the feed's current CalendarEvent items:

- an occurrence another feed already has (same UID and original start: an invitation on two calendars)
  is skipped, so each event is mirrored once;

- an occurrence starting within WINDOW_DAYS of today that Trunky lacks becomes a new CalendarEvent;
- a changed title, start, end, location or busy status gets a new statement and aReplacement of the old
  one (a location that disappears gets theRemovalTime);
- a CalendarEvent starting within the window whose occurrence is no longer in the feed gets
  theRemovalTime (cancelled or deleted). Items outside the window are left alone, so past events remain.

Times are written in the event's own time zone, with its UTC offset (2026-10-09T09:30:00+02:00), and
the zone's IANA name goes in theTimeZone (Exchange's Windows names are mapped; "W. Europe Standard Time"
becomes Europe/Berlin). All-day events are plain dates with no theTimeZone.

An occurrence is identified by the feed's UID plus, for a repeating series, its original start
(theOriginalStartDateTime), which stays fixed when one occurrence is moved; original starts are compared
as instants, so the same moment written in two zones still matches. New items go into the
feed's home set. As a guard against a truncated feed, an empty feed or one that would remove more than
half of the window's events (and more than 5) raises instead of writing.
"""
import datetime as dt, re, urllib.request, uuid
from pathlib import Path

from dateutil import rrule, tz

COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
NAME = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6"
REPLACEMENT = "8f9dc95b-c4d3-4500-9a6c-9ddc63cdecf9"
REMOVAL_TIME = "7ede6e59-945b-4a85-94d8-cce67bf154cc"
CAL_EVENT = "b7375bb0-3ed1-45fc-bcac-6eb20ebbb8d3"
START = "add98a95-7e97-4160-9017-476710afe97c"        # theStartDateTime
END = "f83cd505-501b-4c07-9910-5781f0bf02e2"          # theEndDateTime
ICAL_UID = "d75ad5d3-1a0f-4052-8518-831b5b10356c"     # theICalendarUID
ORIG_START = "1ac82ec0-ff86-4fd0-b899-e9ba404d605d"   # theOriginalStartDateTime
FEED = "40d24795-9b2f-4ad1-92dd-e1acfaaaab3f"         # theCalendarFeed
LOCATION = "c8545a8a-12d7-402f-b742-42ce0e6ad8d5"     # theLocation
BUSY = "f08d9b3d-483d-4cb0-9d8e-3fa667842bfa"         # theBusyStatus
TIME_ZONE = "d1697ad1-ea8f-4b75-9a48-4e6074ad3045"    # theTimeZone
ENV = Path.home() / ".config" / "trunky-ecs.env"
WINDOW_DAYS = 7
WIDE_DAYS = 120   # how far series are expanded when checking whether an occurrence still exists
HOME = tz.gettz("America/Chicago")
BUSY_MAP = {"BUSY": "busy", "TENTATIVE": "tentative", "FREE": "free", "OOF": "out-of-office",
            "WORKINGELSEWHERE": "working-elsewhere"}
# Windows time-zone names used by Exchange, mapped to IANA names (from the CLDR windowsZones table)
WINDOWS_TZ = {
    "Central Standard Time": "America/Chicago", "Eastern Standard Time": "America/New_York",
    "Mountain Standard Time": "America/Denver", "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles", "Alaskan Standard Time": "America/Anchorage",
    "Hawaiian Standard Time": "Pacific/Honolulu", "Atlantic Standard Time": "America/Halifax",
    "Newfoundland Standard Time": "America/St_Johns", "Canada Central Standard Time": "America/Regina",
    "Central Standard Time (Mexico)": "America/Mexico_City", "Central America Standard Time": "America/Guatemala",
    "SA Pacific Standard Time": "America/Bogota", "Pacific SA Standard Time": "America/Santiago",
    "E. South America Standard Time": "America/Sao_Paulo", "Argentina Standard Time": "America/Buenos_Aires",
    "UTC": "UTC", "Coordinated Universal Time": "UTC", "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik", "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris", "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw", "E. Europe Standard Time": "Europe/Chisinau",
    "FLE Standard Time": "Europe/Kiev", "GTB Standard Time": "Europe/Bucharest",
    "Turkey Standard Time": "Europe/Istanbul", "Israel Standard Time": "Asia/Jerusalem",
    "South Africa Standard Time": "Africa/Johannesburg", "Russian Standard Time": "Europe/Moscow",
    "Arabian Standard Time": "Asia/Dubai", "Iran Standard Time": "Asia/Tehran",
    "Pakistan Standard Time": "Asia/Karachi", "India Standard Time": "Asia/Kolkata",
    "Nepal Standard Time": "Asia/Kathmandu", "Bangladesh Standard Time": "Asia/Dhaka",
    "SE Asia Standard Time": "Asia/Bangkok", "China Standard Time": "Asia/Shanghai",
    "Singapore Standard Time": "Asia/Singapore", "Taipei Standard Time": "Asia/Taipei",
    "Tokyo Standard Time": "Asia/Tokyo", "Korea Standard Time": "Asia/Seoul",
    "AUS Eastern Standard Time": "Australia/Sydney", "E. Australia Standard Time": "Australia/Brisbane",
    "Cen. Australia Standard Time": "Australia/Adelaide", "W. Australia Standard Time": "Australia/Perth",
    "New Zealand Standard Time": "Pacific/Auckland",
}


def secret(name):
    for line in ENV.read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{name} missing from {ENV}")


def zone_name(tzid):
    """IANA name for an iCalendar TZID (no TZID: floating time, taken as America/Chicago)."""
    if not tzid:
        return "America/Chicago"
    name = WINDOWS_TZ.get(tzid, tzid)
    if tz.gettz(name) is None or "/" not in name and name != "UTC":
        raise ValueError(f"unknown time zone {tzid!r}; add it to WINDOWS_TZ")
    return name


def zone(tzid):
    return tz.gettz(zone_name(tzid))


def start_zone(params, value):
    """IANA zone name of a DTSTART (UTC for a 'Z' value); None for an all-day date."""
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return None
    return "UTC" if value.endswith("Z") else zone_name(params.get("TZID"))


def parse_time(params, value):
    """(aware datetime, all_day) for a DTSTART/DTEND/EXDATE/RECURRENCE-ID value."""
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return dt.datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=HOME), True
    if value.endswith("Z"):
        return dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc), False
    return dt.datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=zone(params.get("TZID"))), False


def unescape(s):
    return re.sub(r"\\([\\,;nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), s).strip()


def records(text):
    """Each VEVENT as {property: [(params, value), ...]}."""
    text = re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n"))
    out = []
    for block in re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", text, re.S):
        rec = {}
        for line in block.split("\n"):
            if ":" not in line:
                continue
            head, value = line.split(":", 1)
            name, *ps = head.split(";")
            rec.setdefault(name.upper(), []).append((dict(p.split("=", 1) for p in ps if "=" in p), value))
        out.append(rec)
    return out


def fmt(t, all_day, zname):
    return t.date().isoformat() if all_day else t.astimezone(tz.gettz(zname)).isoformat()


def key_of(s):
    """An original start as a comparable key: the instant in UTC (dates stay dates; "" for none)."""
    if not s or "T" not in s:
        return s
    return dt.datetime.fromisoformat(s).astimezone(dt.timezone.utc).isoformat()


def until_utc(rule, start_zone):
    """dateutil needs UNTIL in UTC when DTSTART is time-zone aware."""
    def fix(m):
        v = m.group(1)
        if v.endswith("Z"):
            return m.group(0)
        t = (dt.datetime.strptime(v[:8], "%Y%m%d").replace(hour=23, minute=59, second=59) if len(v) == 8
             else dt.datetime.strptime(v, "%Y%m%dT%H%M%S"))
        return "UNTIL=" + t.replace(tzinfo=start_zone).astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return re.sub(r"UNTIL=([0-9TZ]+)", fix, rule)


def occurrences(recs, lo, hi):
    """Every occurrence starting in [lo, hi), plus every non-repeating event whatever its date (so the
    caller can tell a moved single event from a deleted one), keyed by (uid, original start or "")."""
    one = lambda r, k: (r.get(k) or [({}, "")])[0]
    occ, overrides = {}, set()
    for r in recs:
        if r.get("RECURRENCE-ID") and one(r, "STATUS")[1].upper() != "CANCELLED":
            overrides.add((one(r, "UID")[1], parse_time(*one(r, "RECURRENCE-ID"))[0]))
    for r in recs:
        uid = one(r, "UID")[1]
        if one(r, "STATUS")[1].upper() == "CANCELLED":
            continue
        start, all_day = parse_time(*one(r, "DTSTART"))
        zname = start_zone(*one(r, "DTSTART"))
        end = parse_time(*one(r, "DTEND"))[0] if r.get("DTEND") else start + dt.timedelta(days=1 if all_day else 0)
        busy = BUSY_MAP.get(one(r, "X-MICROSOFT-CDO-BUSYSTATUS")[1].upper()) or \
            ("free" if one(r, "TRANSP")[1].upper() == "TRANSPARENT" else "busy")
        base = {"uid": uid, "title": unescape(one(r, "SUMMARY")[1]), "location": unescape(one(r, "LOCATION")[1]),
                "busy": busy, "all_day": all_day, "zone": zname}
        if r.get("RECURRENCE-ID"):
            orig = parse_time(*one(r, "RECURRENCE-ID"))[0]
            if lo <= start < hi or lo <= orig < hi:
                o = fmt(orig, all_day, zname)
                occ[(uid, key_of(o))] = dict(base, start=start, end=end, orig=o)
        elif r.get("RRULE"):
            ex = {parse_time(ps, v)[0] for ps, vals in r.get("EXDATE", []) for v in vals.split(",")}
            series = rrule.rrulestr(until_utc(one(r, "RRULE")[1], start.tzinfo), dtstart=start)
            for t in series.between(lo, hi, inc=True):
                if t < hi and t not in ex and (uid, t) not in overrides:
                    o = fmt(t, all_day, zname)
                    occ[(uid, key_of(o))] = dict(base, start=t, end=t + (end - start), orig=o)
        else:
            occ[(uid, "")] = dict(base, start=start, end=end, orig="")
    return occ


def current_events(view, feed):
    """{key: {"id": item, attr: [(handle, value), ...]}} for the feed's current CalendarEvent items."""
    items = {r[3] for r in view.current if r[2] == FEED and r[4] == feed}
    by_item = {i: {"id": i} for i in items}
    for _, h, a, e, v, _ in view.current:
        if e in by_item:
            by_item[e].setdefault(a, []).append((h, v))
    first = lambda d, a: (d.get(a) or [(None, "")])[0][1]
    return {(first(d, ICAL_UID), key_of(first(d, ORIG_START))): d for d in by_item.values()}


def other_feeds_keys(view, feed):
    """Keys (uid, original start) of the current CalendarEvent items of every other feed."""
    feeds = {r[4] for r in view.current if r[2] == FEED and r[4] != feed}
    return {k for f in feeds for k in current_events(view, f)}


def run(row, view):
    feed, now = row["feed"], dt.datetime.now(HOME)
    req = urllib.request.Request(secret(row["secret"]), headers={"User-Agent": "trunky-ecs/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        recs = records(r.read().decode("utf-8", "replace"))
    if not recs:
        raise RuntimeError("feed has no events; not syncing")
    today = dt.datetime.combine(now.date(), dt.time(), HOME)
    lo, hi = today - dt.timedelta(days=WINDOW_DAYS), today + dt.timedelta(days=WINDOW_DAYS + 1)
    in_window = lambda s: lo <= (dt.datetime.fromisoformat(s) if "T" in s else
                                 dt.datetime.fromisoformat(s).replace(tzinfo=HOME)) < hi
    feed_occ = occurrences(recs, lo - dt.timedelta(days=WIDE_DAYS), hi + dt.timedelta(days=WIDE_DAYS))
    have = current_events(view, feed)
    elsewhere = other_feeds_keys(view, feed)
    stamp = now.isoformat(timespec="seconds")
    out, added, changed, removed, duplicates = [], 0, 0, 0, 0

    for key, o in sorted(feed_occ.items(), key=lambda kv: kv[1]["start"]):
        want = {NAME: o["title"], START: fmt(o["start"], o["all_day"], o["zone"]),
                END: fmt(o["end"], o["all_day"], o["zone"]), TIME_ZONE: o["zone"] or "",
                LOCATION: o["location"], BUSY: o["busy"]}
        if key not in have:
            if not lo <= o["start"] < hi:
                continue
            # The same event (UID and occurrence) already mirrored from another feed: one item is enough
            if key in elsewhere:
                duplicates += 1
                continue
            e = str(uuid.uuid4())
            out += [(COMP, e, CAL_EVENT, "uuid"), (FEED, e, feed, "uuid"), (ICAL_UID, e, o["uid"], "str")]
            if o["orig"]:
                out.append((ORIG_START, e, o["orig"], "str"))
            out += [(a, e, v, "str") for a, v in want.items() if v]
            added += 1
            continue
        d, touched = have[key], False
        for a, v in want.items():
            old = d.get(a) or []
            if [x[1] for x in old] == ([v] if v else []):
                continue
            touched = True
            new = str(uuid.uuid4())
            if v:
                out.append((a, d["id"], v, "str", new))
            for h, _ in old:
                out.append((REPLACEMENT, h, new, "uuid") if v else (REMOVAL_TIME, h, stamp, "str"))
        changed += touched

    gone = [d for k, d in have.items() if k not in feed_occ and in_window((d.get(START) or [(None, "")])[0][1] or
                                                                      today.isoformat())]
    window_total = sum(1 for d in have.values() if (d.get(START) and in_window(d[START][0][1])))
    if len(gone) > 5 and len(gone) > window_total / 2:
        raise RuntimeError(f"feed would remove {len(gone)} of {window_total} events in the window; "
                           "not syncing (possible truncated feed)")
    for d in gone:
        out.append((REMOVAL_TIME, d["id"], stamp, "str"))
        removed += 1
    note = (f"{len(recs)} feed records; window {lo.date()} to {(hi - dt.timedelta(days=1)).date()}: "
            f"{added} new, {changed} changed, {removed} removed, {duplicates} skipped as in another feed")
    return {"statements": out, "note": note, "set": view.home[feed]}
