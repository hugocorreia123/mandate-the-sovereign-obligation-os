"""Mandate — Phase 15: prove the perimeter, don't promise it.

Fourteen phases have called this system "sovereign". That word has so
far rested on an architectural argument: the deterministic core needs
no network, and tiers 1-3 call nothing. True — and worth exactly
nothing to a bank, because a claim about egress that lives in a README
is a claim nobody can check.

A compose file is not evidence either. `internal: true` can be
overridden by a stray network, a helpful `extra_hosts`, a sidecar, a
proxy variable, a base image that phones home. Configuration drifts;
that is what configuration does.

So: this module tries to LEAVE. From inside the appliance, at runtime,
it attempts real connections to real endpoints. If any of them
succeeds, the appliance is not sovereign — whatever the config claims
— and it says so with the escape route named.

That is the whole design. A test that can only pass is not a test.
This one CAN fail, and knowing exactly how it fails is the product.
"""

from __future__ import annotations

import os
import socket
import ssl
from dataclasses import dataclass, field
from typing import Optional

# Endpoints that matter, and why each one is on the list.
EGRESS_TARGETS: list[tuple[str, int, str]] = [
    ("api.groq.com", 443,
     "the Tier-0 model provider — if this is reachable, a document "
     "can leave"),
    ("api.openai.com", 443,
     "any dependency could reach a model API without asking"),
    ("huggingface.co", 443,
     "model/tokenizer downloads at import time are a classic silent "
     "egress"),
    ("pypi.org", 443,
     "a package install path is a code-execution path"),
    ("8.8.8.8", 53,
     "raw DNS — the most common hole in an otherwise closed box"),
    ("1.1.1.1", 443,
     "a bare IP proves the block is not merely DNS-based"),
]

# Proxy variables silently re-open a closed perimeter.
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy")


@dataclass
class Probe:
    host: str
    port: int
    why: str
    depth: int
    detail: str = ""

    @property
    def reachable(self) -> bool:
        """Egress means the PAYLOAD got out. A route to a proxy that
        refuses the request is not egress — it is a route."""
        return self.depth >= Depth.PAYLOAD

    @property
    def route_exists(self) -> bool:
        return self.depth >= Depth.TCP


@dataclass
class SovereigntyReport:
    probes: list[Probe] = field(default_factory=list)
    proxies: dict[str, str] = field(default_factory=dict)
    groq_key_present: bool = False
    sovereign: bool = True
    findings: list[str] = field(default_factory=list)

    @property
    def escapes(self) -> list[Probe]:
        return [p for p in self.probes if p.reachable]


class Depth:
    """How far out did we actually get? The distinction matters.

    A TCP connect proves a ROUTE exists. It does not prove EGRESS: a
    deny-proxy accepts the socket and then refuses the request, so a
    connect-only probe reports a locked-down box as leaking. The first
    version of this module did exactly that — it called a proxied
    sandbox "not sovereign" on the strength of a handshake with the
    proxy itself.

    Data leaves at the application layer. So we go there.
    """
    NONE = 0        # DNS did not resolve
    TCP = 1         # a socket opened — a route exists
    TLS = 2         # a TLS session with a cert for THIS host
    PAYLOAD = 3     # a real HTTP response from the real host


# Depth NONE is reached by a DNS failure OR a refused route — the
# label must not claim to know which. The detail column says.
DEPTH_NAME = {0: "nothing", 1: "TCP only", 2: "TLS", 3: "PAYLOAD OUT"}


