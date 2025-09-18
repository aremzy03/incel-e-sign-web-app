# E-Sign Application

A comprehensive Django-based e-signature platform inspired by SignNow and DocuSign, providing secure document signing workflows with sequential signing, notifications, and audit logging.

## 🚀 Project Overview

The E-Sign Application is a full-featured electronic signature platform that enables users to upload documents, create signing workflows, and manage the complete document signing process. Built with Django and Django REST Framework, it provides a robust API for document management, envelope creation, sequential signing, and comprehensive audit trails.

### Core Features

- **📄 Document Management**: Upload, store, and manage PDF documents with size and type validation
- **📮 Envelope System**: Create signing workflows with multiple signers and sequential signing order
- **✍️ Sequential Signing**: Enforce proper signing order with turn-based validation
- **🔔 Real-time Notifications**: In-app and email notifications powered by Celery background tasks
- **📋 Audit Logging**: Immutable audit trails for compliance and security
- **🖊️ Reusable Signatures**: Upload and manage multiple signature images for reuse
- **🔐 JWT Authentication**: Secure token-based authentication with refresh token support
- **⚡ Async Processing**: Background task processing with Celery and Redis

## 🛠️ Tech Stack

### Backend Framework
- **Django 5.2.6**: Web framework for rapid development
- **Django REST Framework**: Powerful API framework for building RESTful APIs
- **Django REST Framework SimpleJWT**: JWT authentication with token blacklisting

### Database & Storage
- **PostgreSQL**: Primary database for production
- **SQLite**: Used for testing (automatic fallback)
- **Django Storages**: File storage abstraction (local/S3 support)

### Task Queue & Caching
- **Celery**: Distributed task queue for background processing
- **Redis**: Message broker and result backend for Celery

### Authentication & Security
- **JWT (JSON Web Tokens)**: Stateless authentication
- **Token Blacklisting**: Secure token revocation
- **CORS Headers**: Cross-origin resource sharing support

### Testing & Development
- **Pytest**: Testing framework with Django integration
- **Pytest-Cov**: Code coverage reporting
- **Python Decouple**: Environment variable management

### Additional Libraries
- **PyPDF**: PDF document processing
- **Boto3**: AWS S3 integration (optional)
- **Django Allauth**: Authentication utilities

## 🚀 Setup Instructions

### Prerequisites
- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- Git

### 1. Clone Repository
```bash
git clone <repo-url>
cd incel-e-sign-web-app
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the project root:
```bash
cp .env.example .env  # If example exists, or create manually
```

Required environment variables:
```env
# Database Configuration
DB_NAME=esign_db
DB_USER=esign_user
DB_PASSWORD=esign_pass
DB_HOST=localhost
DB_PORT=5432

# Django Configuration
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# Redis Configuration (for Celery)
REDIS_URL=redis://localhost:6379/0

# Email Configuration (optional)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# AWS S3 Configuration (optional, for production)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=us-east-1
```

### 5. Database Setup
```bash
# Create PostgreSQL database
createdb esign_db

# Run migrations
python manage.py migrate
```

### 6. Start Services

#### Start Redis Server
```bash
redis-server
```

#### Start Celery Worker (in a new terminal)
```bash
celery -A esign worker -l info
```

#### Start Django Development Server
```bash
python manage.py runserver
```

The application will be available at `http://localhost:8000`

## 🧪 Running Tests

### Test Suite Overview
The application includes comprehensive test coverage with 114+ tests covering all core functionality, security, and edge cases.

### Running Tests
```bash
# Run all tests with coverage
pytest --cov

# Run tests with detailed coverage report
pytest --cov=. --cov-report=html --cov-report=term-missing

# Run specific test modules
pytest documents/tests/ -v
pytest envelopes/tests/ -v
pytest signatures/tests/ -v
pytest notifications/tests/ -v
pytest audit/tests/ -v

# Run integration tests
pytest tests/test_integration.py -v
```

### Test Coverage
- **Authentication & User Management**: 11 tests
- **Document Management**: 36 tests
- **Envelope Management**: 47 tests
- **Signature Management**: 19 tests
- **Notification System**: 21 tests
- **Audit Logging**: 23 tests
- **Integration Tests**: Complete workflow testing

### Coverage Goals
- **MVP**: ≥80% coverage
- **Production**: ≥90% coverage

## 🚀 Quickstart Walkthrough

Follow this step-by-step guide to test the complete e-signature workflow:

#### 1. Create a User
```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "full_name": "Test User",
    "password": "securepass123"
  }'
```

#### 2. Login and Get JWT Token
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepass123"
  }'
