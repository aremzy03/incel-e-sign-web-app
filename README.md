## E-Sign Application (MVP)

A Django-based e-signature platform inspired by SignNow and DocuSign.

### Setup Instructions

1. Clone the repository
   - git clone <repo_url>
   - cd incel-e-sign-web-app

2. Install dependencies
   - pip install -r requirements.txt

3. Create a .env file with environment variables
   - DB_NAME, DB_USER, DB_PASS, SECRET_KEY, DEBUG

4. Run migrations
   - python manage.py migrate

5. Start the development server
   - python manage.py runserver

### Auth Service

JWT-based authentication endpoints:

- POST /auth/register/
- POST /auth/login/
- POST /auth/logout/
- GET /auth/profile/

### 📄 Document Handling

Complete document management system for uploading, retrieving, and deleting PDF documents.

#### Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/documents/upload/` | Upload PDF document | ✅ |
| `GET` | `/documents/` | List user's documents | ✅ |
| `GET` | `/documents/{id}/` | Retrieve single document | ✅ |
| `DELETE` | `/documents/{id}/delete/` | Delete document | ✅ |

#### 1. Upload Document

**Endpoint:** `POST /documents/upload/`

Upload a PDF document to the system.

**Request:**
```bash
curl -X POST http://localhost:8000/documents/upload/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@document.pdf"
```

**Request Details:**
- Content-Type: `multipart/form-data`
- Authentication: Required (JWT Bearer token)
- Body: Form data with key `file` containing PDF file

**Constraints:**
- File type: PDF only (`.pdf` extension required)
- File size: ≤ 20MB
- Authentication: Required

**Response (Success - 201):**
```json
{
  "success": true,
  "message": "Document uploaded successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "file_name": "contract.pdf",
    "file_url": "/media/documents/550e8400-e29b-41d4-a716-446655440000_contract.pdf",
    "file_size": 1024000,
    "status": "draft",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Invalid file type or size
- `401 Unauthorized`: Missing or invalid authentication
- `500 Internal Server Error`: Server error during upload

#### 2. List Documents

**Endpoint:** `GET /documents/`

Retrieve all documents owned by the authenticated user.

**Request:**
```bash
curl -X GET http://localhost:8000/documents/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "file_name": "contract.pdf",
    "file_url": "/media/documents/550e8400-e29b-41d4-a716-446655440000_contract.pdf",
    "file_size": 1024000,
    "status": "draft",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  },
  {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "file_name": "invoice.pdf",
    "file_url": "/media/documents/550e8400-e29b-41d4-a716-446655440001_invoice.pdf",
    "file_size": 512000,
    "status": "sent",
    "created_at": "2024-01-01T11:00:00Z",
    "updated_at": "2024-01-01T11:30:00Z"
  }
]
```

**Features:**
- Returns only documents owned by the authenticated user
- Ordered by creation date (newest first)
- Empty array if no documents exist

#### 3. Retrieve Single Document

**Endpoint:** `GET /documents/{id}/`

Get details of a specific document.

**Request:**
```bash
curl -X GET http://localhost:8000/documents/550e8400-e29b-41d4-a716-446655440000/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "file_name": "contract.pdf",
  "file_url": "/media/documents/550e8400-e29b-41d4-a716-446655440000_contract.pdf",
  "file_size": 1024000,
  "status": "draft",
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T12:00:00Z"
}
```

**Error Responses:**
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Document not found or user is not the owner

#### 4. Delete Document

**Endpoint:** `DELETE /documents/{id}/delete/`

Permanently delete a document.

**Request:**
```bash
curl -X DELETE http://localhost:8000/documents/550e8400-e29b-41d4-a716-446655440000/delete/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 204):**
```json
{
  "success": true,
  "message": "Document deleted successfully"
}
```

**Error Responses:**
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Document not found or user is not the owner
- `500 Internal Server Error`: Server error during deletion

**⚠️ Warning:** Deletion is permanent and cannot be undone.

#### Document Constraints

**File Type Restrictions:**
- Only PDF files are accepted
- File extension must be `.pdf`
- Content-Type should be `application/pdf`

**Size Limitations:**
- Maximum file size: 20MB
- Files larger than 20MB will be rejected with a 400 error

