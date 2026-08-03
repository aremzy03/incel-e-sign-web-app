# First-Party Integrations: Server-to-Server Orchestration Plan

## 1. Purpose

Enable trusted first-party applications to create and send envelopes on behalf of real e-sign users so that:

- Each user in the other application maps to an e-sign `CustomUser`.
- When that user creates/sends an envelope via the integration, `Envelope.creator` is that user.
- The envelope appears in the e-sign UI (list, detail, dashboard) exactly as if created in the product UI.
- Partner apps authenticate as machines for **token exchange only**; all business API calls use a **user-scoped JWT**.

This document is the architecture and implementation map for that feature.

---

## 2. Goals & Non-Goals

### Goals

- Admin-registered integrations (`client_id` + hashed `client_secret`).
- Token exchange: client credentials + user identity → SimpleJWT access/refresh for that user.
- Reuse existing document upload, envelope create, and envelope send APIs.
- Preserve audit, notifications, signing workflow reset, and ownership rules.
- Testable end-to-end path matching current `APITestCase` / pytest patterns.

### Non-Goals (MVP)

- Public third-party developer portal / self-serve app registration.
- Per-user personal API keys.
- OAuth2 authorization-code “Connect e-sign” for untrusted partners.
- Outbound webhooks (follow-up).
- Guest / email-only signers that are not e-sign users (follow-up: find-or-invite).
- Parallel “integration envelope” domain model.

---

## 3. Product Decisions (Locked)


| Decision            | Choice                                          | Rationale                                                       |
| ------------------- | ----------------------------------------------- | --------------------------------------------------------------- |
| Actor for envelopes | Real `CustomUser`                               | UI parity via existing `creator` / queryset rules               |
| App registration    | **Admin / staff only**                          | Client secret can mint JWTs for asserted emails; high privilege |
| Developer accounts  | **Not for MVP**                                 | Only needed for public partner ecosystem                        |
| Auth after exchange | Existing SimpleJWT                              | Same as login / Google OAuth; no new business auth class        |
| Envelope APIs       | Reuse `/api/documents/`, `/api/envelopes/`      | Avoid duplicating create/send logic                             |
| User join key       | Email (unique on `CustomUser`)                  | Matches Google OAuth find/create pattern                        |
| JIT user create     | Configurable (recommend **on** for first-party) | Other app may onboard users who never opened e-sign UI          |


---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        First-party application                          │
│  (CRM / HR / internal portal — server side only holds client_secret)    │
└───────────────┬─────────────────────────────────────┬───────────────────┘
                │ 1. POST /api/v1/integrations/token/ │
                │    client_id + client_secret        │
                │    + email (+ optional full_name)   │
                ▼                                     │
┌───────────────────────────────────┐                 │
│  e-sign integrations service      │                 │
│  - Verify client credentials      │                 │
│  - Resolve / JIT CustomUser       │                 │
│  - RefreshToken.for_user(user)    │                 │
│  - Optional JWT claims:           │                 │
│      client_id, auth_via          │                 │
└───────────────┬───────────────────┘                 │
                │ 2. { access, refresh }              │
                ▼                                     │
┌───────────────────────────────────┐                 │
│  Existing JWT-protected APIs      │◄────────────────┘
│  Authorization: Bearer <access>   │  3. upload → create → send
│  request.user = that CustomUser   │
│  - POST /api/documents/upload/    │
│  - POST /api/envelopes/create/    │
│  - POST /api/envelopes/{id}/send/ │
│  - GET  /api/envelopes/{id}/      │
└───────────────┬───────────────────┘
                │
                ▼
