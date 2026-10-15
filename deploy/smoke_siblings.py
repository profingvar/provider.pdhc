#!/usr/bin/env python3
"""provider1.pdhc — does every call to a SIBLING service actually work? (#708)

Run it INSIDE the container, which is the only place the real credentials and
the real network names exist:

    docker exec provider1_app python deploy/smoke_siblings.py
    docker exec provider1_app python deploy/smoke_siblings.py --json

READ-ONLY. It creates nothing, writes nothing, acknowledges nothing and pushes
no status, so it is safe against production at any time.

## What provider1 calls

    request.pdhc   /api/v1/provider/feed                  the work queue
                   /api/v1/provider/download/<sr>         the bundle
                   /api/v1/provider/receipt/<tok>/ack     acknowledgement
    gateway.pdhc   /api/v1/provider/report/<sr>           the report (live)
                   /api/v1/requests[/<g>/status]          the LEGACY fallback,
                                                          which gateway no
                                                          longer serves
    plan.pdhc      /api/v1/plandefinitions/<g>            the form metadata
                   /api/v1/concepts/<g>                   response types

provider1 is an EXTERNAL-shaped caller: it holds a PAT
(`X-Provider-Token`), not an SSO session, which is the arrangement
onboard.pdhc exists to create. That makes it the one service where "my
credential is wrong" and "the platform moved" are easiest to confuse, because
both arrive as a 4xx on a POST the provider cannot see the other side of.

## Why a smoke here

`plan_client` is explicitly FAIL-SOFT: "any error returns an empty map so the
form degrades to plain text inputs rather than breaking submission". So a
plan.pdhc that moved shows the provider a working form with every widget
reduced to a text box — no error, no banner, and values that then fail
gateway's `ObservationValidator` because the JSON types no longer match.
That is a bad failure to debug from the far end of a contract.

So each path is probed with a deliberately invalid or absent credential and
asserted to REFUSE (401/403/405) rather than 404. A 404 is the shape a moved
endpoint takes; here it reaches the provider as a plain-text form, an empty
feed, or a push that silently went nowhere.

## What is NOT probed, deliberately

No POST, anywhere. `push_status`, `ack` and the report submission all WRITE to
a sibling and, worse, write against a real receipt token. Their paths are
checked for existence with a GET, which answers 405 when the route is
registered POST-only — that is the whole read-only half of a write edge.

Exit code is 0 only if every check passed.
"""
from __future__ import annotations

import json as _json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

#: Every sibling path provider1 builds -> the client module that builds it.
#: `%s` stands for a path parameter. Checked ANCHORED, because a truncated
#: prefix is a substring of the real path and must not pass (#804).
PROBED_PATHS = {
    "/provider/feed": "app/services/upstream_client.py",
    "/provider/download/%s": "app/services/upstream_client.py",
    "/provider/receipt/%s/ack": "app/services/upstream_client.py",
    "/provider/report": "app/services/upstream_client.py",
    "/requests": "app/services/upstream_client.py",
    "/plandefinitions/%s": "app/services/plan_client.py",
    "/concepts/%s": "app/services/plan_client.py",
}

#: Probed but composed inline here, with no client module to drift from:
#:   /api/health, /api/v1/health  — bare liveness pings.
INLINE_PATHS = ("/api/health", "/api/v1/health")

NOBODY = "00000000-0000-4000-8000-000000000000"

RESET, RED, GRN, BOLD = "\033[0m", "\033[31m", "\033[32m", "\033[1m"

results: list[dict] = []


def check(name: str):
    def wrap(fn):
        started = time.time()
        try:
            ok, note = fn()
        except Exception as e:                      # noqa: BLE001
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append({"check": name, "ok": bool(ok), "note": note,
                        "ms": int((time.time() - started) * 1000)})
        return ok
    return wrap


def _repo_root() -> pathlib.Path:
    """Where `app/` lives.

    The IMAGE flattens the package to /app/app/..., while a checkout is
    <repo>/provider_portal/app/... — one hardcoded relative path resolves in
    only one of them, and the guard is worth most BEFORE a deploy (#804).
    The first version of this script looked only for `provider_portal/` and
    reported all six client modules missing when run in the container.
    """
    here = pathlib.Path(__file__).resolve().parent.parent
    for cand in (here, here / "provider_portal", here.parent / "provider_portal"):
        if (cand / "app" / "services").is_dir():
            return cand
    return here


def _path_appears_in_client(template: str, src: str) -> bool:
    frags = [f for f in template.split("%s") if f]
    if not frags:
        return False
    if not re.search(r"""[}"']""" + re.escape(frags[0]), src):
        return False
    return all(f in src for f in frags[1:])


