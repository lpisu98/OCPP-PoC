FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY dns_attacker.py ./
COPY cp_client.py ./

EXPOSE 53/udp

CMD ["python3", "dns_attacker.py"]
