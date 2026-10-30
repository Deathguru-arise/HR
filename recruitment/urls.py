from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"), path("register/", views.register, name="register"),
    path("accounts/login/", views.login_view, name="login"), path("accounts/logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"), path("profile/", views.profile, name="profile"), path("drives/<int:drive_id>/", views.drive_detail, name="drive_detail"),
    path("drives/new/", views.create_drive, name="create_drive"), path("drives/<int:drive_id>/apply/", views.apply, name="apply"),
    path("applications/<int:application_id>/", views.application_detail, name="application_detail"),
    path("applications/<int:application_id>/resume/", views.resume_file, name="resume_file"),
    path("applications/<int:application_id>/decision/", views.update_decision, name="update_decision"),
    path("health/", views.health, name="health"),
]
