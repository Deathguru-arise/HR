from decimal import Decimal
import io
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta
from recruitment.models import (
    Application, Company, Drive, EligibilityCheck,
    ResumeAnalysis, StageScore, UserProfile,
)
from recruitment.services import (
    _detect_skills, _resolve_aliases, _is_negated,
    parse_sections, extract_cgpa, extract_graduation_year,
    detect_arrears, _classify_skill_context, extract_projects,
    extract_certifications, detect_red_flags,
    generate_interview_questions, extract_skills_from_jd,
    run_eligibility_gate, process_resume, extract_resume,
)
from recruitment.evaluation import (
    compute_skill_metrics, compute_top_k_overlap,
    compute_spearman_correlation, compute_cohens_kappa,
)


class SkillExtractionTests(TestCase):
    def test_basic_skill_detection(self):
        text = "Experienced software developer proficient in Python, Django, PostgreSQL, and Docker."
        skills = _detect_skills(text, text.lower())
        self.assertIn("Python", skills)
        self.assertIn("Django", skills)
        self.assertIn("PostgreSQL", skills)
        self.assertIn("Docker", skills)

    def test_alias_resolution(self):
        text = "Familiar with ml, k8s, reactjs, and express."
        found = _detect_skills(text, text.lower())
        resolved = _resolve_aliases(text.lower(), found)
        all_skills = set(found + resolved)
        self.assertIn("Machine Learning", all_skills)
        self.assertIn("Kubernetes", all_skills)
        self.assertIn("React", all_skills)
        self.assertIn("Express.js", all_skills)

    def test_negation_guard(self):
        text = "Strong background in Python and SQL. No experience in AWS or Kubernetes. Never used Ruby."
        lower = text.lower()
        skills = _detect_skills(text, lower)
        self.assertIn("Python", skills)
        self.assertIn("SQL", skills)
        self.assertNotIn("AWS", skills)
        self.assertNotIn("Kubernetes", skills)
        self.assertNotIn("Ruby", skills)


class ParsingAndExtractionTests(TestCase):
    def setUp(self):
        self.sample_resume = (
            "Alex Mercer\n"
            "alex@example.com | +91 9876543210\n\n"
            "EDUCATION\n"
            "B.Tech in Computer Science and Engineering\n"
            "ABC Institute of Technology, Graduating: 2025\n"
            "CGPA: 8.65 / 10 | Nil arrears\n\n"
            "TECHNICAL SKILLS\n"
            "Languages: Python, Java, JavaScript, SQL\n"
            "Frameworks: Django, FastAPI, React\n"
            "Tools: Git, Docker, Linux\n\n"
            "PROJECTS\n"
            "1. Cloud Storage Management API\n"
            "Built a distributed file storage microservice using Python, FastAPI, and PostgreSQL.\n"
            "Deployed with Docker containers and automated CI/CD pipeline using GitHub Actions.\n\n"
            "2. Real-time Chat Engine\n"
            "Developed WebSocket messaging application with Redis pub/sub and React frontend.\n\n"
            "CERTIFICATIONS\n"
            "AWS Certified Cloud Practitioner - Amazon Web Services\n"
            "Deep Learning Specialization - Coursera\n\n"
            "EXPERIENCE\n"
            "Backend Engineering Intern (6 months)\n"
            "Maintained REST APIs and optimized database queries with PostgreSQL and Redis.\n"
        )

    def test_parse_sections(self):
        sections = parse_sections(self.sample_resume)
        self.assertIn("education", sections)
        self.assertIn("skills", sections)
        self.assertIn("projects", sections)
        self.assertIn("certifications", sections)
        self.assertIn("experience", sections)

    def test_cgpa_extraction(self):
        self.assertEqual(extract_cgpa("Candidate CGPA: 8.65"), 8.65)
        self.assertEqual(extract_cgpa("Aggregate: 85.0%"), 8.5)
        self.assertEqual(extract_cgpa("GPA: 3.6/4.0"), 9.0)

    def test_graduation_year_extraction(self):
        self.assertEqual(extract_graduation_year("Graduating in June 2025"), 2025)

    def test_arrears_detection(self):
        self.assertFalse(detect_arrears("No active backlogs. Nil arrears."))
        self.assertTrue(detect_arrears("Currently clearing 2 active backlogs."))
        self.assertIsNone(detect_arrears("Degree in Engineering."))

    def test_skill_context_demonstrated_vs_listed(self):
        sections = parse_sections(self.sample_resume)
        skills = ["Python", "Docker", "Java", "Linux"]
        context = _classify_skill_context(self.sample_resume, sections, skills)
        # Python and Docker are used with "Built" and "Deployed" in projects
        self.assertEqual(context.get("Python"), "demonstrated")
        self.assertEqual(context.get("Docker"), "demonstrated")
        # Java was only in the skills list
        self.assertEqual(context.get("Java"), "listed_only")

    def test_project_and_cert_extraction(self):
        sections = parse_sections(self.sample_resume)
        projects = extract_projects(self.sample_resume, sections)
        self.assertGreaterEqual(len(projects), 1)
        certs = extract_certifications(self.sample_resume, sections)
        self.assertGreaterEqual(len(certs), 1)


