from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('recruitment', '0002_resume_analysis_v2_fields'),
    ]

    operations = [
        # --- UserProfile additions ---
        migrations.AddField(
            model_name='userprofile',
            name='arrears',
            field=models.PositiveSmallIntegerField(blank=True, help_text='Number of active arrears/backlogs (0 = none)', null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='phone',
            field=models.CharField(blank=True, max_length=20),
        ),

        # --- Drive additions ---
        migrations.AddField(
            model_name='drive',
            name='max_arrears',
            field=models.PositiveSmallIntegerField(blank=True, help_text='Maximum allowed active arrears (0 = none allowed)', null=True),
        ),
        migrations.AddField(
            model_name='drive',
            name='allowed_branches',
            field=models.TextField(blank=True, help_text='Comma-separated allowed departments/branches (blank = all)'),
        ),
        migrations.AddField(
            model_name='drive',
            name='blind_review',
            field=models.BooleanField(default=False, help_text='Hide candidate name, college and gender during HR review'),
        ),

        # --- Application STATUS update ---
        migrations.AlterField(
            model_name='application',
            name='status',
            field=models.CharField(
                choices=[
                    ('submitted', 'Submitted'),
                    ('eligible', 'Eligible'),
                    ('shortlisted', 'Shortlisted'),
                    ('aptitude', 'Aptitude round'),
                    ('technical', 'Technical round'),
                    ('hr_round', 'HR round'),
                    ('offer', 'Offer extended'),
                    ('not_selected', 'Not selected'),
                ],
                default='submitted',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='application',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),

        # --- ResumeAnalysis additions ---
        migrations.AddField(
            model_name='resumeanalysis',
            name='sections',
            field=models.JSONField(blank=True, default=dict, help_text='Section name → text content'),
        ),
        migrations.AddField(
            model_name='resumeanalysis',
            name='cgpa_extracted',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True),
        ),
        migrations.AddField(
            model_name='resumeanalysis',
            name='graduation_year_extracted',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='resumeanalysis',
            name='has_arrears',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='resumeanalysis',
            name='projects',
            field=models.JSONField(blank=True, default=list, help_text='Extracted project entries'),
        ),
        migrations.AddField(
            model_name='resumeanalysis',
            name='certifications',
            field=models.JSONField(blank=True, default=list, help_text='Extracted certifications'),
        ),
        migrations.AddField(
            model_name='resumeanalysis',
            name='achievements',
            field=models.JSONField(blank=True, default=list, help_text='Extracted achievements'),
        ),
        migrations.AddField(
            model_name='resumeanalysis',
            name='red_flags',
            field=models.JSONField(blank=True, default=list, help_text='Structural red flags'),
        ),
        migrations.AddField(
            model_name='resumeanalysis',
            name='interview_questions',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='resumeanalysis',
            name='model_name',
            field=models.CharField(default='local-rules-v3', max_length=100),
        ),

        # --- New EligibilityCheck model ---
        migrations.CreateModel(
            name='EligibilityCheck',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('passed', models.BooleanField(default=False)),
                ('criteria', models.JSONField(default=list, help_text='List of {criterion, required, actual, passed, reason}')),
                ('checked_at', models.DateTimeField(auto_now_add=True)),
                ('application', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='eligibility',
                    to='recruitment.application',
                )),
            ],
        ),

        # --- New StageScore model ---
        migrations.CreateModel(
            name='StageScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stage', models.CharField(
                    choices=[
                        ('aptitude', 'Aptitude'),
                        ('technical', 'Technical'),
                        ('hr_round', 'HR'),
                        ('offer', 'Offer'),
                    ],
                    max_length=16,
                )),
                ('score', models.PositiveSmallIntegerField(blank=True, help_text='Score out of 100', null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('application', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stage_scores',
                    to='recruitment.application',
                )),
                ('scored_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='stage_scores',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['created_at']},
        ),
    ]

