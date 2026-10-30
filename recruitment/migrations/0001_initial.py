from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Company", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=160, unique=True)), ("verified", models.BooleanField(default=False)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="companies", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="UserProfile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("role", models.CharField(choices=[("candidate", "Candidate"), ("hr", "HR / Recruiter"), ("admin", "Placement administrator")], default="candidate", max_length=12)),
            ("student_id", models.CharField(blank=True, max_length=40)), ("department", models.CharField(blank=True, max_length=100)),
            ("graduation_year", models.PositiveSmallIntegerField(blank=True, null=True)), ("cgpa", models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="placement_profile", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="Drive", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=160)), ("description", models.TextField()),
            ("required_skills", models.TextField(help_text="Comma-separated mandatory skills")), ("preferred_skills", models.TextField(blank=True, help_text="Comma-separated preferred skills")),
            ("minimum_cgpa", models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)), ("graduation_year", models.PositiveSmallIntegerField(blank=True, null=True)),
            ("applicant_limit", models.PositiveIntegerField(blank=True, null=True)), ("opens_at", models.DateTimeField(default=django.utils.timezone.now)),
            ("closes_at", models.DateTimeField()), ("status", models.CharField(choices=[("draft", "Draft"), ("open", "Open"), ("closed", "Closed")], default="draft", max_length=8)),
            ("rubric_weights", models.JSONField(blank=True, default=dict)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="drives", to="recruitment.company")),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="drives_created", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="Application", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("resume", models.FileField(max_length=255, upload_to="resumes/%Y/%m/")), ("original_filename", models.CharField(max_length=255)),
            ("status", models.CharField(choices=[("submitted", "Submitted"), ("review", "Under review"), ("shortlisted", "Shortlisted"), ("not_selected", "Not selected")], default="submitted", max_length=16)),
            ("hr_note", models.TextField(blank=True)), ("decision_reason", models.TextField(blank=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("candidate", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applications", to=settings.AUTH_USER_MODEL)),
            ("drive", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applications", to="recruitment.drive")),
        ], options={"ordering": ["-created_at"]}),
        migrations.AddConstraint(model_name="application", constraint=models.UniqueConstraint(fields=("drive", "candidate"), name="one_application_per_candidate_drive")),
        migrations.CreateModel(name="ResumeAnalysis", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("extracted_text", models.TextField(blank=True)),
            ("facts", models.JSONField(blank=True, default=dict)), ("summary", models.TextField(blank=True)), ("flags", models.JSONField(blank=True, default=list)),
            ("score", models.PositiveSmallIntegerField(blank=True, null=True)), ("criterion_scores", models.JSONField(blank=True, default=dict)),
            ("model_name", models.CharField(default="local-rules", max_length=100)), ("processed_at", models.DateTimeField(auto_now=True)),
            ("application", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="analysis", to="recruitment.application")),
        ]),
        migrations.CreateModel(name="AuditEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("action", models.CharField(max_length=100)),
            ("object_type", models.CharField(max_length=80)), ("object_id", models.CharField(max_length=80)), ("details", models.JSONField(blank=True, default=dict)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at"]}),
    ]
