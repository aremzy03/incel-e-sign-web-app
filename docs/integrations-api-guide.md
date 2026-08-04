# First-Party Integrations API Guide

How to implement and use e-sign’s **server-to-server (S2S)** integration so a trusted first-party app can create and send envelopes **as a real e-sign user**.

Related docs:

- Architecture plan: [`integrations-s2s-orchestration-plan.md`](./integrations-s2s-orchestration-plan.md)
- Ops / secret rotation: [`integrations-secret-rotation-runbook.md`](./integrations-secret-rotation-runbook.md)
- Machine-readable contract: [`openapi/integrations-v1.yaml`](./openapi/integrations-v1.yaml)
- Bruno smoke collection: `api-testing/bruno/`

---

## 1. Overview

| Concept | Behavior |
|--------|----------|
| Machine auth | `client_id` + `client_secret` on **token exchange only** |
| Business auth | User-scoped JWT (`Authorization: Bearer <access>`) |
| Envelope owner | `Envelope.creator` = the resolved `CustomUser` (UI parity) |
| Join key | User **email** (unique on `CustomUser`) |
| JIT users | Optional per integration (`allow_jit_user_create`, default on) |

Partners never act as a shared “service user.” After exchange, call the same document/envelope APIs the product UI uses.

```text
Partner app (holds client_secret)
    │
    ├─1─ POST /api/v1/integrations/token/
    │      { client_id, client_secret, email, full_name? }
    │    ← access, refresh, user
    │
    │  Three-step (or composite in §4.7):
    ├─2─ POST /api/documents/upload/          Bearer access
    ├─3─ POST /api/envelopes/create/          Bearer access (+ email signers OK)
    ├─4─ POST /api/envelopes/{id}/send/       Bearer access
    └─5─ GET  /api/envelopes/{id}/            Bearer access (poll)
         or wait for webhooks (§4.8)
```

Base URL examples:

- Local: `http://localhost:8000`
- Production: your deployed API host (HTTPS required)

Response envelope (most e-sign JSON APIs):

```json
{
  "status": "success" | "error",
  "message": "Human-readable summary",
  "data": { }
}
```

---

## 2. Features

### 2.1 Admin-registered integrations

Staff create an **Integration** in Django admin. On save, the system generates:

- `client_id` — public identifier  
- `client_secret` — shown **once**; only a hash is stored  

Configurable per integration:

| Field | Purpose |
|-------|---------|
| `is_active` | Soft disable; exchange returns 401 when false |
| `allow_jit_user_create` | Create `CustomUser` when email is unknown |
| `allowed_cidrs` | Optional IP/CIDR allowlist for token exchange (empty = allow all) |
| `notes` | Internal ops notes |

See the [secret rotation runbook](./integrations-secret-rotation-runbook.md) for create / rotate / revoke.

### 2.2 Token exchange

`POST /api/v1/integrations/token/` verifies client credentials, resolves (or JIT-creates) the user by email, optionally upserts `IntegrationUserLink`, and returns SimpleJWT tokens with claims:

- `client_id` — integration that minted the token  
- `auth_via` — `"integration"`  

Access tokens use a shorter lifetime (`INTEGRATION_ACCESS_TOKEN_LIFETIME`, default **30 minutes**). Prefer exchange → act → discard for fire-and-forget flows.

### 2.3 Partner user linking (`external_user_id`)

Optional request field. When set, e-sign upserts `IntegrationUserLink` keyed by `(integration, external_user_id)` so the partner can keep a stable id if email changes later.

### 2.4 Document + envelope pipeline (reused)

After exchange, use existing APIs with the user JWT. Ownership, audit, notifications, and UI list rules are unchanged. Signers may be specified by **UUID** and/or **email** (find-or-invite). Optional composite send and outbound webhooks are described below.

### 2.5 Audit enrichment

- Successful exchange → audit action `INTEGRATION_TOKEN_EXCHANGE`  
- Envelope create/send via integration JWT → messages may include `[client_id=...]`

### 2.6 IP allowlist (token exchange)

If `allowed_cidrs` is non-empty, requests from IPs outside the list receive **403**. Ensure reverse proxies set client IP correctly (`X-Forwarded-For` trust configuration).

