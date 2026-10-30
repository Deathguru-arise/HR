# Placement Intelligence

A local-first college placement portal prototype for candidates and recruiters. It includes recruitment drives, applications, server-side file access control, PDF/DOCX/TXT text extraction, evidence snippets, transparent skill-coverage scoring, HR review decisions, and an audit trail.

## Run locally

1. Install Python 3.11 or newer.
2. In this folder, create and activate a virtual environment: `py -m venv .venv` then `.venv\Scripts\Activate.ps1`.
3. Install dependencies: `py -m pip install -r requirements.txt`.
4. Create the database: `py manage.py migrate`.
5. Create the first administrator: `py manage.py createsuperuser`.
6. Start the portal: `py manage.py runserver` and open http://127.0.0.1:8000.

Use Django admin at `/admin/` to create recruiter accounts: add a user, then add a `User profile` with role `HR / Recruiter` or `Placement administrator`. Candidate accounts can register from the public page. Candidates can update their graduation year, department, and CGPA through their profile in Django admin in this initial version.

## Current scope and limitations

- This first release uses deterministic local text and skill matching; it does not call a language model, embedding service, or external AI API. No cloud fallback is present. `OLLAMA_*` settings are reserved for a later local-model integration.
- PDF and DOCX text extraction are supported. Scanned PDF OCR is not included; such files are flagged with a readable-text error and need an OCR integration.
- Skill matching uses a small editable vocabulary in `recruitment/services.py`. It does not infer proficiency or experience duration. The score is an evidence-coverage aid, never a shortlist probability.
- Rubric weights are saved with each drive; the initial scorer uses an 80/20 required/preferred split. The drive creation form lets HR set these weights.
- Development uses SQLite and local media storage. SQLite locking is suitable for a local prototype, not a high-concurrency deployment. Use PostgreSQL and review upload/storage security, backups, retention, deployment settings, and institutional privacy requirements before real use.
- Accounts created through public registration are candidates only. Recruiter/admin privileges must be granted by a trusted administrator.
- For local demo use, do not expose the development server to the public internet. Set a strong secret key and `DJANGO_DEBUG=0` for any controlled deployment.

## Privacy and decision process

Resume files are served through an authenticated view with per-application role checks. The application records key workflow events. Candidates cannot see other candidates' files, scores, or private notes. HR users see only applications for drives they created; placement admins can review all records. Final application status is a human decision.

The project brief recommends benchmarking local models, OCR, embeddings, and accuracy before any deployment. Those evaluation and governance steps remain necessary; this prototype does not claim hiring accuracy.
