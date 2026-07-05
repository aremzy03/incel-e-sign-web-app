# E-Sign Application

## 🚀 Project Overview

The E-Sign Application is a full-featured electronic signature platform that enables users to upload documents, create signing workflows, and manage the complete document signing process. Built with Django and Django REST Framework, it provides a robust API for document management, envelope creation, sequential signing, and comprehensive audit trails.

### Core Features

- **📄 Document Management**: Upload, store, and manage PDF documents (and Word files auto-converted to PDF) with size and type validation
- **📮 Envelope System**: Create signing workflows with multiple signers and sequential signing order
- **✍️ Sequential Signing**: Enforce proper signing order with turn-based validation
- **🔔 Real-time Notifications**: In-app and email notifications powered by Celery background tasks
- **👥 Contacts Management**: Save recipients, search by email, and invite non-users
- **📋 Audit Logging**: Immutable audit trails for compliance and security
- **🖊️ Reusable Signatures**: Upload and manage multiple signature images for reuse
- **🧩 Form Fields**: Backend support for initials, date, text, and designation fields (assign to signers, prefill by sender, flattened into final PDF)
- **🔒 Locked PDFs**: Completed envelopes automatically password-protect signed PDFs and surface the password to creators and recipients
- **📊 Dashboard**: Overview of signing activity (metrics, envelope counts, action-required list, recent activity)
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
- **ReportLab**: PDF canvas generation for overlays
- **Pillow**: Image handling for signature processing
- **dj-database-url**: Database URL configuration
- **django-redis**: Redis caching backend
- **sentry-sdk**: Error tracking and monitoring

## 🔒 Security & Production Features

### Security Enhancements

- **Security Headers**: Comprehensive HTTP security headers including HSTS, XSS protection, content type sniffing protection
- **HTTPS Enforcement**: Automatic SSL redirect and secure cookie settings in production
- **Rate Limiting**: Built-in throttling for API endpoints to prevent abuse
- **Input Validation**: Comprehensive input sanitization and validation
- **Secure Secret Management**: Environment-based configuration with validation warnings
- **IP Address Extraction**: Proper proxy header handling for accurate audit logging
- **CORS Configuration**: Environment-based CORS settings with strict production defaults

### Production Readiness

- **Comprehensive Logging**: Structured logging with file rotation, error tracking, and JSON formatting
- **Health Check Endpoints**: `/health/` and `/health/detailed/` for monitoring system status
- **Database Connection Pooling**: Optimized PostgreSQL connection management
- **Error Monitoring**: Sentry SDK integration for production error tracking
- **Environment-Based Configuration**: All sensitive settings configurable via environment variables
- **Static & Media Files**: Production-ready S3 storage support with local fallback

### Performance Optimizations

- **Query Optimization**: select_related and prefetch_related across all views to prevent N+1 queries
- **Database Indexing**: Optimized indexes on frequently queried fields
- **Redis Caching**: Configurable Redis caching backend with fallback support
- **Pagination**: Default pagination for all list views with configurable page sizes
- **Connection Pooling**: Persistent database connections for improved performance

## 🚀 Setup Instructions

### Prerequisites
- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- Git
- LibreOffice (for Word → PDF conversion)

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

Install LibreOffice (required for Word → PDF conversion):
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y libreoffice

# macOS (Homebrew)
brew install --cask libreoffice

# Fedora/RHEL
sudo dnf install -y libreoffice
```

### 4. Environment Configuration
Create a `.env` file in the project root:
```bash
cp .env.example .env  # If example exists, or create manually
```

Required environment variables:
```env
# Database Configuration
DATABASE_URL=postgresql://user:password@host:port/dbname
# OR use individual components:
DB_NAME=esign_db
DB_USER=esign_user
DB_PASSWORD=esign_pass
DB_HOST=localhost
DB_PORT=5432
DB_CONN_MAX_AGE=600  # Connection pool timeout (seconds)

# Django Configuration
SECRET_KEY=your-secret-key-here  # MUST be set in production
DEBUG=False  # MUST be False in production
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com  # Comma-separated list

# Security Headers (Production)
SECURE_SSL_REDIRECT=True  # Redirect HTTP to HTTPS
SECURE_HSTS_SECONDS=31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO, https  # If behind reverse proxy

# CORS Configuration
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com  # Comma-separated

# Redis Configuration (for Celery and Caching)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=django-db  # or redis://localhost:6379/1
CACHE_LOCATION=redis://127.0.0.1:6379/1
CACHE_TIMEOUT=300  # Cache timeout in seconds (default: 5 minutes)

# Static & Media Files
STATIC_URL=/static/
STATIC_ROOT=/path/to/staticfiles
MEDIA_URL=/media/
MEDIA_ROOT=/path/to/media

# Temporary local storage (used during signing even when USE_S3=True)
TEMP_UPLOAD_SUBDIR=temp_uploads
TEMP_SIGNED_SUBDIR=signed_docs

# AWS S3 Configuration (optional, for production)
USE_S3=True  # Set to True to enable S3 storage
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=us-east-1
AWS_S3_CUSTOM_DOMAIN=your-cdn-domain.com  # Optional CDN domain
AWS_LOCATION=incel-esign-app  # S3 key prefix for staging/signing/completed PDFs

# Async signing pipeline
SIGNING_CUTOVER_AT=2026-08-01T02:00:00+01:00  # ISO 8601; envelopes pending before this are frozen at sign (409)
MAX_MERGE_DOCUMENTS=10
GUNICORN_TIMEOUT=120
CELERY_WORKER_CONCURRENCY=4  # CapRover signing worker; queues: notifications,signing

# Email Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=no-reply@yourdomain.com
FRONTEND_BASE_URL=https://yourdomain.com

# Google OAuth (for "Continue with Google")
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret
# Next.js route that handles final login step after Django verifies Google
GOOGLE_OAUTH_REDIRECT_PATH=/auth/google/callback

# Rate Limiting (API Throttling)
THROTTLE_RATE_ANON=100/hour  # Anonymous users
THROTTLE_RATE_USER=1000/hour  # Authenticated users
THROTTLE_RATE_AUTH=10/minute  # Login/register endpoints
THROTTLE_RATE_UPLOAD=20/hour  # File upload endpoints

# Pagination
PAGE_SIZE=20  # Default items per page
MAX_PAGE_SIZE=100  # Maximum items per page

# Error Monitoring (Sentry)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id  # Optional
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1  # 10% of transactions
SENTRY_RELEASE=1.0.0  # Optional version tag
```

### 5. Database Setup
```bash
# Create PostgreSQL database (if using individual DB settings)
createdb esign_db

# Run migrations (includes new performance indexes for notifications and audit logs)
python manage.py migrate

# Verify migrations were applied
python manage.py showmigrations
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

### 7. Running with Docker (Production-style)

You can run the backend in a production-like setup using the provided `Dockerfile`.

#### Build the image

```bash
docker build -t esign-backend:latest .
```

#### Required environment variables

At minimum you should provide (for production-style runs):

- `SECRET_KEY`
- `DEBUG` (usually `False`)
- `ALLOWED_HOSTS`
- `DATABASE_URL` (or individual DB vars)
- `CELERY_BROKER_URL` (Redis URL)
- `CACHE_LOCATION` (Redis URL for Django cache)

You can either pass these with `-e` or keep them in a `.env` file (recommended).

Example `.env` snippet:

```env
SECRET_KEY=change-me
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://user:password@host:5432/esign_db
CELERY_BROKER_URL=redis://redis:6379/0
CACHE_LOCATION=redis://redis:6379/1
```

#### Run the web API (Gunicorn)

```bash
docker run --env-file .env -p 8000:8000 esign-backend:latest
```

The default container role is `web`, which starts:

```bash
gunicorn -c gunicorn_config.py esign.wsgi:application
```

Migrations are run automatically on startup when `SERVICE_ROLE` is `web`
and `RUN_MIGRATIONS_ON_START` is not explicitly set to `false`.

#### Run a Celery worker (using the same image)

Use the same image, but set the role to `worker`:

```bash
docker run --env-file .env \
  -e SERVICE_ROLE=worker \
  esign-backend:latest
```

This is equivalent to running:

```bash
celery -A esign worker -l info
```

By default, migrations are also attempted on worker startup, but you can
disable that with:

```bash
docker run --env-file .env \
  -e SERVICE_ROLE=worker \
  -e RUN_MIGRATIONS_ON_START=false \
  esign-backend:latest
```

> Note: The image includes LibreOffice, so Word → PDF uploads will work
> inside the container as long as the necessary environment variables
> (e.g. storage, DB, Redis) are configured correctly.

### 8. GitHub Actions CI/CD Pipeline

The project includes a comprehensive CI/CD workflow that automates testing, Docker image building, and deployment.

#### Workflow Overview

The GitHub Actions workflow (`.github/workflows/ci-cd.yml`) provides:

1. **Continuous Integration (CI)**: Runs on all pushes and pull requests
   - Executes pytest test suite with coverage reporting
   - Validates code quality before merging

2. **Continuous Deployment (CD)**: Runs on pushes to `main` branch
   - Builds production Docker image
   - Pushes image to GitHub Container Registry (GHCR)
   - Deploys to production server via SSH

#### Workflow Jobs