def _probe(url, headers=None, params=None, timeout=10):
    """(status, short body). A transport failure is status 0, so a service
    that is DOWN and a path that MOVED stay distinguishable."""
    import requests
    try:
        r = requests.get(url, headers=headers or {}, params=params or {},
                         timeout=timeout)
        return r.status_code, (r.text or "")[:120]
    except requests.RequestException as e:
        return 0, f"{type(e).__name__}: {e}"


def _exists(code: int) -> tuple[bool, str]:
    if code == 0:
        return False, "unreachable"
    if code == 404:
        return False, ("404 — the path MOVED, and this client degrades "
                       "silently rather than saying so")
    if code in (400, 401, 403, 405, 422):
        return True, f"{code} (refused, so the path is live)"
    if 200 <= code < 300:
        return True, f"{code} (answered)"
    return False, f"{code}"


def main(as_json: bool = False) -> int:
    from app import create_app
    app = create_app()

    with app.app_context():
        from flask import current_app
        cfg = current_app.config
        req = (cfg.get("REQUEST_SERVICE_URL") or "").rstrip("/")
        gw = (cfg.get("GATEWAY_SERVICE_URL") or "").rstrip("/")
        plan = (cfg.get("PLAN_BASE_URL") or "").rstrip("/")

        @check("paths: every probed path appears in its client module")
        def _():
            root = _repo_root()
            missing = []
            for template, mod in PROBED_PATHS.items():
                f = root / mod
                if not f.exists():
                    missing.append(f"{mod} is missing (looked under {root})")
                    continue
                if not _path_appears_in_client(template,
                                               f.read_text(encoding="utf-8")):
                    missing.append(f"{template} does not START a URL in {mod}")
            return (not missing), (
                f"all {len(PROBED_PATHS)} anchored to a URL boundary; "
                f"{len(INLINE_PATHS)} inline liveness paths unguarded by "
                f"design" if not missing else "; ".join(missing))

        @check("config: every sibling base URL is set")
        def _():
            miss = [n for n, v in (("REQUEST_SERVICE_URL", req),
                                   ("GATEWAY_SERVICE_URL", gw),
                                   ("PLAN_BASE_URL", plan)) if not v]
            return (not miss), ("all three set" if not miss
                                else "MISSING: " + ", ".join(miss))

        @check("config: the two base URLs are NOT the same service")
        def _():
            # `status_callback` sends a report WITH a payload to gateway and a
            # status-only update to request. Pointing both at one host would
            # send clinical values to whichever answers, and both would 200.
            if not (req and gw):
                return False, "one of the two is unset"
            same = req.rstrip("/") == gw.rstrip("/")
            return (not same), ("distinct" if not same else
                                f"BOTH are {req} — a report payload would go "
                                f"to the status endpoint")

        # ── request.pdhc: the work queue ──
        @check("request: /provider/feed EXISTS (not 404)")
        def _():
            if not req:
                return False, "REQUEST_SERVICE_URL not set"
            code, body = _probe(f"{req}/provider/feed", headers={
                "X-Provider-Token": "smoke-not-a-real-token"})
            if 200 <= code < 300:
                return False, (f"{code} for a junk PAT — the feed is "
                               f"unauthenticated: {body[:60]}")
            return _exists(code)

        @check("request: /provider/download/<sr> EXISTS (not 404)")
        def _():
            if not req:
                return False, "REQUEST_SERVICE_URL not set"
            # A guid that cannot exist. The distinction that matters is
            # 401/403 (credential refused — the path is there) versus 404,
            # which here could ALSO mean "no such service request". So a 404
            # is reported rather than failed: it is genuinely ambiguous on
            # this one path, and saying so is better than a false red.
            code, _b = _probe(f"{req}/provider/download/{NOBODY}", headers={
                "X-Provider-Token": "smoke-not-a-real-token"})
            if code == 404:
                return True, ("404 — AMBIGUOUS here: either the path moved or "
                              "that service request does not exist. The feed "
                              "check above is the unambiguous one")
            return _exists(code)

        @check("request: the ack path EXISTS and refuses a junk receipt")
        def _():
            # POST-only, so GET answers 405 — which proves the route is
            # registered without acknowledging anything. Acking for real
            # would mutate a sibling against a live receipt token.
            if not req:
                return False, "REQUEST_SERVICE_URL not set"
            code, _b = _probe(
                f"{req}/provider/receipt/smoke-not-a-real-receipt/ack")
            if code == 404:
                return False, ("404 — an acknowledgement would silently go "
                               "nowhere")
            return _exists(code)

        # ── gateway.pdhc: where the report with a payload goes ──
        @check("gateway: the LIVE report path /provider/report/<sr> EXISTS")
        def _():
            # POST-only, so GET answers 405 — which proves the route is
            # registered without submitting a report against a real service
            # request. This is the path `submit_report` defaults to.
            if not gw:
                return False, "GATEWAY_SERVICE_URL not set"
            code, _b = _probe(f"{gw}/provider/report/{NOBODY}", headers={
                "X-Provider-Token": "smoke-not-a-real-token"})
            if code == 404:
                return False, ("404 — every provider report would fail, and "
                               "`status_callback` only logs a warning")
            return _exists(code)

        @check("gateway: the LEGACY /requests fallback is GONE, so it cannot "
               "rescue anything")
        def _():
            # Reported, not failed. `/requests` and `/requests/<g>/status` are
            # labelled "Legacy endpoints (fallback)" in `upstream_client`, and
            # gateway no longer serves either under /api/v1 — enumerated from
            # its live url_map 2026-10-15, which has /api/v1/provider/{feed,
            # download,receipt,report} and a bare GET /requests that is a
            # different thing.
            #
            # Why it matters that this is VISIBLE rather than merely true:
            # both fallbacks are still REACHABLE. `subscription._sync_legacy`
            # calls `fetch_requests` and `status_callback._push_legacy` calls
            # `push_status`, each taken when the composite-key path is not
            # available — and each would 404, raise, and be swallowed into a
            # logged warning. A fallback that cannot work is worse than no
            # fallback, because the code reads as though there is a safety net.
            if not gw:
                return False, "GATEWAY_SERVICE_URL not set"
            code, body = _probe(f"{gw}/requests", headers={
                "X-Provider-Token": "smoke-not-a-real-token"})
            if code == 404:
                return True, ("404 as expected — the legacy fallback is dead; "
                              "_sync_legacy and _push_legacy cannot succeed "
                              "if they are ever reached")
            if 200 <= code < 300:
                return False, f"{code} for a junk PAT: {body[:60]}"
            return True, f"{code} — still answering something (reported)"

        # ── plan.pdhc: the form metadata, and the fail-soft that hides it ──
        @check("plan: /plandefinitions/<g> EXISTS (not 404)")
        def _():
            if not plan:
                return False, "PLAN_BASE_URL not set"
            code, _b = _probe(f"{plan}/api/v1/plandefinitions/{NOBODY}")
            if code == 404:
                return True, ("404 — AMBIGUOUS: the path, or that plan "
                              "definition. The concepts check below reads a "
                              "collection, which is not ambiguous")
            return _exists(code)

        @check("plan: the concepts COLLECTION answers, so the form is not "
               "silently degrading")
        def _():
            # The unambiguous one, and the reason this check exists:
            # `plan_client` returns an EMPTY MAP on any error, and the provider
            # then sees a working form with every widget reduced to a text
            # box — whose JSON types then fail gateway's ObservationValidator.
            # No error, no banner, and a very bad thing to debug from the far
            # end of a contract.
            if not plan:
                return False, "PLAN_BASE_URL not set"
            code, body = _probe(f"{plan}/api/v1/concepts")
            if code == 404:
                return False, ("404 — every guided form degrades to plain "
                               "text inputs, silently")
            if 200 <= code < 300:
                return True, f"200 ({len(body)} bytes of body)"
            return _exists(code)

        @check("plan: provider's own client returns {} for an absent plandef")
        def _():
            # Drives `plan_client.concept_form_meta`, so a wrong path or a
            # changed payload shape is wrong here too. `{}` is correct for a
            # plandef that does not exist AND for every failure, which is
            # precisely why the collection check above is the real one.
            from app.services.plan_client import concept_form_meta
            got = concept_form_meta(NOBODY)
            return isinstance(got, dict) and not got, (
                "{} for an absent plan definition — fail-soft as documented"
                if not got else f"returned {len(got)} concept(s)")

    failed = [r for r in results if not r["ok"]]
    if as_json:
        print(_json.dumps({"service": "provider1.pdhc", "checks": results,
                           "failed": len(failed)}, indent=2))
    else:
        print(f"\n{BOLD}provider1.pdhc — sibling smoke{RESET}\n")
        for r in results:
            mark = f"{GRN}OK{RESET}" if r["ok"] else f"{RED}FAIL{RESET}"
            print(f"  {mark:<14} {r['check']:<58}\n{' ' * 18}{r['note']}  "
                  f"({r['ms']}ms)")
        if failed:
            print(f"\n{RED}{BOLD}{len(failed)} check(s) failed.{RESET}\n")
        else:
            print(f"\n{GRN}{BOLD}All {len(results)} checks passed.{RESET}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(as_json="--json" in sys.argv))
