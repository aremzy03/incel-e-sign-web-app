# PDF Editor Design: Document Prep vs E-Sign Tagging

## 1. Purpose

Define how this product should add **real PDF editing** (page operations and additive content) without turning the envelope wizard’s Place Fields step into a Sejda clone.

This is an architecture note for later audit and implementation. No code in this document should be treated as already shipped.

**Related:** `docs/signing-pipeline-audit.md` (how signatures are flattened into PDFs). Editor commit must not go through that per-field overlay loop.

**Date:** 2026-09-21

**Repos:**


| Layer | Path                                |
| ----- | ----------------------------------- |
| API   | `incel-e-sign-web-app` (this repo)  |
| UI    | `../incel-e-sign-web-app-front-end` |


---



## 2. Goals & Non-Goals



### Goals

- Give senders iLovePDF/Sejda-style **document preparation** on `draft` PDFs: organize pages, then optionally stamp sender-owned markup.
- Keep envelope **Place Fields** as DocuSign/SignNow tagging (`FieldPositions` JSON), not as a PDF writer.
- Commit edits as a **new immutable PDF version**, then place signature fields on that frozen file.
- Share one coordinate space with Place Fields and signing after commit (normalize rotation/crop on apply).
- Reuse existing frontend building blocks: `react-pdf` / PDF.js, `PdfPageThumbnail`, `@dnd-kit`, merge API.



### Non-Goals (this design)

- True in-place glyph editing (rewrite original `Tj`/`TJ` operators, reflow, subsetted CID fonts). That is Acrobat / Apryse / Nutrient.
- Editing documents attached to a **pending** envelope (same rule as merge).
- Certificate-based PDF signatures (PAdES).
- Replacing PDF.js with a commercial WebViewer in v1.

---



## 3. Product Decision (Locked)

This app is an **e-sign product**. The market split is:


| Product                         | Job                    | Source of truth while working |
| ------------------------------- | ---------------------- | ----------------------------- |
| iLovePDF / Sejda                | Fix a PDF, download it | Task + new file               |
| DocuSign / SignNow / Adobe Sign | Collect signatures     | Envelope + field JSON         |
| Adobe Acrobat                   | Real PDF content edit  | Native PDF engine             |


**Locked choice:** ship **DocuSign prepare + a small iLovePDF toolbox**. Do not ship a full Sejda editor inside Place Fields.

Adobe’s split is the model: Acrobat mutates files; Sign places tabs. Sender markup (whiteout, letterhead text) is baked **before** the envelope is live. Signer tabs stay as fields until sign-time flatten.

---



## 4. What Exists Today



### 4.1 Backend


| Capability                                                   | Status      | Location                                                                                     |
| ------------------------------------------------------------ | ----------- | -------------------------------------------------------------------------------------------- |
| Upload PDF / Word                                            | Shipped     | `POST /api/documents/upload/` (Word → PDF via LibreOffice)                                   |
| Preview / download / delete                                  | Shipped     | `documents/urls.py`                                                                          |
| Merge PDFs                                                   | Shipped     | `POST /api/documents/merge/` — `draft` or `completed` only; blocked if on a pending envelope |
| Envelope fields                                              | Shipped     | `fields.Field` — signature/initials/date/text/designation                                    |
| Sign flatten                                                 | Shipped     | `signatures/utils/pdf_signing.py` overlay merge (see signing audit)                          |
| Rotate / split / delete pages / crop / whiteout / add images | **Missing** | —                                                                                            |


Merge is the only structural write. It concatenates pages with pypdf in the HTTP request (not a Celery job).

### 4.2 Frontend (`incel-e-sign-web-app-front-end`)

Wizard: **Documents → Recipients → Place Fields → Settings → Review & Send**.


