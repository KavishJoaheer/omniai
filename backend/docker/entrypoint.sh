#!/bin/sh
# Entrypoint for the omniai-backend image.
# Dispatches on OMNIAI_ROLE: api | worker | migrate | shell
# Always runs alembic upgrade head before serving (unless OMNIAI_SKIP_MIGRATIONS=1).

set -eu

role="${OMNIAI_ROLE:-api}"
http_port="${HTTP_PORT:-9380}"
worker_concurrency="${WORKER_CONCURRENCY:-10}"

run_migrations() {
    if [ "${OMNIAI_SKIP_MIGRATIONS:-0}" = "1" ]; then
        echo "[entrypoint] skipping migrations (OMNIAI_SKIP_MIGRATIONS=1)"
        return 0
    fi
    if [ -z "${DB_URL:-}" ]; then
        echo "[entrypoint] DB_URL is unset, skipping migrations"
        return 0
    fi
    echo "[entrypoint] running alembic upgrade head"
    alembic -c /app/alembic.ini upgrade head
}

case "$role" in
    api)
        run_migrations
        echo "[entrypoint] starting API on :${http_port}"
        exec uvicorn omniai.interfaces.http.app:create_app \
            --factory \
            --host 0.0.0.0 \
            --port "${http_port}" \
            --proxy-headers \
            --forwarded-allow-ips "*"
        ;;

    worker)
        # Workers don't run migrations — the API container does.
        echo "[entrypoint] starting arq worker"
        exec arq omniai.workers.worker.WorkerSettings
        ;;

    migrate)
        run_migrations
        echo "[entrypoint] migrations complete"
        ;;

    shell)
        # Useful for kubectl exec / debugging
        exec sh
        ;;

    *)
        # Treat unknown role as a verbatim command
        exec "$@"
        ;;
esac
