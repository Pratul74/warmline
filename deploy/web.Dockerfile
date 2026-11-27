# The "web" image: nginx (unprivileged) serving the built frontend and proxying /api/.
# Build from the repository root:
#   docker build -f deploy/web.Dockerfile --build-arg VITE_SITE_URL=https://example.com .
# Files allowed into the build are listed in web.Dockerfile.dockerignore.

# ---------- Build: compile the React app into static files ----------
FROM node:24-alpine AS build

WORKDIR /src

# Exact dependency versions from the lockfile (cached unless the lockfile changes)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Baked into the public bundle: no secrets. The API is on the same origin under /api,
# so the image works for any domain; only the link-preview URL needs the real domain.
ARG VITE_SITE_URL=http://localhost
ENV VITE_API_BASE_URL=/api \
    VITE_SITE_URL=${VITE_SITE_URL}
RUN npm run build


# ---------- Runtime: nginx running as uid 101, listening on 8080/8443 ----------
FROM nginxinc/nginx-unprivileged:1.28-alpine

# Remove the image's sample site; 40-select-site.sh writes the real one at start.
RUN rm -f /etc/nginx/conf.d/default.conf

COPY deploy/nginx/00-http.conf /etc/nginx/conf.d/00-http.conf
COPY deploy/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY deploy/nginx/site-http-only.conf deploy/nginx/site-https.conf /etc/nginx/warmline/
COPY --chmod=755 deploy/nginx/40-select-site.sh /docker-entrypoint.d/40-select-site.sh
COPY --from=build /src/dist /usr/share/nginx/html

EXPOSE 8080 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
