# SRC API Key Storage & Moderator System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **IMPORTANT:** Do NOT commit anything without explicit user approval. Present diffs for review first.

**Goal:** Enable game moderators to securely store their Speedrun.com API keys (encrypted at rest) so they can later approve runs on thps.run with those keys forwarded to SRC.

**Architecture:** Fernet symmetric encryption (from the `cryptography` library) protects SRC API keys at rest. A server-side encryption key in `.env` encrypts on write and decrypts on read. A new `SRCCredential` model (OneToOne to Django's `auth.User`) stores the encrypted key — this keeps it off the `Player` model and away from any public API schema. A new M2M field on `Games` links to `Players` for moderator assignments. The `/me` endpoint is extended to let mods submit, view status of, and delete their SRC API key.

**Tech Stack:** Django 6.x, django-ninja, cryptography (Fernet), Pydantic v2

**Why a separate SRCCredential model?** Django's built-in `auth.User` cannot have fields added to it without migrating to a custom user model (disruptive on an existing project). A OneToOne extension model is the standard Django pattern. The `Player` model is linked to `User` but is exposed through the API — keeping the credential on a separate, unexposed model provides defense-in-depth.

**Why Fernet?** Fernet provides authenticated symmetric encryption with built-in key derivation, IV generation, and HMAC verification. The encrypted value is tamper-evident and includes a timestamp. Decryption requires the same key that encrypted it (stored in `.env` as `SRC_ENCRYPTION_KEY`). If the key is lost, all stored SRC API keys become unrecoverable — users would need to re-submit.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/srl/encryption.py` | Fernet encrypt/decrypt utility functions |
| Create | `backend/srl/models/src_credential.py` | `SRCCredential` model (OneToOne to User) |
| Modify | `backend/srl/models/__init__.py` | Export `SRCCredential` |
| Modify | `backend/srl/models/games.py` | Add `moderators` M2M to Players |
| Create | `backend/srl/migrations/0026_add_src_credential.py` | Migration for SRCCredential model |
| Create | `backend/srl/migrations/0027_add_game_moderators.py` | Migration for Games.moderators M2M |
| Modify | `backend/api/v1/schemas/auth.py` | New schemas: `SRCKeyRequest`, `SRCKeyStatusResponse`, `ModeratedGameSchema`; update `PlayerProfileResponse` |
| Modify | `backend/api/v1/routers/auth/me.py` | New endpoints: POST/DELETE `/me/src-key`; update `_build_profile_response` |
| Modify | `backend/website/settings.py` | Add `SRC_ENCRYPTION_KEY` setting |
| Modify | `.env.example` | Add `SRC_ENCRYPTION_KEY` placeholder |
| Modify | `requirements.txt` | Add `cryptography` |

---

## Task 1: Add Encryption Infrastructure

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `backend/website/settings.py`
- Create: `backend/srl/encryption.py`

- [ ] **Step 1: Add `cryptography` to requirements.txt**

Add after the `celery-types` line:

```
cryptography>=44.0.0
```

- [ ] **Step 2: Add `SRC_ENCRYPTION_KEY` to `.env.example`**

Add under the `# Auth / Email` section:

```env
# SRC API Key Encryption (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
SRC_ENCRYPTION_KEY=
```

- [ ] **Step 3: Add `SRC_ENCRYPTION_KEY` to Django settings**

In `backend/website/settings.py`, add near the other `os.getenv()` calls (e.g., after the `SECRET_KEY` line):

```python
SRC_ENCRYPTION_KEY = os.getenv("SRC_ENCRYPTION_KEY", "")
```

- [ ] **Step 4: Create the encryption utility module**

Create `backend/srl/encryption.py`:

```python
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _get_fernet() -> Fernet:
    """Returns a Fernet instance using the configured encryption key."""
    key = settings.SRC_ENCRYPTION_KEY
    if not key:
        raise ValueError(
            "SRC_ENCRYPTION_KEY is not configured. "
            "Generate one with: python -c "
            "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode())


def encrypt_src_key(plain_key: str,) -> str:
    """Encrypts an SRC API key for database storage.

    Args:
        plain_key: The raw SRC API key.

    Returns:
        The Fernet-encrypted ciphertext as a UTF-8 string.
    """
    f = _get_fernet()
    return f.encrypt(plain_key.encode()).decode()


def decrypt_src_key(encrypted_key: str,) -> str:
    """Decrypts a stored SRC API key for use in SRC API calls.

    Args:
        encrypted_key: The Fernet-encrypted ciphertext.

    Returns:
        The original plaintext SRC API key.

    Raises:
        cryptography.fernet.InvalidToken: If the key is corrupted or the
            encryption key has changed.
    """
    f = _get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()
```

- [ ] **Step 5: Generate an encryption key for local development**

Run locally or in the Django container:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output into your `.env` file as `SRC_ENCRYPTION_KEY=<generated_key>`.

---

## Task 2: Create SRCCredential Model

**Files:**
- Create: `backend/srl/models/src_credential.py`
- Modify: `backend/srl/models/__init__.py`
- Create: migration (via `makemigrations`)

- [ ] **Step 1: Create the SRCCredential model file**

Create `backend/srl/models/src_credential.py`:

```python
from django.db import models


class SRCCredential(models.Model):
    class Meta:
        verbose_name = "SRC Credential"
        verbose_name_plural = "SRC Credentials"

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="src_credential",
    )
    encrypted_api_key = models.TextField(
        verbose_name="Encrypted SRC API Key",
        help_text="Fernet-encrypted SRC API key. Never expose this value in any API response.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self) -> str:
        return f"SRC Credential for {self.user.username}"
```

- [ ] **Step 2: Export from models `__init__.py`**

In `backend/srl/models/__init__.py`, add the import and `__all__` entry:

```python
from srl.models.src_credential import SRCCredential
```

Add `"SRCCredential"` to the `__all__` list.

- [ ] **Step 3: Generate the migration**

```bash
python manage.py makemigrations srl --name add_src_credential
```

Verify the generated migration creates the `SRCCredential` table with `user` (OneToOne), `encrypted_api_key` (TextField), `created_at`, and `updated_at`.

- [ ] **Step 4: Run the migration**

```bash
python manage.py migrate
```

---

## Task 3: Add Moderators M2M to Games

**Files:**
- Modify: `backend/srl/models/games.py:60` (after `platforms` field)
- Create: migration (via `makemigrations`)

- [ ] **Step 1: Add the moderators field to Games**

In `backend/srl/models/games.py`, add an import for `Players` and a new M2M field.

First, add the import at the top of the file (after the `Platforms` import on line 5):

```python
from srl.models.players import Players
```

Then add the field after the `platforms` M2M field (after line 63):

```python
    moderators = models.ManyToManyField(
        Players,
        related_name="moderated_games",
        verbose_name="Moderators",
        blank=True,
        help_text=(
            "Players who are moderators for this game on thps.run. "
            "If a player is a moderator here but not on SRC, thps.run takes precedence."
        ),
    )
```

Note: Direct import is safe here — `players.py` does not import from `games.py`, so there is no circular import risk. This follows the existing codebase pattern (e.g., `Platforms` is imported directly).

- [ ] **Step 2: Generate the migration**

```bash
python manage.py makemigrations srl --name add_game_moderators
```

Verify the generated migration creates a M2M through table for `Games.moderators`.

- [ ] **Step 3: Run the migration**

```bash
python manage.py migrate
```

---

## Task 4: Update Auth Schemas

**Files:**
- Modify: `backend/api/v1/schemas/auth.py`

- [ ] **Step 1: Add new schemas for SRC key management**

Add these schemas to `backend/api/v1/schemas/auth.py`:

```python
class SRCKeyRequest(Schema):
    src_api_key: str = Field(
        ...,
        min_length=1,
        description="Speedrun.com API key to store for run approvals",
    )


class SRCKeyStatusResponse(Schema):
    has_src_key: bool
    message: str
```

- [ ] **Step 2: Add ModeratedGameSchema**

Add to the same file:

```python
class ModeratedGameSchema(Schema):
    id: str
    name: str
    slug: str
```

- [ ] **Step 3: Update PlayerProfileResponse**

Add three new fields to `PlayerProfileResponse`:

```python
class PlayerProfileResponse(Schema):
    player_id: str
    name: str
    nickname: str | None
    pronouns: str | None
    countrycode: str | None
    twitch: str | None
    youtube: str | None
    twitter: str | None
    bluesky: str | None
    pfp: str | None
    claim_status: str
    username: str
    is_moderator: bool = False
    has_src_key: bool = False
    moderated_games: list[ModeratedGameSchema] = []
```

---

## Task 5: Update `/me` Profile Response

**Files:**
- Modify: `backend/api/v1/routers/auth/me.py`

- [ ] **Step 1: Add imports**

Update the existing `api.v1.schemas.auth` import in `me.py` to include `ModeratedGameSchema`, and add a new import for `SRCCredential`:

```python
from srl.models import CountryCodes, Players, SRCCredential

from api.v1.schemas.auth import (
    CountryCodeResponse,
    ModeratedGameSchema,
    PfpUploadResponse,
    PlayerProfileResponse,
    PlayerUpdateRequest,
)
```

(The `srl.models` import line replaces the existing one to add `SRCCredential`. The `api.v1.schemas.auth` import replaces the existing one to add `ModeratedGameSchema`.)

- [ ] **Step 2: Update `_build_profile_response` to include moderator data**

Replace the existing `_build_profile_response` function:

```python
def _build_profile_response(
    player: Players,
) -> PlayerProfileResponse:
    """Creates the profile response from the Players model to return to the user."""
    # Note: For a single-player profile endpoint, these 2-3 queries are acceptable.
    # If this were a list endpoint, we'd prefetch moderated_games and src_credential
    # on the queryset instead.
    moderated = player.moderated_games.all()

    has_src_key = False
    if player.user_id:
        has_src_key = SRCCredential.objects.filter(user_id=player.user_id).exists()

    return PlayerProfileResponse(
        player_id=player.id,
        name=player.name,
        nickname=player.nickname,
        pronouns=player.pronouns,
        countrycode=player.countrycode.id if player.countrycode else None,
        twitch=player.twitch,
        youtube=player.youtube,
        twitter=player.twitter,
        bluesky=player.bluesky,
        pfp=player.pfp,
        claim_status=player.claim_status,
        username=player.user.username if player.user else "",
        is_moderator=moderated.exists(),
        has_src_key=has_src_key,
        moderated_games=[
            ModeratedGameSchema(id=g.id, name=g.name, slug=g.slug)
            for g in moderated
        ],
    )
```

---

## Task 6: Add `/me/src-key` Endpoints

**Files:**
- Modify: `backend/api/v1/routers/auth/me.py`

- [ ] **Step 1: Add additional imports for the new endpoints**

These are *additional* imports to add to `me.py` on top of those already added in Task 5. Add them to the appropriate location in the existing import groups:

```python
import requests as http_requests  # add to stdlib/third-party imports at top

from api.rate_limiting import auth_rate_limit  # add to api imports section
from api.v1.schemas.auth import SRCKeyRequest, SRCKeyStatusResponse  # merge into existing auth import
from srl.encryption import encrypt_src_key  # add to srl imports section
```

The final merged `api.v1.schemas.auth` import should look like:

```python
from api.v1.schemas.auth import (
    CountryCodeResponse,
    ModeratedGameSchema,
    PfpUploadResponse,
    PlayerProfileResponse,
    PlayerUpdateRequest,
    SRCKeyRequest,
    SRCKeyStatusResponse,
)
```

Note: `dedent` and `requests` (`http_requests`) are not in the existing `me.py` — `dedent` is already imported (line 4), but `requests` is new.

- [ ] **Step 2: Add the POST `/me/src-key` endpoint**

Add after the `upload_pfp` endpoint and before `delete_me`:

```python
@router.post(
    "/me/src-key",
    response={200: SRCKeyStatusResponse, codes_4xx: ErrorResponse},
    summary="Store SRC API Key",
    description=dedent(
        """
    Stores an encrypted Speedrun.com API key for the authenticated player.
    Only available to players who are moderators of at least one game.
    The key is verified against the SRC API to confirm it belongs to the
    authenticated player before storage.
    """
    ),
    auth=player_session_auth,
)
@auth_rate_limit
def set_src_key(
    request: HttpRequest,
    body: SRCKeyRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    if not player.moderated_games.exists():
        return Status(
            403,
            ErrorResponse(
                error="Only moderators can store an SRC API key",
                details=None,
            ),
        )

    # Verify the SRC API key by calling the SRC profile endpoint
    try:
        src_response = http_requests.get(
            "https://www.speedrun.com/api/v1/profile",
            headers={"X-API-Key": body.src_api_key},
            timeout=10,
        )
    except http_requests.RequestException:
        return Status(
            400,
            ErrorResponse(
                error="Failed to contact Speedrun.com API",
                details=None,
            ),
        )

    if src_response.status_code != 200:
        return Status(
            400,
            ErrorResponse(
                error="Invalid or expired SRC API key",
                details=None,
            ),
        )

    try:
        src_data = src_response.json()
        src_user_id: str = src_data["data"]["id"]
    except (KeyError, ValueError) as e:
        return Status(
            400,
            ErrorResponse(
                error="Unexpected response from Speedrun.com API",
                details={"exception": str(e)},
            ),
        )

    # Ensure the API key belongs to the authenticated player
    if src_user_id != player.id:
        return Status(
            403,
            ErrorResponse(
                error="This SRC API key does not belong to your account",
                details=None,
            ),
        )

    # Encrypt and store (update_or_create handles both new and existing)
    encrypted = encrypt_src_key(body.src_api_key)
    SRCCredential.objects.update_or_create(
        user=player.user,
        defaults={"encrypted_api_key": encrypted},
    )

    return Status(
        200,
        SRCKeyStatusResponse(
            has_src_key=True,
            message="SRC API key stored successfully",
        ),
    )
```

- [ ] **Step 3: Add the DELETE `/me/src-key` endpoint**

Add after `set_src_key`:

```python
@router.delete(
    "/me/src-key",
    response={204: None, codes_4xx: ErrorResponse},
    summary="Remove SRC API Key",
    description=dedent(
        """
    Removes the stored SRC API key for the authenticated player.
    After removal, the player will not be able to approve runs until
    they re-submit their key.
    """
    ),
    auth=player_session_auth,
)
def delete_src_key(
    request: HttpRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    if not player.user:
        return Status(
            404,
            ErrorResponse(
                error="No SRC API key found",
                details=None,
            ),
        )

    deleted, _ = SRCCredential.objects.filter(user=player.user).delete()
    if not deleted:
        return Status(
            404,
            ErrorResponse(
                error="No SRC API key found",
                details=None,
            ),
        )

    return Status(204, None)
```

- [ ] **Step 4: Update `delete_me` to also clear moderator assignments**

In the existing `delete_me` endpoint, add inside the `transaction.atomic()` block (before `if user is not None: user.delete()`):

```python
            # Remove moderator assignments for the deleted account
            player.moderated_games.clear()
```

This ensures a deleted account doesn't remain listed as a moderator for any game.

---

## Task 7: Add Moderated Games to Public Player Profile (Optional)

> **Note:** This task adds `moderated_games` as an embed on the public `/players/{id}` endpoint. The user expressed this as a "maybe" — skip if not desired.

**Files:**
- Modify: `backend/api/v1/schemas/players.py`
- Modify: `backend/api/v1/routers/resources/players.py`
- Modify: `backend/api/v1/schemas/base.py` (VALID_EMBEDS registration)

Note: Task 4 already defines `ModeratedGameSchema` in `auth.py` for the `/me` response. For the public embed, we reuse that same schema shape but define `ModeratedGameEmbedSchema` extending `BaseEmbedSchema` to follow the embed pattern used by other player embeds (e.g., `CountrySchema`, `AwardSchema`).

- [ ] **Step 1: Add ModeratedGameEmbedSchema to player schemas**

In `backend/api/v1/schemas/players.py`, add:

```python
class ModeratedGameEmbedSchema(BaseEmbedSchema):
    """Schema for games a player moderates.

    Attributes:
        id (str): Game ID.
        name (str): Game name.
        slug (str): Game slug/abbreviation.
    """

    id: str
    name: str
    slug: str
```

- [ ] **Step 2: Add embed field to PlayerSchema**

In `PlayerSchema`, add a new field:

```python
    moderated_games: list[ModeratedGameEmbedSchema] | None = Field(
        None, description="Games this player moderates - included with ?embed=moderator.",
    )
```

- [ ] **Step 3: Register the embed in VALID_EMBEDS**

In `backend/api/v1/schemas/base.py`, add `"moderator"` to the `VALID_EMBEDS` dict for the players endpoint (follow existing pattern for how embeds are registered).

- [ ] **Step 4: Add embed handling in the players router**

In `backend/api/v1/routers/resources/players.py`, add logic to handle the `moderator` embed in the player detail endpoint:

```python
if "moderator" in embeds:
    player_data["moderated_games"] = [
        {"id": g.id, "name": g.name, "slug": g.slug}
        for g in player.moderated_games.all()
    ]
```

And add `prefetch_related("moderated_games")` to the player queryset when the `moderator` embed is requested.

---

## Summary of Changes by File

| File | What Changes |
|------|-------------|
| `requirements.txt` | + `cryptography>=44.0.0` |
| `.env.example` | + `SRC_ENCRYPTION_KEY=` with generation instructions |
| `backend/website/settings.py` | + `SRC_ENCRYPTION_KEY` env read |
| `backend/srl/encryption.py` | New: `encrypt_src_key()`, `decrypt_src_key()` |
| `backend/srl/models/src_credential.py` | New: `SRCCredential` model |
| `backend/srl/models/__init__.py` | + import and export `SRCCredential` |
| `backend/srl/models/games.py` | + `moderators` M2M field |
| `backend/api/v1/schemas/auth.py` | + `SRCKeyRequest`, `SRCKeyStatusResponse`, `ModeratedGameSchema`; updated `PlayerProfileResponse` |
| `backend/api/v1/routers/auth/me.py` | + POST/DELETE `/me/src-key`; updated `_build_profile_response`; updated `delete_me` |
| Migrations (auto-generated) | `0026_add_src_credential`, `0027_add_game_moderators` |

---

## Security Considerations

1. **Encryption key rotation:** If `SRC_ENCRYPTION_KEY` changes, all stored credentials become unrecoverable. For a future enhancement, consider storing a key version identifier alongside the encrypted value to support key rotation.
2. **Memory exposure:** The decrypted key exists briefly in process memory during Celery task execution. This is standard for any encryption-at-rest approach. Avoid logging the decrypted value.
3. **API key verification:** The POST `/me/src-key` endpoint verifies the SRC API key belongs to the authenticated player by calling the SRC profile API and matching the returned user ID. This prevents storing someone else's key.
4. **Rate limiting:** The POST `/me/src-key` endpoint uses `@auth_rate_limit` since it makes an external API call to SRC. Note: this decorator is IP-based (uses `REMOTE_ADDR`), which is consistent with the existing `verify_src.py` pattern. A per-user rate limit could be added later if needed.
5. **Cascade deletion:** `SRCCredential` uses `on_delete=CASCADE` — when the Django User is deleted, the credential is automatically removed.
6. **No exposure in API:** The encrypted key is never included in any API response. Only a boolean `has_src_key` is exposed in the `/me` profile.

---

## Future Work (Out of Scope)

- **Run approval workflow:** The actual endpoint where a moderator approves a run and the approval is forwarded to SRC via Celery. This will consume `decrypt_src_key()` from the encryption module.
- **SRC moderator sync:** Syncing moderator assignments from Speedrun.com to the `Games.moderators` M2M.
- **Superuser moderator assignment endpoint:** An API endpoint for superusers to assign/remove moderators.
- **Encryption key rotation:** Supporting multiple encryption keys for zero-downtime rotation.