**Test Job** (runs on all triggers):
- Sets up Python 3.12 environment
- Installs dependencies from `requirements.txt`
- Runs `pytest` with coverage reporting
- Uploads coverage reports to Codecov (optional)

**Build & Push Job** (main branch only):
- Builds Docker image using the project's `Dockerfile`
- Tags image with `latest` and commit SHA
- Pushes to `ghcr.io/<username>/<repository>:latest`
- Uses Docker layer caching for faster builds

**Deploy Job** (main branch only, after successful build):
- Connects to deployment server via SSH
- Pulls latest image from GHCR
- Stops and removes existing container
- Starts new container with updated image
- Performs health check to verify deployment

#### Required GitHub Secrets

Configure the following secrets in your GitHub repository settings (`Settings` → `Secrets and variables` → `Actions`):

**Deployment Secrets:**
- `DEPLOY_HOST`: SSH hostname or IP address of your deployment server
- `DEPLOY_USER`: SSH username for the deployment server
- `DEPLOY_SSH_KEY`: Private SSH key for authentication (contents of `~/.ssh/id_rsa` or similar)
- `DEPLOY_PORT`: SSH port (optional, defaults to 22)

**Application Secrets:**
- `SECRET_KEY`: Django secret key for production
- `ALLOWED_HOSTS`: Comma-separated list of allowed hostnames
- `DATABASE_URL`: PostgreSQL connection string
- `CELERY_BROKER_URL`: Redis URL for Celery broker
- `CACHE_LOCATION`: Redis URL for Django cache

**Optional:**
- `GHCR_PAT`: GitHub Personal Access Token with `read:packages` permission (if `GITHUB_TOKEN` doesn't have sufficient permissions)

#### Setting Up SSH Key for Deployment

1. **Generate SSH key pair** (if you don't have one):
   ```bash
   ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions_deploy
   ```

2. **Copy public key to deployment server**:
   ```bash
   ssh-copy-id -i ~/.ssh/github_actions_deploy.pub user@your-server.com
   ```

3. **Add private key to GitHub Secrets**:
   - Copy the contents of `~/.ssh/github_actions_deploy` (private key)
   - Go to GitHub repository → Settings → Secrets → New repository secret
   - Name: `DEPLOY_SSH_KEY`
   - Value: Paste the entire private key (including `-----BEGIN` and `-----END` lines)

#### Workflow Triggers

The workflow automatically runs:
- **On every push to `main`**: Runs tests, builds image, and deploys
- **On pull requests to `main`**: Runs tests only (no deployment)

You can also manually trigger the workflow:
- Go to `Actions` tab → Select workflow → `Run workflow`

#### Viewing Workflow Results

1. Navigate to the `Actions` tab in your GitHub repository
2. Click on a workflow run to see detailed logs
3. Each job shows:
   - Test results and coverage
   - Docker build logs
   - Deployment status and health checks

#### Troubleshooting

**Tests failing:**
- Check that all dependencies are in `requirements.txt`
- Verify test database configuration
- Review test logs in the Actions tab

**Docker build failing:**
- Ensure `Dockerfile` is in the repository root
- Check that all required files are present (not in `.dockerignore`)
- Review build logs for specific errors

**Deployment failing:**
- Verify SSH key is correctly configured in secrets
- Check that deployment server is accessible
- Ensure Docker is installed on the deployment server
- Verify all required secrets are set (especially `SECRET_KEY`, `DATABASE_URL`)
- Check deployment logs for container startup errors

**Image pull failing:**
- Ensure repository has `packages: write` permission
- Verify `GITHUB_TOKEN` has sufficient permissions (or use `GHCR_PAT`)
- Check that image was successfully pushed in the build job

#### Customizing the Workflow

You can customize the workflow by editing `.github/workflows/ci-cd.yml`:

- **Change deployment target**: Modify the deploy job's SSH commands
- **Add additional test steps**: Add new steps in the test job
- **Modify image tags**: Update the metadata extraction step
- **Add notifications**: Integrate Slack, Discord, or email notifications

## 🚀 Production Deployment

### Pre-Deployment Checklist

1. **Environment Variables**
   - Set `DEBUG=False` in production
   - Set a strong, unique `SECRET_KEY`
   - Configure `ALLOWED_HOSTS` with your domain(s)
   - Set `DATABASE_URL` or individual DB settings for production database
   - Configure CORS origins appropriately
   - Set up email configuration
   - Configure Redis/Celery URLs

2. **Security Settings**
   - All security headers are automatically enabled when `DEBUG=False`
   - Ensure HTTPS is configured (SECURE_SSL_REDIRECT will enforce it)
   - Set up reverse proxy headers if behind load balancer
   - Configure rate limiting thresholds as needed

3. **Static & Media Files**
   - Run `python manage.py collectstatic` to collect static files
   - Configure web server (Nginx/Apache) or CDN for static files
   - Set up S3 or other cloud storage for media files in production

4. **Database**
   - Run all migrations: `python manage.py migrate`
   - Set up database backups
   - Configure connection pooling settings

5. **Monitoring**
   - Set up Sentry DSN for error tracking
   - Configure logging to appropriate handlers
   - Set up health check monitoring (use `/health/detailed/` endpoint)

6. **Performance**
   - Configure Redis for caching (recommended)
   - Set up Celery workers for background tasks
   - Review and adjust pagination settings
   - Monitor database query performance

### Production Server Setup

**Using Gunicorn:**
```bash
pip install gunicorn
gunicorn esign.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

**Using Docker (Example):**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
CMD ["gunicorn", "esign.wsgi:application", "--bind", "0.0.0.0:8000"]
```

### Collect Static Files
```bash
python manage.py collectstatic --noinput
```

### Deploying to Render

The application includes configuration files for easy deployment to Render:

1. **render.yaml**: Blueprint configuration for all services (web, database, Redis, Celery)
2. **build.sh**: Build script that runs during deployment
3. **gunicorn_config.py**: Production Gunicorn configuration
4. **Procfile**: Alternative service definition

#### Quick Deploy Steps:

1. Push your code to GitHub/GitLab
2. In Render Dashboard:
   - Click "New +" → "Blueprint"
   - Connect your repository
   - Render will detect `render.yaml` automatically
3. Configure environment variables in Render dashboard:
   - `ALLOWED_HOSTS`: Your Render app domain (e.g., `your-app.onrender.com`)
   - `CORS_ALLOWED_ORIGINS`: Your frontend URL(s)
   - `DATABASE_URL`: Auto-linked if using Render PostgreSQL
   - `CELERY_BROKER_URL`: Auto-linked if using Render Redis
   - `CACHE_LOCATION`: Auto-linked if using Render Redis
   - Email and other optional settings
4. Deploy: Render will automatically build and deploy

**Note**: Update `ALLOWED_HOSTS` in `render.yaml` with your actual Render domain before deploying.

#### Manual Service Setup (Alternative):

If not using Blueprint, create services manually:
- **PostgreSQL**: New → PostgreSQL
- **Redis**: New → Redis  
- **Web Service**: New → Web Service (use `build.sh` and gunicorn start command)
- **Background Worker**: New → Background Worker (for Celery)

### Logging

Logs are automatically configured and written to:
- `logs/django.log` - General application logs
- `logs/django_errors.log` - Error-level logs
- Console output for development

Log levels are automatically adjusted based on `DEBUG` setting.

### Rate Limiting

API endpoints are automatically rate-limited:
- **Anonymous users**: 100 requests/hour
- **Authenticated users**: 1000 requests/hour  
- **Auth endpoints** (login/register): 10 requests/minute
- **Upload endpoints**: 20 requests/hour

Adjust limits via environment variables if needed.

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
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": [
      "550e8400-e29b-41d4-a716-446655440000",
      "550e8400-e29b-41d4-a716-446655440005"
    ],
    "name": "My Important Contract Bundle",
    "description": "Please review all terms carefully before signing",
    "signing_order": [
      {
        "signer_id": "550e8400-e29b-41d4-a716-446655440001", 
        "order": 1
      },
      {
        "signer_id": "550e8400-e29b-41d4-a716-446655440002", 
        "order": 2
      }
    ],
    "documents_with_positions": [
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440000",
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}},
          {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "position": {"page": 1, "x": 150, "y": 350, "width": 200, "height": 50}}
        ]
      },
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440005",
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 2, "x": 100, "y": 200, "width": 180, "height": 40}}
        ]
      }
    ]
  }'