┌───────────────────────────────────┐
│  Domain (unchanged ownership)     │
│  Document.owner = user            │
│  Envelope.creator = user          │
│  Audit actor = user               │
│  Notifications / Celery as today  │
│  UI list = get_envelopes_         │
│    accessible_by_user(user)       │
└───────────────────────────────────┘
```

### Identity model

Two identities on the wire, separated by phase:


| Phase          | Identity              | Mechanism                     |
| -------------- | --------------------- | ----------------------------- |
| Token exchange | Integration (machine) | `client_id` + `client_secret` |
| Business APIs  | End user              | User JWT (`request.user`)     |


Never use a shared “service user” as `Envelope.creator` for multi-user first-party apps.

---

## 5. Current System Constraints (Must Respect)

Source of truth in codebase today:

- Auth: DRF `JWTAuthentication` only; envelopes require `IsAuthenticated`.
- Create: `EnvelopeCreateSerializer` — documents must be owned by `request.user`; signers must be existing `CustomUser` UUIDs.
- Send: creator-only; `draft`/`rejected` → `pending`; resets signing workflow; notifies first signer.
- Access: `get_envelopes_accessible_by_user()` — creator **or** signer.
- Users: `CustomUser` with unique `email` as `USERNAME_FIELD`.
- Tokens: `RefreshToken.for_user(user)` in `users/views.py` (login / Google OAuth).
- No existing API-key, integration, or webhook models.

Partner flows must not bypass document ownership or creator checks.

---

## 6. Data Model

New Django app: `integrations`.

### 6.1 `Integration`


| Field                       | Type                  | Notes                                                            |
| --------------------------- | --------------------- | ---------------------------------------------------------------- |
| `id`                        | UUID PK               |                                                                  |
| `name`                      | CharField             | Human label, e.g. "HR Portal"                                    |
| `client_id`                 | CharField, unique     | Public identifier (uuid or opaque string)                        |
| `client_secret_hash`        | CharField             | Store hash only (e.g. Django `make_password` / dedicated hasher) |
| `is_active`                 | Boolean               | Soft disable without delete                                      |
| `allow_jit_user_create`     | Boolean               | Default `True` for first-party; can disable per app              |
| `created_by`                | FK `CustomUser`, null | Staff who registered it                                          |
| `notes`                     | TextField, blank      | Ops notes                                                        |
| `created_at` / `updated_at` | DateTime              |                                                                  |


**Secret handling**

- On create (admin action): generate high-entropy secret, show **once**, store only hash.
- Rotation: generate new secret, invalidate old hash, show once again.
- Compare with constant-time verification.

### 6.2 `IntegrationUserLink` (optional MVP+, recommended soon)


| Field              | Type                              | Notes             |
| ------------------ | --------------------------------- | ----------------- |
| `id`               | UUID PK                           |                   |
| `integration`      | FK                                |                   |
| `user`             | FK `CustomUser`                   |                   |
| `external_user_id` | CharField                         | Partner’s user id |
| `linked_at`        | DateTime                          |                   |
| Unique             | `(integration, external_user_id)` |                   |
| Unique             | `(integration, user)`             | Optional          |


MVP can resolve by email only; add this when partner user ids should be stable even if email changes.

### 6.3 Out of scope for MVP models

- Per-integration scopes table (can add later: `envelopes:write`, etc.).
- Webhook endpoints / delivery logs.
- Organization / tenant tables.

---

## 7. API Design

### 7.1 Versioned integration auth

Base path: `/api/v1/integrations/`


| Method | Path                                       | Auth                              | Purpose                                                             |
| ------ | ------------------------------------------ | --------------------------------- | ------------------------------------------------------------------- |
| `POST` | `/api/v1/integrations/token/`              | None (client credentials in body) | Exchange → user JWT                                                 |
| `POST` | `/api/v1/integrations/`                    | Staff / admin only                | Register integration (optional API; Django admin is enough for MVP) |
| `POST` | `/api/v1/integrations/{id}/rotate-secret/` | Staff only                        | Rotate secret                                                       |


#### Token exchange request

```http
POST /api/v1/integrations/token/
Content-Type: application/json