```
Save the `access` token from the response for the next steps.

#### 3. Upload a Document
```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@document.pdf"
```

#### 4. Create an Envelope
```bash
curl -X POST http://localhost:8000/api/envelopes/create/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "DOCUMENT_ID_FROM_STEP_3",
    "signing_order": [
      {"signer_id": "SIGNER_USER_ID", "order": 1}
    ]
  }'
```

#### 5. Send the Envelope
```bash
curl -X POST http://localhost:8000/api/envelopes/ENVELOPE_ID/send/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### 6. Sign the Document (as the signer)
```bash
# Option 1: Sign with inline signature image
curl -X POST http://localhost:8000/api/signatures/ENVELOPE_ID/sign/ \
  -H "Authorization: Bearer SIGNER_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
  }'

# Option 2: Sign with reusable signature ID
curl -X POST http://localhost:8000/api/signatures/ENVELOPE_ID/sign/ \
  -H "Authorization: Bearer SIGNER_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_id": "USER_SIGNATURE_UUID"
  }'

# Option 3: Sign with default signature (no parameters needed)
curl -X POST http://localhost:8000/api/signatures/ENVELOPE_ID/sign/ \
  -H "Authorization: Bearer SIGNER_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 📚 Features & API Overview

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/auth/register/` | User registration | ❌ |
| `POST` | `/api/auth/login/` | User login (JWT tokens) | ❌ |
| `POST` | `/api/auth/logout/` | User logout (blacklist token) | ✅ |
| `GET` | `/api/auth/profile/` | Get user profile | ✅ |

### Document Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/documents/upload/` | Upload PDF document (≤20MB) | ✅ |
| `GET` | `/api/documents/` | List user's documents | ✅ |
| `GET` | `/api/documents/{id}/` | Retrieve single document | ✅ |
| `DELETE` | `/api/documents/{id}/delete/` | Delete document | ✅ |

### Envelope Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/envelopes/create/` | Create envelope with signing order | ✅ |
| `POST` | `/api/envelopes/{id}/send/` | Send envelope to signers | ✅ |
| `POST` | `/api/envelopes/{id}/reject/` | Reject envelope | ✅ |
| `GET` | `/api/envelopes/` | List envelopes (creator + signer) | ✅ |
| `GET` | `/api/envelopes/{id}/` | Retrieve envelope details | ✅ |

### Signature Operations

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/signatures/{envelope_id}/sign/` | Sign document (sequential) | ✅ |
| `POST` | `/api/signatures/{envelope_id}/decline/` | Decline to sign | ✅ |

### Reusable Signatures

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/api/signatures/user/` | List user's signatures | ✅ |
| `POST` | `/api/signatures/user/` | Upload new signature | ✅ |
| `GET` | `/api/signatures/user/{id}/` | Get signature details | ✅ |
| `PATCH` | `/api/signatures/user/{id}/` | Update signature (set default) | ✅ |
| `DELETE` | `/api/signatures/user/{id}/` | Delete signature | ✅ |

### Notifications

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/api/notifications/` | List user notifications | ✅ |
| `PATCH` | `/api/notifications/{id}/read/` | Mark notification as read | ✅ |

### Audit Logs (Admin Only)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/api/audit/logs/` | List audit logs | ✅ (Admin) |
| `GET` | `/api/audit/logs/{id}/` | Get audit log details | ✅ (Admin) |

## 🔄 Workflow

### Document Signing Lifecycle

```
Draft → Sent → Completed / Rejected
  ↓       ↓         ↓
Create   Send    All Signers
Envelope  to      Complete
         Signers  or Any
                  Declines
```

### Sequential Signing Process

1. **Document Upload**: User uploads PDF document
2. **Envelope Creation**: Create envelope with signing order
3. **Envelope Sending**: Send to first signer in sequence
4. **Sequential Signing**: Each signer signs in order
5. **Completion**: All signers complete or any declines

### Signing Order Logic
- Signers must sign in the order specified in `signing_order`
- Only the current signer (lowest pending order) can act
- Signing moves to the next signer automatically
- Declining cancels the entire envelope

### Notification Flow
- **Envelope Sent**: Notifies first signer
- **Turn-based**: Notifies next signer when previous completes
- **Completion**: Notifies creator when all signers complete
- **Decline**: Notifies creator when any signer declines

### Audit Log Entries
Every significant action generates an immutable audit log:
- Document uploads/deletions
- Envelope creation/sending/rejection
- Document signing/declining
- User authentication events

## 🖊️ Reusable Signatures

