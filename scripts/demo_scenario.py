"""Deterministic demo of one complete interlibrary loan cycle against the running API.

Local demo only (the API is unauthenticated). Standard library only; no extra dependency.
Needs the seeded demo data (member 6 is the disabled member used by the pre-check).

    docker compose up --build -d
    docker compose run --rm api python -m app.persistence.seed
    python scripts/demo_scenario.py            # --base-url http://127.0.0.1:8000 --run-id demo-1

What it shows (copy CP-0001, owned by the Central Branch, borrowed by the North Branch):
two simultaneous requests for the same copy -> exactly one wins; idempotent replay and key
reuse; an illegal transfer jump is refused; the full outward trip; activation; the borrower's
return (the copy stays blocked); the return trip; final state AVAILABLE at the owner, loan CLOSED.

Determinism: every decision is fixed (no randomness, no clock reads, no sleeping), every step is
asserted, and the printed transcript contains only values that do not depend on timing, so two
runs against freshly seeded databases print byte-identical output. Which of the two racing
requests wins, and therefore the loan's id (ids are reserved before validation, so rejected
requests leave gaps), is intentionally NOT printed. Transfer ids are printed: only the winner
creates transfers. It needs a database in which copy 1 is AVAILABLE;
because the loan cycle ends with the copy AVAILABLE again, the demo can be repeated with a new
--run-id (Idempotency-Keys are derived from it).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any

Caller = Callable[[str, str, "dict[str, Any] | None", "dict[str, str] | None"], "tuple[int, Any]"]

API = "/api/v1"
COPY_ID = 1
DESTINATION_BRANCH_ID = 2  # North Branch; copy 1 is owned by branch 1 (Central)


class DemoError(Exception):
    """An assertion about the API's behaviour did not hold."""


