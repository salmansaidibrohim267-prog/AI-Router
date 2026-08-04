# API — Authentication

All API requests must present a valid credential. Interactive docs:
`/docs` (Swagger) and `/redoc`.

## Methods

### Bearer API keys (primary)

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

- Keys are managed by `app/auth/` (API key manager, RBAC, sessions,
  service accounts).
- For local development the default dev key is `test-key`.
- Keys support scoped/expiring tokens and per-tenant isolation
  (`docs/operations/` → tenancy).

### API key header (alternative)

The same key may be passed via `X-API-Key` on some routes; Bearer is
canonical.

## Tenant context

Tenancy middleware resolves the tenant from the authenticated principal;
billing, quotas and isolation are scoped to that tenant automatically.

## Enforcing auth

Set `ALLOWED_HOSTS` to restrict hosts in production. When a key is missing
or invalid the API responds with `401`; malformed inputs return `422`.

## Examples

```bash
BASE=http://localhost:8000 KEY=test-key

# Health
curl -s $BASE/ready -H "Authorization: Bearer $KEY"

# Chat
curl -s $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d @examples/requests/chat.json
```