def _probe(host: str, port: int, timeout: float = 3.0
           ) -> tuple[int, str]:
    """Return how deep we got, and what stopped us."""
    try:
        socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return Depth.NONE, f"DNS did not resolve ({e.strerror or e})"
    except Exception as e:
        return Depth.NONE, f"DNS error: {e}"

    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
    except (socket.timeout, TimeoutError):
        s.close()
        return Depth.NONE, "TCP timed out (filtered at the network)"
    except OSError as e:
        s.close()
        return Depth.NONE, f"TCP refused ({e.strerror or e})"

    if port != 443:
        s.close()
        return Depth.TCP, "TCP route open (non-TLS port)"

    try:
        ctx = ssl.create_default_context()
        w = ctx.wrap_socket(s, server_hostname=host)
    except ssl.SSLError as e:
        s.close()
        return Depth.TCP, f"TCP open but TLS refused ({e.reason or e})"
    except Exception as e:
        s.close()
        return Depth.TCP, f"TCP open, TLS failed ({e})"

    # A TLS session proves we are talking to something that holds a
    # cert for this host. Now: does a real request come back?
    try:
        w.sendall(
            f"HEAD / HTTP/1.1\r\nHost: {host}\r\n"
            f"User-Agent: mandate-sovereignty-audit\r\n"
            f"Connection: close\r\n\r\n".encode())
        data = w.recv(256)
    except Exception as e:
        w.close()
        return Depth.TLS, f"TLS up but no response ({e})"
    finally:
        try:
            w.close()
        except Exception:
            pass

    if not data:
        return Depth.TLS, "TLS up, empty response"
    first = data.split(b"\r\n")[0].decode("latin-1", "replace")
    # A proxy denial is still a denial: the payload did not reach the
    # host. Report it as blocked, and say who blocked it.
    if b" 403" in data[:16] or b" 407" in data[:16] or \
            b"denied" in data.lower()[:200]:
        return Depth.TLS, f"reached a gateway, request DENIED ({first})"
    return Depth.PAYLOAD, f"real response: {first}"


def audit(targets: Optional[list] = None,
          timeout: float = 3.0) -> SovereigntyReport:
    """Try to leave. Report every way out that worked."""
    r = SovereigntyReport()
    for host, port, why in (targets or EGRESS_TARGETS):
        depth, detail = _probe(host, port, timeout)
        r.probes.append(Probe(host, port, why, depth, detail))

    r.proxies = {v: os.environ[v] for v in PROXY_VARS
                 if os.environ.get(v)}
    r.groq_key_present = bool(os.environ.get("GROQ_API_KEY"))

    for p in r.escapes:
        r.findings.append(
            f"EGRESS: {p.host}:{p.port} is REACHABLE — {p.why}. "
            f"{p.detail}")
    if r.proxies:
        r.findings.append(
            f"PROXY: {', '.join(r.proxies)} set — a proxy variable "
            f"re-opens a perimeter the network closed, and does it "
            f"invisibly.")
    if r.groq_key_present:
        r.findings.append(
            "CREDENTIAL: GROQ_API_KEY is present in the environment. "
            "Harmless if nothing can be reached — but a key inside a "
            "sovereign appliance has no purpose, and its presence "
            "means someone intended egress.")

    routed = [p for p in r.probes
              if p.route_exists and not p.reachable]
    if routed:
        r.findings.append(
            f"ROUTE (not egress): {len(routed)} target(s) accepted a "
            f"connection but refused the request — "
            f"{', '.join(p.host for p in routed)}. Nothing left the "
            f"box, but something is answering on its behalf: a proxy "
            f"or gateway sits in the path. A perimeter enforced by a "
            f"proxy is a policy; one enforced by routing is a wall.")

    # DNS-only blocking is a real finding: it is a weaker guarantee.
    blocked = [p for p in r.probes if not p.route_exists]
    dns_only = [p for p in blocked if "DNS" in p.detail]
    if blocked and dns_only and len(dns_only) == len(blocked):
        r.findings.append(
            "WEAK: every target failed at DNS only. A bare IP may "
            "still route. Block at the network, not the resolver.")

    r.sovereign = not r.escapes and not r.proxies
    return r


def render(r: SovereigntyReport) -> str:
    lines = ["", "=" * 68,
             "  SOVEREIGNTY AUDIT — can anything leave this box?",
             "=" * 68, ""]
    lines.append(f"{'target':<26}{'':2}{'verdict':<10}"
                 f"{'reached':<12}detail")
    for p in r.probes:
        mark = ("✗ EGRESS" if p.reachable
                else "~ route" if p.route_exists else "✓ blocked")
        lines.append(f"{p.host + ':' + str(p.port):<26}{'':2}"
                     f"{mark:<10}{DEPTH_NAME[p.depth]:<12}"
                     f"{p.detail[:38]}")
    lines.append("")
    if r.sovereign:
        lines += ["  ✓ SOVEREIGN — every egress attempt failed.",
                  "    Verified by trying, not by configuration.", ""]
    else:
        lines += ["  ✗ NOT SOVEREIGN — this box can reach the "
                  "outside world.", ""]
    for f in r.findings:
        lines.append(f"  • {f}")
    if r.findings:
        lines.append("")
    lines.append("=" * 68)
    return "\n".join(lines)
