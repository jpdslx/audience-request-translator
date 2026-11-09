"""Checks that the tool gives the right answer, and that its counts are right.

Run: python3 -m unittest discover tests

The recount tests rebuild the two buildable audiences a second, independent way: plain Python
over the raw tables, without any of the tool's SQL. If both ways agree, the count is right.
"""
import datetime
import glob
import json
import os
import sqlite3
import unittest

from audience import engine, query

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.date(2026, 11, 6)


def load(name):
    with open(os.path.join(ROOT, "examples", name + ".json")) as fh:
        return json.load(fh)


class Recount:
    """The audience rules, written again in plain Python."""

    SPELLINGS = {"ES": {"es", "esp", "spain"}, "PT": {"pt", "prt", "portugal"}}

    def __init__(self):
        conn = sqlite3.connect(engine.DB_PATH)
        conn.row_factory = sqlite3.Row
        self.customers = [dict(r) for r in conn.execute("SELECT * FROM customers")]
        self.consent = [dict(r) for r in conn.execute("SELECT * FROM consent")]
        self.bookings = [dict(r) for r in conn.execute("SELECT * FROM bookings")]
        self.events = [dict(r) for r in conn.execute("SELECT * FROM app_events")]
        self.complaints = [dict(r) for r in conn.execute("SELECT * FROM complaints")]
        conn.close()
        self.person_of = {c["customer_id"]: c["email_hash"] for c in self.customers}

    def people_in(self, country):
        return {c["email_hash"] for c in self.customers
                if c["country_residence"].strip().lower() in self.SPELLINGS[country]}

    def consented(self, channel):
        latest = {}  # person -> (timestamp, set of statuses at that timestamp)
        for row in self.consent:
            if row["channel"] != channel:
                continue
            person = self.person_of[row["customer_id"]]
            ts, statuses = latest.get(person, ("", set()))
            if row["updated_at"] > ts:
                latest[person] = (row["updated_at"], {row["status"]})
            elif row["updated_at"] == ts:
                statuses.add(row["status"])
        return {p for p, (_, s) in latest.items() if s == {"granted"}}

    def bounced(self):
        return {c["email_hash"] for c in self.customers if c["email_status"] == "bounced"}

    def open_complaint(self):
        return {self.person_of[k["customer_id"]] for k in self.complaints if k["status"] == "open"}


class RecountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Recount()

    def tool_count(self, name):
        return engine.run(load(name))["final"]

    def test_request_1_spain_email(self):
        r = self.r
        start = (TODAY - datetime.timedelta(days=365)).isoformat()
        recent = {r.person_of[b["customer_id"]] for b in r.bookings
                  if b["status"] == "completed" and start < b["return_date"] <= TODAY.isoformat()}
        expected = (r.people_in("ES") & recent & r.consented("email")) - r.bounced() - r.open_complaint()
        self.assertEqual(self.tool_count("1_spain_email_recent"), len(expected))

    def test_saved_query_gives_the_same_count(self):
        # The self-contained query handed to Analytics must match what the tool reports.
        result = engine.run(load("1_spain_email_recent"))
        conn = sqlite3.connect(engine.DB_PATH)
        self.assertEqual(conn.execute(result["sql"]).fetchone()[0], result["final"])
        conn.close()

    def test_request_3_portugal_push(self):
        r = self.r
        start = (TODAY - datetime.timedelta(days=30)).isoformat()
        opened = {r.person_of[e["customer_id"]] for e in r.events
                  if e["event_type"] == "app_open" and start < e["event_ts"][:10] <= TODAY.isoformat()}
        upcoming = {r.person_of[b["customer_id"]] for b in r.bookings
                    if b["status"] == "confirmed" and b["pickup_date"] >= TODAY.isoformat()}
        expected = ((r.people_in("PT") & opened) - upcoming) & r.consented("push")
        expected -= r.open_complaint()  # bounced email doesn't matter for push
        self.assertEqual(self.tool_count("3_portugal_app_push"), len(expected))


