# Operaciones del backend AparCáceres

Guía operativa para desplegar y mantener el backend en producción.
Asume el stack `docker compose` del repo (`docker-compose.yml`) con la
configuración del backend en `backend/.env`, más un reverse proxy (nginx en
los ejemplos; Traefik / Caddy serían equivalentes).

## 1. Topología de despliegue recomendada

```
                 (público, TLS)
   Cliente ──────────────────► nginx ─────► uvicorn (api:8000) ─────► redis-stack (6379)
                                  │              │                             │
                                  │              │                       AOF + RDB
                                  │              │                       en /data
                                  │              │
                                  │              └─ /metrics (Prometheus scrape)
                                  └─ /healthz (loadbalancer probe)
```

- nginx termina TLS y reenvía cabeceras (`X-Forwarded-For`, `X-Forwarded-Proto`,
  `X-Request-ID`).
- uvicorn corre con `--proxy-headers` para que Starlette tome las cabeceras
  forwarded en serio (necesario para `slowapi.get_remote_address`).
- redis-stack queda en la red interna del compose; nunca se publica en
  Internet sin autenticación.
- `/metrics` se expone solo en la red interna; el scrape de Prometheus
  ocurre por la misma vía.

## 2. nginx + TLS

Plantilla mínima para terminar TLS y proxiar al `api`:

```nginx
# /etc/nginx/sites-available/aparcaceres.conf
upstream aparcaceres_api {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name aparcaceres.example.com;

    # Renovación de certificados con Let's Encrypt (HTTP-01).
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Resto del tráfico se redirige a HTTPS.
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name aparcaceres.example.com;

    ssl_certificate     /etc/letsencrypt/live/aparcaceres.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aparcaceres.example.com/privkey.pem;

    # Hardening básico. Ajustar a la política de seguridad propia.
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;

    # Tamaño máximo de body (los GeoJSON municipales no se suben por API,
    # pero dejamos margen para futuros uploads de catálogo).
    client_max_body_size 5m;

    # Generación / propagación de Request ID. El backend lo respeta si llega.
    set $request_id_header $http_x_request_id;
    if ($request_id_header = "") {
        set $request_id_header $request_id;
    }

    location / {
        proxy_pass http://aparcaceres_api;

        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Request-ID      $request_id_header;
        add_header       X-Request-ID      $request_id_header always;

        proxy_read_timeout 30s;
        proxy_connect_timeout 5s;
    }

    # Healthcheck público para el balanceador. No exige TLS al upstream.
    location = /healthz {
        proxy_pass http://aparcaceres_api/healthz;
        access_log off;
    }
}
```

Tras ajustar el fichero:

```bash
sudo ln -s /etc/nginx/sites-available/aparcaceres.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Renovación de certificados (cron):

```cron
# /etc/cron.d/certbot-aparcaceres
0 3 * * * root certbot renew --quiet --post-hook "systemctl reload nginx"
```

### Sobre `/metrics`

El endpoint `/metrics` (Prometheus) NO se expone públicamente. Se accede
desde la red interna del compose, donde corre el scraper. Para exposiciones
externas autenticadas, añadir un `location = /metrics` con `auth_basic`.

## 3. Persistencia de Redis

`docker-compose.yml` ya configura AOF (`--appendonly yes --appendfsync everysec`)
y RDB (`--save 900 1 --save 300 10`). El volumen nombrado `redis-data` sobrevive
a `docker compose down` (se pierde solo con `docker compose down -v`).

Comprobaciones rápidas tras un deploy:

```bash
docker compose exec redis redis-cli CONFIG GET appendonly
docker compose exec redis redis-cli LASTSAVE
docker compose exec redis redis-cli INFO persistence | head -20
```

Esperado:
- `appendonly` = `yes`
- `LASTSAVE` reciente (RDB)
- `aof_enabled:1`, `aof_last_rewrite_time_sec` razonable.

## 4. Backups

### 4.1 Manual

`scripts/redis-backup.sh` (en este repo) lanza `BGSAVE` y copia el `dump.rdb`
y el `appendonlydir/` a un directorio destino con timestamp. Para correrlo
puntualmente:

```bash
./scripts/redis-backup.sh /var/backups/aparcaceres
```

### 4.2 Automatizado (cron en el host)

```cron
# /etc/cron.d/aparcaceres-redis-backup
# Backup diario a las 03:00, retención 14 días.
0 3 * * * deploy /opt/aparcaceres/scripts/redis-backup.sh /var/backups/aparcaceres 14 >> /var/log/aparcaceres-backup.log 2>&1
```

### 4.3 Off-site (S3 / object storage)

Tras cada backup local, sincronizar a un bucket. Ejemplo con `rclone`:

```bash
rclone sync /var/backups/aparcaceres remote:aparcaceres-backups/redis \
    --max-age 14d --transfers 4 --checksum