| Piece                                        | Role                                                                 |
| -------------------------------------------- | -------------------------------------------------------------------- |
| `react-pdf` 10 + `pdfjs-dist` 5.3.93         | Render only (`src/lib/pdf-worker.ts`)                                |
| `VerticalPDFViewer`                          | Multi-page canvas for tagging                                        |
| `FieldPalettePanel` + `@dnd-kit`             | Drop signer fields onto pages                                        |
| `PdfPageThumbnail` + `PlaceFieldsRightPanel` | **Navigate** pages, not reorder them                                 |
| `FIELD_TYPES`                                | `signature`, `initials`, `date`, `text`, `designation`               |
| Documents table                              | Select ≥2 → Merge Selected                                           |
| Wizard Documents step                        | “Merge into single PDF” switch                                       |
| `src/lib/utils/field-geometry.ts`            | PDF points ↔ viewport px (already has scale / legacy-shrink repairs) |


There is **no** `pdf-lib`, Apryse, or Nutrient. The browser never writes PDF bytes. Merge is `mergeDocuments()` → `POST /documents/merge/`.

Wizard merge already clears tags: `setFieldPositions({})` after success. Any page editor must do the same or remap field `page` indexes.

---



## 5. Industry Architecture (What to Copy)

Standard web PDF products use **three layers**. PDF.js is never the writer.

```
1. RENDER     PDF.js / react-pdf  →  page canvases + optional text layer
2. SESSION    operation JSON      →  undo/redo, no PDF rewrite per keystroke
3. COMMIT     pypdf / pikepdf     →  one new PDF from original + ops
```

Sejda: Java SAMBox **tasks** (merge, split, rotate, crop) plus a separate “Apply changes” for the WYSIWYG editor. Web = upload → server → download.

iLovePDF: one URL per **task**, progress screen, server worker, disposable files.

DocuSign / SignNow: Place Fields is tagging. Optional page delete/rotate in **prepare**. Sender text/image is flattened at send, not live content-stream edit.

**“Click existing text to edit”** in Sejda/Smallpdf is almost always: use the PDF.js text layer for hit-testing, **whiteout** the box, **draw new text**. They do not reconstruct Word-like runs from subsetted fonts. For contracts, paint-only whiteout is insufficient (old text remains selectable); commit must **redact** (remove underlying operators) or use a commercial SDK.

---



## 6. Where It Lives in This UI

Do **not** add rotate / whiteout / rewrite-text tools to Place Fields. That step is Correct/tagging.

```
Library / Wizard step 1 (Documents)
  Upload → [optional] PDF Editor → frozen Document version
Wizard step 3 (Place Fields)
  Overlay tags only (existing FieldPositions)
Send → sign flatten (existing pipeline)
```


| Surface                | Current route                | Add                                            |
| ---------------------- | ---------------------------- | ---------------------------------------------- |
| **Tools (iLovePDF)**   | `/dashboard/documents`       | Organize + Edit on `draft`                     |
| **Prepare (DocuSign)** | Envelope wizard Place Fields | Unchanged tagging                              |
| **Entry from wizard**  | Step 1 Documents             | “Prepare PDF” opens the editor, then continues |


Same pending-envelope guard as merge. Edit after fields exist → remap or drop fields in the same transaction (wizard merge already drops).

---



## 7. Feature Tiers



### Tier A — Organize pages (build first)

Lossless page-tree operations. Highest value for contracts (drop blanks, fix scan rotation). Maps to pypdf/pikepdf.


| Op               | Meaning                                                                       |
| ---------------- | ----------------------------------------------------------------------------- |
| Reorder          | New page sequence                                                             |
| Delete / extract | Subset or new Document                                                        |
| Rotate           | 90 / 180 / 270 — **bake into content** (or normalize `/Rotate` to 0 on write) |
| Split            | One Document → N documents by ranges                                          |
| Merge            | Already shipped; keep                                                         |


**UI:** make `PdfPageThumbnail` a **sortable** strip (`@dnd-kit` is already a dependency). Click still scrolls the viewer.

### Tier B — Additive sender markup (build second)

Same overlay idea as `FieldBox`, but **sender-owned** and **baked on Save**, not assigned to a signer.


| Op                       | Notes                                                         |
| ------------------------ | ------------------------------------------------------------- |
| Whiteout                 | Filled rect; on commit **redact** if possible, not only paint |
| Add text / image         | Content stream or flattened annotation                        |
| Page numbers / watermark | Overlay on all or selected pages                              |


Keep these out of `FIELD_TYPES` so sign flatten does not apply them twice.

