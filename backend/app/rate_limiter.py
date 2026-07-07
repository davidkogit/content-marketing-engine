"""
Shared rate limiter instance for use by auth routers and main.py middleware.

Provides a single ``Limiter`` instance keyed on remote IP that is
imported by both the FastAPI application factory (for middleware) and
auth routers (for endpoint-level decorators).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
