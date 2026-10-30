"""
Local resume parsing, evidence validation, and transparent rubric scoring.

Model: evidence-based rule engine v2
Changes from v1:
  - 300+ skill vocabulary across 12 tech domains
  - Alias/synonym resolution (ML → Machine Learning, JS → JavaScript …)
  - Negation guard: skips skill if preceded by a negative phrase
  - Experience-year extraction via regex (e.g. "5 years of Python")
  - Education-level detection (PhD > Master > Bachelor > Diploma)
  - Section-aware confidence weighting (Skills section > random mention)
  - Configurable rubric now supports required_skills, preferred_skills,
    experience, and education dimensions
  - Expanded evidence context window (200 pre / 300 post characters)
"""

import io
import json
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RESUME_BYTES = 8 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# Evidence context window (characters before/after a match)
EVIDENCE_PRE  = 200
EVIDENCE_POST = 300

# ---------------------------------------------------------------------------
# Skill vocabulary — 300+ entries across 12 domains
# ---------------------------------------------------------------------------

_SKILL_VOCAB = [
    # --- Programming Languages ---
    "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#",
    "Go", "Rust", "Kotlin", "Swift", "Scala", "Ruby", "PHP",
    "Dart", "R", "MATLAB", "Perl", "Shell", "Bash", "PowerShell",
    "Groovy", "Lua", "Haskell", "Elixir", "Clojure", "Julia",

    # --- Web / Frontend ---
    "HTML", "CSS", "SCSS", "SASS", "React", "Next.js", "Vue.js",
    "Angular", "Svelte", "Redux", "Tailwind CSS", "Bootstrap",
    "jQuery", "GraphQL", "REST", "WebSocket", "Vite", "Webpack",

    # --- Backend / Frameworks ---
    "Django", "Flask", "FastAPI", "Spring Boot", "Spring",
    "Node.js", "Express.js", "NestJS", "Laravel", "Rails",
    "ASP.NET", ".NET", "Hibernate", "gRPC",

    # --- Databases ---
    "SQL", "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis",
    "Cassandra", "DynamoDB", "Elasticsearch", "Neo4j", "Oracle",
    "MariaDB", "CouchDB", "InfluxDB", "Supabase", "Firebase",

    # --- Cloud / DevOps ---
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform",
    "Ansible", "Jenkins", "GitHub Actions", "GitLab CI",
    "CircleCI", "Helm", "Prometheus", "Grafana", "Linux", "Nginx",
    "Apache", "Serverless", "Lambda", "EC2", "S3", "CloudFormation",

    # --- Data / Analytics ---
    "Pandas", "NumPy", "SciPy", "Matplotlib", "Seaborn",
    "Plotly", "Power BI", "Tableau", "Excel", "Looker",
    "Spark", "Hadoop", "Kafka", "Airflow", "dbt", "Snowflake",
    "BigQuery", "Databricks", "ETL",

    # --- Machine Learning / AI ---
    "Machine Learning", "Deep Learning", "Neural Networks",
    "Natural Language Processing", "Computer Vision",
    "Reinforcement Learning", "Transfer Learning",
    "PyTorch", "TensorFlow", "Keras", "Scikit-learn",
    "XGBoost", "LightGBM", "Hugging Face", "OpenCV",
    "NLTK", "spaCy", "BERT", "LLM", "Generative AI",
    "Stable Diffusion", "LangChain", "RAG", "MLflow",

    # --- Version Control / Collaboration ---
    "Git", "GitHub", "GitLab", "Bitbucket", "Jira", "Confluence",
    "Slack", "Notion", "Trello", "Figma", "Postman",

    # --- Security ---
    "Cybersecurity", "Penetration Testing", "OAuth", "JWT",
    "OWASP", "SSL", "TLS", "Cryptography", "Firewalls",

    # --- Mobile ---
    "Android", "iOS", "React Native", "Flutter", "Expo",
    "Jetpack Compose", "SwiftUI", "Objective-C", "Xamarin",

    # --- Soft / Process ---
    "Agile", "Scrum", "Kanban", "DevOps", "CI/CD",
    "Test-Driven Development", "TDD", "Microservices", "SOA",

    # --- Engineering / Domain specific ---
    "MATLAB", "AutoCAD", "SolidWorks", "ROS", "Embedded Systems",
    "FPGA", "Verilog", "VHDL", "PLC", "IoT",
    "Salesforce", "SAP", "ERP", "Tableau", "Data Science",
    "Statistics", "Probability", "Linear Algebra", "Calculus",
]