{
  "client_id": "int_...",
  "client_secret": "...",
  "email": "ada@example.com",
  "full_name": "Ada Lovelace"
}
```

Optional later:

```json
{
  "external_user_id": "hr-user-123"
}
```

#### Token exchange response (align with existing auth shape)

```json
{
  "status": "success",
  "message": "Token issued successfully",
  "data": {
    "access": "<jwt>",
    "refresh": "<jwt>",
    "user": {
      "id": "<uuid>",
      "email": "ada@example.com",
      "full_name": "Ada Lovelace"
    }
  }
}
```

#### Error cases


| Condition                        | Status |
| -------------------------------- | ------ |
| Unknown `client_id` / bad secret | 401    |
| Inactive integration             | 401    |
| User not found and JIT disabled  | 404    |
| Invalid email / validation       | 400    |
| Throttled                        | 429    |


### 7.2 Business APIs (unchanged)

After exchange, partner uses existing endpoints with `Authorization: Bearer <access>`:

1. `POST /api/documents/upload/`
2. `POST /api/envelopes/create/`
3. `POST /api/envelopes/{id}/send/`
4. `GET /api/envelopes/{id}/` (status polling)

Signers in `signing_order` remain **existing user UUIDs** until a find-or-invite enhancement ships.

### 7.3 Optional composite endpoint (phase 2)

`POST /api/v1/integrations/envelopes/send/` — multipart/json orchestration of upload + create + send in one call. Must call the same internal create/send services (or serializers) to keep audit/notifications identical. Not required for MVP if partners can do three calls.

---

## 8. Auth & Token Details

### Issuance

Reuse SimpleJWT exactly as `LoginView` / Google callback:

```python
refresh = RefreshToken.for_user(user)
refresh["client_id"] = integration.client_id
refresh["auth_via"] = "integration"
access = refresh.access_token
# Mirror claims on access if needed for audit middleware
```

### Lifetimes

- Start with existing `SIMPLE_JWT` settings (access 8h, refresh 7d).
- Prefer partners treat access as short-lived: exchange → act → discard for fire-and-forget flows.
- Consider a shorter access lifetime for `auth_via=integration` later if risk requires it.

### Blacklist / logout

Refresh tokens remain blacklistable via existing logout / rotation settings.

### DRF configuration

- No change to default `JWTAuthentication` for business routes.
- Token endpoint: `AllowAny` + dedicated throttle scope (reuse `auth` or add `integration_token`).

---

## 9. Registration & Operations

### Who registers integrations?

**Staff/admin only** (Django admin for MVP).

Do **not** open registration to normal users while token exchange can assert arbitrary emails.

### Admin workflows

1. Staff creates `Integration` (name, JIT flag, notes).
2. System generates `client_id` + raw `client_secret`; display secret once.
3. Ops store secret in partner app env vars.
4. Staff can deactivate (`is_active=False`) or rotate secret.
5. Audit admin actions (Django admin log and/or `audit.log_action`).

### Partner configuration (env)

```env
ESIGN_BASE_URL=https://api.example.com
ESIGN_CLIENT_ID=int_...
ESIGN_CLIENT_SECRET=...
```

---

## 10. User Resolution Rules

On token exchange:

1. Normalize email (lowercase/strip).
2. If `CustomUser` exists with that email → use it (update `full_name` only if empty / policy allows).
3. If missing and `integration.allow_jit_user_create` → create user:
  - `email`, `username=email`, `full_name` (required or fallback to email local-part)
  - Unusable password (`set_unusable_password()`) so login is via Google/password reset later
4. If missing and JIT off → 404 with clear message.
5. If user `is_active=False` → 403.

Optional: upsert `IntegrationUserLink` when `external_user_id` provided.

---

## 11. Partner Orchestration Sequence

```
Other app (authenticated local user)
  │
  ├─1─ POST /api/v1/integrations/token/
  │      { client_id, client_secret, email, full_name }
  │    ← access, refresh, user.id
  │
  ├─2─ POST /api/documents/upload/          (Bearer access)
  │    ← document_id
  │
  ├─3─ Resolve signer UUIDs in e-sign
  │      (search existing users / pre-provisioned accounts)
  │
  ├─4─ POST /api/envelopes/create/          (Bearer access)
  │      { name, document_ids, signing_order, ... }
  │    ← envelope_id (status: draft)
  │
  ├─5─ POST /api/envelopes/{id}/send/       (Bearer access)
  │    ← status: pending; first signer notified
  │
  └─6─ Store envelope_id in other app; optional poll GET /api/envelopes/{id}/
