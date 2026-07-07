"""Auth module — JWT authentication, bcrypt password hashing, and role-based access control.

Public API:
    - router: FastAPI APIRouter with auth endpoints
    - schemas (RoleDTO, TokenResponse, UserResponse, etc.)
    - dependencies (get_current_user, require_role)
    - JWTService, UserService, hash_password, verify_password
"""

from app.auth.router import router

__all__ = [
    "router",
]

