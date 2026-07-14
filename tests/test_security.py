"""Phase 6 — security baseline tests.

Covers: the permission matrix (incl. deny-by-default), password
hashing, token forgery/tampering/expiry, and — the point of the whole
module — that authorization is *enforced on the obligation state
machine*, so only an approver can satisfy an obligation.
"""

import time
from datetime import date

import pytest

from graph import (Claim, ClaimType, Obligation, ObligationGraph,
                   ObligationStatus, ObligationType, SourceSpan)
from security import (Action, AuthError, PermissionDenied, Principal,
                      Role, authorize, can, hash_password, issue_token,
                      verify_password, verify_token)

VIEWER = Principal("ana", Role.VIEWER)
OPERATOR = Principal("bruno", Role.OPERATOR)
APPROVER = Principal("carla", Role.APPROVER)
ADMIN = Principal("diogo", Role.ADMIN)


# ---------------------------------------------------- permission matrix
def test_matrix_grants_and_denies():
    authorize(VIEWER, Action.READ)                 # ok
    authorize(OPERATOR, Action.PROCESS)            # ok
    authorize(APPROVER, Action.APPROVE)            # ok
    authorize(ADMIN, Action.MANAGE_USERS)          # ok
    with pytest.raises(PermissionDenied):
        authorize(VIEWER, Action.PROCESS)
    with pytest.raises(PermissionDenied):
        authorize(OPERATOR, Action.APPROVE)        # the key denial
    with pytest.raises(PermissionDenied):
        authorize(APPROVER, Action.VOID)


def test_anonymous_is_denied_by_default():
    with pytest.raises(PermissionDenied):
        authorize(None, Action.READ)
    assert can(None, Action.READ) is False


def test_can_is_non_raising():
    assert can(APPROVER, Action.APPROVE) is True
    assert can(OPERATOR, Action.APPROVE) is False


# ---------------------------------------------------------- passwords
def test_password_hash_verify_roundtrip():
    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored) is True
    assert verify_password("wrong password", stored) is False


def test_password_hashes_are_salted_uniquely():
    a = hash_password("same password 123")
    b = hash_password("same password 123")
    assert a != b                      # different salt each time
    assert verify_password("same password 123", a)
    assert verify_password("same password 123", b)


def test_password_minimum_length_enforced():
    with pytest.raises(ValueError):
        hash_password("short")


def test_verify_rejects_garbage_record():
    assert verify_password("anything", "not-a-valid-record") is False


# ------------------------------------------------------------- tokens
def test_token_roundtrip():
    tok = issue_token(APPROVER)
    p = verify_token(tok)
    assert p.subject == "carla" and p.role is Role.APPROVER


def test_tampered_token_rejected():
    tok = issue_token(OPERATOR)
    body, sig = tok.split(".", 1)
    # forge a payload claiming approver, keep the old signature
    forged = issue_token(APPROVER).split(".", 1)[0] + "." + sig
    with pytest.raises(AuthError):
        verify_token(forged)


def test_expired_token_rejected():
    tok = issue_token(ADMIN, ttl_seconds=-1)
    with pytest.raises(AuthError):
        verify_token(tok)


def test_malformed_token_rejected():
    with pytest.raises(AuthError):
        verify_token("garbage")


# ----------------------------- enforcement on the obligation lifecycle
def _obligation(g: ObligationGraph) -> str:
    c = g.add_claim(Claim(
        type=ClaimType.OBLIGATION_TRIGGER, value={"x": 1},
        confidence=0.9, source=SourceSpan(doc_id="d1")))
    o = g.create_obligation(Obligation(
        type=ObligationType.RESPOND, description="contestação",
        debtor="X", creditor="Y", jurisdiction="PT",
        regime_id="cpc_processual", event_date=date(2026, 3, 23),
        claim_ids=[c.id]))
    g.transition(o.id, ObligationStatus.IN_PROGRESS, "agent")
    g.transition(o.id, ObligationStatus.AWAITING_APPROVAL, "agent")
    return o.id


def test_operator_cannot_approve(tmp_path):
    g = ObligationGraph(tmp_path / "log.jsonl")
    oid = _obligation(g)
    with pytest.raises(PermissionDenied):
        g.transition(oid, ObligationStatus.SATISFIED, "x",
                     principal=OPERATOR)
    # unchanged: the gate held
    assert g.obligations[oid].status is ObligationStatus.AWAITING_APPROVAL


def test_approver_can_approve_and_is_named_in_the_log(tmp_path):
    g = ObligationGraph(tmp_path / "log.jsonl")
    oid = _obligation(g)
    g.transition(oid, ObligationStatus.SATISFIED, "ignored",
                 principal=APPROVER)
    assert g.obligations[oid].status is ObligationStatus.SATISFIED
    # the ledger records WHO approved, with their role
    last = g.log_path.read_text().splitlines()[-1]
    assert "approver:carla" in last
    assert g.verify_chain() is True


def test_viewer_cannot_even_transition(tmp_path):
    g = ObligationGraph(tmp_path / "log.jsonl")
    oid = _obligation(g)
    with pytest.raises(PermissionDenied):
        g.transition(oid, ObligationStatus.IN_PROGRESS, "x",
                     principal=VIEWER)


def test_admin_can_void(tmp_path):
    g = ObligationGraph(tmp_path / "log.jsonl")
    oid = _obligation(g)
    g.transition(oid, ObligationStatus.ESCALATED, "x",
                 principal=APPROVER)
    g.transition(oid, ObligationStatus.VOID, "x", principal=ADMIN)
    assert g.obligations[oid].status is ObligationStatus.VOID
