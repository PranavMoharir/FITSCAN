# The public entry point of a production deployment (docker-compose.prod.yml): Caddy with the
# rate-limit plugin github.com/mholt/caddy-ratelimit (Apache-2.0). Caddy has no rate limiting of
# its own, so xcaddy compiles the plugin in. Both versions are pinned; the images are multi-arch
# (amd64 and arm64), so this builds on an Oracle Ampere A1 server as well as on a laptop.

FROM caddy:2.11.9-builder-alpine AS build
RUN xcaddy build v2.11.9 \
    --with github.com/mholt/caddy-ratelimit@5625512f24f6f59d6f64fb3aafe5eecff0b286db

FROM caddy:2.11.9-alpine
COPY --from=build /usr/bin/caddy /usr/bin/caddy
# The Caddyfile is mounted read-only by docker-compose.prod.yml (deploy/caddy/Caddyfile).