### 2.7 Idempotency-Key

Send header `Idempotency-Key: <opaque-string>` on:

- `POST /api/envelopes/create/`
- `POST /api/envelopes/{id}/send/`
- `POST /api/v1/integrations/envelopes/send/`

Same key + same authenticated user + same endpoint scope → original success response is replayed without duplicate side effects. Failures are not stored. Different keys create new work.

---

## 3. Partner configuration

Store secrets in the **partner** environment (not in e-sign `.env`):

```env
ESIGN_BASE_URL=https://api.example.com
ESIGN_CLIENT_ID=int_...
ESIGN_CLIENT_SECRET=...
```

Never commit `ESIGN_CLIENT_SECRET`. Never log raw secrets or full JWTs.

---

## 4. Endpoints

### 4.1 Token exchange

**`POST /api/v1/integrations/token/`**

| | |
|--|--|
| Auth | None (credentials in body) |
| Throttle | `integration_token` scope (defaults to same rate as login/`auth`) |
| Content-Type | `application/json` |

#### Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `client_id` | string | yes | Max 64 chars |
| `client_secret` | string | yes | Raw secret; whitespace preserved |
| `email` | string (email) | yes | Asserted e-sign user; normalized (strip) |
| `full_name` | string | no | Used on JIT create / fill empty name; JIT falls back to email local-part |
| `external_user_id` | string | no | Upserts `IntegrationUserLink` when non-empty |

```http
POST /api/v1/integrations/token/ HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "client_id": "int_A16vncjs4BNfVP638CICsA",
  "client_secret": "<one-time-secret>",
  "email": "ada@example.com",
  "full_name": "Ada Lovelace",
  "external_user_id": "hr-user-123"
}
```

#### Success response — `200 OK`

```json
{
  "status": "success",
  "message": "Token issued successfully",
  "data": {
    "access": "<jwt>",
    "refresh": "<jwt>",
    "user": {
      "id": "657c99e4-5658-42cc-9c3c-5e0d2700104b",
      "email": "ada@example.com",
      "full_name": "Ada Lovelace"
    }
  }
}
```

Use `data.access` as `Authorization: Bearer <access>` on subsequent calls.

#### Error responses

| Condition | Status | Example `message` |
|-----------|--------|-------------------|
| Validation (bad email, missing fields) | `400` | `"Invalid request"` (`data` = field errors) |
| Unknown client / bad secret / inactive | `401` | `"Invalid client credentials"` |
| IP not on allowlist | `403` | `"Client IP is not allowed for this integration"` |
| User inactive | `403` | `"User account is inactive"` |
| User missing and JIT disabled | `404` | `"User not found"` |
| Throttled | `429` | DRF throttle response |
| Unexpected failure | `500` | `"Unable to issue token"` |

Example validation error:

```json
{
  "status": "error",
  "message": "Invalid request",
  "data": {
    "email": ["Enter a valid email address."]
  }
}
```

---

### 4.2 Upload document

**`POST /api/documents/upload/`**

| | |
|--|--|
| Auth | Bearer access JWT |
| Content-Type | `multipart/form-data` |
| Body | Field name **`file`** — PDF or Word (`.pdf`, `.doc`, `.docx`), max 20MB |

```http
POST /api/documents/upload/ HTTP/1.1
Authorization: Bearer <access>
Content-Type: multipart/form-data; boundary=----boundary

------boundary
Content-Disposition: form-data; name="file"; filename="contract.pdf"
Content-Type: application/pdf

<binary>
------boundary--
```

#### Success — `201 Created`

```json
{
  "status": "success",
  "message": "Document uploaded successfully",
  "data": {
    "id": "<document-uuid>",
    "file_name": "contract.pdf"
  }
}
```

(`data` is the full document serializer payload; use `data.id` as `document_id`.)

Document **owner** is the JWT user.

#### Common errors

| Status | Meaning |
|--------|---------|
| `401` | Missing/invalid JWT (`token_not_valid`, etc.) |
| `400` | Invalid/missing file (`Invalid file data`) |

---

### 4.3 Create envelope

**`POST /api/envelopes/create/`**

| | |
|--|--|
| Auth | Bearer access JWT |
| Content-Type | `application/json` |