**Ownership & Access:**
- Users can only see and manage their own documents
- Attempting to access another user's document returns 404
- All operations require valid JWT authentication

**Document Status:**
- `draft`: Document is being prepared
- `sent`: Document has been sent for signing
- `completed`: Document has been fully signed
- `rejected`: Document was rejected

#### Testing Document Handling

**Run Document Tests:**
```bash
# Run all document-related tests
pytest documents/tests/ -v

# Run specific test categories
pytest documents/tests/test_models.py -v      # Model tests
pytest documents/tests/test_upload.py -v      # Upload functionality
pytest documents/tests/test_retrieval.py -v   # List and detail views
pytest documents/tests/test_deletion.py -v    # Delete functionality

# Run all tests
pytest -v
```

**Test Coverage:**
- ✅ **Upload Tests (8 tests):**
  - Successful PDF upload
  - File type validation (PDF only)
  - File size validation (≤20MB)
  - Authentication requirements
  - Multiple uploads by same user
  - Different users uploading independently
  - Empty file handling
  - Missing file data

- ✅ **Retrieval Tests (10 tests):**
  - List returns only user's documents
  - Proper ordering (newest first)
  - Detail view for document owner
  - 404 for non-owners
  - Authentication requirements
  - Empty document lists
  - Data isolation between users
  - Serializer field validation

- ✅ **Deletion Tests (9 tests):**
  - Owner can delete their documents
  - Document removal from database
  - 404 for non-owners
  - Authentication requirements
  - Multiple deletions by same user
  - Different users deleting independently
  - Response structure validation
  - Documents with different statuses

- ✅ **Model Tests (9 tests):**
  - Document creation with valid data
  - Status defaults to "draft"
  - Owner relationship validation
  - String representation
  - File size conversion
  - Status choices validation
  - Document ordering
  - Cascade delete behavior
  - Required fields validation

**Total Test Coverage:** 36 document-related tests covering all CRUD operations, security, and edge cases.


### Document Model

The Document model represents uploaded documents in the e-signature workflow:

**Fields:**
- `id` (UUIDField): Unique identifier for the document (primary key)
- `owner` (ForeignKey): User who owns this document (related_name="documents")
- `file_url` (CharField): File path or S3 URL where the document is stored
- `file_name` (CharField): Original name of the uploaded file (max_length=255)
- `file_size` (IntegerField): Size of the file in bytes
- `status` (CharField): Current status with choices:
  - `draft`: Document is being prepared
  - `sent`: Document has been sent for signing
  - `completed`: Document has been fully signed
  - `rejected`: Document was rejected
- `created_at` (DateTimeField): Timestamp when the document was created
- `updated_at` (DateTimeField): Timestamp when the document was last updated

**Features:**
- Automatic UUID generation for document IDs
- Cascade delete when owner is deleted
- Default status of "draft"
- File size conversion to MB via `file_size_mb` property
- Admin interface with filtering and search capabilities

### Envelope Model

The Envelope model manages the signing workflow for documents, defining the order of signers and tracking the signing process:

**Fields:**
- `id` (UUIDField): Unique identifier for the envelope (primary key)
- `document` (ForeignKey): The document being signed (related_name="envelopes")
- `creator` (ForeignKey): User who created the envelope (related_name="created_envelopes")
- `status` (CharField): Current status with choices:
  - `draft`: Envelope is being prepared
  - `sent`: Envelope has been sent to signers
  - `completed`: All signers have completed signing
  - `rejected`: Envelope was rejected
- `signing_order` (JSONField): Ordered list of signers with validation
- `created_at` (DateTimeField): Timestamp when the envelope was created
- `updated_at` (DateTimeField): Timestamp when the envelope was last updated

**Signing Order Format:**
```json
[
  {"signer_id": "550e8400-e29b-41d4-a716-446655440000", "order": 1},
  {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 2},
  {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 3}
]
```

**Signing Order Validation Rules:**
- Must be a list of dictionaries
- Each entry must have `signer_id` (valid UUID) and `order` (positive integer)
- Orders must start from 1 and be sequential (no gaps, no duplicates)
- `signer_id` values must correspond to existing users
- Empty list is valid (no signers assigned yet)

