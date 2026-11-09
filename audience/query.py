"""Builds the SQL for an audience from a structured request.

Everything here is fixed code. The AI never writes SQL: it only picks filters from the menu below,
and this module turns them into tested building blocks. The data clean-up and the audience policy
are applied to every query, whatever the request says.
"""

TODAY = "2026-11-06"  # "today" for this exercise, set by the data catalogue

# Every way a country is written in the data, mapped to one code.
COUNTRY_SPELLINGS = {
    "DE": ["DE", "DEU", "GERMANY"],
    "ES": ["ES", "ESP", "SPAIN"],
    "FR": ["FR", "FRA", "FRANCE"],
    "IT": ["IT", "ITA", "ITALY"],
    "NL": ["NL", "NLD", "NETHERLANDS"],
    "PT": ["PT", "PRT", "PORTUGAL"],
}
COUNTRY_NAMES = {"DE": "Germany", "ES": "Spain", "FR": "France", "IT": "Italy",
                 "NL": "the Netherlands", "PT": "Portugal"}
CHANNELS = ["email", "push", "sms"]
LANGUAGES = {"de": "German", "en": "English", "es": "Spanish", "fr": "French", "it": "Italian",
             "nl": "Dutch", "pt": "Portuguese"}
TIERS = ["Base", "Silver", "Gold", "Platinum"]

# The menu: the only filters the tool knows how to apply.
MENU = {
    "completed_booking_within": "completed rental that ended in the last N months (months)",
    "completed_booking_made_within": "completed rental that was booked in the last N months (months)",
    "no_completed_booking_within": "no completed rental in the last N months (months)",
    "min_completed_rentals": "at least N completed rentals ever (count)",
    "has_upcoming_booking": "has a confirmed booking with a future pickup",
    "no_upcoming_booking": "has no confirmed booking with a future pickup",
    "app_opened_within": "opened the app in the last N days (days)",
    "loyalty_tier_in": "loyalty tier is one of the listed tiers (tiers)",
    "language_in": "preferred language is one of the listed languages (languages)",
    "no_booking_created_within": "made no new booking in the last N months (months)",
    "min_spend_within": "spent at least X EUR on completed rentals in the last N months (months, eur)",
    "cancelled_between": "cancelled a booking, by cancellation date or by pickup date (basis, start, end)",
}


def _country_case():
    parts = []
    for code, spellings in COUNTRY_SPELLINGS.items():
        values = ", ".join("'%s'" % s for s in spellings)
        parts.append("WHEN upper(trim(country_residence)) IN (%s) THEN '%s'" % (values, code))
    return "CASE " + " ".join(parts) + " END"


CLEANUP_INDEXES = [
    "rec(customer_id)", "rec(person)", "person(person)", "consent_now(person, channel)",
    "bk(person)", "ev(person)", "complaint(person)",
]


def cleanup_tables():
    """The clean-up layer as (name, query) pairs, in the order they depend on each other."""
    body = base_ctes()[len("WITH "):]
    tables = []
    for chunk in body.split("\n),\n"):
        name, sql = chunk.split(" AS (\n", 1)
        tables.append((name.strip(), sql.rstrip().rstrip(")").rstrip()))
    return tables


def base_ctes():
    """The clean-up layer, shared by every query.

    - rec:         one row per customer record, country written one way
    - person:      one row per person (records sharing an email address are one person)
    - consent_now: each person's consent per channel, from their most recent record across all
                   their customer records; equally recent records that disagree count as revoked
    - bk / ev:     bookings and app events, attached to the person
    - complaint:   people with an open complaint on any of their records
    """
    return """WITH rec AS (
  SELECT customer_id, email_hash AS person, %(country)s AS country,
         language, loyalty_tier, email_status
  FROM customers
),
person AS (
  SELECT person,
         MIN(country) AS country,
         MAX(email_status = 'bounced') AS bounced,
         MAX(CASE loyalty_tier WHEN 'Base' THEN 1 WHEN 'Silver' THEN 2
                               WHEN 'Gold' THEN 3 WHEN 'Platinum' THEN 4 END) AS tier_rank,
         COUNT(*) AS records
  FROM rec GROUP BY person
),
cons AS (
  SELECT r.person, c.channel, c.status, c.updated_at
  FROM consent c JOIN rec r ON r.customer_id = c.customer_id
),
cons_last AS (
  SELECT person, channel, MAX(updated_at) AS ts FROM cons GROUP BY person, channel
),
consent_now AS (
  SELECT l.person, l.channel,
         CASE WHEN SUM(c.status = 'revoked') > 0 THEN 'revoked' ELSE 'granted' END AS status
  FROM cons_last l
  JOIN cons c ON c.person = l.person AND c.channel = l.channel AND c.updated_at = l.ts
  GROUP BY l.person, l.channel
),
bk AS (
  SELECT r.person, b.*,
         CASE WHEN b.status IN ('cancelled', 'canceled') THEN 'cancelled' ELSE b.status END AS st
  FROM bookings b JOIN rec r ON r.customer_id = b.customer_id
),
ev AS (
  SELECT r.person, e.event_type, date(e.event_ts) AS day
  FROM app_events e JOIN rec r ON r.customer_id = e.customer_id
),
complaint AS (
  SELECT DISTINCT r.person
  FROM complaints k JOIN rec r ON r.customer_id = k.customer_id
  WHERE k.status = 'open'
)""" % {"country": _country_case()}