```

**Request Details:**
- Content-Type: `application/json`
- Authentication: Required (JWT Bearer token)
- Body: JSON with `document_ids` (list of document UUIDs), optional `name` (string), optional `description` (string), `signing_order` (list of signers), and optional `documents_with_positions` (list of document-specific signer positions).

**Payload Structure:**
```json
{
  "document_ids": ["uuid-of-document-1", "uuid-of-document-2"], // List of document UUIDs
  "name": "Optional custom envelope name", // Optional string
  "description": "Optional description or notes for recipients", // Optional string
  "signing_order": [
    {
      "signer_id": "uuid-user-1", 
      "order": 1
    },
    {
      "signer_id": "uuid-user-2", 
      "order": 2
    }
  ],
  "documents_with_positions": [
    {
      "document_id": "uuid-of-document-1", // Document to apply positions to
      "signer_document_positions": [ // List of signer positions for this specific document
        {"signer_id": "uuid-user-1", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}},
        {"signer_id": "uuid-user-2", "position": {"page": 1, "x": 150, "y": 350, "width": 200, "height": 50}}
      ]
    },
    {
      "document_id": "uuid-of-document-2",
      "signer_document_positions": [
        {"signer_id": "uuid-user-1", "position": {"page": 2, "x": 100, "y": 200, "width": 180, "height": 40}}
      ]
    }
  ]
}
```

**Constraints:**
- At least one `document_id` is required.
- Documents in `document_ids` must exist and belong to the authenticated user.
- Each `signer_id` in `signing_order` and `documents_with_positions` must reference a valid user.
- `signing_order` must be a list of dictionaries with valid `signer_id` and sequential `order` values (starting from 1, no gaps, no duplicates).
- `documents_with_positions` (if provided) must be a list of dictionaries.
- Each entry in `documents_with_positions` must have a `document_id` that is present in the main `document_ids` list.
- Each `signer_document_positions` entry must have a `signer_id` that is present in the main `signing_order`.
- Optional `position` field within `signer_document_positions` defines signature coordinates: `page` (positive integer), `x`, `y`, `width`, `height` (non-negative numbers, integers or floats). If omitted for a signer/document, default or request-provided coordinates will be used.
- If no custom `name` is provided, a default name like "Untitled Envelope - YYYY-MM-DD HH:MM" will be generated.

**Response (Success - 201):**
```json
{
  "success": true,
  "message": "Envelope created successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "creator": "550e8400-e29b-41d4-a716-446655440004",
    "creator_email": "creator@example.com",
    "name": "My Important Contract Bundle",
    "description": "Please review all terms carefully before signing",
    "status": "draft",
    "is_self_sign": false,
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ],
    "signer_count": 2,
    "pdf_lock_password": null,
    "documents": [
      {
        "id": "uuid-of-envelopedocument-1",
        "document": "550e8400-e29b-41d4-a716-446655440000",
        "order": 1,
        "document_file_name": "document1.pdf",
        "document_file_url": "/media/documents/document1.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}},
          {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "position": {"page": 1, "x": 150, "y": 350, "width": 200, "height": 50}}
        ]
      },
      {
        "id": "uuid-of-envelopedocument-2",
        "document": "550e8400-e29b-41d4-a716-446655440005",
        "order": 2,
        "document_file_name": "document2.pdf",
        "document_file_url": "/media/documents/document2.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 2, "x": 100, "y": 200, "width": 180, "height": 40}}
        ]
      }
    ],
    "signatures": [],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Validation errors (documents not found, invalid signers, malformed signing order, invalid document/signer positions, no documents provided).
- `401 Unauthorized`: Missing or invalid authentication.

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

**Response (202 Accepted):** Signing is asynchronous. Poll the job until `status` is `succeeded` or `failed`.

```json
{
  "status": "success",
  "message": "Signing job queued",
  "data": {
    "job_id": "uuid",
    "status": "queued",
    "envelope_id": "uuid"
  }
}
```

Poll job status:

```bash
curl -X GET http://localhost:8000/api/signatures/jobs/JOB_ID/ \
  -H "Authorization: Bearer SIGNER_ACCESS_TOKEN"
```

Retry a failed job (signer only):

```bash
curl -X POST http://localhost:8000/api/signatures/jobs/JOB_ID/retry/ \
  -H "Authorization: Bearer SIGNER_ACCESS_TOKEN"
```

**Cutover guard:** Envelopes that were `pending` before `SIGNING_CUTOVER_AT` return **409** with message *"Envelope frozen for system upgrade. Ask the creator to resend."*

## 📚 Features & API Overview

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/auth/register/` | User registration | ❌ |
| `POST` | `/api/auth/login/` | User login (JWT tokens) | ❌ |
| `POST` | `/api/auth/logout/` | User logout (blacklist token) | ✅ |
| `GET` | `/api/auth/profile/` | Get user profile | ✅ |
| `GET` | `/api/auth/profile/detail/` | Get user profile with shared envelopes | ✅ |
| `PATCH` | `/api/auth/profile/detail/` | Update own profile (name/photo) | ✅ |
| `GET` | `/api/auth/google/login/` | Start Google OAuth login flow (redirects to Google) | ❌ |
| `GET` | `/api/auth/google/callback/` | Google OAuth callback → issues JWT tokens, redirects to frontend | ❌ |
### Profile Detail Endpoint

Get a user's profile (including profile photo) and envelopes that involve both the authenticated user and the target user. Update your own profile with name and/or profile photo.

#### GET /api/auth/profile/detail/

- Returns the target user's profile and all envelopes where BOTH the requester and the target user participate (as creator or signer).
- If `user_id` is omitted, returns the requester's own profile and envelopes shared with self.

Request:
```bash
curl -X GET "http://localhost:8000/api/auth/profile/detail/?user_id=<TARGET_USER_UUID>" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Query parameters:
- `user_id` (optional, UUID): Target user's id. When omitted, defaults to the authenticated user.

Response (200):
```json
{
  "status": "success",
  "message": "Profile retrieved",
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "full_name": "User Name",
      "is_active": true,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-02T00:00:00Z",
      "profile_photo": null,
      "profile_photo_url": null
    },
    "envelopes_between_users": [
      {
        "id": "uuid",
        "creator": "uuid",
        "name": "Envelope Name",
        "status": "pending",
        "signing_order": [],
        "signer_count": 2,
        "documents": [],
        "signatures": [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
      }
    ]
  }
}
```

Errors:
- 401 Unauthorized: Missing/invalid token
- 404 Not Found: `user_id` does not exist or inactive

#### PATCH /api/auth/profile/detail/

- Update the authenticated user's own profile. Supports partial updates.
- Fields: `full_name` (string), `profile_photo` (file)

Request (multipart/form-data):
```bash
curl -X PATCH "http://localhost:8000/api/auth/profile/detail/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: multipart/form-data" \
  -F "full_name=New Name" \
  -F "profile_photo=@/path/to/photo.jpg"
```

Response (200):
```json
{
  "status": "success",
  "message": "Profile updated",
  "data": {
    "id": "uuid",
    "email": "you@example.com",
    "full_name": "New Name",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-02T00:00:00Z",
    "profile_photo": "profile_photos/filename.jpg",
    "profile_photo_url": "http://localhost:8000/media/profile_photos/filename.jpg"
  }
}
```

Notes:
- Ensure MEDIA_URL and MEDIA_ROOT are configured so `profile_photo_url` resolves correctly.
- Any authenticated user can GET this endpoint for any `user_id`; only the requester can PATCH.
| `GET` | `/api/auth/users/` | Search users by email/name | ✅ |

### Document Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/documents/upload/` | Upload PDF or Word document (≤20MB, Word auto-converted to PDF) | ✅ |
| `POST` | `/api/documents/merge/` | Merge multiple existing PDFs into one new Document | ✅ |
| `GET` | `/api/documents/` | List user's documents | ✅ |
| `GET` | `/api/documents/{id}/` | Retrieve single document | ✅ |
| `DELETE` | `/api/documents/{id}/delete/` | Delete document | ✅ |

### Envelope Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/envelopes/create/` | Create envelope with documents & signing order | ✅ |
| `POST` | `/api/envelopes/{id}/send/` | Send envelope to signers | ✅ |
| `POST` | `/api/envelopes/{id}/reject/` | Reject envelope | ✅ |
| `PATCH` | `/api/envelopes/{id}/edit/` | Edit draft or rejected envelope (creator only) | ✅ |
| `GET` | `/api/envelopes/` | List envelopes (creator + signer); optional `?is_self_sign=true\|false` | ✅ |
| `GET` | `/api/envelopes/{id}/` | Retrieve envelope details | ✅ |
| `GET` | `/api/envelopes/{id}/documents/` | Retrieve all documents of an envelope | ✅ |
| `DELETE` | `/api/envelopes/{id}/delete/` | Delete envelope (creator only) | ✅ |

### Signature Operations

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/signatures/self-sign/` | Self-sign document(s) in one call (returns **202** + `job_id`) | ✅ |
| `POST` | `/api/signatures/{envelope_id}/sign/` | Sign document (sequential, returns **202** + `job_id`) | ✅ |
| `GET` | `/api/signatures/jobs/{id}/` | Poll async signing job status | ✅ |
| `POST` | `/api/signatures/jobs/{id}/retry/` | Retry a failed signing job (signer only) | ✅ |
| `POST` | `/api/signatures/{envelope_id}/decline/` | Decline to sign | ✅ |

### Fields (Non-signature Annotations)

Backend-only APIs to manage non-signature fields: initials, date, text, designation. Senders can place and prefill fields and assign them to specific signers. During signing, assignees can submit values for their fields. On signing completion, the backend flattens field values into the PDF.

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/api/fields/{envelope_id}/` | List all fields for envelope (creator only) | ✅ |
| `POST` | `/api/fields/{envelope_id}/` | Bulk create/update fields (creator only) | ✅ |
| `GET` | `/api/fields/signing/{envelope_id}/` | List fields assigned to current signer | ✅ |
| `POST` | `/api/fields/signing/{envelope_id}/values/` | Bulk save signer field values | ✅ |

Field object shape (JSON):

