# syntax=docker/dockerfile:1.7
# Imagen runtime del frontend Flutter web de AparCáceres.
# Usa build multi-stage para compilar el bundle web y servir únicamente los
# artefactos estáticos finales con nginx.

FROM ghcr.io/cirruslabs/flutter:stable AS build

WORKDIR /app

ARG API_BASE_URL=http://localhost:8000

COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

COPY . .
RUN flutter build web --release --dart-define=API_BASE_URL=${API_BASE_URL}


FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build/web /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1