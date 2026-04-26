#!/usr/bin/env bash
# Backup del Redis Stack del compose AparCáceres.
#
# Lanza BGSAVE en el servicio `redis`, espera a que termine y copia
# `dump.rdb` y `appendonlydir/` a `<destino>/<timestamp>/`. Aplica
# retención borrando snapshots con más de N días.
#
# Uso:
#   ./scripts/redis-backup.sh <destino> [retention_days=14]
#
# Requiere:
#   - docker compose disponible en el PATH
#   - permisos para escribir en <destino>
#   - el servicio `redis` del compose en marcha
#
# Cron sugerido (diario a las 03:00, retención 14 días):
#   0 3 * * * deploy /opt/aparcaceres/scripts/redis-backup.sh /var/backups/aparcaceres 14 >> /var/log/aparcaceres-backup.log 2>&1

set -euo pipefail

DEST=${1:?"falta destino: ./scripts/redis-backup.sh <destino> [retention_days]"}
RETENTION_DAYS=${2:-14}
COMPOSE_SERVICE=${COMPOSE_SERVICE:-redis}

# Localiza el compose: tomamos el del repo si no hay override.
COMPOSE_FILE=${COMPOSE_FILE:-"$(cd "$(dirname "$0")/.." && pwd)/docker-compose.yml"}

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "[redis-backup] compose no encontrado: $COMPOSE_FILE" >&2
    exit 1
fi

mkdir -p "$DEST"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H-%M-%SZ")
SNAPSHOT_DIR="$DEST/$TIMESTAMP"
mkdir -p "$SNAPSHOT_DIR"

echo "[redis-backup] iniciando snapshot en $SNAPSHOT_DIR"

# 1. BGSAVE: pedimos al servidor que vuelque el RDB a disco. No bloquea.
LAST_SAVE_BEFORE=$(docker compose -f "$COMPOSE_FILE" exec -T "$COMPOSE_SERVICE" redis-cli LASTSAVE)
docker compose -f "$COMPOSE_FILE" exec -T "$COMPOSE_SERVICE" redis-cli BGSAVE

# 2. Esperar a que LASTSAVE avance (BGSAVE terminado).
for _ in $(seq 1 60); do
    LAST_SAVE_NOW=$(docker compose -f "$COMPOSE_FILE" exec -T "$COMPOSE_SERVICE" redis-cli LASTSAVE)
    if [[ "$LAST_SAVE_NOW" != "$LAST_SAVE_BEFORE" ]]; then
        break
    fi
    sleep 1
done

if [[ "$LAST_SAVE_NOW" == "$LAST_SAVE_BEFORE" ]]; then
    echo "[redis-backup] BGSAVE no completó en 60s; abortando" >&2
    exit 2
fi

# 3. Copia del dump RDB y del directorio AOF al volumen del backup.
#    `docker compose cp` saca los ficheros del contenedor al host.
docker compose -f "$COMPOSE_FILE" cp "$COMPOSE_SERVICE":/data/dump.rdb "$SNAPSHOT_DIR/dump.rdb" || true
docker compose -f "$COMPOSE_FILE" cp "$COMPOSE_SERVICE":/data/appendonlydir "$SNAPSHOT_DIR/appendonlydir" || true

# 4. Retención: borra snapshots con más de RETENTION_DAYS días.
find "$DEST" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -print -exec rm -rf {} +

echo "[redis-backup] snapshot completo: $SNAPSHOT_DIR"
