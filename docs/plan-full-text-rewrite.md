# Plan 2 — Full text rewrite

Replace words that are already in the PDF. The old glyphs are removed from the page content stream. The new words are written in their place. Search and select-all must not find the old word.

This plan starts only after [Plan 1](plan-additive-text-edits.md) is in production. Plan 1 adds text by painting over the page and leaves the original operators alone. That writer cannot do this job. This plan adds a second writer, PyMuPDF, and a text layer in the editor so a click can land on an existing word.

[pdf-editor-design.md](pdf-editor-design.md) deferred this work (Tier C) because pypdf and ReportLab cannot delete `Tj` / `TJ` operators, and because subset fonts usually lack the new characters. This plan is that tier, specified far enough to build. It does not license a commercial SDK. It uses PyMuPDF (`pymupdf`), which can redact text operators and insert new text with a real font file.

Sejda’s browser behavior is the interaction model: pdf.js reads the text, HTML boxes sit on the words, and save sends an operation list. Sejda’s server is not available. The operation shape below is ours. The field names inside Sejda’s `editTextOperations` were never captured ([08-evidence-and-open-questions.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/08-evidence-and-open-questions.md), first open question). Do not spend time matching them.

**Date:** 2026-11-17 (revised 2026-11-18, see “Changes since this plan was written” below)

**Depends on:** Plan 1’s editor route, session model, revision model, guards, and `apply_add_text`. Plan 1 is in production.

**License:** PyMuPDF is AGPL-3.0 (or commercial from Artifex). The app is internal and open source, so the AGPL is accepted. No commercial license is needed.

## Changes since this plan was written

The editor changed after this plan was drafted. Where the sections below disagree with this list, this list wins. The affected sections have been updated to match.

1. **One screen for edit and sign.** `/dashboard/documents/[id]/edit` is now the edit-and-sign screen. It has an **Edit document** group (Add text) and a **Sign** group (signature, initials, date signed, designation). **Sign & complete** commits pending text into the PDF, then self-signs. Opened with `?from=wizard`, only the Edit group shows. The old self-sign editor is gone; `/dashboard/envelopes/self-sign` is only a document picker.
2. **The viewer is `VerticalPDFViewer`, not `text-edit-viewer.tsx`.** `text-edit-viewer.tsx` is no longer used by any route. The editor renders with `VerticalPDFViewer` in `fitToWidth` mode (the page fills the canvas width, zoom multiplies that). Added text is drawn through its `renderPageOverlay` slot, which passes each page’s size in CSS px and in points. The run layer goes in the same slot.
3. **Three layers, not two.** Bottom to top: canvas, overlay slot (run layer, then add-text boxes), signature/initials/date/designation fields. Field boxes win a click, then add-text boxes, then runs.
4. **Add text is a tool, not a bare click.** A click on empty page space creates a text box only while the **Add text** tool is on, so stray clicks don’t make boxes. Rewrite keeps that: clicking a run edits it in any mode; empty space adds text only in Add text mode.
5. **One undo history lives in the editor page**, covering added text and placed fields (`src/app/dashboard/documents/[id]/edit/page.tsx`). `edit_text` ops join that history. `use-text-edit-session` still owns the server session, autosave, restore, and commit.
6. **Placed signing fields are stored in PDF points** and converted to px for display, so zoom and window size never move them. Run geometry is already in points from pdf.js; keep it that way.
7. **Signing after a rewrite.** Because Sign & complete saves text first, a rewrite is committed before signing. A `422 rewrite_failed` must stop the signing step and show the message on the screen; it must not sign the unchanged file.
8. **Signers’ Add text during signing** (`signatures/recipient_text.py`, the sign page) stays add-only. Rewrite is for the document owner in the editor only.
9. **Bundled fonts.** `signatures/fonts/initials/` now holds the handwriting fonts for initials. The Liberation fonts for rewrite go in `documents/fonts/` as planned; the two sets are separate.

**Sejda notes:** [`incel-e-sign-web-app-front-end/sedja-references`](../../incel-e-sign-web-app-front-end/sedja-references/README.md)

## Sejda notes this plan uses

Plan 1 already maps the notes for adding text, the page scale, and save-as-a-list. This plan uses the notes for clicking text that is already in the file. The server that deletes those glyphs was not visible. [08-evidence-and-open-questions.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/08-evidence-and-open-questions.md) says the PDF library on their server is unknown, and the recorded Apply had empty operation lists. Where this plan specifies PyMuPDF rectangles and Liberation fonts, that is our design, grounded in what their browser was seen to do.

| Note | Use it for |
| --- | --- |
| [README](../../incel-e-sign-web-app-front-end/sedja-references/README.md) | Browser records edits. Server rewrites the PDF. `editTextOperations` is the list this plan fills |
| [01-architecture.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md) | Text engine names: `getTextContent`, `flattenTextLayer`, `existingTextEdit`, `findDocFont`, `isType3Font` (§1.3). pdf.js cannot save the page (§1.2) |
| [03-rendering-with-pdfjs.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md) | How existing text becomes boxes (§3.5): `getTextContent()`, join duplicates, refuse tiny text, substitute a font when the subset lacks letters. Scan detection on the first 10 pages (§3.5). Coordinate formula (§3.3) |
| [04-editing-tools.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md) | Click a run and edit it in place (§4.2). Find and replace is a series of those edits (§4.10). One page at a time (§4.1). Whiteout is not deletion (§4.7) |
| [05-apply-changes-protocol.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md) | `editTextOperations` sits next to `appendTextOperations` on the same task (§5.2). Both lists are always present. We send one `ops` array with both `op` values instead |
| [06-limits-errors-recovery.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md) | Messages for scans, XFA, complex scripts, and missing font characters (§6.2, §6.3) |
| [07-rebuild-blueprint.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) | The `EditText` shape (§7.2): new text fields plus `originalItems` for what to remove. Step 10 (§7.3) is this whole plan: remove drawing commands inside the original boxes, then draw the new text. pdf-lib cannot do that step (§7.1) |
| [08-evidence-and-open-questions.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/08-evidence-and-open-questions.md) | The exact JSON of one edit was not captured. The sample object in doc 5 and the `EditText` interface in doc 7 are reconstructions. Ours is a third shape, written down in section 5, and it is the one the serializer enforces |

[02-upload-and-file-lifecycle.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/02-upload-and-file-lifecycle.md) still does not apply. The file being rewritten is the draft already stored for the document.

---

## 1. What ships

On the same editor route, `/dashboard/documents/[id]/edit`, the sender can:

1. Click a word or a text run that is already drawn in the PDF and change it.
2. Add new text, which remains the Plan 1 operation.
3. Find a string and replace the runs that contain it.
4. Save once. The server removes the old runs, draws the replacements, then paints any new Plan 1 boxes.

The screen is the edit-and-sign screen, so it is not renamed. Once this plan ships, its **Edit document** group gains **Edit text** (click a word to change it) and **Find & replace** next to **Add text**. Until the rewrite path is on (`rewrite: false`, section 12), the group shows only **Add text**.

A rewrite is one existing text run replaced by a new string in the same place. It is not a word processor. It does not reflow the paragraph, resize the page, or move the following words out of the way. If the new string is wider than the old run, it can overlap the next run. The editor warns. It still saves, because that is how this class of tool behaves and because refusing every overflow blocks legitimate short edits that only look wide in the fallback font.

---

## 2. What this plan does not do

