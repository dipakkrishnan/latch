FROM openclaw:local

USER root

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-pip python3-venv xvfb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/latch
COPY pyproject.toml README.md ./
COPY src ./src
COPY docker/latch-openclaw-plugin /opt/latch-openclaw-plugin

RUN python3 -m venv /opt/latch-venv \
    && /opt/latch-venv/bin/pip install --no-cache-dir /tmp/latch

RUN mkdir -p /home/node/.cache/ms-playwright \
    && PLAYWRIGHT_BROWSERS_PATH=/home/node/.cache/ms-playwright \
       node /app/node_modules/playwright-core/cli.js install --with-deps chromium \
    && chown -R node:node /home/node/.cache/ms-playwright

COPY docker/openclaw-with-latch-entrypoint.sh /usr/local/bin/openclaw-with-latch-entrypoint.sh
RUN chmod 755 /usr/local/bin/openclaw-with-latch-entrypoint.sh \
    && chmod -R 755 /opt/latch-openclaw-plugin \
    && rm -rf /tmp/latch

USER node
WORKDIR /app
ENV PATH="/opt/latch-venv/bin:${PATH}"

ENTRYPOINT ["/usr/local/bin/openclaw-with-latch-entrypoint.sh"]
