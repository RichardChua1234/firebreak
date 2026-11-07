"""Test suite for Firebreak. Standard library only -- no pytest needed:

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import datetime as _dt
import os
import pathlib
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from firebreak import guard, policy as policy_mod, risk as risk_mod   # noqa: E402
from firebreak.ledger import Ledger                                     # noqa: E402
from firebreak.models import PaymentRequest, normalise_merchant         # noqa: E402
from firebreak.paypal_api import MockPayPal, PayPalError                # noqa: E402

POLICY = ("Never pay more than $50 without asking me. "
          "Hard limit of $300 a day and $2000 a month. "
          "Never pay sketchy-ads-ltd. Only use USD. "
          "If I've never paid a merchant before, check with me first.")


def hist(days_ago: int, merchant: str, amount: str, status: str = "COMPLETED") -> dict:
    when = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days_ago)
    return {"merchant": merchant, "amount": amount, "currency": "USD",
            "date": when.isoformat(timespec="seconds"), "status": status,
            "transaction_id": f"t-{merchant}-{days_ago}"}


class TestPolicyCompilation(unittest.TestCase):
    def setUp(self):
        self.p = policy_mod.compile_policy(POLICY, use_ai=False)

    def test_compiles_without_a_model(self):
        self.assertEqual(self.p.compiled_by, "deterministic")

    def test_extracts_every_stated_limit(self):
        kinds = {r.kind for r in self.p.rules}
        self.assertEqual(kinds, {
            policy_mod.REQUIRE_APPROVAL_ABOVE, policy_mod.DAILY_CAP,
            policy_mod.MONTHLY_CAP, policy_mod.MERCHANT_BLOCK,
            policy_mod.CURRENCY_ALLOW, policy_mod.BLOCK_NEW_MERCHANTS})

    def test_two_limits_in_one_sentence_both_survive(self):
        """'$300 a day and $2000 a month' must yield two rules, not one."""
        caps = {r.kind: r.params["amount"] for r in self.p.rules
                if r.kind in (policy_mod.DAILY_CAP, policy_mod.MONTHLY_CAP)}
        self.assertEqual(caps[policy_mod.DAILY_CAP], "300")
        self.assertEqual(caps[policy_mod.MONTHLY_CAP], "2000")

    def test_keeps_the_english_it_came_from(self):
        for r in self.p.rules:
            self.assertTrue(r.source, f"{r.rule_id} lost its source text")

    def test_unknown_rule_kinds_are_refused_not_guessed(self):
        """A model inventing a rule kind must not silently become policy."""
        rules = policy_mod._rules_from_ai([
            {"kind": "wire_transfer_everything", "params": {}},
            {"kind": policy_mod.DAILY_CAP, "params": {"amount": 100}},
        ])
        self.assertEqual([r.kind for r in rules], [policy_mod.DAILY_CAP])


class TestMerchantFolding(unittest.TestCase):
    def test_the_same_merchant_written_three_ways(self):
        keys = {normalise_merchant(x) for x in
                ("Sketchy Ads Ltd", "sketchy-ads-ltd", "Sketchy  Ads  LTD.")}
        self.assertEqual(len(keys), 1)

    def test_ban_fires_against_a_differently_punctuated_name(self):
        """Regression: the do-not-pay rule silently missed 'Sketchy Ads Ltd'."""
        p = policy_mod.compile_policy(POLICY, use_ai=False)
        d = policy_mod.evaluate(p, PaymentRequest.build("Sketchy Ads Ltd", "20.00"))
        self.assertEqual(d.action, "BLOCK")


class TestEnforcement(unittest.TestCase):
    def setUp(self):
        self.p = policy_mod.compile_policy(POLICY, use_ai=False)
        self.known = [hist(60, "Acme Hosting", "45.00"), hist(70, "Figma", "15.00")]

    def ev(self, merchant, amount, history=None, purpose="test"):
        req = PaymentRequest.build(merchant, amount, purpose=purpose)
        risk = risk_mod.analyze(req, history or [])
        return policy_mod.evaluate(self.p, req, history or [], risk)

    def test_small_payment_to_a_known_merchant_is_auto_approved(self):
        d = self.ev("Figma", "15.00", self.known)
        self.assertEqual(d.action, "AUTO_APPROVE", d.explain())

    def test_above_the_ceiling_escalates(self):
        self.assertEqual(self.ev("Acme Hosting", "180.00", self.known).action, "ESCALATE")

    def test_exactly_at_the_ceiling_is_allowed(self):
        """Boundary: $50 is not 'more than $50'.

        Uses policy-only evaluation so the assertion isolates the ceiling rule --
        the risk engine would (correctly) escalate this as a 3.3x outlier.
        """
        req = PaymentRequest.build("Figma", "50.00", purpose="boundary")
        self.assertEqual(policy_mod.evaluate(self.p, req, self.known).action, "AUTO_APPROVE")

    def test_one_cent_over_escalates(self):
        req = PaymentRequest.build("Figma", "50.01", purpose="boundary")
        self.assertEqual(policy_mod.evaluate(self.p, req, self.known).action, "ESCALATE")

    def test_daily_cap_blocks(self):
        d = self.ev("Acme Hosting", "320.00", self.known + [hist(0, "Acme Hosting", "20.00")])
        self.assertEqual(d.action, "BLOCK", d.explain())

    def test_monthly_cap_blocks(self):
        heavy = [hist(2, "Acme Hosting", "1900.00")]
        self.assertEqual(self.ev("Acme Hosting", "200.00", heavy).action, "BLOCK")

    def test_unseen_merchant_escalates(self):
        self.assertEqual(self.ev("Northwind Supplies", "30.00", self.known).action, "ESCALATE")

    def test_wrong_currency_blocks(self):
        req = PaymentRequest.build("Figma", "15.00", currency="SGD", purpose="x")
        self.assertEqual(policy_mod.evaluate(self.p, req, self.known).action, "BLOCK")

    def test_block_wins_over_escalate(self):
        """A banned merchant that is also new must BLOCK, not merely escalate."""
        d = self.ev("Sketchy Ads Ltd", "20.00", self.known)
        self.assertEqual(d.action, "BLOCK")
        self.assertTrue(any("do-not-pay" in r for r in d.reasons))

    def test_same_inputs_give_the_same_verdict(self):
        a = self.ev("Figma", "15.00", self.known)
        b = self.ev("Figma", "15.00", self.known)
        self.assertEqual((a.action, a.reasons, a.policy_hits),
                         (b.action, b.reasons, b.policy_hits))

    def test_purpose_required_escalates(self):
        p = policy_mod.compile_policy("Every payment must state a purpose.", use_ai=False)
        req = PaymentRequest.build("Figma", "15.00", purpose="")
        self.assertEqual(policy_mod.evaluate(p, req, self.known).action, "ESCALATE")

    def test_velocity_limit_blocks(self):
        p = policy_mod.compile_policy("No more than 2 payments a day.", use_ai=False)
        vh = [hist(0, "Figma", "5.00"), hist(0, "Figma", "5.00")]
        req = PaymentRequest.build("Figma", "5.00", purpose="x")
        self.assertEqual(policy_mod.evaluate(p, req, vh).action, "BLOCK")


class TestRiskEngine(unittest.TestCase):
    def test_duplicate_is_high_severity(self):
        h = [hist(3, "Figma", "15.00")]
        findings = risk_mod.analyze(PaymentRequest.build("Figma", "15.00"), h)
        self.assertIn("possible_duplicate", [f.code for f in findings])
        self.assertTrue(any(f.severity == "high" for f in findings))

    def test_price_increase_is_detected(self):
        h = [hist(20, "Acme", "10.00")]
        findings = risk_mod.analyze(PaymentRequest.build("Acme", "12.00"), h)
        self.assertIn("price_increase", [f.code for f in findings])

    def test_small_escalation_is_not_flagged(self):
        h = [hist(20, "Acme", "10.00")]
        findings = risk_mod.analyze(PaymentRequest.build("Acme", "10.50"), h)
        self.assertNotIn("price_increase", [f.code for f in findings])

    def test_new_merchant_flagged(self):
        findings = risk_mod.analyze(PaymentRequest.build("Brand New", "10.00"), [])
        self.assertEqual([f.code for f in findings], ["new_merchant"])

    def test_risk_never_auto_approves(self):
        """A risky payment escalates; risk findings can never yield AUTO_APPROVE."""
        p = policy_mod.compile_policy("No limits at all.", use_ai=False)
        req = PaymentRequest.build("Figma", "15.00", purpose="dup")
        h = [hist(1, "Figma", "15.00")]
        risk = risk_mod.analyze(req, h)
        self.assertEqual(policy_mod.evaluate(p, req, h, risk).action, "ESCALATE")


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "ledger.jsonl")

    def test_chain_verifies(self):
        lg = Ledger(self.path)
        for i in range(5):
            lg.append("decision", {"n": i})
        ok, problems = lg.verify()
        self.assertTrue(ok, problems)
        self.assertEqual(lg.count(), 5)

    def test_editing_a_record_is_detected(self):
        lg = Ledger(self.path)
        lg.append("decision", {"amount": "180.00"})
        lg.append("decision", {"amount": "15.00"})
        raw = pathlib.Path(self.path).read_text().replace("180.00", "1.80")
        pathlib.Path(self.path).write_text(raw)
        ok, problems = Ledger(self.path).verify()
        self.assertFalse(ok)
        self.assertTrue(problems)

    def test_deleting_a_record_is_detected(self):
        lg = Ledger(self.path)
        for i in range(4):
            lg.append("decision", {"n": i})
        lines = pathlib.Path(self.path).read_text().splitlines()
        pathlib.Path(self.path).write_text("\n".join(lines[:1] + lines[2:]) + "\n")
        ok, _ = Ledger(self.path).verify()
        self.assertFalse(ok)


class TestPayPalClient(unittest.TestCase):
    def test_cannot_capture_an_unapproved_order(self):
        """The real API refuses this; the mock must refuse it too."""
        pp = MockPayPal()
        order = pp.create_order(PaymentRequest.build("Figma", "15.00"))
        with self.assertRaises(PayPalError):
            pp.capture_order(order["id"])

    def test_approved_order_captures_and_lands_in_history(self):
        pp = MockPayPal()
        req = PaymentRequest.build("Figma", "15.00")
        order = pp.create_order(req)
        pp.approve(order["id"])
        res = pp.capture_order(order["id"])
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(len(pp.list_transactions()), 1)

    def test_payout_records_a_transaction(self):
        pp = MockPayPal()
        pp.send_payout(PaymentRequest.build("Acme", "45.00"))
        self.assertEqual(len(pp.list_transactions()), 1)

    def test_approve_url_is_exposed_for_the_human_gate(self):
        pp = MockPayPal()
        order = pp.create_order(PaymentRequest.build("Figma", "15.00"))
        self.assertTrue(pp.approve_url(order).startswith("http"))


class TestOrchestration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = os.path.join(self.tmp, "l.jsonl")
        self.policy = policy_mod.compile_policy(POLICY, use_ai=False)
        self.paypal = MockPayPal(history=[hist(90, "Figma", "15.00")])
        self.fb = guard.Firebreak(self.paypal, self.policy, ledger_path=self.ledger,
                                  use_ai=False, mode="payouts")

    def test_auto_approved_payment_actually_moves_money(self):
        d, result = self.fb.act(PaymentRequest.build("Figma", "15.00", purpose="seat"))
        self.assertEqual(d.action, "AUTO_APPROVE")
        self.assertIn("batch_header", result)

    def test_blocked_payment_creates_nothing(self):
        d, result = self.fb.act(PaymentRequest.build("Sketchy Ads Ltd", "20.00", purpose="ads"))
        self.assertEqual(d.action, "BLOCK")
        self.assertIsNone(result)
        self.assertEqual(len(self.paypal.transactions), 1)   # only the seed

    def test_escalated_payment_is_held_and_logged(self):
        # over the $50 ceiling but *under* the $300 daily cap, so it escalates
        # rather than blocking -- otherwise this would test the cap, not the hold
        d, _ = self.fb.act(PaymentRequest.build("Acme", "120.00", purpose="big"))
        self.assertEqual(d.action, "ESCALATE")
        events = [e["event"] for e in Ledger(self.ledger).entries()]
        self.assertIn("awaiting_human", events)

    def test_every_request_is_recorded_including_refusals(self):
        self.fb.act(PaymentRequest.build("Figma", "15.00", purpose="a"))
        self.fb.act(PaymentRequest.build("Sketchy Ads Ltd", "20.00", purpose="b"))
        events = [e["event"] for e in Ledger(self.ledger).entries()]
        self.assertIn("executed", events)
        self.assertIn("refused", events)

    def test_human_approval_is_attributed_by_name(self):
        pp = MockPayPal()
        fb = guard.Firebreak(pp, self.policy, ledger_path=os.path.join(self.tmp, "l2.jsonl"),
                             use_ai=False, mode="orders")
        order = pp.create_order(PaymentRequest.build("Acme", "500.00"))
        pp.approve(order["id"])
        fb.confirm(order["id"], approved_by="richard")
        executed = [e for e in Ledger(os.path.join(self.tmp, "l2.jsonl")).entries()
                    if e["event"] == "executed"]
        self.assertEqual(executed[-1]["payload"]["approved_by"], "richard")


class TestIntentFallback(unittest.TestCase):
    def test_parses_a_payment_sentence_without_a_model(self):
        req = guard.intent_from_text("pay Acme 180 for the hosting invoice", use_ai=False)
        self.assertEqual(req.amount, Decimal("180"))
        self.assertIn("acme", req.merchant.lower())

    def test_detects_currency(self):
        req = guard.intent_from_text("pay Figma 15 sgd", use_ai=False)
        self.assertEqual(req.currency, "SGD")

    def test_no_amount_is_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):
            guard.intent_from_text("please handle the invoice", use_ai=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