class VerdictTests(unittest.TestCase):
    """Each of the six requests gets the right kind of answer."""

    EXPECTED = {
        "1_spain_email_recent": "build",
        "2_germany_high_value": "ask",
        "3_portugal_app_push": "build",
        "4_cancelled_october": "ask",
        "5_likely_to_churn": "cannot_answer",
        "6_dormant_service_message": "refuse",
    }

    def test_six_requests(self):
        for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.json"))):
            name = os.path.splitext(os.path.basename(path))[0]
            with self.subTest(name):
                self.assertEqual(engine.decide(load(name)), self.EXPECTED[name])

    def test_missing_channel_always_asks(self):
        spec = dict(load("1_spain_email_recent"), channel=None)
        self.assertEqual(engine.decide(spec), "ask")

    def test_rule_break_beats_everything(self):
        spec = dict(load("1_spain_email_recent"), rule_breaks=["bypass_consent"])
        self.assertEqual(engine.decide(spec), "refuse")

    def test_asking_to_include_complaints_is_refused(self):
        spec = dict(load("1_spain_email_recent"), rule_breaks=["include_open_complaints"])
        self.assertEqual(engine.run(spec)["verdict"], "refuse")

    def test_answers_only_explain_what_the_request_touched(self):
        # Live test, 8 Nov: a request about complaints was also told about bounced emails, because
        # one message covered two rules. Each rule now has its own message; this checks every rule
        # and every missing-data case, so a new one can't bring the problem back.
        from audience import render
        base = load("1_spain_email_recent")
        self.assertEqual(set(engine.RULE_BREAKS), set(engine.RULE_BREAK_ALTERNATIVES))
        for key in engine.RULE_BREAKS:
            with self.subTest(rule=key):
                text = render.render(engine.run(dict(base, rule_breaks=[key])))
                self.assertIn(engine.RULE_BREAKS[key], text)
                for other, message in engine.RULE_BREAKS.items():
                    if other != key:
                        self.assertNotIn(message, text)
        for key in engine.MISSING_DATA:
            with self.subTest(missing=key):
                text = render.render(engine.run(dict(base, missing_data=[key])))
                for other, gap in engine.MISSING_DATA.items():
                    if other != key:
                        self.assertNotIn(gap["why"], text)

    def test_every_offered_switch_can_be_built(self):
        # Each "I can switch to..." in an answer must point to a filter that exists (story 1 again).
        switches = {"completed_booking_within": "completed_booking_made_within",
                    "completed_booking_made_within": "completed_booking_within",
                    "no_booking_created_within": "no_completed_booking_within",
                    "no_completed_booking_within": "no_booking_created_within"}
        for offered in switches.values():
            self.assertIn(offered, query.MENU)

    def test_channel_is_asked_once(self):
        # If the reading already asks "email or push?", the code doesn't add a second channel question.
        spec = dict(load("1_spain_email_recent"), channel=None,
                    ambiguities=[{"question": "Email or push?", "options": ["Email", "Push"]}])
        self.assertEqual(len(engine.validate(spec)), 0)
        self.assertEqual(engine.decide(spec), "ask")

    def test_refusal_offers_fit_the_rule_broken(self):
        # Asking to include complaints must not get the service-message advice.
        from audience import render
        spec = dict(load("1_spain_email_recent"), rule_breaks=["include_open_complaints"])
        self.assertNotIn("Legal", render.render(engine.run(spec)))

    CANCELLED = {"request": "Everybody who cancelled in October.", "country": None, "channel": "email",
                 "filters": [{"type": "cancelled_between", "basis": "cancellation_date",
                              "start": "2026-10-01", "end": "2026-10-31"}]}

    def test_cancellations_always_ask_about_rebooking(self):
        # Live test, 8 Nov: the reading skipped this question. The code now asks it itself.
        result = engine.run(dict(self.CANCELLED))
        self.assertEqual(result["verdict"], "ask")
        self.assertIn("booked ahead", result["questions"][0]["question"])

    def test_rebooking_question_is_asked_once(self):
        spec = dict(self.CANCELLED, ambiguities=[
            {"question": "Leave out people with a rental booked ahead?", "options": ["Yes", "No"]}])
        self.assertEqual(len(engine.run(spec)["questions"]), 1)

    def test_rebooking_answer_lets_it_build(self):
        out = dict(self.CANCELLED, filters=self.CANCELLED["filters"] + [{"type": "no_upcoming_booking"}])
        keep = dict(self.CANCELLED, keep_people_booked_ahead=True)
        self.assertEqual(engine.decide(out), "build")
        self.assertEqual(engine.decide(keep), "build")

    def test_no_field_names_in_questions(self):
        # Live test, 8 Nov: options showed names like "(no_upcoming_booking)".
        from audience import render
        spec = dict(self.CANCELLED, ambiguities=[{"question": "By `pickup_date`?", "options": [
            "Leave them out (no_upcoming_booking)", "Cancelled during October (cancellation_date in Oct)"]}])
        text = render.render(engine.run(spec))
        self.assertNotRegex(text.split("\n", 2)[2], r"[a-z]+_[a-z]+")
        self.assertIn("a) Leave them out\n", text)

    def test_every_time_filter_states_its_meaning(self):
        # Story 2: a reading the manager can't see is a reading they can't correct.
        from audience import render
        timed = [k for k, v in query.MENU.items() if "months" in v or "days" in v]
        for t in timed:
            with self.subTest(t):
                self.assertIsNotNone(render.assumption({"type": t, "months": 12, "days": 30, "eur": 1000}))

    def test_no_market_is_stated(self):
        # Live test, 8 Nov: "everyone" didn't say it meant all markets. An assumption is always shown.
        from audience import render
        ask = render.render(engine.run({"request": "everyone", "channel": None, "filters": []}))
        self.assertIn("all markets (no market named)", ask)
        built = render.render(engine.run({"request": "everyone", "channel": "email", "filters": []}))
        self.assertIn(render.NO_MARKET, built)
        spain = render.render(engine.run(load("1_spain_email_recent")))
        self.assertNotIn(render.NO_MARKET, spain)

    def test_filter_not_on_menu_asks(self):
        spec = dict(load("1_spain_email_recent"), filters=[{"type": "made_up_score"}])
        self.assertEqual(engine.decide(spec), "ask")