```json
{
  "id": "uuid-optional-for-update",
  "envelope": "uuid",                
  "document": "uuid",                
  "page": 1,
  "x": 150,
  "y": 450,
  "width": 200,
  "height": 40,
  "type": "initials | date | text | designation",
  "assigned_signer": "uuid-of-user",
  "required": true,
  "prefill_value": "AC" ,            
  "value": null,                      
  "placeholder": "Enter text",
  "font_family": "Helvetica",
  "font_size": 12,
  "date_format": "YYYY-MM-DD",
  "max_length": 50
}
```

Notes:
- Coordinates are in PDF points; `y` is measured from the top (UI convention). Backend converts for stamping.
- If `prefill_value` is set, the signer cannot override it; otherwise, signer-provided `value` is used.
- Supported types stamped as text: `initials`, `date`, `text`, `designation`.

Examples

List envelope fields (creator):

```bash
curl -X GET http://localhost:8000/api/fields/ENVELOPE_ID/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Bulk upsert fields (creator):

```bash
curl -X POST http://localhost:8000/api/fields/ENVELOPE_ID/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"document":"DOC_UUID","page":1,"x":150,"y":450,"width":100,"height":24,"type":"initials","assigned_signer":"USER_UUID","required":true,"prefill_value":null,"font_family":"Helvetica","font_size":12},
    {"document":"DOC_UUID","page":1,"x":150,"y":500,"width":220,"height":24,"type":"text","assigned_signer":"USER_UUID","required":false,"placeholder":"Your company","max_length":60}
  ]'
```

List fields for signer:

```bash
curl -X GET http://localhost:8000/api/fields/signing/ENVELOPE_ID/ \
  -H "Authorization: Bearer SIGNER_ACCESS_TOKEN"
```

Submit signer values:

```bash
curl -X POST http://localhost:8000/api/fields/signing/ENVELOPE_ID/values/ \
  -H "Authorization: Bearer SIGNER_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"id":"FIELD_UUID_1","value":"AC"},
    {"id":"FIELD_UUID_2","value":"Senior Engineer"}
  ]'
```

Flattening behavior
- During `POST /api/signatures/{envelope_id}/sign/`, after embedding signatures, the backend stamps text for any assigned fields per document using `font_family`, `font_size`, and `date_format` where applicable.
- If both `prefill_value` and `value` are empty for a required field, you can enforce blocking completion; open an issue if you want strict enforcement enabled by default.

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

### Contacts

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/api/contacts/` | List user's saved contacts | ✅ |
| `POST` | `/api/contacts/search/` | Search by email; invite if not found | ✅ |
| `POST` | `/api/contacts/add/` | Add contact by email/name (links if user exists) | ✅ |
| `POST` | `/api/contacts/invite/` | Send invite email and store as invited | ✅ |

### Health Check & Monitoring

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/health/` | Basic health check | ❌ |
| `GET` | `/health/detailed/` | Detailed health check (database, cache, Celery) | ❌ |

**Health Check Endpoints:**

The application provides two health check endpoints for monitoring:

**Basic Health Check (`GET /health/`):**
```bash
curl http://localhost:8000/health/
```

**Response:**
```json
{
  "status": "healthy",
  "service": "e-sign-api"
}
```

**Detailed Health Check (`GET /health/detailed/`):**
```bash
curl http://localhost:8000/health/detailed/
```

**Response (200 - All healthy):**
```json
{
  "status": "healthy",
  "service": "e-sign-api",
  "checks": {
    "database": {
      "status": "healthy",
      "engine": "django.db.backends.postgresql"
    },
    "cache": {
      "status": "healthy",
      "backend": "django_redis.cache.RedisCache"
    },
    "celery": {
      "status": "healthy",
      "workers": 2
    }
  }
}
```

**Response (503 - Degraded):**
Returns status code 503 if any critical service (database) is unhealthy.

Use these endpoints for:
- Load balancer health checks
- Monitoring systems (Prometheus, Datadog, etc.)
- Kubernetes liveness/readiness probes

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
5. **Completion & PDF Locking**: When all signers finish, the system locks every signed PDF with a generated password (visible on the envelope detail view); any decline still halts the workflow

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
- GET /auth/users/ - Search users by email or full name

#### Google OAuth Login (Django backend + external frontend)

The E-Sign app supports logging in with Google using a separate frontend (e.g., Next.js) and this Django backend:

- **Backend flow**:
  - Frontend redirects browser to `GET /api/auth/google/login/?next=/desired/path`.
  - User is redirected to Google, approves access, and Google calls back `GET /api/auth/google/callback/`.
  - Backend exchanges the authorization code with Google, validates the `id_token`, and creates or fetches a `CustomUser` by verified email.
  - Backend issues **JWT access/refresh tokens** (via SimpleJWT) and redirects back to `FRONTEND_BASE_URL + GOOGLE_OAUTH_REDIRECT_PATH` with query params:
    - `status` (`success` or `error`)
    - `access` (JWT access token, when successful)
    - `refresh` (JWT refresh token, when successful)
    - `next` (original `next` path from the login URL)
    - `message` (optional error info)

- **Frontend responsibilities (e.g., Next.js)**:
  - Provide a “Continue with Google” button that sends the user to `/api/auth/google/login/`.
  - Implement a route matching `GOOGLE_OAUTH_REDIRECT_PATH` (e.g., `/auth/google/callback`) to:
    - Read `access`/`refresh` from the query string when `status=success`.
    - Store tokens (e.g., in localStorage or via an API route into HttpOnly cookies).
    - Redirect the user to the `next` path or a default dashboard.
  - Attach the `access` token as `Authorization: Bearer <token>` for all API requests to this Django backend (same as email/password login).

#### User Search Endpoint

**GET /api/auth/users/?search=query&page_size=10**

Search for users by email address or full name with pagination support.

**Request Details:**
- Method: GET
- Authentication: Required (JWT Bearer token)
- Query Parameters:
  - `search` (optional): Search query for email or full name
  - `page_size` (optional): Number of results per page (default: 10, max: 100)

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/auth/users/?search=user@example.com&page_size=10" \
  -H "Authorization: Bearer <your-jwt-token>"
```

**Response (Success - 200):**
```json
{
  "status": "success",
  "message": "Users retrieved successfully",
  "data": {
    "count": 2,
    "next": null,
    "previous": null,
    "results": [
      {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "email": "user@example.com",
        "full_name": "John Doe",
        "is_active": true,
        "created_at": "2024-01-15T10:30:00Z"
      },
      {
        "id": "987fcdeb-51a2-43d1-b789-123456789abc",
        "email": "another.user@example.com",
        "full_name": "Jane Smith",
        "is_active": true,
        "created_at": "2024-01-14T15:45:00Z"
      }
    ]
  }
}
```

**Features:**
- **Case-insensitive search**: Searches both email and full_name fields
- **Pagination**: Configurable page size with next/previous links
- **Active users only**: Returns only active users
- **Ordered results**: Results ordered by email for consistency
- **Security**: Only authenticated users can search

**Use Cases:**
- Finding users to add to signing workflows
- User lookup during envelope creation
- General user directory functionality

### 📄 Document Handling

Complete document management system for uploading, converting (if Word), retrieving, and deleting PDF documents.

#### Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/documents/upload/` | Upload PDF document | ✅ |
| `GET` | `/documents/` | List user's documents | ✅ |
| `GET` | `/documents/{id}/` | Retrieve single document | ✅ |
| `DELETE` | `/documents/{id}/delete/` | Delete document | ✅ |

#### 1. Upload Document

**Endpoint:** `POST /documents/upload/`

Upload a document to the system. Accepts PDF files directly or Word documents (`.doc`, `.docx`) which are automatically converted to PDF on upload. The stored document will be a PDF regardless of the original format.

**Request:**
```bash
curl -X POST http://localhost:8000/documents/upload/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@document.docx"
```

**Request Details:**
- Content-Type: `multipart/form-data`
- Authentication: Required (JWT Bearer token)
- Body: Form data with key `file` containing a PDF or Word file

**Constraints:**
- File type: PDF (`.pdf`) or Word (`.doc`, `.docx`)
- Word files are converted to PDF during upload (LibreOffice required)
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
- `400 Bad Request`: Invalid file type, size, or Word-to-PDF conversion failure
- `401 Unauthorized`: Missing or invalid authentication
- `500 Internal Server Error`: Server error during upload

**Word Document Conversion:**
- Word files (`.doc`, `.docx`) are automatically converted to PDF using LibreOffice
- If LibreOffice is not installed or `soffice` is not on PATH, upload will fail with a 400 error
- Ensure LibreOffice is properly installed and accessible before uploading Word documents

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
    "status": "pending",
    "created_at": "2024-01-01T11:00:00Z",
    "updated_at": "2024-01-01T11:30:00Z"
  }
]
```

#### 2a. Merge Documents

**Endpoint:** `POST /api/documents/merge/`

Merge multiple existing PDF documents (owned by the authenticated user) into a single PDF. The merged file is stored as a new `Document`, and the endpoint returns its id and URL.

**Request:**
```bash
curl -X POST http://localhost:8000/api/documents/merge/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": [
      "550e8400-e29b-41d4-a716-446655440000",
      "550e8400-e29b-41d4-a716-446655440005"
    ],
    "name": "merged.pdf"
  }'
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- Body:
  - `document_ids` (array<UUID>, required, length ≥ 2): Ordered list of source documents to merge
  - `name` (string, optional): Desired filename for the merged PDF (defaults to "Merged Document")

