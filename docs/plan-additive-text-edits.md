# Plan 1 — Additive text edits

Add new text onto a draft PDF. The original words, images, and drawing commands stay in the file. Nothing is deleted, covered, or rewritten.

This plan is the first editing feature. [Plan 2](plan-full-text-rewrite.md) is the later suite that replaces existing text. [pdf-editor-design.md](pdf-editor-design.md) is the product split this plan follows: prepare the file in a document editor, then tag signers in Place Fields.

**Date:** 2026-11-17

**Repos:**

| Layer | Path |
| --- | --- |
| API | `incel-e-sign-web-app` |
| UI | `incel-e-sign-web-app-front-end` |
| Sejda notes | [`incel-e-sign-web-app-front-end/sedja-references`](../../incel-e-sign-web-app-front-end/sedja-references/README.md) |

## Sejda notes this plan uses

Those notes describe sejda.com/pdf-editor from the outside. The browser draws the PDF and records edits. A server we cannot see writes the new file. This plan copies the browser half and the “send a list of operations” save. It does not copy Sejda’s server, task polling, or the tools that are not new text.

Read these before implementing. Paths are relative to this file.

| Note | Use it for |
| --- | --- |
| [README](../../incel-e-sign-web-app-front-end/sedja-references/README.md) | The split: pdf.js canvas plus HTML layers in the browser, one JSON task on Apply, server returns a new PDF |
| [01-architecture.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md) | Why the PDF is not modified until Apply (§1.2). `PdfEditorSettings.defaultText` is `Type your text` (§1.1). The operation collector and undo live in the browser (§1.3) |
| [03-rendering-with-pdfjs.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md) | Page stack (§3.2) and the CSS-pixel to PDF-point scale (§3.3). Sejda stores bottom-left PDF points. This plan stores top-left points to match `fields.Field`. The scale math is the same idea |
| [04-editing-tools.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md) | Add text only: §4.2. New text becomes `appendTextOperations`. Undo is a snapshot of the layers, not a PDF write (§4.12). Whiteout, shapes, images, and page tools in the rest of that file are out of this plan |
| [05-apply-changes-protocol.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md) | Save is one body that always contains the operation lists (§5.2). Their lists were empty in the capture, so the fields inside one text op are inferred (§5.2, “What one operation probably looks like”) |
| [06-limits-errors-recovery.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md) | 200 pages or 50 MB (§6.1). Leave-page guard and restore-unsaved-edits (§6.4) |
| [07-rebuild-blueprint.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) | Build order for a viewer, layers, and an add-text tool (§7.3 steps 1–5 and 9). Rule: store points, never screen pixels (§7.2). “Browser only” in §7.1 loses existing-text edit. This plan is that additive half, with our Django server as the writer instead of pdf-lib |
| [08-evidence-and-open-questions.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/08-evidence-and-open-questions.md) | What was seen versus guessed. Do not treat the sample `appendTextOperations` object in doc 5 as a schema we must match |

[02-upload-and-file-lifecycle.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/02-upload-and-file-lifecycle.md) is not a template. Sejda uploads to its own file id and deletes the file after two hours. This app already stores drafts at `staging/{document_id}.pdf` and keeps revisions. Use our document APIs.

---

## 1. What ships

A sender opens a draft document, types new text on top of the pages, moves and formats those boxes, and saves. Save produces a new PDF. The new file is what Place Fields, preview, download, and signing use after that.

While the sender is typing, the browser only changes HTML on top of a pdf.js canvas. The PDF bytes do not change until Save. That is the split in the [Sejda README](../../incel-e-sign-web-app-front-end/sedja-references/README.md) and [01-architecture.md §1.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md). New text there is `appendTextOperations` ([04-editing-tools.md §4.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md), [05-apply-changes-protocol.md §5.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md)). Sejda’s server is not available to us. This plan uses the writer this app already has: ReportLab drawing on a transparent page, merged once with pypdf. The operation list is ours (`add_text`), not a copy of their JSON.

The current writer is `embed_fields_single_pass` and `embed_text` in `signatures/utils/pdf_signing.py`. Signing already draws text with `drawString` and converts Y from the top of the page to PDF’s bottom-left origin. Plan 1 copies that drawing idea into a **document** service. It does not call the signing pipeline, and it does not loop `embed_text` once per box. One read of the source PDF, one overlay canvas per page, one write.

---

## 2. What this plan does not do

- Click an existing word and change it. The old glyphs stay selectable and searchable. That is Plan 2. Sejda’s version of that click is `editTextOperations` ([04-editing-tools.md §4.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)).
- Whiteout, redaction, highlight, shapes, ink, images, links, form fields, page delete, page rotate, page reorder. Sejda documents each of those in [04-editing-tools.md](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md) (§4.3–§4.11) and lists them on the task body in [05-apply-changes-protocol.md §5.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md). They can share this session later. They are not in the first slice. [07-rebuild-blueprint.md §7.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) is why whiteout is not in this slice: a white rectangle hides text and does not remove it.
- Editing inside the envelope wizard’s Place Fields step. That step stays signer tags (`Field` rows, `FIELD_TYPES` in `src/types/envelope.ts`).
- Editing a document that belongs to a pending envelope. Same rule as merge (`documents/views.py`, `EnvelopeDocument` with `envelope__status='pending'`).
- Overwriting `Document.file_url`’s object in place. Save writes a new storage key, then points the document at it.
- Using the browser as the PDF writer. No `pdf-lib` in the save path. A browser preview of the boxes is fine. The bytes the signer receives come from the server.
- Client-supplied PDF bytes as the save body. The client sends operations. The server opens the stored file and applies them.

---

## 3. User flow

### 3.1 Open

Entry points, both opening the same editor:

- Document library: **Edit text** on a draft row, beside download.
- Document detail (`src/app/dashboard/documents/[id]/page.tsx`): **Edit text** in the header, next to download.
- Envelope wizard step 1 (Documents): **Prepare PDF** on a draft that is not yet on a pending envelope. After save, the wizard’s `uploadedDocuments` entry uses the new `file_url` and `getDocumentViewerRevisionKey` so react-pdf reloads.

Route: `/dashboard/documents/[id]/edit`.

The page loads `GET /api/documents/{id}/`. If a saved edit session exists for this user and this `file_url`, the editor offers **Restore unsaved text**. Accepting loads that session’s operations. Dismissing leaves the session in the database but does not show the boxes (the user can restore again until they save or discard).

### 3.2 Edit

The page is the document viewer already used for read-only preview (`VerticalPDFViewer` with `editorLayout` and `readOnly` on the detail page), plus a text tool.

1. **Text** is the only tool. It is on when the page opens. Sejda also opens with the text tool active ([04-editing-tools.md §4.1](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)).
2. Click an empty part of a page. A box appears at the click, containing the placeholder `Type your text`. The placeholder is selected. Typing replaces it. The string is Sejda’s `PdfEditorSettings.defaultText` ([01-architecture.md §1.1](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md), [04-editing-tools.md §4.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)).
3. The box shows the real formatting: font, size, color, bold, italic, alignment. It is HTML over the canvas, not a second rendering of the PDF. Sejda’s stack puts that HTML on `textLayer`, above the canvas ([03-rendering-with-pdfjs.md §3.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). This plan has that one layer, not their image, form, annotation, draw, and guides layers.
4. Drag the box to move it. Drag the corner to resize the frame. Text wraps inside the frame. Sejda uses the same gesture ([04-editing-tools.md §4.1](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)).
5. A small toolbar on the selected box sets font, size, color, bold, italic, alignment, and delete. Sejda’s text menu is the model ([04-editing-tools.md §4.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)). Their font list is `/css/pdf-editor/fonts.css` ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). Ours is the three standard families in section 6.1.
6. Escape or click another empty spot deselects. Clicking empty space with the tool on creates another box. It does not edit PDF text underneath. Sejda’s text tool does edit existing words on that same click ([04-editing-tools.md §4.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md)). This plan does not. `renderTextLayer` stays off so the click cannot land on a PDF word.
7. Undo and redo walk a stack of session snapshots. Delete removes the box from the session. It does not touch the PDF. Sejda undoes by restoring an earlier layer snapshot because nothing has been written yet ([04-editing-tools.md §4.12](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md), [01-architecture.md §1.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md)).
8. Zoom uses the existing signing zoom constants (`SIGNING_ZOOM_MIN`, `SIGNING_ZOOM_MAX`, `SIGNING_ZOOM_STEP` in `signing-toolbar`). Box positions are stored in PDF points, so zoom only changes how the HTML is painted.

### 3.3 Save

**Save** is disabled when the session has no changes.

1. Client sends the operation list to `POST /api/documents/{id}/text-edits/commit/`. Sejda’s equivalent is one `POST /api/tasks` whose body always includes `appendTextOperations` ([05-apply-changes-protocol.md §5.1–§5.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md)). We do not poll a task id. Commit is the request that returns the new file.
2. Server checks guards, downloads the current file, draws every text box in one pass, uploads a new object, points `Document.file_url` at it, updates `file_size` and `updated_at`.
3. Response includes the new `file_url`, `file_size`, and a revision id.
4. Client clears the local operation list, invalidates the `['document', id]` query, and reloads the viewer. The words that were HTML are now part of the PDF. A second save with an empty list is a no-op. Sejda reloads by downloading the task result ([05-apply-changes-protocol.md §5.3–§5.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md)). We reload our document preview.

**Discard** deletes the open session and returns to the document page. The PDF is unchanged.

Closing the tab with unsaved boxes triggers `beforeunload`.

### 3.4 After save

Place Fields, self-sign, and signing read the new file. Signer tags (`fields.Field`) are not created by this editor. Text baked here is page content. It is not a signer field, so sign-time flatten will not draw it a second time.

If the document already has `Field` rows or the wizard is holding `fieldPositions` for it, save still succeeds **only when the page count and page size are unchanged**, which they are for this plan. Field coordinates stay valid because this plan does not rotate, delete, or resize pages. The client still refreshes the viewer revision key so the canvas shows the new bytes under the same tags.

---

## 4. Why the PDF is not rewritten

A PDF page is a content stream of drawing commands. Existing words are `Tj` / `TJ` operators inside `BT` … `ET`, usually in a subset font. Plan 1 never reads or edits that stream.

ReportLab builds a new one-page PDF the size of the target page, with text and nothing else. pypdf `merge_page` appends that page’s content on top of the original page. The original operators remain. Select-all in a reader still finds the original words. Search still finds them. The new words are additional text in the file.

That is the correct behavior for this plan, and it is the behavior to test. A test that expects the original word to disappear belongs to Plan 2, and it must fail against this writer. Sejda’s own whiteout warning is the same distinction: paint hides the word, it does not remove the operators ([04-editing-tools.md §4.7](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md), [07-rebuild-blueprint.md §7.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md)).

---

## 5. Coordinate contract

This is the contract Place Fields and signing already use. Do not invent another one.

Sejda’s rule is the one to copy for *when* to convert, not for *which corner is zero*. They store PDF points and convert from screen pixels with the page scale. They never store pixels ([03-rendering-with-pdfjs.md §3.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md), [07-rebuild-blueprint.md §7.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) rule 1). Their origin is the bottom-left of the page (`pdfY = pageHeight − cssY / scale`). Ours is the top-left, because `fields.Field.y` is already “points from the top edge.” The server subtracts from the page height once, in `apply_add_text`. Do not also store a bottom-left `y` in the session or the boxes will not match signer fields.

`fields.Field` stores:

- `page`: 1-based index into the file being edited.
- `x`: points from the left edge of the page.
- `y`: points from the **top** edge of the page.
- `width`, `height`: points.