def http_caller(base_url: str) -> Caller:
    def call(method, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - local demo
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    return call


class Demo:
    def __init__(self, call: Caller, run_id: str, out: Callable[[str], None]) -> None:
        self.call = call
        self.run_id = run_id
        self.out = out
        self.step_no = 0

    # -- helpers ---------------------------------------------------------------------------

    def say(self, text: str) -> None:
        self.out(text)

    def step(self, title: str) -> None:
        self.step_no += 1
        self.say(f"\n[{self.step_no}] {title}")

    def expect(self, label: str, got_status: int, want_status: int, body: Any) -> Any:
        if got_status != want_status:
            raise DemoError(f"{label}: expected HTTP {want_status}, got {got_status}: {body}")
        self.say(f"    {label} -> {got_status}")
        return body

    def error_code(self, body: Any) -> str:
        return body["error"]["code"] if isinstance(body, dict) and "error" in body else "?"

    def copy(self) -> dict[str, Any]:
        status, body = self.call("GET", f"{API}/copies/{COPY_ID}", None, None)
        return self.expect(f"GET copy {COPY_ID}", status, 200, body)

    def show_copy(self, status: str, branch_id: int) -> None:
        copy = self.copy()
        if (copy["status"], copy["current_branch_id"]) != (status, branch_id):
            raise DemoError(f"copy is {copy['status']} at branch {copy['current_branch_id']}")
        self.say(f"    copy {copy['code']}: {copy['status']} at branch {copy['current_branch_id']}")

    def request(self, key: str, member_id: int) -> tuple[int, Any]:
        return self.call(
            "POST",
            f"{API}/loans/interlibrary",
            {
                "member_id": member_id,
                "copy_id": COPY_ID,
                "destination_branch_id": DESTINATION_BRANCH_ID,
            },
            {"Idempotency-Key": key},
        )

    def precheck_run_id_is_unused(self, keys) -> None:
        """Side-effect-free probe: ask with each key for a request that must be rejected
        (member 6 is disabled in the seed). A key that was committed by an earlier run answers
        `idempotency_key_reuse` BEFORE any validation; an unused key answers `member_disabled`
        and, because rejected requests roll their key claim back, stays unused."""
        for key in keys:
            status, body = self.request(key, 6)
            code = self.error_code(body)
            if code == "idempotency_key_reuse":
                raise DemoError(
                    f"run-id {self.run_id!r} was already used on this database; "
                    "pass a different --run-id (nothing was changed)"
                )
            if (status, code) != (409, "member_disabled"):
                raise DemoError(f"unexpected pre-check answer {status} {code}: {body}")
        self.say("    pre-check: run-id unused (probe requests were rejected, nothing written)")

    def transition(self, transfer_id: int, next_status: str, want: int = 200) -> Any:
        status, body = self.call(
            "POST",
            f"{API}/transfers/{transfer_id}/transitions",
            {"next_status": next_status},
            None,
        )
        return self.expect(f"POST transfer {transfer_id} -> {next_status}", status, want, body)

    # -- the scenario ----------------------------------------------------------------------

    def run(self) -> None:
        self.step("Start: the copy is available at its owning branch")
        self.show_copy("AVAILABLE", 1)

        self.step("Two simultaneous requests (different keys, different members) for ONE copy")
        keys = {1: f"{self.run_id}-req-a", 2: f"{self.run_id}-req-b"}
        self.precheck_run_id_is_unused(keys.values())
        results: dict[int, tuple[int, Any]] = {}
        barrier = threading.Barrier(2)

        def fire(member_id: int) -> None:
            barrier.wait(timeout=15)
            results[member_id] = self.request(keys[member_id], member_id)

        threads = [threading.Thread(target=fire, args=(m,)) for m in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        if len(results) != 2:
            raise DemoError("a concurrent request did not finish")
        outcomes = sorted(status for status, _ in results.values())
        if outcomes != [201, 409]:
            raise DemoError(
                f"expected exactly one 201 and one 409, got {outcomes}. Is copy {COPY_ID} "
                "AVAILABLE and this --run-id unused? (a repeated run-id replays the old loan)"
            )
        winner_member = next(m for m, (s, _) in results.items() if s == 201)
        loser_member = 3 - winner_member
        loser_body = results[loser_member][1]
        if self.error_code(loser_body) != "copy_not_available":
            raise DemoError(f"unexpected loser error: {loser_body}")
        loan = results[winner_member][1]
        loan_id = loan["id"]
        self.say("    outcomes: one request created the loan (201), the other was refused (409)")
        self.say("    refusal code: copy_not_available")
        self.say(
            f"    loan {loan_id}: {loan['status']}; transfers: "
            f"{[(t['direction'], t['status']) for t in loan['transfers']]}"
        )
        outward_id = next(t["id"] for t in loan["transfers"] if t["direction"] == "OUTBOUND")
        self.show_copy("RESERVED", 1)

        self.step("Idempotency: same key and body replays; same key with another body is refused")
        win_key = keys[winner_member]
        status, body = self.request(win_key, winner_member)
        replay = self.expect("replay of the winning request", status, 200, body)
        if replay["id"] != loan_id:
            raise DemoError("replay returned a different loan")
        self.say(f"    same loan returned: {replay['id'] == loan_id}")
        status, body = self.request(win_key, loser_member)
        self.expect("same key, different body", status, 409, body)
        self.say(f"    refusal code: {self.error_code(body)}")

        self.step("An illegal jump on the outward transfer is refused")
        body = self.transition(outward_id, "RECEIVED", want=409)
        self.say(f"    refusal code: {self.error_code(body)}")

        self.step(
            "Outward trip: dispatched, in transit, received (location changes only on receipt)"
        )
        self.transition(outward_id, "DISPATCHED")
        self.show_copy("IN_TRANSIT", 1)
        self.transition(outward_id, "IN_TRANSIT")
        self.show_copy("IN_TRANSIT", 1)
        received = self.transition(outward_id, "RECEIVED")
        self.say(f"    history: {[e['to_status'] for e in received['events']]}")
        self.show_copy("RESERVED", DESTINATION_BRANCH_ID)

        self.step("Activation (the member is re-validated)")
        status, body = self.call("POST", f"{API}/loans/{loan_id}/activate", None, None)
        active = self.expect("POST activate", status, 200, body)
        period = datetime.fromisoformat(active["due_at"]) - datetime.fromisoformat(
            active["started_at"]
        )
        self.say(f"    loan: {active['status']}, due {period.days} days after start")
        self.show_copy("ON_LOAN", DESTINATION_BRANCH_ID)

        self.step("The borrower returns the copy in GOOD condition (it is NOT free yet)")
        status, body = self.call(
            "POST", f"{API}/loans/{loan_id}/return", {"condition": "GOOD"}, None
        )
        returning = self.expect("POST return", status, 200, body)
        self.say(f"    loan: {returning['status']} (still blocks the copy)")
        return_id = next(t["id"] for t in returning["transfers"] if t["direction"] == "RETURN")
        self.show_copy("PENDING_RETURN", DESTINATION_BRANCH_ID)
        status, body = self.request(f"{self.run_id}-blocked", winner_member)
        self.expect("a new request while the copy is coming back", status, 409, body)
        self.say(f"    refusal code: {self.error_code(body)}")

        self.step("Return trip: dispatched, in transit, received at the owning branch")
        self.transition(return_id, "DISPATCHED")
        self.transition(return_id, "IN_TRANSIT")
        self.show_copy("IN_TRANSIT", DESTINATION_BRANCH_ID)
        self.transition(return_id, "RECEIVED")

        self.step("Final state")
        status, body = self.call("GET", f"{API}/loans/{loan_id}", None, None)
        final = self.expect("GET loan", status, 200, body)
        if final["status"] != "CLOSED":
            raise DemoError(f"loan is {final['status']}, expected CLOSED")
        self.say(
            f"    loan {loan_id}: {final['status']}; all transfers: "
            f"{sorted({t['status'] for t in final['transfers']})}"
        )
        self.show_copy("AVAILABLE", 1)
        self.say("\nDEMO OK: complete loan cycle verified")


def run_demo(call: Caller, run_id: str = "demo-1", out: Callable[[str], None] = print) -> None:
    Demo(call, run_id, out).run()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--run-id", default="demo-1", help="prefix of the Idempotency-Keys used")
    args = parser.parse_args(argv)
    try:
        run_demo(http_caller(args.base_url), args.run_id)
    except DemoError as error:
        print(f"\nDEMO FAILED: {error}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        print(f"\nCannot reach the API at {args.base_url}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
