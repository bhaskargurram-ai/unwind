"""Mock payments MCP server — charge/refund/void with settlement windows (§5.2, §8).

Models the reversibility structure of money movement:

* ``charge`` — **R4** once **settled**; **R2** while inside a *void-before-
  settlement* window (``void_window_s``). This is the cleanest illustration of
  the half-life dimension (§5.2): the *same* charge is compensable now and
  irreversible later.
* ``void`` — the clean inverse of an *unsettled* charge (removes it as if it
  never happened, modulo an authorization-hold notification residue).
* ``refund`` — a **partial compensation** (R3): it issues a *new, opposite*
  transaction. It never restores exact prior state — the original charge, any
  processing fee, and the customer notification all persist as **residue**
  (Garcia-Molina & Salem: compensation is semantic, not bitwise).
* ``get_balance`` / ``get_charge`` — **R0** reads for pre-state capture.

:class:`PaymentsBackend` is a pure, testable in-process backend; :func:`build_server`
wires it to FastMCP for the sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from unwind.types import now_ts

__all__ = [
    "DEFAULT_VOID_WINDOW_S",
    "PROCESSING_FEE_CENTS",
    "Charge",
    "PaymentsBackend",
    "build_server",
    "main",
]

# Default void-before-settlement window (§5.2 half-life). 1 hour.
DEFAULT_VOID_WINDOW_S: float = 3600.0
# A processing fee that a refund does NOT return -> residue.
PROCESSING_FEE_CENTS: int = 30


@dataclass
class Charge:
    """A charge. ``settled_at`` closes the void window; ``refunded`` marks partial undo."""

    id: str
    account: str
    amount_cents: int
    created_at: float
    void_window_s: float
    voided: bool = False
    refunded: bool = False

    def is_settled(self, at: float) -> bool:
        return (at - self.created_at) > self.void_window_s


@dataclass
class PaymentsBackend:
    """In-process payments ledger with an injectable clock for deterministic tests."""

    balances_cents: dict[str, int] = field(default_factory=dict)
    charges: dict[str, Charge] = field(default_factory=dict)
    fees_collected_cents: int = 0
    _seq: int = 0
    clock: Any = now_ts

    def _next_id(self) -> str:
        self._seq += 1
        return f"chg-{self._seq}"

    # --- R0 reads ---------------------------------------------------------
    def get_balance(self, account: str) -> dict[str, Any]:
        return {"account": account, "balance_cents": self.balances_cents.get(account, 0)}

    def get_charge(self, charge_id: str) -> dict[str, Any]:
        c = self.charges[charge_id]
        return {
            "id": c.id,
            "account": c.account,
            "amount_cents": c.amount_cents,
            "created_at": c.created_at,
            "settled": c.is_settled(float(self.clock())),
            "voided": c.voided,
            "refunded": c.refunded,
        }

    # --- forward action ---------------------------------------------------
    def charge(
        self, account: str, amount_cents: int, void_window_s: float = DEFAULT_VOID_WINDOW_S
    ) -> dict[str, Any]:
        cid = self._next_id()
        self.charges[cid] = Charge(
            id=cid,
            account=account,
            amount_cents=amount_cents,
            created_at=float(self.clock()),
            void_window_s=void_window_s,
        )
        self.balances_cents[account] = self.balances_cents.get(account, 0) - amount_cents
        self.fees_collected_cents += PROCESSING_FEE_CENTS
        return {"id": cid, "void_window_s": void_window_s, "fee_cents": PROCESSING_FEE_CENTS}

    # --- clean inverse (only pre-settlement) -----------------------------
    def void(self, charge_id: str) -> dict[str, Any]:
        """Void an unsettled charge — the clean R2 inverse. Fails once settled."""
        c = self.charges[charge_id]
        if c.is_settled(float(self.clock())):
            return {
                "voided": False,
                "reason": "already_settled",
                "residue": ["charge_settled_no_void_possible"],
            }
        if c.voided:
            return {"voided": True, "reason": "already_voided", "residue": []}
        c.voided = True
        self.balances_cents[c.account] += c.amount_cents
        # The processing fee is returned on a void (unlike a refund).
        self.fees_collected_cents -= PROCESSING_FEE_CENTS
        return {"voided": True, "residue": ["authorization_hold_notification"]}

    # --- partial compensation (post-settlement) --------------------------
    def refund(self, charge_id: str) -> dict[str, Any]:
        """Refund a charge as a NEW opposite transaction — partial compensation (R3).

        Restores the *balance* (semantic) but leaves residue: the original charge
        record persists, the processing fee is NOT returned, and a customer
        notification fires. Never exact restoration.
        """
        c = self.charges[charge_id]
        if c.refunded:
            return {"refunded": True, "reason": "already_refunded", "residue": []}
        c.refunded = True
        self.balances_cents[c.account] += c.amount_cents
        # Fee is retained on a refund -> monetary residue.
        return {
            "refunded": True,
            "fee_retained_cents": PROCESSING_FEE_CENTS,
            "residue": [
                "original_charge_record_persists",
                "processing_fee_not_returned",
                "customer_refund_notification_fired",
            ],
        }


def build_server(backend: PaymentsBackend | None = None):  # type: ignore[no-untyped-def]
    """Wire a :class:`PaymentsBackend` to a FastMCP server (deferred mcp import)."""
    from mcp.server.fastmcp import FastMCP

    be = backend or PaymentsBackend()
    server = FastMCP("mock-payments")

    @server.tool(description="R0: read an account balance.")
    def get_balance(account: str) -> dict[str, Any]:
        return be.get_balance(account)

    @server.tool(description="R0: read a charge record (pre-state capture).")
    def get_charge(charge_id: str) -> dict[str, Any]:
        return be.get_charge(charge_id)

    @server.tool(description="R4 post-settlement / R2 within void window: charge an account.")
    def charge(
        account: str, amount_cents: int, void_window_s: float = DEFAULT_VOID_WINDOW_S
    ) -> dict[str, Any]:
        return be.charge(account, amount_cents, void_window_s)

    @server.tool(description="R2 inverse: void an UNSETTLED charge (fails once settled).")
    def void(charge_id: str) -> dict[str, Any]:
        return be.void(charge_id)

    @server.tool(description="R3 partial compensation: refund; leaves fee + notification residue.")
    def refund(charge_id: str) -> dict[str, Any]:
        return be.refund(charge_id)

    return server


def main() -> None:
    """Entry point: ``python -m bench.sandbox.mock_servers.payments_server`` (stdio)."""
    build_server().run()


if __name__ == "__main__":
    main()