- Edit text that is not text. Scans, photos of paper, and words that were converted to curves have no text operators. `getTextContent()` returns nothing useful. The editor shows “This page has no editable text” and still allows Plan 1 add-text. Sejda’s wording is “Changing existing text inside scans not supported” ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)).
- Complex scripts: Arabic, Hebrew, Devanagari, and other text that needs glyph reordering. Refuse the run with “This script can’t be edited.” Sejda refuses the same cases ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md), [06-limits-errors-recovery.md §6.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md)).
- Rotated runs (the text matrix is not horizontal) and pages with `/Rotate != 0`. Plan 1 already rejects rotated pages. This plan also rejects a single rotated run on an upright page.
- Type 3 fonts. pdf.js can flag them. Skip those runs.
- Editing inside Place Fields, pending envelopes, non-draft documents, or encrypted files. Same guards as Plan 1 (`assert_document_editable`).
- Rewriting text during signing. A signer’s Add text on the sign page stays add-only.
- True redaction of an arbitrary rectangle as a separate product button. The rewrite engine removes text inside the run’s box, which is a redaction of that box. A freeform “redact this area” tool can call the same `apply_redactions` later. It is not required to ship rewrite. Do not label a white rectangle as redaction. Sejda’s whiteout is that white rectangle, and the product warns that the text remains in the file ([04-editing-tools.md §4.7](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md), [07-rebuild-blueprint.md §7.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md)).
- Reconstructing the original subset font when the new string needs characters the subset does not contain. Fall back to a bundled font and tell the user. Section 8.
- Client-side rewrite with `pdf-lib`. `pdf-lib` can draw new text. It cannot reliably delete existing text operators. The server is the writer, same rule as Plan 1. [07-rebuild-blueprint.md §7.1](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) says the same thing: the browser-only route loses “edit existing text,” and the full route needs PDFBox or PyMuPDF on a server. We take the PyMuPDF side of that choice. Their note names PDFBox as the other option. Either library can do step 10. This codebase is Python, so PyMuPDF is the one we add.

---

## 3. Why Plan 1’s writer cannot do this

`apply_add_text` merges a ReportLab overlay. The original content stream is still in the file. After a Plan 1 save:

- Select-all copies the old word and the new word.
- Search finds the old word.
- A white rectangle would hide the old word on screen and leave it in the file. That is Sejda’s whiteout, not their text edit ([04-editing-tools.md §4.7](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)).

PyMuPDF `page.apply_redactions()` deletes text operators whose glyphs intersect a rectangle, including text inside Form XObjects. `page.insert_text()` then draws the replacement with an embedded font. That pair is the rewrite.

pypdf can read a content stream as bytes. Rewriting it by hand means tracking `q`/`Q`, the text matrix, `Tm`, `Td`, `TJ` kerning arrays, and custom encodings. That is a PDF engine. Do not start one. PyMuPDF is the engine. [07-rebuild-blueprint.md §7.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) step 10 describes the job the engine has to do: find the text-drawing commands whose glyphs fall inside the original boxes, remove them, and draw the new string in the same font when it has the letters. `apply_redactions` plus `insert_text` is that job. We do not parse the content stream ourselves.

LibreOffice is already installed for Word → PDF upload. Sending a PDF through LibreOffice to change one word reflows the document. Do not use it here.

---

## 4. User flow

### 4.1 Open

Same route and same session as Plan 1. Session create grows a `text_runs` payload (section 6). The client can also build runs itself from pdf.js. Prefer the client as the source of the boxes the user sees, and send those boxes back on save. The server does not trust the client for the deletion: it deletes the rectangle the client names, then checks the result (section 10). Building runs on the server as well is a debug aid, not the hit-target.

On open, for each page, the client loads the page with pdf.js (already loaded by react-pdf) and calls `getTextContent()`. It groups items into runs (section 7) and stores them in memory. They are not operations. They are the hit targets.

If the first 10 pages have no text items with a non-empty string, show a banner: “No editable text found. You can still add text.” Sejda reads up to the first 10 pages with `getTextContent()` and, when none of them contain text, calls `markWholeDocAsScan` ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). Use that same 10-page sample. Per page, if that page has no runs, the click falls through to Plan 1 add-text. Their editor still allows adding text, images, and the other tools on a scan. We still allow add-text.

### 4.2 Change an existing run