**Constraints:**
- All `document_ids` must exist and be owned by the requester
- Each source document must have a valid `file_url` on disk or accessible storage
- Pages are appended preserving the order of `document_ids`

**Response (Success - 201):**
```json
{
  "status": "success",
  "message": "Documents merged successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440099",
    "file_url": "/media/merged_docs/550e8400-e29b-41d4-a716-446655440099_merged.pdf",
    "name": "merged.pdf"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Fewer than two documents provided, missing source file
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: A referenced document is not owned by the requester
- `500 Internal Server Error`: Merge/write failure


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
- PDF (`.pdf`) accepted as-is
- Word files (`.doc`, `.docx`) accepted and auto-converted to PDF on upload
- Converted PDFs are stored; subsequent workflows operate on the PDF

**Size Limitations:**
- Maximum file size: 20MB
- Files larger than 20MB will be rejected with a 400 error

**LibreOffice Dependency:**
- LibreOffice is required for Word document conversion
- The `soffice` command must be available on the system PATH
- Install LibreOffice using the instructions in the Setup section
- Word uploads will fail with clear error messages if LibreOffice is not available

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
  - File type validation (PDF and Word files)
  - File size validation (≤20MB)
  - Authentication requirements
  - Multiple uploads by same user
  - Different users uploading independently
  - Empty file handling
  - Missing file data
  - Word-to-PDF conversion (requires LibreOffice)

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
- `name` (CharField): User-defined name of the envelope (optional, defaults to "Untitled Envelope" + timestamp)
- `description` (TextField): Optional description or notes for recipients about this envelope
- `status` (CharField): Current status with choices:
  - `draft`: Envelope is being prepared
  - `pending`: Envelope has been sent to signers
  - `completed`: All signers have completed signing
  - `self_signed`: Creator signed their own document(s) without recipients
  - `rejected`: Envelope was rejected
- `signing_order` (JSONField): Ordered list of signers with validation and optional signature position coordinates
- `created_at` (DateTimeField): Timestamp when the envelope was created
- `updated_at` (DateTimeField): Timestamp when the envelope was last updated

**Signing Order Format:**
```json
[
  {
    "signer_id": "550e8400-e29b-41d4-a716-446655440000", 
    "order": 1,
    "position": {
      "page": 1,
      "x": 150,
      "y": 450,
      "width": 200,
      "height": 50
    }
  },
  {
    "signer_id": "550e8400-e29b-41d4-a716-446655440001", 
    "order": 2,
    "position": {
      "page": 2,
      "x": 120,
      "y": 600,
      "width": 180,
      "height": 40
    }
  },
  {
    "signer_id": "550e8400-e29b-41d4-a716-446655440002", 
    "order": 3
  }
]
```

**Signing Order Validation Rules:**
- Must be a list of dictionaries
- Each entry must have `signer_id` (valid UUID) and `order` (positive integer)
- Orders must start from 1 and be sequential (no gaps, no duplicates)
- `signer_id` values must correspond to existing users
- Optional `position` field must contain numeric `page`, `x`, `y`, `width`, and `height` fields
- All position values must be >= 0 (accepts both integers and floats)
- Empty list is valid (no signers assigned yet)

**Features:**
- Automatic UUID generation for envelope IDs
- Cascade delete when document or creator is deleted
- Default status of "draft"
- Comprehensive signing order validation
- Properties: `signer_count`, `is_completed`, `is_sent` (returns True when status is "pending")
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
print(f"Is sent: {envelope.is_sent}")  # True when status is "pending"
```

### 📮 Envelope Creation

Complete envelope management system for creating signing workflows around documents.

#### Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/envelopes/create/` | Create new envelope for document | ✅ |
| `DELETE` | `/api/envelopes/{id}/delete/` | Delete envelope (creator only) | ✅ |

#### 1. Create Envelope

**Endpoint:** `POST /api/envelopes/create/`

Create a new envelope with multiple documents and a specified signing order. You can optionally provide a custom name for the envelope and document-specific signature positions.

**Request:**
```bash
curl -X POST http://localhost:8000/api/envelopes/create/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": [
      "550e8400-e29b-41d4-a716-446655440000",
      "550e8400-e29b-41d4-a716-446655440005"
    ],
    "name": "My Important Contract Bundle",
    "description": "Please review all terms carefully before signing",
    "signing_order": [
      {
        "signer_id": "550e8400-e29b-41d4-a716-446655440001", 
        "order": 1
      },
      {
        "signer_id": "550e8400-e29b-41d4-a716-446655440002", 
        "order": 2
      }
    ],
    "documents_with_positions": [
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440000",
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}},
          {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "position": {"page": 1, "x": 150, "y": 350, "width": 200, "height": 50}}
        ]
      },
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440005",
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 2, "x": 100, "y": 200, "width": 180, "height": 40}}
        ]
      }
    ]
  }'
```

**Request Details:**
- Content-Type: `application/json`
- Authentication: Required (JWT Bearer token)
- Body: JSON with `document_ids` (list of document UUIDs), optional `name` (string), optional `description` (string), `signing_order` (list of signers), and optional `documents_with_positions` (list of document-specific signer positions).

**Payload Structure:**
```json
{
  "document_ids": ["uuid-of-document-1", "uuid-of-document-2"], // List of document UUIDs
  "name": "Optional custom envelope name", // Optional string
  "description": "Optional description or notes for recipients", // Optional string
  "signing_order": [
    {
      "signer_id": "uuid-user-1", 
      "order": 1
    },
    {
      "signer_id": "uuid-user-2", 
      "order": 2
    }
  ],
  "documents_with_positions": [
    {
      "document_id": "uuid-of-document-1", // Document to apply positions to
      "signer_document_positions": [ // List of signer positions for this specific document
        {"signer_id": "uuid-user-1", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}},
        {"signer_id": "uuid-user-2", "position": {"page": 1, "x": 150, "y": 350, "width": 200, "height": 50}}
      ]
    },
    {
      "document_id": "uuid-of-document-2",
      "signer_document_positions": [
        {"signer_id": "uuid-user-1", "position": {"page": 2, "x": 100, "y": 200, "width": 180, "height": 40}}
      ]
    }
  ]
}
```

**Constraints:**
- At least one `document_id` is required.
- Documents in `document_ids` must exist and belong to the authenticated user.
- Each `signer_id` in `signing_order` and `documents_with_positions` must reference a valid user.
- `signing_order` must be a list of dictionaries with valid `signer_id` and sequential `order` values (starting from 1, no gaps, no duplicates).
- `documents_with_positions` (if provided) must be a list of dictionaries.
- Each entry in `documents_with_positions` must have a `document_id` that is present in the main `document_ids` list.
- Each `signer_document_positions` entry must have a `signer_id` that is present in the main `signing_order`.
- Optional `position` field within `signer_document_positions` defines signature coordinates: `page` (positive integer), `x`, `y`, `width`, `height` (non-negative numbers, integers or floats). If omitted for a signer/document, default or request-provided coordinates will be used.
- If no custom `name` is provided, a default name like "Untitled Envelope - YYYY-MM-DD HH:MM" will be generated.

**Response (Success - 201):**
```json
{
  "success": true,
  "message": "Envelope created successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "creator": "550e8400-e29b-41d4-a716-446655440004",
    "creator_email": "creator@example.com",
    "name": "My Important Contract Bundle",
    "description": "Please review all terms carefully before signing",
    "status": "draft",
    "is_self_sign": false,
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ],
    "signer_count": 2,
    "documents": [
      {
        "id": "uuid-of-envelopedocument-1",
        "document": "550e8400-e29b-41d4-a716-446655440000",
        "order": 1,
        "document_file_name": "document1.pdf",
        "document_file_url": "/media/documents/document1.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}},
          {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "position": {"page": 1, "x": 150, "y": 350, "width": 200, "height": 50}}
        ]
      },
      {
        "id": "uuid-of-envelopedocument-2",
        "document": "550e8400-e29b-41d4-a716-446655440005",
        "order": 2,
        "document_file_name": "document2.pdf",
        "document_file_url": "/media/documents/document2.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 2, "x": 100, "y": 200, "width": 180, "height": 40}}
        ]
      }
    ],
    "signatures": [],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Validation errors (documents not found, invalid signers, malformed signing order, invalid document/signer positions, no documents provided).
- `401 Unauthorized`: Missing or invalid authentication.

#### 2. Send Envelope

**Endpoint:** `POST /envelopes/{id}/send/`

Send an envelope to start the signing process. This changes the status from `draft` (or `rejected`) to `pending`, creates signature records for all signers, and initiates notifications.

**Request:**
```bash
curl -X POST http://localhost:8000/api/envelopes/550e8400-e29b-41d4-a716-446655440000/send/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{id}` - UUID of the envelope to send
- Body: None required

