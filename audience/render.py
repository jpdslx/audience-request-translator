"""Turns a result into an answer a CRM manager can read in under a minute."""
import datetime
import re

from . import query

_FIELD = r"`?\b[a-z]+(?:_[a-z0-9]+)+\b`?"  # snake_case names such as no_upcoming_booking


def plain(text):
    """Takes field and filter names out of text the reading wrote, so managers only see plain words.

    A bracket that holds a field name is dropped; any other field name becomes ordinary words."""
    text = re.sub(r"\s*\([^()]*%s[^()]*\)" % _FIELD, "", text)
    return re.sub(_FIELD, lambda m: m.group(0).strip("`").replace("_", " "), text)

CHANNEL_NAMES = {"email": "email", "push": "push", "sms": "SMS"}


def _date(iso):
    return datetime.date.fromisoformat(iso).strftime("%-d %b %Y")


def _months_back(months):
    d = datetime.date.fromisoformat(query.TODAY)
    month = d.month - months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return d.replace(year=year, month=month).isoformat()


def describe(f):
    """One filter in plain words."""
    t = f["type"]
    if t == "completed_booking_within":
        return "Completed at least one rental that ended between %s and %s" % (
            _date(_months_back(f["months"])), _date(query.TODAY))
    if t == "completed_booking_made_within":
        return "Completed at least one rental that was booked between %s and %s" % (
            _date(_months_back(f["months"])), _date(query.TODAY))
    if t == "no_completed_booking_within":
        return "No completed rental in the last %d months" % f["months"]
    if t == "min_completed_rentals":
        return "At least %d completed rentals in total" % f["count"]
    if t == "has_upcoming_booking":
        return "Has a confirmed booking with a pickup from today"
    if t == "no_upcoming_booking":
        return "No confirmed booking with a pickup from today"
    if t == "app_opened_within":
        start = datetime.date.fromisoformat(query.TODAY) - datetime.timedelta(days=f["days"] - 1)
        return "Opened the app in the last %d days (%s to %s)" % (
            f["days"], start.strftime("%-d %b"), _date(query.TODAY))
    if t == "loyalty_tier_in":
        return "Loyalty tier: %s" % " or ".join(f["tiers"])
    if t == "language_in":
        return "Preferred language: %s" % " or ".join(
            query.LANGUAGES.get(x, x) for x in f["languages"])
    if t == "no_booking_created_within":
        return "Made no new booking in the last %d months" % f["months"]
    if t == "min_spend_within":
        return "Spent at least €%s on completed rentals in the last %d months" % (
            format(f["eur"], ",g"), f["months"])
    if t == "cancelled_between":
        by = "cancellation date" if f["basis"] == "cancellation_date" else "pickup date"
        return "Cancelled a booking, %s between %s and %s" % (by, _date(f["start"]), _date(f["end"]))
    return t


def assumption(f):
    """What the tool assumed for a filter, if anything, so the manager can correct it."""
    t = f["type"]
    if t == "completed_booking_within":
        return ("\"In the last %d months\" counts rentals that **ended** in that period. "
                "I can switch to the date the booking was made." % f["months"])
    if t == "completed_booking_made_within":
        return ("\"In the last %d months\" counts rentals that were **booked** in that period. "
                "I can switch back to rentals that ended in that period." % f["months"])
    if t == "min_spend_within":
        return ("\"Spent\" means net revenue after discounts, from completed rentals that **ended** in the "
                "last %d months. Cancelled bookings don't count." % f["months"])
    if t in ("has_upcoming_booking", "no_upcoming_booking"):
        return ("\"Upcoming booking\" means a confirmed booking with a pickup date from today "
                "(%s)." % _date(query.TODAY))
    if t == "app_opened_within":
        return ("\"App user\" means someone who actually opened the app in that period, "
                "not everyone flagged as having the app.")
    if t == "no_booking_created_within":
        return ("\"Haven't booked\" means no new booking **made** in that period. I can switch to "
                "\"no rental taken\" instead.")
    if t == "no_completed_booking_within":
        return ("This counts rentals **taken** (completed) in the last %d months, not bookings made. "
                "I can switch to \"no new booking made\" instead." % f["months"])
    return None


NO_MARKET = "No market was named, so this covers all markets. Tell me a market to narrow it."


def no_market(spec):
    """True when the request named no market and no language, so the tool assumes all markets."""
    return (not spec.get("country")
            and not any(f.get("type") == "language_in" for f in spec.get("filters", [])))


def who_lines(spec):
    lines = []
    if spec.get("country") in query.COUNTRY_NAMES:
        lines.append("Living in %s" % query.COUNTRY_NAMES[spec["country"]])
    lines += [describe(f) for f in spec.get("filters", [])]
    return lines


def _options(options):
    letters = "abcdefgh"
    return "\n".join("   %s) %s" % (letters[i], o) for i, o in enumerate(options))


