from pathlib import Path
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .models import Application, AuditEvent, Company, Drive, ResumeAnalysis, UserProfile
from .services import extract_resume, process_resume, local_model_status

def role(user):
    if user.is_superuser: return "admin"
    return getattr(getattr(user, "placement_profile", None), "role", "candidate")

def home(request):
    drives = Drive.objects.filter(status="open", closes_at__gt=timezone.now()).select_related("company")[:6]
    return render(request, "home.html", {"drives": drives})

def register(request):
    if request.method == "POST":
        username, email = request.POST.get("username", "").strip(), request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        if not username or not email or len(password) < 10:
            messages.error(request, "Enter a username, email, and password of at least 10 characters.")
        elif User.objects.filter(username=username).exists(): messages.error(request, "That username is already in use.")
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            UserProfile.objects.create(user=user, role="candidate")
            login(request, user); return redirect("dashboard")
    return render(request, "register.html")

def login_view(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user:
            login(request, user); return redirect("dashboard")
        messages.error(request, "The username or password was not recognized.")
    return render(request, "login.html")

@login_required
def logout_view(request):
    if request.method == "POST": logout(request)
    return redirect("home")

@login_required
def dashboard(request):
    user_role = role(request.user)
    if user_role == "candidate":
        applications = Application.objects.filter(candidate=request.user).select_related("drive", "drive__company")
        drives = Drive.objects.filter(status="open", closes_at__gt=timezone.now()).select_related("company")
        return render(request, "candidate_dashboard.html", {"applications": applications, "drives": drives})
    if user_role in ("hr", "admin"):
        drives = Drive.objects.all().select_related("company") if user_role == "admin" else Drive.objects.filter(created_by=request.user).select_related("company")
        apps = Application.objects.filter(drive__in=drives).select_related("candidate", "drive", "drive__company")
        return render(request, "hr_dashboard.html", {"drives": drives, "applications": apps, "role": user_role, "model_status": local_model_status()})
    raise PermissionDenied

@login_required
def profile(request):
    if role(request.user) != "candidate": raise PermissionDenied
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        try:
            cgpa = request.POST.get("cgpa") or None
            profile.student_id = request.POST.get("student_id", "")[:40]
            profile.department = request.POST.get("department", "")[:100]
            profile.graduation_year = int(request.POST["graduation_year"]) if request.POST.get("graduation_year") else None
            profile.cgpa = cgpa
            profile.save()
            messages.success(request, "Your placement profile has been updated.")
            return redirect("dashboard")
        except (ValueError, TypeError): messages.error(request, "Check the graduation year and CGPA values.")
    return render(request, "profile.html", {"profile": profile})

def drive_detail(request, drive_id):
    drive = get_object_or_404(Drive.objects.select_related("company"), pk=drive_id)
    profile = getattr(request.user, "placement_profile", None) if request.user.is_authenticated else None
    return render(request, "drive_detail.html", {"drive": drive, "can_apply": bool(profile and profile.role == "candidate"), "already_applied": request.user.is_authenticated and Application.objects.filter(drive=drive, candidate=request.user).exists()})

@login_required
def create_drive(request):
    if role(request.user) not in ("hr", "admin"): raise PermissionDenied
    if request.method == "POST":
        try:
            company_name = request.POST.get("company", "").strip()
            title = request.POST.get("title", "").strip()
            closing = timezone.datetime.fromisoformat(request.POST["closes_at"])
            if timezone.is_naive(closing): closing = timezone.make_aware(closing)
            if not company_name or not title or closing <= timezone.now(): raise ValueError("Enter a company, role, and future closing time.")
            with transaction.atomic():
                company, _ = Company.objects.get_or_create(name=company_name, defaults={"created_by": request.user})
                weights = {"required_skills": int(request.POST.get("required_weight", 80)), "preferred_skills": int(request.POST.get("preferred_weight", 20))}
                if sum(weights.values()) != 100 or min(weights.values()) < 0: raise ValueError("Scoring weights must be non-negative and total 100.")
                drive = Drive.objects.create(company=company, title=title, description=request.POST.get("description", ""),
                    required_skills=request.POST.get("required_skills", ""), preferred_skills=request.POST.get("preferred_skills", ""),
                    closes_at=closing, applicant_limit=int(request.POST.get("applicant_limit") or 0) or None,
                    minimum_cgpa=request.POST.get("minimum_cgpa") or None, graduation_year=request.POST.get("graduation_year") or None,
                    status="open", rubric_weights=weights, created_by=request.user)
                AuditEvent.objects.create(actor=request.user, action="drive_created", object_type="Drive", object_id=str(drive.pk))
            messages.success(request, "Recruitment drive published."); return redirect("dashboard")
        except (ValueError, KeyError): messages.error(request, "Check the required fields, future deadline, applicant cap, and weights.")
    return render(request, "create_drive.html")

@login_required
def apply(request, drive_id):
    if request.method != "POST": raise Http404
    if role(request.user) != "candidate": raise PermissionDenied
    drive = get_object_or_404(Drive, pk=drive_id)
    resume = request.FILES.get("resume")
    if not resume: messages.error(request, "Choose a resume to apply."); return redirect("drive_detail", drive_id=drive.pk)
    try:
        text, pages = extract_resume(resume, resume.name)
        with transaction.atomic():
            locked = Drive.objects.select_for_update().get(pk=drive.pk)
            if not locked.is_open(): raise ValueError("This drive is closed or has reached its applicant limit.")
            profile = getattr(request.user, "placement_profile", None)
            eligibility_flags = []
            if locked.minimum_cgpa and (not profile or profile.cgpa is None):
                eligibility_flags.append("CGPA not on file; eligibility needs verification.")
            elif locked.minimum_cgpa and profile.cgpa < locked.minimum_cgpa:
                raise ValueError("Your recorded CGPA does not meet this drive's requirement.")
            if locked.graduation_year and (not profile or profile.graduation_year is None):
                eligibility_flags.append("Graduation year not on file; eligibility needs verification.")
            elif locked.graduation_year and profile.graduation_year != locked.graduation_year:
                raise ValueError("Your recorded graduation year does not meet this drive's requirement.")
            application = Application.objects.create(drive=locked, candidate=request.user, resume=resume, original_filename=Path(resume.name).name)
            result = process_resume(text, pages, locked)
            result["flags"].extend(eligibility_flags)
            facts = result.get("facts", {})
            ResumeAnalysis.objects.create(
                application=application,
                extracted_text=text[:100000],
                facts=facts,
                summary=result.get("summary", ""),
                flags=result.get("flags", []),
                score=result.get("score"),
                criterion_scores=result.get("criterion_scores", {}),
                experience_years=facts.get("total_experience_years") or None,
                education_level=facts.get("education_level", ""),
                section_confidence=facts.get("section_confidence") or None,
            )
            AuditEvent.objects.create(actor=request.user, action="application_submitted", object_type="Application", object_id=str(application.pk))
        messages.success(request, "Application submitted. The match score is an evidence-coverage aid; HR makes the decision.")
    except (ValueError, IntegrityError) as exc:
        messages.error(request, str(exc) or "You have already applied to this drive.")
    return redirect("dashboard")

def _can_view_application(user, application):
    return role(user) == "admin" or (role(user) == "candidate" and application.candidate_id == user.id) or (role(user) == "hr" and application.drive.created_by_id == user.id)

@login_required
def application_detail(request, application_id):
    app = get_object_or_404(Application.objects.select_related("drive", "drive__company", "candidate"), pk=application_id)
    if not _can_view_application(request.user, app): raise PermissionDenied
    return render(request, "application_detail.html", {"app": app, "is_hr": role(request.user) in ("hr", "admin")})

@login_required
def resume_file(request, application_id):
    app = get_object_or_404(Application.objects.select_related("drive"), pk=application_id)
    if not _can_view_application(request.user, app): raise PermissionDenied
    response = FileResponse(app.resume.open("rb"), as_attachment=True, filename=Path(app.original_filename).name)
    return response

@login_required
def update_decision(request, application_id):
    app = get_object_or_404(Application.objects.select_related("drive"), pk=application_id)
    if request.method != "POST" or not _can_view_application(request.user, app) or role(request.user) == "candidate": raise PermissionDenied
    status = request.POST.get("status")
    if status not in dict(Application.STATUS): raise Http404
    app.status, app.decision_reason, app.hr_note = status, request.POST.get("decision_reason", "")[:2000], request.POST.get("hr_note", "")[:4000]
    app.save(update_fields=["status", "decision_reason", "hr_note"])
    AuditEvent.objects.create(actor=request.user, action="application_decision_updated", object_type="Application", object_id=str(app.pk), details={"status": status})
    return redirect("application_detail", application_id=app.pk)

def health(request):
    return render(request, "health.html", {"status": local_model_status()})
