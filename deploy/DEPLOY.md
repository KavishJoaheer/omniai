# Omni-AI deployment runbook

This document is for the **operator** — the person responsible for keeping
Omni-AI running, backed up, and recoverable. Read it end-to-end before your
first production deploy.

## Topology

```
            ┌──────────────┐
   user ───►│   nginx      │  (frontend image, 8080)
            │   /v1 ──┐    │
            └─────────┼────┘
                      ▼
            ┌──────────────┐    ┌──────────────┐
            │     API      │───►│   Postgres   │  (durable: data + chunks + audit)
            │  (FastAPI)   │    └──────────────┘
            │  9380        │    ┌──────────────┐
            │              │───►│    MinIO     │  (durable: raw + parsed text)
            └─────┬────────┘    └──────────────┘
                  │              ┌──────────────┐
                  ▼              │  OpenSearch  │  (durable: vector + bm25)
            ┌──────────────┐  ◄──┘
            │    Worker    │    ┌──────────────┐
            │   (arq)      │───►│    Redis     │  (queue, no durable data)
            └──────────────┘    └──────────────┘
                  │
                  ▼ (host-side or in-cluster)
            ┌──────────────┐
            │   Ollama     │  (LLM + embeddings)
            └──────────────┘
```

Two compose stacks live in `deploy/compose/`:
- `docker-compose.yml` — dev mode, source-mounted, no auth secrets
- `docker-compose.prod.yml` — built images, healthchecks, restart policies

A Helm chart for Kubernetes lives in `deploy/helm/omniai/`.

---

## Pre-flight checklist

Before going to production, **do every one of these**:

1. [ ] Generate a strong `ENCRYPTION_KEY`:
       ```sh
       python -c "import secrets; print(secrets.token_urlsafe(48))"
       ```
       Store it in your secrets manager. **Losing this key bricks every
       provider API key (Anthropic/OpenAI/Gemini) stored in the database.**
2. [ ] Generate a strong `AUTH_SECRET`:
       ```sh
       openssl rand -hex 32
       ```
3. [ ] Replace every `__CHANGE_ME__` in `.env.prod`.
4. [ ] Set a real `BOOTSTRAP_ADMIN_PASSWORD`. The bootstrap user is created
       only on first boot; rotating this env var afterwards has no effect.
5. [ ] Set `API_CORS_ORIGINS` to your real frontend host(s).
6. [ ] Decide your `RERANKER_KIND`:
       - `paired` (default) — works with the existing Ollama embedding model
       - `sentence-transformers` — better quality but pulls ~450 MB of model
         weights on first run; install with `pip install -e ".[reranker]"`
7. [ ] Decide your `OCR_KIND`:
       - `none` — disable OCR (fastest, smallest image)
       - `tesseract` — uncomment the apt-install in `backend/Dockerfile`,
         rebuild
       - `ollama_vision` — point `OLLAMA_VISION_MODEL` at a vision model
         you've pulled (e.g. `llava` or `llama3.2-vision`)
8. [ ] Configure backup automation (see "Backups" below).
9. [ ] Configure monitoring (see "Observability" below).
10. [ ] Decide where Ollama runs:
        - Same host: `OLLAMA_BASE_URL=http://host.docker.internal:11434`
        - In-cluster: deploy Ollama separately, set
          `OLLAMA_BASE_URL=http://ollama.ollama.svc.cluster.local:11434`
        - Cloud provider (Anthropic/OpenAI/Gemini): leave Ollama unused; set
          provider keys via the `/v1/providers` API after first login.

---

## Deploying

### Docker Compose (single host)

```sh
cp deploy/compose/.env.prod.example deploy/compose/.env.prod
$EDITOR deploy/compose/.env.prod    # fill in secrets

docker compose \
  -f deploy/compose/docker-compose.prod.yml \
  --env-file deploy/compose/.env.prod \
  up -d --build
```

Watch logs:

```sh
docker compose -f deploy/compose/docker-compose.prod.yml logs -f api worker
```