Plan 1 stores the text frame the same way. The box origin is its top-left corner.

Conversion to ReportLab, which uses a bottom-left origin, happens once on the server, matching `embed_text` in `signatures/utils/pdf_signing.py`:

```
page_height = float(page.mediabox.height)
page_width = float(page.mediabox.width)
# y is the top of the text frame
baseline = page_height - y - (font_size * 0.8)
```

`0.8 * font_size` puts the baseline inside the frame so a 12 pt font in a ~16 pt frame sits optically where the HTML box sat. The HTML box uses the same ratio: the first baseline is `0.8 * fontSize` CSS pixels from the top of the box, after converting points to the page’s current CSS scale. If those two ratios differ, the saved PDF will not match the editor. Lock both to `0.8` and cover it with a visual fixture test (section 16).

Horizontal alignment is inside the frame:

- `left`: draw at `x`.
- `center`: draw at `x + (width - stringWidth) / 2`.
- `right`: draw at `x + width - stringWidth`.

Wrapping: split on `\n` first, then wrap each paragraph to `width` using ReportLab `stringWidth` and the same font and size. Line step is `font_size * 1.2`. Lines that fall below `y + height` are clipped, not drawn. The editor shows the same clip with `overflow: hidden` on the box so save matches the screen.

### 5.1 Browser conversion

On pointer up, convert CSS pixels inside the page element to points immediately. Store points. Never store screen pixels. That is [07-rebuild-blueprint.md §7.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) rule 1. Their measured example is an A4 page shown at `scale = 1300 / 595` ([03-rendering-with-pdfjs.md §3.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). Use the same ratio: rendered CSS width divided into the page width in points.

```
scaleX = pageWidthPt / pageCssWidth
scaleY = pageHeightPt / pageCssHeight
xPt = cssX * scaleX
yPt = cssY * scaleY
widthPt = cssWidth * scaleX
heightPt = cssHeight * scaleY
```

`pageWidthPt` and `pageHeightPt` come from the loaded pdf.js page (`viewport` at scale 1, or react-pdf’s page width/height divided by the render scale). They are the page’s real MediaBox size. Do not use `DEFAULT_PAGE_WIDTH_PT` (612) or `DEFAULT_PAGE_HEIGHT_PT` (792) from `src/lib/utils/field-geometry.ts`. Those constants exist for US Letter tagging and are wrong for A4 and for any other page size.

`pageCssWidth` and `pageCssHeight` are the rendered page element’s size, which already includes the viewer scale (`VerticalPDFViewer` uses `(editorLayout ? 1.2 : 1) * viewerScale`). Dividing by the element size absorbs that scale. Do not also divide by `1.2` or by `96/72`.

`field-geometry.ts` has repairs for boxes that were saved as viewport pixels and for boxes shrunk by a 72/96 factor (`maybeRepairShrunkViewportPosition`, `positionStoredAsPdfPoints`). The text editor must not send coordinates that need those repairs. Add a dedicated pair of functions, for example `pageCssBoxToPdfPoints` and `pdfPointsToPageCssBox`, that take the measured page size. Do not route text boxes through `viewportPositionToBackend`, which assumes the wizard’s 1.2 scale and a letter page.

Painting a stored box back onto the page:

```
left = xPt / scaleX
top = yPt / scaleY
width = widthPt / scaleX
height = heightPt / scaleY
```

### 5.2 Rotation

If `page.rotate` is not 0, the viewer’s width and height are swapped relative to the raw MediaBox, and a top-left CSS point is not the same point `merge_page` will use. Plan 1 refuses to open the editor for a document whose pages have a non-zero `/Rotate`, with the message: “This PDF’s pages are rotated. Rotate it upright before adding text.” Detect that on the server when the session is created (`PdfReader`, `page.rotation`) and return it on the session payload so the client can show the message without guessing.

Baking rotation to 0 is an organize feature in `pdf-editor-design.md` (Tier A). It is a prerequisite for rotated files, not part of this plan. Unrotated files, including scans that are stored upright, work. Sejda keeps a per-page `data-rotation` and refuses to rotate a page that already has edits, so every edit on a page uses one scale ([03-rendering-with-pdfjs.md §3.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). This plan goes further and refuses to open the editor at all when any page is rotated, because our signer coordinates are not rotation-aware. [07-rebuild-blueprint.md §7.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) is the reminder that a rotated page’s screen position has to be un-rotated before it is saved. We avoid that math by not editing those files yet.

### 5.3 Page identity

Every operation stores the 1-based page index in the file the session was opened against. This plan does not insert, delete, or reorder pages, so the index is stable from open to save. Sejda stores the original page number for the same reason, and applies deletions and reorders last ([04-editing-tools.md §4.11](../../incel-e-sign-web-app-front-end/sedja-references/docs/04-editing-tools.md), [07-rebuild-blueprint.md §7.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) rule 2). When this plan later gains page tools, keep that rule. Do not renumber `page` on existing text ops until after the text is drawn.

The session also stores `base_file_url`. Commit rejects the request if `Document.file_url` is no longer that URL (`409`). Someone else, or another tab, saved first. The client reloads and asks the user to redo the boxes on the new file. Sejda’s equivalent failure is an expired upload: the file id is gone and the edits have to be put on a new upload ([06-limits-errors-recovery.md §6.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md)). We do not expire the file after two hours. We do refuse to apply ops onto a different file than the one the session was opened against.

---

## 6. Session and operations

The session is the source of truth until Save. The PDF is not modified on each keystroke. Sejda’s operation collector works the same way: layers are marked added, modified, or deleted, and those marks become the task body only when the user applies ([01-architecture.md §1.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md), [05-apply-changes-protocol.md §5.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md)). Their captured body lists every operation array, empty when unused. We send one array, `ops`, and only the `add_text` variant in this plan.

### 6.1 Operation

```ts
interface AddTextOp {
  opId: string                 // client uuid, stable across autosave
  op: 'add_text'
  page: number                 // 1-based
  x: number                    // points, top-left of the frame
  y: number
  width: number
  height: number
  text: string                 // empty string deletes nothing; commit skips blank and the placeholder
  font: 'Helvetica' | 'Times-Roman' | 'Courier'
  fontSize: number             // points, 6–72
  color: string                // '#rrggbb'
  bold: boolean
  italic: boolean
  align: 'left' | 'center' | 'right'
}
```

Placeholder text `Type your text` is not committed. A box still showing the placeholder is dropped on save. A box with only whitespace is dropped.

Limits, enforced on the client and again on the server:

| Limit | Value |
| --- | --- |
| Text length per box | 2 000 characters |
| Boxes per document | 200 |
| Boxes per page | 50 |
| Font size | 6–72 |
| Frame must lie inside the page | `x >= 0`, `y >= 0`, `x + width <= page_width`, `y + height <= page_height`, with a 0.5 pt tolerance |
| Color | `#` plus 6 hex digits |

ReportLab built-in font names for the four styles:

| font | bold | italic | ReportLab name |
| --- | --- | --- | --- |
| Helvetica | false | false | Helvetica |
| Helvetica | true | false | Helvetica-Bold |
| Helvetica | false | true | Helvetica-Oblique |
| Helvetica | true | true | Helvetica-BoldOblique |
| Times-Roman | false | false | Times-Roman |
| Times-Roman | true | false | Times-Bold |
| Times-Roman | false | true | Times-Italic |
| Times-Roman | true | true | Times-BoldItalic |
| Courier | false | false | Courier |
| Courier | true | false | Courier-Bold |
| Courier | false | true | Courier-Oblique |
| Courier | true | true | Courier-BoldOblique |

These 12 fonts are the standard PDF set. They do not need to be embedded as files. They do not contain every Unicode character. The server rejects a box whose text contains a character those fonts cannot draw (code point above 255, or a WinAnsi gap) with `400` and `{ opId, reason: 'unsupported_character' }`. The client uses the same check before save: if a WinAnsi encode of the string throws, show “This font can’t draw one of the characters. Remove it or wait for the rewrite editor.” Plan 2 is where embedded Unicode fonts arrive. Do not silently substitute a different font in Plan 1. The screen and the file must use the same face.

Sejda does substitute. If the embedded font lacks a typed letter, the editor switches to a similar serif, sans, or mono face and says so ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md)). That behavior belongs to Plan 2, because it needs a font file we embed ourselves. Plan 1 has no such file. Rejecting the character is the honest version of their “original font replaced” warning until those files exist. They also refuse complex scripts ([03-rendering-with-pdfjs.md §3.5](../../incel-e-sign-web-app-front-end/sedja-references/docs/03-rendering-with-pdfjs.md), [06-limits-errors-recovery.md §6.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md)). The WinAnsi check covers that for this plan.