### Features
- **Multiple Signatures**: Upload and manage multiple signature images
- **Default Signature**: Set one signature as default for automatic use
- **File Validation**: Size (≤1MB) and format (JPEG, PNG, GIF, BMP, WEBP) validation
- **User Isolation**: Users can only access their own signatures

### Usage in Document Signing
When signing documents, you can use signatures in three ways:

1. **Inline Signature**: Provide base64-encoded signature image
2. **Signature ID**: Reference a specific reusable signature
3. **Default Signature**: Use your default signature automatically

### Signature Priority Logic
1. Explicit `signature_image` (if provided)
2. Explicit `signature_id` (if provided)
3. Default signature (if user has one)
4. Error (if none available)

## 🧪 Testing & Integration

#### Running Tests
```bash
# Run all tests with coverage (targets ≥95% coverage)
pytest --cov

# Run tests with detailed coverage report
pytest --cov=. --cov-report=html --cov-report=term-missing

# Run specific test modules
pytest documents/tests/test_upload.py -v
pytest envelopes/tests/test_creation.py -v
pytest signatures/tests/test_signatures.py -v

# Run integration tests specifically
pytest tests/test_integration.py -v
```

#### Integration Tests
The comprehensive integration test suite (`tests/test_integration.py`) covers the complete signing lifecycle:

- **Happy Path Flow**: Full sequential signing workflow from document upload to completion
- **Decline Flow**: Signer declining to sign and proper notification handling
- **Creator Rejection**: Creator rejecting envelope before signing
- **Document Upload Edge Cases**: File size validation (≤20MB accepted, >20MB rejected)
- **Audit Log Immutability**: Regular users cannot modify/delete audit logs, admin access
- **User Registration & Authentication**: Complete auth flow testing
- **Notification System**: Verification of notifications during workflow

#### Coverage Report
The test suite includes comprehensive coverage with a target of ≥95%:

- **Document Tests**: Upload, retrieval, deletion, and model validation
- **Envelope Tests**: Creation, sending, rejection, and access control
- **Signature Tests**: Signing, declining, and turn-based validation
- **Integration Tests**: End-to-end workflow testing with notifications and audit logs
- **Edge Cases**: File size boundaries, non-sequential orders, permission violations

Coverage reports are generated in both terminal and HTML format:
- Terminal: `--cov-report=term-missing`
- HTML: `--cov-report=html` (opens `htmlcov/index.html`)