# Deduplicate while preserving order
seen = set()
SKILL_VOCAB = []
for s in _SKILL_VOCAB:
    if s.lower() not in seen:
        SKILL_VOCAB.append(s)
        seen.add(s.lower())

# ---------------------------------------------------------------------------
# Alias / synonym map  →  canonical form
# Matching on the alias will report the canonical skill name.
# ---------------------------------------------------------------------------

ALIASES = {
    "ml": "Machine Learning",
    "ai": "Machine Learning",
    "dl": "Deep Learning",
    "nlp": "Natural Language Processing",
    "cv": "Computer Vision",
    "js": "JavaScript",
    "ts": "TypeScript",
    "py": "Python",
    "node": "Node.js",
    "nodejs": "Node.js",
    "express": "Express.js",
    "mongo": "MongoDB",
    "postgres": "PostgreSQL",
    "psql": "PostgreSQL",
    "k8s": "Kubernetes",
    "tf": "TensorFlow",
    "pytorch": "PyTorch",
    "sklearn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "hf": "Hugging Face",
    "gha": "GitHub Actions",
    "iac": "Terraform",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "tdd": "Test-Driven Development",
    "reactjs": "React",
    "react.js": "React",
    "vuejs": "Vue.js",
    "vue": "Vue.js",
    "nextjs": "Next.js",
    "sass": "SCSS",
    "genai": "Generative AI",
    "llms": "LLM",
    "gpt": "LLM",
    "chatgpt": "LLM",
    "power bi": "Power BI",
    "tableau": "Tableau",
    "aws lambda": "Lambda",
    "microsoft azure": "Azure",
    "google cloud": "GCP",
    "springboot": "Spring Boot",
    "spring mvc": "Spring",
    "asp.net core": "ASP.NET",
    "dotnet": ".NET",
    ".net core": ".NET",
    "ruby on rails": "Rails",
    "git hub": "GitHub",
    "data structures": "Algorithms",
}

# ---------------------------------------------------------------------------
# Negation phrases — if any of these precede a skill match within 60 chars,
# the match is discarded as a false positive.
# ---------------------------------------------------------------------------

NEGATION_PHRASES = [
    "no experience in", "not familiar with", "no knowledge of",
    "lack of", "without", "never used", "no background in",
    "limited knowledge", "unfamiliar with", "no exposure to",
    "not proficient", "no skills in", "cannot", "not experienced",
    "no understanding of",
]

# ---------------------------------------------------------------------------
# Section headers — skills mentioned under a dedicated section get higher confidence
# ---------------------------------------------------------------------------

SKILLS_SECTION_RE = re.compile(
    r"(technical\s+skills?|skills?|core\s+competencies?|proficiencies|technologies)",
    re.IGNORECASE,
)

EXPERIENCE_SECTION_RE = re.compile(
    r"(work\s+experience|professional\s+experience|employment|experience)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Education patterns
# ---------------------------------------------------------------------------

EDUCATION_LEVELS = [
    ("phd",     re.compile(r"\b(ph\.?d|doctorate|doctoral)\b", re.IGNORECASE), 4),
    ("master",  re.compile(r"\b(m\.?s\.?|m\.?e\.?|mba|master[\'s]*)\b", re.IGNORECASE), 3),
    ("bachelor",re.compile(r"\b(b\.?e\.?|b\.?tech|b\.?s\.?|bachelor[\'s]*)\b", re.IGNORECASE), 2),
    ("diploma", re.compile(r"\b(diploma|associate[\'s]*|certificate)\b", re.IGNORECASE), 1),
]

# ---------------------------------------------------------------------------
# Experience year patterns
# ---------------------------------------------------------------------------

EXPERIENCE_YEAR_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience\s+(?:in|with)\s+)?"
    r"([A-Za-z][A-Za-z0-9+.#\s]{1,30})",
    re.IGNORECASE,
)

TOTAL_EXP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:total|overall|professional)?\s+experience",
    re.IGNORECASE,
)


# ===========================================================================
# Public API
# ===========================================================================

