# Incel E-Sign API — Bruno collection

Manual / smoke API tests for first-party S2S integrations and core auth.

## Setup

1. Open `api-testing/bruno` in Bruno (**File → Open Collection**).
2. Select the **Local** environment.
3. Copy `.env.example` → `.env` and fill:
   - `LOGIN_EMAIL` / `LOGIN_PASSWORD` — for `Auth/Login`
   - `ESIGN_CLIENT_ID` / `ESIGN_CLIENT_SECRET` — from Django admin (Integrations; secret shown once)
   - `PARTNER_USER_EMAIL` / `PARTNER_USER_FULL_NAME` — user asserted on token exchange
   - `SIGNER_USER_ID` — existing e-sign user UUID (required for create; not email-only yet)
   - Optional: `PARTNER_EXTERNAL_USER_ID` for `IntegrationUserLink` upsert
4. Ensure the Django server is running (`baseUrl` defaults to `http://localhost:8000`).
5. Apply migrations if needed (`integrations` Phase 3: `0002_phase3_hardening`).

## Folders

| Folder | Purpose |
|--------|---------|
| `Auth/` | Password login → stores `accessToken` / `refreshToken` |
| `Integrations/` | Token exchange happy path + negative cases |
| `Partner Flow/` | Sequenced smoke: exchange → upload → create → send → get |
| `fixtures/` | Tiny sample PDF for document upload |

## Run

**Bruno app:** run folders in order (`Partner Flow` uses `seq` 1–5).

**CLI** (from this directory, with `.env` loaded or vars exported):

```bash
cd api-testing/bruno
# Quote values with spaces in .env (e.g. PARTNER_USER_FULL_NAME="Fourth User")
set -a && source .env && set +a
# --sandbox=developer required for @file() uploads (CLI Safe Mode blocks FS)
bru run --env Local --sandbox=developer
# Partner Flow only:
bru run "Partner Flow" --env Local --sandbox=developer
# smoke only:
bru run --env Local --sandbox=developer --tags smoke
# integrations negatives + happy path:
bru run Integrations --env Local
```

Runtime chaining uses `bru.setVar` for `accessToken` / `documentId` / `envelopeId` so the next request in the same CLI run gets a valid JWT (empty env placeholders were causing `token_not_valid` on upload).

Upload uses a Developer Mode pre-request FormData workaround: Bruno CLI 4.0 sets body mode to `multipart-form`, but the runner only builds multipart when mode is `multipartForm`, which otherwise yields Django `No file was submitted.`

Secrets stay in gitignored `.env` — never commit real `client_secret` or passwords.

## Notes

- Login and token exchange both nest JWTs under `data.access` / `data.refresh` (not top-level SimpleJWT shape).
- Signers must already be e-sign users (UUIDs). See `docs/integrations-s2s-orchestration-plan.md` Appendix A.
- Ops: `docs/integrations-secret-rotation-runbook.md`.
