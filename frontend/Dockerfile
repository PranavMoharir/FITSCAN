# Multi-stage build (HLD §16.1): Node builds the Vite app, then a small static web server
# serves the built files. The browser loads the app from here and calls the API directly.

FROM node:24-alpine AS build
WORKDIR /app

# Install dependencies first, so this layer is cached until package-lock.json changes.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Vite writes these values into the JavaScript bundle at build time.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_POLL_INTERVAL_MS=2000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_POLL_INTERVAL_MS=$VITE_POLL_INTERVAL_MS
RUN npm run build


FROM node:24-alpine AS runtime
WORKDIR /app
RUN npm install --global --no-audit --no-fund serve@14.2.6
COPY --from=build /app/dist ./dist
USER node
EXPOSE 5173
# -s (single-page app): unknown paths return index.html, so client-side routes still load.
CMD ["serve", "-s", "dist", "-l", "tcp://0.0.0.0:5173", "--no-clipboard"]
