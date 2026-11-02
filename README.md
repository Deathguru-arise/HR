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

## Features in v3

- **Knockout Eligibility Gate:** Separates hard eligibility (CGPA cutoff, max active arrears, graduation year, eligible branches) from fit scoring. Disqualifying reasons are clearly logged before rubric scoring.
- **Section-Aware Resume Parsing:** Parses resumes into Education, Experience, Projects, Technical Skills, Certifications, and Achievements.
- **Skill Context Weighting:** Distinguishes between *Demonstrated* skills (action verbs in projects/experience) and *Listed-only* skills (skills section only).
- **Candidate Comparison View:** Compare 2 to 4 candidates side by side across eligibility, skills, projects, depth, red flags, and interview round scores (`/drives/<id>/compare/?ids=...`).
- **Job Description Skill Parser:** Auto-extracts required and preferred skills directly from pasted job descriptions using taxonomy and contextual boundaries (`POST /drives/parse-jd/`).
- **Printable HR One-Page Report:** Executive screening summary with evidence excerpts, priority triage bands (High / Medium / Low), and candidate gaps (`/applications/<id>/report/`).
- **Interview Question Generator:** Generates role-specific questions targeted at candidate gaps and claims requiring depth verification.
- **Multi-Round Stage Pipeline:** Tracks candidate progression (`Applied → Eligible → Shortlisted → Aptitude → Technical → HR → Offer / Rejected`) with recorded round scorecards.
- **Fairness & Privacy:** Blind-review toggle to mask names/colleges, file signature content-sniffing validation, and DPDP Act 2023 consent capture.
- **HR Agreement Benchmark Tooling:** Automated evaluation suite (`evaluate_agreement`) calculating Precision/Recall, Top-K overlap, Spearman's rank correlation ($\rho$), and Cohen's Kappa ($\kappa$) against HR ground truth labels.

## Automated test suite

Run the complete 24-test suite:
```powershell
python manage.py test recruitment
```

## HR agreement evaluation & benchmarking

1. Generate the HR labeling CSV template:
```powershell
python manage.py evaluate_agreement --generate-template hr_labeling_template.csv
```
2. Run benchmark evaluation against HR labeled data:
```powershell
python manage.py evaluate_agreement --labels hr_labeling_template.csv
```

## Privacy and decision process

Resume files are served through an authenticated view with per-application role checks. The application records key workflow events. Candidates cannot see other candidates' files, scores, or private notes. HR users see only applications for drives they created; placement admins can review all records. Final application status is a human decision.

## Local resume extraction model

The project uses the downloaded `resume-ner-bucket/local` DistilBERT model through its quantized ONNX artifact at `resume-ner-bucket/local/onnx/model_quantized.onnx`. The model and tokenizer run locally. The HR review page shows selected extracted education, date, skill, institution, and certification spans with confidence values; these are review aids and do not alter the role-fit score. Graduation year is still checked using the existing rules and must be verified when missing or uncertain.

The bucket also includes the training/validation data and training scripts. Its existing model is already fine-tuned for resume entity extraction; use `python -m training.train_ner` from `resume-ner-bucket/local` to fine-tune from the included dataset. That command writes a separate checkpoint under `training/output/resume-ner/distilbert/best`. To point the portal at a different exported model folder, set `RESUME_NER_MODEL_DIR` to that folder; it must include tokenizer/config files and an `onnx/model_quantized.onnx` file. The checked-in model label set has a general `DATE` entity, not a dedicated graduation-year label, so validate extraction on representative local resumes before relying on it. Model and source dataset licensing should be reviewed for the intended use.

HR corrections to graduation-year extraction are saved with an audit event and used to recalculate that application’s eligibility. They are not automatically fed back into training; add verified, consented corrections to a reviewed training set before retraining.

## Resume layout guidance per drive

HR selects one of three illustrated resume layouts when creating a drive: a standard single-column layout, a projects-and-skills-first layout for early-career applicants, or an experience-first layout. The chosen preview and guidance appear on the candidate's drive page before applying. All three examples use a single-column page and clear headings to reduce layout-related extraction noise; candidates still submit a PDF or DOCX resume, and the guide does not guarantee perfect parsing.

The project database currently contains no labeled application outcomes, so a hiring predictor cannot be responsibly trained from it. To (re)build the local taxonomy index, run `py manage.py train_skill_model`; the generated artifact is saved in `recruitment/data/skill_model.json`. Benchmarking, OCR, representative labeled data, and governance review remain necessary before deployment; this prototype does not claim hiring accuracy.