**Features:**
- Automatic UUID generation for envelope IDs
- Cascade delete when document or creator is deleted
- Default status of "draft"
- Comprehensive signing order validation
- Properties: `signer_count`, `is_completed`, `is_sent`
- Admin interface with filtering, search, and signer count display
- Ordered by creation date (newest first)

**Example Usage:**
```python
# Create an envelope with signing order
envelope = Envelope.objects.create(
    document=document,
    creator=user,
    signing_order=[
        {"signer_id": str(signer1.id), "order": 1},
        {"signer_id": str(signer2.id), "order": 2}
    ]
)

# Check properties
print(f"Signers: {envelope.signer_count}")
print(f"Is completed: {envelope.is_completed}")
print(f"Is sent: {envelope.is_sent}")
```

### 📮 Envelope Creation

Complete envelope management system for creating signing workflows around documents.

#### Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/envelopes/create/` | Create new envelope for document | ✅ |

#### 1. Create Envelope

**Endpoint:** `POST /envelopes/create/`

Create a new envelope for a document with specified signing order.

**Request:**
```bash
curl -X POST http://localhost:8000/envelopes/create/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ]
  }'
```

**Request Details:**
- Content-Type: `application/json`
- Authentication: Required (JWT Bearer token)
- Body: JSON with `document_id` and `signing_order`

**Payload Structure:**
```json
{
  "document_id": "uuid-of-document",
  "signing_order": [
    {"signer_id": "uuid-user-1", "order": 1},
    {"signer_id": "uuid-user-2", "order": 2}
  ]
}
```

**Constraints:**
- Document must exist and belong to the authenticated user
- Each `signer_id` must reference a valid user
- Orders must start at 1 and be unique (no duplicates, no gaps)
- Empty `signing_order` array is valid (no signers assigned yet)

**Response (Success - 201):**
```json
{
  "success": true,
  "message": "Envelope created successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "document": "550e8400-e29b-41d4-a716-446655440000",
    "document_file_name": "contract.pdf",
    "creator": "550e8400-e29b-41d4-a716-446655440004",
    "creator_email": "creator@example.com",
    "status": "draft",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ],
    "signer_count": 2,
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Validation errors (document not found, invalid signers, malformed signing order)
- `401 Unauthorized`: Missing or invalid authentication

**Validation Rules:**
- **Document Ownership**: You can only create envelopes for your own documents
- **Signer Validation**: All `signer_id` values must reference existing users
- **Order Validation**: Orders must start from 1 and be sequential (1, 2, 3, etc.)
- **No Duplicates**: No duplicate `signer_id` or `order` values allowed
- **UUID Format**: All IDs must be valid UUID format

**Example Error Responses:**

Document not owned by user:
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "document_id": ["You can only create envelopes for your own documents."]
  }
}
```

Invalid signing order:
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "signing_order": ["Orders must start from 1 and have no gaps."]
  }
}
```

Non-existent signer:
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "signing_order": ["Users not found: ['550e8400-e29b-41d4-a716-446655440999']"]
  }
}
```

#### Testing Envelope Creation

**Run Envelope Tests:**
```bash
# Run all envelope-related tests
pytest envelopes/tests/ -v

# Run specific test categories
pytest envelopes/tests/test_models.py -v      # Model tests
pytest envelopes/tests/test_creation.py -v    # Creation functionality

# Run all tests
pytest -v
```

**Test Coverage:**
- ✅ **Creation Tests (13 tests):**
  - Successful envelope creation with valid document and signers
  - Creation fails if document doesn't belong to creator
  - Creation fails if invalid user_id is in signing_order
  - Creation fails if signing_order has duplicate orders
  - Creation fails if signing_order has duplicate signer_ids
  - Creation fails if signing_order has gaps in order numbers
  - Creation fails if signing_order doesn't start from 1
  - Creation fails if signing_order missing required keys
  - Creation fails if signer_id invalid UUID format
  - Creation fails if order not positive integer
  - Creation succeeds with empty signing_order
  - Unauthenticated request returns 401
  - Creation fails if document not found

#### 2. Send Envelope

**Endpoint:** `POST /envelopes/{id}/send/`

Send an envelope to start the signing process (changes status from draft to sent).

**Request:**
```bash
curl -X POST http://localhost:8000/envelopes/550e8400-e29b-41d4-a716-446655440000/send/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{id}` - UUID of the envelope to send
- Body: None required