def render(result, files=None):
    """files: (audience CSV path, SQL path) for built audiences."""
    spec = result["spec"]
    out = []
    v = result["verdict"]

    if v == "build":
        channel = CHANNEL_NAMES[spec["channel"]]
        place = query.COUNTRY_NAMES.get(spec.get("country"), "all markets")
        langs = [f for f in spec.get("filters", []) if f["type"] == "language_in"]
        if langs and not spec.get("country"):
            place = " or ".join(query.LANGUAGES.get(x, x) for x in langs[0]["languages"]) + " speakers"
        icon = "✅" if result["final"] else "⚠️"
        out.append("## %s %s, %s: %s people\n" % (icon, place[0].upper() + place[1:], channel,
                                                  format(result["final"], ",")))
        if result.get("alternatives"):
            out.append("**Nobody in this group can get %s.** Other channels, with their own consent "
                       "checked: %s.\n" % (channel, ", ".join(
                           "%s %s people" % (CHANNEL_NAMES[ch], format(n, ","))
                           for ch, n in result["alternatives"].items())))
        out.append("> %s\n" % spec["request"])
        out.append("**Who's in**")
        for line in who_lines(spec):
            out.append("- %s" % line)
        out.append("- Latest %s consent is \"yes\"" % channel)
        out.append("\n**How we got to %s**\n" % format(result["final"], ","))
        out.append("| | People |")
        out.append("|---|---:|")
        first_label, first_n = result["steps"][0]
        out.append("| %s | %s |" % (first_label, format(first_n, ",")))
        for label, n in result["steps"][1:]:
            out.append("| %s | %s |" % (label, "-" + format(n, ",") if n else "0"))
        out.append("| **Final audience** | **%s** |" % format(result["final"], ","))
        assumptions = [a for a in (assumption(f) for f in spec.get("filters", [])) if a]
        if no_market(spec):
            assumptions.insert(0, NO_MARKET)
        if assumptions:
            out.append("\n**Please check**")
            out += ["- %s" % a for a in assumptions]
        handled = []
        if result.get("spellings") and len(result["spellings"]) > 1:
            handled.append("%s's %d spellings in the data (all included)" % (
                query.COUNTRY_NAMES[spec["country"]], len(result["spellings"])))
        extra = result["records"] - first_n
        if extra > 0:
            handled.append("%s duplicate record%s (each person counted once)" % (
                format(extra, ","), "" if extra == 1 else "s"))
        if handled:
            out.append("\n**Handled for you:** %s." % ", ".join(handled))
        if files:
            out.append("\n**Files:** audience list `%s` · query for Analytics `%s`" % files)

    elif v == "ask":
        n = len(result["questions"])
        out.append("## ❓ %s before I build this" % ("One question" if n == 1 else "%d questions" % n))
        out.append("> %s\n" % spec["request"])
        for i, q in enumerate(result["questions"], 1):
            out.append("%d. **%s**" % (i, plain(q["question"])))
            if q.get("options"):
                out.append(_options([plain(o) for o in q["options"]]))
        clear = who_lines(spec)
        if no_market(spec):
            clear.insert(0, "All markets (no market named)")
        if spec.get("channel"):
            clear.append("%s channel" % CHANNEL_NAMES.get(spec["channel"], spec["channel"]).capitalize())
        if clear:
            out.append("\n**Already clear:** %s." % "; ".join(c[0].lower() + c[1:] for c in clear))

    elif v == "refuse":
        out.append("## ⛔ I can't build this one")
        out.append("> %s\n" % spec["request"])
        out.append("**Why**")
        from .engine import RULE_BREAKS, RULE_BREAK_ALTERNATIVES
        keys = [k for k in spec["rule_breaks"] if k in RULE_BREAKS]
        out += ["- %s" % RULE_BREAKS[k] for k in keys]
        out.append("\n**What you can do instead**")
        alternatives = []
        if "self_declared_service_message" in keys:
            keys = ["self_declared_service_message"]  # its advice already covers the consent route
        for k in keys:
            alternatives += [a for a in RULE_BREAK_ALTERNATIVES[k] if a not in alternatives]
        out += ["- %s" % a for a in alternatives]

    elif v == "cannot_answer":
        out.append("## ⛔ I can't answer this as asked")
        out.append("> %s\n" % spec["request"])
        out.append("**Why**")
        out += ["- %s" % g["why"] for g in result["gaps"]]
        offers = [g for g in result["gaps"] if g.get("offer")]
        if offers:
            out.append("\n**What I can offer**")
            for g in offers:
                out.append("- %s" % g["offer"])
                if "offer_count" in g:
                    out.append("- About %s people match this rule before consent and exclusions. "
                               "Tell me the channel and I'll build it." % format(g["offer_count"], ","))

    notes = spec.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    if notes:
        out.append("\n**I also noticed**")
        out += ["- %s" % plain(n) for n in notes]
    if v == "ask" and any(q.get("options") for q in result["questions"]):
        out.append("\nAnswer with one letter per question (for example \"a, b\") and I'll build it.")
    return "\n".join(out) + "\n"
