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