**Constraints:**
- Only the envelope creator can send the envelope
- Envelope must be in "draft" status
- Authentication required

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope sent successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "document": "550e8400-e29b-41d4-a716-446655440001",
    "creator": "550e8400-e29b-41d4-a716-446655440002",
    "status": "sent",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440003", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440004", "order": 2}
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Envelope is not in draft status
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: User is not the envelope creator
- `404 Not Found`: Envelope not found

#### 3. Reject Envelope

**Endpoint:** `POST /envelopes/{id}/reject/`

Reject an envelope (changes status to rejected).

**Request:**
```bash
curl -X POST http://localhost:8000/envelopes/550e8400-e29b-41d4-a716-446655440000/reject/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{id}` - UUID of the envelope to reject
- Body: None required

**Constraints:**
- Only the envelope creator can reject the envelope
- Can reject envelopes in any status
- Authentication required

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope rejected successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "document": "550e8400-e29b-41d4-a716-446655440001",
    "creator": "550e8400-e29b-41d4-a716-446655440002",
    "status": "rejected",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440003", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440004", "order": 2}
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: User is not the envelope creator
- `404 Not Found`: Envelope not found

**Example Error Responses:**

Non-creator attempting to send:
```json
{
  "success": false,
  "message": "You can only send envelopes you created."
}
```

Sending non-draft envelope:
```json
{
  "success": false,
  "message": "Only draft envelopes can be sent. Current status: sent"
}
```

#### Envelope Status Workflow

**Status Transitions:**
- `draft` → `sent` (via send endpoint)
- `draft` → `rejected` (via reject endpoint)
- `sent` → `rejected` (via reject endpoint)
- `completed` → `rejected` (via reject endpoint)

**Status Descriptions:**
- `draft`: Envelope is being prepared
- `sent`: Envelope has been sent to signers
- `completed`: All signers have completed signing
- `rejected`: Envelope was rejected by creator

#### Testing Envelope Send & Reject

**Run Envelope Send/Reject Tests:**
```bash
# Run all envelope-related tests
pytest envelopes/tests/ -v

# Run specific test categories
pytest envelopes/tests/test_models.py -v      # Model tests
pytest envelopes/tests/test_creation.py -v    # Creation functionality
pytest envelopes/tests/test_send_reject.py -v # Send/reject functionality

# Run all tests
pytest -v
```

**Test Coverage:**
- ✅ **Send/Reject Tests (16 tests):**
  - Creator can successfully send draft envelope
  - Sending changes status from draft → sent
  - Creator can successfully reject envelope
  - Rejecting changes status to rejected
  - Non-creator attempting send returns 403 Forbidden
  - Non-creator attempting reject returns 403 Forbidden
  - Sending non-draft envelope returns validation error
  - Sending completed envelope returns validation error
  - Sending rejected envelope returns validation error
  - Rejecting any status envelope succeeds
  - Rejecting completed envelope succeeds
  - Unauthenticated send request returns 401
  - Unauthenticated reject request returns 401
q### 📮 Retrieve Envelopes

Complete envelope retrieval system for listing and viewing envelope details with signature statuses.

#### Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/envelopes/` | List envelopes (for creators + signers) | ✅ |
| `GET` | `/envelopes/{id}/` | Retrieve full details of an envelope | ✅ |

#### 1. List Envelopes

**Endpoint:** `GET /envelopes/`

List all envelopes where the authenticated user is either the creator or a signer.

**Request:**
```bash
curl -X GET http://localhost:8000/envelopes/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: GET
- Authentication: Required (JWT Bearer token)
- Body: None required

**Access Control:**
- Returns envelopes created by the authenticated user
- Returns envelopes where the authenticated user is a signer
- Envelopes are ordered by creation date (newest first)

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelopes retrieved successfully",
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "document": "550e8400-e29b-41d4-a716-446655440001",
      "creator": "550e8400-e29b-41d4-a716-446655440002",
      "status": "sent",
      "signing_order": [
        {"signer_id": "550e8400-e29b-41d4-a716-446655440003", "order": 1},
        {"signer_id": "550e8400-e29b-41d4-a716-446655440004", "order": 2}
      ],
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:05:00Z",
      "signatures": [
        {
          "signer": "550e8400-e29b-41d4-a716-446655440003",
          "status": "signed",
          "signed_at": "2024-01-01T12:10:00Z"
        },
        {
          "signer": "550e8400-e29b-41d4-a716-446655440004",
          "status": "pending",
          "signed_at": null
        }
      ]
    }
  ]
}
```

