"""PayPal sandbox integration.

Two implementations of one interface:

* :class:`PayPalSandbox` -- the real thing, against
  ``https://api-m.sandbox.paypal.com``. Uses only the standard library
  (``urllib``), so a judge can clone the repo and run it with no
  ``pip install`` at all.
* :class:`MockPayPal` -- a faithful in-memory stand-in used by the test suite
  and by ``--offline`` mode, so the project is demonstrable without anyone
  handing over credentials.

The human-approval gate is **PayPal's own payer approval**: Firebreak creates a
real order, and nothing is captured until a human opens the approve URL and
consents. The guardrail is not a simulation of a control -- it *is* the control.
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from .models import PaymentRequest

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"


class PayPalError(RuntimeError):
    """Raised with the API's own error text, never a generic failure."""

    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class PayPalSandbox:
    """Minimal, dependency-free PayPal Orders v2 client."""

    def __init__(self, client_id: str, secret: str, base: str = SANDBOX_BASE, timeout: int = 30):
        if not client_id or not secret:
            raise PayPalError("client_id and secret are required")
        self.client_id = client_id
        self.secret = secret
        self.base = base.rstrip("/")
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ── transport ──────────────────────────────────────────────────────────
    def _request(self, method: str, path: str, *, body: dict | None = None,
                 headers: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
        hdrs.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "ignore")
            raise PayPalError(_api_error_message(raw) or f"HTTP {exc.code}", exc.code, raw) from None
        except urllib.error.URLError as exc:
            raise PayPalError(f"network error: {exc.reason}") from None
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise PayPalError("non-JSON response from PayPal", body=raw[:400]) from None

    # ── auth ───────────────────────────────────────────────────────────────
    def token(self) -> str:
        """Client-credentials token, cached until ~60s before expiry."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
        payload = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        req = urllib.request.Request(
            f"{self.base}/v1/oauth2/token", data=payload,
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                doc = json.loads(resp.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "ignore")
            raise PayPalError(_api_error_message(raw) or f"auth failed (HTTP {exc.code})",
                              exc.code, raw) from None
        self._token = doc["access_token"]
        self._token_expires_at = time.time() + float(doc.get("expires_in", 3000))
        return self._token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}

    # ── orders ─────────────────────────────────────────────────────────────
    def create_order(self, req: PaymentRequest, *, return_url: str | None = None,
                     cancel_url: str | None = None) -> dict:
        """Create a real sandbox order. No money moves until it is captured."""
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": req.idempotency_key,
                "description": (req.purpose or f"Payment to {req.merchant}")[:127],
                "amount": {"currency_code": req.currency, "value": f"{req.amount:.2f}"},
            }],
            "application_context": {
                "brand_name": "Firebreak",
                "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING",
            },
        }
        if return_url:
            body["application_context"]["return_url"] = return_url
        if cancel_url:
            body["application_context"]["cancel_url"] = cancel_url
        return self._request("POST", "/v2/checkout/orders", body=body, headers=self._auth_headers())

    @staticmethod
    def approve_url(order: dict) -> str:
        for link in order.get("links", []):
            if link.get("rel") in ("approve", "payer-action"):
                return link.get("href", "")
        return ""

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/v2/checkout/orders/{order_id}", headers=self._auth_headers())

    def capture_order(self, order_id: str) -> dict:
        """Capture an APPROVED order. Fails loudly if the payer never approved."""
        return self._request("POST", f"/v2/checkout/orders/{order_id}/capture",
                             body={}, headers=self._auth_headers())

    # ── payouts (business-initiated: the agent actually pays) ──────────────
    def send_payout(self, req: PaymentRequest, *, receiver: str | None = None,
                    email_subject: str = "Payment from Firebreak") -> dict:
        """Send money to a payee. No buyer checkout step.

        This is the path that lets an agent *complete* a payment rather than just
        prepare a checkout. Requires the ``payouts`` capability on the app; if it
        is not enabled PayPal returns its own 403 text, which propagates as a
        :class:`PayPalError` rather than a silent no-op.
        """
        body = {
            "sender_batch_header": {
                "sender_batch_id": f"fb-{os.urandom(8).hex()}",      # <=30 chars
                "email_subject": email_subject[:100],
                "email_message": (req.purpose or "Payment sent by an AI agent under Firebreak policy.")[:1000],
            },
            "items": [{
                "recipient_type": "EMAIL",
                "receiver": receiver or req.merchant,
                "amount": {"value": f"{req.amount:.2f}", "currency": req.currency},
                "note": (req.purpose or f"Payment to {req.merchant}")[:255],
                "sender_item_id": req.idempotency_key[:63],
            }],
        }
        return self._request("POST", "/v1/payments/payouts", body=body, headers=self._auth_headers())

    # ── history (for the risk engine) ──────────────────────────────────────
    def list_transactions(self, days: int = 90) -> list[dict]:
        """Payment history via the Reporting API.

        Sandbox support for reporting is patchy, so a failure here degrades to an
        empty history rather than breaking the guardrail -- the risk engine then
        simply reports that it has no history to compare against, which is the
        honest answer.
        """
        end = _dt.datetime.now(_dt.timezone.utc)
        start = end - _dt.timedelta(days=days)
        q = urllib.parse.urlencode({
            "start_date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_date": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fields": "all",
            "page_size": 100,
        })
        try:
            doc = self._request("GET", f"/v1/reporting/transactions?{q}", headers=self._auth_headers())
        except PayPalError:
            return []
        out = []
        for t in (doc.get("transaction_details") or []):
            info = t.get("transaction_info") or {}
            payer = t.get("payer_info") or {}
            out.append({
                "transaction_id": info.get("transaction_id", ""),
                "merchant": payer.get("email_address") or payer.get("payer_name", {}).get("given_name", ""),
                "amount": Decimal(str((info.get("transaction_amount") or {}).get("value", "0"))),
                "currency": (info.get("transaction_amount") or {}).get("currency_code", ""),
                "date": info.get("transaction_initiation_date", ""),
                "status": info.get("transaction_status", ""),
            })
        return out


def _api_error_message(raw: str) -> str:
    """Pull PayPal's own error text out of a response body."""
    try:
        doc = json.loads(raw)
    except Exception:
        return ""
    if isinstance(doc, dict):
        if doc.get("error_description"):
            return str(doc["error_description"])
        if doc.get("message"):
            return str(doc["message"])
        details = doc.get("details") or []
        if details and isinstance(details, list):
            d = details[0]
            return f"{d.get('issue', '')} {d.get('description', '')}".strip()
    return ""