**Constraints:**
- Only the envelope creator can send the envelope.
- Envelope must be in `draft` or `rejected` status.
- Authentication required.

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope sent successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "creator": "550e8400-e29b-41d4-a716-446655440002",
    "name": "My Important Contract Bundle",
    "description": "Please review all terms carefully before signing",
    "status": "pending",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440003", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440004", "order": 2}
    ],
    "signer_count": 2,
    "documents": [
      {
        "id": "uuid-of-envelopedocument-1",
    "document": "550e8400-e29b-41d4-a716-446655440000",
        "order": 1,
        "document_file_name": "document1.pdf",
        "document_file_url": "/media/documents/document1.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": []
      }
    ],
    "signatures": [
      {
        "id": "uuid-of-signature-1",
        "signer": "550e8400-e29b-41d4-a716-446655440003",
        "signer_email": "signer1@example.com",
        "signer_name": "Test Signer 1",
        "status": "pending",
        "signing_order": 1,
        "signed_at": null,
        "signature_image": null,
        "created_at": "2024-01-01T12:00:00Z",
        "updated_at": "2024-01-01T12:00:00Z"
      }
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Validation errors (envelope not in `draft` or `rejected` status, invalid `signing_order`).
- `401 Unauthorized`: Missing or invalid authentication.
- `403 Forbidden`: User is not the envelope creator.
- `404 Not Found`: Envelope not found.

#### 3. Reject Envelope

**Endpoint:** `POST /envelopes/{id}/reject/`

Reject an envelope (creator only). This changes the status to `rejected`, cancels the signing workflow, and notifies all relevant parties.

**Request:**
```bash
curl -X POST http://localhost:8000/api/envelopes/550e8400-e29b-41d4-a716-446655440000/reject/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{id}` - UUID of the envelope to reject
- Body: None required

**Constraints:**
- Only the envelope creator can reject the envelope.
- Can reject envelopes in any status (`draft`, `pending`, `completed`, `rejected`).
- Authentication required.

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope rejected successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "creator": "550e8400-e29b-41d4-a716-446655440002",
    "name": "My Important Contract Bundle",
    "description": "Please review all terms carefully before signing",
    "status": "rejected",
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440003", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440004", "order": 2}
    ],
    "signer_count": 2,
    "documents": [
      {
        "id": "uuid-of-envelopedocument-1",
        "document": "550e8400-e29b-41d4-a716-446655440000",
        "order": 1,
        "document_file_name": "document1.pdf",
        "document_file_url": "/media/documents/document1.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": []
      }
    ],
    "signatures": [], // Signatures might be empty if rejected before any signing
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `401 Unauthorized`: Missing or invalid authentication.
- `403 Forbidden`: User is not the envelope creator.
- `404 Not Found`: Envelope not found.

#### 3a. Edit Draft or Rejected Envelope

**Endpoint:** `PATCH /envelopes/{id}/edit/`

Edit an existing draft or rejected envelope. Only the envelope creator can edit. Allows updating `name`, `description`, `document_ids`, `signing_order`, and `documents_with_positions`.

**Request:**
```bash
curl -X PATCH http://localhost:8000/api/envelopes/550e8400-e29b-41d4-a716-446655440003/edit/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Revised Contract Bundle",
    "description": "Updated terms - please review again",
    "document_ids": [
      "550e8400-e29b-41d4-a716-446655440000",
      "550e8400-e29b-41d4-a716-446655440006" // New document
    ],
    "signing_order": [
      {
        "signer_id": "550e8400-e29b-41d4-a716-446655440001", 
        "order": 1,
      },
      {
        "signer_id": "550e8400-e29b-41d4-a716-446655440007", // New signer
        "order": 2
      }
    ],
    "documents_with_positions": [
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440000",
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 160, "y": 460, "width": 210, "height": 55}}
        ]
      },
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440006",
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 80, "y": 90, "width": 100, "height": 30}},
          {"signer_id": "550e8400-e29b-41d4-a716-446655440007", "position": {"page": 1, "x": 180, "y": 190, "width": 110, "height": 35}}
        ]
      }
    ]
  }'
```

**Request Details:**
- Method: PATCH
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{id}` - UUID of the envelope to edit
- Body: JSON with optional `name`, `description`, `document_ids`, `signing_order`, and `documents_with_positions`.

**Constraints:**
- Only the envelope creator can edit the envelope.
- Envelope must be in `draft` or `rejected` status.
- If `document_ids` is provided, it must not be empty. All documents must exist and belong to the creator.
- `signing_order` must follow validation rules (sequential orders starting at 1, valid UUID users, no duplicates).
- `documents_with_positions` must follow validation rules (document_ids and signer_ids must exist in the envelope, valid position data).
- If a rejected envelope is edited, its `status` will revert to `draft`.

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope updated successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "creator": "550e8400-e29b-41d4-a716-446655440004",
    "name": "Revised Contract Bundle",
    "description": "Updated terms - please review again",
    "status": "draft", // Status is reverted to draft if previously rejected
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440007", "order": 2}
    ],
    "signer_count": 2,
    "documents": [
      {
        "id": "uuid-of-envelopedocument-1",
        "document": "550e8400-e29b-41d4-a716-446655440000",
        "order": 1,
        "document_file_name": "document1.pdf",
        "document_file_url": "/media/documents/document1.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 160, "y": 460, "width": 210, "height": 55}}
        ]
      },
      {
        "id": "uuid-of-envelopedocument-3",
        "document": "550e8400-e29b-41d4-a716-446655440006",
        "order": 2,
        "document_file_name": "document new.pdf",
        "document_file_url": "/media/documents/document_new.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 80, "y": 90, "width": 100, "height": 30}},
          {"signer_id": "550e8400-e29b-41d4-a716-446655440007", "position": {"page": 1, "x": 180, "y": 190, "width": 110, "height": 35}}
        ]
      }
    ],
    "signatures": [],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Validation errors (envelope not in `draft` or `rejected` status, invalid `document_ids`, invalid `signing_order`, invalid `documents_with_positions`).
- `401 Unauthorized`: Missing or invalid authentication.
- `403 Forbidden`: User is not the envelope creator.
- `404 Not Found`: Envelope not found.

#### 4. List Envelopes

**Endpoint:** `GET /envelopes/`

List all envelopes where the authenticated user is either the creator or a signer.

**Request:**
```bash
curl -X GET http://localhost:8000/api/envelopes/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: GET
- Authentication: Required (JWT Bearer token)
- Body: None required
- Optional query params:
  - `status` — filter by envelope status (`draft`, `pending`, `completed`, `self_signed`, `rejected`)
  - `search` — case-insensitive match on name, description, or creator email/name
  - `is_self_sign` — `true` returns only self-signed envelopes; `false` excludes them

**Notes:**
- Self-signed envelopes (`is_self_sign: true`) cannot be sent or edited via the multi-party envelope endpoints.

**Access Control:**
- Returns envelopes created by the authenticated user.
- Returns envelopes where the authenticated user is a signer.
- Envelopes are ordered by creation date (newest first).

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelopes retrieved successfully",
  "data": [
    {
    "id": "550e8400-e29b-41d4-a716-446655440003",
      "creator": "550e8400-e29b-41d4-a716-446655440004",
      "creator_email": "creator@example.com",
      "name": "My Important Contract Bundle",
    "status": "pending",
    "is_self_sign": false,
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
      {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
    ],
      "signer_count": 2,
      "documents": [
        {
          "id": "uuid-of-envelopedocument-1",
          "document": "550e8400-e29b-41d4-a716-446655440000",
          "order": 1,
          "document_file_name": "document1.pdf",
          "document_file_url": "/media/documents/document1.pdf",
          "document_signed_file_url": null,
          "signer_document_positions": [
            {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}}
          ]
        }
      ],
      "signatures": [
        {
          "id": "uuid-of-signature-1",
          "signer": "550e8400-e29b-41d4-a716-446655440001",
          "signer_email": "signer1@example.com",
          "signer_name": "Test Signer 1",
          "status": "signed",
          "signing_order": 1,
          "signed_at": "2024-01-01T12:10:00Z",
          "signature_image": "base64-encoded-signature-data",
          "created_at": "2024-01-01T12:00:00Z",
          "updated_at": "2024-01-01T12:00:00Z"
        }
    ],
    "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:05:00Z"
  }
  ]
}
```

**Password Visibility:** When an envelope reaches `completed`, the `pdf_lock_password` field will contain the generated password required to open the locked PDFs. Creators and participants can retrieve it from the envelope detail endpoint.

#### 5. Retrieve Envelope Details

**Endpoint:** `GET /envelopes/{id}/`

Retrieve full details of a specific envelope including associated documents and signature statuses.

**Request:**
```bash
curl -X GET http://localhost:8000/api/envelopes/550e8400-e29b-41d4-a716-446655440003/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Request Details:**
- Method: GET
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{id}` - UUID of the envelope to retrieve
- Body: None required

**Access Control:**
- Creator can view their envelope.
- Signers can view envelopes they are assigned to.
- Other users receive 404 (not found or access denied).

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Envelope retrieved successfully",
  "data": {
      "id": "550e8400-e29b-41d4-a716-446655440003",
      "creator": "550e8400-e29b-41d4-a716-446655440004",
    "creator_email": "creator@example.com",
    "name": "My Important Contract Bundle",
      "status": "pending",
      "is_self_sign": false,
      "signing_order": [
        {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "order": 1},
        {"signer_id": "550e8400-e29b-41d4-a716-446655440002", "order": 2}
      ],
    "signer_count": 2,
    "documents": [
      {
        "id": "uuid-of-envelopedocument-1",
        "document": "550e8400-e29b-41d4-a716-446655440000",
        "order": 1,
        "document_file_name": "document1.pdf",
        "document_file_url": "/media/documents/document1.pdf",
        "document_signed_file_url": null,
        "signer_document_positions": [
          {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}}
        ]
      }
    ],
      "signatures": [
        {
        "id": "uuid-of-signature-1",
          "signer": "550e8400-e29b-41d4-a716-446655440001",
        "signer_email": "signer1@example.com",
        "signer_name": "Test Signer 1",
          "status": "signed",
        "signing_order": 1,
        "signed_at": "2024-01-01T12:10:00Z",
        "signature_image": "base64-encoded-signature-data",
        "created_at": "2024-01-01T12:00:00Z",
        "updated_at": "2024-01-01T12:00:00Z"
      }
    ],
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

#### 6. Envelope Dashboard

**Endpoint:** `GET /envelopes/dashboard/`

**Deprecated alias:** `GET /envelopes/metrics/` (returns the same payload)

Retrieve an aggregated dashboard for the authenticated user: legacy metrics, envelope counts, envelopes requiring the user's signature, and recent activity.

**Request:**
```bash
curl -X GET http://localhost:8000/api/envelopes/dashboard/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Optional query parameters:
- `action_required_limit` (default `10`, max `100`)
- `activity_limit` (default `5`, max `100`)