The api container runs `alembic upgrade head` automatically before serving.
You'll see `[entrypoint] running alembic upgrade head` in the logs on every
restart — this is idempotent.

### Kubernetes (Helm)

```sh
# Build + push images to your registry first.
docker build -t your-registry/omniai-backend:0.1.0  backend/
docker build -t your-registry/omniai-frontend:0.1.0 frontend/
docker push your-registry/omniai-backend:0.1.0
docker push your-registry/omniai-frontend:0.1.0

# Customize a values file
cp deploy/helm/omniai/values.yaml my-values.yaml
$EDITOR my-values.yaml      # set image.repository, secrets, domain

# Install
kubectl create namespace omniai
helm upgrade --install omniai deploy/helm/omniai \
  -n omniai \
  -f my-values.yaml
```

To use **external** managed Postgres / Redis / S3 / OpenSearch instead of the
bundled subcharts, set `postgres.enabled=false` etc., and override the
relevant URLs via values.

---

## Day-2 operations

### Backups

The durable state lives in three places. Back up all three.

| What                    | Where                                | How                                                         |
|-------------------------|--------------------------------------|-------------------------------------------------------------|
| Relational DB           | Postgres `postgres-data` volume      | `pg_dump`                                                   |
| Object store            | MinIO `minio-data` volume            | `mc mirror`                                                 |
| Search index            | OpenSearch `opensearch-data` volume  | `_snapshot` API                                             |
| Encryption key          | Secrets manager                      | (no automated backup — copy off-machine)                    |

**Postgres backup (compose):**
```sh
docker compose -f deploy/compose/docker-compose.prod.yml exec postgres \
  pg_dump -U omniai -Fc omniai > omniai-$(date +%F).dump
```

**MinIO mirror (compose, requires the `mc` client):**
```sh
mc alias set omniai http://localhost:9000 $ACCESS $SECRET
mc mirror --remove omniai/omniai s3-backup/omniai
```

**OpenSearch snapshot (one-time setup, then incremental):**
1. Mount a backup volume into the opensearch container at `/snapshots`.
2. Register the repository:
   ```sh
   curl -XPUT 'http://localhost:9200/_snapshot/local' \
     -H 'Content-Type: application/json' \
     -d '{"type":"fs","settings":{"location":"/snapshots","compress":true}}'
   ```
3. Take a snapshot daily via cron:
   ```sh
   curl -XPUT 'http://localhost:9200/_snapshot/local/snap-'$(date +%F)'?wait_for_completion=true'
   ```

**Verify your backups quarterly** by restoring to a staging instance and
running `python -m pytest backend/tests/`.

### Restore

1. Stop services: `docker compose ... down` (volumes preserved by default).
2. Restore Postgres: `pg_restore -U omniai -d omniai omniai-2026-04-29.dump`
3. Restore MinIO: `mc mirror --remove s3-backup/omniai omniai/omniai`
4. Restore OpenSearch: `_snapshot/local/<name>/_restore`
5. **Make sure `ENCRYPTION_KEY` matches the one in use when the backup was
   taken**, otherwise stored provider API keys cannot be decrypted.
6. Start services: `docker compose ... up -d`

### Rotating `ENCRYPTION_KEY`

This is sensitive — losing both the old and new key bricks stored credentials
permanently.

1. With the **old key still in env**, fetch every provider's plaintext API key
   via the admin API or by running an ad-hoc decrypt script.
2. Update `ENCRYPTION_KEY` in `.env.prod`.
3. Restart the api container.
4. Re-write each provider via `PATCH /v1/providers/{id}` with the plaintext
   API key — it gets re-encrypted under the new key.
5. (Optional) Run an alembic data migration to bulk re-encrypt; not provided
   in the chart — manual is safer for the first rotation.

### Scaling

| Lever                               | When                                              |
|-------------------------------------|---------------------------------------------------|
| `api.replicas` ↑                    | High concurrent chat / retrieval load             |
| `api.hpa.enabled: true`             | Bursty traffic; let CPU drive autoscale           |
| `worker.replicas` ↑                 | Ingestion backlog (parse/index queue grows)       |
| `opensearch.heap`                   | Large corpora — bump to 4g+ for 10M+ chunks       |
| `postgres` resource requests        | Slow queries on chats / chunks tables             |
| Add a managed Redis                 | Multi-node deployment                             |

