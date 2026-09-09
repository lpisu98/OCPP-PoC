FROM mitmproxy/mitmproxy:latest

USER root
RUN mkdir -p /app/captures && chown -R mitmproxy:mitmproxy /app

USER mitmproxy
WORKDIR /app

COPY ocpp_mitm_addon.py .

# Proxy port (CP connects here)
EXPOSE 8080
# mitmweb UI port
EXPOSE 8081

ENV LOG_FILE=/app/captures/captures.jsonl
ENV MODIFY_MODE=false

# Reverse-proxy mode: CPs connect to us on 8080, we forward to the real CSMS.
# The upstream URL can be overridden at runtime via --mode reverse:<url>.
ENTRYPOINT ["mitmweb"]
CMD ["--mode", "reverse:ws://central_system:9000", "--listen-host", "0.0.0.0", "--listen-port", "8080", "--web-host", "0.0.0.0", "--web-port", "8081", "--no-web-open-browser", "-s", "/app/ocpp_mitm_addon.py"]
