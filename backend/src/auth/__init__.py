"""
Auth domain — User model.

Design decisions:
- UUID primary keys: Globally unique, safe for distributed systems, no sequential guessing
- Role enum at user level: Simple RBAC without a separate roles table (sufficient for this domain)
- Email uniqueness enforced at DB level with a unique index
- Password stored as bcrypt hash (never plaintext)
"""

from src.auth.models import User

__all__ = ["User"]