```

`rclone` se configura una vez (`rclone config`) con credenciales del
proveedor (S3, B2, GCS...).

## 5. Restore desde backup

1. Parar el servicio:
   ```bash
   docker compose stop api redis
   ```
2. Restaurar el volumen:
   ```bash
   # Desmontar el volumen actual y reemplazarlo por el backup.
   docker run --rm \
       -v aparcaceres_redis-data:/restore \
       -v /var/backups/aparcaceres/2026-04-26T03-00-00:/backup \
       alpine sh -c "rm -rf /restore/* && cp -a /backup/. /restore/"
   ```
3. Re-arrancar:
   ```bash
   docker compose up -d redis
   docker compose exec redis redis-cli PING   # PONG
   docker compose up -d api
   curl -fsS http://localhost:8000/healthz | jq
   ```

Si el backup era íntegro y el AOF estaba habilitado, los favoritos
(`user:*:favorites`) y el catálogo (`parking:*`) reaparecen tal cual. Si
solo restaurás el RDB sin el AOF, puede perderse la última franja de
escrituras (depende de cuándo fue el último BGSAVE).

## 6. Variables de entorno mínimas en producción

```env
APP_ENV=production
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
LOG_LEVEL=INFO

# Lista explícita de orígenes; nunca "*".
CORS_ORIGINS=https://aparcaceres.example.com

# Token de import (debe coincidir con el que envía el job de re-importación).
IMPORT_TOKEN=<random-32-bytes>

# Clave de firma para los JWT de favoritos.
FAVORITES_SECRET=<random-32-bytes>

# Rate limit y métricas activas en producción.
RATE_LIMIT_ENABLED=true
METRICS_ENABLED=true

# Tamaño de caché y paginación (defaults razonables).
CACHE_NEARBY_TTL=60
DEFAULT_PARKING_LIMIT=100
MAX_PARKING_LIMIT=500

# Resolución de fotos durante el import. Cuando true, el importador
# descarga las fichas SIG (fichatoponimia.php / fichacalle.php) de los
# places sin URL_FOTO explícito, extrae la <img> de /fotosOriginales/
# y persiste la URL resuelta. Cachea por id en parking_photo:{id}
# (TTL 90 días por defecto) para que un re-import no rescraperar.
FETCH_PHOTOS=true
PHOTO_FETCH_CONCURRENCY=20
PHOTO_FETCH_TIMEOUT_SECONDS=5.0
PHOTO_CACHE_TTL_SECONDS=7776000
```

Los secretos (`IMPORT_TOKEN`, `FAVORITES_SECRET`) deben generarse con
`openssl rand -hex 32` y guardarse en el gestor de secretos del orquestador
(no commitear el `.env` con valores reales).

## 7. Runbook rápido

| Síntoma                                       | Primera comprobación                                         |
| --------------------------------------------- | ------------------------------------------------------------ |
| 503 en todo                                   | `curl /healthz` → ver qué componente está `down`             |
| 503 sólo en `/parkings*`                      | `redis-cli FT.INFO idx:parkings_search` → reimport si falta  |
| Respuestas "vacías" tras un import            | Doble buffer en swap; reintentar en ~5s                      |
| Caché de nearby aparece "antigua"             | `redis-cli GET cache:version` debería haber subido           |
| 401 en `/users/me/favorites`                  | Cliente sin Bearer válido o `FAVORITES_SECRET` cambiado      |
| 429 en `/parkings/nearby`                     | Cliente excediendo `RATE_LIMIT_NEARBY`; revisar logs nginx   |
| `LASTSAVE` no avanza                          | Disco lleno o AOF roto; revisar `redis INFO persistence`     |
| `/metrics` no responde                        | `METRICS_ENABLED=false` o instrumentation no se enganchó     |
