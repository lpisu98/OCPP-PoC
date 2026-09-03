# Pre-Step Simulations

This directory contains scenarios that
demonstrate potential pre-attack steps against the OCPP infrastructure. Each scenario
is independently runnable with `docker compose up --build`.

## Scenarios

### 1. CSMS Compromission (`CSMS compromission/`)

Models a brute-force credential discovery attack against the SteVe management
web interface. The attacker container waits for SteVe to become healthy, then
attempts several incorrect passwords before successfully authenticating with
the default `admin / 1234` credentials.

**Architecture:**

| Container       | Role                                                              |
|-----------------|-------------------------------------------------------------------|
| `db`            | MariaDB database for SteVe                                        |
| `app`           | SteVe CSMS (built from `ocpp-base-poc/steve/`)                    |
| `attacker`      | Python script that performs the brute-force login attempts        |
| `tcpdump`       | Packet capture attached to the `app` network namespace            |

**How to run:**

Using the bash script:
```bash
cd pre-steps
./run_csms_compromission.sh [--duration <seconds>]
```

Or directly with Docker Compose:
```bash
cd pre-steps/CSMS\ compromission
docker compose up --build
```

**Environment variables**:

| Variable       | Default                                                           | Description                              |
|----------------|-------------------------------------------------------------------|------------------------------------------|
| `TARGET_URL`   | `http://app:8180/steve`                                           | SteVe manager base URL                   |
| `USERNAME`     | `admin`                                                           | Admin username to test                   |
| `PASSWORD`     | `1234`                                                            | Known correct password                   |
| `WORDLIST`     | `admin,password,1234,steve,changeme,root,test`                    | Comma-separated password candidates      |
| `LOGIN_DELAY_S`| `2`                                                               | Seconds between login attempts           |

**Expected logs (attacker container):**

```
{"timestamp": "...", "level": "INFO", "event": "attack_start", ...}
{"timestamp": "...", "level": "FAIL", "event": "failed_login", ...}   ← multiple
{"timestamp": "...", "level": "SUCCESS", "event": "credential_discovery", ...}
{"timestamp": "...", "level": "SUCCESS", "event": "verified_access", ...}
{"timestamp": "...", "level": "INFO", "event": "attack_complete", ...}
```

**PCAP location:** `data/csms_compromission_capture.pcap`

**Wireshark display filters:**

```
# View all HTTP traffic to/from SteVe
http

# Filter for POST requests to the sign-in endpoint
http.request.method == POST && http.request.uri contains "/manager/signin"

# Filter for successful login (302 redirect after POST)
http.response.code == 302 && http.request.method == POST

# View the authenticated manager page access
http.request.uri contains "/manager" && http.request.method == GET
```

---

### 2. DNS Spoofing (`dns_spoofing/`)

Demonstrates a DNS-based redirection attack. A malicious DNS server resolves
the domain `csms.lab` to an attacker-controlled fake CSMS IP address. The
charge-point simulator is configured to use this malicious DNS resolver and
connects to `ws://csms.lab:9002/`, unknowingly establishing an OCPP session
with the impersonating CSMS.

**Architecture:**

| Container            | Role                                                                    |
|----------------------|-------------------------------------------------------------------------|
| `dns_attacker`       | Malicious DNS server that spoofs `csms.lab` → `172.20.0.10`            |
| `impersonating_csms` | Fake CSMS (reused from `attack_scenarios/03-CSMS-Impersonation`)       |
| `cp-simulator`       | Charge-point simulator configured with the malicious DNS resolver      |
| `tcpdump`            | Owns the CP network namespace and starts capture before the CP          |

All containers share the `dns_lab` network (`172.20.0.0/24`).
The CP starts only after the malicious DNS server and fake CSMS pass their
health checks, preventing a one-shot DNS lookup from racing service startup.

**How to run:**

Using the convenience script (recommended):
```bash
cd pre-steps
./run_dns_spoofing.sh [--duration <seconds>]
```

Or directly with Docker Compose:
```bash
cd pre-steps/dns_spoofing
docker compose up --build
```

**Environment variables** (all optional with sensible defaults):

| Variable        | Default        | Description                                          |
|-----------------|----------------|------------------------------------------------------|
| `LISTEN_HOST`   | `0.0.0.0`      | DNS server bind host                                 |
| `LISTEN_PORT`   | `53`           | DNS server UDP port                                  |
| `SPOOF_DOMAIN`  | `csms.lab`     | Domain to spoof                                      |
| `SPOOF_ADDRESS` | `172.20.0.10`  | IP to return for the spoofed domain                  |
| `UPSTREAM_DNS`  | `8.8.8.8`      | Upstream resolver for non-spoofed queries            |
| `FORWARD_OTHER` | `false`        | Forward non-spoofed queries upstream (true) or REFUSED (false) |

