from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    ROLE_CHOICES = [("candidate", "Candidate"), ("hr", "HR / Recruiter"), ("admin", "Placement administrator")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="placement_profile")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default="candidate")
    student_id = models.CharField(max_length=40, blank=True)
    department = models.CharField(max_length=100, blank=True)
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)
    cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    arrears = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Number of active arrears/backlogs (0 = none)")
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self): return f"{self.user} ({self.role})"


class Company(models.Model):
    name = models.CharField(max_length=160, unique=True)
    verified = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="companies")
    def __str__(self): return self.name


class Drive(models.Model):
    STATUS = [("draft", "Draft"), ("open", "Open"), ("closed", "Closed")]
    RESUME_FORMATS = [
        ("standard", "Standard single-column"),
        ("fresher", "Projects and skills first"),
        ("experienced", "Experience first"),
    ]
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="drives")
    title = models.CharField(max_length=160)
    description = models.TextField()
    required_skills = models.TextField(help_text="Comma-separated mandatory skills")
    preferred_skills = models.TextField(blank=True, help_text="Comma-separated preferred skills")
    resume_format = models.CharField(max_length=20, choices=RESUME_FORMATS, default="standard")
    minimum_cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    max_arrears = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Maximum allowed active arrears (0 = none allowed)")
    allowed_branches = models.TextField(blank=True, help_text="Comma-separated allowed departments/branches (blank = all)")
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)
    applicant_limit = models.PositiveIntegerField(null=True, blank=True)
    opens_at = models.DateTimeField(default=timezone.now)
    closes_at = models.DateTimeField()
    status = models.CharField(max_length=8, choices=STATUS, default="draft")
    rubric_weights = models.JSONField(default=dict, blank=True)
    blind_review = models.BooleanField(default=False, help_text="Hide candidate name, college and gender during HR review")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="drives_created")
    created_at = models.DateTimeField(auto_now_add=True)

    def is_open(self):
        now = timezone.now()
        count = self.applications.count()
        return self.status == "open" and self.opens_at <= now < self.closes_at and (not self.applicant_limit or count < self.applicant_limit)

    def __str__(self): return f"{self.company}: {self.title}"


class Application(models.Model):
    # Extended pipeline stages
    STATUS = [
        ("submitted", "Submitted"),
        ("eligible", "Eligible"),
        ("shortlisted", "Shortlisted"),
        ("aptitude", "Aptitude round"),
        ("technical", "Technical round"),
        ("hr_round", "HR round"),
        ("offer", "Offer extended"),
        ("not_selected", "Not selected"),
    ]
    drive = models.ForeignKey(Drive, on_delete=models.PROTECT, related_name="applications")
    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applications")
    resume = models.FileField(upload_to="resumes/%Y/%m/", max_length=255)
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS, default="submitted")
    hr_note = models.TextField(blank=True)
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["drive", "candidate"], name="one_application_per_candidate_drive")]
        ordering = ["-created_at"]

    def __str__(self): return f"{self.candidate} → {self.drive}"

    @property
    def priority_band_display(self):
        """Human-readable priority band derived from analysis score."""
        try:
            score = self.analysis.score
        except Exception:
            return "Pending"
        if score is None:
            return "Pending"
        if score >= 70:
            return "High"
        if score >= 45:
            return "Medium"
        return "Low"

    @property
    def priority_band_css(self):
        band = self.priority_band_display
        return {"High": "band-high", "Medium": "band-medium", "Low": "band-low"}.get(band, "")


class EligibilityCheck(models.Model):
    """Records the knockout gate result (pass/fail per criterion) for an application."""
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="eligibility")
    passed = models.BooleanField(default=False)
    criteria = models.JSONField(default=list, help_text="List of {criterion, required, actual, passed, reason}")
    checked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Eligibility for {self.application} — {'PASS' if self.passed else 'FAIL'}"


class StageScore(models.Model):
    """Structured scorecard for an interview round."""
    STAGE_CHOICES = [
        ("aptitude", "Aptitude"),
        ("technical", "Technical"),
        ("hr_round", "HR"),
        ("offer", "Offer"),
    ]
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="stage_scores")
    stage = models.CharField(max_length=16, choices=STAGE_CHOICES)
    score = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Score out of 100")
    notes = models.TextField(blank=True)
    scored_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stage_scores")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self): return f"{self.stage} score for {self.application}"


class ResumeAnalysis(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="analysis")
    extracted_text = models.TextField(blank=True)
    facts = models.JSONField(default=dict, blank=True)
    summary = models.TextField(blank=True)
    flags = models.JSONField(default=list, blank=True)
    red_flags = models.JSONField(default=list, blank=True, help_text="Structural red flags: gaps, unsupported claims, etc.")
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    criterion_scores = models.JSONField(default=dict, blank=True)
    # Parsed sections
    sections = models.JSONField(default=dict, blank=True, help_text="Section name → text content")
    # Extracted structured data
    cgpa_extracted = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    graduation_year_extracted = models.PositiveSmallIntegerField(null=True, blank=True)
    has_arrears = models.BooleanField(null=True, blank=True)
    projects = models.JSONField(default=list, blank=True, help_text="Extracted project entries")
    certifications = models.JSONField(default=list, blank=True, help_text="Extracted certifications")
    achievements = models.JSONField(default=list, blank=True, help_text="Extracted achievements")
    # Interview support
    interview_questions = models.JSONField(default=list, blank=True)
    # v2 additional scoring dimensions
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="Estimated total years of professional experience extracted from resume.")
    education_level = models.CharField(max_length=20, blank=True,
        help_text="Highest education level detected: phd, master, bachelor, diploma, or empty.")
    section_confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True,
        help_text="Fraction of matched skills appearing under a dedicated Skills section (0.0–1.0).")
    model_name = models.CharField(max_length=100, default="local-rules-v3")
    processed_at = models.DateTimeField(auto_now=True)


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