Documents in `document_ids` must be **owned by** `request.user`. Each `signing_order` entry needs `order` plus **`signer_id` (UUID) and/or `email`**. Unknown emails are find-or-invited: a `CustomUser` is created with an unusable password, an invite email is sent, and a Contact may be upserted for the creator. Stored `signing_order` always uses resolved UUID `signer_id` values.

Optional header: `Idempotency-Key`.

#### Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `document_ids` | uuid[] | yes | At least one; owned by the JWT user |
| `name` | string | no | Envelope title |
| `description` | string | no | Optional notes |
| `signing_order` | object[] | yes* | See shapes below |
| `documents_with_positions` | object[] | no | Optional placements (`signer_id` UUIDs matching resolved order) |

\*Empty `signing_order` may be allowed by serializer rules in some flows; for partner send, include at least one signer.

**`signing_order` entry shapes (backward compatible):**

```json
{ "signer_id": "<uuid>", "order": 1 }
```

```json
{ "email": "signer@example.com", "order": 1, "full_name": "Optional Name" }
```

```json
{ "signer_id": "<uuid>", "email": "signer@example.com", "order": 1 }
```

(When both `signer_id` and `email` are present, they must refer to the same user.)

```json
{
  "name": "Offer letter — Ada Lovelace",
  "document_ids": ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"],
  "signing_order": [
    { "signer_id": "b7bd2f39-b697-4089-bf6e-e29794ed158d", "order": 1 },
    { "email": "new.hire@example.com", "order": 2, "full_name": "New Hire" }
  ]
}
```

#### Success — `201 Created`

```json
{
  "status": "success",
  "message": "Envelope created successfully",
  "data": {
    "id": "<envelope-uuid>",
    "name": "Offer letter — Ada Lovelace",
    "status": "draft"
  }
}
```

(`data` is the envelope detail serializer; status is **`draft`** until send.)

#### Common errors

| Status | Meaning |
|--------|---------|
| `400` | Validation (`Validation failed`, field errors in `data`) |
| `401` | Invalid/missing JWT |
| `403` | Not permitted |

---

### 4.4 Send envelope

**`POST /api/envelopes/{id}/send/`**

| | |
|--|--|
| Auth | Bearer access JWT |
| Body | Empty |
| Header | Optional `Idempotency-Key` |

Only the **creator** can send. Transitions `draft` / `rejected` → **`pending`**, resets signing workflow, notifies the first signer. When the JWT carries `client_id`, an integration origin is recorded and `envelope.sent` webhooks may fire.

#### Success — `200 OK`

```json
{
  "status": "success",
  "message": "...",
  "data": {
    "id": "<envelope-uuid>",
    "status": "pending"
  }
}
```

#### Common errors

| Status | Meaning |
|--------|---------|
| `403` | Not the creator |
| `404` | Envelope not found |
| `409` | Signing workflow already in progress |
| `400` | Invalid state (e.g. self-sign cannot be sent) |

---

### 4.5 Get envelope (status poll)

**`GET /api/envelopes/{id}/`**

| | |
|--|--|
| Auth | Bearer access JWT |

Caller must be creator or a signer (same accessibility rules as the UI).

#### Success — `200 OK`

```json
{
  "status": "success",
  "message": "...",
  "data": {
    "id": "<envelope-uuid>",
    "status": "pending",
    "name": "..."
  }
}
```

Typical statuses after send: `pending`, then progress through signing until completed (product status set).

---

### 4.6 List envelopes (UI parity check)

**`GET /api/envelopes/`**

Authenticated as the same user (integration access token **or** normal UI login). The partner-created envelope appears because `creator` is that user.

---

### 4.7 Composite create-and-send

**`POST /api/v1/integrations/envelopes/send/`**

| | |
|--|--|
| Auth | **User JWT** (`Authorization: Bearer <access>`) — **not** client credentials |
| Content-Type | `multipart/form-data` **or** `application/json` |
| Header | Optional `Idempotency-Key` |

Orchestrates upload (optional) + create + send using the same `EnvelopeCreateSerializer` and shared `send_envelope` service as the three-step flow (identical audit / notifications / ownership).

#### Multipart

