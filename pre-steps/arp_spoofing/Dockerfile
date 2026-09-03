FROM python:3.11-slim

# Install libpcap (required by scapy), tcpdump, and basic network tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpcap-dev \
    tcpdump \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY arp_attacker.py .

CMD ["python3", "arp_attacker.py"]