**Expected logs (dns_attacker container):**

```
Malicious DNS server starting on 0.0.0.0:53
Spoofing: csms.lab -> 172.20.0.10
SPOOF: csms.lab -> 172.20.0.10
```

**Expected logs (impersonating_csms container):**

```
Fake CSMS listening on ws://0.0.0.0:9002
[CP_BENIGN_001] LEGITIMATE CP CONNECTED TO FAKE CSMS
[CP_BENIGN_001] Received BootNotification — accepting impersonation
...
```

**PCAP location:** `data/dns_spoofing_capture.pcap`

**Wireshark display filters:**

```
# View DNS queries and responses
dns

# Filter specifically for the spoofed domain
dns.qry.name == csms.lab

# View the OCPP WebSocket upgrade and traffic
websocket

# View all traffic between the CP and the fake CSMS
ip.addr == 172.20.0.20 && ip.addr == 172.20.0.10
```

---

### 3. ARP Spoofing MITM (`arp_spoofing/`)

Demonstrates a layer-2 ARP spoofing attack that positions the attacker between a
legitimate charge point and the real SteVe CSMS. The attacker container sends
forged ARP replies to both victims, claiming the other party's IP address maps to
the attacker's MAC address. With IP forwarding enabled, the OCPP WebSocket traffic
is transparently routed through the attacker and captured by a sidecar `tcpdump`.

**Architecture:**

| Container       | Role                                                              |
|-----------------|-------------------------------------------------------------------|
| `db`            | MariaDB database for SteVe                                        |
| `app`           | Real SteVe CSMS at `172.30.0.10`                                  |
| `cp-simulator`  | Legitimate charge point at `172.30.0.20`                          |
| `attacker`      | ARP spoofing + IP forwarding — places itself in the traffic path  |
| `tcpdump`       | Packet capture attached to the `attacker` network namespace      |

All containers share the `arp_lab` network (`172.30.0.0/24`). The attacker needs
`NET_ADMIN` and `NET_RAW` capabilities and `net.ipv4.ip_forward=1` so the Linux
kernel can relay packets between the CP and CSMS.

**How to run:**

Using the bash script:
```bash
cd pre-steps
./run_arp_spoofing.sh [--duration <seconds>]
```

Or directly with Docker Compose:
```bash
cd pre-steps/arp_spoofing
docker compose up --build
```

**Environment variables**:

| Variable           | Default        | Description                                          |
|--------------------|----------------|------------------------------------------------------|
| `TARGET1_IP`       | `172.30.0.10`  | IP of the CSMS (first ARP target)                   |
| `TARGET2_IP`       | `172.30.0.20`  | IP of the CP simulator (second ARP target)          |
| `INTERFACE`        | auto-detected  | Network interface used for ARP spoofing (falls back to first non-loopback) |
| `SPOOF_INTERVAL_S` | `2`            | Seconds between ARP spoof bursts                    |

**Expected logs (attacker container):**

```
{"timestamp": "...", "level": "INFO", "event": "attack_start", ...}
{"timestamp": "...", "level": "INFO", "event": "attacker_mac", ...}
{"timestamp": "...", "level": "INFO", "event": "target_discovered", ...}   ← both targets
{"timestamp": "...", "level": "INFO", "event": "ip_forward_enabled", ...}
{"timestamp": "...", "level": "SUCCESS", "event": "mitm_position_active", ...}
{"timestamp": "...", "level": "INFO", "event": "arp_poison", ...}           ← repeated
{"timestamp": "...", "level": "INFO", "event": "attack_complete", ...}
```

**PCAP location:** `data/arp_spoofing_capture.pcap`

**Wireshark display filters:**

```
# View ARP traffic and spoofed replies
arp

# View ARP requests/replies involving the attacker
arp.src.proto_ipv4 == 172.30.0.10 or arp.src.proto_ipv4 == 172.30.0.20 or arp.src.proto_ipv4 == 172.30.0.30

# View the OCPP WebSocket traffic between CP and CSMS (routed through attacker)
websocket and (ip.addr == 172.30.0.10 and ip.addr == 172.30.0.20)

# View all traffic between the CP and the CSMS
ip.addr == 172.30.0.10 && ip.addr == 172.30.0.20
```