**Response (Success - 200):**
```json
{
  "status": "success",
  "message": "Dashboard retrieved successfully",
  "data": {
    "metrics": {
      "documents_signed": 8,
      "pending_signatures": 3,
      "active_envelopes": 5,
      "completion_rate": 57.14
    },
    "counts": {
      "pending_my_signature": 2,
      "pending_sent": 3,
      "completed": 4,
      "draft": 1
    },
    "action_required": [],
    "recent_activity": []
  }
}
```

**Notes:**
- `metrics` preserves the former `/envelopes/metrics/` fields.
- `metrics.documents_signed` / `metrics.pending_signatures` reflect the user's signature records.
- `metrics.active_envelopes` counts envelopes created by the user that are still draft or pending.
- `metrics.completion_rate` is the percentage of the user's envelopes that have reached `completed`.
- `counts.pending_my_signature` counts envelopes where the user is the current signer.
- `counts.pending_sent`, `counts.completed`, and `counts.draft` count envelopes created by the user in each status.
- `action_required` lists envelopes with status `pending` where the authenticated user is the current signer. Self-signed envelopes are excluded.
- `recent_activity` lists recent send, sign, and reject actions performed by the user.

#### 5a. Retrieve Envelope Documents

**Endpoint:** `GET /envelopes/{id}/documents/`

Fetch all documents attached to an envelope (creator or assigned signer only). Useful for obtaining `file_url` for the signer UI before posting to the sign endpoint. This endpoint now returns a list of documents.

**Request:**
```bash
curl -X GET http://localhost:8000/api/envelopes/550e8400-e29b-41d4-a716-446655440003/documents/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 200):**
```json
{
  "status": "success",
  "message": "Envelope documents retrieved successfully",
  "data": [
    {
      "id": "uuid-of-envelopedocument-1",
      "document": "550e8400-e29b-41d4-a716-446655440000",
      "order": 1,
      "document_file_name": "document1.pdf",
      "document_file_url": "/media/documents/document1.pdf",
      "document_signed_file_url": null,
      "signer_document_positions": [
        {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 1, "x": 150, "y": 450, "width": 200, "height": 50}}
      ]
    },
    {
      "id": "uuid-of-envelopedocument-2",
      "document": "550e8400-e29b-41d4-a716-446655440005",
      "order": 2,
      "document_file_name": "document2.pdf",
      "document_file_url": "/media/documents/document2.pdf",
      "document_signed_file_url": null,
      "signer_document_positions": [
        {"signer_id": "550e8400-e29b-41d4-a716-446655440001", "position": {"page": 2, "x": 100, "y": 200, "width": 180, "height": 40}}
      ]
    }
  ]
}
```

**Error Responses:**
- `401 Unauthorized`: Missing or invalid authentication.
- `404 Not Found`: Envelope not found or access denied.

#### 6. Delete Envelope

**Endpoint:** `DELETE /envelopes/{id}/delete/`

Permanently delete an envelope. Only the envelope creator can delete it.

**Request:**
```bash
curl -X DELETE http://localhost:8000/api/envelopes/550e8400-e29b-41d4-a716-446655440003/delete/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response (Success - 204 No Content):**
```json
{
  "status": "success",
  "message": "Envelope deleted successfully"
}
```

**Error Responses:**
- `401 Unauthorized`: Missing or invalid authentication.
- `404 Not Found`: Envelope not found or user is not the creator.
- `500 Internal Server Error`: Server error during deletion.

### ✍️ Signature Operations

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/signatures/self-sign/` | Self-sign document(s) in one call (no recipients) | ✅ |
| `POST` | `/api/signatures/{envelope_id}/sign/` | Current signer signs all documents in the envelope | ✅ |
| `POST` | `/api/signatures/{envelope_id}/decline/` | Current signer declines (rejects entire envelope) | ✅ |

**Workflow comparison:**
- **Multi-party:** upload → create envelope → send → sequential sign
- **Self-sign:** upload → `POST /api/signatures/self-sign/` → `self_signed` (no send step, no recipient notifications)

#### Self-Sign Document(s)

**Endpoint:** `POST /api/signatures/self-sign/`

Upload document(s) first via `POST /api/documents/upload/`, then call this endpoint to place signature(s), optionally embed input field values, and receive a self-signed envelope in one request. No recipients, send step, or notification emails.

**Request:**
```bash
curl -X POST http://localhost:8000/api/signatures/self-sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": ["550e8400-e29b-41d4-a716-446655440000"],
    "name": "Self-signed agreement",
    "documents_with_positions": [
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440000",
        "signer_document_positions": [
          { "position": { "page": 1, "x": 100, "y": 500, "width": 120, "height": 40 } }
        ]
      }
    ],
    "fields": [
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440000",
        "page": 1, "x": 100, "y": 600, "width": 200, "height": 24,
        "type": "text", "required": true, "value": "Jane Doe"
      }
    ],
    "signature_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "pdf_password_protection_enabled": true
  }'
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- Body: Same envelope shape as create (`document_ids`, `name`, `description`, `documents_with_positions`, `fields`, `pdf_password_protection_enabled`) plus sign options (`signature_image`, `signature_id`, optional fallback `page`/`x`/`y`/`width`/`height`).
- `signing_order` is **not accepted** — the server sets the current user as the sole signer.
- `signer_id` in `documents_with_positions` is optional (defaults to the authenticated user).
- Field items may include inline `value` (in addition to `prefill_value`); required fields must supply one of them.
- Signature source: `signature_image`, `signature_id`, or the user's default `UserSignature`.

**Response (Success - 201):**
```json
{
  "status": "success",
  "message": "Document self-signed successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "status": "self_signed",
    "is_self_sign": true,
    "signing_order": [
      {"signer_id": "550e8400-e29b-41d4-a716-446655440004", "order": 1}
    ],
    "documents": [
      {
        "document_signed_file_url": "/media/temp_signed/550e8400-e29b-41d4-a716-446655440000_signed_....pdf"
      }
    ],
    "pdf_lock_password": "generated-password-if-enabled"
  }
}
```

**Constraints:**
- Documents must exist and belong to the authenticated user.
- Documents must be available in local temporary storage for PDF signing (same requirement as multi-party sign).
- Self-signed envelopes cannot be sent (`POST /api/envelopes/{id}/send/`) or edited (`PATCH /api/envelopes/{id}/edit/`).
- No notifications or emails are sent for this flow.

**Error Responses:**
- `400 Bad Request`: Validation errors, missing field values, document not in local storage, or invalid signature source.
- `401 Unauthorized`: Missing or invalid authentication.

#### 1. Sign Document

**Endpoint:** `POST /api/signatures/{envelope_id}/sign/`

Current signer signs all documents within the envelope. Only the current signer (next in sequence) can sign. Signature placement is automatically handled using predefined coordinates from the `EnvelopeDocument` or falls back to request-provided/default coordinates.

**Request:**
```bash
curl -X POST http://localhost:8000/api/signatures/550e8400-e29b-41d4-a716-446655440003/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "page": 1,
    "x": 100,
    "y": 100,
    "width": 120,
    "height": 40
  }'
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{envelope_id}` - UUID of the envelope
- Body: JSON with optional `signature_image` (base64 encoded) or `signature_id` (UUID of UserSignature). Optional `page`, `x`, `y`, `width`, `height` can be provided as fallback for signature placement if not defined in `EnvelopeDocument`.

**Payload Options:**
```json
{
  // Option 1: Provide inline signature image (fallback position if not in EnvelopeDocument)
  "signature_image": "base64-encoded-signature-data",
  "page": 1,
  "x": 100,
  "y": 100,
  "width": 120,
  "height": 40
}
```

```json
{
  // Option 2: Use reusable signature (fallback position if not in EnvelopeDocument)
  "signature_id": "uuid-of-user-signature",
  "page": 1,
  "x": 100,
  "y": 100,
  "width": 120,
  "height": 40
}
```

```json
{
  // Option 3: Use default signature (fallback position if not in EnvelopeDocument)
  // Empty payload - system uses default signature automatically
  "page": 1,
  "x": 100,
  "y": 100,
  "width": 120,
  "height": 40
}
```

