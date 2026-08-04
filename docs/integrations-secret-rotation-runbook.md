# First-party integration secret rotation runbook

Ops guide for create, rotate, revoke/deactivate, and partner environment updates.
Never paste live secrets into tickets, chat, or logs.

## Threat context

Compromise of `client_secret` ≈ ability to mint user-scoped JWTs for asserted
emails (JIT create may invent users). Treat secrets like production passwords.

## Create an integration

1. Sign in as Django staff and open **Integrations → Add**.
2. Set **name**, **allow_jit_user_create**, optional **allowed_cidrs**
   (JSON list of IPs/CIDRs, e.g. `["203.0.113.0/24"]`; empty = allow all).
3. Save. Copy **client_id** and **client_secret** from the one-time admin
   message — the raw secret is never stored again.
4. Deliver credentials to the partner out-of-band (secrets manager / sealed
   channel). Partner stores them in **their** env, not in e-sign `.env`.

## Rotate a secret

1. In admin, select exactly one Integration → action **Rotate client secret**.
2. Copy the new secret from the admin message (shown once).
3. Update the partner env with the new `client_secret` (same `client_id`).
4. Confirm partner token exchange succeeds, then discard the old secret.
5. Old hash is invalidated immediately on rotate — coordinate a short
   cutover window with the partner.

## Revoke / deactivate a compromised client

1. Prefer **Deactivate** (`is_active=False`) via admin action or edit form.
   Token exchange returns **401** for inactive clients.
2. Optionally rotate the secret after deactivate so a reactivation cannot
   reuse the leaked secret.
3. Ask the partner to remove credentials from their env and rotate any
   downstream secrets that may have been exposed with the same incident.
4. Review audit logs for `INTEGRATION_TOKEN_EXCHANGE` and envelope
   `CREATE_ENVELOPE` / `SEND_ENVELOPE` messages containing `client_id=...`
   around the compromise window.

## Partner environment checklist

| Variable / value | Notes |
|------------------|-------|
| `client_id` | Public; safe to put in non-secret config |
| `client_secret` | Secret store only; never commit |
| Token URL | `POST /api/v1/integrations/token/` over HTTPS |
| Access lifetime | Integration access JWTs use `INTEGRATION_ACCESS_TOKEN_LIFETIME` (default 30m) |
| Webhook signing secret | Shown once when creating/rotating an **Integration webhook endpoint** in admin; partner verifies `X-ESign-Signature`. Encrypted at rest in e-sign; never log |

## Webhook signing secrets

1. Django admin → **Integration webhook endpoints** → Add (pick Integration, HTTPS URL, optional `enabled_events`).
2. Copy **signing_secret** from the one-time admin message; deliver out-of-band to the partner.
3. To rotate: select exactly one endpoint → action **Rotate webhook signing secret**; update partner verification secret immediately.
4. Deactivate an endpoint to stop deliveries without deleting history.
5. Events: `envelope.sent`, `envelope.completed` (only for envelopes originated via that integration’s JWT).

## IP allowlist notes

- Non-empty `allowed_cidrs` → token exchange from other IPs returns **403**.
- Empty list → allow all (default).
- Prefer CIDRs of partner egress / NAT ranges, not individual developer laptops, unless intentionally locking staging.