#### Test Categories
- **Unit Tests**: Individual component testing
- **Integration Tests**: Complete API workflow testing with database, notifications, and audit logs
- **Edge Case Tests**: Boundary conditions and error scenarios
- **Security Tests**: Authentication, authorization, and audit log immutability validation

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
  "status": "success",
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
  "status": "error",
  "message": "Validation failed",
  "data": {
    "document_id": ["You can only create envelopes for your own documents."]
  }
}
```

Invalid signing order:
```json
{
  "status": "error",
  "message": "Validation failed",
  "data": {
    "signing_order": ["Orders must start from 1 and have no gaps."]
  }
}
```

Non-existent signer:
```json
{
  "status": "error",
  "message": "Validation failed",
  "data": {
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
  "status": "error",
  "message": "You can only send envelopes you created."
}
```

Sending non-draft envelope:
```json
{
  "status": "error",
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
  "status": "error",
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
  "status": "error",
  "message": "It's not your turn to sign yet. Please wait for your turn."
}
```

Invalid signature data:
```json
{
  "status": "error",
  "message": "Validation failed",
  "data": {
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

### Asynchronous Tasks

The E-Sign application uses Celery with Redis for asynchronous task processing, enabling background operations for document processing, email notifications, and other time-consuming tasks.

#### Setup

**Dependencies:**
- `celery`: Distributed task queue
- `redis`: Message broker and result backend

**Installation:**
```bash
pip install celery redis
```

**Configuration:**
The Celery configuration is set in `esign/settings.py`:
```python
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
```

#### Running Celery

**Start Redis Server:**
```bash
redis-server
```

**Start Celery Worker:**
```bash
celery -A esign worker -l info
```

**Start Celery Beat Scheduler (Optional):**
```bash
celery -A esign beat -l info
```

#### Available Tasks

**Test Task:**
```python
from core.tasks import test_task

# Execute task asynchronously
result = test_task.delay()
print(result.get())  # "Task executed"
```

#### Testing Celery Tasks

Run Celery tests with eager execution:
```bash
pytest core/tests/test_celery.py -v
```

The test configuration uses `CELERY_TASK_ALWAYS_EAGER=True` to run tasks synchronously during testing.

### In-App Notifications

The E-Sign application includes a comprehensive in-app notification system that keeps users informed about envelope and signature status changes in real-time using Celery background tasks.

#### Features

- **Real-time Notifications**: Users receive instant notifications for envelope and signature events
- **User-specific**: Each user only sees their own notifications
- **Read Status Tracking**: Notifications can be marked as read/unread
- **Background Processing**: Notifications are created asynchronously using Celery
- **Comprehensive Coverage**: Notifications for all major workflow events

#### Endpoints

**List Notifications:**
```bash
GET /notifications/
```
Returns all notifications for the authenticated user, ordered by creation date (newest first).

**Response:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "message": "John Doe has requested you to sign the document 'contract.pdf'.",
    "is_read": false,
    "created_at": "2024-01-01T12:00:00Z"
  }
]
```

**Mark Notification as Read:**
```bash
PATCH /notifications/{id}/read/
```
Marks a specific notification as read for the authenticated user.

**Response:**
```json
{
  "success": true,
  "message": "Notification marked as read",
    "data": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "message": "John Doe has requested you to sign the document 'contract.pdf'.",
      "is_read": true,
      "created_at": "2024-01-01T12:00:00Z"
    }
}
```

#### Notification Triggers

The system automatically sends notifications for the following events with actor identity and document information:

**Envelope Events:**
- **Envelope Sent**: Notifies the first signer when an envelope is sent
  - Message: "[Creator Name] has requested you to sign the document '[File Name]'."
  - Example: "John Doe has requested you to sign the document 'contract.pdf'."

- **Envelope Rejected**: Notifies all signers when creator rejects an envelope
  - Message: "[Creator Name] has cancelled the envelope for '[File Name]'."
  - Example: "John Doe has cancelled the envelope for 'contract.pdf'."

**Signature Events:**
- **Document Signed (Next Signer)**: Notifies the next signer in sequence
  - Message: "It is now your turn to sign the document '[File Name]'."
  - Example: "It is now your turn to sign the document 'contract.pdf'."

- **Document Signed (Last Signer)**: Notifies creator that envelope is completed
  - Message: "Your envelope for '[File Name]' has been fully signed and completed."
  - Example: "Your envelope for 'contract.pdf' has been fully signed and completed."

- **Signature Declined**: Notifies the envelope creator
  - Message: "Signer [Signer Name] declined to sign the document '[File Name]'. The envelope has been rejected."
  - Example: "Signer Jane Smith declined to sign the document 'contract.pdf'. The envelope has been rejected."

#### Usage Examples

**List User Notifications:**
```bash
curl -X GET http://localhost:8000/notifications/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Mark Notification as Read:**
```bash
curl -X PATCH http://localhost:8000/notifications/550e8400-e29b-41d4-a716-446655440000/read/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Programmatic Notification Creation:**
```python
from notifications.utils import create_notification, create_envelope_sent_notification

# Create custom notification asynchronously
create_notification.delay(
    str(user.id),
    "Custom notification message"
)