### 6.2 Database

New app models in `documents/models.py` (one migration):

```python
class DocumentEditSession(models.Model):
    id = UUIDField(primary_key=True, default=uuid4)
    document = ForeignKey(Document, related_name='edit_sessions', on_delete=CASCADE)
    owner = ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE)
    base_file_url = CharField(max_length=2048)
    ops = JSONField(default=list)          # list[AddTextOp]
    status = CharField(max_length=16, choices=[
        ('open', 'Open'),
        ('committed', 'Committed'),
        ('discarded', 'Discarded'),
    ], default='open')
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

class DocumentRevision(models.Model):
    id = UUIDField(primary_key=True, default=uuid4)
    document = ForeignKey(Document, related_name='revisions', on_delete=CASCADE)
    file_url = CharField(max_length=2048)
    file_size = IntegerField()
    source = CharField(max_length=32)      # 'upload' | 'add_text'
    session = ForeignKey(DocumentEditSession, null=True, on_delete=SET_NULL)
    created_at = DateTimeField(auto_now_add=True)
```

Indexes: `(document, status)`, `(document, created_at)`.

On the first session create for a document, if no revision exists, insert one `source='upload'` row pointing at the current `file_url`. That row is the pre-edit file. Do not delete it on later saves.

Only one `open` session per `(document, owner)`. Creating a session while one is open returns the open one.

`ops` is replaced wholesale on autosave. The client sends the full list. The server does not merge patches. That keeps autosave idempotent.

### 6.3 Undo

The undo stack lives in the browser only. Cap it at 50 snapshots. Each snapshot is the full `AddTextOp[]` plus the selected `opId`. Undo restores the previous array. Redo restores the next. A new edit after undo drops the redo branch.

Autosave writes the current array, not the undo history. After a refresh, Restore brings back the boxes, not the undo stack.

---

## 7. API

All routes require the document owner. Mount them in `documents/urls.py` next to preview and download.

### 7.1 `POST /api/documents/{id}/text-edits/`

Open or return the session.

Guards, in order, shared helper `assert_document_editable(document)` used by every route in this plan:

1. Caller is `document.owner`. Else `404` (do not reveal existence).
2. `document.status == 'draft'`. Else `409` `{ reason: 'not_draft' }`. Completed documents are not edited in place. A later copy-to-new-draft action can call this same writer. It is not in this plan.
3. No `EnvelopeDocument` for this document with `envelope.status == 'pending'`. Else `409` `{ reason: 'pending_envelope' }`. Copy the query from `MergeDocumentsView`.
4. Every page has `/Rotate == 0`. Else `409` `{ reason: 'rotated_pages', pages: [2, 5] }`.
5. File downloads and opens with pypdf. Else `422` `{ reason: 'unreadable_pdf' }`.
6. Page count `<= 200` and `file_size <= 50 * 1024 * 1024`. Else `413`. These match the ceilings recorded for Sejda and are enough to keep a synchronous commit acceptable for the first slice. Larger files wait for the job queue in section 12.

Response `200`:

```json
{
  "session_id": "uuid",
  "base_file_url": "…",
  "page_count": 3,
  "pages": [
    { "page": 1, "width": 612, "height": 792, "rotate": 0 }
  ],
  "ops": [],
  "updated_at": "2026-11-17T08:00:00Z"
}
```

`pages` is what the client uses as `pageWidthPt` / `pageHeightPt`. The client still measures the CSS box locally. It does not trust a hardcoded letter size.

### 7.2 `PUT /api/documents/{id}/text-edits/`

Replace `ops` on the open session. Body: `{ "ops": [ AddTextOp, … ] }`.

Validate every op (section 6.1) against the page sizes captured at session create. On failure, `400` with `{ errors: [{ opId, reason }] }` and do not write. On success, `200` with the stored session. Debounce the client at 1 second after the last change. Skip the request when the serialized ops are unchanged.

`409` `{ reason: 'base_changed' }` if `Document.file_url` differs from `session.base_file_url`.

### 7.3 `POST /api/documents/{id}/text-edits/commit/`

Body: `{ "ops": [ AddTextOp, … ] }`. The body is the list to apply, not “whatever is in the database.” The server stores it on the session, then applies it. That way a save that races an older autosave still writes what the user is looking at.

Empty list after dropping placeholders: `200` with the current document, no new file, session marked `committed`.

Otherwise:

1. Re-run guards.
2. Download `base_file_url` to a temp file (`documents/services/pdf_files.py` already has temp-file and S3 helpers).
3. `apply_add_text(source_path, dest_path, ops, page_sizes)`.
4. Upload the result with a new key: `edits/{document_id}/{session_id}.pdf`. Do not use `build_staging_key`, which is `staging/{document_id}.pdf` and would overwrite the original.
5. In one database transaction: insert `DocumentRevision` (`source='add_text'`), set `Document.file_url` and `file_size`, set session `status='committed'`.
6. If the database update fails after the upload, delete the new object (`delete_storage_url`) and leave `file_url` on the previous revision. Same pattern as `create_draft_document_from_local_pdf`.

Response `200`:

```json
{
  "document_id": "uuid",
  "file_url": "…",
  "file_size": 12345,
  "revision_id": "uuid",
  "session_id": "uuid"
}
```

Commit is synchronous for this plan. The request holds the worker for the duration of the merge. Section 12 says when to move it to Celery.

### 7.4 `DELETE /api/documents/{id}/text-edits/`

Mark the open session `discarded`. `204`. The PDF is not modified.

### 7.5 Client module

Add functions in `src/lib/api/documents.ts` next to `getDocument` and the merge helper:

- `openTextEditSession(id)`
- `saveTextEditSession(id, ops)`
- `commitTextEdits(id, ops)`
- `discardTextEditSession(id)`

Types live next to those functions, not in `src/types/envelope.ts`. Envelope field types and text-edit operations are different objects and must not be assigned to each other.

---

## 8. Server apply

New module: `documents/services/pdf_text.py`.

```python
def apply_add_text(source_path: str, dest_path: str, ops: list[dict]) -> None:
    """
    Read source_path once. For each page that has ops, build one ReportLab
    overlay the size of that page's MediaBox and merge it. Write dest_path.
    Does not modify source_path.
    """
```

Algorithm:

1. `PdfReader` on the source. `PdfWriter` for the output.
2. Group ops by 1-based page. Drop ops with blank text or text equal to `Type your text`.
3. For each page:
   - If the page has no ops, `writer.add_page(page)` and continue.
   - Read `media_box` width and height.
   - Build one `reportlab.pdfgen.canvas.Canvas` with `pagesize=(page_width, page_height)`.
   - For each op on that page, set the font name from the table in section 6.1, set fill color from the hex string, wrap the text, and `drawString` each visible line at the converted baseline.
   - `showPage` / `save` the overlay into a `BytesIO`.
   - `PdfReader` on that buffer, `page.merge_page(overlay_page)`, `writer.add_page(page)`.
4. Copy the document info and outline if pypdf’s `clone_reader_document_root` (or the equivalent already used by merge) preserves them more faithfully than adding pages one by one. Prefer the same page-copy helper merge uses, then merge the overlay onto the copied page, so form fields and annotations already in the file survive. Additive text must not strip AcroForm fields. Add a test that a PDF with one text field still has that field after commit.

Do not call `signatures.utils.pdf_signing.embed_text` in a loop. That function rewrites the whole file per stamp (`signing-pipeline-audit` GAP-07, called out again in `pdf-editor-design.md` section 11). A 40-box document would read and write the PDF 40 times and drop annotations depending on the writer flags.

Do not call `signatures.services.signing`. That path is for envelope fields and signature images. Mixing them would stamp signer values during document prep.

Color: parse `#rrggbb` into `reportlab.lib.colors.Color(r/255, g/255, b/255)`. Invalid color is a `400` before this function runs.

Text drawing uses `canvas.drawString`, not a form field and not a FreeText annotation. The result is page content. A later Plan 2 rewrite can see it with `getTextContent()` because it is real text. That is what we want: text added in Plan 1 can be rewritten in Plan 2 after save.

Encryption: if the PDF asks for an owner password to modify, refuse at session create with `409` `{ reason: 'encrypted' }`. Do not try passwords in this plan. The viewer already has a password dialog for opening (`usePdfPasswordDialog`). Opening and modifying are different permissions. If the user can preview but the file has a modify restriction, the editor shows the encrypted error from the session response.

---

## 9. Frontend structure

New route: `src/app/dashboard/documents/[id]/edit/page.tsx`.

It is a client page, same shell as the document detail page: header, zoom, page indicator, back link. It is not the envelope wizard and it does not render `FieldBox`.

### 9.1 Components

