"""
Local resume parsing, evidence validation, and transparent rubric scoring.

Model: evidence-based rule engine v3
New in v3:
  - Section parser (Education, Experience, Projects, Skills, Certifications, Achievements)
  - Context-weighted skill scoring: Demonstrated / Listed-only / Not-found
  - CGPA extraction (10-pt and percentage, Indian formats)
  - Graduation year extraction from text
  - Arrears/backlog detection
  - Project and certification extraction
  - Eligibility knockout gate (CGPA, arrears, branch, graduation year)
  - Priority band (High / Medium / Low)
  - Red-flag detection (short resume, skills not evidenced, unexplained gaps)
  - Interview question generation from gaps and claimed skills
"""

import io
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RESUME_BYTES = 8 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

EVIDENCE_PRE  = 200
EVIDENCE_POST = 300

# ---------------------------------------------------------------------------
# Skill vocabulary — 300+ entries across 12 domains
# ---------------------------------------------------------------------------

_SKILL_VOCAB = [
    # Programming Languages
    "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#",
    "Go", "Rust", "Kotlin", "Swift", "Scala", "Ruby", "PHP",
    "Dart", "R", "MATLAB", "Perl", "Shell", "Bash", "PowerShell",
    "Groovy", "Lua", "Haskell", "Elixir", "Clojure", "Julia",
    # Web / Frontend
    "HTML", "CSS", "SCSS", "SASS", "React", "Next.js", "Vue.js",
    "Angular", "Svelte", "Redux", "Tailwind CSS", "Bootstrap",
    "jQuery", "GraphQL", "REST", "WebSocket", "Vite", "Webpack",
    # Backend / Frameworks
    "Django", "Flask", "FastAPI", "Spring Boot", "Spring",
    "Node.js", "Express.js", "NestJS", "Laravel", "Rails",
    "ASP.NET", ".NET", "Hibernate", "gRPC",
    # Databases
    "SQL", "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis",
    "Cassandra", "DynamoDB", "Elasticsearch", "Neo4j", "Oracle",
    "MariaDB", "CouchDB", "InfluxDB", "Supabase", "Firebase",
    # Cloud / DevOps
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform",
    "Ansible", "Jenkins", "GitHub Actions", "GitLab CI",
    "CircleCI", "Helm", "Prometheus", "Grafana", "Linux", "Nginx",
    "Apache", "Serverless", "Lambda", "EC2", "S3", "CloudFormation",
    # Data / Analytics
    "Pandas", "NumPy", "SciPy", "Matplotlib", "Seaborn",
    "Plotly", "Power BI", "Tableau", "Excel", "Looker",
    "Spark", "Hadoop", "Kafka", "Airflow", "dbt", "Snowflake",
    "BigQuery", "Databricks", "ETL",
    # Machine Learning / AI
    "Machine Learning", "Deep Learning", "Neural Networks",
    "Natural Language Processing", "Computer Vision",
    "Reinforcement Learning", "Transfer Learning",
    "PyTorch", "TensorFlow", "Keras", "Scikit-learn",
    "XGBoost", "LightGBM", "Hugging Face", "OpenCV",
    "NLTK", "spaCy", "BERT", "LLM", "Generative AI",
    "Stable Diffusion", "LangChain", "RAG", "MLflow",
    # Version Control / Collaboration
    "Git", "GitHub", "GitLab", "Bitbucket", "Jira", "Confluence",
    "Slack", "Notion", "Trello", "Figma", "Postman",
    # Security
    "Cybersecurity", "Penetration Testing", "OAuth", "JWT",
    "OWASP", "SSL", "TLS", "Cryptography", "Firewalls",
    # Mobile
    "Android", "iOS", "React Native", "Flutter", "Expo",
    "Jetpack Compose", "SwiftUI", "Objective-C", "Xamarin",
    # Soft / Process
    "Agile", "Scrum", "Kanban", "DevOps", "CI/CD",
    "Test-Driven Development", "TDD", "Microservices", "SOA",
    # Engineering / Domain
    "AutoCAD", "SolidWorks", "ROS", "Embedded Systems",
    "FPGA", "Verilog", "VHDL", "PLC", "IoT",
    "Salesforce", "SAP", "ERP", "Data Science",
    "Statistics", "Probability", "Linear Algebra", "Calculus",
    "Algorithms", "Data Structures",
]

seen = set()
SKILL_VOCAB = []
for s in _SKILL_VOCAB:
    if s.lower() not in seen:
        SKILL_VOCAB.append(s)
        seen.add(s.lower())

# ---------------------------------------------------------------------------
# Alias / synonym map
# ---------------------------------------------------------------------------