# Create notification using template functions
envelope = Envelope.objects.get(id=envelope_id)
message = create_envelope_sent_notification(envelope)
create_notification.delay(str(signer.id), message)
```

#### Notification Model

The `Notification` model includes:
- `id`: Unique identifier (UUID)
- `user`: User who receives the notification (ForeignKey)
- `message`: Notification content (TextField)
- `is_read`: Read status (BooleanField, default=False)
- `created_at`: Creation timestamp (DateTimeField, auto_now_add=True)

#### Notification Template System

The notification system uses a unified template approach that ensures consistency between in-app and email notifications:

**Template Functions:**
- `create_envelope_sent_notification(envelope)` - For envelope sent notifications
- `create_signer_turn_notification(envelope)` - For signer turn notifications  
- `create_envelope_completed_notification(envelope)` - For envelope completion
- `create_signer_declined_notification(envelope, signer)` - For signature declines
- `create_envelope_rejected_notification(envelope)` - For envelope rejections

**Template Features:**
- **Actor Identity**: Always includes the relevant user's name (creator/signer)
- **Document Context**: Always includes the document file name
- **Consistent Formatting**: Standardized message structure across all notification types
- **Reusable**: Same templates can be used for both in-app and email notifications

#### Testing Notifications

Run notification tests:
```bash
pytest notifications/tests/test_notifications.py -v
```

Test coverage includes:
- ✅ **Model Tests (3 tests):**
  - Notification creation and validation
  - String representation
  - Ordering by creation date

- ✅ **Utility Tests (2 tests):**
  - Celery task execution
  - Error handling for invalid users

- ✅ **Template Tests (5 tests):**
  - Envelope sent notification template
  - Signer turn notification template
  - Envelope completed notification template
  - Signer declined notification template
  - Envelope rejected notification template

- ✅ **API Tests (6 tests):**
  - List notifications for authenticated users
  - Authentication requirements
  - User isolation (users only see their own notifications)
  - Mark notifications as read
  - Permission validation

- ✅ **Integration Tests (5 tests):**
  - Envelope send notifies first signer with creator name and file name
  - Envelope reject notifies all signers with creator name and file name
  - Signing notifies next signer with file name
  - Last signer signing notifies creator with file name
  - Declining notifies creator with signer name and file name

**Total Coverage:** 21 tests covering all notification functionality, templates, API endpoints, and workflow integration.

### 🔍 Audit Logging

The E-Sign application includes comprehensive audit logging to track all user actions and system events. This ensures compliance, security, and provides a complete audit trail for all document and signature operations.

#### Purpose and Features

The audit logging system provides:
- **Immutable Records**: All audit logs are read-only and cannot be modified or deleted
- **Complete Action Tracking**: Records all significant user actions and system events
- **IP and User Agent Logging**: Captures request metadata for security analysis
- **Admin-Only Access**: Audit logs are only accessible to administrators
- **Generic Target Support**: Can track actions on any model instance

#### Audit Log Fields

Each audit log entry contains:
- **`id`**: Unique UUID identifier
- **`actor`**: User who performed the action (null for system actions)
- **`action`**: Action type (e.g., "UPLOAD_DOC", "SEND_ENVELOPE", "SIGN_DOC")
- **`target_object`**: The model instance being acted upon
- **`message`**: Descriptive message about the action
- **`ip_address`**: IP address of the request (supports X-Forwarded-For)
- **`user_agent`**: Browser/client user agent string
- **`created_at`**: Timestamp when the action occurred

#### Tracked Actions

The system automatically logs the following actions:

1. **Document Operations:**
   - `UPLOAD_DOC`: When a user uploads a document
   - `DELETE_DOC`: When a user deletes a document

2. **Envelope Operations:**
   - `CREATE_ENVELOPE`: When a user creates an envelope
   - `SEND_ENVELOPE`: When a user sends an envelope for signing
   - `REJECT_ENVELOPE`: When a user rejects an envelope

3. **Signature Operations:**
   - `SIGN_DOC`: When a user signs a document
   - `DECLINE_SIGN`: When a user declines to sign a document

#### Sample Audit Log Entries

```
2024-01-15T10:30:45Z | Abdulmalik | UPLOAD_DOC
User Abdulmalik uploaded document 'Contract.pdf'.

2024-01-15T10:35:12Z | Fatima | SIGN_DOC  
User Fatima signed envelope #123 for document 'Agreement.pdf'.

2024-01-15T10:40:22Z | John Doe | DECLINE_SIGN
User John Doe declined to sign envelope #456 for document 'Proposal.pdf'.
```

#### Accessing Audit Logs

**Django Admin Interface:**
- Navigate to `/admin/` and login as an admin user
- Go to "Audit Logs" section
- View all audit entries in read-only format
- Search and filter by action, user, or date

**API Endpoints (Admin Only):**
- `GET /audit/logs/` - List all audit logs with search and filtering
- `GET /audit/logs/{id}/` - Retrieve specific audit log details

Example API usage:
```bash
# List audit logs (admin only)
curl -X GET http://localhost:8000/audit/logs/ \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"

# Search audit logs
curl -X GET "http://localhost:8000/audit/logs/?search=upload" \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"

# Get specific audit log
curl -X GET http://localhost:8000/audit/logs/{audit_log_id}/ \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"
```

#### Security and Immutability

- **Read-Only Design**: Audit logs cannot be modified or deleted through normal application flows
- **Admin Protection**: Only admin users can access audit logs via API or admin interface
- **Exception Handling**: Audit logging failures do not break user workflows
- **IP Tracking**: Captures both direct IP and X-Forwarded-For headers for proxy scenarios

#### Testing Audit Logging

Run audit logging tests:
```bash
pytest audit/tests/test_audit.py -v
```

Test coverage includes:
- ✅ **Model Tests (3 tests):**
  - Audit log creation and validation
  - String representation with and without actor
  - Generic foreign key relationships

- ✅ **Utility Tests (5 tests):**
  - log_action function creates entries correctly
  - Request metadata extraction (IP, user agent)
  - X-Forwarded-For header handling
  - Unauthenticated user handling
  - Exception handling and graceful failures

- ✅ **API Tests (4 tests):**
  - Admin-only access enforcement
  - Audit log list and detail views
  - Search functionality
  - Proper serialization of audit data

- ✅ **Integration Tests (7 tests):**
  - Document upload creates audit log
  - Document deletion creates audit log
  - Envelope creation creates audit log
  - Envelope send creates audit log
  - Envelope rejection creates audit log
  - Document signing creates audit log
  - Signature decline creates audit log

- ✅ **Admin Tests (4 tests):**
  - Read-only field enforcement
  - Add permission blocking
  - Change permission blocking
  - Delete permission blocking

**Total Coverage:** 23 tests covering all audit logging functionality, API endpoints, admin interface, and workflow integration.

#### Developer Usage

To add audit logging to new actions, use the `log_action` utility:

```python
from audit.utils import log_action

