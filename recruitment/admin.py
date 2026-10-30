from django.contrib import admin
from .models import Application, AuditEvent, Company, Drive, ResumeAnalysis, UserProfile

admin.site.register([UserProfile, Company, Drive, Application, ResumeAnalysis, AuditEvent])
