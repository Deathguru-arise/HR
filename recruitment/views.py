from pathlib import Path
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .models import (
    Application, AuditEvent, Company, Drive,
    EligibilityCheck, ResumeAnalysis, StageScore, UserProfile,
)
from .services import (
    extract_resume, process_resume, local_model_status,
    run_eligibility_gate, compute_priority_band, extract_skills_from_jd,
)


# ---------------------------------------------------------------------------
# Role helper
# ---------------------------------------------------------------------------

def role(user):
    if user.is_superuser:
        return "admin"
    return getattr(getattr(user, "placement_profile", None), "role", "candidate")


def _require_hr(user):
    if role(user) not in ("hr", "admin"):
        raise PermissionDenied


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------

def home(request):
    drives = Drive.objects.filter(status="open", closes_at__gt=timezone.now()).select_related("company")[:6]
    return render(request, "home.html", {"drives": drives})


def register(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        if not username or not email or len(password) < 10:
            messages.error(request, "Enter a username, email, and password of at least 10 characters.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "That username is already in use.")
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            UserProfile.objects.create(user=user, role="candidate")
            login(request, user)
            return redirect("dashboard")
    return render(request, "register.html")


def login_view(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "The username or password was not recognized.")
    return render(request, "login.html")


@login_required
def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("home")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    user_role = role(request.user)
    if user_role == "candidate":
        applications = Application.objects.filter(candidate=request.user).select_related(
            "drive", "drive__company"
        ).prefetch_related("analysis")
        drives = Drive.objects.filter(status="open", closes_at__gt=timezone.now()).select_related("company")
        return render(request, "candidate_dashboard.html", {"applications": applications, "drives": drives})
    if user_role in ("hr", "admin"):
        drives = (
            Drive.objects.all().select_related("company")
            if user_role == "admin"
            else Drive.objects.filter(created_by=request.user).select_related("company")
        )
        apps = Application.objects.filter(drive__in=drives).select_related(
            "candidate", "drive", "drive__company"
        ).prefetch_related("analysis", "eligibility")

        # Dashboard funnel counts
        funnel = {
            "total": apps.count(),
            "eligible": apps.filter(status="eligible").count(),
            "shortlisted": apps.filter(status="shortlisted").count(),
            "offer": apps.filter(status="offer").count(),
        }

        return render(request, "hr_dashboard.html", {
            "drives": drives,
            "applications": apps,
            "role": user_role,
            "model_status": local_model_status(),
            "funnel": funnel,
        })
    raise PermissionDenied


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@login_required
def profile(request):
    if role(request.user) != "candidate":
        raise PermissionDenied
    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        try:
            cgpa = request.POST.get("cgpa") or None
            arrears_val = request.POST.get("arrears")
            profile_obj.student_id = request.POST.get("student_id", "")[:40]
            profile_obj.department = request.POST.get("department", "")[:100]
            profile_obj.phone = request.POST.get("phone", "")[:20]
            profile_obj.graduation_year = int(request.POST["graduation_year"]) if request.POST.get("graduation_year") else None
            profile_obj.cgpa = cgpa
            profile_obj.arrears = int(arrears_val) if arrears_val is not None and arrears_val != "" else None
            profile_obj.save()
            messages.success(request, "Your placement profile has been updated.")
            return redirect("dashboard")
        except (ValueError, TypeError):
            messages.error(request, "Check the graduation year, CGPA, and arrears values.")
    return render(request, "profile.html", {"profile": profile_obj})


# ---------------------------------------------------------------------------
# Drive views
# ---------------------------------------------------------------------------

def drive_detail(request, drive_id):
    drive = get_object_or_404(Drive.objects.select_related("company"), pk=drive_id)
    profile_obj = getattr(request.user, "placement_profile", None) if request.user.is_authenticated else None
    already_applied = (
        request.user.is_authenticated
        and Application.objects.filter(drive=drive, candidate=request.user).exists()
    )
    return render(request, "drive_detail.html", {
        "drive": drive,
        "can_apply": bool(profile_obj and profile_obj.role == "candidate"),
        "already_applied": already_applied,
    })


@login_required
def create_drive(request):
    _require_hr(request.user)
    if request.method == "POST":
        try:
            company_name = request.POST.get("company", "").strip()
            title = request.POST.get("title", "").strip()
            closing = timezone.datetime.fromisoformat(request.POST["closes_at"])
            if timezone.is_naive(closing):
                closing = timezone.make_aware(closing)
            if not company_name or not title or closing <= timezone.now():
                raise ValueError("Enter a company, role, and future closing time.")
            with transaction.atomic():
                company, _ = Company.objects.get_or_create(
                    name=company_name, defaults={"created_by": request.user}
                )
                weights = {
                    "required_skills": int(request.POST.get("required_weight", 70)),
                    "preferred_skills": int(request.POST.get("preferred_weight", 20)),
                    "experience": int(request.POST.get("experience_weight", 5)),
                    "education": int(request.POST.get("education_weight", 5)),
                }
                if sum(weights.values()) != 100 or min(weights.values()) < 0:
                    raise ValueError("Scoring weights must be non-negative and total 100.")
                max_arrears_val = request.POST.get("max_arrears")
                drive = Drive.objects.create(
                    company=company,
                    title=title,
                    description=request.POST.get("description", ""),
                    required_skills=request.POST.get("required_skills", ""),
                    preferred_skills=request.POST.get("preferred_skills", ""),
                    closes_at=closing,
                    applicant_limit=int(request.POST.get("applicant_limit") or 0) or None,
                    minimum_cgpa=request.POST.get("minimum_cgpa") or None,
                    max_arrears=int(max_arrears_val) if max_arrears_val not in (None, "") else None,
                    allowed_branches=request.POST.get("allowed_branches", ""),
                    graduation_year=request.POST.get("graduation_year") or None,
                    blind_review=bool(request.POST.get("blind_review")),
                    status="open",
                    rubric_weights=weights,
                    created_by=request.user,
                )
                AuditEvent.objects.create(
                    actor=request.user, action="drive_created",
                    object_type="Drive", object_id=str(drive.pk),
                )
            messages.success(request, "Recruitment drive published.")
            return redirect("dashboard")
        except (ValueError, KeyError) as exc:
            messages.error(request, str(exc) or "Check the required fields, future deadline, and weights.")
    return render(request, "create_drive.html")


# ---------------------------------------------------------------------------
# Application submission
# ---------------------------------------------------------------------------

@login_required
def apply(request, drive_id):
    if request.method != "POST":
        raise Http404
    if role(request.user) != "candidate":
        raise PermissionDenied
    drive = get_object_or_404(Drive, pk=drive_id)
    resume = request.FILES.get("resume")
    if not resume:
        messages.error(request, "Choose a resume to apply.")
        return redirect("drive_detail", drive_id=drive.pk)
    if not request.POST.get("dpdp_consent"):
        messages.error(request, "You must provide consent for data processing under DPDP Act 2023 to apply.")
        return redirect("drive_detail", drive_id=drive.pk)
    try:
        text, pages = extract_resume(resume, resume.name)
        with transaction.atomic():
            locked = Drive.objects.select_for_update().get(pk=drive.pk)
            if not locked.is_open():
                raise ValueError("This drive is closed or has reached its applicant limit.")

            application = Application.objects.create(
                drive=locked,
                candidate=request.user,
                resume=resume,
                original_filename=Path(resume.name).name,
            )
            result = process_resume(text, pages, locked)
            facts = result.get("facts", {})

            ResumeAnalysis.objects.create(
                application=application,
                extracted_text=text[:100000],
                facts=facts,
                summary=result.get("summary", ""),
                flags=result.get("flags", []),
                red_flags=result.get("red_flags", []),
                score=result.get("score"),
                criterion_scores=result.get("criterion_scores", {}),
                sections=result.get("sections", {}),
                cgpa_extracted=result.get("cgpa_extracted"),
                graduation_year_extracted=result.get("graduation_year_extracted"),
                has_arrears=result.get("has_arrears"),
                projects=result.get("projects", []),
                certifications=result.get("certifications", []),
                achievements=result.get("achievements", []),
                interview_questions=result.get("interview_questions", []),
                experience_years=facts.get("total_experience_years") or None,
                education_level=facts.get("education_level", ""),
                section_confidence=facts.get("section_confidence") or None,
            )

            # Run eligibility gate
            passed, criteria = run_eligibility_gate(application, locked)
            EligibilityCheck.objects.create(
                application=application,
                passed=passed,
                criteria=criteria,
            )
            if passed:
                application.status = "eligible"
                application.save(update_fields=["status"])

            AuditEvent.objects.create(
                actor=request.user, action="application_submitted",
                object_type="Application", object_id=str(application.pk),
            )

        messages.success(
            request,
            "Application submitted. The match score is an evidence-coverage aid; HR makes the decision."
        )
    except (ValueError, IntegrityError) as exc:
        messages.error(request, str(exc) or "You have already applied to this drive.")
    return redirect("dashboard")


# ---------------------------------------------------------------------------
# Application detail / review
# ---------------------------------------------------------------------------

def _can_view_application(user, application):
    return (
        role(user) == "admin"
        or (role(user) == "candidate" and application.candidate_id == user.id)
        or (role(user) == "hr" and application.drive.created_by_id == user.id)
    )


@login_required
def application_detail(request, application_id):
    app = get_object_or_404(
        Application.objects.select_related("drive", "drive__company", "candidate")
        .prefetch_related("analysis", "eligibility", "stage_scores"),
        pk=application_id,
    )
    if not _can_view_application(request.user, app):
        raise PermissionDenied
    user_role = role(request.user)
    is_hr = user_role in ("hr", "admin")
    blind = app.drive.blind_review and is_hr

    # Stage scores for HR
    stage_scores = list(app.stage_scores.all()) if is_hr else []

    return render(request, "application_detail.html", {
        "app": app,
        "is_hr": is_hr,
        "blind": blind,
        "stage_scores": stage_scores,
        "stage_choices": StageScore.STAGE_CHOICES,
    })


@login_required
def resume_file(request, application_id):
    app = get_object_or_404(Application.objects.select_related("drive"), pk=application_id)
    if not _can_view_application(request.user, app):
        raise PermissionDenied
    response = FileResponse(
        app.resume.open("rb"), as_attachment=True,
        filename=Path(app.original_filename).name,
    )
    return response


@login_required
def update_decision(request, application_id):
    app = get_object_or_404(Application.objects.select_related("drive"), pk=application_id)
    if request.method != "POST" or not _can_view_application(request.user, app) or role(request.user) == "candidate":
        raise PermissionDenied
    new_status = request.POST.get("status")
    if new_status not in dict(Application.STATUS):
        raise Http404
    old_status = app.status
    app.status = new_status
    app.decision_reason = request.POST.get("decision_reason", "")[:2000]
    app.hr_note = request.POST.get("hr_note", "")[:4000]
    app.save(update_fields=["status", "decision_reason", "hr_note"])
    AuditEvent.objects.create(
        actor=request.user, action="application_decision_updated",
        object_type="Application", object_id=str(app.pk),
        details={"old_status": old_status, "new_status": new_status},
    )
    messages.success(request, f"Status updated to '{app.get_status_display()}'.")
    return redirect("application_detail", application_id=app.pk)


# ---------------------------------------------------------------------------
# Stage scoring (HR only)
# ---------------------------------------------------------------------------

@login_required
def add_stage_score(request, application_id):
    app = get_object_or_404(Application.objects.select_related("drive"), pk=application_id)
    _require_hr(request.user)
    if not _can_view_application(request.user, app):
        raise PermissionDenied
    if request.method != "POST":
        raise Http404
    stage = request.POST.get("stage")
    valid_stages = dict(StageScore.STAGE_CHOICES)
    if stage not in valid_stages:
        messages.error(request, "Invalid stage.")
        return redirect("application_detail", application_id=app.pk)
    score_val = request.POST.get("score")
    StageScore.objects.create(
        application=app,
        stage=stage,
        score=int(score_val) if score_val else None,
        notes=request.POST.get("notes", "")[:2000],
        scored_by=request.user,
    )
    AuditEvent.objects.create(
        actor=request.user, action="stage_score_added",
        object_type="Application", object_id=str(app.pk),
        details={"stage": stage},
    )
    messages.success(request, f"{valid_stages[stage]} score recorded.")
    return redirect("application_detail", application_id=app.pk)


# ---------------------------------------------------------------------------
# Drive shortlist (ranked view)
# ---------------------------------------------------------------------------

@login_required
def drive_shortlist(request, drive_id):
    drive = get_object_or_404(Drive.objects.select_related("company"), pk=drive_id)
    _require_hr(request.user)
    if role(request.user) == "hr" and drive.created_by_id != request.user.id:
        raise PermissionDenied

    status_filter = request.GET.get("status", "")
    band_filter = request.GET.get("band", "")

    apps = Application.objects.filter(drive=drive).select_related(
        "candidate", "drive"
    ).prefetch_related("analysis", "eligibility")

    if status_filter:
        apps = apps.filter(status=status_filter)

    # Sort by score descending (nulls last)
    def sort_key(a):
        try:
            return a.analysis.score or -1
        except Exception:
            return -1

    apps_list = sorted(apps, key=sort_key, reverse=True)

    # Apply band filter after sorting
    if band_filter:
        apps_list = [a for a in apps_list if a.priority_band_display == band_filter]

    # Funnel counts for this drive
    all_apps = Application.objects.filter(drive=drive)
    funnel_data = [
        {"code": s_code, "label": s_label, "count": all_apps.filter(status=s_code).count()}
        for s_code, s_label in Application.STATUS
    ]

    return render(request, "shortlist.html", {
        "drive": drive,
        "applications": apps_list,
        "status_choices": Application.STATUS,
        "status_filter": status_filter,
        "band_filter": band_filter,
        "funnel_data": funnel_data,
        "blind": drive.blind_review,
    })


@login_required
def bulk_action(request, drive_id):
    """Bulk shortlist, reject, or compare selected applications."""
    drive = get_object_or_404(Drive, pk=drive_id)
    _require_hr(request.user)
    if request.method != "POST":
        raise Http404
    action = request.POST.get("action")
    ids = request.POST.getlist("selected")
    if not ids:
        messages.error(request, "Select at least one application.")
        return redirect("drive_shortlist", drive_id=drive.pk)

    if action == "compare":
        if len(ids) < 2 or len(ids) > 4:
            messages.error(request, "Select between 2 and 4 candidates to compare side by side.")
            return redirect("drive_shortlist", drive_id=drive.pk)
        return redirect(f"/drives/{drive.id}/compare/?ids={','.join(ids)}")

    if action not in ("shortlisted", "not_selected"):
        messages.error(request, "Invalid bulk action.")
        return redirect("drive_shortlist", drive_id=drive.pk)

    apps = Application.objects.filter(pk__in=ids, drive=drive)
    updated = apps.update(status=action)
    for app in apps:
        AuditEvent.objects.create(
            actor=request.user, action=f"bulk_{action}",
            object_type="Application", object_id=str(app.pk),
        )
    messages.success(request, f"{updated} application(s) updated to '{dict(Application.STATUS)[action]}'.")
    return redirect("drive_shortlist", drive_id=drive.pk)


# ---------------------------------------------------------------------------
# Candidate side-by-side comparison (2-4 candidates)
# ---------------------------------------------------------------------------

@login_required
def compare_candidates(request, drive_id):
    drive = get_object_or_404(Drive.objects.select_related("company"), pk=drive_id)
    _require_hr(request.user)
    if role(request.user) == "hr" and drive.created_by_id != request.user.id:
        raise PermissionDenied

    raw_ids = request.GET.get("ids", "").strip()
    id_list = [int(i.strip()) for i in raw_ids.split(",") if i.strip().isdigit()]
    if len(id_list) < 2 or len(id_list) > 4:
        messages.error(request, "Please select 2 to 4 candidates to compare.")
        return redirect("drive_shortlist", drive_id=drive.pk)

    apps = list(Application.objects.filter(pk__in=id_list, drive=drive).select_related(
        "candidate", "candidate__placement_profile"
    ).prefetch_related("analysis", "eligibility", "stage_scores"))

    if len(apps) < 2:
        messages.error(request, "Could not find enough matching applications for comparison.")
        return redirect("drive_shortlist", drive_id=drive.pk)

    # Required skills to compare across candidates
    req_skills = [s.strip() for s in drive.required_skills.split(",") if s.strip()]

    # Build per-candidate comparison data
    comparison_cards = []
    for app in apps:
        analysis = getattr(app, "analysis", None)
        facts = analysis.facts if analysis else {}
        matched_req = set(facts.get("required_skill_evidence", []))
        skill_ctx = facts.get("skill_context", {})
        demonstrated = [s for s, c in skill_ctx.items() if c == "demonstrated"]
        listed = [s for s, c in skill_ctx.items() if c == "listed_only"]

        card = {
            "app": app,
            "display_name": f"Candidate #{app.id}" if drive.blind_review else (app.candidate.get_full_name() or app.candidate.username),
            "score": analysis.score if analysis else None,
            "priority_band": app.priority_band_display,
            "priority_css": app.priority_band_css,
            "eligibility_passed": app.eligibility.passed if hasattr(app, "eligibility") else None,
            "req_skills_matched": [s for s in req_skills if s in matched_req],
            "req_skills_missing": [s for s in req_skills if s not in matched_req],
            "demonstrated_count": len(demonstrated),
            "demonstrated_skills": demonstrated[:8],
            "listed_count": len(listed),
            "experience_years": analysis.experience_years if analysis else 0,
            "education_level": analysis.education_level if analysis else "—",
            "cgpa": (getattr(getattr(app.candidate, "placement_profile", None), "cgpa", None)
                     or (analysis.cgpa_extracted if analysis else None)),
            "arrears": getattr(getattr(app.candidate, "placement_profile", None), "arrears", None),
            "projects_count": len(analysis.projects) if analysis and analysis.projects else 0,
            "certifications_count": len(analysis.certifications) if analysis and analysis.certifications else 0,
            "red_flags": analysis.red_flags if analysis else [],
            "status_display": app.get_status_display(),
            "status_code": app.status,
            "stage_scores": list(app.stage_scores.all()),
        }
        comparison_cards.append(card)

    return render(request, "compare.html", {
        "drive": drive,
        "comparison_cards": comparison_cards,
        "req_skills": req_skills,
        "blind": drive.blind_review,
    })


# ---------------------------------------------------------------------------
# Job Description Skill Extraction API
# ---------------------------------------------------------------------------

@login_required
def parse_jd_skills(request):
    _require_hr(request.user)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    import json
    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
        text = body.get("text", "")
    except Exception:
        text = request.POST.get("text", "")

    result = extract_skills_from_jd(text)
    return JsonResponse({
        "status": "ok",
        "required_skills": ", ".join(result["required_skills"]),
        "preferred_skills": ", ".join(result["preferred_skills"]),
        "all_skills": result["all_skills"],
    })


# ---------------------------------------------------------------------------
# Candidate report (printable HR one-pager)
# ---------------------------------------------------------------------------

@login_required
def candidate_report(request, application_id):
    app = get_object_or_404(
        Application.objects.select_related("drive", "drive__company", "candidate")
        .prefetch_related("analysis", "eligibility", "stage_scores"),
        pk=application_id,
    )
    if not _can_view_application(request.user, app):
        raise PermissionDenied
    user_role = role(request.user)
    blind = app.drive.blind_review and user_role in ("hr", "admin")

    try:
        analysis = app.analysis
    except Exception:
        analysis = None

    priority_band = "Pending"
    if analysis and analysis.score is not None:
        priority_band = compute_priority_band(analysis.score, analysis.red_flags)

    return render(request, "candidate_report.html", {
        "app": app,
        "analysis": analysis,
        "is_hr": user_role in ("hr", "admin"),
        "blind": blind,
        "priority_band": priority_band,
    })


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def health(request):
    return render(request, "health.html", {"status": local_model_status()})
