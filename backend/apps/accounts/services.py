from apps.common.exceptions import ApprovalRequired

from .models import APPROVER_ROLES, AuditLog, User


def audit(action, user=None, entity="", entity_id="", approved_by=None, **details):
    return AuditLog.objects.create(
        action=action,
        user=user if user and user.is_authenticated else None,
        approved_by=approved_by,
        entity=entity,
        entity_id=str(entity_id or ""),
        details=details,
    )


def find_approver(pin):
    """Return the active owner/manager whose PIN matches, or None."""
    if not pin:
        return None
    candidates = User.objects.filter(is_active=True).exclude(pin_hash="")
    for user in candidates:
        if (user.role in APPROVER_ROLES or user.is_superuser) and user.check_pin(pin):
            return user
    return None


def require_permission_or_approval(user, perm, approval_pin=None, message=None):
    """
    Let the action go ahead if the user holds the permission, otherwise a manager must
    approve it by entering their PIN on the till. Returns the approving user (or None).
    """
    if user.has_pos_perm(perm):
        return None
    approver = find_approver(approval_pin)
    if approver is None or not approver.has_pos_perm(perm):
        raise ApprovalRequired(message or "Manager approval required.")
    return approver