| Field | Notes |
|-------|-------|
| `file` | PDF/Word upload (same rules as document upload) |
| `name` / `description` | Optional |
| `signing_order` | JSON string of the signing_order array (email and/or signer_id) |
| `documents_with_positions` / `fields` | Optional JSON strings |

#### JSON (skip upload)

| Field | Notes |
|-------|-------|
| `document_ids` | Required if no `file` — owned by JWT user |
| `signing_order` | Array (email and/or signer_id) |
| `name` / `description` / … | Same as create |

#### Success — `201 Created`

```json
{
  "status": "success",
  "message": "Envelope created and sent successfully",
  "data": {
    "envelope_id": "<uuid>",
    "document_ids": ["<uuid>"],
    "status": "pending",
    "envelope": { },
    "uploaded_document": null
  }
}
```

(`uploaded_document` is set when a multipart `file` was provided.)

#### Common errors

| Status | Meaning |
|--------|---------|
| `400` | Missing file/`document_ids`, validation failed |
| `401` | Missing/invalid JWT |
| `409` | Signing workflow in progress |

---

### 4.8 Outbound webhooks

Staff register **Integration webhook endpoints** in Django admin (per Integration): URL, enabled events, signing secret (shown once; encrypted at rest).

| Event | When |
|-------|------|
| `envelope.sent` | After successful send for an envelope originated via an integration JWT (`client_id`) |
| `envelope.completed` | When that envelope reaches `completed` |

**Delivery:** Celery POST JSON to the partner URL with retries/backoff.

**Headers:**

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `X-ESign-Event` | e.g. `envelope.sent` |
| `X-ESign-Delivery-Id` | Delivery UUID |
| `X-ESign-Signature` | `t=<unix>,v1=<hmac-sha256-hex>` over `{t}.{body}` |

Partners verify with the webhook signing secret from admin. Use **HTTPS** URLs in production. Never log signing secrets. Ops: rotate via admin action (secret shown once) — see [runbook](./integrations-secret-rotation-runbook.md).

Example payload shape:

```json
{
  "event": "envelope.sent",
  "occurred_at": "2026-08-04T12:00:00+00:00",
  "data": {
    "envelope_id": "...",
    "status": "pending",
    "name": "...",
    "creator_id": "...",
    "document_ids": [],
    "signing_order": []
  }
}
```

---

## 5. End-to-end implementation checklist

1. **Ops:** Staff creates Integration in admin; store `client_id` / `client_secret` in partner secrets manager. Optionally register webhook URL + store signing secret.  
2. **Identity:** For each end user action, call token exchange with that user’s email (`full_name` if JIT).  
3. **Upload** PDF/Word with the returned access token, **or** use composite §4.7.  
4. **Create** envelope with `document_ids` + `signing_order` (UUID and/or email). Prefer `Idempotency-Key`.  
5. **Send** envelope (or rely on composite); store `envelope_id` in the partner system.  
6. **Poll** `GET /api/envelopes/{id}/` and/or consume webhooks (`envelope.sent` / `envelope.completed`).  
7. Prefer short-lived use of access tokens; re-exchange when expired (default ~30m for integration access).

---

## 6. Security notes

- Treat `client_secret` and webhook `signing_secret` like production passwords.  
- Rotate/deactivate via admin when compromised ([runbook](./integrations-secret-rotation-runbook.md)).  
- HTTPS in production (API and webhook URLs).  
- Do not log secrets or full tokens.  
- Signer emails may invent invited users with unusable passwords — treat like JIT trust assumptions.

---

## 7. Testing

- Automated: `pytest integrations/tests/`  
- Manual / smoke: Bruno collection under `api-testing/bruno/` (Partner Flow folder).  

```bash
cd api-testing/bruno
set -a && source .env && set +a
bru run "Partner Flow" --env Local --sandbox=developer
```

---

## 8. OpenAPI

The companion OpenAPI 3.1 document describes these paths and schemas:

[`docs/openapi/integrations-v1.yaml`](./openapi/integrations-v1.yaml)

Import it into Swagger UI, Postman, or Bruno for contract-driven clients. Keep this guide and the YAML in sync when endpoints change.

Public developer portal / self-serve registration is **not** available — staff admin only.
