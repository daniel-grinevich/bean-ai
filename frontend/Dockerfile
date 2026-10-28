# syntax=docker/dockerfile:1
# Bean AI frontend: the static Vite build served by nginx on port 80, proxying /api to the backend.
# Set BACKEND_URL at container start (no trailing slash); defaults to http://bean-backend:8000.

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
ENV BACKEND_URL=http://bean-backend:8000
# Only substitute BACKEND_URL, leaving nginx's own $variables alone.
ENV NGINX_ENVSUBST_FILTER=^BACKEND_URL$
COPY docker/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1
