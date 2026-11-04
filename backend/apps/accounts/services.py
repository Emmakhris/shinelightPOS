from concurrent.futures import ThreadPoolExecutor

from django.core.cache import cache

from apps.common.exceptions import ApprovalRequired, PinLocked

from .models import AuditLog, User

PIN_MAX_TRIES = 5
PIN_LOCK_SECONDS = 15 * 60


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
    candidates = [u for u in User.objects.filter(is_active=True).exclude(pin_hash="") if u.is_approver]
    if not candidates:
        return None
    # Each check is slow on purpose. Doing them together keeps the wait the same however many managers there are.
    with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
        matches = pool.map(lambda user: user.check_pin(pin), candidates)
        return next((user for user, matched in zip(candidates, matches) if matched), None)


def limit_pin_tries(kind, user, check, locked_message):
    """
    Run a PIN check, allowing PIN_MAX_TRIES wrong PINs for this user before a PIN_LOCK_SECONDS lockout.
    A try is counted before checking, so many requests at once cannot get past the limit. The count
    is kept in the cache, not the database, so a sale's rollback cannot erase it. It lives in the
    server process, and restarting the POS clears it.
    """
    key = f"pin-tries:{kind}:{user.pk}"
    cache.add(key, 0, PIN_LOCK_SECONDS)
    tries = cache.incr(key)
    if tries > PIN_MAX_TRIES:
        raise PinLocked(locked_message)
    result = check()
    if result:
        cache.delete(key)
        return result
    if tries == PIN_MAX_TRIES:
        cache.set(key, tries, PIN_LOCK_SECONDS)  # the lockout runs from the last wrong PIN
        raise PinLocked(locked_message, after_rollback=lambda: audit(
            "pin_locked", user, "user", user.pk, kind=kind, minutes=PIN_LOCK_SECONDS // 60))
    return result


def approver_for(user, pin):
    """The manager whose PIN this user entered, with the limit on wrong PINs applied."""
    if not pin:
        return None
    return limit_pin_tries(
        "approval", user, lambda: find_approver(pin),
        f"Too many wrong PINs. Try again in up to {PIN_LOCK_SECONDS // 60} minutes, "
        "or ask a manager to sign in at this till.",
    )


def require_permission_or_approval(user, perm, approval_pin=None, message=None):
    """
    Let the action go ahead if the user holds the permission, otherwise a manager must
    approve it by entering their PIN on the till. Returns the approving user (or None).
    """
    if user.has_pos_perm(perm):
        return None
    approver = approver_for(user, approval_pin)
    if approver is None or not approver.has_pos_perm(perm):
        raise ApprovalRequired(message or "Manager approval required.")
    return approver
