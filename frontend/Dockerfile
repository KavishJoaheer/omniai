# syntax=docker/dockerfile:1.7
# Multi-stage build for the Omni-AI React frontend.
# Output is a tiny nginx image serving the built /dist/ over port 8080.

# ---- Stage 1: build --------------------------------------------------------

FROM node:20-alpine AS builder

WORKDIR /app

# Copy lock files first for better Docker layer caching
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

# VITE_API_BASE can be baked at build time so the bundle calls the right host.
# In k8s/compose this is typically the public host or "/" when served behind a
# reverse proxy that routes /v1/* to the API.
ARG VITE_API_BASE=/
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build


# ---- Stage 2: serve --------------------------------------------------------

FROM nginx:1.27-alpine AS runtime

# Drop the default nginx config
RUN rm -f /etc/nginx/conf.d/default.conf

# Custom config: serve the SPA on :8080, fall back to index.html so client
# routes work, and proxy /v1/* to the backend (set BACKEND_URL at runtime).
COPY --from=builder /app/docker/nginx.conf.template /etc/nginx/templates/default.conf.template

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

ENV NGINX_PORT=8080 \
    BACKEND_URL=http://api:9380

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O- http://localhost:${NGINX_PORT}/healthz || exit 1
