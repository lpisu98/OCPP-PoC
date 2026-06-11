# Your Dockerfile
FROM oven/bun:latest
COPY . /app
WORKDIR /app
# Daemon mode: auto-connects + runs a scenario on startup
CMD ["bun", "src/cli/main.ts", \
     "--ws-url", "ws://app:8180/steve/websocket/CentralSystemService/", \
     "--cp-id", "CP_BENIGN_001", \
     "--daemon", \
     "--scenario-template", "full-charging-cycle", \
     "--scenario-connector", "1"]