1. The pointer is over a run. The run’s box highlights.
2. Click. The run becomes `contenteditable`. The box is opaque, filled with white, so the canvas word underneath is hidden while typing. The PDF on the server is unchanged. Sejda’s text layer does this with boxes built from `getTextContent()`, then `contenteditable` on the one you clicked ([04-editing-tools.md §4.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md), [03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). Their changed run becomes an `editTextOperations` entry. Ours becomes an `edit_text` op. The white fill is only on the HTML box. It is not a whiteout shape in the file.
3. The original string, the original box, the baseline, the font size, and the color are kept on the operation as `remove` and `original`. The text the user typed is `text`.
4. If the user clears the box and leaves it empty, commit treats it as a deletion of that run: remove the glyphs, write nothing.
5. Escape or click away commits the HTML edit into the session. Undo (the editor page’s one history) restores the previous snapshot, which drops the rewrite op and shows the canvas word again (the white box is gone).
6. A run that is rotated, Type 3, or a complex script does not become editable. The tooltip explains why.

Moving an existing run to a new place on the page is not supported. The replacement is drawn at the original baseline. If the user needs the words elsewhere, they delete the run (empty text) and add a Plan 1 box. Dragging the rewrite box would desync the deletion rectangle from the new text. Sejda does allow dragging edited text ([04-editing-tools.md §4.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md), “Drag text with your mouse to move it”). We can add that later by keeping `remove` fixed on the original glyphs and adding a separate draw position, which is what their `originalItems` versus the new box is for ([07-rebuild-blueprint.md §7.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md), `EditText.originalItems`). Leave the draw position equal to the original baseline in this plan.

### 4.3 Find and replace

A panel on the editor:

- Query string.
- Replacement string.
- Match case (default off).
- **Replace** steps to the next run whose string contains the query and applies one rewrite.
- **Replace all** creates one rewrite op per matching run on the loaded pages.

Find walks the in-memory runs. It does not scan the PDF on the server. Runs the user has already rewritten are matched against their new `text`, not the original string. Sejda searches the text it already read from the pages (`findOccurrences`), highlights each hit, and each replacement is a normal existing-text edit that lands in `editTextOperations` ([04-editing-tools.md §4.10](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)). Do not add a server search endpoint. Their “also replace in links” option is out of scope. We have no link tool.

Replace all is capped at 200 runs, the same box cap as Plan 1. Above that, the panel says how many matched and asks for a narrower query.

### 4.4 Add text

Add text stays a tool: empty-space clicks create a box only while **Add text** is on. Hit testing order:

1. If the click is inside a signing field (signature, initials, date, designation), select that field.
2. Else if it is inside an existing rewrite box or an add-text box, select that box.
3. Else if it is inside an unedited run, start a rewrite (in any mode).
4. Else, if the Add text tool is on, start an add-text box. Otherwise deselect.

### 4.5 Save

One commit. Body is the full op list: `add_text` ops from Plan 1 and `edit_text` ops from this plan. The editor sends it from **Save changes**, and from **Sign & complete** before it self-signs. If the commit returns `422`, Sign & complete stops and does not sign.

Server order, fixed:

1. Guards, including `base_file_url`.
2. Download the source.
3. Apply every `edit_text` with PyMuPDF. Write a temp file.
4. Apply every `add_text` with `apply_add_text` onto that temp file.
5. Verify (section 10). On verification failure, do not swap `Document.file_url`. Return `422` with the run ids that failed.
6. Upload `edits/{document_id}/{session_id}.pdf`, insert `DocumentRevision` with `source='edit_text'`, swap `file_url`, mark the session committed.

Rewrites run before adds. A redaction rectangle that runs after an overlay can delete the new text if the rectangles intersect. Sejda sends both lists on one task and leaves the order to the server ([05-apply-changes-protocol.md §5.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md)). [07-rebuild-blueprint.md §7.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) rule 2 says page deletions and reorders happen last so earlier ops still name the original page. Our rule is the same kind of ordering: destroy glyphs first, paint new boxes second, and do not renumber pages in this plan at all.

---

## 5. Operation

```ts
interface EditTextOp {
  opId: string
  op: 'edit_text'
  page: number
  text: string                    // replacement; empty means delete the run
  fontSize: number                // points, from the pdf.js run
  color: string                   // '#rrggbb', from the run
  fontName: string                // pdf.js font name, informational
  baseline: { x: number; y: number }   // PDF user space, bottom-left origin
  remove: { x: number; y: number; width: number; height: number }
  // remove is the tight glyph box, bottom-left origin, y growing up.
  // This is the rectangle the server deletes. It is not the HTML box
  // after the user resizes it. Resize is not offered on rewrite boxes.
  originalText: string
  fallbackFont: 'LiberationSans' | 'LiberationSerif' | 'LiberationMono' | null
  // null means "try the embedded font, then the suggested fallback"
}
```

`add_text` ops are unchanged from Plan 1. A session list may contain both. The closest Sejda shapes are `appendTextOperations` for `add_text` and `editTextOperations` for `edit_text` ([05-apply-changes-protocol.md §5.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md)). [07-rebuild-blueprint.md §7.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) draws `EditText` as an `AppendText` plus `originalItems`, the boxes to remove. Our `remove` rectangle is that `originalItems` list collapsed to one box per run. Their sample JSON in doc 5 uses `left`, `top`, `pageNum`, `fontName`, `fontSize`, and `fontColor`, and doc 8 marks it as an illustration. Do not parse or emit that JSON. The serializer in this plan is the contract.

The client sets `fallbackFont` when it already knows the embedded font cannot draw `text` (section 8). `null` lets the server try the embedded font first.

### 5.1 How the client builds `remove` and `baseline`

From a pdf.js text item (`getTextContent` item):

```ts
const [a, b, c, d, e, f] = item.transform
const fontSize = Math.hypot(c, d) || Math.abs(d) || item.height
const baseline = { x: e, y: f }          // PDF user space, y up
const remove = {
  x: e,
  y: f - fontSize * 0.3,                 // descenders
  width: Math.max(item.width, 0.5),
  height: fontSize * 1.25,
}
```

`e` and `f` are the text position in PDF user space (bottom-left, y up) for an unrotated page. `item.width` is in PDF units. This box is intentionally tight. A box as tall as the whole line gap will delete the line above when the server redacts. Sejda’s screen-to-PDF formula is `pdfX = cssX / scale` and `pdfY = pageHeight − cssY / scale` ([03-rendering-with-pdfjs.md §3.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). `getTextContent()` already returns PDF user space, so this plan does not start from CSS for `remove`. It uses the transform. CSS is only for painting the hit target (section 6.2), and that paint uses the same scale.

Only accept the item when the run is horizontal:

```ts
const horizontal = Math.abs(b) < 0.5 && Math.abs(c) < 0.5 && d > 0
```

Otherwise the run is not editable.

### 5.2 Server conversion into PyMuPDF

PyMuPDF rectangles use a top-left origin, y down. `page.rect.height` is the page height in points for an unrotated page.

```python
height = page.rect.height
box = edit["remove"]
y0 = height - (box["y"] + box["height"])
y1 = height - box["y"]
rect = fitz.Rect(box["x"], y0, box["x"] + box["width"], y1)

baseline = edit["baseline"]
point = fitz.Point(baseline["x"], height - baseline["y"])
```

Do not reuse Plan 1’s top-left frame for `remove`. Plan 1 frames are text boxes the user created. `remove` is a glyph box around existing drawing commands. Mixing the two origins will delete a rectangle on the wrong part of the page. The serializer checks that `remove.height` is within `4 * fontSize` and that `remove` lies inside the page in bottom-left space. A box taller than that is a client bug, and commit returns `400`.

Add a unit test that a known word’s pdf.js box, converted with this formula, intersects the PyMuPDF char bbox of that word and does not intersect the line above. Build the fixture with ReportLab so both coordinates are known.

---

## 6. Reading runs in the browser

`VerticalPDFViewer` renders with `renderTextLayer={false}`. The rewrite editor needs the text geometry, not pdf.js’s default HTML text layer (that layer is for selection and accessibility, and its DOM is awkward to turn into one editable run). Sejda builds its own boxes on `textLayer` from `getTextContent()` rather than relying on the stock text-layer divs alone ([03-rendering-with-pdfjs.md §3.2 and §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). Do the same. Their clean-up pass joins stacked duplicates (`flattenTextLayer`) and refuses text that is too small to edit. Section 6.1 is that pass, smaller.

Use pdf.js directly on the document the viewer already opened:

```ts
const page = await pdf.getPage(pageNumber)
const viewport = page.getViewport({ scale: 1 })
const content = await page.getTextContent()
```

react-pdf’s `Document` `onLoadSuccess` receives the pdf.js document proxy. `VerticalPDFViewer` owns that `Document` and does not expose the proxy yet. Add an `onDocumentProxy?: (documentId, pdf) => void` prop that it calls from `onLoadSuccess`, and build runs from that proxy in the editor page. Do not load the file a second time.

The proxy is replaced when the file changes (for example after **Save changes** commits text: the document gets a new URL and the `Document` remounts). Runs built from the old proxy describe the old file. Drop them and rebuild from the new proxy; keep no `edit_text` ops across a commit (commit clears ops, as Plan 1 already does).

### 6.1 Grouping items into runs

`getTextContent()` returns fragments, not words the user thinks of as words. Sejda flattens duplicates and joins fragments (`flattenTextLayer` in the reference notes). Do a smaller version:

1. Drop items with empty or whitespace-only `str`.
2. Drop items that fail the horizontal test.
3. Drop items whose `fontSize < 4` (Sejda’s message is “Text is too small to edit. Please zoom in and try again.”, [03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). The user can zoom; the test is in points, so zoom does not make a 3 pt run editable. That is acceptable. Do not invent a second size check in CSS pixels. Their zoom-and-retry message assumes the editor’s own zoom changes the scale used to hit-test. Ours does not, because the cutoff is in points. Say “This text is too small to edit” with no zoom instruction.
4. Sort by baseline `y` descending (PDF y up), then by `x`.
5. Join two neighbors into the same run when:
   - the same page, and
   - baselines differ by at most `0.25 * fontSize`, and
   - the gap between the end of the first and the start of the second is at most `0.6 * fontSize`, and
   - font size differs by at most 0.5 pt, and
   - the pdf.js font name matches.
6. Join with `''` if the gap is under `0.15 * fontSize`, otherwise with a single space. PDF writers often omit the space character and encode the gap in the position instead.
7. The run’s `remove` box is the union of the item boxes. The run’s baseline is the first item’s baseline. The run’s `fontSize` is the first item’s size. The run’s string is the join.

Cap display: if a page has more than 2 000 runs after joining, stop making runs on that page and show “This page has too many text pieces to edit.” Add-text still works. This guards pathological files where every letter is its own item and joining failed.

### 6.2 Painting

Runs are absolutely positioned divs over the canvas, drawn in `VerticalPDFViewer`’s `renderPageOverlay` slot, using the same CSS conversion as Plan 1, but from the bottom-left `remove` box. The slot passes `widthPx`, `heightPx`, `widthPt` and `heightPt` for the page, so `scale = widthPx / widthPt` follows fit-to-width and zoom without extra work:

```
scale = pageCssWidth / pageWidthPt   // = widthPx / widthPt from the overlay slot
left = remove.x * scale
top = (pageHeightPt - remove.y - remove.height) * scale
width = remove.width * scale
height = remove.height * scale
```

Unedited runs are transparent hit targets. `pointer-events: auto`. They do not show the string again. The canvas already drew it. Showing it twice blurs the page.

The edited run is opaque white, with the new string in the fallback or original font at `fontSize * scale` CSS pixels, baseline at `0.8 * fontSize` from the top of the box if you are matching Plan 1’s HTML, **except** rewrite boxes should anchor the CSS text to the pdf.js baseline so the new glyphs cover the old ones:

```
paddingTop = (remove.y + remove.height - baseline.y - fontSize * 0.8) * scale
```

Check this on the ReportLab fixture. If the white box does not cover the old canvas glyphs, increase `remove.height` slightly (the 1.25 factor) rather than painting a page-sized plate.

New Plan 1 boxes sit above the run layer so a click on an add-text box wins. Signing fields sit above both (the viewer’s field layer is above the overlay slot), so a click on a placed field wins over everything.

Keep the slot click-through: the overlay wrapper is `pointer-events: none`. Runs and boxes opt in with `pointer-events: auto`; the empty-space surface only catches clicks while the Add text tool is on.

### 6.3 Fonts while typing

The canvas word uses the embedded font. The HTML replacement will not, unless that font is loaded in CSS. Plan 1 maps Helvetica / Times / Courier to system stacks. For a rewrite, use the same three stacks chosen by the fallback suggestion (section 8) as soon as the user types a missing character. Before that, use the stack that matches the font name (serif, mono, sans). The screen will not be pixel-identical to the PDF. The save path embeds a real file. Do not fetch the subset from the PDF into the page for CSS; subset files without a usable cmap for new characters are why the fallback exists.

---

## 7. Server apply

New dependency: `pymupdf` in `requirements.txt`, **pinned to `pymupdf==1.26.7`** (Phase A, 2026-11-18). Import name is `fitz`. License: AGPL-3.0, accepted for this internal, open-source app (see the header). The constant names in §7.1 were checked against 1.26.7 and exist as written.

### Phase A as built (2026-11-18)

Built in `documents/services/pdf_rewrite.py`, `apply_text_session` in `documents/services/pdf_text.py`, and the session/commit views. All 12 Liberation files (sans, serif, mono × regular, bold, italic, bold italic) are in `documents/fonts/` with `LICENSE-Liberation.txt` (SIL OFL 1.1). Where the build differs from the text below, this list is what the code does:

1. **Coordinates.** `remove` and `baseline` are converted with `page.transformation_matrix` instead of `height − y`. It is the same formula for an ordinary page and also handles a MediaBox that does not start at (0, 0).
2. **No-fill redaction is explicit.** `add_redact_annot(rect, fill=False, cross_out=False)`. PyMuPDF fills with white by default; deletions (empty `text`) pass `fill=(1, 1, 1)`.
3. **Standard fonts that were never embedded** (Helvetica, Arial, Times, Courier) use their metric-compatible Liberation twin **without** `font_replaced`: nothing was embedded to keep, so “It was missing characters you typed” would be untrue. If the run is bold/italic and that file is missing, the warning is `style_replaced`. `font_replaced` is kept for an embedded font that really cannot draw the new text, and for a client-requested `fallbackFont`.
4. **A character no font can draw** (the chosen font, embedded or Liberation, lacks it — e.g. CJK) is refused: `400 unsupported_character` with `opIds`. Nothing is inserted with a font that failed the coverage check.
5. **Verification also checks the run’s own position.** Besides the characters inside `remove` (§10), the server reads the original run’s characters from the source page (on its baseline, from its baseline x, spelling `originalText`) and fails the op if every one of them is still drawn at the same position in the output. A box that misses the word entirely would otherwise pass: the new word drawn on top hides the old one from the box check.
6. **Pre-checks before anything is deleted**, from PyMuPDF’s character map: a box containing characters from another line → `400 box_covers_other_text`; a box containing non-horizontal text → `400 rotated_text`. Overlapping boxes from two ops are rejected at validation as `boxes_overlap`.
7. **Engine missing.** If PyMuPDF does not import, the session reports `rewrite: false` and `edit_text` ops are rejected with `rewrite_unavailable`.
8. **The output is written only after verification passes**, so a failed rewrite leaves no file and the document and open session are untouched.

### Phase B as built (2026-11-18)

Frontend: `src/lib/pdf-edit/text-runs.ts` (grouping, locks, stable ids, CSS box), `classifyPdfFont` in `src/lib/pdf-edit/fonts.ts` (same order as the server), `src/components/pdf-edit/use-text-runs.ts` (reads text through the viewer’s pdf.js document), `src/components/pdf-edit/text-run-layer.tsx` (hit targets and in-place editing), `VerticalPDFViewer`’s `onDocumentProxy`, and the editor page. `text-edit-viewer.tsx` is deleted. Differences from the sections below:

1. **Add text mode wins the page.** While the Add text tool is on, a click anywhere places a box, including over words; runs only take clicks when it is off. With no mode for editing words, that keeps the two gestures unambiguous. (§4.4 said runs win in any mode.)
2. **All pages are read in the background** once the document loads (one page after another), not only visible pages. Find & replace (Phase C) needs them anyway. The sidebar shows “Reading the document’s text…” until done, and “No editable text found. You can still add text.” when the first 10 pages have none.
3. **Runs carry `page.view`**, so CSS boxes subtract the view origin (pages whose CropBox does not start at 0,0), matching the server’s `transformation_matrix`.
4. **Colour is `#000000`.** pdf.js text content has no colour; reading it from the operator list is left for Phase C.
5. **Unchanged edits are not sent.** An edit whose text equals the original (opened then closed, or undone back) is dropped when the run is left, isn’t counted as a change, and is filtered out of the commit.
6. **The font fallback is decided on the server only.** The editor previews with the serif/sans/mono stack and shows “Original font replaced. It was missing characters you typed.” after a save that reports `font_replaced`. Predicting it before save from the font’s cmap is not built.
7. **Failed edits are outlined.** A save that returns `opIds` (e.g. `rewrite_failed`, `box_covers_other_text`) outlines those runs in red with “This change couldn’t be saved. Undo it or try again.”
8. **`VerticalPDFViewer` keys its `Document` on the file URL**, so a save that changes the file remounts it cleanly (the same `sendWithPromise` crash the signing viewer had).

Checked in the browser on a test document: “Please pay the invoice.” → “Please pay the receipt.” and “Jose Martinez” → “José Martínez” in one save; the downloaded file contains the new text and not the old, revision `edit_text`. A second save on the same document worked, and the previously rewritten lines were editable again (§14). Sign & complete with a pending rewrite uses the same save path but was not run end-to-end (the dev database is missing signatures migration 0006).

### Phase C as built (2026-11-18)

Frontend: `src/lib/pdf-edit/find-replace.ts` (matching and replacing over runs), `src/components/pdf-edit/find-replace-panel.tsx` (in the sidebar’s Edit document group; Ctrl/⌘+F opens it), match highlighting and the overflow warning in `text-run-layer.tsx`. Server verification and the box-covers-other-text check were already built in Phase A. Notes:

1. **Find & replace** matches each run’s current text (pending replacement, else original), case-insensitive unless Match case is on. Find next steps in reading order and stops at the end (“No more matches. Press Find next to start from the top.”). Replace and Replace all replace every occurrence of the query inside a matching run. Replace all is one undo step, waits until every page’s text has been read, and refuses more than 200 matches.
2. **Overflow warning.** A replacement wider than the original run by more than 4 pt gets an amber outline and, while typing, “Longer than the original. It may overlap the words after it.” Saving is still allowed.
3. **Pages with too many text pieces** are listed in the Edit text card (“…too many text pieces to edit. You can still add text there.”).
4. **Verification tells old letters from new by font.** A replacement that starts with the original (“Ref: A1” → “Ref: A1-2026”) drawn in a metric-compatible Liberation font puts its first letters exactly where the old ones were; the check counts only characters in the original run’s font as left behind. Where the original embedded font was reused, fonts can’t tell them apart and a replacement that contains the original is allowed (§10’s rule). This was found in the browser: the first version refused that edit with `rewrite_failed`.
5. **Not built:** the XFA banner, and predicting the font fallback before save.

### Colour and style (2026-11-18)

Replacements keep the original text’s colour and weight.

1. **Server reads styles when the session opens.** `page_text_styles` (in `pdf_rewrite.py`) returns, per page, `[x0, y0, x1, y1, "#rrggbb", bold, italic, font_name]` for every span (box in PDF user space). It runs in `assert_document_editable`, on the file that is already downloaded: about 2 ms and 1 KB a page (29-page document: ~62 ms, 27 KB). Only the open response carries `text_styles`; autosave keeps the ones it has.
2. **`font_name` is the real name** inside the embedded font program (“Arial Black”, “Calibri Light”); many PDFs only say “CIDFont+F3”. The editor uses it for the preview’s family and weight.
3. **The editor** looks up each pdf.js text piece’s span by its centre, takes the colour and bold/italic from it, and starts a new run where colour or style changes (a red “E-mail:” next to a blue link become two runs).
4. **On save the original letters decide.** `rewrite_text` reads the colour and bold/italic most of the run’s characters are drawn with and uses them, ignoring the client’s colour unless the run can’t be found. It works on copies of the ops, so the stored session isn’t modified.
5. **Font lookup accepts either name**: the PDF’s (“CIDFont+F3”) or the real one (“Arial Black”), compared without case, spaces, hyphens or a trailing “Regular”.
6. **Whitespace-insensitive “new text landed” check.** A reused subset font can map its space glyph to U+00A0, so “Weight: 1,800” reads back as “Weight:\xa01,800”.
7. **Same font, new text containing the old** (“Zenith Bank” → “Zenith Bank Plc”) is allowed, as §10 says; one clause had still refused it.
8. **A second save in the same visit works.** Commit closes the server session; the editor now opens a new one right after, on the new file (also bringing that file’s styles). Before, the next autosave and save got 404.

Checked on a copy of the Hivolt invoice: the grey “Weight: 1,759.5kg”, dark red Arial Black heading and black “Zenith Bank” previewed and saved in their own colours and fonts (Calibri Light, Arial Black, Calibri reused, no font warnings), in two saves without reloading.

Checked in the browser on a two-page test document: “invoice” found 3 times; Find next highlighted the first; Replace changed one; Replace all changed the rest; one undo restored the whole replace-all and redo re-applied it; an overlong replacement showed the warning; the save produced “receipt” on both pages and the long reference line, revision `edit_text`.

New module: `documents/services/pdf_rewrite.py`.

Bundled fonts, committed as files, not downloaded at runtime:

```
documents/fonts/LiberationSans-Regular.ttf
documents/fonts/LiberationSans-Bold.ttf
documents/fonts/LiberationSans-Italic.ttf
documents/fonts/LiberationSans-BoldItalic.ttf
documents/fonts/LiberationSerif-Regular.ttf
documents/fonts/LiberationSerif-Bold.ttf
documents/fonts/LiberationSerif-Italic.ttf
documents/fonts/LiberationSerif-BoldItalic.ttf
documents/fonts/LiberationMono-Regular.ttf
documents/fonts/LiberationMono-Bold.ttf
documents/fonts/LiberationMono-Italic.ttf
documents/fonts/LiberationMono-BoldItalic.ttf
```

Liberation is metric-compatible with Arial, Times New Roman, and Courier New. The license file ships next to the fonts. Regular is the only face required for the first rewrite milestone. Bold and italic files land in the same milestone if the run’s pdf.js font name contains `Bold` or `Italic` / `Oblique`. If the matching file is missing, use regular and add a warning on the commit response. Do not fail the save for style.

### 7.1 `rewrite_text`

```python
def rewrite_text(source_path: str, dest_path: str, edits: list[dict]) -> list[dict]:
    """
    Apply edit_text operations. Return a list of warnings
    ({opId, code}). Raise RewriteError if verification fails.
    Does not modify source_path.
    """
```

Per page that has edits:

1. `doc = fitz.open(source_path)`.
2. Add one redaction annotation per edit, with **no fill**:

   ```python
   page.add_redact_annot(rect)
   ```

   Fill paints a white plate that can cover neighbors and images. The replacement glyphs cover the old area. Empty replacements (deletions) pass `fill=(1, 1, 1)` only on that rectangle, because otherwise the hole shows whatever was behind the text. Deletion fill is white. If the page background is not white, a white hole is visible. Accept that in this plan and mention it in the UI for empty rewrites: “Deleted text is covered with white.”

3. Apply every annotation on the page in **one** call:

   ```python
   page.apply_redactions(
       images=fitz.PDF_REDACT_IMAGE_NONE,
       graphics=fitz.PDF_REDACT_LINE_ART_NONE,
       text=fitz.PDF_REDACT_TEXT_REMOVE,
   )
   ```

   Confirm the constant names against the pinned PyMuPDF docs when implementing. The intent is: remove text, leave images, leave vector art. Applying redactions one edit at a time rewrites the content stream repeatedly and moves later coordinates.

4. For each edit whose `text` is non-empty, `page.insert_text` at `point` with `fontsize=edit["fontSize"]`, `fontfile=resolve_font(...)`, and `color=(r, g, b)`.

5. `doc.save(dest_path, garbage=4, deflate=True)`.

`garbage=4` removes unused objects, including font programs that the redaction orphaned. That is what makes the old glyph data actually gone, not only unreferenced from the page. A test opens the output as bytes and asserts the original word is absent both from `page.get_text()` and from a latin-1 / utf-8 scan of the raw bytes when the word was unique in the file. Subset hex encodings will not contain the ASCII word. The `get_text()` assertion is the one that matters. The raw scan catches a careless overlay that left the ASCII string in the stream.

### 7.2 Font resolution

```python
def resolve_font(doc, page, edit) -> tuple[str, str | None]:
    """
    Return (fontfile_path, warning_code or None).
    """
```

Order:

1. If `edit["fallbackFont"]` is set, use that Liberation file. Warning `font_replaced` if the caller asked for a fallback.
2. Else find the page font whose base name matches `edit["fontName"]` after stripping a subset prefix (`ABCDEF+Calibri` → `Calibri`). `page.get_fonts(full=True)` and `doc.extract_font(xref)`.
3. If the extracted buffer is an OpenType or TrueType the library can open (`fitz.Font(fontfile=...)` or `fontbuffer`), and `font.valid_codepoints()` contains every non-space character in `edit["text"]`, write the buffer to a temp file and use it. No warning.
4. Else pick Liberation by the original font name:
   - Name contains `Times`, `Georgia`, `Cambria`, `Garamond`, `Liberation Serif`, or `Serif` → serif.
   - Name contains `Courier`, `Consolas`, `Mono`, or `Typewriter` → mono.
   - Else sans.
   - Bold / italic from the name, when those files exist.
   - Warning `font_replaced`.

The client should do the same classification so the warning appears before save, not only after. The server decision wins. The commit response includes `warnings: [{ opId, code: 'font_replaced', font: 'LiberationSans' }]`. The editor shows “Original font replaced. It was missing characters you typed.” That sentence is Sejda’s ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md), [06-limits-errors-recovery.md §6.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md)). Their picker chooses serif, sans, or mono (`isSerif`, `isMonospace`, `suggestedFont`). Section 7.2’s name table is that picker, pointed at Liberation files instead of their `fonts.css` list. They also refuse a style change the embedded font cannot do (“This font does not support this style change”). We fall back to Liberation Regular when the bold or italic file is missing, and we put that on the warning rather than blocking the save.

Do not use ReportLab’s Helvetica for rewrites. Plan 1 boxes still use Helvetica. Rewritten runs use Liberation or the extracted font so non-WinAnsi characters work. A rewrite of the word `Hello` to `Hello` can keep the embedded font when the cmap covers those letters. A rewrite to `Héllo` falls back.

### 7.3 Commit orchestration

`documents/services/pdf_text.py` grows `apply_text_session(source_path, dest_path, ops) -> warnings`:

1. Split ops into `edit_text` and `add_text`. Reject any other `op` (Plan 1 already rejects unknown ops).
2. If there are rewrites, `rewrite_text` into a temp file. Else the temp file is the source.
3. If there are adds, `apply_add_text` from that temp file to `dest_path`. Else move the temp file to `dest_path`.
4. Return warnings.

The view from Plan 1’s `POST …/text-edits/commit/` calls `apply_text_session` instead of `apply_add_text` directly. Plan 1 behavior is the case where every op is `add_text`: `rewrite_text` is not called, and the output bytes stay on the ReportLab path. Add a test that a Plan 1 commit with PyMuPDF installed produces the same extracted text as before this plan.

`DocumentRevision.source` is `edit_text` when the list contained any rewrite, otherwise `add_text`.

---

## 8. Matching a run to a font on the client

pdf.js font names look like `g_d0_f1`. The useful name is on the font object (`commonObjs`, `loadedName`, and the `name` field which often still has the subset prefix). Sejda’s names for this lookup are `findDocFont` and `getSubsetFontOriginalName` ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md), [01-architecture.md §1.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md)). Strip a `ABCDEF+` prefix the same way before classifying serif, sans, or mono.