#### 2. Retrieve Envelope Details

**Endpoint:** `GET /envelopes/{id}/`

Retrieve full details of a specific envelope including signature statuses.

**Request:**
```bash
curl -X GET http://localhost:8000/envelopes/550e8400-e29b-41d4-a716-446655440000/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: GET
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{id}` - UUID of the envelope to retrieve
- Body: None required

**Access Control:**
- Creator can view their envelope
- Signers can view envelopes they are assigned to
- Other users receive 404 (not found or access denied)

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope retrieved successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "document": "550e8400-e29b-41d4-a716-446655440001",
    "creator": "550e8400-e29b-41d4-a716-446655440002",
    "status": "sent",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440003", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440004", "order": 2}
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z",
    "signatures": [
      {
        "signer": "550e8400-e29b-41d4-a716-446655440003",
        "status": "signed",
        "signed_at": "2024-01-01T12:10:00Z"
      },
      {
        "signer": "550e8400-e29b-41d4-a716-446655440004",
        "status": "pending",
        "signed_at": null
      }
    ]
  }
}
```

**Response Fields:**
- `id`: Unique envelope identifier
- `document`: Document ID being signed
- `creator`: User ID who created the envelope
- `status`: Current envelope status (draft, sent, completed, rejected)
- `signing_order`: Ordered list of signers
- `created_at`: Envelope creation timestamp
- `updated_at`: Last update timestamp
- `signatures`: Array of signature objects with:
  - `signer`: User ID of the signer
  - `status`: Signature status (pending, signed, declined)
  - `signed_at`: Timestamp when signed (null if not signed)

**Error Responses:**

Unauthorized access (404):
```json
{
  "success": false,
  "message": "Envelope not found or access denied"
}
```

Unauthenticated request (401):
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**Constraints:**
- Authentication required for all requests
- Users can only access envelopes they created or are assigned to sign
- Envelopes are ordered by creation date (newest first)
- Signature data includes current status and timestamps

#### Testing Envelope Retrieval

**Run Envelope Retrieval Tests:**
```bash
# Run envelope retrieval tests
pytest envelopes/tests/test_retrieval.py -v

# Run all envelope tests
pytest envelopes/tests/ -v
```

**Test Coverage:**
- ✅ **Retrieval Tests (15 tests):**
  - Creator can list and view their envelopes
  - Signer can list and view envelopes assigned to them
  - User can list multiple envelopes (as creator and signer)
  - Other users cannot list unrelated envelopes
  - Unauthenticated request returns 401
  - Creator can view envelope detail with signatures
  - Signer can view envelope detail they are assigned to
  - Other user cannot view unrelated envelope (404)
  - Unauthenticated detail request returns 401
  - Nonexistent envelope returns 404
  - Envelope detail includes all required fields
  - Envelope list ordering (newest first)
  - Envelope with no signatures
  - Envelope with mixed signature statuses
  - Send nonexistent envelope returns 404
  - Reject nonexistent envelope returns 404
  - Send response contains correct data structure
  - Reject response contains correct data structure

### ✍️ Envelope & Signing Flow

Complete workflow system for document signing from envelope creation to final signature completion.

#### Complete Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/envelopes/create/` | Create envelope with document + signing_order | ✅ |
| `POST` | `/envelopes/{id}/send/` | Send envelope (creator only) | ✅ |
| `POST` | `/envelopes/{id}/reject/` | Reject envelope (creator only) | ✅ |
| `GET` | `/envelopes/` | List envelopes (for creators + signers) | ✅ |
| `GET` | `/envelopes/{id}/` | Retrieve full envelope details with signatures | ✅ |
| `POST` | `/signatures/{envelope_id}/sign/` | Current signer signs document | ✅ |
| `POST` | `/signatures/{envelope_id}/decline/` | Current signer declines (envelope rejected) | ✅ |

#### Envelope Lifecycle

```
Draft → Sent → Completed / Rejected
  ↓       ↓         ↓
Create   Send    All Signers
Envelope  to      Complete
         Signers  or Any
                  Declines
```