| Component | Responsibility |
| --- | --- |
| `src/app/dashboard/documents/[id]/edit/page.tsx` | Load document, open session, hold ops, wire save / discard / undo |
| `src/components/pdf-edit/text-edit-viewer.tsx` | Renders pages with react-pdf. Hosts the text layer. Reports page CSS size and PDF point size |
| `src/components/pdf-edit/text-box.tsx` | One absolutely positioned box. Drag, resize, `contentEditable`, toolbar |
| `src/components/pdf-edit/text-edit-toolbar.tsx` | Font, size, color, bold, italic, align, delete for the selected box |
| `src/components/pdf-edit/use-text-edit-session.ts` | Ops state, selection, undo stack, autosave debounce, dirty flag |
| `src/lib/pdf-edit/geometry.ts` | `pageCssBoxToPdfPoints`, `pdfPointsToPageCssBox`, frame clamp |
| `src/lib/pdf-edit/fonts.ts` | The 12-name table, WinAnsi check, default op factory |
| `src/lib/api/documents.ts` | The four API functions |

Reuse:

| Need | Use |
| --- | --- |
| PDF render | `react-pdf` `Document` and `Page`, worker setup from `src/lib/pdf-worker` (the detail page and `VerticalPDFViewer` already set `GlobalWorkerOptions.workerSrc`) |
| Auth and file URL | `getDocumentFileUrlForViewer`, `getPdfJsDocumentOptions`, `getDocumentViewerRevisionKey` from `src/lib/url.ts` |
| Zoom | `SIGNING_ZOOM_*` from `signing-toolbar` |
| Buttons, inputs | Existing `Button`, `Select`, `Input` |
| Loading and errors | `PdfLoadingIndicator`, `AsyncStatePanel`, `classifyError` |

Do not extend `VerticalPDFViewer` with a text-editing mode. That component is the tagging canvas: it takes `fieldPositions`, `onFieldDrop`, and `FieldBox`. A flag that sometimes draws signer fields and sometimes draws free text will put text ops into envelope payloads. The new viewer can copy the page loop, password dialog, and preview-fallback behavior. It should not import `FieldBox`.

`renderTextLayer` stays `false`. `renderAnnotationLayer` stays `false`. Plan 1 does not hit-test existing text. Turning the text layer on here would make clicks land on PDF words and fight the “click to add” gesture.

### 9.2 Page stack

For each page, one relatively positioned box the size of the rendered page:

```
div.page (position: relative, width/height = rendered CSS size)
  react-pdf Page (canvas)
  div.textLayer (position: absolute, inset: 0)
    TextBox… (position: absolute, left/top/width/height in CSS px)
```

The text layer receives the click that creates a box. Boxes stop propagation so a click inside a box does not create another one. Pointer events on the canvas itself are not required.

### 9.3 TextBox behavior

- `contentEditable` when selected. Placeholder `Type your text` is the initial `text` value and is rendered in a muted color until the user types, using a `data-placeholder` state rather than committing the placeholder as real text. On focus, if the value is still the placeholder, select all.
- Drag uses pointer events on a header strip or on the box border, not on the editable text, so selecting text does not move the box. `react-draggable` is already used by `FieldBox`. It is acceptable here. Store the result in points on drag stop, using the measured page size.
- Resize from the bottom-right corner. Minimum frame: 24 pt wide, `fontSize * 1.2` tall.
- Clamp the frame to the page on every move and resize.
- Toolbar floats above the box. Font is a select of Helvetica, Times Roman, Courier. Size is a number input 6–72. Color is a native color input. Bold, italic, and alignment are toggles.
- Delete removes the op from the session.
- The box paints with the chosen font via CSS. Map the three families to:

```css
Helvetica, Arial, sans-serif
'Times New Roman', Times, serif
'Courier New', Courier, monospace
```

The PDF uses the standard font, not the system font. The CSS list is only so the screen is close. The acceptance test for position is the baseline ratio, not pixel-identical glyphs. Say this in the toolbar as nothing. Do not promise “what you see is the embedded font” until Plan 2 subsets a real file.

### 9.4 Defaults for a new box

Click point is the top-left of the frame.

| Property | Default |
| --- | --- |
| text | empty, UI shows placeholder |
| font | Helvetica |
| fontSize | 12 |
| color | `#000000` |
| bold, italic | false |
| align | left |
| width | 180 pt, clamped to the remaining page width |
| height | 20 pt |

`opId` is `crypto.randomUUID()`.

### 9.5 Dirty state and reload

`dirty` is true when the current ops differ from the last successfully saved session ops (JSON stringify of the list sorted by `opId` is enough; also treat the list as dirty if autosave has not returned). The header Save button is primary when dirty. The document detail link and the wizard back action check `dirty` and confirm.

After commit, `queryClient.invalidateQueries({ queryKey: ['document', id] })`. The viewer `key` includes `getDocumentViewerRevisionKey` so react-pdf fetches the new bytes instead of a cached document.

---

## 10. How this meets signing

| Moment | What is in the PDF |
| --- | --- |
| Upload | Original file, `staging/{id}.pdf`, `DocumentRevision.source = 'upload'` |
| Text save | New object `edits/{id}/{session}.pdf`. Original object still stored. `Document.file_url` points at the new object |
| Place Fields | Tags stored as `Field` rows. They are not drawn yet |
| Sign | `embed_fields_single_pass` draws signature images and field text onto whatever `file_url` is current |

The words from this editor are already in the file before signing. Signing must not receive them as `text_stamps`. There is no code path that reads `DocumentEditSession` during sign. Committed sessions are history. Open sessions are ignored by signing because a pending envelope cannot be edited and a draft envelope has not started signing.

If a wizard has local `fieldPositions` for this document and the user saves text, keep those positions. Page index and page size did not change. Refresh the PDF bytes under them.

Self-sign (`self-sign-tools-sidebar.tsx`) is a different feature: signer tools placed and flattened at sign time. Do not add this editor’s text boxes to that sidebar. A user who wants words in the file before signing uses **Edit text**. A user who wants a signer to type uses a text field.

---

## 11. Autosave, recovery, leave guard

