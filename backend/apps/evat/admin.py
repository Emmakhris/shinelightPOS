from django.contrib import admin

from .models import EvatSubmission


@admin.register(EvatSubmission)
class EvatSubmissionAdmin(admin.ModelAdmin):
    list_display = ["number", "kind", "status", "simulated", "reference", "created_at", "sent_at"]
    list_filter = ["status", "kind", "simulated"]
    search_fields = ["number", "reference"]
    readonly_fields = [f.name for f in EvatSubmission._meta.fields]