### Tier C — “Edit existing text” / find-replace (defer)

Whiteout + redraw (acceptable lite), or license Apryse/Nutrient (real). Do not start here.

---



## 8. Target Data Model

Canonical while editing = **ops**, not a folded PDF (same invariant as the signing audit).

```json
{
  "base_document_id": "uuid",
  "source_url": "staging/{id}.pdf",
  "pages": [
    { "source_page": 1, "rotate": 90 },
    { "source_page": 3, "rotate": 0 }
  ],
  "ops": [
    { "op": "whiteout", "page": 1, "rect": [x, y, w, h] },
    { "op": "add_text", "page": 1, "x": 72, "y": 400, "text": "Invoice", "font": "Helvetica", "size": 12 },
    { "op": "add_image", "page": 2, "src": "blob-key", "x": 100, "y": 100, "width": 120, "height": 40 }
  ]
}
```

Coordinates: **PDF points, Y from top**, matching `fields.Field`. Convert from PDF.js viewport in one helper (extend `field-geometry.ts`; do not add a third space).

Commit:

```
apply(original_bytes, session) → new_bytes
upload documents/{id}/edit/job-{job_id}.pdf
pointer-swap Document.file_url
```

Invariants:

1. Never overwrite the original in place (keep `staging/` / original for retry).
2. Compose is a pure function: same source + ops ⇒ same bytes (idempotent job-scoped output key).
3. After commit, `/Rotate` is 0 and CropBox is the visible box so Place Fields and `embed_signature` share geometry.
4. `acks_late` redelivery must not double-apply (job-scoped object already exists → skip).

---



## 9. Suggested API

Keep `POST /api/documents/merge/`. Add task-style endpoints; do not accept a raw “replace this PDF blob” from the client as the only API.

```
POST /api/documents/{id}/organize/
  { pages: [{ source_page, rotate }], delete?: number[] }
  → 202 { job_id }  (or 201 for small files)

POST /api/documents/split/
  { document_id, ranges: [[1,3],[4,10]] }
  → new Document ids

POST /api/documents/{id}/edit-session/
  create session, return page_count

PATCH /api/documents/{id}/edit-session/
  autosave ops JSON

POST /api/documents/{id}/edit-session/commit/
  → 202 job → poll → new file_url / file_size
```

**Guards (copy from merge):**

- Owner only.
- `Document.status` in `draft` (and optionally `completed` **copies**, not in-place).
- Reject if `EnvelopeDocument` exists with `envelope.status == pending`.
- If the document already has `Field` rows or wizard `fieldPositions`, require `drop_fields: true` or return a page-remap map.

Large files: Celery `signing`-style queue (or a dedicated `pdf` queue), `transaction.on_commit`, poll `GET /api/documents/jobs/{id}/`. Merge today is synchronous; do not extend that pattern to 80-page scans.

Authoritative apply stays **on the server**. Optional `pdf-lib` in the browser is preview-only so signing and editing cannot diverge.

---



## 10. Frontend Implementation Map

Reuse, do not fork a second PDF viewer.


| Need          | Reuse                                                              |
| ------------- | ------------------------------------------------------------------ |
| Page render   | `VerticalPDFViewer` / `PdfViewer`                                  |
| Thumbnails    | `PdfPageThumbnail` — add drag handle + rotate/delete chrome        |
| Drag          | `@dnd-kit` (palette already uses it)                               |
| Overlay boxes | Pattern from `FieldBox` / `SignatureBox`, new `EditMarkupBox` type |
| Geometry      | `src/lib/utils/field-geometry.ts`                                  |
| API client    | `src/lib/api/documents.ts` next to `mergeDocuments`                |
| Library CTA   | `/dashboard/documents` beside Merge Selected                       |
| Wizard        | Step 1: “Prepare PDF” for the current draft doc(s)                 |


Suggested routes:

- `/dashboard/documents/[id]/organize`
- `/dashboard/documents/[id]/edit` (Tier B)

After organize/edit returns, wizard `uploadedDocuments` must point at the new `file_url` and revision key (`getDocumentViewerRevisionKey`) so react-pdf reloads.

