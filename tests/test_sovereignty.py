"""Phase 15 — proving the perimeter.

The module under test is unusual: its job is to FAIL when the box can
leave. So the tests fake a network, because a test that depends on the
real one tests the CI runner's firewall rather than the code.
"""

import pytest

from sovereignty import (Depth, EGRESS_TARGETS, PROXY_VARS, Probe,
                         SovereigntyReport, audit, render)


def _fake(depths: dict):
    """Patch the probe: host -> (depth, detail)."""
    def probe(host, port, timeout=3.0):
        return depths.get(host, (Depth.NONE, "TCP refused (blocked)"))
    return probe


@pytest.fixture()
def blocked(monkeypatch):
    import sovereignty
    monkeypatch.setattr(sovereignty, "_probe",
                        _fake({}))          # everything blocked
    for v in PROXY_VARS + ("GROQ_API_KEY",):
        monkeypatch.delenv(v, raising=False)


# ------------------------------------------- route is not egress
def test_a_route_to_a_deny_proxy_is_not_egress(monkeypatch):
    """The bug this module had on its first run: a TCP connect to a
    proxy that then REFUSES the request was reported as "reachable",
    which called a locked-down box leaky. Data leaves at the
    application layer, so that is where the verdict is taken."""
    import sovereignty
    monkeypatch.setattr(sovereignty, "_probe", _fake({
        "api.groq.com": (Depth.TLS,
                         "reached a gateway, request DENIED (403)")}))
    for v in PROXY_VARS + ("GROQ_API_KEY",):
        monkeypatch.delenv(v, raising=False)
    r = audit()
    groq = [p for p in r.probes if p.host == "api.groq.com"][0]
    assert groq.route_exists is True
    assert groq.reachable is False          # nothing left the box
    assert r.sovereign is True
    assert any("ROUTE (not egress)" in f for f in r.findings)


def test_a_real_response_is_egress_and_fails_the_audit(monkeypatch):
    import sovereignty
    monkeypatch.setattr(sovereignty, "_probe", _fake({
        "api.groq.com": (Depth.PAYLOAD,
                         "real response: HTTP/1.1 200 OK")}))
    for v in PROXY_VARS + ("GROQ_API_KEY",):
        monkeypatch.delenv(v, raising=False)
    r = audit()
    assert r.sovereign is False
    assert any("EGRESS: api.groq.com" in f for f in r.findings)
    assert len(r.escapes) == 1


def test_a_fully_blocked_box_is_sovereign(blocked):
    r = audit()
    assert r.sovereign is True
    assert r.escapes == []
    assert "✓ SOVEREIGN" in render(r)


# --------------------------------------------- the quiet holes
def test_a_proxy_variable_breaks_sovereignty_even_with_all_probes_blocked(
        blocked, monkeypatch):
    """A perimeter closed by the network can be silently re-opened by
    an environment variable. Blocked probes are not enough."""
    monkeypatch.setenv("HTTPS_PROXY", "http://corp-proxy:3128")
    r = audit()
    assert r.sovereign is False
    assert any("PROXY" in f for f in r.findings)


def test_a_credential_inside_the_appliance_is_reported(
        blocked, monkeypatch):
    """Harmless if nothing is reachable — but a key in a sovereign box
    has no purpose, and its presence means someone intended egress."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_whatever")
    r = audit()
    assert r.groq_key_present is True
    assert any("CREDENTIAL" in f for f in r.findings)
    assert r.sovereign is True      # a finding, not a breach


def test_dns_only_blocking_is_flagged_as_weak(monkeypatch):
    """If every target failed at DNS, a bare IP may still route.
    Block at the network, not the resolver."""
    import sovereignty
    monkeypatch.setattr(sovereignty, "_probe",
                        lambda h, p, timeout=3.0:
                        (Depth.NONE, "DNS did not resolve"))
    for v in PROXY_VARS + ("GROQ_API_KEY",):
        monkeypatch.delenv(v, raising=False)
    r = audit()
    assert any("WEAK" in f for f in r.findings)


# ------------------------------------------------- the target list
def test_the_target_list_covers_the_ways_out_that_matter():
    hosts = {h for h, _, _ in EGRESS_TARGETS}
    assert "api.groq.com" in hosts          # our own tier-0 provider
    assert "huggingface.co" in hosts        # silent import-time fetch
    assert "8.8.8.8" in hosts               # raw DNS
    assert "1.1.1.1" in hosts               # a bare IP, not just DNS
    assert all(why for _, _, why in EGRESS_TARGETS)  # each says why


def test_every_finding_names_the_escape_route(monkeypatch):
    import sovereignty
    monkeypatch.setattr(sovereignty, "_probe", _fake({
        "huggingface.co": (Depth.PAYLOAD, "real response: 200")}))
    for v in PROXY_VARS + ("GROQ_API_KEY",):
        monkeypatch.delenv(v, raising=False)
    r = audit()
    assert "huggingface.co" in r.findings[0]
    assert "silent egress" in r.findings[0]     # and WHY it matters


def test_render_is_readable_for_both_verdicts(blocked):
    ok = render(audit())
    assert "SOVEREIGNTY AUDIT" in ok and "✓ SOVEREIGN" in ok
    bad = render(SovereigntyReport(
        probes=[Probe("api.groq.com", 443, "why", Depth.PAYLOAD,
                      "200 OK")],
        sovereign=False, findings=["EGRESS: api.groq.com"]))
    assert "✗ NOT SOVEREIGN" in bad