The arq queue is shared via Redis, so multiple worker pods load-balance
automatically — no orchestration needed.

### Observability

- **Health:** `GET /v1/health` returns `{"status":"healthy"}`.
- **Metrics:** `GET /v1/metrics` is Prometheus text format. Already
  annotated for Prometheus auto-discovery in the api Deployment template.
  Scrape includes:
  - `omniai_http_requests_total{method,path,status}`
  - `omniai_http_request_duration_seconds` (histogram)
  - `omniai_chat_messages_total{status}`
  - `omniai_retrieval_total{rerank}`
  - `omniai_documents_indexed_total{status}`
  - `omniai_rate_limited_total{tenant}`
- **Audit log:** `GET /v1/admin/audit-events` (admin only). All write
  operations write here — collection deletes, member changes, connector
  CRUD, etc.
- **Structured logs:** stdout, plain Python logging. Pipe through
  Loki / Datadog / CloudWatch. Each request line includes path + status.

### Common failure modes

| Symptom                                      | Cause                                                | Fix                                                  |
|----------------------------------------------|------------------------------------------------------|------------------------------------------------------|
| API returns 500 on first boot                | Migrations failed (DB permissions or schema drift)  | `kubectl logs deploy/...-api`; check Postgres user role |
| Documents stuck at PARSING                   | Worker pod down or Redis unreachable                | `kubectl get pods | grep worker`; restart            |
| Documents stuck at EMBEDDING                 | Ollama down / wrong base URL                        | `curl $OLLAMA_BASE_URL/api/tags`                     |
| Chat hangs partway through                   | Provider API key invalid                            | Re-set via `/v1/providers/{id}`                      |
| 429 rate-limited responses                   | `RATE_LIMIT_PER_MINUTE` too low                     | Raise + restart api pods                             |
| Out-of-memory on worker                      | Large PDFs + reranker model loaded                  | Bump worker memory limit; lower batch sizes          |
| OpenSearch refusing connections              | `vm.max_map_count` too low                          | Already handled in Helm via initContainer            |

### Upgrading

1. `git pull` the new release.
2. Rebuild images.
3. `docker compose ... up -d --build` (compose) **or**
   `helm upgrade omniai deploy/helm/omniai -f my-values.yaml` (k8s).
4. Migrations run automatically on api start.
5. Watch the api logs for migration completion.
6. Run `python -m pytest backend/tests/` against staging before production.

### Decommissioning a tenant

Use the audit log to record the action, then:

```sh
# Delete from API (cascades to documents + chunks + memberships)
for col in $(curl -H "Authorization: Bearer $ADMIN_KEY" /v1/collections | jq -r '.[].id'); do
  curl -X DELETE -H "Authorization: Bearer $ADMIN_KEY" /v1/collections/$col
done

# Then in DB, drop the tenant row + cascade
psql -c "DELETE FROM tenants WHERE slug='deprecated-tenant';"
```

There's no built-in API endpoint for full tenant teardown yet — file an
issue if you need one as a hardened path.

---

## Security posture

### Headers (M14)

Every HTTP response from the API carries:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Content-Security-Policy` | `default-src 'self'; …` (see `app.py`) |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` — **production only** (`APP_ENV=production`) |

### Account lockout (M14)

| Env var | Default | Description |
|---------|---------|-------------|
| `LOGIN_LOCKOUT_THRESHOLD` | `5` | Failed attempts before the account is locked |
| `LOGIN_LOCKOUT_MINUTES` | `15` | How long the lock lasts |

After `LOGIN_LOCKOUT_THRESHOLD` consecutive bad passwords the account is
locked for `LOGIN_LOCKOUT_MINUTES` minutes.  A successful login resets the
counter immediately.  The API returns HTTP 403 with a human-readable message
telling the user how many minutes remain.