When the user types, for each new character:

- If the font object exposes a cmap or glyph set and the character is missing, set `fallbackFont` from the name table in section 7.2 and show the warning immediately.
- If the cmap is unavailable, leave `fallbackFont` null and let the server decide. Do not block typing.

This check is a preview. The server repeats it. A mismatch (client said the embedded font works, server falls back) is a warning, not an error.

---

## 9. Find and replace

Implementation is client-side over the run list. The interaction to copy is [04-editing-tools.md §4.10](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md): a search box, match case, find next, replace and find next, replace all. Each hit becomes one existing-text edit, and undo can revert the replacement (`undoReplacement`). We skip “also replace in links.” There is no link editor. Match case defaults off. Their control exists. Ours can default the other way without changing the data model.

- Case-insensitive by default. Compare with `toLocaleLowerCase('en')`. Do not use a locale that changes length (Turkish `İ`) for the first version; use a simple `toLowerCase` and document that Turkish casing is inexact.
- A match is a run whose current string contains the query. The current string is `text` if a rewrite op exists for that run, else `originalText`.
- Replace builds an `edit_text` op. `remove` and `baseline` stay the original run’s values, even if a previous replace changed the string. The glyphs in the file are still the original ones until save. Replacing twice before save updates the same op’s `text`. It does not stack two redactions.
- Identify the op for a run by `runId`, stored on the run and copied onto the op as `opId` (`edit-` + a hash of page, baseline x, baseline y, original text, width). Stable ids mean a second replace edits the same op. Including `originalText` means two identical words on the same baseline still get different boxes because `x` differs.
- **Replace all** loops the matches and creates or updates those ops. One undo step restores the whole replace-all, not each word. Push one snapshot before the loop.