#### Signature Lifecycle

```
Pending → Signed / Declined
   ↓         ↓        ↓
Created   Document  Envelope
When      Signed    Rejected
Sent
```

#### 1. Create Envelope

**Endpoint:** `POST /envelopes/create/`

Create a new envelope for a document with specified signing order.

**Request:**
```bash
curl -X POST http://localhost:8000/envelopes/create/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ]
  }'
```

**Response (Success - 201):**
```json
{
  "success": true,
  "message": "Envelope created successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "document": "550e8400-e29b-41d4-a716-446655440000",
    "creator": "550e8400-e29b-41d4-a716-446655440004",
    "status": "draft",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  }
}
```

#### 2. Send Envelope

**Endpoint:** `POST /envelopes/{id}/send/`

Send an envelope to signers (creator only). Changes status from "draft" to "sent" and creates signature records.

**Request:**
```bash
curl -X POST http://localhost:8000/envelopes/550e8400-e29b-41d4-a716-446655440003/send/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope sent successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "status": "sent",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z",
    "signatures": [
      {
        "signer": "550e8400-e29b-41d4-a716-446655440001",
        "status": "pending",
        "signed_at": null
      },
      {
        "signer": "550e8400-e29b-41d4-a716-446655440002",
        "status": "pending",
        "signed_at": null
      }
    ]
  }
}
```

#### 3. Reject Envelope

**Endpoint:** `POST /envelopes/{id}/reject/`

Reject an envelope (creator only). Changes status to "rejected".

**Request:**
```bash
curl -X POST http://localhost:8000/envelopes/550e8400-e29b-41d4-a716-446655440003/reject/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope rejected successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "status": "rejected",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:10:00Z"
  }
}
```

#### 4. List Envelopes

**Endpoint:** `GET /envelopes/`

List all envelopes where the authenticated user is either the creator or a signer.

**Request:**
```bash
curl -X GET http://localhost:8000/envelopes/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelopes retrieved successfully",
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440003",
      "document": "550e8400-e29b-41d4-a716-446655440000",
      "creator": "550e8400-e29b-41d4-a716-446655440004",
      "status": "sent",
      "signing_order": [
        {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
        {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
      ],
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:05:00Z",
      "signatures": [
        {
          "signer": "550e8400-e29b-41d4-a716-446655440001",
          "status": "signed",
          "signed_at": "2024-01-01T12:10:00Z"
        },
        {
          "signer": "550e8400-e29b-41d4-a716-446655440002",
          "status": "pending",
          "signed_at": null
        }
      ]
    }
  ]
}
```

#### 5. Retrieve Envelope Details

**Endpoint:** `GET /envelopes/{id}/`

Retrieve full details of a specific envelope including signature statuses.

**Request:**
```bash
curl -X GET http://localhost:8000/envelopes/550e8400-e29b-41d4-a716-446655440003/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope retrieved successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "document": "550e8400-e29b-41d4-a716-446655440000",
    "creator": "550e8400-e29b-41d4-a716-446655440004",
    "status": "sent",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z",
    "signatures": [
      {
        "signer": "550e8400-e29b-41d4-a716-446655440001",
        "status": "signed",
        "signed_at": "2024-01-01T12:10:00Z"
      },
      {
        "signer": "550e8400-e29b-41d4-a716-446655440002",
        "status": "pending",
        "signed_at": null
      }
    ]
  }
}
```

#### 6. Sign Document

**Endpoint:** `POST /signatures/{envelope_id}/sign/`

Current signer signs the document. Only the current signer (next in sequence) can sign.