**Constraints:**
- Only the current signer (lowest pending order) can sign.
- Envelope must be in `pending` status.
- Authentication required.
- Either `signature_image`, `signature_id`, or a default signature must be available.
- Position coordinates in request are fallback options if not defined in `EnvelopeDocument`.

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Document signed successfully",
  "data": {
    "id": "uuid-of-signature-1",
    "signer": "550e8400-e29b-41d4-a716-446655440001",
    "signer_email": "signer1@example.com",
    "signer_name": "Test Signer 1",
    "status": "signed",
    "signing_order": 1,
    "signed_at": "2024-01-01T12:10:00Z",
    "signature_image": "base64-encoded-signature-data",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Invalid signature data, invalid position coordinates.
- `401 Unauthorized`: Missing or invalid authentication.
- `403 Forbidden`: Not current signer, already signed/declined, or not authorized.
- `404 Not Found`: Envelope not found.

#### 2. Decline Signature

**Endpoint:** `POST /api/signatures/{envelope_id}/decline/`

Current signer declines to sign all documents within the envelope. This immediately rejects the entire envelope.

**Request:**
```bash
curl -X POST http://localhost:8000/api/signatures/550e8400-e29b-41d4-a716-446655440003/decline/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decline_message": "Document terms are not acceptable."
  }'
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{envelope_id}` - UUID of the envelope
- Body: Optional JSON with `decline_message` (string).

**Payload Options:**
```json
{
  // Option 1: Provide a decline message
  "decline_message": "Reason for declining the document."
}
```

```json
{
  // Option 2: Decline without a specific message
  // Empty payload - system records decline without specific reason
}
```

**Constraints:**
- Only the current signer can decline.
- Envelope must be in `pending` status.
- Authentication required.

**Response (Success - 200):**
```json
{
  "success": true,
  "message": "Document declined successfully. Envelope has been rejected.",
  "data": {
    "id": "uuid-of-signature-1",
    "signer": "550e8400-e29b-41d4-a716-446655440001",
    "signer_email": "signer1@example.com",
    "signer_name": "Test Signer 1",
    "status": "declined",
    "signing_order": 1,
    "signed_at": null,
    "signature_image": null,
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:05:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Envelope not in `pending` status.
- `401 Unauthorized`: Missing or invalid authentication.
- `403 Forbidden`: Not current signer or already signed/declined, or not authorized.
- `404 Not Found`: Envelope not found.

### Notifications and Audit Logs

- Notification messages (in-app and email) now use the envelope's custom `name` (e.g., "[Creator Name] has requested you to sign the document '[Envelope Name]'.") and reflect the number of documents in the envelope where appropriate.
- Audit log entries for envelope and signature actions now include the envelope's custom `name` and the count of documents in the message.

## 🎯 Automatic Signature Placement

The system now supports **automatic signature placement** using predefined coordinates stored in the envelope's `signing_order` field. When signers approve their signature, the system automatically places their signature image at the specified location on the document without requiring manual coordinate input from the signer.

### How It Works

1. **Envelope Creation**: When creating an envelope, specify position coordinates for each signer in the `signing_order`
2. **Automatic Placement**: When a signer signs, the system uses their predefined position coordinates
3. **Fallback Support**: If no position is defined, the system falls back to default coordinates or request parameters

### Position Priority

The system follows this priority order for signature placement:

1. **Envelope Position**: Uses coordinates from the signer's entry in `envelope.signing_order[].position`
2. **Request Position**: Uses coordinates provided in the signing request (fallback)
3. **Default Position**: Uses system defaults (page: 1, x: 100, y: 100, width: 120, height: 40)

### Benefits

- **Consistent Placement**: Signatures always appear in the correct location
- **No Manual Input**: Signers don't need to specify coordinates when signing
- **Professional Documents**: Ensures properly formatted signed documents
- **Flexible Fallback**: Still works with existing workflows that don't use predefined positions

#### Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/signatures/{envelope_id}/sign/` | Sign a document in envelope (with automatic placement) | ✅ |
| `POST` | `/signatures/{envelope_id}/decline/` | Decline to sign document | ✅ |

#### 1. Sign Document

**Endpoint:** `POST /signatures/{envelope_id}/sign/`

Sign a document in the envelope (sequential signing workflow with automatic placement).

**Request (Automatic Placement):**
```bash
# Simple signing - position coordinates come from envelope
curl -X POST http://localhost:8000/signatures/550e8400-e29b-41d4-a716-446655440000/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
  }'
```

**Request (Using Reusable Signature):**
```bash
# Sign using a saved signature
curl -X POST http://localhost:8000/signatures/550e8400-e29b-41d4-a716-446655440000/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_id": "550e8400-e29b-41d4-a716-446655440001"
  }'
```

**Request (Using Default Signature):**
```bash
# Sign using default signature (no payload needed)
curl -X POST http://localhost:8000/signatures/550e8400-e29b-41d4-a716-446655440000/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Request (Manual Position - Fallback):**
```bash
# Fallback: provide position coordinates if not defined in envelope
curl -X POST http://localhost:8000/signatures/550e8400-e29b-41d4-a716-446655440000/sign/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "signature_image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "page": 1,
    "x": 100,
    "y": 100,
    "width": 120,
    "height": 40
  }'
```

**Request Details:**
- Method: POST
- Authentication: Required (JWT Bearer token)
- URL Parameter: `{envelope_id}` - UUID of the envelope
- Body: JSON with optional signature data and position coordinates (now optional fallbacks)

**Payload Options:**
```json
{
  // Option 1: Provide signature image (position from envelope)
  "signature_image": "base64-encoded-signature-data"
}
```

```json
{
  // Option 2: Use reusable signature (position from envelope)
  "signature_id": "uuid-of-user-signature"
}
```

```json
{
  // Option 3: Use default signature (position from envelope)
  // Empty payload - system uses default signature automatically
}
```

```json
{
  // Option 4: Manual coordinates (fallback when envelope has no position)
  "signature_image": "base64-encoded-signature-data",
  "page": 1,
  "x": 100,
  "y": 100,
  "width": 120,
  "height": 40
}
```

**Constraints:**
- Only the current signer (lowest pending order) can sign
- Envelope must be in "pending" status
- Authentication required
- Position coordinates are automatically used from envelope's `signing_order` if defined
- Position coordinates in request are fallback options if not defined in envelope
- Either signature_image, signature_id, or default signature must be available

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
- Envelope must be in "pending" status
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
- **In-progress signing (performance mode)**: uploads and intermediate signed artifacts are stored on the server under `MEDIA_ROOT` for fast read/write.
- **After envelope completion**: the final locked PDF is uploaded to S3 and `Document.file_url` / `Document.signed_file_url` are updated to the S3 URL.

Temporary directories (under `MEDIA_ROOT`):
- `TEMP_UPLOAD_SUBDIR` (default: `temp_uploads`)
- `TEMP_SIGNED_SUBDIR` (default: `signed_docs`)

Environment variables (see `.env.example`):
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- AWS_STORAGE_BUCKET_NAME
- AWS_S3_REGION_NAME

#### Cleanup of temporary PDFs

Temporary local PDFs are retained for **24 hours** and should be cleaned up by a scheduler.

Management command:

```bash
python manage.py cleanup_temp_pdfs
python manage.py cleanup_temp_pdfs --hours 24
python manage.py cleanup_temp_pdfs --dry-run
```

Example cron (daily at 03:15):

```bash
15 3 * * * /path/to/venv/bin/python /path/to/app/manage.py cleanup_temp_pdfs --hours 24
```

### Testing & Validation

**Run All Tests:**
```bash
pytest
```

**If your shell env has non-boolean `DEBUG` (common in release shells), run with explicit env overrides:**

```bash
DEBUG=True SECRET_KEY=testsecret ALLOWED_HOSTS=localhost .venv/bin/pytest -q
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
The Celery configuration is set in `esign/settings.py` and uses `django-celery-results` for storing task results:
```python
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "django-db"
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

Apply result-backend migrations:
```bash
python manage.py migrate
```

Quick smoke test in Django shell:
```python
from notifications.tasks import create_notification
create_notification.delay("<user-uuid>", "Hello from Celery!")
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

## 🔒 Security Features

### Security Headers
- **HSTS**: HTTP Strict Transport Security enabled in production
- **XSS Protection**: Browser XSS filter enabled
- **Content Type Protection**: Prevents MIME type sniffing
- **Frame Options**: X-Frame-Options set to DENY
- **Secure Cookies**: All cookies marked secure in production

### Authentication & Authorization
- **JWT Authentication**: Stateless token-based authentication
- **Token Blacklisting**: Secure token revocation support
- **Permission Classes**: All endpoints require authentication by default
- **Rate Limiting**: Prevents brute force and API abuse

### Data Protection
- **Input Validation**: All user inputs validated and sanitized
- **SQL Injection Protection**: Django ORM provides built-in protection
- **Audit Logging**: Comprehensive audit trails for compliance
- **IP Address Tracking**: Proper proxy header handling for accurate logging

### Environment Security
- **Secret Management**: All secrets via environment variables
- **DEBUG Mode**: Automatically disabled security features in production
- **CORS Configuration**: Strict origin checking in production
- **HTTPS Enforcement**: Automatic redirect from HTTP to HTTPS