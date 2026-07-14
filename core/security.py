"""Mandate — Phase 6: the security baseline.

Authorization enforced where consequence lives. The doctrine of the
project applied to access: a human approves — but not *any* human.

Contents:
  - Role / Action model with an explicit permission matrix
  - Principal (an authenticated actor)
  - password hashing (scrypt, per-user salt — stdlib only)
  - tamper-proof session tokens (HMAC-SHA256, expiring — stdlib only)
  - authorize(): raises PermissionDenied; the graph calls it

Design notes:
  * No new dependencies: hashlib.scrypt + hmac are enough and are the
    right primitives. Rolling our own crypto is avoided; we compose
    stdlib ones.
  * Tokens are signed, not encrypted: they carry no secrets, only a
    subject, a role and an expiry — a stolen token is a session, which
    is why it expires.
  * Deny-by-default: an unknown role or an unknown action is denied.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    VIEWER = "viewer"        # read the ledger
    OPERATOR = "operator"    # process documents, draft, move to review
    APPROVER = "approver"    # sign off: the human gate
    ADMIN = "admin"          # everything, incl. voiding + user mgmt


class Action(str, Enum):
    READ = "read"
    PROCESS = "process"            # create claims / obligations
    TRANSITION = "transition"      # move within the workflow
    APPROVE = "approve"            # -> SATISFIED (the gate)
    VOID = "void"                  # cancel an obligation
    MANAGE_USERS = "manage_users"


# Explicit matrix — deny by default; nothing is implied.
PERMISSIONS: dict[Role, frozenset[Action]] = {
    Role.VIEWER: frozenset({Action.READ}),
    Role.OPERATOR: frozenset({Action.READ, Action.PROCESS,
                              Action.TRANSITION}),
    Role.APPROVER: frozenset({Action.READ, Action.TRANSITION,
                              Action.APPROVE}),
    Role.ADMIN: frozenset({Action.READ, Action.PROCESS,
                           Action.TRANSITION, Action.APPROVE,
                           Action.VOID, Action.MANAGE_USERS}),
}


class PermissionDenied(Exception):
    """Raised when a principal lacks the permission for an action."""


class AuthError(Exception):
    """Raised on bad credentials or an invalid/expired token."""


@dataclass(frozen=True)
class Principal:
    """An authenticated actor. `subject` lands in the audit log."""
    subject: str
    role: Role

    def actor(self) -> str:
        return f"{self.role.value}:{self.subject}"


# ----------------------------------------------------------- passwords
_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    """scrypt with a fresh 16-byte salt. Returns 'salt$hash' (hex)."""
    if not password or len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification against a 'salt$hash' record."""
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return hmac.compare_digest(dk.hex(), hash_hex)


# -------------------------------------------------------------- tokens
def _secret() -> bytes:
    s = os.environ.get("MANDATE_SECRET_KEY")
    if not s:
        # Ephemeral per-process key: tokens die with the process rather
        # than being signed by a guessable default. Deployments MUST
        # set MANDATE_SECRET_KEY.
        s = _EPHEMERAL
    return s.encode()


_EPHEMERAL = secrets.token_hex(32)


def _b64(raw: bytes) -> str:
    return urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(principal: Principal, ttl_seconds: int = 3600) -> str:
    """Signed, expiring session token: payload.signature."""
    payload = {"sub": principal.subject, "role": principal.role.value,
               "exp": int(time.time()) + ttl_seconds}
    body = _b64(json.dumps(payload, sort_keys=True).encode())
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def verify_token(token: str) -> Principal:
    """Validate signature + expiry. Raises AuthError on any problem."""
    try:
        body, sig = token.split(".", 1)
    except (ValueError, AttributeError):
        raise AuthError("malformed token")
    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64(expected), sig):
        raise AuthError("bad signature — token tampered or forged")
    try:
        payload = json.loads(_unb64(body))
    except Exception:
        raise AuthError("malformed payload")
    if payload.get("exp", 0) < time.time():
        raise AuthError("token expired")
    try:
        return Principal(subject=payload["sub"],
                         role=Role(payload["role"]))
    except (KeyError, ValueError):
        raise AuthError("invalid principal in token")


# ------------------------------------------------------ authorization
def authorize(principal: Principal | None, action: Action) -> None:
    """Deny-by-default permission check. Raises PermissionDenied."""
    if principal is None:
        raise PermissionDenied(
            f"anonymous principal may not {action.value}")
    allowed = PERMISSIONS.get(principal.role, frozenset())
    if action not in allowed:
        raise PermissionDenied(
            f"role '{principal.role.value}' may not {action.value}")


def can(principal: Principal | None, action: Action) -> bool:
    """Non-raising variant — for UI (hide what you may not do)."""
    try:
        authorize(principal, action)
        return True
    except PermissionDenied:
        return False