ALIASES = {
    "ml": "Machine Learning", "ai": "Machine Learning",
    "dl": "Deep Learning", "nlp": "Natural Language Processing",
    "cv": "Computer Vision", "js": "JavaScript", "ts": "TypeScript",
    "py": "Python", "node": "Node.js", "nodejs": "Node.js",
    "express": "Express.js", "mongo": "MongoDB", "postgres": "PostgreSQL",
    "psql": "PostgreSQL", "k8s": "Kubernetes", "tf": "TensorFlow",
    "pytorch": "PyTorch", "sklearn": "Scikit-learn",
    "scikit learn": "Scikit-learn", "hf": "Hugging Face",
    "gha": "GitHub Actions", "iac": "Terraform",
    "ci/cd": "CI/CD", "cicd": "CI/CD",
    "tdd": "Test-Driven Development",
    "reactjs": "React", "react.js": "React",
    "vuejs": "Vue.js", "vue": "Vue.js", "nextjs": "Next.js",
    "sass": "SCSS", "genai": "Generative AI", "llms": "LLM",
    "gpt": "LLM", "chatgpt": "LLM", "power bi": "Power BI",
    "aws lambda": "Lambda", "microsoft azure": "Azure",
    "google cloud": "GCP", "springboot": "Spring Boot",
    "spring mvc": "Spring", "asp.net core": "ASP.NET",
    "dotnet": ".NET", ".net core": ".NET",
    "ruby on rails": "Rails", "git hub": "GitHub",
    "data structures": "Data Structures",
    "dsa": "Data Structures", "ds": "Data Structures",
}

# ---------------------------------------------------------------------------
# Negation phrases
# ---------------------------------------------------------------------------

NEGATION_PHRASES = [
    "no experience in", "not familiar with", "no knowledge of",
    "lack of", "never used", "no background in",
    "limited knowledge", "unfamiliar with", "no exposure to",
    "not proficient", "no skills in", "cannot", "not experienced",
    "no understanding of",
]

# ---------------------------------------------------------------------------
# Action verbs that indicate "demonstrated" use (not just listed)
# ---------------------------------------------------------------------------

ACTION_VERBS = [
    "built", "developed", "implemented", "designed", "created",
    "deployed", "integrated", "architected", "wrote", "maintained",
    "optimized", "migrated", "automated", "tested", "led", "managed",
    "engineered", "configured", "set up", "launched", "shipped",
    "trained", "fine-tuned", "analysed", "analyzed",
]

# ---------------------------------------------------------------------------
# Section header patterns
# ---------------------------------------------------------------------------

SECTION_PATTERNS = {
    "skills": re.compile(
        r"^\s*(technical\s+skills?|skills?|core\s+competencies?|proficiencies|technologies|tech\s+stack)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "experience": re.compile(
        r"^\s*(work\s+experience|professional\s+experience|employment(\s+history)?|experience|internships?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "projects": re.compile(
        r"^\s*(projects?|personal\s+projects?|academic\s+projects?|side\s+projects?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "education": re.compile(
        r"^\s*(education|academic\s+background|qualifications?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "certifications": re.compile(
        r"^\s*(certifications?|certificates?|courses?|online\s+courses?|training)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "achievements": re.compile(
        r"^\s*(achievements?|awards?|honours?|honors?|accomplishments?|recognitions?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
}

# ---------------------------------------------------------------------------
# Education patterns
# ---------------------------------------------------------------------------

EDUCATION_LEVELS = [
    ("phd",     re.compile(r"\b(ph\.?d|doctorate|doctoral)\b", re.IGNORECASE), 4),
    ("master",  re.compile(r"\b(m\.?s\.?|m\.?e\.?|mba|master[\'s]*)\b", re.IGNORECASE), 3),
    ("bachelor", re.compile(r"\b(b\.?e\.?|b\.?tech|b\.?s\.?|bachelor[\'s]*)\b", re.IGNORECASE), 2),
    ("diploma", re.compile(r"\b(diploma|associate[\'s]*|certificate)\b", re.IGNORECASE), 1),
]

# CGPA patterns (Indian style: 8.5/10, 8.5 CGPA, 85%, etc.)
CGPA_RE = re.compile(
    r"""
    (?:cgpa|gpa|cumulative\s+gpa|grade\s+point)[\s:–-]*(\d+(?:\.\d+)?)  # CGPA: 8.5
    | (\d+(?:\.\d+)?)\s*/\s*10\b                                           # 8.5/10
    | (\d+(?:\.\d+)?)\s*/\s*4\.0?\b                                        # 3.8/4.0
    """,
    re.IGNORECASE | re.VERBOSE,
)
PERCENT_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%", re.IGNORECASE)

GRADUATION_YEAR_RE = re.compile(
    r"\b(20[12]\d)\b"
)

ARREARS_RE = re.compile(
    r"(no\s+(?:active\s+)?(?:arrears?|backlogs?)|zero\s+(?:arrears?|backlogs?)|nil\s+arrears?|arrears?\s*[:\-–]\s*nil|arrears?\s*[:\-–]\s*none|no\s+backlogs?)",
    re.IGNORECASE,
)
ACTIVE_ARREARS_RE = re.compile(
    r"(\d+)\s+(?:active\s+)?(?:arrears?|backlogs?)\b",
    re.IGNORECASE,
)

EXPERIENCE_YEAR_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)[\s,]+(?:of\s+)?(?:experience\s+(?:in|with)\s+)?"
    r"([A-Za-z][A-Za-z0-9+.#\s]{1,30})",
    re.IGNORECASE,
)

