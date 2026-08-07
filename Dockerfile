# ── Stage 1: build the React frontend ───────────────────────
FROM node:20-alpine AS client-build
WORKDIR /app/client
COPY client/package.json ./
RUN npm install
COPY client/ ./
RUN npm run build

# ── Stage 2: production server ──────────────────────────────
# Debian-based (not Alpine) — Playwright only ships glibc (manylinux)
# wheels on PyPI, no musl build exists, so `pip install playwright` can
# never succeed on Alpine's musl libc regardless of which Chromium binary
# is on PATH.
FROM node:20-bookworm-slim
WORKDIR /app

# Python + python-pptx — used by server/render_ppt.py to build the
# corporate PPT with real gradient fills (pptxgenjs has no native
# multi-stop gradient support). "epigrafe" format additionally needs
# Playwright + Chromium for its HTML-first renderer.
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*
COPY server/requirements.txt ./server/
RUN pip3 install --no-cache-dir --break-system-packages -r server/requirements.txt
# Downloads Playwright's own bundled Chromium plus the OS shared libraries
# it needs (--with-deps runs apt-get for those automatically).
RUN python3 -m playwright install --with-deps chromium

# Install server dependencies
COPY server/package.json ./server/
RUN cd server && npm install --omit=dev

# Copy server source
COPY server/ ./server/

# Copy the built frontend from stage 1 into client/build,
# matching the path server/index.js expects (../client/build)
COPY --from=client-build /app/client/build ./client/build

WORKDIR /app/server

ENV PORT=3000
EXPOSE 3000

CMD ["node", "index.js"]