**Request:**
```bash
curl -X POST http://localhost:8000/signatures/550e8400-e29b-41d4-a716-446655440003/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
  }'
```

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Document signed successfully",
  "data": {
    "signature_id": "550e8400-e29b-41d4-a716-446655440005",
    "signer": "550e8400-e29b-41d4-a716-446655440001",
    "status": "signed",
    "signed_at": "2024-01-01T12:10:00Z",
    "envelope_status": "sent",
    "next_signer": "550e8400-e29b-41d4-a716-446655440002"
  }
}
```

#### 7. Decline Signature

**Endpoint:** `POST /signatures/{envelope_id}/decline/`

Current signer declines to sign. This immediately rejects the entire envelope.

**Request:**
```bash
curl -X POST http://localhost:8000/signatures/550e8400-e29b-41d4-a716-446655440003/decline/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Signature declined successfully",
  "data": {
    "signature_id": "550e8400-e29b-41d4-a716-446655440005",
    "signer": "550e8400-e29b-41d4-a716-446655440001",
    "status": "declined",
    "declined_at": "2024-01-01T12:10:00Z",
    "envelope_status": "rejected"
  }
}
```

#### Important Notes

**Sequential Signing:**
- Signatures must be completed in the order specified in `signing_order`
- Only the current signer (next in sequence) can perform signing actions
- Previous signers cannot modify their signatures once completed

**Access Control:**
- **Creator:** Can create, send, and reject envelopes they created
- **Signers:** Can view envelopes they're assigned to and sign when it's their turn
- **Other Users:** Cannot access unrelated envelopes (returns 404)

**Status Transitions:**
- **Envelope:** `draft` → `sent` → `completed` / `rejected`
- **Signature:** `pending` → `signed` / `declined`

**Automatic Actions:**
- When all signers complete: envelope status → `completed`
- When any signer declines: envelope status → `rejected`
- When creator rejects: envelope status → `rejected`

**Security Features:**
- JWT authentication required for all endpoints
- Users can only access envelopes they created or are assigned to sign
- Current signer validation prevents out-of-order signing
- Comprehensive input validation and error handling

#### Testing the Complete Workflow

**Run All Envelope & Signature Tests:**
```bash
# Run envelope tests
pytest envelopes/tests/ -v

# Run signature tests  
pytest signatures/tests/ -v

# Run specific test categories
pytest envelopes/tests/test_creation.py -v      # Envelope creation
pytest envelopes/tests/test_send_reject.py -v   # Send/reject functionality
pytest envelopes/tests/test_retrieval.py -v     # List/retrieve functionality
pytest signatures/tests/test_signatures.py -v   # Signing workflow
```

**Test Coverage:**
- ✅ **Envelope Creation & Management (29 tests):**
  - Creation, validation, send/reject functionality
  - Retrieval and listing with proper access control
  - Comprehensive error handling and security

- ✅ **Signature Workflow (19 tests):**
  - Sequential signing enforcement
  - Sign and decline functionality
  - Current signer validation
  - Envelope status transitions
  - Security and edge case testing

**Total Coverage:** 48 tests covering the complete envelope and signing workflow.

### ✍️ Signatures

Complete signature management system for sequential document signing workflow.

#### Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/signatures/{envelope_id}/sign/` | Sign a document in envelope | ✅ |
| `POST` | `/signatures/{envelope_id}/decline/` | Decline to sign document | ✅ |

#### 1. Sign Document

**Endpoint:** `POST /signatures/{envelope_id}/sign/`

Sign a document in the envelope (sequential signing workflow).

**Request:**
```bash
curl -X POST http://localhost:8000/signatures/550e8400-e29b-41d4-a716-446655440000/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
  }'
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{envelope_id}` - UUID of the envelope
- Body: JSON with `signature_image` (base64 encoded)

**Payload Structure:**
```json
{
  "signature_image": "base64-encoded-signature-data"
}
```

**Constraints:**
- Only the current signer (lowest pending order) can sign
- Envelope must be in "sent" status
- Signature image must be valid base64 encoded data
- Authentication required

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Document signed successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "signer": "550e8400-e29b-41d4-a716-446655440002",
    "signer_email": "signer1@example.com",
    "signer_name": "Test Signer 1",
    "status": "signed",
    "signing_order": 1,
    "signed_at": "2024-01-01T12:05:00Z",
    "signature_image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Invalid signature data, envelope not in sent status, already signed
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: Not current signer or not authorized
- `404 Not Found`: Envelope not found

#### 2. Decline Signature

**Endpoint:** `POST /signatures/{envelope_id}/decline/`

Decline to sign a document in the envelope (cancels entire envelope).

**Request:**
```bash
curl -X POST http://localhost:8000/signatures/550e8400-e29b-41d4-a716-446655440000/decline/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{envelope_id}` - UUID of the envelope
- Body: None required

