# Placement Intelligence

## Project idea

Placement Intelligence is a local-first college placement portal for candidates, recruiters, and placement administrators. It brings recruitment drives, candidate applications, resume review, and human decisions into one small web application.

The central idea is to help HR review resume evidence against a role's stated requirements. The portal extracts readable text from resumes, finds skills from a maintained vocabulary, captures excerpts as evidence, and calculates a transparent rubric score. The score is a coverage aid for reviewers; it is not a prediction of hiring success.

## Who uses it

- **Candidates** create accounts, maintain placement details, browse open drives, submit resumes, and review their application status.
- **HR / recruiters** create drives, review applications for their own drives, inspect scores and evidence, and record a decision and private notes.
- **Placement administrators** can review records across the portal.

Public registration creates candidate accounts only. Trusted administrators assign recruiter or placement administrator roles.

## Main workflow

1. A recruiter creates a drive with its role description, required and preferred skills, eligibility criteria, deadline, applicant limit, and rubric weights.
2. A candidate completes a placement profile and applies with a PDF, DOCX, or TXT resume.
3. The server extracts readable resume text and checks profile eligibility information.
4. The local analysis detects recognized skills, extracts evidence excerpts, and estimates explicitly stated experience and education level.
5. The portal stores the analysis and a workflow audit event, then displays the application to authorized reviewers.
6. HR reviews the original resume and extracted evidence, then records the final human decision.

## Resume analysis and model

The analysis has two distinct parts:

- **Rubric scorer:** deterministic rules calculate a score from the drive's required and preferred skills, experience, education, and configured weights. Each criterion is shown separately. The score does not decide application status.
- **Skill suggestion model:** an offline TF-IDF index was trained from 195 skill profiles based on the project's built-in skill vocabulary and aliases. It can suggest related terms for HR to verify. Suggestions are unconfirmed, do not affect the score, and are not hiring recommendations.

The local model artifact is `recruitment/data/skill_model.json`. Rebuild it from the project root with:

```powershell
py manage.py train_skill_model
```

The database currently has no labeled application outcomes, so the project does not train or claim to provide a hiring suitability predictor. The taxonomy index is a text retrieval aid, not a model of candidate performance.

## Privacy and access

Resume files are served through an authenticated view with per-application access checks. Candidates can access their own application records; recruiters can review applications for drives they created; placement administrators can access records across the portal. Resume processing and the skill index run locally, with no hosted AI service or cloud fallback configured.

## Technology and project structure

- **Django** provides the web application, authentication, permissions, views, and admin interface.
- **SQLite** stores application data for local development.
- **PyMuPDF**, **python-docx**, and Python text processing support PDF, DOCX, and TXT resumes.
- `placement_intelligence/` contains Django project settings and URL configuration.
- `recruitment/` contains data models, views, resume processing, skill model, and management commands.
- `templates/` contains the portal pages; `static/` contains the styles.

## Run locally

1. Create and activate a virtual environment: `py -m venv .venv` then `.venv\\Scripts\\Activate.ps1`.
2. Install dependencies: `py -m pip install -r requirements.txt`.
3. Apply database migrations: `py manage.py migrate`.
4. Create an administrator: `py manage.py createsuperuser`.
5. Start the development server: `py manage.py runserver` and open `http://127.0.0.1:8000`.
6. In Django admin, create recruiter accounts and assign their user profile role. Candidates can register through the public site.

## Current limitations

- Scanned PDF OCR is not included; resumes need readable text.
- Skill recognition depends on the maintained vocabulary and aliases. It does not verify proficiency or independently establish experience.
- Experience and education extraction use text patterns and can be incomplete or inaccurate; reviewers should inspect the source resume.
- The model suggestions are based on a small project taxonomy, not a large resume corpus or labeled outcomes.
- SQLite and local media storage suit a prototype, not a high-concurrency production service.
- Before institutional deployment, review privacy and retention requirements, upload security, backups, hosting configuration, accessibility, and model evaluation with representative data.