# Log a user action
log_action(
    actor=request.user,
    action="CUSTOM_ACTION",
    target=model_instance,
    message=f"User {request.user.get_full_name()} performed custom action on {model_instance}.",
    request=request  # Optional: for IP and user agent extraction
)
```

The audit logging system ensures complete traceability of all user actions while maintaining security and immutability of the audit trail.

## 🤝 Contributing

We welcome contributions to the E-Sign Application! Please follow these guidelines:

### Development Workflow
1. **Fork the repository** and create a feature branch
2. **Follow naming conventions**:
   - Branches: `feature/description`, `bugfix/description`, `chore/description`
   - Commits: Use conventional commit format (`feat:`, `fix:`, `docs:`, etc.)

### Coding Standards
- **Python**: Follow PEP 8, use snake_case for variables
- **Django**: Follow Django best practices and conventions
- **Tests**: Write tests for new features (aim for ≥90% coverage)
- **Documentation**: Update API docs and README for changes

### Code Review Process
- All code must pass peer review before merging
- Ensure all tests pass: `pytest --cov`
- Update documentation for API changes
- Follow the project's coding style guidelines

### Reporting Issues
- Use GitHub Issues for bug reports and feature requests
- Provide clear reproduction steps for bugs
- Include relevant logs and environment details

### Pull Request Guidelines
- Write clear, descriptive commit messages
- Include tests for new functionality
- Update documentation as needed
- Ensure CI/CD checks pass

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### MIT License Summary
- ✅ Commercial use allowed
- ✅ Modification allowed
- ✅ Distribution allowed
- ✅ Private use allowed
- ❌ No liability or warranty provided

---

## 📞 Support

For support and questions:
- Create an issue on GitHub
- Check the documentation above
- Review the test cases for usage examples

---

**Built with ❤️ using Django, Django REST Framework, and modern web technologies.**

### ✍️ Reusable Signatures

The E-Sign application supports reusable signatures, allowing users to upload and manage multiple signature images that can be reused across different documents. This feature enhances user experience by eliminating the need to create new signatures for each document.

#### Features

- **Multiple Signatures**: Users can upload one or more signature images
- **Default Signature**: Users can set one signature as their default
- **Automatic Fallback**: When signing documents, the system automatically uses the default signature if no specific signature is provided
- **Signature ID Support**: Users can specify which signature to use when signing documents
- **File Validation**: Signature images are validated for size (≤1MB) and format (JPEG, PNG, GIF, BMP, WEBP)
- **User Isolation**: Users can only access and manage their own signatures

#### Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/signatures/user/` | List user's signatures | ✅ |
| `POST` | `/signatures/user/` | Upload new signature | ✅ |
| `GET` | `/signatures/user/{id}/` | Get signature details | ✅ |
| `PATCH` | `/signatures/user/{id}/` | Update signature (e.g., set as default) | ✅ |
| `DELETE` | `/signatures/user/{id}/` | Delete signature | ✅ |

#### 1. List User Signatures

**Endpoint:** `GET /signatures/user/`

Retrieve all signatures owned by the authenticated user.

**Request:**
```bash
curl -X GET http://localhost:8000/signatures/user/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "image": "/media/user_signatures/signature1.png",
      "is_default": true,
      "created_at": "2024-01-01T12:00:00Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "image": "/media/user_signatures/signature2.png",
      "is_default": false,
      "created_at": "2024-01-01T11:00:00Z"
    }
  ]
}
```

#### 2. Upload New Signature

**Endpoint:** `POST /signatures/user/`

Upload a new signature image.

**Request:**
```bash
curl -X POST http://localhost:8000/signatures/user/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "image=@signature.png" \
  -F "is_default=true"
```

**Request Details:**
- Content-Type: `multipart/form-data`
- Authentication: Required (JWT Bearer token)
- Body: Form data with `image` file and optional `is_default` boolean

