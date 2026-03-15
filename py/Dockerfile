FROM python:3.12-slim

COPY . /src
RUN pip install --no-cache-dir /src

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
      -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

ENV AGENT_2FA_DIR=/data
EXPOSE 8100 8200

# Init config on first run, then start serving
CMD ["sh", "-c", "latch init && latch serve --transport streamable-http --mcp-host 0.0.0.0 --mcp-port 8100 --approval-port 8200"]