```

### UI parity check

Same user logs into e-sign UI → `GET /api/envelopes/` includes the envelope (`creator=user`).

---

## 12. Security Controls


| Control                 | MVP requirement                                                    |
| ----------------------- | ------------------------------------------------------------------ |
| Secret at rest          | Hashed only                                                        |
| Secret in transit       | HTTPS only in production                                           |
| Registration            | Staff only                                                         |
| Token endpoint throttle | Strict (e.g. reuse `auth` 10/minute or tighter per IP + client_id) |
| Inactive clients        | Rejected                                                           |
| Impersonation surface   | Trusted first-party only; document threat model                    |
| JWT claims              | `client_id`, `auth_via` for forensic audit                         |
| Logging                 | Never log raw `client_secret` or full tokens                       |
| Optional                | IP allowlist field on `Integration`                                |


### Threat model (accepted for first-party)

Compromise of `client_secret` ≈ ability to mint sessions for any email (if JIT on) or any existing user email. Mitigations: rotate, deactivate, network restrict, monitor exchange volume.

---

## 13. Audit & Observability

- On successful token exchange: optional audit action `INTEGRATION_TOKEN_EXCHANGE` (actor = resolved user, metadata = `client_id`).
- Envelope create/send: existing `CREATE_ENVELOPE` / `SEND_ENVELOPE` with `request.user` (real user). Enrich metadata with `client_id` from JWT claims when present.
- Metrics/logs: count exchanges by `client_id`, failures (bad secret, inactive, unknown user).
- Sentry: tag `auth_via=integration` where available.

---

## 14. Codebase Layout

```text
integrations/
├── __init__.py
├── apps.py
├── models.py              # Integration, (IntegrationUserLink)
├── admin.py               # Create + one-time secret display, rotate action
├── serializers.py         # TokenExchangeSerializer, IntegrationAdminSerializer
├── views.py               # TokenExchangeView, (admin create/rotate)
├── services/
│   ├── credentials.py     # generate/hash/verify secret
│   ├── token_exchange.py  # resolve user + issue JWT
│   └── users.py           # find / JIT create
├── urls.py
├── throttles.py           # optional dedicated throttle
├── tests/
│   ├── test_models.py
│   ├── test_token_exchange.py
│   ├── test_credentials.py
│   └── test_envelope_parity.py
└── migrations/
```

Wire in:

- `INSTALLED_APPS` → `integrations`
- `esign/urls.py` → `path('api/v1/integrations/', include('integrations.urls'))`

Do **not** fork envelope create/send into this app for MVP; call existing views via HTTP from partner, or later extract shared services if composite endpoint is added.

---

## 15. Implementation Phases

### Phase 0 — Foundations

- [x] Create `integrations` app and models.
- [x] Migrations + Django admin (create, deactivate, rotate secret UX).
- [x] Credential generate / hash / verify helpers.
- [x] Unit tests for credentials.

### Phase 1 — Token exchange

- [x] `POST /api/v1/integrations/token/`
- [x] User resolve + JIT create path
- [x] JWT issuance with `client_id` / `auth_via` claims
- [x] Throttling + error contract
- [x] API tests for success / 401 / 404 / inactive / JIT off

### Phase 2 — End-to-end partner flow (no new business endpoints)

- [x] Document partner sequence in README (or this doc appendix)
- [x] Integration test: exchange → upload → create → send → assert creator + list visibility
- [x] Mock Celery email like existing envelope send tests

### Phase 3 — Hardening (recommended before production)

- [x] `IntegrationUserLink` (if needed)
- [x] Audit enrichment with `client_id`
- [x] IP allowlist (optional)
- [x] Secret rotation runbook
- [x] Shorter integration access token lifetime (optional)

### Phase 4 — Follow-ups (out of MVP)

- [ ] Email-based signer resolution / find-or-invite
- [ ] Composite create-and-send endpoint
- [ ] Outbound webhooks (`envelope.sent`, `envelope.completed`)
- [ ] Idempotency-Key on create/send
- [ ] Public developer portal (only if third parties appear)

---

## 16. Testing Strategy

Align with existing patterns: `APITestCase` + `APIClient`, fixtures in `integrations/tests/`, Celery eager in `esign.test_settings`.

### Unit

- Secret hashing and verify (wrong secret fails).
- User resolve: existing email; JIT create; JIT disabled; inactive user.

### API — token exchange

- Valid credentials + email → 200, JWT authenticates as that user.
- Bad secret / unknown client / inactive → 401.
- Unknown email + JIT off → 404.
- Unknown email + JIT on → user created with unusable password.
- Throttle behavior (optional smoke).

### API — UI parity (critical)

1. Exchange as user A.
2. Upload + create + send with access token.
3. Assert `envelope.creator_id == user_a.id`.
4. Authenticate as user A via normal `RefreshToken.for_user` (simulating UI).
5. `GET /api/envelopes/` includes that envelope.
6. Other user B does not see it (unless signer).

### Regression

- Existing envelope create/send tests remain green.
- Document ownership still enforced when JWT user ≠ document owner.

### Manual / partner

- Postman collection: token → upload → create → send → get.
- Staging integration with real first-party app env secrets.

---

## 17. Configuration

Suggested settings / env (names illustrative):


| Setting                                          | Purpose                              |
| ------------------------------------------------ | ------------------------------------ |
| (none required beyond existing JWT)              | Reuse `SIMPLE_JWT`                   |
| Optional `INTEGRATION_TOKEN_THROTTLE`            | Override throttle rate               |
| `INTEGRATION_ACCESS_TOKEN_LIFETIME` / `INTEGRATION_ACCESS_TOKEN_LIFETIME_MINUTES` | Shorter access JWT for `auth_via=integration` (default 30m) |


Secrets for partners live in **partner** env, not in e-sign `.env` (except when e-sign itself is the client).

---

## 18. Documentation Deliverables

- This orchestration plan (`docs/integrations-s2s-orchestration-plan.md`).
- README section: “First-party integrations” with sequence and admin registration steps.
- OpenAPI/Swagger update when token endpoint ships (per project API rules).
- Ops runbook: create integration, rotate secret, revoke compromised client
  (`docs/integrations-secret-rotation-runbook.md`).

---

## 19. Success Criteria

MVP is done when:

1. Staff can register an integration and obtain a one-time `client_secret`.
2. Partner can exchange credentials + user email for a JWT.
3. Partner can upload, create, and send an envelope with that JWT.
4. The same user sees the envelope in e-sign UI list/dashboard as creator.
5. Automated tests cover exchange failures and UI parity.
6. Raw secrets are never stored; inactive clients cannot exchange.

---

## 20. Open Questions (Resolve During Phase 0/1)


| Question                                           | Recommendation                                                 |
| -------------------------------------------------- | -------------------------------------------------------------- |
| JIT create on by default?                          | **Yes** for first-party; per-integration flag                  |
| Staff-only via Django admin or also REST?          | **Admin first**; REST only if ops needs automation             |
| Put `client_id` on access token, refresh, or both? | Both if SimpleJWT allows easy claim copy                       |
| Require `full_name` on exchange?                   | Required when JIT create; optional if user exists              |
| Signer provisioning from partner                   | Out of MVP; document that signers must already be e-sign users |


---

## 21. Summary

Implement a small `integrations` app whose only job is **admin-trusted client credentials → user JWT**. Reuse the existing document and envelope pipeline so ownership, audit, notifications, and UI visibility stay correct. Keep registration admin-only while the exchange endpoint can assert user identity. Expand later with links, webhooks, and email-based signers without changing the core “real user as creator” model.

---

## Appendix A — Partner sequence (quick reference)

**Admin (one-liner):** Django admin → create Integration → copy one-time `client_id` / `client_secret` into the partner app env.

**Partner flow:**

1. `POST /api/v1/integrations/token/` with `client_id`, `client_secret`, `email` (+ `full_name` when JIT-creating) → user-scoped `access` / `refresh`.
2. `POST /api/documents/upload/` with `Authorization: Bearer <access>` → `document_id`.
3. `POST /api/envelopes/create/` with document IDs and `signing_order` → draft `envelope_id`.
4. `POST /api/envelopes/{id}/send/` → status `pending`; first signer notified.
5. Store `envelope_id`; optional poll `GET /api/envelopes/{id}/`.

**Signer constraint:** Each `signer_id` in `signing_order` must be an existing e-sign `CustomUser` UUID (find-or-invite is out of MVP).

**UI parity:** The same user logging into e-sign sees the envelope under `GET /api/envelopes/` because `Envelope.creator` is that user.