Find does not wrap across pages in a surprising way: **Find next** moves to the next match in page order, then to the next page, and stops at the end with “No more matches.”

---

## 10. Verification before the file is swapped

After `apply_text_session`, before upload:

For each `edit_text` whose `originalText` has at least 2 characters and contains a letter or digit:

1. Open the output with PyMuPDF.
2. Look at `page.get_text('rawdict')` characters on that page.
3. A character “falls inside” `remove` when its bbox center is inside the rect expanded by 1 pt (after the same top-left conversion).
4. Fail the commit if any character inside that rect equals the corresponding character of `originalText` and the replacement does not also contain that word. Practical check: the concatenation of characters whose centers lie in the rect, with spaces ignored, must not equal `originalText` with spaces ignored, unless `text` stripped equals `originalText` stripped (a no-op rewrite).
5. If `text` is non-empty, `page.get_text()` for that page must contain `text`. This can false-fail when the same string was already elsewhere on the page. Only assert it when `text` was not already in the source page’s extracted text, or when `text` is longer than `originalText` and the count of occurrences increased.

On failure: `422` `{ reason: 'rewrite_failed', opIds: [...] }`. Delete the temp output. Leave `Document.file_url` and the open session alone. The UI says “Couldn’t replace the text on the page. The file was not changed.” and leaves the boxes in place.