Sejda’s version of this section is [06-limits-errors-recovery.md §6.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md): `beforeunload` while edits are unsaved, a local snapshot restored with “Restore edits from session around {time}”, and `recoveryAutoSavingEnabled: false` so they do not write continuously. `PdfEditorSettings` turns recovery on ([01-architecture.md §1.1](../../incel-e-sign-web-app-front-end/sedja-references/docs/01-architecture.md)). We keep the leave guard and the restore prompt. We do autosave the op list to our API, because the session is already a database row and there is no two-hour file expiry to race. Their snapshot lives in the browser. Ours lives on the open `DocumentEditSession`.

- Autosave: `PUT` the full op list, 1 s after the last edit, only if dirty.
- `beforeunload` while dirty.
- On open, if `ops.length > 0` and `updated_at` is set, show “Restore unsaved text from {time}?” Stored images are not part of this plan, so the session JSON stays small. Sejda drops an image from the snapshot when it is too large to keep locally ([06-limits-errors-recovery.md §6.4](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md)). We have no images in this plan.
- If commit returns `base_changed`, show “This document was updated. Your text was not applied.” Keep the ops on screen. Do not autosave them onto the new file. The user copies text manually or discards. Automatic replay onto a changed file is Plan 2’s problem only if page geometry is still identical; for Plan 1, refusing is safer because the boxes may now sit on different content.
- Session left `open` for 7 days can be discarded by a cleanup command later. Not required to ship. Do not delete the PDF objects from this cleanup.

---

## 12. Synchronous commit and when to stop

Commit runs in the request. That matches merge, which also uses pypdf in the request.

Move commit to Celery when any of these is true in practice:

- Commit p95 over 10 seconds.
- Documents over 50 MB or 200 pages need editing (the cap currently rejects them).
- Workers time out behind the gateway.

The job shape is already described in `pdf-editor-design.md` section 9: `202` with `job_id`, poll, write the output to a job-scoped key, skip if that key exists (redelivery). Do not build the queue in the first slice. Do write `apply_add_text` as a pure function of `(source path, ops) → dest path` so a task can call it later without a rewrite.

---

## 13. Errors the UI must show

| Server reason | UI copy |
| --- | --- |
| `not_draft` | Only draft documents can be edited. |
| `pending_envelope` | This document is in an envelope that’s still out for signature. |
| `rotated_pages` | This PDF’s pages are rotated. Rotate it upright before adding text. |
| `encrypted` | This PDF is protected and can’t be edited. |
| `unreadable_pdf` | This file couldn’t be opened as a PDF. |
| `base_changed` | This document was updated. Your text was not applied. |
| `unsupported_character` | This font can’t draw one of the characters in a text box. |
| `413` | This document is too large to edit here (limit 200 pages or 50 MB). Sejda uses the same ceiling ([06-limits-errors-recovery.md §6.1](../../incel-e-sign-web-app-front-end/sedja-references/docs/06-limits-errors-recovery.md)). |
| Validation `errors[]` | Highlight the matching box and show the reason (off page, font size, empty). |

Network failures on autosave: keep the local ops, show a non-blocking “Couldn’t save draft” on the header, retry the next debounce. Network failure on commit: keep the ops, leave the session open, show the error on the Save button. Do not clear dirty state unless the response is `200`.

---

## 14. Build order

### Phase A — Apply function and tests

No UI.

1. Models and migration for `DocumentEditSession` and `DocumentRevision`.
2. `documents/services/pdf_text.py` with `apply_add_text`.
3. Tests in section 16 that do not need HTTP.

Exit: a unit test writes “Invoice” onto a ReportLab-generated PDF and pypdf’s extracted text contains both the original word and “Invoice”.

### Phase B — HTTP

1. Serializers for `AddTextOp`.
2. `assert_document_editable`.
3. The four routes.
4. API tests for each guard and for commit swapping `file_url` without deleting the previous object.

Exit: a draft PDF can be committed through the API and downloaded with the new text.

### Phase C — Editor UI

1. Geometry helpers and font table, with unit tests for a non-letter page (A4, 595 × 842 pt) at scale 1.2 and at zoom 1.5.
2. Route, viewer, text box, toolbar, undo, autosave, save, discard.
3. Entry buttons on the document detail page and the documents list. Wizard step 1 “Prepare PDF” can follow in the same phase if the wizard already has the document id. If wiring the wizard risks clearing `fieldPositions`, ship library and detail first.

Exit: the acceptance script in section 17 passes in the browser.

### Phase D — Hardening

1. Annotation-preservation test (AcroForm still present).
2. `beforeunload`, restore prompt, `base_changed` dialog.
3. Reject encrypted and rotated files in the UI from the session response, not only as a failed save.

---

## 15. Files to add or change

Backend, new:

- `documents/models.py` — two models
- `documents/migrations/0007_document_edit_session.py` (next number at implementation time)
- `documents/services/pdf_text.py`
- `documents/serializers_text_edit.py` (keep upload serializers untouched)
- `documents/tests/test_pdf_text.py`
- `documents/tests/test_text_edit_api.py`

Backend, change:

- `documents/urls.py` — four routes
- `documents/views.py` — or a new `documents/text_edit_views.py` included from `urls.py`. Prefer the new module so upload and preview views stay as they are.

Frontend, new:

- `src/app/dashboard/documents/[id]/edit/page.tsx`
- `src/components/pdf-edit/text-edit-viewer.tsx`
- `src/components/pdf-edit/text-box.tsx`
- `src/components/pdf-edit/text-edit-toolbar.tsx`
- `src/components/pdf-edit/use-text-edit-session.ts`
- `src/lib/pdf-edit/geometry.ts`
- `src/lib/pdf-edit/fonts.ts`
- `src/lib/pdf-edit/geometry.test.ts`

Frontend, change:

- `src/lib/api/documents.ts` — client functions
- `src/app/dashboard/documents/[id]/page.tsx` — Edit text button
- `src/app/dashboard/documents/page.tsx` — row action
- Wizard step 1 only after the editor works standalone