class RedFlagsAndQuestionsTests(TestCase):
    def test_short_resume_flag(self):
        short_text = "Brief profile. Skills: Python."
        flags = detect_red_flags(short_text, {"skills": ["Python"]})
        self.assertTrue(any("short" in f.lower() for f in flags))

    def test_unsupported_skills_flag(self):
        text = "Long resume text " * 50
        facts = {
            "skill_context": {f"Skill{i}": "listed_only" for i in range(8)},
            "missing_required": ["Django"],
        }
        flags = detect_red_flags(text, facts)
        self.assertTrue(any("evidence" in f.lower() for f in flags))

    def test_interview_questions_generation(self):
        user = User.objects.create_user(username="recruiter", password="Password123!")
        company = Company.objects.create(name="TechCorp", created_by=user)
        drive = Drive.objects.create(
            company=company,
            title="Python Dev",
            description="Looking for Python and Django",
            required_skills="Python, Django, AWS",
            closes_at=timezone.now() + timedelta(days=7),
            created_by=user,
        )
        facts = {
            "skills": ["Python"],
            "skill_context": {"Python": "demonstrated"},
            "missing_required": ["Django", "AWS"],
            "matching_required": ["Python"],
            "projects": [{"title": "API Backend"}],
            "experience_years": 1.0,
        }
        questions = generate_interview_questions(facts, drive)
        self.assertGreaterEqual(len(questions), 2)
        # Should have gap questions for Django and AWS
        reasons = [q["reason"] for q in questions]
        self.assertTrue(any("Django" in r for r in reasons))


class JobDescriptionParserTests(TestCase):
    def test_jd_skills_extraction(self):
        jd_text = (
            "Senior Backend Engineer\n\n"
            "Requirements:\n"
            "- Strong proficiency in Python, Django, and PostgreSQL\n"
            "- Solid foundation in Docker and Git\n\n"
            "Preferred / Nice to have:\n"
            "- Experience with Redis and Kubernetes\n"
            "- Familiarity with AWS cloud services\n"
        )
        res = extract_skills_from_jd(jd_text)
        self.assertIn("Python", res["required_skills"])
        self.assertIn("Django", res["required_skills"])
        self.assertIn("PostgreSQL", res["required_skills"])
        self.assertIn("Kubernetes", res["preferred_skills"])
        self.assertIn("Redis", res["preferred_skills"])


class EligibilityGateTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(username="hr_user", password="Password123!")
        UserProfile.objects.create(user=self.recruiter, role="hr")
        self.company = Company.objects.create(name="Apex Systems", created_by=self.recruiter)
        self.drive = Drive.objects.create(
            company=self.company,
            title="Graduate Engineer Trainee",
            description="Engineering roles for 2025 batch",
            required_skills="Python, SQL",
            minimum_cgpa=Decimal("7.50"),
            max_arrears=0,
            graduation_year=2025,
            allowed_branches="CSE, IT",
            closes_at=timezone.now() + timedelta(days=10),
            created_by=self.recruiter,
        )

    def test_eligible_candidate(self):
        candidate = User.objects.create_user(username="stud1", password="Password123!")
        UserProfile.objects.create(
            user=candidate, role="candidate",
            cgpa=Decimal("8.20"), arrears=0,
            graduation_year=2025, department="Computer Science (CSE)",
        )
        app = Application(drive=self.drive, candidate=candidate)
        passed, criteria = run_eligibility_gate(app, self.drive)
        self.assertTrue(passed)
        self.assertTrue(all(c["passed"] for c in criteria))

    def test_ineligible_candidate_cgpa_cutoff(self):
        candidate = User.objects.create_user(username="stud2", password="Password123!")
        UserProfile.objects.create(
            user=candidate, role="candidate",
            cgpa=Decimal("6.80"), arrears=0,
            graduation_year=2025, department="CSE",
        )
        app = Application(drive=self.drive, candidate=candidate)
        passed, criteria = run_eligibility_gate(app, self.drive)
        self.assertFalse(passed)
        cgpa_crit = next(c for c in criteria if c["criterion"] == "Minimum CGPA")
        self.assertFalse(cgpa_crit["passed"])

    def test_ineligible_candidate_arrears(self):
        candidate = User.objects.create_user(username="stud3", password="Password123!")
        UserProfile.objects.create(
            user=candidate, role="candidate",
            cgpa=Decimal("8.50"), arrears=1,
            graduation_year=2025, department="CSE",
        )
        app = Application(drive=self.drive, candidate=candidate)
        passed, criteria = run_eligibility_gate(app, self.drive)
        self.assertFalse(passed)
        arrears_crit = next(c for c in criteria if c["criterion"] == "Active arrears")
        self.assertFalse(arrears_crit["passed"])


class WorkflowViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.hr = User.objects.create_user(username="lead_hr", email="hr@corp.com", password="StrongPassword123!")
        UserProfile.objects.create(user=self.hr, role="hr")

        self.candidate = User.objects.create_user(username="dev_candidate", email="dev@test.com", password="StrongPassword123!")
        self.candidate_profile = UserProfile.objects.create(
            user=self.candidate, role="candidate",
            cgpa=Decimal("8.80"), arrears=0, graduation_year=2025, department="CSE",
        )

        self.company = Company.objects.create(name="NextGen Labs", created_by=self.hr)
        self.drive = Drive.objects.create(
            company=self.company,
            title="Junior Software Engineer",
            description="Entry level software developer role",
            required_skills="Python, Django, SQL",
            preferred_skills="Docker",
            minimum_cgpa=Decimal("7.00"),
            max_arrears=0,
            graduation_year=2025,
            status="open",
            closes_at=timezone.now() + timedelta(days=5),
            created_by=self.hr,
        )

    def test_public_pages(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(f"/drives/{self.drive.id}/")
        self.assertEqual(resp.status_code, 200)

    def test_application_submission_with_dpdp_consent(self):
        self.client.login(username="dev_candidate", password="StrongPassword123!")
        resume_content = (
            b"Dev Candidate Resume\n"
            b"Education: B.Tech CSE 2025. CGPA: 8.80. Nil arrears.\n"
            b"Skills: Python, Django, SQL, Git.\n"
            b"Projects: Built an inventory app with Python and Django.\n"
        )
        resume_file = io.BytesIO(resume_content)
        resume_file.name = "resume.txt"

        resp = self.client.post(f"/drives/{self.drive.id}/apply/", {
            "resume": resume_file,
            "dpdp_consent": "on",
        })
        self.assertEqual(resp.status_code, 302)

        app = Application.objects.get(drive=self.drive, candidate=self.candidate)
        self.assertEqual(app.status, "eligible")
        self.assertTrue(hasattr(app, "eligibility"))
        self.assertTrue(app.eligibility.passed)
        self.assertTrue(hasattr(app, "analysis"))
        self.assertGreater(app.analysis.score, 0)

    def test_comparison_view_for_hr(self):
        # Create second candidate
        c2 = User.objects.create_user(username="cand2", password="StrongPassword123!")
        UserProfile.objects.create(user=c2, role="candidate", cgpa=Decimal("7.8"), arrears=0, graduation_year=2025)
        
        app1 = Application.objects.create(drive=self.drive, candidate=self.candidate, original_filename="c1.txt")
        EligibilityCheck.objects.create(application=app1, passed=True)
        ResumeAnalysis.objects.create(
            application=app1, score=85,
            facts={"required_skill_evidence": ["Python", "Django"], "skill_context": {"Python": "demonstrated"}},
        )

        app2 = Application.objects.create(drive=self.drive, candidate=c2, original_filename="c2.txt")
        EligibilityCheck.objects.create(application=app2, passed=True)
        ResumeAnalysis.objects.create(
            application=app2, score=70,
            facts={"required_skill_evidence": ["Python"], "skill_context": {"Python": "listed_only"}},
        )

        self.client.login(username="lead_hr", password="StrongPassword123!")
        resp = self.client.get(f"/drives/{self.drive.id}/compare/?ids={app1.id},{app2.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Candidate comparison (2)")
        self.assertContains(resp, "Python")

    def test_candidate_report_view(self):
        app = Application.objects.create(drive=self.drive, candidate=self.candidate, original_filename="c1.txt")
        EligibilityCheck.objects.create(application=app, passed=True)
        ResumeAnalysis.objects.create(
            application=app, score=88,
            facts={"required_skill_evidence": ["Python"], "missing_required_skills": ["SQL"], "evidence": {}},
            interview_questions=[{"question": "How do you optimize SQL?", "reason": "Missing skill", "type": "gap"}],
        )

        self.client.login(username="lead_hr", password="StrongPassword123!")
        resp = self.client.get(f"/applications/{app.id}/report/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CANDIDATE SCREENING REPORT")
        self.assertContains(resp, "How do you optimize SQL?")



class EvaluationMetricsTests(TestCase):
    def test_skill_metrics(self):
        pred = ["Python", "Django", "Docker", "Go"]
        truth = ["Python", "Django", "Kubernetes"]
        metrics = compute_skill_metrics(pred, truth)
        # 2 TP (Python, Django), 2 FP (Docker, Go), 1 FN (Kubernetes)
        self.assertEqual(metrics["tp"], 2)
        self.assertEqual(metrics["fp"], 2)
        self.assertEqual(metrics["fn"], 1)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertAlmostEqual(metrics["recall"], 2 / 3, places=2)

    def test_top_k_overlap(self):
        pred_ids = [101, 102, 103, 104, 105]
        hr_ids = [101, 103, 105, 108, 109]
        overlap = compute_top_k_overlap(pred_ids, hr_ids, k=3)
        # Top 3: pred={101, 102, 103}, hr={101, 103, 105} -> intersection is {101, 103} = 2/3
        self.assertAlmostEqual(overlap, 2 / 3, places=2)

    def test_spearman_correlation(self):
        scores = [90, 80, 70, 60, 50]
        hr_ranks = [5, 4, 3, 2, 1]
        rho = compute_spearman_correlation(scores, hr_ranks)
        self.assertEqual(rho, 1.0)

    def test_cohens_kappa(self):
        sys_bands = ["High", "High", "Medium", "Low", "Low"]
        hr_bands = ["High", "High", "Medium", "Low", "Low"]
        kappa = compute_cohens_kappa(sys_bands, hr_bands)
        self.assertEqual(kappa, 1.0)
