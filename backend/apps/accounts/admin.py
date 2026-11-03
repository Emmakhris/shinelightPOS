from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuditLog, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "first_name", "last_name", "role", "is_active"]
    list_filter = ["role", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (("POS", {"fields": ("role", "phone")}),)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "action", "user", "approved_by", "entity", "entity_id"]
    list_filter = ["action"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]
