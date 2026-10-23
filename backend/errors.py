"""Exception types shared by the backend modules."""


class AccessDenied(PermissionError):
    """A user-supplied path attempted to leave the music library."""