**Constraints:**
- Only the current signer can decline
- Envelope must be in "sent" status
- Authentication required

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Document declined successfully. Envelope has been rejected.",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "signer": "550e8400-e29b-41d4-a716-446655440002",
    "signer_email": "signer1@example.com",
    "signer_name": "Test Signer 1",
    "status": "declined",
    "signing_order": 1,
    "signed_at": null,
    "signature_image": "",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Envelope not in sent status, already signed/declined
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: Not current signer or not authorized
- `404 Not Found`: Envelope not found

#### Sequential Signing Workflow

**Signing Order Logic:**
- Signers must sign in the order specified in the envelope's `signing_order`
- Only the current signer (lowest pending order) can act
- Signing moves to the next signer automatically
- Declining cancels the entire envelope (status → "rejected")

**Status Transitions:**
- `pending` → `signed` (via sign endpoint)
- `pending` → `declined` (via decline endpoint)
- When all signers sign: envelope status → `completed`
- When any signer declines: envelope status → `rejected`

**Example Workflow:**
1. Envelope created with 3 signers: [Signer1, Signer2, Signer3]
2. Envelope sent → Signature records created (all "pending")
3. Signer1 signs → Status: "signed", Signer2 becomes current
4. Signer2 signs → Status: "signed", Signer3 becomes current
5. Signer3 signs → Status: "signed", Envelope → "completed"

**Example Error Responses:**

Not current signer:
```json
{
  "success": false,
  "message": "It's not your turn to sign yet. Please wait for your turn."
}
```

Invalid signature data:
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "signature_image": ["Signature image must be valid base64 encoded data."]
  }
}
```

#### Testing Signatures

**Run Signature Tests:**
```bash
# Run all signature-related tests
pytest signatures/tests/ -v

# Run specific test categories
pytest signatures/tests/test_signatures.py -v  # Sign/decline functionality

# Run all tests
pytest -v
```

**Test Coverage:**
- ✅ **Signature Tests (19 tests):**
  - First signer can sign successfully
  - Signing unlocks the next signer
  - Final signer signing marks envelope completed
  - Signer can decline, marking envelope rejected
  - Non-current signer attempting sign returns 403
  - Non-current signer attempting decline returns 403
  - Unauthorized user attempting sign returns 403
  - Unauthorized user attempting decline returns 403
  - Unauthenticated sign request returns 401
  - Unauthenticated decline request returns 401
  - Signing draft envelope returns 400
  - Declining draft envelope returns 400
  - Signing already signed document returns 403 (not current signer)
  - Declining already signed document returns 403 (not current signer)
  - Signing with invalid signature image returns 400
  - Signing nonexistent envelope returns 404
  - Declining nonexistent envelope returns 404
  - Sign response contains correct data structure
  - Decline response contains correct data structure

### Document Handling Dependencies

Installed packages:
- django-storages
- boto3
- PyPDF2

Storage setup:
- Development: local file storage (default)
- Production: configure AWS S3 using `django-storages` (commented placeholders in `esign/settings.py`)

Environment variables (see `.env.example`):
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- AWS_STORAGE_BUCKET_NAME
- AWS_S3_REGION_NAME

### Testing & Validation

**Run All Tests:**
```bash
pytest
```

**Test Coverage Summary:**
- ✅ **Authentication & User Management (11 tests):**
  - User registration, login, logout, profile management
  - JWT token blacklist functionality
  - Authentication requirements and validation

- ✅ **Document Management (36 tests):**
  - Model creation and relationships (9 tests)
  - Upload functionality (8 tests)
  - Retrieval functionality (10 tests)
  - Deletion functionality (9 tests)

- ✅ **Envelope Management (47 tests):**
  - Model creation and relationships (9 tests)
  - Signing order validation (9 tests)
  - Envelope creation functionality (13 tests)
  - Envelope send/reject functionality (16 tests)
  - Status properties and cascade deletes
  - Comprehensive validation rules testing

- ✅ **Signature Management (19 tests):**
  - Sequential signing workflow (19 tests)
  - Sign and decline functionality
  - Current signer validation
  - Envelope status transitions
  - Comprehensive security and edge case testing

- ✅ **Dependencies & Integration (1 test):**
  - Document handling dependencies (django-storages, boto3, pypdf)

**Total Test Coverage:** 114 tests covering all core functionality, security, and edge cases.


