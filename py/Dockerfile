FROM python:3.12-slim

RUN pip install --no-cache-dir latch-agent

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
      -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

ENV AGENT_2FA_DIR=/data
EXPOSE 8200

ENTRYPOINT ["latch"]
CMD ["serve", "--port", "8200"]
