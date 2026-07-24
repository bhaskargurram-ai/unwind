# ReversiBench Sandbox

The **live validation** harness (PROJECT.md §6 Stage 5, §8 "Live validation").
This is what makes ReversiBench's fidelity claims *real rather than asserted*: a
compensation is only credited if `pre_read → forward → inverse` actually executes
against a running server and the state diff confirms restoration.

## What's here

| File | Role |
|---|---|
| `harness.py` | Drives `pre_read → forward → inverse → pre_read` and grades fidelity by **state diff** into `exact / semantic / acceptable-approximation / failed`, reporting **residue**. |
| `mock_servers/comms_server.py` | Mock email/Slack MCP server. `send_email`/`post_message` are R3 with a **~30 s recall half-life**; `retract_message` is best-effort mitigation that fails once read or past the window. |
| `mock_servers/payments_server.py` | Mock payments MCP server. `charge` is **R4 post-settlement / R2 within a void window**; `void` is the clean inverse (pre-settlement only); `refund` is a **partial** compensation leaving fee + notification residue. |
| `docker-compose.sandbox.yml` | Compose fragment adding the two mock servers alongside the real filesystem/git/sqlite servers referenced by the root compose. |

## Why mocks for comms/payments?

Public comms and payments servers cannot be exercised destructively in a
benchmark (you cannot really send thousands of emails or settle charges to
measure undo fidelity). The mocks reproduce the exact **reversibility structure**
we need — external observation, recall windows, settlement windows, partial
compensation with residue — while the **real** filesystem/git/sqlite servers cover
the R0–R2 cases faithfully. Fidelity numbers in the paper come from this live
execution, per benchmark hygiene.

## Running

Standalone over stdio (used by the catalog crawler and the proxy in the demo):

```bash
python -m bench.sandbox.mock_servers.comms_server
python -m bench.sandbox.mock_servers.payments_server
```

In-process (used by the harness unit tests — no subprocess):

```python
from bench.sandbox.mock_servers.payments_server import PaymentsBackend
from bench.sandbox.harness import BackendCaller, run_forward_inverse

clock = [0.0]
be = PaymentsBackend(clock=lambda: clock[0])
caller = BackendCaller(be)

report = run_forward_inverse(
    caller,
    pre_read="get_balance", pre_read_args={"account": "acct-1"},
    forward="charge", forward_args={"account": "acct-1", "amount_cents": 500},
    inverse="void",
    inverse_args_fn=lambda pre, fwd: {"charge_id": fwd["id"]},
    key_fields=["balance_cents"],
)
print(report.grade, report.residue)   # -> FidelityGrade.SEMANTIC / .ACCEPTABLE_APPROXIMATION
```

Determinism: both backends take an injectable `clock`, so half-life / settlement
expiry is tested without real sleeping and results are reproducible for
`make results`.

## Docker

`docker-compose.sandbox.yml` is a **fragment** intended to be merged with the
root `docker-compose.yml` (which brings up `server-filesystem`, `mcp-server-git`,
`mcp-server-sqlite`):

```bash
docker compose -f docker-compose.yml -f bench/sandbox/docker-compose.sandbox.yml up
```

Sandbox state (`*.db`, `_state/`) is gitignored — never commit it (PROJECT.md
§12).
