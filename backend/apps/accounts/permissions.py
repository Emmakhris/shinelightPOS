from rest_framework.permissions import SAFE_METHODS, BasePermission


def HasPerm(perm, read_perm=None):
    """
    Permission class factory. HasPerm("manage_catalog", read_perm="sell") lets anyone who can
    sell read the catalog, while only catalog managers may change it.
    """

    class _HasPerm(BasePermission):
        def has_permission(self, request, view):
            user = request.user
            if not (user and user.is_authenticated):
                return False
            if request.method in SAFE_METHODS and read_perm:
                return user.has_pos_perm(read_perm) or user.has_pos_perm(perm)
            return user.has_pos_perm(perm)

    _HasPerm.__name__ = f"HasPerm_{perm}"
    return _HasPerm