**Constraints:**
- File size: ≤ 1MB
- File formats: JPEG, JPG, PNG, GIF, BMP, WEBP
- Authentication: Required

**Response (Success - 201):**
```json
{
  "status": "success",
  "message": "Signature created successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "image": "/media/user_signatures/signature.png",
    "is_default": true,
    "created_at": "2024-01-01T12:00:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Invalid file type, size, or format
- `401 Unauthorized`: Missing or invalid authentication

#### 3. Get Signature Details

**Endpoint:** `GET /signatures/user/{id}/`

Retrieve details of a specific signature.

**Request:**
```bash
curl -X GET http://localhost:8000/signatures/user/550e8400-e29b-41d4-a716-446655440000/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "image": "/media/user_signatures/signature.png",
  "is_default": true,
  "created_at": "2024-01-01T12:00:00Z"
}
```

**Error Responses:**
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Signature not found or user is not the owner

#### 4. Update Signature

**Endpoint:** `PATCH /signatures/user/{id}/`

Update signature properties (e.g., set as default).

**Request:**
```bash
curl -X PATCH http://localhost:8000/signatures/user/550e8400-e29b-41d4-a716-446655440000/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "is_default": true
  }'
```

**Response (Success - 200):**
```json
{
  "status": "success",
  "message": "Signature updated successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "image": "/media/user_signatures/signature.png",
    "is_default": true,
    "created_at": "2024-01-01T12:00:00Z"
  }
}
```

**Note:** When setting a signature as default, all other signatures for the user are automatically set to non-default.

#### 5. Delete Signature

**Endpoint:** `DELETE /signatures/user/{id}/`

Delete a signature.

**Request:**
```bash
curl -X DELETE http://localhost:8000/signatures/user/550e8400-e29b-41d4-a716-446655440000/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 204):**
```json
{
  "status": "success",
  "message": "Signature deleted successfully"
}
```

**Error Responses:**
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Signature not found or user is not the owner

#### Using Reusable Signatures in Document Signing

The document signing endpoint now supports three ways to provide signatures:

**1. Inline Signature Image (Original Method):**
```bash
curl -X POST http://localhost:8000/signatures/ENVELOPE_ID/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
  }'
```

**2. Reusable Signature ID:**
```bash
curl -X POST http://localhost:8000/signatures/ENVELOPE_ID/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

**3. Default Signature (No Parameters):**
```bash
curl -X POST http://localhost:8000/signatures/ENVELOPE_ID/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### Signature Priority Logic

When signing documents, the system follows this priority order:

1. **Explicit signature_image**: If provided, use the inline signature
2. **Explicit signature_id**: If provided, use the specified UserSignature
3. **Default signature**: If user has a default signature, use it automatically
4. **Error**: If none of the above are available, return an error

#### Constraints and Validation

**File Upload Constraints:**
- Maximum file size: 1MB
- Allowed formats: JPEG, JPG, PNG, GIF, BMP, WEBP
- File must be a valid image

**Default Signature Constraints:**
- Only one signature can be default per user
- Setting a signature as default automatically unsets all others
- Users can have zero or one default signature

**Access Control:**
- Users can only access their own signatures
- Attempting to access another user's signature returns 404
- All operations require valid JWT authentication

#### Testing Reusable Signatures

**Run User Signature Tests:**
```bash
# Run all user signature tests
pytest signatures/tests/test_user_signatures.py -v

# Run all signature tests
pytest signatures/tests/ -v
```

**Test Coverage:**
- ✅ **Model Tests (3 tests):**
  - User signature creation and validation
  - Default signature constraint enforcement
  - String representation

- ✅ **Serializer Tests (2 tests):**
  - File size validation (≤1MB)
  - File format validation (image formats only)

- ✅ **API Tests (8 tests):**
  - Create user signature with authentication
  - List user signatures (user isolation)
  - Update signature (set as default)
  - Delete signature
  - Unauthorized access prevention
  - Cross-user access prevention

- ✅ **Document Signing Integration Tests (6 tests):**
  - Sign document with signature_id
  - Sign document with default signature
  - Sign document with no signature provided (error)
  - Sign document with invalid signature_id
  - Sign document with another user's signature_id
  - Sign document with both signature_image and signature_id (error)

**Total Coverage:** 19 tests covering all reusable signature functionality, API endpoints, and document signing integration.

#### User Signature Model

The `UserSignature` model includes:
- `id`: Unique identifier (UUID)
- `user`: User who owns this signature (ForeignKey)
- `image`: Signature image file (ImageField)
- `is_default`: Whether this is the user's default signature (BooleanField)
- `created_at`: Creation timestamp (DateTimeField, auto_now_add=True)

