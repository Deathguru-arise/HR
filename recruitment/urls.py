from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),

    # Candidate
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),

    # Drives
    path("drives/<int:drive_id>/", views.drive_detail, name="drive_detail"),
    path("drives/new/", views.create_drive, name="create_drive"),
    path("drives/<int:drive_id>/apply/", views.apply, name="apply"),
    path("drives/<int:drive_id>/shortlist/", views.drive_shortlist, name="drive_shortlist"),
    path("drives/<int:drive_id>/bulk/", views.bulk_action, name="bulk_action"),

    # Applications
    path("applications/<int:application_id>/", views.application_detail, name="application_detail"),
    path("applications/<int:application_id>/resume/", views.resume_file, name="resume_file"),
    path("applications/<int:application_id>/decision/", views.update_decision, name="update_decision"),
    path("applications/<int:application_id>/stage/", views.add_stage_score, name="add_stage_score"),
    path("applications/<int:application_id>/report/", views.candidate_report, name="candidate_report"),

    # System
    path("health/", views.health, name="health"),
]