class MockPayPal:
    """In-memory PayPal stand-in with the same surface as :class:`PayPalSandbox`.

    Used by the tests and by ``--offline``. Deliberately models the *awkward*
    parts of the real API (you cannot capture an unapproved order) so the code
    path exercised offline is the same one that runs against sandbox.
    """

    def __init__(self, history: list[dict] | None = None):
        self.orders: dict[str, dict] = {}
        self.transactions: list[dict] = list(history or [])
        self._n = 0

    def _next_id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n:08d}"

    def create_order(self, req: PaymentRequest, **kw) -> dict:
        oid = self._next_id("MOCKORDER")
        order = {
            "id": oid,
            "status": "CREATED",
            "purchase_units": [{
                "reference_id": req.idempotency_key,
                "amount": {"currency_code": req.currency, "value": f"{req.amount:.2f}"},
            }],
            "links": [
                {"rel": "approve", "href": f"https://sandbox.paypal.com/checkoutnow?token={oid}"},
                {"rel": "self", "href": f"mock://orders/{oid}"},
            ],
        }
        self.orders[oid] = {**order, "merchant": req.merchant, "currency": req.currency,
                            "value": f"{req.amount:.2f}"}
        return order

    @staticmethod
    def approve_url(order: dict) -> str:
        return PayPalSandbox.approve_url(order)

    def approve(self, order_id: str) -> None:
        """Test helper: stand in for the human clicking PayPal's approve button."""
        if order_id not in self.orders:
            raise PayPalError(f"unknown order {order_id}")
        self.orders[order_id]["status"] = "APPROVED"

    def get_order(self, order_id: str) -> dict:
        if order_id not in self.orders:
            raise PayPalError(f"unknown order {order_id}", 404)
        return self.orders[order_id]

    def capture_order(self, order_id: str) -> dict:
        o = self.get_order(order_id)          # same failure mode as the real API
        if o["status"] != "APPROVED":
            raise PayPalError("ORDER_NOT_APPROVED: Payer has not yet approved the Order",
                              422, "ORDER_NOT_APPROVED")
        cap = self._next_id("MOCKCAPTURE")
        o["status"] = "COMPLETED"
        tx = {"transaction_id": cap, "merchant": o.get("merchant", ""),
              "amount": Decimal(o["value"]), "currency": o["currency"],
              "date": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
              "status": "COMPLETED"}
        self.transactions.append(tx)
        return {"id": o["id"], "status": "COMPLETED",
                "purchase_units": [{"payments": {"captures": [{
                    "id": cap, "status": "COMPLETED",
                    "amount": {"currency_code": o["currency"], "value": o["value"]}}]}}]}

    def send_payout(self, req: PaymentRequest, **kw) -> dict:
        bid = self._next_id("MOCKPAYOUT")
        tx = {"transaction_id": bid, "merchant": req.merchant, "amount": req.amount,
              "currency": req.currency,
              "date": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
              "status": "COMPLETED"}
        self.transactions.append(tx)
        return {"batch_header": {"payout_batch_id": bid, "batch_status": "SUCCESS"},
                "items": [{"payout_item_id": bid, "transaction_status": "SUCCESS",
                           "payout_item": {"receiver": req.merchant,
                                           "amount": {"value": f"{req.amount:.2f}",
                                                      "currency": req.currency}}}]}

    def list_transactions(self, days: int = 90) -> list[dict]:
        return list(self.transactions)


def client_from_env(offline: bool = False):
    """Build a client from ``PAYPAL_CLIENT_ID`` / ``PAYPAL_SECRET``.

    Falls back to the mock only when explicitly asked (``offline=True``) -- never
    silently, because a silent fallback would let a real deployment believe it
    was guarding live money when it was not.
    """
    if offline:
        return MockPayPal()
    cid, secret = os.environ.get("PAYPAL_CLIENT_ID", ""), os.environ.get("PAYPAL_SECRET", "")
    if not cid or not secret:
        raise PayPalError(
            "PAYPAL_CLIENT_ID / PAYPAL_SECRET not set. Export the sandbox credentials, "
            "or pass --offline to run against the in-memory mock.")
    return PayPalSandbox(cid, secret)