**Features:**
- Automatic UUID generation for signature IDs
- Cascade delete when user is deleted
- Database constraint ensuring only one default signature per user
- Model-level logic to automatically unset other defaults when setting a new default
- Indexes for efficient querying by user and default status

## Integration Tests for Reusable Signatures

The application includes comprehensive integration tests for the reusable signatures feature located in `tests/test_user_signatures_integration.py`. These tests validate the complete workflow of the UserSignature feature using Django REST Framework's APITestCase and APIClient.

### Test Coverage

The integration tests cover the following scenarios:

#### 1. Upload Reusable Signature (`UploadReusableSignatureTest`)
- **Success Case**: Upload signature with base64 image, verify it's saved and belongs to user, assert it appears in GET `/signatures/user/`
- **Unauthorized Access**: Test uploading without authentication (401 Unauthorized)
- **Invalid File Format**: Test uploading non-image files (400 Bad Request)

#### 2. Set Default Signature (`SetDefaultSignatureTest`)
- **Multiple Signatures**: Upload 2 signatures, set one as default
- **Single Default Constraint**: Assert only one signature can be default at a time
- **Default Switching**: Change default signature and verify previous default is unset

#### 3. Sign with Explicit Signature ID (`SignWithExplicitSignatureTest`)
- **Successful Signing**: Create envelope requiring signer, signer uploads reusable signature, signer signs using signature_id
- **Signature Record Creation**: Assert Signature record created with image copied from UserSignature
- **Invalid Signature ID**: Test signing with non-existent signature_id (400 Bad Request)
- **Other User's Signature**: Test signing with another user's signature_id (400 Bad Request)

#### 4. Sign with Auto-Default (`SignWithAutoDefaultTest`)
- **Auto-Default Usage**: Upload default signature, create envelope, sign without providing signature
- **Default Applied**: Assert default signature is used automatically
- **No Default Available**: Test signing with no signature provided and no default signature (400 Bad Request)

#### 5. Delete Reusable Signature (`DeleteReusableSignatureTest`)
- **Successful Deletion**: Upload signature, DELETE `/signatures/user/<id>/`, assert removed from database
- **Deletion Impact**: Attempt to sign with deleted signature_id → 400 Bad Request
- **Unauthorized Deletion**: Another user tries to delete your UserSignature → 404 Not Found

#### 6. Permission Enforcement (`PermissionEnforcementTest`)
- **Access Control**: Users can only access their own signatures
- **Cross-User Access**: Another user tries to GET or UPDATE your UserSignature → 404 Not Found
- **Data Isolation**: Verify users cannot see each other's signatures

#### 7. Complete Workflow Integration (`UserSignatureWorkflowIntegrationTest`)
- **End-to-End Flow**: Upload → set default → sign → delete
- **Multiple Signatures**: Upload multiple signatures, set one as default
- **Explicit vs Auto**: Sign using explicit signature_id, then sign using default
- **Deletion Verification**: Delete signature and verify it can't be used

#### 8. Edge Cases (`UserSignatureEdgeCasesTest`)
- **Conflicting Parameters**: Test signing with both signature_image and signature_id provided
- **Large File Upload**: Test uploading signature exceeding size limit
- **User Isolation**: Verify multiple users can have default signatures independently

### Test Setup and Fixtures

The tests use the following setup:
- **Test Users**: Creator and two signers with JWT authentication
- **Test Images**: Generated PNG images in different colors for signature testing
- **Test Documents**: PDF content for envelope creation
- **Mock Celery**: Celery tasks are mocked to avoid Redis dependency in tests

### Authentication and Authorization

All tests use JWT token authentication:
```python
self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
```

### Database Verification

Tests verify both API responses and database state:
- Signature records are created with correct status
- UserSignature records are properly associated with users
- Audit logs are created for all major actions
- Cascade deletions work correctly

### Running the Tests

```bash
# Run all user signature integration tests
python -m pytest tests/test_user_signatures_integration.py -v

# Run with coverage
python -m pytest tests/test_user_signatures_integration.py --cov=signatures --cov-report=term-missing

# Run specific test class
python -m pytest tests/test_user_signatures_integration.py::UploadReusableSignatureTest -v
```

### Test Validation

These integration tests ensure that:
- The reusable signature workflow functions correctly end-to-end
- Security and permission enforcement work as expected
- Database integrity is maintained throughout operations
- Error handling provides appropriate responses
- Audit trails are properly maintained


