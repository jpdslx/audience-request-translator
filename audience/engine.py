"""Decides build / ask / push back, and runs the audience.

The decision is made here, in code, from what the request reading flagged. The AI never chooses
the outcome and can't switch off a rule.
"""
import os
import sqlite3

from . import query

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "option_B_audience_translator", "crm_case.sqlite")

# Requests that break a rule. Refused, whatever else the request says.
# One rule per entry, so an answer only explains the rule the request touched.
RULE_BREAKS = {
    "bypass_consent": (
        "This would send marketing without checking consent. Marketing always needs the customer's "
        "latest consent for that channel, and no campaign can switch that off."),
    "include_open_complaints": (
        "People with an open complaint are never sent marketing. This applies to every audience and "
        "every channel, and can't be switched off."),
    "include_bounced": (
        "Email addresses that bounced are never emailed. This applies to every email audience and "
        "can't be switched off."),
    "self_declared_service_message": (
        "Only Legal can classify a message as a service message. A CRM manager can't decide that, "
        "and I can't either. Service messages also aren't built as marketing audiences."),
}
RULE_BREAK_ALTERNATIVES = {
    "bypass_consent": [
        "Send it as a marketing message, and I'll build the audience with consent applied.",
    ],
    "include_open_complaints": [
        "I'll build the same audience without them, and the answer shows how many people that leaves out.",
    ],
    "include_bounced": [
        "I'll build the same audience without them, and the answer shows how many people that leaves out.",
    ],
    "self_declared_service_message": [
        "Ask Legal to classify the message. If it is a service message, it goes through the service "
        "process, outside the marketing audience tool.",
        "Or send it as a marketing message, and I'll build the audience with consent applied.",
    ],
}

# Requests the data can't answer. Pushed back, with an offer where one exists.
MISSING_DATA = {
    "churn_prediction": {
        "why": ("There's no churn model or agreed churn definition in the data, so I can't predict "
                "who is likely to leave. Guessing would look precise and could be wrong."),
        "offer": ("A simple rule instead of a prediction: people who rented at least twice before, "
                  "had no rental in the last 12 months, and have nothing booked ahead. "
                  "You can change the numbers."),
        "offer_filters": [
            {"type": "min_completed_rentals", "count": 2},
            {"type": "no_completed_booking_within", "months": 12},
            {"type": "no_upcoming_booking"},
        ],
    },
    "contact_history": {
        "why": ("There's no record of who was contacted, when or on which channel, so I can't "
                "filter on past messages."),
        "offer": None,
    },
}

REBOOKED_QUESTION = {
    "question": ("Should we leave out people who already have a new rental booked ahead? They've "
                 "booked again, so they may not need a win-back message."),
    "options": ["Leave them out", "Keep everyone"],
}

CHANNEL_QUESTION = {
    "question": "Which channel is this for? It decides which consent applies.",
    "options": ["Email", "Push", "SMS"],
}


def connect():
    conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    prepare(conn)
    return conn


def prepare(conn):
    """Builds the clean-up tables once per run, so each count is a quick lookup.

    Same logic as the self-contained query saved for Analytics, just computed once.
    """
    for name, sql in query.cleanup_tables():
        conn.execute("DROP TABLE IF EXISTS temp.%s" % name)
        conn.execute("CREATE TEMP TABLE %s AS %s" % (name, sql))
    for i, target in enumerate(query.CLEANUP_INDEXES):
        conn.execute("CREATE INDEX IF NOT EXISTS temp.ix_%d ON %s" % (i, target))


def _asks_channel(spec):
    """True if the reading already asks which channel, so the code doesn't ask twice."""
    for q in spec.get("ambiguities", []) + spec.get("unknown_terms", []):
        options = " ".join(q.get("options", [])).lower()
        if "email" in options and "push" in options:
            return True
    return False


def _asks_rebooked(spec):
    """True if the reading already asks about rentals booked ahead."""
    for q in spec.get("ambiguities", []) + spec.get("unknown_terms", []):
        text = q.get("question", "").lower()
        if "booked ahead" in text or "booked again" in text or "rebook" in text:
            return True
    return False