def extract_resume(file_obj, filename):
    """Parse a resume file and return (full_text, pages_list)."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Upload a PDF, DOCX, or TXT resume.")
    if file_obj.size > MAX_RESUME_BYTES:
        raise ValueError("Resume must be 8 MB or smaller.")
    file_obj.seek(0)

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
        # Also capture table cells
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
      facts, summary, flags, score, criterion_scores
    """
    lower_text = text.lower()

    # ---- Step 1: Skill detection ----------------------------------------
    detected_skills   = _detect_skills(text, lower_text)
    alias_resolved    = _resolve_aliases(lower_text, detected_skills)
    all_skills        = list({s for s in detected_skills + alias_resolved})

    # ---- Step 2: Drive skill lists --------------------------------------
    required  = [s.strip() for s in drive.required_skills.split(",")  if s.strip()]
    preferred = [s.strip() for s in (drive.preferred_skills or "").split(",") if s.strip()]

    # ---- Step 3: Matching -----------------------------------------------
    skill_set = {s.lower() for s in all_skills}
    matching_required  = [s for s in required  if s.lower() in skill_set]
    matching_preferred = [s for s in preferred if s.lower() in skill_set]
    missing            = [s for s in required  if s.lower() not in skill_set]

    # ---- Step 4: Evidence extraction ------------------------------------
    evidence = _extract_evidence(text, pages, set(required + preferred + all_skills))

    # ---- Step 5: Experience year extraction -----------------------------
    experience_map, total_exp_years = _extract_experience_years(text)

    # ---- Step 6: Education detection ------------------------------------
    edu_level, edu_label = _detect_education(text)

    # ---- Step 7: Section confidence -------------------------------------
    section_confidence = _compute_section_confidence(text, all_skills)

    # ---- Step 8: Rubric weights -----------------------------------------
    weights = drive.rubric_weights or {}
    req_w  = int(weights.get("required_skills",  70))
    pref_w = int(weights.get("preferred_skills", 20))
    exp_w  = int(weights.get("experience",        5))
    edu_w  = int(weights.get("education",         5))
    total_w = max(1, req_w + pref_w + exp_w + edu_w)

    # ---- Step 9: Sub-scores ---------------------------------------------
    required_pct  = len(matching_required)  / len(required)  if required  else 1.0
    preferred_pct = len(matching_preferred) / len(preferred) if preferred else 0.0

    # Experience: award 100% if candidate has 1+ year, scale linearly up to 10 yrs
    exp_score_pct = min(1.0, total_exp_years / 10.0) if total_exp_years else 0.0

    # Education: award proportionally to level (max level = 4 → PhD)
    edu_score_pct = edu_level / 4.0

    # Section confidence bonus: if ≥50% of matched skills appear under a skills
    # section, apply a small boost (capped so total stays ≤100)
    confidence_bonus = round(section_confidence * 5)  # max +5 points

    raw_score = (
        req_w  * required_pct
        + pref_w * preferred_pct
        + exp_w  * exp_score_pct
        + edu_w  * edu_score_pct
    ) / total_w * 100

    score = min(100, round(raw_score) + confidence_bonus)

    # ---- Step 10: Flags -------------------------------------------------
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

    # ---- Step 11: Summary -----------------------------------------------
    summary = (
        f"Resume lists: {', '.join(all_skills) if all_skills else 'no recognized skills'}. "
        f"Required skills matched: {', '.join(matching_required) if matching_required else 'none'}. "
        f"Preferred skills matched: {', '.join(matching_preferred) if matching_preferred else 'none'}. "
        f"Education detected: {edu_label}. "
        f"Estimated experience: {total_exp_years:.1f} years. "
        f"Final composite score: {score}/100."
    )

    return {
        "facts": {
            "skills": all_skills,
            "required_skill_evidence":  matching_required,
            "preferred_skill_evidence": matching_preferred,
            "missing_required_skills":  missing,
            "evidence": evidence,
            "experience_years_by_skill": experience_map,
            "total_experience_years":   total_exp_years,
            "education_level":  edu_label,
            "education_score":  round(edu_score_pct * 100),
            "section_confidence": section_confidence,
        },
        "summary": summary,
        "flags":   flags,
        "score":   score,
        "criterion_scores": {
            "required_skills":  {"weight": req_w,  "score": round(required_pct  * 100), "evidence": matching_required},
            "preferred_skills": {"weight": pref_w, "score": round(preferred_pct * 100), "evidence": matching_preferred},
            "experience":       {"weight": exp_w,  "score": round(exp_score_pct * 100), "total_years": total_exp_years},
            "education":        {"weight": edu_w,  "score": round(edu_score_pct * 100), "level": edu_label},
        },
    }