This check is what stops a bad rectangle from shipping a file that still contains the old word under the new one.

Also refuse, at validation time, a `remove` rect that contains the center of another run the user did not edit. That happens when grouping built a box around two lines. Return `400` `{ reason: 'box_covers_other_text', opId }` and highlight the run. The user can still add text. They cannot save a rewrite that would eat the line above.

The server computes “contains another run” from PyMuPDF `rawdict`, not from the client’s run list. The client’s grouping is for hit testing. The server’s char map is the authority for what will be deleted.

---

## 11. Unsupported runs and files

| Case | Detection | Behavior |
| --- | --- | --- |
| Scan, or page with no text | No runs after `getTextContent`. Sejda samples 10 pages ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)) | Banner. Add-text still works |
| Rotated page | Plan 1 session guard, `/Rotate != 0`. Sejda stores `data-rotation` and blocks rotate once a page has edits ([03-rendering-with-pdfjs.md §3.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)) | Editor does not open |
| Rotated run | `abs(b)` or `abs(c)` ≥ 0.5 in the text matrix. [07-rebuild-blueprint.md §7.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) says screen positions have to be un-rotated before save | Run is not a hit target |
| Type 3 | Font name or pdf.js font type. Sejda’s text engine has `isType3Font` ([01-architecture.md §1.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md)) | Run is not a hit target |
| Font size under 4 pt | `fontSize` | Run is not a hit target |
| Complex script | Unicode range of the run (Arabic, Hebrew, Syriac, Thaana, Devanagari, Bengali, and the other Indic blocks) | Run is not a hit target. Tooltip |
| XFA | pdf.js load error or the XFA dataset. Sejda sets `enableXfa: false` and shows “Document contains XFA elements, which are not supported.” ([03-rendering-with-pdfjs.md §3.1](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md), [06-limits-errors-recovery.md §6.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md)) | Banner “This form type can’t be edited.” Add-text still allowed if the pages render |
| Encrypted / pending / not draft | Plan 1 guards | Unchanged |
| Replacement much wider than the run | Canvas `measureText` of the new string at `fontSize` is more than `remove.width + 4` pt | Inline warning on the box. Save allowed |
| Two rewrites whose `remove` rects intersect | Server validation | `400`. The UI asks the user to undo one |

Owner-password permissions: Plan 1 refuses encrypted files. Keep that. Do not add a password field in this plan.

---

## 12. API changes

No new route. Plan 1’s session and commit routes grow.

`POST /api/documents/{id}/text-edits/` response adds:

```json
{
  "rewrite": true,
  "limits": { "max_runs_per_page": 2000, "min_font_size": 4 }
}
```

`rewrite: false` if PyMuPDF failed to import on that environment. The UI then stays on Plan 1 behavior and hides find/replace and run hit targets. Production must have the package. The flag exists so a partial deploy does not offer clicks the server will reject.

`PUT` and `POST …/commit/` accept `edit_text` ops. The serializer is a discriminated union on `op`.

Commit response adds:

```json
{
  "warnings": [
    { "opId": "…", "code": "font_replaced", "font": "LiberationSans" }
  ]
}
```

`422` body for verification failure:

```json
{ "reason": "rewrite_failed", "opIds": ["…"] }
```

Dependency: `pymupdf` in `requirements.txt`. System packages are the wheels PyMuPDF publishes. No extra apt package if the wheel is used. Confirm `import fitz` in `core/tests/test_dependencies.py` next to the existing pypdf import test.

---

## 13. Frontend changes

On top of the current editor files:

| File | Change |
| --- | --- |
| `src/components/envelope/VerticalPDFViewer.tsx` | `onDocumentProxy(documentId, pdf)` prop, called from `onLoadSuccess` |
| `src/app/dashboard/documents/[id]/edit/page.tsx` | Build runs from the proxy per loaded page. Render the run layer in `renderPageOverlay` under the add-text boxes. `edit_text` ops join the page’s one undo history. Handle `rewrite_failed` and `font_replaced` from commit, and stop Sign & complete on `422` |
| `src/components/pdf-edit/text-run.tsx` | Transparent hit target. Becomes the editor when clicked |
| `src/components/pdf-edit/text-run-layer.tsx` | The page’s runs plus in-progress rewrites, for the overlay slot (sibling of `signing-page-text-layer.tsx`, which draws add-text boxes) |
| `src/components/pdf-edit/find-replace-panel.tsx` | Query, replace, replace all. Shown in the editor sidebar’s Edit document group |
| `src/components/document-editor/editor-tools-sidebar.tsx` | **Edit text** and **Find & replace** in the Edit document group, hidden when `rewrite: false` |
| `src/lib/pdf-edit/text-runs.ts` | Group `getTextContent` items, horizontal test, script test, stable `runId` |
| `src/lib/pdf-edit/fonts.ts` | Fallback classification shared with the warning copy |
| `src/components/pdf-edit/use-text-edit-session.ts` | Hold both op types for autosave, restore and commit (the undo history is the page’s) |
| `src/lib/api/documents.ts` | Types for `EditTextOp`, warnings and `rewrite_failed` |

`src/components/pdf-edit/text-edit-viewer.tsx` is no longer used by any route. Do not extend it; delete it when this plan starts.

Page stack, bottom to top:

```
canvas
overlay slot: run layer (hit targets and in-progress rewrites)
overlay slot: add-text layer (Plan 1 boxes)
signing fields (signature, initials, date, designation)
find panel (sidebar, not on the page)
```

Build runs when the page’s pdf.js page has loaded, not for every off-screen page up front. The viewer already knows which pages are mounted. When a page unmounts, keep its runs in a map so Find can see pages the user has visited. **Replace all** only covers pages whose runs are loaded. Before replace-all, load text content for every page (a progress label: “Reading text…”). That pass does not render canvases. It only calls `getPage` and `getTextContent`.

