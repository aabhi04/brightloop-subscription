class AppError(Exception):
    """Business error that maps to an HTTP status and `{ "error": message }`."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFound(AppError):
    def __init__(self, what: str = "Resource"):
        super().__init__(f"{what} not found", 404)


class Forbidden(AppError):
    def __init__(self, message: str = "You do not have permission to do this"):
        super().__init__(message, 403)


class Unauthorized(AppError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, 401)


def get_or_404(db, model, obj_id: int, label: str | None = None):
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFound(label or model.__name__)
    return obj