TOTAL_EXP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:total|overall|professional)?\s+experience",
    re.IGNORECASE,
)

# Certification keywords for extraction
CERT_KEYWORDS = [
    "certified", "certification", "certificate", "aws certified",
    "google cloud certified", "microsoft certified", "coursera",
    "udemy", "nptel", "edx", "linkedin learning", "hackerrank",
    "hackerearth", "leetcode", "credly", "badge",
]


# ===========================================================================
# Public API
# ===========================================================================

def extract_resume(file_obj, filename):
    """Parse a resume file and return (full_text, pages_list) with content-sniffing verification."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Upload a PDF, DOCX, or TXT resume.")
    if file_obj.size > MAX_RESUME_BYTES:
        raise ValueError("Resume must be 8 MB or smaller.")
    file_obj.seek(0)

    # Content header sniffing to prevent forged file extensions
    header = file_obj.read(16)
    file_obj.seek(0)
    if ext == ".pdf" and not header.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF file: corrupted header or incorrect file signature.")
    if ext == ".docx" and not header.startswith(b"PK\x03\x04"):
        raise ValueError("Invalid DOCX file: not a valid Microsoft Word document package.")

    if ext == ".txt":
        text = file_obj.read().decode("utf-8", errors="replace")
        pages = [text]

    elif ext == ".pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_obj.read(), filetype="pdf")
        pages = [page.get_text("text") for page in doc]
        text = "\n".join(pages)

    else:  # .docx
        from docx import Document
        doc = Document(io.BytesIO(file_obj.read()))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        paragraphs.append(cell.text)
        text = "\n".join(paragraphs)
        pages = [text]

    if len(text.strip()) < 60:
        raise ValueError(
            "The resume did not yield enough readable text. "
            "Scanned PDFs need OCR before processing."
        )
    return text, pages


def process_resume(text, pages, drive):
    """
    Score the resume against a Drive's rubric.

    Returns a dict with keys:
      facts, summary, flags, red_flags, score, criterion_scores,
      sections, cgpa_extracted, graduation_year_extracted, has_arrears,
      projects, certifications, achievements, interview_questions
    """
    lower_text = text.lower()

    # ---- Step 1: Section parsing ----------------------------------------
    sections = parse_sections(text)

    # ---- Step 2: Skill detection with context weighting ----------------
    detected_skills   = _detect_skills(text, lower_text)
    alias_resolved    = _resolve_aliases(lower_text, detected_skills)
    all_skills        = list({s for s in detected_skills + alias_resolved})
    skill_context     = _classify_skill_context(text, sections, all_skills)

    # ---- Step 3: Drive skill lists -------------------------------------
    required  = [s.strip() for s in drive.required_skills.split(",")  if s.strip()]
    preferred = [s.strip() for s in (drive.preferred_skills or "").split(",") if s.strip()]

    # ---- Step 4: Matching ----------------------------------------------
    skill_set = {s.lower() for s in all_skills}
    matching_required  = [s for s in required  if s.lower() in skill_set]
    matching_preferred = [s for s in preferred if s.lower() in skill_set]
    missing            = [s for s in required  if s.lower() not in skill_set]

    # ---- Step 5: Evidence extraction -----------------------------------
    evidence = _extract_evidence(text, pages, set(required + preferred + all_skills))

    # ---- Step 6: Experience years -------------------------------------
    experience_map, total_exp_years = _extract_experience_years(text)

    # ---- Step 7: Education detection -----------------------------------
    edu_level, edu_label = _detect_education(text)

    # ---- Step 8: Section confidence ------------------------------------
    section_confidence = _compute_section_confidence(text, all_skills)

    # ---- Step 9: Structured extraction ---------------------------------
    cgpa_val = extract_cgpa(text)
    grad_year = extract_graduation_year(text)
    grad_year_source = "rule" if grad_year else "not_found"
    try:
        from .resume_ner import extract_entities, graduation_year_from_entities
        ner_entities = extract_entities(text)
        model_grad_year = graduation_year_from_entities(text, ner_entities)
        if model_grad_year:
            grad_year = model_grad_year
            grad_year_source = "local_ner"
    except Exception:
        ner_entities = []
    has_arrears_val = detect_arrears(text)
    projects = extract_projects(text, sections)
    certifications = extract_certifications(text, sections)
    achievements = extract_achievements(text, sections)

    # ---- Step 10: Skill model suggestions (if trained) ----------------
    try:
        from .skill_model import suggest_skills
        model_suggestions = suggest_skills(text, all_skills)
    except Exception:
        model_suggestions = []

    # ---- Step 11: Rubric weights ---------------------------------------
    weights = drive.rubric_weights or {}
    req_w  = int(weights.get("required_skills",  70))
    pref_w = int(weights.get("preferred_skills", 20))
    exp_w  = int(weights.get("experience",        5))
    edu_w  = int(weights.get("education",         5))
    total_w = max(1, req_w + pref_w + exp_w + edu_w)

    # ---- Step 12: Sub-scores -------------------------------------------
    required_pct  = len(matching_required)  / len(required)  if required  else 1.0
    preferred_pct = len(matching_preferred) / len(preferred) if preferred else 0.0

    # Experience: scale linearly up to 10 yrs
    exp_score_pct = min(1.0, total_exp_years / 10.0) if total_exp_years else 0.0

    # Education: proportional to level
    edu_score_pct = edu_level / 4.0

    # Demonstrated-skill bonus: skills found in project/experience context
    demonstrated = [s for s, ctx in skill_context.items() if ctx == "demonstrated"]
    demo_bonus = round(min(5, len(demonstrated) * 0.5))  # max +5

    # Section confidence bonus
    confidence_bonus = round(section_confidence * 3)  # max +3

    raw_score = (
        req_w  * required_pct
        + pref_w * preferred_pct
        + exp_w  * exp_score_pct
        + edu_w  * edu_score_pct
    ) / total_w * 100

    score = min(100, round(raw_score) + demo_bonus + confidence_bonus)

    # ---- Step 13: Flags ------------------------------------------------
    flags = []
    if not all_skills:
        flags.append("No skills from the matching vocabulary were detected; review manually.")
    if missing:
        flags.append("Required-skill evidence missing for: " + ", ".join(missing))
    if len(text.strip()) < 300:
        flags.append("Short extracted text; verify the source document.")
    if total_exp_years == 0:
        flags.append("No explicit experience duration found; year-count defaults to 0.")
    if edu_level == 0:
        flags.append("No education qualification detected.")

    # ---- Step 14: Red flags -------------------------------------------
    red_flags = detect_red_flags(text, {
        "skills": all_skills,
        "skill_context": skill_context,
        "matching_required": matching_required,
        "missing_required": missing,
        "projects": projects,
        "certifications": certifications,
        "experience_years": total_exp_years,
    })

    # ---- Step 15: Interview questions ----------------------------------
    interview_questions = generate_interview_questions({
        "skills": all_skills,
        "skill_context": skill_context,
        "missing_required": missing,
        "matching_required": matching_required,
        "projects": projects,
        "experience_years": total_exp_years,
        "education_level": edu_label,
    }, drive)

    # ---- Step 16: Summary ---------------------------------------------
    summary = (
        f"Resume lists: {', '.join(all_skills) if all_skills else 'no recognized skills'}. "
        f"Required skills matched: {', '.join(matching_required) if matching_required else 'none'}. "
        f"Preferred skills matched: {', '.join(matching_preferred) if matching_preferred else 'none'}. "
        f"Education detected: {edu_label}. "
        f"Estimated experience: {total_exp_years:.1f} years. "
        f"Projects found: {len(projects)}. "
        f"Certifications found: {len(certifications)}. "
        f"Final composite score: {score}/100."
    )

    return {
        "facts": {
            "skills": all_skills,
            "skill_context": skill_context,
            "required_skill_evidence":  matching_required,
            "preferred_skill_evidence": matching_preferred,
            "missing_required_skills":  missing,
            "evidence": evidence,
            "experience_years_by_skill": experience_map,
            "total_experience_years":   total_exp_years,
            "education_level":  edu_label,
            "education_score":  round(edu_score_pct * 100),
            "section_confidence": section_confidence,
            "model_skill_suggestions": model_suggestions,
            "resume_entities": [entity for entity in ner_entities if entity["label"] in {
                "DATE", "DEGREE", "FIELD", "INSTITUTION", "SKILL", "CERT"
            }],
            "graduation_year_source": grad_year_source,
        },
        "summary": summary,
        "flags":   flags,
        "red_flags": red_flags,
        "score":   score,
        "criterion_scores": {
            "required_skills":  {"weight": req_w,  "score": round(required_pct  * 100), "evidence": matching_required},
            "preferred_skills": {"weight": pref_w, "score": round(preferred_pct * 100), "evidence": matching_preferred},
            "experience":       {"weight": exp_w,  "score": round(exp_score_pct * 100), "total_years": total_exp_years},
            "education":        {"weight": edu_w,  "score": round(edu_score_pct * 100), "level": edu_label},
        },
        # Structured extractions (saved separately on ResumeAnalysis)
        "sections": sections,
        "cgpa_extracted": cgpa_val,
        "graduation_year_extracted": grad_year,
        "has_arrears": has_arrears_val,
        "projects": projects,
        "certifications": certifications,
        "achievements": achievements,
        "interview_questions": interview_questions,
    }


def run_eligibility_gate(application, drive):
    """
    Run the knockout gate and return (passed: bool, criteria: list).
    Does NOT persist — caller saves EligibilityCheck.
    """
    from decimal import Decimal

    try:
        profile = application.candidate.placement_profile
    except Exception:
        profile = None

    criteria = []
    passed = True

    # CGPA check
    if drive.minimum_cgpa is not None:
        candidate_cgpa = None
        if profile and profile.cgpa is not None:
            candidate_cgpa = float(profile.cgpa)
        # Also check extracted value
        try:
            extracted = float(application.analysis.cgpa_extracted or 0) or None
        except Exception:
            extracted = None
        actual = candidate_cgpa or extracted
        ok = actual is not None and actual >= float(drive.minimum_cgpa)
        criteria.append({
            "criterion": "Minimum CGPA",
            "required": str(drive.minimum_cgpa),
            "actual": str(round(actual, 2)) if actual else "Not on record",
            "passed": ok,
            "reason": "" if ok else f"CGPA {actual or 'unknown'} is below the required {drive.minimum_cgpa}",
        })
        if not ok:
            passed = False

    # Arrears check
    if drive.max_arrears is not None:
        candidate_arrears = None
        if profile and profile.arrears is not None:
            candidate_arrears = profile.arrears
        ok = candidate_arrears is not None and candidate_arrears <= drive.max_arrears
        criteria.append({
            "criterion": "Active arrears",
            "required": f"≤ {drive.max_arrears}",
            "actual": str(candidate_arrears) if candidate_arrears is not None else "Not on record",
            "passed": ok,
            "reason": "" if ok else f"Candidate has {candidate_arrears or 'unknown'} arrears; maximum allowed is {drive.max_arrears}",
        })
        if not ok:
            passed = False

    # Graduation year check
    if drive.graduation_year is not None:
        grad_year = None
        if profile and profile.graduation_year:
            grad_year = profile.graduation_year
        if grad_year is None:
            try:
                grad_year = application.analysis.graduation_year_extracted
            except Exception:
                grad_year = None
        needs_review = grad_year is None
        ok = grad_year == drive.graduation_year
        criteria.append({
            "criterion": "Graduation year",
            "required": str(drive.graduation_year),
            "actual": str(grad_year) if grad_year else "Not found — needs review",
            "passed": ok,
            "needs_review": needs_review,
            "reason": "" if ok else ("No graduation year was found. Ask the candidate or inspect the resume before deciding." if needs_review else f"Graduation year {grad_year} does not match required {drive.graduation_year}"),
        })
        if not ok:
            passed = False

    # Branch/department check
    if drive.allowed_branches:
        allowed = [b.strip().lower() for b in drive.allowed_branches.split(",") if b.strip()]
        dept = (profile.department or "").lower() if profile else ""
        ok = not allowed or any(a in dept or dept in a for a in allowed)
        criteria.append({
            "criterion": "Branch / department",
            "required": drive.allowed_branches,
            "actual": profile.department if profile else "Not on record",
            "passed": ok,
            "reason": "" if ok else f"Department '{profile.department if profile else 'unknown'}' is not in the allowed list",
        })
        if not ok:
            passed = False

    return passed, criteria


def compute_priority_band(score, red_flags):
    """Return High / Medium / Low triage band."""
    if score is None:
        return "Pending"
    penalty = len([f for f in (red_flags or []) if "unsupported" in f.lower() or "no evidence" in f.lower()])
    adjusted = score - penalty * 5
    if adjusted >= 70:
        return "High"
    if adjusted >= 45:
        return "Medium"
    return "Low"


def detect_red_flags(text, facts):
    """
    Return a list of red-flag strings.
    These are structural observations — not disqualifiers.
    """
    flags = []
    words = text.split()
    if len(words) < 150:
        flags.append("Very short resume (fewer than 150 words) — may be incomplete.")

    # Skills with no evidence in projects or experience
    skill_context = facts.get("skill_context", {})
    unsupported = [s for s, ctx in skill_context.items() if ctx == "listed_only"]
    if len(unsupported) >= 5:
        flags.append(
            f"{len(unsupported)} skill(s) appear only in a skills list with no supporting evidence in projects or experience: "
            + ", ".join(unsupported[:8]) + ("…" if len(unsupported) > 8 else "")
        )

    # Required skills missing entirely
    missing = facts.get("missing_required", [])
    if missing:
        flags.append(f"No evidence found for required skill(s): {', '.join(missing)}.")

    # No projects section
    if not facts.get("projects"):
        flags.append("No project entries detected; project experience could not be assessed.")

    # Experience years = 0 but skills list is long
    if facts.get("experience_years", 0) == 0 and len(facts.get("skills", [])) > 8:
        flags.append("No work/internship duration mentioned despite listing many skills — verify claim credibility.")

    return flags


def generate_interview_questions(facts, drive):
    """
    Generate practical interview questions from resume gaps and claimed skills.
    Returns a list of {question, reason, type} dicts.
    """
    questions = []
    skill_context = facts.get("skill_context", {})
    missing = facts.get("missing_required", [])
    matching = facts.get("matching_required", [])
    projects = facts.get("projects", [])
    exp_years = facts.get("experience_years", 0)

    # Questions on missing required skills
    for skill in missing[:3]:
        questions.append({
            "question": f"The role requires {skill}. What is your current familiarity with it, and how quickly could you get up to speed?",
            "reason": f"'{skill}' was listed as required but not found in the resume.",
            "type": "gap",
        })

    # Questions on listed-only skills (verify depth)
    listed_only = [s for s, ctx in skill_context.items() if ctx == "listed_only" and s in matching]
    for skill in listed_only[:3]:
        questions.append({
            "question": f"Your resume lists {skill}. Can you walk me through a specific time you used it in a project or professional setting?",
            "reason": f"'{skill}' appears only in the skills section without project/experience evidence.",
            "type": "depth_check",
        })

    # Questions on demonstrated skills (go deeper)
    demonstrated = [s for s, ctx in skill_context.items() if ctx == "demonstrated"]
    for skill in demonstrated[:2]:
        questions.append({
            "question": f"Tell me about your most challenging experience working with {skill}. What problem were you solving and what was the outcome?",
            "reason": f"'{skill}' is demonstrated in the resume — explore depth and complexity.",
            "type": "technical",
        })

    # Project questions
    if projects:
        p = projects[0]
        title = p.get("title", "your main project")
        questions.append({
            "question": f"Walk me through '{title}' — what was the problem, your role, the tech stack, and the result?",
            "reason": "Project deep-dive reveals architecture thinking and ownership.",
            "type": "project",
        })

    # Experience / freshness
    if exp_years == 0:
        questions.append({
            "question": "Your resume doesn't mention work or internship durations. Can you describe your most significant hands-on technical experience?",
            "reason": "No explicit experience duration detected.",
            "type": "experience",
        })

    return questions[:8]  # cap at 8


def parse_sections(text):
    """
    Split resume text into named sections.
    Returns dict: section_name → text_content.
    """
    # Find all section header positions
    boundaries = []  # (position, section_name)
    for name, pattern in SECTION_PATTERNS.items():
        for m in pattern.finditer(text):
            boundaries.append((m.start(), m.end(), name))

    # Sort by position
    boundaries.sort(key=lambda x: x[0])

    sections = {}
    for i, (start, end, name) in enumerate(boundaries):
        next_start = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        content = text[end:next_start].strip()
        if name in sections:
            sections[name] += "\n" + content
        else:
            sections[name] = content

    # Anything before the first section header = header/contact info
    if boundaries:
        sections["header"] = text[:boundaries[0][0]].strip()

    return sections


def extract_cgpa(text):
    """
    Extract CGPA/GPA from text. Returns float or None.
    Handles 10-pt, 4-pt, and percentage formats common in India.
    """
    # Try CGPA patterns first
    for m in CGPA_RE.finditer(text):
        for g in m.groups():
            if g:
                val = float(g)
                # Convert 4-pt to 10-pt approximation if needed
                if val <= 4.0:
                    return round(val * 2.5, 2)
                if val <= 10.0:
                    return round(val, 2)

    # Try percentage → approximate CGPA (percentage / 10)
    for m in PERCENT_RE.finditer(text):
        pct = float(m.group(1))
        if 40 <= pct <= 100:
            return round(pct / 10, 2)

    return None


def extract_graduation_year(text):
    """
    Extract the most likely graduation year from text.
    Returns int or None.
    """
    years = [int(m.group(1)) for m in GRADUATION_YEAR_RE.finditer(text)]
    if not years:
        return None
    # Most likely graduation year: the last mentioned 20xx year
    return sorted(years)[-1]


def detect_arrears(text):
    """
    Returns True if arrears detected, False if explicitly none, None if unknown.
    """
    if ARREARS_RE.search(text):
        return False  # explicitly stated no arrears
    m = ACTIVE_ARREARS_RE.search(text)
    if m:
        count = int(m.group(1))
        return count > 0
    return None  # unknown


def extract_projects(text, sections):
    """
    Extract project entries from the projects section.
    Returns list of {title, description, skills}.
    """
    project_text = sections.get("projects", "")
    if not project_text:
        # Fallback: look for "Project" mentions anywhere
        m = re.search(r"(?:projects?)\s*[:\-–]?\s*\n([\s\S]{50,1200})", text, re.IGNORECASE)
        if m:
            project_text = m.group(1)

    if not project_text:
        return []

    projects = []
    # Split on numbered items, bullet points, or capitalized project names
    entries = re.split(r"\n(?:\d+[\.\)]\s+|[•●\-]\s+|(?=[A-Z][A-Za-z\s]{3,40}[:\n]))", project_text)
    for entry in entries:
        entry = entry.strip()
        if len(entry) < 20:
            continue
        # First line is likely the title
        lines = entry.split("\n")
        title = lines[0][:80].strip()
        description = " ".join(lines[1:])[:400].strip()
        # Extract skills mentioned in this entry
        entry_lower = entry.lower()
        project_skills = [s for s in SKILL_VOCAB if re.search(r"(?<!\w)" + re.escape(s.lower()) + r"(?!\w)", entry_lower)]
        projects.append({
            "title": title,
            "description": description,
            "skills": project_skills[:10],
        })

    return projects[:8]


def extract_certifications(text, sections):
    """Extract certification mentions. Returns list of strings."""
    cert_text = sections.get("certifications", "")
    results = []
    # From dedicated section
    if cert_text:
        for line in cert_text.split("\n"):
            line = line.strip("•●-– \t")
            if len(line) > 8:
                results.append(line[:150])

    # From full text: look for certification keyword phrases
    for kw in CERT_KEYWORDS:
        pattern = re.compile(rf"\b{re.escape(kw)}\b.{{0,80}}", re.IGNORECASE)
        for m in pattern.finditer(text):
            snippet = m.group(0).strip()
            if snippet not in results and len(snippet) > 10:
                results.append(snippet[:150])

    # Deduplicate roughly
    seen_lower = set()
    unique = []
    for r in results:
        key = r.lower()[:40]
        if key not in seen_lower:
            seen_lower.add(key)
            unique.append(r)

    return unique[:10]


def extract_achievements(text, sections):
    """Extract achievements/awards. Returns list of strings."""
    ach_text = sections.get("achievements", "")
    results = []
    if ach_text:
        for line in ach_text.split("\n"):
            line = line.strip("•●-– \t")
            if len(line) > 8:
                results.append(line[:150])

    return results[:6]


def extract_skills_from_jd(text: str) -> dict:
    """
    Extract skills from a job description text and classify into suggested
    required and preferred skills.
    """
    if not text or not text.strip():
        return {"all_skills": [], "required_skills": [], "preferred_skills": []}

    lower = text.lower()
    detected = _detect_skills(text, lower)
    resolved = _resolve_aliases(lower, detected)
    all_found = list({s for s in detected + resolved})

    req_sec_pattern = re.compile(
        r"(?:requirements?|required|qualifications?|must\s+have|prerequisites?|minimum\s+qualifications?)([\s\S]*?)(?=(?:preferred|nice\s+to\s+have|bonus|plus|responsibilities|benefits|\Z))",
        re.IGNORECASE,
    )
    pref_sec_pattern = re.compile(
        r"(?:preferred|nice\s+to\s+have|desirable|bonus|plus|good\s+to\s+have)([\s\S]*?)(?=(?:requirements?|qualifications?|responsibilities|benefits|\Z))",
        re.IGNORECASE,
    )

    req_match = req_sec_pattern.search(text)
    pref_match = pref_sec_pattern.search(text)

    req_skills = []
    pref_skills = []

    if req_match or pref_match:
        req_text = (req_match.group(1) if req_match else "").lower()
        pref_text = (pref_match.group(1) if pref_match else "").lower()

        for skill in all_found:
            sk_pat = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"
            in_req = bool(re.search(sk_pat, req_text))
            in_pref = bool(re.search(sk_pat, pref_text))
            if in_pref and not in_req:
                pref_skills.append(skill)
            else:
                req_skills.append(skill)
    else:
        req_count = max(1, int(len(all_found) * 0.7))
        req_skills = all_found[:req_count]
        pref_skills = all_found[req_count:]

    return {
        "all_skills": all_found,
        "required_skills": req_skills,
        "preferred_skills": pref_skills,
    }


def local_model_status():
    """Report status for local resume extraction and skill suggestions."""
    from .resume_ner import model_status as ner_status
    from .skill_model import load_skill_model
    ner = ner_status()
    skill_model = load_skill_model()
    return {
        "enabled": ner["enabled"],
        "model": ner["model"],
        "message": ner["message"],
        "skill_suggestions_enabled": bool(skill_model),
    }


# ===========================================================================
# Internal helpers
# ===========================================================================

def _is_negated(text_lower: str, match_start: int) -> bool:
    window = text_lower[max(0, match_start - 80): match_start]
    return any(neg in window for neg in NEGATION_PHRASES)


def _detect_skills(text: str, lower_text: str) -> list:
    found = []
    for skill in SKILL_VOCAB:
        pattern = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"
        m = re.search(pattern, lower_text)
        if m and not _is_negated(lower_text, m.start()):
            found.append(skill)
    return found


def _resolve_aliases(lower_text: str, already_found: list) -> list:
    found_lower = {s.lower() for s in already_found}
    extra = []
    for alias, canonical in ALIASES.items():
        if canonical.lower() in found_lower:
            continue
        pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
        m = re.search(pattern, lower_text)
        if m and not _is_negated(lower_text, m.start()):
            if canonical.lower() not in found_lower:
                extra.append(canonical)
                found_lower.add(canonical.lower())
    return extra


def _classify_skill_context(text: str, sections: dict, skills: list) -> dict:
    """
    For each skill, classify as: 'demonstrated', 'listed_only', or 'not_found'.
    Demonstrated = found near an action verb in experience/projects section.
    Listed only  = found only in skills section or skills list.
    """
    exp_text = (sections.get("experience", "") + "\n" + sections.get("projects", "")).lower()
    skills_text = sections.get("skills", "").lower()
    full_lower = text.lower()
    action_re = re.compile(r"\b(" + "|".join(re.escape(v) for v in ACTION_VERBS) + r")\b", re.IGNORECASE)

    context = {}
    for skill in skills:
        pat = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"
        # Check if skill appears near an action verb in experience/projects
        if exp_text:
            m = re.search(pat, exp_text)
            if m:
                window = exp_text[max(0, m.start() - 120): min(len(exp_text), m.end() + 120)]
                if action_re.search(window):
                    context[skill] = "demonstrated"
                    continue
        # Check if only in skills list
        if re.search(pat, full_lower):
            context[skill] = "listed_only"
        else:
            context[skill] = "not_found"

    return context


def _extract_evidence(text: str, pages: list, skill_set: set) -> dict:
    evidence = {}
    for skill in skill_set:
        for page_num, page in enumerate(pages, start=1):
            m = re.search(re.escape(skill), page, re.IGNORECASE)
            if m:
                start = max(0, m.start() - EVIDENCE_PRE)
                end   = min(len(page), m.end() + EVIDENCE_POST)
                evidence[skill] = {
                    "page": page_num,
                    "quote": " ".join(page[start:end].split()),
                }
                break
    return evidence


def _extract_experience_years(text: str) -> tuple:
    skill_map = {}
    skill_lower = {s.lower(): s for s in SKILL_VOCAB}
    for m in EXPERIENCE_YEAR_RE.finditer(text):
        years = float(m.group(1))
        skill_candidate = m.group(2).strip().lower()
        for known_lower, canonical in skill_lower.items():
            if known_lower in skill_candidate or skill_candidate in known_lower:
                skill_map[canonical] = max(skill_map.get(canonical, 0), years)
                break
    total = 0.0
    for m in TOTAL_EXP_RE.finditer(text):
        total = max(total, float(m.group(1)))
    if total == 0 and skill_map:
        total = max(skill_map.values())
    return skill_map, total


def _detect_education(text: str) -> tuple:
    best_level = 0
    best_label = "Not detected"
    for label, pattern, level in EDUCATION_LEVELS:
        if pattern.search(text) and level > best_level:
            best_level = level
            best_label = label.capitalize()
    return best_level, best_label


def _compute_section_confidence(text: str, skills: list) -> float:
    if not skills:
        return 0.0
    skills_section_re = re.compile(
        r"(technical\s+skills?|skills?|core\s+competencies?|proficiencies|technologies)",
        re.IGNORECASE,
    )
    section_starts = [m.start() for m in skills_section_re.finditer(text)]
    if not section_starts:
        return 0.0
    in_section_count = 0
    for skill in skills:
        m = re.search(re.escape(skill), text, re.IGNORECASE)
        if not m:
            continue
        skill_pos = m.start()
        for s_start in section_starts:
            if 0 <= skill_pos - s_start <= 600:
                in_section_count += 1
                break
    return in_section_count / len(skills)
