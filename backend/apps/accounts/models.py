from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    CASHIER = "cashier", "Cashier"
    WAITER = "waiter", "Waiter"


# What each role may do. Checked by apps.accounts.permissions.HasPerm and services.
ROLE_PERMISSIONS = {
    Role.OWNER: {"*"},
    Role.MANAGER: {
        "sell", "refund", "void", "discount_override", "price_override", "no_sale",
        "manage_catalog", "manage_inventory", "manage_customers", "manage_shifts",
        "cash_movement", "view_reports", "view_audit", "manage_tables",
    },
    Role.CASHIER: {"sell", "manage_customers", "cash_movement"},
    Role.WAITER: {"sell"},
}

APPROVER_ROLES = (Role.OWNER, Role.MANAGER)


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CASHIER)
    pin_hash = models.CharField(max_length=128, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["first_name", "username"]

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    def set_pin(self, pin):
        self.pin_hash = make_password(pin) if pin else ""

    def check_pin(self, pin):
        return bool(self.pin_hash and pin and check_password(str(pin), self.pin_hash))

    def has_pos_perm(self, perm):
        if self.is_superuser:
            return True
        perms = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in perms or perm in perms

    @property
    def is_approver(self):
        return self.is_superuser or self.role in APPROVER_ROLES


class AuditLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="audit_entries")
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_audit_entries"
    )
    action = models.CharField(max_length=60, db_index=True)
    entity = models.CharField(max_length=60, blank=True)
    entity_id = models.CharField(max_length=60, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
