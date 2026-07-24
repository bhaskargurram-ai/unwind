"""Mock comms MCP server — email/Slack with a reversibility half-life (§5.2, §8).

Models the *reversibility structure* of real comms tools so the sandbox can
validate compensations on them safely:

* ``send_email`` / ``post_message`` — **R3**: an external recipient may observe
  the message. A retraction (``retract_message``) is only a *mitigation* and only
  works **within a ~30s recall half-life** and only if the message is still
  unread; after that it fails and leaves residue (the recipient saw it).
* ``list_messages`` / ``get_message`` — **R0** reads for pre-state capture.
* ``mark_read`` — flips a message to read, which *closes* the recall window
  (used by the harness to demonstrate half-life expiry / residue).

The pure in-process backend (:class:`CommsBackend`) is importable and testable
without any MCP runtime; :func:`build_server` wires it to FastMCP for the sandbox
(``python -m bench.sandbox.mock_servers.comms_server``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from unwind.types import now_ts

__all__ = ["RECALL_HALF_LIFE_S", "CommsBackend", "Message", "build_server", "main"]

# Reversibility half-life for a message recall (§5.2). ~30s, per the spec's
# "email recall ~30 s" example.
RECALL_HALF_LIFE_S: float = 30.0


@dataclass
class Message:
    """A sent message. ``read`` and ``retracted`` drive recall eligibility."""

    id: str
    channel: str  # "email" or a slack channel id
    to: str
    body: str
    sent_at: float
    read: bool = False
    retracted: bool = False


@dataclass
class CommsBackend:
    """In-process comms state. Deterministic clock via an injectable ``now``.

    Tests pass an explicit ``clock`` so half-life expiry is exercised without
    real sleeping.
    """

    messages: dict[str, Message] = field(default_factory=dict)
    _seq: int = 0
    clock: Any = now_ts  # callable[[], float]

    def _next_id(self) -> str:
        self._seq += 1
        return f"msg-{self._seq}"

    # --- R0 reads (pre-state capture) ------------------------------------
    def list_messages(self) -> list[dict[str, Any]]:
        return [self.get_message(m.id) for m in self.messages.values()]

    def get_message(self, message_id: str) -> dict[str, Any]:
        m = self.messages[message_id]
        return {
            "id": m.id,
            "channel": m.channel,
            "to": m.to,
            "body": m.body,
            "sent_at": m.sent_at,
            "read": m.read,
            "retracted": m.retracted,
        }

    # --- R3 forward actions ----------------------------------------------
    def send_email(self, to: str, body: str) -> dict[str, Any]:
        mid = self._next_id()
        self.messages[mid] = Message(
            id=mid, channel="email", to=to, body=body, sent_at=float(self.clock())
        )
        return {"id": mid, "recall_half_life_s": RECALL_HALF_LIFE_S}

    def post_message(self, channel: str, body: str) -> dict[str, Any]:
        mid = self._next_id()
        self.messages[mid] = Message(
            id=mid, channel=channel, to=channel, body=body, sent_at=float(self.clock())
        )
        return {"id": mid, "recall_half_life_s": RECALL_HALF_LIFE_S}

    def mark_read(self, message_id: str) -> dict[str, Any]:
        self.messages[message_id].read = True
        return {"id": message_id, "read": True}

    # --- Mitigation (NOT a clean inverse) --------------------------------
    def retract_message(self, message_id: str) -> dict[str, Any]:
        """Best-effort recall. Fails outside the half-life or once read.

        Returns a graded outcome plus ``residue`` — the side-effects a retraction
        cannot remove (a delivery notification, and the fact a read recipient
        already saw it). This is what the harness grades: even a "successful"
        retraction is at best an *acceptable approximation*, never exact (the
        message was, briefly, out there).
        """
        m = self.messages[message_id]
        elapsed = float(self.clock()) - m.sent_at
        residue = ["delivery_notification_fired"]
        if m.read:
            return {
                "retracted": False,
                "reason": "already_read",
                "residue": [*residue, "recipient_already_read"],
            }
        if elapsed > RECALL_HALF_LIFE_S:
            return {
                "retracted": False,
                "reason": "recall_window_elapsed",
                "elapsed_s": elapsed,
                "residue": residue,
            }
        m.retracted = True
        return {"retracted": True, "elapsed_s": elapsed, "residue": residue}


def build_server(backend: CommsBackend | None = None):  # type: ignore[no-untyped-def]
    """Wire a :class:`CommsBackend` to a FastMCP server (deferred mcp import)."""
    from mcp.server.fastmcp import FastMCP

    be = backend or CommsBackend()
    server = FastMCP("mock-comms")

    @server.tool(description="R0: list all messages (nullipotent read).")
    def list_messages() -> list[dict[str, Any]]:
        return be.list_messages()

    @server.tool(description="R0: read one message by id (pre-state capture).")
    def get_message(message_id: str) -> dict[str, Any]:
        return be.get_message(message_id)

    @server.tool(description="R3: send an email. Recall only within ~30s, if unread.")
    def send_email(to: str, body: str) -> dict[str, Any]:
        return be.send_email(to, body)

    @server.tool(description="R3: post a message to a channel. Recall only within ~30s.")
    def post_message(channel: str, body: str) -> dict[str, Any]:
        return be.post_message(channel, body)

    @server.tool(description="Mark a message read (closes the recall window).")
    def mark_read(message_id: str) -> dict[str, Any]:
        return be.mark_read(message_id)

    @server.tool(description="Mitigation: best-effort recall; graded, leaves residue.")
    def retract_message(message_id: str) -> dict[str, Any]:
        return be.retract_message(message_id)

    return server


def main() -> None:
    """Entry point: ``python -m bench.sandbox.mock_servers.comms_server`` (stdio)."""
    build_server().run()


if __name__ == "__main__":
    main()