def local_model_status():
    """Report local Ollama endpoint status without sending data anywhere."""
    endpoint = os.environ.get("OLLAMA_URL",   "http://127.0.0.1:11434")
    model    = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
    return {
        "enabled":  bool(os.environ.get("OLLAMA_MODEL")),
        "endpoint": endpoint,
        "model":    model,
        "message":  "Local Ollama is optional. This release uses evidence-checked local rules v2.",
    }


# ===========================================================================
# Internal helpers
# ===========================================================================

def _is_negated(text_lower: str, match_start: int) -> bool:
    """Return True if the skill match is preceded by a negation phrase."""
    window = text_lower[max(0, match_start - 80): match_start]
    return any(neg in window for neg in NEGATION_PHRASES)


def _detect_skills(text: str, lower_text: str) -> list:
    """Match skills from the vocabulary against resume text, with negation guard."""
    found = []
    for skill in SKILL_VOCAB:
        pattern = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"
        m = re.search(pattern, lower_text)
        if m and not _is_negated(lower_text, m.start()):
            found.append(skill)
    return found


def _resolve_aliases(lower_text: str, already_found: list) -> list:
    """
    Scan for alias/abbreviation mentions and map them to canonical skill names.
    Returns a list of canonical skills not already in already_found.
    """
    found_lower = {s.lower() for s in already_found}
    extra = []
    for alias, canonical in ALIASES.items():
        if canonical.lower() in found_lower:
            continue  # already captured
        pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
        m = re.search(pattern, lower_text)
        if m and not _is_negated(lower_text, m.start()):
            if canonical.lower() not in found_lower:
                extra.append(canonical)
                found_lower.add(canonical.lower())
    return extra


def _extract_evidence(text: str, pages: list, skill_set: set) -> dict:
    """Extract contextual quote evidence for each skill across pages."""
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
    """
    Returns (skill_to_years_map, total_experience_years).
    Extracts patterns like '5 years of Python', '3+ years experience in AWS'.
    Also detects total experience ('8 years of professional experience').
    """
    skill_map = {}
    skill_lower = {s.lower(): s for s in SKILL_VOCAB}

    for m in EXPERIENCE_YEAR_RE.finditer(text):
        years   = float(m.group(1))
        skill_candidate = m.group(2).strip().lower()
        # Match against known skill names
        for known_lower, canonical in skill_lower.items():
            if known_lower in skill_candidate or skill_candidate in known_lower:
                # Keep the maximum years if mentioned multiple times
                skill_map[canonical] = max(skill_map.get(canonical, 0), years)
                break

    # Total experience years
    total = 0.0
    for m in TOTAL_EXP_RE.finditer(text):
        total = max(total, float(m.group(1)))

    # Fall back: if no explicit total, use the max across all skill years or sum a reasonable estimate
    if total == 0 and skill_map:
        total = max(skill_map.values())

    return skill_map, total


def _detect_education(text: str) -> tuple:
    """
    Returns (level_int, label_str).
    level: 0=none, 1=diploma, 2=bachelor, 3=master, 4=phd
    """
    best_level = 0
    best_label = "Not detected"
    for label, pattern, level in EDUCATION_LEVELS:
        if pattern.search(text) and level > best_level:
            best_level = level
            best_label = label.capitalize()
    return best_level, best_label


def _compute_section_confidence(text: str, skills: list) -> float:
    """
    Returns a float 0.0–1.0 representing the proportion of detected skills
    that appear within a Skills/Competencies section vs. random context.
    """
    if not skills:
        return 0.0

    # Find all "skills section" boundary positions
    section_starts = [m.start() for m in SKILLS_SECTION_RE.finditer(text)]
    if not section_starts:
        return 0.0

    in_section_count = 0
    for skill in skills:
        m = re.search(re.escape(skill), text, re.IGNORECASE)
        if not m:
            continue
        skill_pos = m.start()
        # Check if skill is within 600 chars of any section header
        for s_start in section_starts:
            if 0 <= skill_pos - s_start <= 600:
                in_section_count += 1
                break

    return in_section_count / len(skills)
