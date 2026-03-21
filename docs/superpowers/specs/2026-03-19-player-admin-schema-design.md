# Player Admin Schema — Conditional Field Exposure

## Problem

The `GET /api/v1/players/{id}` endpoint returns the same fields regardless of who is calling it. Moderators and admins need to see internal fields (`user`, `claim_status`, `sync_paused`) that should not be exposed to the public API.

## Decision

Use two response schemas: `PlayerSchema` (public) and `PlayerAdminSchema` (moderator+). The GET endpoint inspects the caller's auth role and returns the appropriate schema.

## Design

### New schema: `PlayerAdminSchema`

Extends `PlayerSchema` with three fields:

| Field | Type | Description |
|-------|------|-------------|
| `user` | `str \| None` | Bound Django user's username, or `null` if unbound |
| `claim_status` | `str` | One of `"unclaimed"`, `"claimed"`, `"deleted"` |
| `sync_paused` | `bool` | Whether SRC sync is paused for this player |

Location: `backend/api/v1/schemas/players.py`

A `@field_validator` on `user` converts the Django `User` ORM object to its `username` string (or `None` if no user is bound).

### Router changes

Only `GET /{id}` in `backend/api/v1/routers/resources/players.py` changes:

1. After fetching the player, check `request.auth` for moderator+ role.
2. `PublicOrRoleAuth` already sets `request.auth["role"]` to `"public"` for unauthenticated GET requests, or the actual role string (`"moderator"`, `"admin"`) for authenticated requests.
3. Select `PlayerAdminSchema` or `PlayerSchema` based on role.
4. Update the response type annotation to `200: PlayerSchema | PlayerAdminSchema`.

```python
is_mod = (
    request.auth
    and request.auth.get("role") in ("moderator", "admin")
)
schema_cls = PlayerAdminSchema if is_mod else PlayerSchema
player_data = schema_cls.model_validate(player)
```

### What does NOT change

- `POST /` and `PUT /{id}` continue returning `PlayerSchema` only.
- No new endpoints, auth classes, or model changes.
- `DELETE /{id}` is unaffected.

## Files modified

1. `backend/api/v1/schemas/players.py` — add `PlayerAdminSchema`
2. `backend/api/v1/routers/resources/players.py` — conditional schema selection in GET handler