To **manually unlock** an account (e.g. legitimate user locked out):
```sql
UPDATE users
SET failed_login_attempts = 0, locked_until = NULL
WHERE email = 'user@example.com';
```

### Distributed connector scheduler lock (M14)

The `ConnectorScheduler` uses a per-connector lock so multiple API replicas
don't double-sync the same source simultaneously.

- **Single process / single-host** — in-process `asyncio.Lock` (automatic,
  no config needed).
- **Multi-replica / Kubernetes** — set `REDIS_URL` to point at the shared
  Redis.  The lock uses Redis `SET NX EX` with TTL = `sync_interval_seconds`,
  so a crashed replica never blocks a connector for more than one interval.

```yaml
# values.yaml (Helm)
api:
  env:
    REDIS_URL: "redis://redis-service:6379/0"
```

### Code execution sandbox (M14)

| `SANDBOX_KIND` | Description |
|----------------|-------------|
| `none` (default) | Code-node endpoints return 503; no execution risk |
| `subprocess` | Isolated child process; suitable for trusted/internal use |
| `docker` | Full kernel-namespace isolation; **recommended for untrusted input** |

Docker sandbox requirements:
- Docker daemon must be running on the host.
- The API container needs access to `/var/run/docker.sock` (add to Helm
  `volumes` / `volumeMounts` or use a Docker-in-Docker sidecar).
- Override the Python image with `SANDBOX_DOCKER_IMAGE` (default:
  `python:3.11-slim`).

```yaml
# docker-compose.prod.yml snippet for socket access
services:
  api:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      SANDBOX_KIND: docker
      SANDBOX_DOCKER_IMAGE: python:3.11-slim
```

> ⚠️  Mounting the Docker socket grants the container the ability to manage
> other containers on the host.  Use a dedicated `socat` proxy or a
> socket-proxy sidecar (e.g. `tecnativa/docker-socket-proxy`) to restrict
> the API surface exposed to the api container.

### Audit log

`GET /v1/admin/audit-events` supports cursor-based pagination (M14):

```
GET /v1/admin/audit-events?limit=50
GET /v1/admin/audit-events?limit=50&before_id=<nextCursor>
```

The response envelope is:
```json
{
  "data": {
    "items": [...],
    "nextCursor": "aud_abc123" | null,
    "hasMore": true | false
  }
}
```

### Legacy security checklist

- **All provider credentials encrypted at rest** with Fernet (AES-128-CBC +
  HMAC-SHA256), keyed off `ENCRYPTION_KEY`.
- **Auth tokens** are JWTs signed with `AUTH_SECRET`. Rotate every 90 days.
- **Sessions** are HTTP-only cookies; set `SESSION_COOKIE_SECURE=true` once
  you're behind HTTPS (Helm chart does this implicitly via TLS ingress).
- **Per-tenant rate limit** is applied at the middleware layer.
- **Per-tenant quotas** (document count + total bytes) enforced at upload.
- **Per-collection RBAC** scopes which users can read/write each collection
  separately from tenant role.

What's **not** yet done (track in the project's TODO):
- OAuth/OIDC SSO (Google, Microsoft) — infrastructure ready, routes pending.
- MFA — would slot into the existing auth_service.
- Per-row encryption of document text — currently only credentials are
  encrypted; raw document text in MinIO is plaintext.
- Hardware-bound key vault — `ENCRYPTION_KEY` lives in env / k8s Secret;
  for stricter compliance, integrate AWS KMS / Vault Transit.

---

## Where to look in the code

- HTTP entrypoint: `backend/omniai/interfaces/http/app.py`
- Container wiring: `backend/omniai/bootstrap/container.py`
- Migration files: `backend/omniai/adapters/relational/sqlalchemy/migrations/versions/`
- Chat pipeline: `backend/omniai/application/chat_service.py`
- Retrieval pipeline: `backend/omniai/application/retrieval_service.py`
- Workers: `backend/omniai/workers/`
- Settings (every env var): `backend/omniai/config/settings.py`
- Tests: `backend/tests/` — `python -m pytest tests/ -v`