Do not change:

- `signatures/utils/pdf_signing.py`
- `signatures/services/signing.py`
- `src/types/envelope.ts` `FIELD_TYPES`
- `VerticalPDFViewer` props
- `FieldBox`

---

## 16. Tests

Backend, `documents/tests/test_pdf_text.py`:

| Test | Assert |
| --- | --- |
| `test_add_text_keeps_original_text` | Source contains `Hello`. After apply, extracted text contains `Hello` and the added word |
| `test_add_text_top_left_origin` | A box at `y=0` draws near the top of the page. Compare the text position from pypdf or a tiny content-stream read against `page_height - font_size` within 2 pt |
| `test_add_text_two_boxes_one_pass` | Two ops on one page, one op on another. Output page count unchanged. All three strings present. Source file bytes unchanged |
| `test_add_text_clips_overflow_line` | A second line whose baseline is below the frame is absent |
| `test_add_text_alignment_center` | Centered string’s x is within 1 pt of the frame center minus half the width |
| `test_add_text_preserves_acroform` | A one-field PDF still reports that field after apply |
| `test_placeholder_and_blank_skipped` | Ops with `""` and `Type your text` add no new text |

Backend, `documents/tests/test_text_edit_api.py`:

| Test | Assert |
| --- | --- |
| `test_commit_swaps_file_url_and_keeps_previous_object` | Revision row for the old URL exists. New URL is `edits/{id}/{session}.pdf`. Download of the old key still works |
| `test_commit_pending_envelope_rejected` | `409 pending_envelope` |
| `test_commit_non_draft_rejected` | `409 not_draft` |
| `test_commit_other_owner_404` | |
| `test_commit_rotated_page_rejected` | Build a page with `/Rotate 90` |
| `test_commit_base_changed` | Change `file_url` after session create. `409` |
| `test_commit_off_page_box_400` | Session ops unchanged |
| `test_commit_unsupported_character_400` | Text `Héllo` with Helvetica |
| `test_commit_empty_is_noop` | `file_url` unchanged, session committed |
| `test_autosave_replaces_ops` | Second PUT wins entirely |

Frontend, `src/lib/pdf-edit/geometry.test.ts`:

| Test | Assert |
| --- | --- |
| A4 at scale 1.2 | A CSS box in the top-left 100 × 20 px converts to points using 595 / cssWidth, not 612 |
| Zoom 1.5 then back | Round-trip CSS → points → CSS within 0.5 px |
| Clamp | A box dragged past the right edge stores `x + width == pageWidth` |

Manual browser script is section 17. Automated UI tests are useful for the geometry and for “Save calls commit with points.” A full drag test is optional.

---

## 17. Acceptance

On a draft, unrotated, unencrypted PDF:

1. Open **Edit text**. The pages render. No signer field palette is visible.
2. Click the page. A box appears with the placeholder. Type `Added in editor`. Set the font to Times, 16 pt, bold.
3. Drag the box. Reload the page. Restore. The box is back with the same words and place.
4. Save. The viewer reloads. The words are visible with no HTML box selected. Download the PDF. The words are in the file. The original words of the PDF are still in the file (select and search).
5. Open Place Fields on that document. The new words show as page content. Dropping a signature field does not duplicate the added words at sign time.
6. Put the document on a pending envelope. **Edit text** returns the pending-envelope error and does not open the canvas.
7. Undo before save removes the box and does not change the file.

---

## 18. Risks

| Risk | What to do |
| --- | --- |
| Boxes drift from the PDF after save | One baseline ratio, shared by CSS and ReportLab. Test `y=0` against the page height. Use measured page size, never 612 × 792 |
| Clicks meant to add text select PDF text | Keep `renderTextLayer={false}` |
| Text ops get stored as envelope fields | Separate types, separate route, do not import `FieldBox` |
| Commit strips existing form fields | Copy pages the way merge does, then `merge_page`. Test an AcroForm |
| Standard fonts reject normal punctuation or a name with an accent | Fail the op with `unsupported_character`. Do not swap in a random TTF in this plan |
| Two tabs save | `base_file_url` check. Second save gets `409` |
| User thinks white space over an old word deleted it | This plan has no whiteout tool. Empty space is empty space. The original text is still there. The UI does not call this “edit existing text” |
| Signing draws the new text again | Session ops are not `Field` rows. Sign code is not modified |

---

## 19. Handoff to Plan 2

Plan 2 starts from a committed Plan 1 file. Text added here is ordinary page text, so Plan 2’s `getTextContent()` pass will see it and can rewrite it.

Leave these seams, without implementing them now:

- `AddTextOp.op` is the string `'add_text'`. Later ops (`edit_text`, and anything else) are different `op` values in the same list. The Plan 1 validator rejects unknown `op` values. Sejda’s task is the same idea with one array per tool ([05-apply-changes-protocol.md §5.2](../../incel-e-sign-web-app-front-end/sedja-references/docs/05-apply-changes-protocol.md)). Their `appendTextOperations` is this plan. Their `editTextOperations` is Plan 2.
- `apply_add_text` only reads ops with `op == 'add_text'`. Plan 2 will run a rewrite pass **before** this function, on the same source file, then call this function for the remaining adds. Do not fold rewrite into ReportLab. [07-rebuild-blueprint.md §7.3](../../incel-e-sign-web-app-front-end/sedja-references/docs/07-rebuild-blueprint.md) step 10 is that rewrite, and it says to plan the most time for it. Step 9 is this plan’s save.
- The editor route stays `/dashboard/documents/[id]/edit`. Plan 2 adds a tool switch on that page. It does not add a second product surface.
- The session model’s `ops` JSON field has no schema constraint in the database. The schema lives in the serializer, which Plan 2 will extend.

Until Plan 2 ships, the editor copy should say **Add text**, not **Edit PDF**.
