# Signing Pipeline Audit: Speed, Reliability, and Target Design

## 1. Purpose

Document how document signing currently works, where it diverges from industry e-sign platforms (DocuSign, Adobe Sign, SignNow), and the concrete changes needed so later work can be audited and implemented without re-deriving the analysis.

This is an architecture note, not an implemented change. No code in this document should be treated as already shipped.

**Scope:** the async signing job path (accept sign → embed PDFs → finalize envelope), not the signing UI, auth, or envelope create/send.

**Date:** 2026-09-21

---

## 2. Goals & Non-Goals

### Goals

- Make signing **intent** durable independently of PDF rendering.
- Make PDF output a **repeatable function** of (immutable source + field values), so worker redelivery and job retry cannot double-stamp ink.
- Take PDF composition **off the “I finished signing” critical path** as far as product UX allows.
- Stamp each document in **one pass**, not once per field.
- Fail, retry, and reclaim jobs without leaving mixed stamped/unstamped documents.

### Non-Goals (this audit)

- Certificate-based PDF digital signatures (PAdES / PKCS#7 / ByteRange). That is a separate product track.
- Replacing Celery with Temporal / Step Functions. Not required for the first reliability cutover.
- Changing sequential signing order or the `202` + poll client contract.

---

## 3. Current Architecture

```
POST /api/signatures/{envelope_id}/sign/
  validate turn, freeze, already-signed
  Signature → processing   (row lock)
  SigningJob → queued
  transaction.on_commit → Celery process_signing_job

process_signing_job
  resolve signature image (data URL or UserSignature)
  chord: embed_document_for_signer × N documents
    download PDF (S3 or local)
    embed_signature / embed_text  (full rewrite per field)
    upload signing/{envelope}/{doc}/vN.pdf
    pointer-swap Document.signed_file_url
  finalize_signer_chord
    mark Signature signed
    if last signer: complete_envelope (password lock + completed/)
    else: notify next signer
```

Primary code:

| Piece | Location |
| --- | --- |
| HTTP accept + poll + retry | `signatures/views.py` |
| Job create / in-flight guard | `signatures/services/job_service.py` |
| Celery orchestration | `signatures/tasks.py` |
| Per-document S3 download/stamp/upload | `signatures/services/signing_worker.py` |
| Field/signature overlay loop | `signatures/services/signing.py` (`embed_document_pdf_for_signer`) |
| PDF overlay merge | `signatures/utils/pdf_signing.py` |
| Versioned object keys | `documents/services/pdf_files.py` |
| Worker / S3 timeouts | `esign/settings.py` (`CELERY_*`, `AWS_S3_*`) |

What is already at industry shape:

- Non-blocking `202 Accepted` and `GET /api/signatures/jobs/{id}/`.
- `transaction.on_commit` enqueue so workers cannot beat the `SigningJob` insert.
- `select_for_update` + `get_active_signing_job` to collapse double-clicks.
- Dedicated `signing` queue, `acks_late`, `reject_on_worker_lost`, `prefetch=1`.
- Immutable version keys `signing/{envelope_id}/{document_id}/vN.pdf`.
- Transient vs permanent error split (narrow; see Gap 5).
- Audit events, Sentry spans, duration logs, manual retry endpoint.

---

## 4. Core Design Mismatch

Industry platforms treat the scribble as **data** and the PDF as a **render**:

1. Sign commits field values, consent, and an audit row (milliseconds, transactional).
2. Preview is page images + overlays, not a newly baked PDF.
3. Authoritative PDF is composed **once** at completion (or on-demand download) from `original PDF + all field values`.
4. Retry always produces the same bytes.

This system treats the PDF as the **source of truth after every signer**:

1. Sign still returns `202` quickly, but “succeeded” waits on download + N rewrites + upload.
2. Each signer **folds** a new stamp onto the previous PDF (`vN` → `vN+1`).
3. Worker redelivery and job retry re-run that fold, which can apply ink twice.

Until compose is idempotent, `acks_late` and “Retry” amplify duplicate signatures instead of making the pipeline safe.

**Locked product decision for the target design:** keep sequential signing and the job/poll API; change the worker so PDF bytes are derived from an immutable source plus DB field values, not from the last stamped file.

---

## 5. Gap Register

Severity:

- **P0** — can corrupt a signed document or leave an envelope unrecoverable.
- **P1** — wrong latency profile or stuck jobs under normal failure.
- **P2** — cost, operability, or future-scale.

### GAP-01 — Stamping is not idempotent (P0)

**Problem.** Embed is “download current URL, overlay image, upload next version.” Celery is at-least-once (`acks_late`). If the worker uploads `v2`, updates `Document.signed_file_url`, then dies before ACK, redelivery downloads `v2` and stamps again → `v3` with duplicate ink.

The same happens on **manual retry** after a partial chord: document A succeeded, B failed; retry stamps A a second time.

`next_signing_version()` only names the next object. It does not mean “apply this signer’s ink only if absent.”

**Evidence.** `signatures/services/signing_worker.py` (download current URL → embed → `upload_signing_version`); `documents/services/pdf_files.py` `next_signing_version`; `esign/settings.py` `CELERY_TASK_ACKS_LATE = True`.

**Solution.**

- Snapshot the input object on the job at enqueue: `source_key` / `source_url` (immutable).
- Always compose from that snapshot (or from the envelope original + all values), never from a URL that this job already mutated.
- Upload to a **job-scoped** key, e.g. `signing/{envelope_id}/{document_id}/job-{job_id}.pdf`.
- Pointer-swap `Document.signed_file_url` only after a successful compose.
- Treat “output object already exists for this `job_id` + `document_id`” as success (skip re-stamp).

Acceptance: kill the worker after S3 upload; redelivery produces identical bytes and a single visible signature.

---

### GAP-02 — Partial multi-document success has no compensation (P0)

**Problem.** `finalize_signer_chord` fails the job if any embed returns `{ok: False}`, but successful sibling tasks have already pointer-swapped their documents. The envelope is a mix of stamped and unstamped files. Retry (GAP-01) then double-stamps the successful ones.

**Evidence.** `signatures/tasks.py` `finalize_signer_chord` (`all(r.get("ok") …)` then `_mark_job_failed`); no rollback in `signing_worker.py`.

**Solution.** Pick one:

- **Preferred:** compose from original + all values, write job-scoped outputs, pointer-swap **all documents in finalize** (or none). Embed tasks only produce bytes; they do not publish.
- **Minimum if publish stays in embed tasks:** store `input_url` per document on the job; retry always reads those inputs; never read `document.signed_file_url` as the stamp source for a retry of the same signer.

Acceptance: fail document 2 of 3; retry; all three PDFs show this signer’s ink exactly once.

---

### GAP-03 — Legal state and artifact publish are not atomic (P0)

**Problem.** `finalize_signer_chord` calls `mark_signature_signed` before `complete_envelope`. If lock/S3 complete fails:

- `Signature.status` is already `signed`.
- Job is `failed`.
- Retry runs `process_signing_job`, which **re-embeds first**, then skips `mark_signature_signed` because status is not `processing`, then calls `complete_envelope` again.

Result: double-stamp on the way to a second complete.

**Evidence.** `signatures/tasks.py` `finalize_signer_chord`; `signatures/services/signing.py` `mark_signature_signed`, `complete_envelope`.

**Solution.** Split into two terminal steps:

1. **Commit intent:** `Signature` → `signed`, audit row. Idempotent. Does not depend on PDF.
2. **Publish artifact:** compose (if not already) and write `completed/`. Retryable without re-applying intent.

Recommended job (or signature) states: `queued → processing → signed_pending_publish → succeeded` with `failed` from any of the last three. Re-embed is forbidden once intent is committed unless compose is a pure function of original + values (then re-embed is a no-op in effect).

Acceptance: inject failure in `complete_envelope`; retry; envelope completes; PDF has one stamp per signer.

---

### GAP-04 — Jobs can stick in `processing` forever (P1)

**Problem.** Chord + Redis result backend can drop the callback (`chord_unlock`, result expiry, worker death after the header ran). Then:

- `Signature` stays `processing`.
- `get_active_signing_job` keeps returning `202`.
- `POST .../jobs/{id}/retry/` only accepts `status == failed`.

There is no TTL, reclaim, or sweeper.

**Evidence.** `signatures/tasks.py` chord in `process_signing_job`; `signatures/views.py` `SigningJobRetryView`; `signatures/services/job_service.py` `get_active_signing_job`.

**Solution.**

- Periodic task: `queued`/`processing` older than `SIGNING_JOB_STALE_AFTER` (suggest 15–20 minutes, under the 25-minute soft time limit) → `failed` with a clear error, Signature back to `pending` if intent was not committed.
- Allow retry from that failed state.
- Optional: Celery chord error callback / `link_error` writing the same failed state so stale is a backstop, not the primary path.

Acceptance: drop Redis results mid-chord; within the stale window the job is `failed` and retry works.

---

### GAP-05 — Retry policy misses the failures we will actually see (P1)

**Problem.** `_is_retryable_signing_error` retries only `EndpointConnectionError`, `ConnectionError`, `TimeoutError`. `botocore.ClientError` (S3 503 / SlowDown), incomplete reads, and Redis blips are treated as permanent. After max retries, embed tasks **return** `{ok: False}` instead of failing the chord — the callback runs, the job fails, the user must retry.

Boto3 client retries (`AWS_S3_MAX_ATTEMPTS`, default 3) help short blips; they do not cover multi-second S3 brownouts.

Unknown `RuntimeError` / pypdf errors also never retry at the Celery layer (conservative for double-stamp, painful until GAP-01 is fixed).

**Evidence.** `signatures/tasks.py` `_is_retryable_signing_error`; `documents/services/s3_client.py`; tests in `signatures/tests/test_signing_task_retry.py`.

**Solution.** After GAP-01 (idempotent compose):

- Retry S3 `ClientError` when HTTP status is 408/429/5xx, plus `IncompleteRead`, `ReadTimeoutError`.
- Keep `ValueError`, `SignatureImageError`, `FileNotFoundError`, `DocumentNotAvailableForSigningError` as permanent.
- Cap retries (already `max_retries=3` with exponential countdown). Send exhausted jobs to `failed` (existing) and consider a metrics/alert on `SIGNING_JOB_FAILED`.

Acceptance: simulated S3 503 on first two attempts succeeds on the third without duplicate ink.

---

### GAP-06 — Flatten runs on the signer’s “done” path (P1)

**Problem.** Industry: Finish → commit rows → UI can show signed; PDF compose is background. Here, job `succeeded` waits on S3 + CPU. Last signer also pays a second hop: upload `vN`, then `complete_envelope` downloads it and writes `completed/`.

**Evidence.** `signatures/tasks.py` finalize waits on embed results; `signatures/services/signing.py` `complete_envelope`.

**Solution.**

- Commit `Signature` signed as soon as validation + job persist succeed, **or** as soon as field values are stored and compose is queued (product choice; prefer after compose is idempotent so a failed compose can retry without user action).
- Minimum UX: keep `202` but drive the client off `Signature.status` / job status without blocking on `completed/` upload. Publish `completed/` asynchronously after `signed`.
- Do not re-download for complete if the worker still has local bytes; upload `completed/` from the same temp file (or copy object server-side `CopyObject`).

Acceptance: p50 time from `POST /sign` to `Signature.status=signed` is a DB transaction, not S3. Artifact URL may lag; poll already exists.

---

### GAP-07 — Stamp is O(fields) full PDF rewrites (P1)

**Problem.** `embed_document_pdf_for_signer` calls `embed_signature` / `embed_text` once per position/field. Each call parses the whole PDF, builds a full-page overlay, `merge_page`, writes a new file. Ten fields ⇒ ten parse/serialize cycles. pypdf + ReportLab is also slower than native PDF libraries on large scans.

**Evidence.** `signatures/services/signing.py` loops; `signatures/utils/pdf_signing.py` `embed_signature`, `embed_text`.

**Solution.**

- Open each document once. Collect all images and strings for that signer (and, in the target design, all prior signers’ values). Draw them onto one overlay (or inject XObjects once). Write once.
- Keep `embed_signature` / `embed_text` as test helpers if useful, but production path should be `embed_fields(pdf, fields: list[Stamp])`.
- Later optimization (P2): switch the engine to PyMuPDF / pikepdf / a native lib if pypdf corrupts real-world PDFs (GAP-08).

Acceptance: a document with 20 fields produces one `PdfWriter.write` (or equivalent). Benchmark a 20-page / 10 MB file before and after.

---

### GAP-08 — Incoming PDFs are not sanitized (P1)

**Problem.** Vendors flatten/rasterize on upload so JavaScript, AcroForms, `/Rotate`, and broken xref tables never hit the stamp path. This system stamps the original. `merge_page` on arbitrary customer PDFs is a known blank-page / corruption class.

**Evidence.** No ingest flatten in `documents/` upload path; stamp uses original bytes in `pdf_signing.py`.

**Solution.**

- On upload (or first send), produce a **normalized original**: strip JS/actions, flatten existing AcroForm values into page content, normalize rotation to 0, write a clean PDF. Store that as the immutable source (`staging/` or `originals/{document_id}.pdf`).
- Stamp and preview only that object.
- Reject or quarantine PDFs that fail normalize.

Acceptance: a form-heavy PDF with filled AcroForm values shows those values as static ink and still receives signature images in the correct place.

---

### GAP-09 — Signature image stored as a huge text column (P2)

**Problem.** Drawn/uploaded signatures travel as base64 data URLs on `SigningJob.signature_image_data` and `Signature.signature_image`. Large rows, backup bloat, easy to leak in logs.

**Evidence.** `signatures/models.py`; `signatures/views.py` copies request body onto the job; `mark_signature_signed` persists the data URL again.

**Solution.**

- Write the PNG/JPEG to object storage (`signatures/{user_id}/{signature_id}.png` or `jobs/{job_id}/appearance.png`).
- Store only a URL/key on `SigningJob` / `Signature`.
- Keep `user_signature_id` deferral (already good).
- Cap upload size in the serializer (e.g. 200 KB decoded, matching common vendor limits).

Acceptance: job row size stays small; worker loads bytes from storage; logs never contain the data URL.

---

### GAP-10 — No page-image cache (P2)

**Problem.** Vendors rasterize at upload; signing UI and some compose paths use those images. This system re-parses PDF vectors on every sign and (on the client) likely re-renders from the PDF.

**Solution (later).** At normalize time (GAP-08), emit per-page PNGs (or PDF page objects) under `pages/{document_id}/{page}.png`. Preview uses those. Compose can still stamp vectors if quality requires it.

Not blocking for idempotent compose.

---

### GAP-11 — Chord orchestration overhead for small envelopes (P2)

**Problem.** A chord of N document tasks plus Redis results is extra latency when N is 1–3 and PDFs are small. Parallelism wins for many/large documents.

**Solution.** If `len(documents) == 1` (or below a threshold), run embed + finalize inline in `process_signing_job` (already the eager-mode pattern). Keep the chord for larger envelopes. Optional later: one task stamps all docs in-process with a thread/process pool.

---

## 6. Target Architecture

```
POST /sign
  validate turn
  persist field values + appearance blob key
  Signature → processing (or signed if compose is fully async)
  SigningJob { source_keys[], appearance_key, signer_id }
  202 + job_id

compose_signing_job  (idempotent)
  for each document:
    if output exists for job_id+document_id: skip
    pdf = load(immutable original)
    stamps = all signers’ values up to this signer (sequential)
    one-pass embed
    put job-scoped object
  pointer-swap all document URLs in one DB transaction
  Signature → signed
  enqueue publish_completed if last signer

publish_completed  (idempotent)
  CopyObject or upload completed/{envelope}/{doc}.pdf
  optional password lock
  envelope status → completed | self_signed
```

Invariants to enforce in code review:

1. **Intent is a DB row.** A signed `Signature` is never rolled back because S3 failed.
2. **Compose is a pure function.** `compose(original, values, appearance) → bytes`. Same inputs ⇒ same output.
3. **Publish is a pointer swap.** Never stamp “on top of” `signed_file_url`.
4. **At-least-once is OK** because (2) and job-scoped output keys make it at-most-once in effect.

---

## 7. Implementation Phases

Implement in this order. Do not start Phase 2 until Phase 1 acceptance tests pass; `acks_late` without idempotency is how duplicate ink is created.

### Phase 1 — Correctness (P0): GAP-01, GAP-02, GAP-03, GAP-07

1. Add `SigningJob.source_urls` (JSON: `{document_id: url}`) captured at enqueue from current `file_url` / `signed_file_url`.
2. Add job-scoped output keys; skip compose if the object already exists.
3. One-pass `embed_fields` per document.
4. Pointer-swap documents in finalize only (or swap using job-scoped keys that retries reuse).
5. Do not re-embed after `Signature` is `signed`; split publish/complete into a retryable step.

**Exit:** worker kill, partial chord failure, and `complete_envelope` failure all retry to a single stamp per signer.

### Phase 2 — Operability (P1): GAP-04, GAP-05, GAP-06

1. Stale-job sweeper + retry allowed from failed.
2. Broader S3 retry classification.
3. Avoid extra download on complete (`CopyObject` or reuse local bytes).
4. Optionally mark `signed` before `completed/` is visible; keep polling.

**Exit:** no job remains `processing` past the stale window; p95 compose retries recover from S3 503.

### Phase 3 — Artifact quality (P1/P2): GAP-08, GAP-09

1. Normalize PDF on upload/send; stamp only the normalized original.
2. Appearance images in object storage, not base64 columns.
3. Serializer size cap on `signature_image`.

**Exit:** form PDFs flatten cleanly; job table no longer stores data URLs.

### Phase 4 — Scale (P2): GAP-10, GAP-11

1. Page-image cache for preview.
2. Inline compose for single-document envelopes.
3. Revisit PDF engine if normalize+pypdf still corrupts files.

---

## 8. Suggested Schema / Config (Phase 1–2)

Not applied yet. For implementers:

**`SigningJob` (additive):**

- `source_urls` — `JSONField`, map of document id → object URL used as compose input.
- `appearance_storage_key` — `CharField`, optional replacement for `signature_image_data`.
- `stale_at` or rely on `updated_at` + settings threshold.

Keep `signature_image_data` until Phase 3 so rollback is easy.

**Settings:**

- `SIGNING_JOB_STALE_AFTER_SECONDS` (default `900`)
- `SIGNING_SIGNATURE_IMAGE_MAX_BYTES` (default `204800`)
- Existing `CELERY_TASK_*` and `AWS_S3_*` stay.

**Storage keys:**

- Immutable original: `staging/{document_id}.pdf` or `originals/{document_id}.pdf` after GAP-08
- Job output: `signing/{envelope_id}/{document_id}/job-{job_id}.pdf`
- Completed: `completed/{envelope_id}/{document_id}.pdf` (unchanged)

---

## 9. Test Plan

Add failing tests first (project rule: reproduce before fix). Suggested cases:

| Test | Guards |
| --- | --- |
| `test_embed_redelivery_does_not_double_stamp` | Kill after upload; second run; PDF has one image XObject / file size not 2× |
| `test_partial_chord_retry_stamps_each_doc_once` | Doc 2 fails; retry; three docs, one stamp each |
| `test_complete_envelope_failure_does_not_re_embed` | Signature already signed; complete retried; bytes unchanged |
| `test_stale_processing_job_marked_failed` | Freeze time; sweeper; retry allowed |
| `test_s3_503_retries_then_succeeds` | `ClientError` then success |
| `test_one_pass_embed_writes_once` | Mock writer; 10 fields → one write |
| `test_sign_rejects_oversized_signature_image` | Phase 3 serializer cap |

Existing coverage to keep: `test_signing_job_lifecycle.py`, `test_signing_task_retry.py`, `test_s3_finalize_on_completion.py`, `test_pdf_signing.py`.

---

## 10. Audit Checklist (for reviewers)

When a phase PR lands, check:

- [ ] Compose never reads a URL this job already wrote, unless that object is the job-scoped idempotent output.
- [ ] `acks_late` redelivery is covered by a test that asserts identical PDF bytes.
- [ ] `Signature.status=signed` does not require `completed/` to exist.
- [ ] Failed compose does not leave a sibling document published unless retry is proven safe (GAP-02).
- [ ] No new base64 signature blobs in Postgres (Phase 3+).
- [ ] Stale sweeper cannot fail a job that is still running inside the soft time limit without a heartbeat (if you add heartbeats, document them).
- [ ] Sequential signing still enforced; signer 2’s compose includes signer 1’s values.
- [ ] Metrics: job duration, embed duration per document, fail/retry counts (Sentry tags already include `job_id` / `envelope_id`).

---

## 11. Out of Scope Follow-ups

- Platform certificate seal (DocuSign-style DigiCert PAdES on download).
- True `/Sig` widgets + ByteRange (conflicts with flatten-after-sign; do not flatten those widgets).
- Replacing Redis+Celery chords with a workflow engine.
- Full-page rasterization as the default ingest path (only as a fallback for PDFs that fail vector normalize).