def _rebooked_open(spec):
    """A cancellation audience where nobody has decided yet about people who already booked again.

    Checked in code so the question is asked every time, whatever the reading did."""
    filters = [f.get("type") for f in spec.get("filters", [])]
    return ("cancelled_between" in filters
            and "has_upcoming_booking" not in filters and "no_upcoming_booking" not in filters
            and not spec.get("keep_people_booked_ahead"))


def validate(spec):
    """Questions the code adds on its own, whatever the reading said."""
    questions = []
    if _rebooked_open(spec) and not _asks_rebooked(spec):
        questions.append(REBOOKED_QUESTION)
    if not spec.get("channel"):
        if not _asks_channel(spec):
            questions.append(CHANNEL_QUESTION)
    elif spec["channel"] not in query.CHANNELS:
        questions.append({"question": "I can only build for email, push or SMS. Which one?",
                          "options": ["Email", "Push", "SMS"]})
    if spec.get("country") and spec["country"] not in query.COUNTRY_SPELLINGS:
        questions.append({"question": "There are no customers in '%s' in this data. Which market "
                                      "did you mean?" % spec["country"],
                          "options": sorted(query.COUNTRY_NAMES.values())})
    for f in spec.get("filters", []):
        if f.get("type") not in query.MENU:
            questions.append({"question": "I can't filter on '%s' yet. Can you describe it with "
                                          "bookings, app activity, loyalty tier or spend?"
                                          % f.get("type"), "options": []})
    return questions


def decide(spec):
    """Returns 'refuse', 'cannot_answer', 'ask' or 'build', in that order of priority."""
    if spec.get("rule_breaks"):
        return "refuse"
    if spec.get("missing_data"):
        return "cannot_answer"
    if spec.get("unknown_terms") or spec.get("ambiguities") or validate(spec):
        return "ask"
    return "build"


def count(conn, conditions, select="COUNT(*)"):
    where = "\n  AND ".join(conditions) if conditions else "1 = 1"
    sql = "SELECT %s FROM person p WHERE %s;" % (select, where)
    return conn.execute(sql).fetchone()[0] or 0


def run(spec):
    """Everything the answer needs."""
    verdict = decide(spec)
    result = {"verdict": verdict, "spec": spec}
    conn = connect()
    try:
        if verdict == "ask":
            result["questions"] = (
                [{"question": u["question"], "options": u.get("options", [])}
                 for u in spec.get("unknown_terms", [])]
                + spec.get("ambiguities", []) + validate(spec))
        elif verdict == "cannot_answer":
            gaps = [MISSING_DATA[k] for k in spec["missing_data"] if k in MISSING_DATA]
            result["gaps"] = gaps
            for gap in gaps:
                if gap.get("offer_filters"):
                    offer_spec = {"country": spec.get("country"), "filters": gap["offer_filters"]}
                    gap["offer_count"] = count(conn, query.who_conditions(offer_spec))
        elif verdict == "build":
            who = query.who_conditions(spec)
            steps = [("Matched your description", count(conn, who))]
            conditions = list(who)
            previous = steps[0][1]
            for label, cond in query.policy_conditions(spec["channel"]):
                conditions.append(cond)
                now = count(conn, conditions)
                steps.append((label, previous - now))
                previous = now
            result["steps"] = steps
            result["final"] = previous
            if previous == 0:
                # Nobody left: show what the other channels would reach, with their own consent.
                result["alternatives"] = {
                    ch: count(conn, who + [c for _, c in query.policy_conditions(ch)])
                    for ch in query.CHANNELS if ch != spec["channel"]}
            result["records"] = count(conn, who, "SUM(p.records)")
            result["sql"] = query.audience_sql(spec)
            where = "\n  AND ".join(conditions)
            result["people"] = [r[0] for r in conn.execute(
                "SELECT p.person FROM person p WHERE %s ORDER BY p.person" % where)]
            if spec.get("country"):
                result["spellings"] = [r[0] for r in conn.execute(
                    "SELECT DISTINCT country_residence FROM customers WHERE upper(trim("
                    "country_residence)) IN (%s) ORDER BY 1" % ", ".join(
                        "'%s'" % s for s in query.COUNTRY_SPELLINGS[spec["country"]]))]
    finally:
        conn.close()
    return result
