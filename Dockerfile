# ── Stage 1: build the React frontend ───────────────────────
FROM node:20-alpine AS client-build
WORKDIR /app/client
COPY client/package.json ./
RUN npm install
COPY client/ ./
RUN npm run build

# ── Stage 2: production server ──────────────────────────────
FROM node:20-alpine
WORKDIR /app

# Python + python-pptx — used by server/render_ppt.py to build the
# corporate PPT with real gradient fills (pptxgenjs has no native
# multi-stop gradient support).
RUN apk add --no-cache python3 py3-pip
COPY server/requirements.txt ./server/
RUN pip3 install --no-cache-dir --break-system-packages -r server/requirements.txt

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
