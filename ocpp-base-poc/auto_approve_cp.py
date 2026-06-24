#!/usr/bin/env python3
"""
Demonstration script for the SteVe API wrapper.

This script polls the SteVe manager web UI for *unknown* charge points
(CPs that sent a BootNotification but are not yet in the database) and
automatically approves them by adding them with status ACCEPTED.

Usage:
    python demo_auto_approve.py
"""

import signal
import sys
import time
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

TARGET_URL = "http://localhost:8180/steve"
USERNAME = "admin"
PASSWORD = "1234"
POLL_INTERVAL_S = 10
BOOTSTRAP_INTERVAL_S = 3       # faster polling for the first BOOTSTRAP_PERIOD_S seconds
BOOTSTRAP_PERIOD_S = 60        # after this many seconds, switch to POLL_INTERVAL_S
RETRY_INTERVAL_S = 5

SESSION = requests.Session()


def _signin_url() -> str:
    return urljoin(TARGET_URL + "/", "manager/signin")


def _chargepoints_url() -> str:
    return urljoin(TARGET_URL + "/", "manager/chargepoints")


def _unknown_add_url(charge_box_id: str) -> str:
    return urljoin(TARGET_URL + "/", f"manager/chargepoints/unknown/add/{charge_box_id}/")


def _extract_csrf_token(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    csrf_input = soup.find("input", {"name": "_csrf"})
    if csrf_input:
        return csrf_input.get("value", "")
    return ""


def ensure_authenticated() -> bool:
    """
    Authenticate against SteVe and keep the resulting session cookies in memory.
    Returns True when the session is ready to use.
    """
    try:
        signin_resp = SESSION.get(_signin_url(), timeout=15)
        signin_resp.raise_for_status()
    except Exception as exc:
        print(f"[ERROR] Could not load sign-in page: {exc}")
        time.sleep(RETRY_INTERVAL_S)
        return False

    csrf_token = _extract_csrf_token(signin_resp.text)
    if not csrf_token:
        print("[ERROR] Could not find CSRF token on sign-in page.")
        time.sleep(RETRY_INTERVAL_S)
        return False

    try:
        login_resp = SESSION.post(
            _signin_url(),
            data={
                "username": USERNAME,
                "password": PASSWORD,
                "_csrf": csrf_token,
            },
            allow_redirects=False,
            timeout=15,
        )
    except Exception as exc:
        print(f"[ERROR] Could not submit login form: {exc}")
        time.sleep(RETRY_INTERVAL_S)
        return False

    if login_resp.status_code not in (302, 303):
        print(f"[ERROR] Login failed with HTTP {login_resp.status_code}.")
        time.sleep(RETRY_INTERVAL_S)
        return False

    if "JSESSIONID" not in SESSION.cookies.get_dict():
        print("[ERROR] Login response did not set a JSESSIONID cookie.")
        time.sleep(RETRY_INTERVAL_S)
        return False

    return True

def fetch_unknown_charge_points() -> List[Tuple[str, str]]:
    """
    Scrape the SteVe manager charge-points page and return a list of tuples:
        [(charge_box_id, csrf_token), ...]
    for every charge box that is currently in the "Unknown Charge Points" table.
    """
    try:
        resp = SESSION.get(_chargepoints_url(), timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[ERROR] Could not fetch charge points page: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    unknown_table = soup.find("div", id="unknownTable")
    if not unknown_table:
        return []

    tbody = unknown_table.find("tbody")
    if not tbody:
        return []

    unknown_cps = []
    for row in tbody.find_all("tr"):
        columns = row.find_all("td")
        if not columns:
            continue

        charge_box_id = columns[0].get_text(strip=True)

        # Extract the CSRF token from the "Add" form in this row
        add_form = row.find(
            "form", action=lambda x: x and f"/unknown/add/{charge_box_id}/" in x
        )
        csrf_token = ""
        if add_form:
            csrf_input = add_form.find("input", {"name": "_csrf"})
            if csrf_input:
                csrf_token = csrf_input.get("value", "")

        unknown_cps.append((charge_box_id, csrf_token))

    return unknown_cps


def approve_charge_point(charge_box_id: str, csrf_token: str) -> bool:
    """
    Approve an unknown charge point by POSTing to the SteVe internal endpoint
    that adds the charge box to the database with ACCEPTED status.

    :param charge_box_id: The charge-box identifier to approve.
    :param csrf_token:    The CSRF token extracted from the page (required).
    :return: True if the approval succeeded (HTTP 302 redirect = success).
    """
    resp = requests.post(
        _unknown_add_url(charge_box_id),
        cookies=SESSION.cookies,
        data={"_csrf": csrf_token},
        allow_redirects=False,
    )
    # SteVe responds with a 302 redirect back to the overview on success.
    return resp.status_code == 302


_shutdown_flag = False


def _handle_shutdown(_signum, _frame):
    global _shutdown_flag
    _shutdown_flag = True


def main() -> None:
    global _shutdown_flag

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    print("SteVe Auto-Approve Daemon")
    print("-" * 40)
    print(f"Target : {TARGET_URL}")
    print(f"Bootstrap: {BOOTSTRAP_INTERVAL_S}s polling for the first "
          f"{BOOTSTRAP_PERIOD_S}s, then {POLL_INTERVAL_S}s")
    print("Polling for unknown charge points...\n")

    start_time = time.time()

    while not _shutdown_flag:
        if not ensure_authenticated():
            continue

        unknown = fetch_unknown_charge_points()
        if not unknown:
            print("[INFO] No new charge points waiting for approval.")
        else:
            print(
                f"[ALERT] Found {len(unknown)} unknown charge point(s): "
                f"{[cp[0] for cp in unknown]}"
            )
            for cp_id, csrf in unknown:
                if approve_charge_point(cp_id, csrf):
                    print(f"[OK]    Charge point '{cp_id}' approved successfully.")
                else:
                    print(f"[FAIL]  Could not approve charge point '{cp_id}'.")

        # Adaptive polling: fast during bootstrap period, then slow
        elapsed = time.time() - start_time
        interval = BOOTSTRAP_INTERVAL_S if elapsed < BOOTSTRAP_PERIOD_S else POLL_INTERVAL_S

        # Sleep in short chunks so we can react to shutdown signals quickly
        for _ in range(interval):
            if _shutdown_flag:
                break
            time.sleep(1)

    print("\n[INFO] Shutting down auto-approve daemon.")


if __name__ == "__main__":
    main()