---



## 11. Interaction with Signing

Editor commit writes **page content**. Sign flatten writes **signer fields** later.


| Time                  | What hits the PDF                                         |
| --------------------- | --------------------------------------------------------- |
| Upload / Word convert | Normalized original (see signing audit GAP-08)            |
| Editor commit         | Page ops + sender markup                                  |
| Sign                  | `embed_signature` / `embed_text` for envelope fields only |


Do **not** implement editor apply by looping `embed_text` once per markup op (signing audit GAP-07). One-pass apply per document.

If signing compose is later changed to `compose(original, all_values)`, editor output becomes the **original** for that envelope document. Version keys must record that.

---



## 12. Implementation Phases



### Phase 1 — Organize (Tier A)

1. Backend: organize + split; versioned output; pending-envelope guard; tests.
2. Frontend: sortable thumbnails; rotate/delete; call organize; invalidate field positions.
3. Normalize rotation on write so tagging geometry stays stable.

**Exit:** reorder + rotate 90° + delete a page on a draft PDF; Place Fields and a signature land on the intended spot.

### Phase 2 — Jobs + wizard entry

1. Async jobs for files over a size/page threshold (mirror signing `202`).
2. Wizard step 1 “Prepare PDF”.
3. Stale-job failure + retry (same lessons as signing GAP-04).



### Phase 3 — Additive markup (Tier B)

1. Edit session JSON + one-pass commit (text, image, whiteout, watermark).
2. Redaction-grade whiteout, not paint-only.
3. Appearance blobs in object storage (not base64 columns).



### Phase 4 — Optional

- Page-image cache for faster thumbnails.
- Licensed WebViewer only if true text-run editing is a hard requirement.
- Ingest flatten of AcroForms (signing audit GAP-08) so editor and stamper share a boring PDF.

---



## 13. Test Plan

Add failing tests first.


| Test                                                        | Guards                                                 |
| ----------------------------------------------------------- | ------------------------------------------------------ |
| `test_organize_pending_envelope_rejected`                   | Same as merge                                          |
| `test_organize_rotate_then_field_coordinates`               | Signature page/x/y still correct after `/Rotate` baked |
| `test_organize_redelivery_idempotent`                       | Job-scoped key; one visible result                     |
| `test_split_ranges_create_new_docs`                         | Source unchanged; new drafts                           |
| `test_edit_commit_does_not_use_envelope_fields`             | Markup baked; `Field` rows untouched                   |
| `test_whiteout_removes_underlying_text`                     | Extracted text no longer contains redacted string      |
| Frontend: thumbnail reorder updates `pages[]` before commit | Session model, not live PDF                            |


Keep existing merge and Place Fields tests.

---



## 14. Audit Checklist (for reviewers)

When a phase PR lands:

- [ ] Place Fields has no PDF-writer tools (rotate/whiteout/text-rewrite belong in prep).
- [ ] Pending envelopes cannot be organized/edited.
- [ ] Commit does not overwrite the previous object in place.
- [ ] Post-commit PDF has normalized rotation for tagging/signing.
- [ ] Field positions dropped or remapped when page indexes change.
- [ ] Editor apply is one pass, not N overlay rewrites.
- [ ] Whiteout on legal docs is redaction, not a white rectangle over live text.
- [ ] Browser is not the source of truth for output bytes.
- [ ] Signing pipeline still only flattens envelope fields.

---



## 15. Out of Scope Follow-ups

- Full Sejda task catalog (compress, n-up, grayscale, Bates, OCR).
- Client-only `pdf-lib` as the production writer.
- Editing completed/signed PDFs in place (fork a new draft copy instead).
- Building a PDF text engine. License or stay at whiteout+overlay.

---



## 16. Practical First Slice

Smallest shippable product: **Organize on** `draft` **documents**.

- Extend merge’s guards and storage versioning.
- Sortable `PdfPageThumbnail` rail.
- `POST /api/documents/{id}/organize/` with page order + rotations.
- Clear `fieldPositions` / refuse if fields exist.

That is iLovePDF “Organize PDF” plus DocuSign page prep, and it fits this stack without a new PDF engine.