FROM node:22-slim AS builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent

COPY frontend/ .
# VITE_API_BASE_URL is baked in at BUILD time (Vite inlines env vars into
# the bundle) — override via --build-arg for non-default gateway URLs.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1
