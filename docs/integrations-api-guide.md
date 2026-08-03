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
    ├─2─ POST /api/documents/upload/          Bearer access
    ├─3─ POST /api/envelopes/create/          Bearer access
    ├─4─ POST /api/envelopes/{id}/send/       Bearer access
    └─5─ GET  /api/envelopes/{id}/            Bearer access (poll)
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

After exchange, use existing APIs with the user JWT. Ownership, audit, notifications, and UI list rules are unchanged.

### 2.5 Audit enrichment

- Successful exchange → audit action `INTEGRATION_TOKEN_EXCHANGE`  
- Envelope create/send via integration JWT → messages may include `[client_id=...]`

### 2.6 IP allowlist (token exchange)

If `allowed_cidrs` is non-empty, requests from IPs outside the list receive **403**. Ensure reverse proxies set client IP correctly (`X-Forwarded-For` trust configuration).

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

Documents in `document_ids` must be **owned by** `request.user`. Each `signer_id` must be an **existing** e-sign user UUID (no email-only signers in MVP).

#### Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `document_ids` | uuid[] | yes | At least one; owned by the JWT user |
| `name` | string | no | Envelope title |
| `description` | string | no | Optional notes |
| `signing_order` | object[] | yes* | `[{ "signer_id": "<uuid>", "order": 1 }, ...]` |
| `documents_with_positions` | object[] | no | Optional per-document signature placements |

\*Empty `signing_order` may be allowed by serializer rules in some flows; for partner send, include at least one signer.

```json
{
  "name": "Offer letter — Ada Lovelace",
  "document_ids": ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"],
  "signing_order": [
    {
      "signer_id": "b7bd2f39-b697-4089-bf6e-e29794ed158d",
      "order": 1
    }
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

Only the **creator** can send. Transitions `draft` / `rejected` → **`pending`**, resets signing workflow, notifies the first signer.

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

## 5. End-to-end implementation checklist

1. **Ops:** Staff creates Integration in admin; store `client_id` / `client_secret` in partner secrets manager.  
2. **Identity:** For each end user action, call token exchange with that user’s email (`full_name` if JIT).  
3. **Upload** PDF/Word with the returned access token.  
4. **Resolve signer UUIDs** in e-sign beforehand (search users API or pre-provisioned accounts).  
5. **Create** envelope with `document_ids` + `signing_order`.  
6. **Send** envelope; store `envelope_id` in the partner system.  
7. **Poll** `GET /api/envelopes/{id}/` as needed (webhooks are out of MVP).  
8. Prefer short-lived use of access tokens; re-exchange when expired (default ~30m for integration access).

---

## 6. Security notes

- Treat `client_secret` like a production password (compromise ≈ mint sessions for asserted emails if JIT is on).  
- Rotate/deactivate via admin when compromised ([runbook](./integrations-secret-rotation-runbook.md)).  
- HTTPS in production.  
- Do not log secrets or full tokens.  
- Signers must already exist as e-sign users (UUIDs) until find-or-invite ships.

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
