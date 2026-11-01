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

- Resume scoring uses deterministic local text and skill matching. An offline TF-IDF skill retriever suggests related taxonomy terms for human verification; suggestions do not affect scores. No hosted AI API is called.
- PDF and DOCX text extraction are supported. Scanned PDF OCR is not included; such files are flagged with a readable-text error and need an OCR integration.
- Skill matching uses an editable vocabulary in `recruitment/services.py`. The TF-IDF suggestion index is trained from this app's skill names and aliases, not labeled candidate outcomes. It does not infer proficiency, hiring suitability, or experience duration. The score is an evidence-coverage aid, never a shortlist probability.
- Rubric weights are saved with each drive; the initial scorer uses an 80/20 required/preferred split. The drive creation form lets HR set these weights.
- Development uses SQLite and local media storage. SQLite locking is suitable for a local prototype, not a high-concurrency deployment. Use PostgreSQL and review upload/storage security, backups, retention, deployment settings, and institutional privacy requirements before real use.
- Accounts created through public registration are candidates only. Recruiter/admin privileges must be granted by a trusted administrator.
- For local demo use, do not expose the development server to the public internet. Set a strong secret key and `DJANGO_DEBUG=0` for any controlled deployment.

## Privacy and decision process

Resume files are served through an authenticated view with per-application role checks. The application records key workflow events. Candidates cannot see other candidates' files, scores, or private notes. HR users see only applications for drives they created; placement admins can review all records. Final application status is a human decision.

The project database currently contains no labeled application outcomes, so a hiring predictor cannot be responsibly trained from it. To (re)build the local taxonomy index, run `py manage.py train_skill_model`; the generated artifact is saved in `recruitment/data/skill_model.json`. Benchmarking, OCR, representative labeled data, and governance review remain necessary before deployment; this prototype does not claim hiring accuracy.