class RuleTests(unittest.TestCase):
    """The tricky rules, checked on a small hand-made database."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript("""
            CREATE TABLE customers(customer_id, email_hash, country_residence, language,
                                   loyalty_tier, created_at, merged_into, email_status, has_app);
            CREATE TABLE consent(consent_id, customer_id, channel, status, updated_at, source);
            CREATE TABLE bookings(booking_id, customer_id, booking_channel, created_at, pickup_date,
                                  return_date, pickup_station, vehicle_class, net_revenue_eur,
                                  status, cancelled_at);
            CREATE TABLE app_events(event_id, customer_id, event_type, event_ts);
            CREATE TABLE complaints(complaint_id, customer_id, opened_at, closed_at, status, topic);
        """)

    def add_customer(self, cid, person, country="DE", status="active"):
        self.conn.execute("INSERT INTO customers VALUES (?,?,?,'de','Base','2020-01-01',NULL,?,0)",
                          (cid, person, country, status))

    def add_consent(self, cid, channel, status, ts):
        self.conn.execute("INSERT INTO consent VALUES (NULL,?,?,?,?,'app')", (cid, channel, status, ts))

    def audience(self, channel="email", country="DE"):
        spec = {"country": country, "channel": channel, "filters": []}
        conds = query.who_conditions(spec) + [c for _, c in query.policy_conditions(channel)]
        engine.prepare(self.conn)
        return engine.count(self.conn, conds)

    def test_every_country_spelling_counts(self):
        for i, spelling in enumerate(["DE", "DEU", "Germany", "de"]):
            self.add_customer(i, "p%d" % i, spelling)
            self.add_consent(i, "email", "granted", "2025-01-01 10:00:00")
        self.assertEqual(self.audience(), 4)

    def test_duplicates_count_once(self):
        for cid in (1, 2):
            self.add_customer(cid, "same_person")
            self.add_consent(cid, "email", "granted", "2025-01-01 10:00:00")
        self.assertEqual(self.audience(), 1)

    def test_latest_consent_across_records_wins(self):
        self.add_customer(1, "p")
        self.add_customer(2, "p")
        self.add_consent(1, "email", "granted", "2024-01-01 10:00:00")
        self.add_consent(2, "email", "revoked", "2025-01-01 10:00:00")
        self.assertEqual(self.audience(), 0)

    def test_equally_recent_disagreement_is_no(self):
        self.add_customer(1, "p")
        self.add_customer(2, "p")
        self.add_consent(1, "email", "granted", "2025-01-01 10:00:00")
        self.add_consent(2, "email", "revoked", "2025-01-01 10:00:00")
        self.assertEqual(self.audience(), 0)

    def test_no_consent_record_means_no(self):
        self.add_customer(1, "p")
        self.assertEqual(self.audience(), 0)

    def test_email_consent_does_not_count_for_push(self):
        self.add_customer(1, "p")
        self.add_consent(1, "email", "granted", "2025-01-01 10:00:00")
        self.assertEqual(self.audience(channel="push"), 0)

    def test_bounced_only_blocks_email(self):
        self.add_customer(1, "p", status="bounced")
        self.add_consent(1, "email", "granted", "2025-01-01 10:00:00")
        self.add_consent(1, "push", "granted", "2025-01-01 10:00:00")
        self.assertEqual(self.audience(channel="email"), 0)
        self.assertEqual(self.audience(channel="push"), 1)

    def test_language_is_separate_from_country(self):
        self.add_customer(1, "p1", "DE")  # language 'de' (default in add_customer)
        self.conn.execute("INSERT INTO customers VALUES (2,'p2','DE','en','Base','2020-01-01',NULL,'active',0)")
        for cid in (1, 2):
            self.add_consent(cid, "email", "granted", "2025-01-01 10:00:00")
        spec = {"country": None, "channel": "email", "filters": [{"type": "language_in", "languages": ["de"]}]}
        conds = query.who_conditions(spec) + [c for _, c in query.policy_conditions("email")]
        engine.prepare(self.conn)
        self.assertEqual(engine.count(self.conn, conds), 1)
        self.assertEqual(self.audience(), 2)  # both live in Germany

    def test_open_complaint_blocks_all_channels(self):
        self.add_customer(1, "p")
        self.add_consent(1, "push", "granted", "2025-01-01 10:00:00")
        self.conn.execute("INSERT INTO complaints VALUES (1,1,'2026-10-01',NULL,'open','billing')")
        self.assertEqual(self.audience(channel="push"), 0)


if __name__ == "__main__":
    unittest.main()