Do not turn on react-pdf’s `renderTextLayer`. The custom run layer is the hit target. Two text layers will steal clicks from each other. Sejda’s page has one `textLayer` for both existing runs and new text ([03-rendering-with-pdfjs.md §3.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). We stack run boxes under add-text boxes so the Plan 1 gesture still wins when they overlap.

Selection across pages is unsupported. A drag that leaves the page ends the edit. Sejda’s message is “Selecting objects on different pages is not supported” ([04-editing-tools.md §4.1](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)). [07-rebuild-blueprint.md §7.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) says to keep that rule.

---

## 14. Composition with signing and Plan 1

Unchanged from Plan 1, with one extra rule:

| Order at commit | Writer | Effect |
| --- | --- | --- |
| 1 | PyMuPDF `rewrite_text` | Deletes old runs, inserts replacements |
| 2 | ReportLab `apply_add_text` | Paints new boxes on top |
| 3 | Later, at sign time, unchanged | `embed_fields_single_pass` paints signer fields (signature images; date, initials and designation text fitted to their boxes, filled by the server) |

On the edit-and-sign screen, steps 1–2 and step 3 can happen in one click: **Sign & complete** commits the text session, then calls self-sign with the new file. Placed signing fields are in PDF points and are not affected by the rewrite (a rewrite never moves or resizes the page).

A rewritten word is page content. Place Fields does not see it as a field. Sign flatten does not redraw it.

Text that Plan 1 baked in a previous save is normal page text. This plan can rewrite it, because it is real `Tj` text in a standard font. That is an explicit acceptance test: add “Invoice” with Plan 1, save, open the editor again, change “Invoice” to “Receipt”, save, and assert the file contains `Receipt` and does not contain `Invoice`.

Do not rewrite text by creating a Plan 1 box on top of the old word. If someone is tempted to ship “edit” that way, the verification test in section 10 is the thing that makes it fail review.

---

## 15. Build order

### Phase A — Engine, no UI

1. Add `pymupdf` and the Liberation Regular files (sans, serif, mono).
2. `rewrite_text` and `resolve_font`.
3. Tests in section 16 that call the function directly.
4. `apply_text_session` calling rewrite then `apply_add_text`.
5. Serializer accepts `edit_text`. Commit uses `apply_text_session`.

Exit: API commit can replace `Hello` with `Goodbye` on a fixture PDF. Extracted text has `Goodbye` and not `Hello`. A Plan 1-only commit still passes the Plan 1 tests.

### Phase B — Hit targets

1. `text-runs.ts` grouping and tests, including a line with a missing space encoded as a gap.
2. `VerticalPDFViewer` `onDocumentProxy`. Run layer in the editor’s overlay slot. Click to edit. Opaque box. Save and Sign & complete send `edit_text`.
3. Warnings for font fallback rendered on the box after commit, and predicted before commit when the cmap is known.

Exit: the browser acceptance script in section 17, items 1–4.

### Phase C — Find and replace, verification, edges

1. Find panel, replace, replace all, one undo step for replace all.
2. Server verification and the “box covers another run” rejection.
3. Banners for scans, small text, rotated runs, complex scripts.
4. Bold/italic Liberation files if Regular-only fallback is visibly wrong on a bold run.

Exit: section 17 items 5–8.

---

## 16. Tests

`documents/tests/test_pdf_rewrite.py`:

| Test | Assert |
| --- | --- |
| `test_replace_word_removes_old_text` | ReportLab PDF with `Hello World`. Edit `Hello` → `Goodbye`. `get_text` contains `Goodbye` and `World`. It does not contain `Hello`. Raw file bytes do not contain `Hello` |
| `test_replace_middle_of_line_keeps_neighbors` | `Alpha Beta Gamma`. Replace `Beta`. `Alpha` and `Gamma` remain. Their char centers are outside the redaction rect |
| `test_delete_run_removes_text` | `text: ""`. Old word gone |
| `test_missing_glyph_uses_liberation` | `Hello` → `Héllo` in Helvetica. Output text contains `Héllo`. Warning `font_replaced`. Extracted font name is not Helvetica |
| `test_embedded_font_reused_when_cmap_covers` | A PDF that embeds a full TTF (not a subset) covering the new letters. Warning list is empty. This fixture can be skipped if generating a full embed is brittle; do not skip the fallback test |
| `test_two_edits_one_apply_redactions_call` | Two words on one page. Both replaced. Spy or a single content-stream generation: both new words present, both old words absent |
| `test_rewrite_then_add_text` | Rewrite one word and add another box. Both results present. Old word absent |
| `test_rewrite_does_not_remove_image` | Page with an image and a word that does not overlap it. After rewrite, `page.get_images()` is non-empty |
| `test_box_covering_next_line_rejected` | A `remove` rect tall enough to include the next line. `400` or `RewriteError` before save. Source file unchanged |
| `test_rotated_run_rejected` | Text drawn with a 90° matrix. Validation error |
| `test_plan1_commit_unchanged` | Only `add_text` ops. Original text still present. New text present. PyMuPDF not required to have modified the content stream (no redaction) |

`src/lib/pdf-edit/text-runs.test.ts`:

| Test | Assert |
| --- | --- |
| Joins fragments split by a small gap into one run with a space | |
| Does not join two lines | Baselines differ by more than `0.25 * fontSize` |
| Drops a rotated item | |
| Drops a 3 pt item | |
| Stable id differs for two identical words at different x | |

API:

| Test | Assert |
| --- | --- |
| `test_commit_rewrite_swaps_revision` | `source='edit_text'`. Previous revision remains downloadable |
| `test_commit_rewrite_failed_keeps_file_url` | Force verification to fail (rect that misses the glyphs). `422`. `file_url` unchanged |
| `test_commit_mixed_ops` | One `edit_text`, one `add_text` |

Fixture helper: build PDFs with ReportLab in the test, the same way `signatures/tests/test_pdf_signing.py` does. Also keep one binary fixture of a “printed” PDF (a word processor export with a subset font) in `documents/tests/fixtures/`. The ReportLab tests prove the geometry. The binary fixture proves a subset font takes the Liberation path. Check the fixture into git. Keep it one page and small.

---

## 17. Acceptance

1. Open a draft PDF that contains the sentence `Please pay the invoice.` The words are not HTML. Click `invoice`. The box becomes editable and hides the canvas word.
2. Type `receipt`. Save. Download. Search in a PDF reader finds `receipt` and does not find `invoice`. The rest of the sentence is still there.
3. Repeat on a word that needs an accent (`Jose` → `José`). The file contains `José`. The UI said the original font was replaced.
4. Add a new Plan 1 box on the same save as a rewrite. Both appear. The rewritten old word is gone. The added box is present. Signer fields placed afterward still land where they were placed.
5. Find `pay`, replace with `send`. Only that run changes.
6. Replace all on a word that appears twice. One undo restores both, before save. After save, undo is gone and the file has the new words.
7. A scanned page shows the no-editable-text banner. Add text still saves.
8. A pending envelope still cannot be opened in the editor.
9. On the edit-and-sign screen, change a word, place a signature, and press **Sign & complete** without saving first. The signed file has the new word, not the old one, and the signature where it was placed. If the rewrite fails verification, nothing is signed and the message is shown.
10. Zoom in and resize the window after editing a run. The edit box stays over the original word.

---

## 18. Risks

| Risk | What to do |
| --- | --- |
| Redaction rectangle eats the line above | Tight `remove` box (`1.25 * fontSize`). Server rejects a rect that contains another run’s character centers. Test `Alpha Beta Gamma` |
| Redaction removes an image or a line that intersects the word | `PDF_REDACT_IMAGE_NONE` and line-art none. Test a page with an image |
| Old word still in the file as an unused stream | `garbage=4`. Assert extracted text, not only the picture on screen |
| Subset font missing glyphs, server inserts `.notdef` boxes | `valid_codepoints()` check before insert. Fall back to Liberation. Never insert with a font that failed the check |
| pdf.js boxes and PyMuPDF boxes disagree by a few points | Fixture test with a known ReportLab string. 1 pt slack in verification. If a real-world PDF fails verification, return `422` rather than shipping a double image of the word |
| White fill on deletion shows on a colored page | UI copy for empty rewrites. Do not pretend the background was sampled in this plan |
| Replacement overlaps the next word | Warn from `measureText`. Do not move the following runs. Reflow is out of scope |
| Users edit in Place Fields because the tool looks similar | The editor stays on `/dashboard/documents/[id]/edit`. Place Fields does not gain a rewrite tool |
| PyMuPDF wheel size and startup | Import inside the rewrite function or the view, not at Django startup if startup time regresses. The dependency test still imports it |
| A Plan 1 overlay from an earlier save is what the user clicks | That is supported. It is ordinary text. The acceptance test covers it |
| Commit applies redaction after add-text and deletes the new box | `apply_text_session` order is rewrite, then add. Test `test_rewrite_then_add_text` |
| Sign & complete signs the unchanged file after a failed rewrite | The editor awaits the commit and stops on any error before calling self-sign (it already does this for add-text). Acceptance item 9 |
| Runs built from the previous file after Save changes | Rebuild runs when `onDocumentProxy` fires with a new proxy. Commit clears ops |

---

## 19. Definition of done

- A unique word in a draft PDF can be replaced. The downloaded file’s extracted text contains the new word and does not contain the old one.
- A character the embedded font cannot draw is replaced with Liberation, and the user is told.
- Add-text from Plan 1 still works on the same save and on a later save.
- A bad rectangle does not become the document’s `file_url`.
- Place Fields, pending-envelope lock, and the signing pipeline are unchanged.
- Scans and rotated pages have an explicit message and a safe path (add text, or refuse to open).

### Preview fonts

The editor previews replacement text in the PDF's own font where it can, falling back in this order:

1. **The embedded font.** `page_text_styles` adds a ninth element to each span: the xref of an embedded TrueType/OpenType program the browser can load (it must map at least one ASCII letter or digit, so subsets without a cmap, such as PyMuPDF's own, are skipped). `GET /api/documents/{id}/text-edits/fonts/{xref}/` returns the bytes (owner only, `Cache-Control: private`). The editor fetches a font only when a run that uses it is edited, registers it with `FontFace` for every weight (`weight: '1 1000'`) and turns `font-synthesis` off, so Arial Black isn't bolded twice. Letters missing from a subset fall back per character, as they do on save.
2. **The installed font by its real name.** `localFamilyNames` turns "Arial-Black" into `'Arial Black', 'Arial'` and "TimesNewRomanPS-BoldMT" into `'Times New Roman'`.
3. **Liberation**, the server's fallback.

The weight comes from the font name (`fontWeightFromName`: Thin 100 … Black/Heavy 900), or 700 when only the PDF's bold flag is set. Font ids belong to the session's file: a save renumbers xrefs, and the reopened session sends new ids.

### Borders and alignment (2026-11-19)

A replacement now stays inside the space its original text had, instead of running across borders and into the next column.

**What the server sends.** Opening a session adds `text_rules`: per page, `[0, x, y0, y1]` for vertical rules and `[1, y, x0, x1]` for horizontal ones, in user space (`page_rules` in `pdf_rewrite.py`). Lines, thin filled rectangles (how Word draws table borders) and the four edges of larger boxes count. Clip paths, white patches and page-sized backgrounds don't. About 20 ms per page.

**The slot** (`findRunFits`, `lib/pdf-edit/text-fit.ts`), worked out once per page when runs are built:
- **Ink edges.** Each run's left and right edges are the visible letters, without padding spaces (about a quarter em each).
- **Right limit.** The nearest vertical border crossing the line, less a 2 pt (or 0.2 em) pad. Without a border, the page's text margin. A word further along the same line, less a word gap, wins over both. Left limit likewise.
- **Never narrower than the original.**
- **Wrap floor.** The first text or horizontal rule below the line within the slot's width, or 36 pt above the page's bottom edge.
- **Alignment** by votes from nearby lines (within 12 lines) that aren't on the same line:
  - a shared left edge with a different right edge votes left;
  - a shared right edge with a different left edge votes right (figure columns);
  - a shared centre with different edges votes centre.
  - With no votes, a cell bordered on both sides decides from its gaps. Otherwise left.
- **Anchor.** The text is pinned at its start, middle or end. Shorter replacements of right-aligned figures stay right-aligned.

The op carries `fit: {left, right, bottom, align, anchor}`; `validate_fit` checks it (reason `invalid_fit`). Ops without `fit` (older drafts) draw as before.

**The policy** (`text_fit.py` and its TypeScript mirror; same tests on both sides):
1. Fits: one line at the original size.
2. Fits at 90% or more: shrunk.
3. Fits wrapped (greedy, by words, line height 1.2) above the floor: wrapped.
4. Fits at 75% or more: shrunk.
5. Otherwise one line at 75%, flagged. The editor outlines it in amber and the save warns `text_overflows`.

**Who measures.** The server measures with the font it draws with, so it decides. Before wrapping it checks that the lines below are still empty once the old text is gone, and falls back to steps 4–5 if not. The preview measures in the browser with the font the save will use:
- the PDF's embedded font when it has every letter typed (checked per character by measuring against two different fallbacks);
- otherwise the Liberation face the server substitutes.

A status line tells the user when text was shrunk ("Shrunk to 84% to fit."), wrapped, or doesn't fit.

**Known limits:**
- Words don't break inside themselves, so a long reference with no spaces can only shrink.
- Justified paragraph lines are treated as left-aligned.
- Wrapped lines don't push the text below them down.
