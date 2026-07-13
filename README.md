# Mandate — The Sovereign Obligation OS

**Legal AI reads documents. IDP extracts fields. Mandate executes what the enterprise owes — and keeps executing when the cloud is gone.**

![status](https://img.shields.io/badge/status-in__progress-F9A826) ![python](https://img.shields.io/badge/python-3.11-blue) ![tests](https://img.shields.io/badge/deadline_engine-21%2F21_hand--verified-2EA44F) ![license](https://img.shields.io/badge/license-Apache--2.0-green)

> 🚧 **Built in public, phase by phase, one verified checkpoint at a time.** Claims below are made only as they are earned; the roadmap shows what's shipped vs planned.

---

## The thesis

Every contract, court notification, regulation and SLA is a **machine that generates obligations** — pay X by date Y, respond within Z business days, renew 90 days before term, notify the regulator. Today those obligations are born in PDFs, live in inboxes, and die in missed deadlines: missed *prazos* are the single largest legal-malpractice category, and unmanaged renewals leak revenue silently.

**Mandate compiles obligation-bearing documents into a living Obligation Graph and executes the follow-through** — deadline computation, drafted responses, human-gated actions — under two doctrines most AI products can't claim:

1. **The sacred/deterministic split.** Anything with legal consequence — deadline arithmetic, money math, obligation state — is rule-encoded, tested, versioned code with statutory citations. **The LLM proposes; the engine computes.** Courts do not accept "the model estimated."
2. **Sovereign & resilient by architecture.** The system runs inside the customer's perimeter and degrades gracefully: frontier LLM → local models → classical heuristics → **rules + playbooks + humans**. The legally dangerous parts never depended on connectivity — an outage is a quality dial, not a failure, and it's logged as an auditable event.

Multilingual by design (language ≠ jurisdiction: an English contract can be governed by Portuguese law — the two are separate, routed axes). Evaluation is the moat: per-field extraction F1 per language per tier, citation faithfulness with verifiable spans, cross-family LLM judges validated against blind human labels (Cohen's κ) — the methodology proven in [Tracer](https://github.com/hugocorreia123/tracer-aml-graph-intelligence) (κ=0.942) and [Voyager](https://github.com/hugocorreia123/voyager) (κ=0.95).

## What exists today (verified)

**Phase 1 — the Deadline Engine + PT jurisdiction pack.** The deterministic heart, built first because everything hangs off it. Three everyday Portuguese counting regimes, each with its statutory basis encoded:

| Regime | Basis | Encoded rules |
|---|---|---|
| `cc_corridos` — prazo civil contínuo | Código Civil art. 279.º | event-day exclusion (al. b); term ending **Sunday/holiday rolls** to next working day (al. e) — **Saturdays do not roll under the CC** |
| `cpc_processual` — prazo processual | CPC art. 138.º + LOSJ art. 28.º | continuous counting **suspended during férias judiciais** (Natal · Palm Sunday→Easter Monday, computed from the Easter algorithm · Verão); urgent-process exception; end falling when courts are closed (**Sat/Sun/holiday**) rolls forward (n.º 2) |
| `cpa_uteis` — prazo administrativo | CPA art. 87.º | business-day counting (weekends & national holidays excluded) |

**21/21 hand-verified test cases green** — including the Saturday-rolls-under-CPC-but-not-CC nuance, month-end clamping (31 Jan + 1 month → 28 Feb), an event landing *inside* férias judiciais, and the Natal window spanning the year boundary. Every computed deadline returns an **explanation trace with legal references** — the auditable evidence chain:

```
regime: Prazo processual (CPC)
refs:   CPC, art. 138.º (contínuo; suspensão em férias judiciais; n.º 2 end-roll)
        + CC art. 279.º b) + LOSJ art. 28.º
  1. Event date: 2026-03-23 (Monday).
  2. Day of the event is not counted; counting starts 2026-03-24 [start-day exclusion].
  3. Counted 10 continuous days with 9 day(s) suspended during judicial
     vacations: reaches 2026-04-11 (Saturday).
  4. End falls on Saturday (2026-04-11): rolls to next day [end-roll rule].
  5. End falls on Sunday (2026-04-12): rolls to next day [end-roll rule].
  6. DUE: 2026-04-13 (Monday), 23:59 Europe/Lisbon.
```

*Documented MVP limitations: municipal holidays, dilação (CPC art. 245.º), the ≥6-month exception, and the art. 139.º grace-days regime are out of scope and listed as such. Encoded rules are a simplified, source-cited engineering implementation — not legal advice.*

## Architecture (planned)

```
Documents (pt/en/es · PDFs, scans, mail) 
   → SOVEREIGN PERCEPTION  (VLM parsing, local path via Ollama;
     typed claims + source spans + calibrated confidence + abstention)
   → OBLIGATION GRAPH  (parties, amounts, legal bases, states —
     append-only, evidence-linked)
   → DEADLINE ENGINE  ✅ (deterministic; jurisdiction packs: PT ✅ · EU next)
   → AGENT CREW  (extract → cross-check → draft → red-team; LangGraph,
     interruptible, store-and-forward)
   → HUMAN GATE  (risk-ranked approve/execute; gates placed by measured
     error rates)
   → AUDIT LOG  (append-only, hash-chained; degradation events included)
```

**The Degradation Ladder** — resilience as architecture, not a feature:

| Tier | Mode | What runs |
|---|---|---|
| 0 | ☁️ Connected | Frontier VLM/LLM (redacted egress) |
| 1 | 🔒 Sovereign | Local models via Ollama (Qwen2.5-VL class; EuroLLM benchmarked) |
| 2 | ⚙️ Classical | Local OCR + layout heuristics + regex + TF-IDF |
| 3 | 📋 Doctrine | **Deterministic core + playbooks + humans — the floor that never falls** |

## Roadmap

- [x] **Phase 1 — Deadline Engine + PT pack**: 3 regimes, férias judiciais via Easter algorithm, 21 hand-verified cases, explanation traces
- [ ] **Phase 1b — EU jurisdiction pack**: Regulation 1182/71 counting rules — proves the pack architecture with a second jurisdiction
- [ ] **Phase 2 — Obligation Graph**: Pydantic schema (claims, obligations, states, evidence spans), append-only store
- [ ] **Phase 3 — Perception, tiered**: VLM extraction (cloud + local Ollama path) vs classical heuristics — **per-field F1, per language, per tier, measured on a hand-built gold set**
- [ ] **Phase 4 — Synthetic corpus + gold set**: pt/en notification & renewal documents with ground truth
- [ ] **Phase 5 — Agent crew**: obligation agent → deadline proposal → drafting agent → red-team, human gate
- [ ] **Phase 6 — Trust layer**: citation faithfulness, cross-family judge, blind human labels → Cohen's κ; conformal confidence
- [ ] **Phase 7 — Security baseline**: RBAC, hash-chained audit log, PII pseudonymization before egress, prompt-injection defenses, threat model
- [ ] **Phase 8 — The appliance**: Docker-Compose sovereign profile, zero-egress by network policy, tier badge + pull-the-cable demo
- [ ] **Phase 9 — Findings-first README**

## Reproduce Phase 1

```bash
git clone https://github.com/hugocorreia123/mandate-the-sovereign-obligation-os
cd mandate-the-sovereign-obligation-os && uv sync
uv run pytest -q        # 21 passed
```

## Related work by me

Mandate applies the detect → investigate → human-decide pattern to a new domain — **legal obligations** — after [Tracer](https://github.com/hugocorreia123/tracer-aml-graph-intelligence) (financial-crime networks, κ=0.942), [Turbine](https://github.com/hugocorreia123/turbine-predictive-maintenance) (physical assets, live demo), and [Sentinel](https://github.com/hugocorreia123/sentinel-fraud-mlops) (transaction fraud MLOps) — with the same discipline: honest baselines, measured findings including the negative ones, and a human in the loop by measured necessity.

---

*Hugo Correia — [LinkedIn](https://www.linkedin.com/in/hugogncorreia) · Data Scientist / ML & AI Engineer, Lisbon*