def filter_sql(f):
    """One menu filter as a SQL condition on person p."""
    t = f["type"]
    today = "'%s'" % TODAY
    if t == "completed_booking_within":
        return ("EXISTS (SELECT 1 FROM bk WHERE bk.person = p.person AND bk.st = 'completed' "
                "AND bk.return_date > date(%s, '-%d months') AND bk.return_date <= %s)"
                % (today, f["months"], today))
    if t == "completed_booking_made_within":
        return ("EXISTS (SELECT 1 FROM bk WHERE bk.person = p.person AND bk.st = 'completed' "
                "AND bk.created_at > date(%s, '-%d months') AND bk.created_at <= %s)"
                % (today, f["months"], today))
    if t == "no_completed_booking_within":
        return ("NOT EXISTS (SELECT 1 FROM bk WHERE bk.person = p.person AND bk.st = 'completed' "
                "AND bk.return_date > date(%s, '-%d months'))" % (today, f["months"]))
    if t == "min_completed_rentals":
        return ("(SELECT COUNT(*) FROM bk WHERE bk.person = p.person AND bk.st = 'completed') >= %d"
                % f["count"])
    if t == "has_upcoming_booking":
        return ("EXISTS (SELECT 1 FROM bk WHERE bk.person = p.person AND bk.st = 'confirmed' "
                "AND bk.pickup_date >= %s)" % today)
    if t == "no_upcoming_booking":
        return ("NOT EXISTS (SELECT 1 FROM bk WHERE bk.person = p.person AND bk.st = 'confirmed' "
                "AND bk.pickup_date >= %s)" % today)
    if t == "app_opened_within":
        return ("EXISTS (SELECT 1 FROM ev WHERE ev.person = p.person AND ev.event_type = 'app_open' "
                "AND ev.day > date(%s, '-%d days') AND ev.day <= %s)" % (today, f["days"], today))
    if t == "loyalty_tier_in":
        ranks = ", ".join(str(TIERS.index(x) + 1) for x in f["tiers"])
        return "p.tier_rank IN (%s)" % ranks
    if t == "language_in":
        codes = ", ".join("'%s'" % x for x in f["languages"])
        return ("EXISTS (SELECT 1 FROM rec r WHERE r.person = p.person AND lower(r.language) IN (%s))"
                % codes)
    if t == "no_booking_created_within":
        return ("NOT EXISTS (SELECT 1 FROM bk WHERE bk.person = p.person "
                "AND bk.created_at > date(%s, '-%d months'))" % (today, f["months"]))
    if t == "min_spend_within":
        return ("(SELECT COALESCE(SUM(bk.net_revenue_eur), 0) FROM bk WHERE bk.person = p.person "
                "AND bk.st = 'completed' AND bk.return_date > date(%s, '-%d months')) >= %s"
                % (today, f["months"], float(f["eur"])))
    if t == "cancelled_between":
        col = "cancelled_at" if f["basis"] == "cancellation_date" else "pickup_date"
        return ("EXISTS (SELECT 1 FROM bk WHERE bk.person = p.person AND bk.st = 'cancelled' "
                "AND bk.%s BETWEEN '%s' AND '%s')" % (col, f["start"], f["end"]))
    raise ValueError("Not on the menu: %s" % t)


def who_conditions(spec):
    """The conditions that describe who the manager asked for (before the policy rules)."""
    conds = []
    if spec.get("country"):
        conds.append("p.country = '%s'" % spec["country"])
    conds += [filter_sql(f) for f in spec.get("filters", [])]
    return conds


def policy_conditions(channel):
    """The audience policy. Always applied, in this order, whatever the request says."""
    steps = [
        ("No %s consent" % ("SMS" if channel == "sms" else channel),
         "EXISTS (SELECT 1 FROM consent_now cn WHERE cn.person = p.person "
         "AND cn.channel = '%s' AND cn.status = 'granted')" % channel),
    ]
    if channel == "email":
        steps.append(("Email bounced", "p.bounced = 0"))
    steps.append(("Open complaint", "p.person NOT IN (SELECT person FROM complaint)"))
    return steps


def audience_sql(spec, select="COUNT(*)"):
    """The full, self-contained query for the final audience."""
    conds = who_conditions(spec) + [c for _, c in policy_conditions(spec["channel"])]
    where = "\n  AND ".join(conds) if conds else "1 = 1"
    return "%s\nSELECT %s\nFROM person p\nWHERE %s;" % (base_ctes(), select, where)
