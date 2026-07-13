# Mandate — The Sovereign Obligation Operating System

**Legal AI reads documents. IDP extracts fields. Mandate executes what the enterprise owes — and keeps executing when the cloud is gone.**

---

## The harsh truth this rides

If you want to build a category-defining system in 2026, recognize two truths at once:

**Truth 1 — Legal AI and IDP are no longer products; they are features of a larger system.** Enterprises are tired of paying for an AI that *reads* a contract or *extracts* an invoice. A contract is not information — it is a **machine that generates obligations**: pay X by date Y, respond within Z business days, renew 90 days before term, notify the regulator, disclose the breach. Today those obligations are born in PDFs, live in inboxes, and die in missed deadlines. The cost isn't abstract: missed prazos are the single largest malpractice category in law; unmanaged renewals and indexation clauses leak revenue silently; a single missed regulatory response window is a front-page fine.

**Truth 2 — The enterprises that need this most are the ones that cannot buy what exists.** Banks under DORA, insurers, courts, healthcare groups, defense, public administration — the exact buyers drowning in obligation-bearing documents — are legally or contractually barred from streaming those documents to a US cloud API. And even where they may, they've learned the second question: *what happens when the API is down, rate-limited, or deprecated mid-quarter?* The current answer across the entire legal-AI landscape is silence.

**Mandate is the answer to both truths in one system: an Obligation Operating System that runs inside your perimeter and degrades gracefully all the way down to paper.**

You don't beat Legal AI and IDP by building a smarter reader. You beat them by **absorbing them** — extraction becomes a subsystem, reading becomes a pipeline stage, and the product becomes the thing the enterprise actually needs: **a living ledger of what it owes, to whom, by when — and the execution of it.**

**Category: Obligation Intelligence. Deployment doctrine: Sovereign by default. Resilience doctrine: the dangerous parts never needed the cloud.**

---

## The Problem, precisely

Enterprise commitments are trapped across three gaps:

1. **The document gap.** Obligations arrive as scanned court notifications, 80-page contracts, regulator letters, email attachments — in Portuguese, English, Spanish, French — unstructured, adversary-authored, deadline-bearing.
2. **The execution gap.** Even when a human reads the document correctly, the follow-through (compute the real deadline under the right legal counting rules, draft the response, route for approval, file, update the ledger) is manual glue-work performed by expensive people under time pressure.
3. **The trust gap.** Where AI is applied, nobody can answer the auditor: *why did the system say the deadline is the 14th? Which model version? What was its measured error rate? Who approved the action? What happened during the outage on the 3rd?*

Humans are currently the expensive, slow, error-prone bridge across all three. Mandate replaces the bridge — and keeps a human exactly where the measured error rate says one must stand.

---

## The Solution

**Mandate ingests every document that creates a commitment and compiles it into a living Obligation Graph — then runs governed agent workflows against that graph:**

- **Perceive.** Vision-language parsing of native PDFs, scans, stamps, tables, handwriting — in the source language, no translate-then-extract. Every extracted fact is a **typed, confidence-scored claim with a source span** (page, region) — and the system abstains into a human queue when unsure, instead of guessing.
- **Compile.** Claims become nodes in the **Obligation Graph**: parties, amounts, legal bases, obligation types, dependencies, states (pending → responded → satisfied → escalated). Amendments, renewals and rulings *mutate the graph*, never overwrite history.
- **Compute.** The **Deadline Engine** — deterministic, rule-encoded, LLM-free — computes the real due date under the governing jurisdiction's counting rules: business vs calendar days, judicial holidays, statutory suspension periods. Courts do not accept "the model estimated." **The LLM proposes; the engine computes.**
- **Act.** An agent crew drafts the response, filing, renewal notice, or payment instruction — citing the exact clause or statute with verifiable links — and a **red-team agent attacks the draft** before it ever reaches a person.
- **Gate.** Every action lands on a risk-ranked **Approve/Execute dashboard** carrying its confidence, its groundedness score, and its evidence chain. **AI suggests; a human decides.** The gate isn't compliance theater — it is placed where the *measured* error rate says it must be.
- **Remember.** Append-only, hash-chained audit log of every claim, computation, draft, approval, and — crucially — every **degradation event**. The outage itself becomes an auditable, DORA-reportable record.

### The MVP wedge (where you start)

**Judicial/regulatory notifications + contract renewals**, end-to-end, in a single Docker-Compose appliance:

1. A scanned *citação* / regulator letter / renewal-bearing contract lands (upload, watch-folder, or mail intake).
2. The **Obligation Agent** extracts parties, amounts, legal basis, obligation type — in Portuguese, English, or Spanish, natively.
3. The **Deadline Engine** computes the true due date under the correct jurisdiction pack — the thing LLMs silently get wrong and that costs real malpractice money.
4. The **Drafting Agent** produces the response in the language of the court/counterparty, citing the governing article with a verifiable link; the **Red-Team Agent** tries to break it.
5. The human sees one screen: obligation, deadline calendar, draft, evidence, confidence — **Approve / Edit / Reject**.
6. The graph updates; the ledger is current; the audit log grew by one immutable chapter.

You win Legal AI and IDP by absorbing them into a system that actually finishes the job — and you win the sovereign market by being the only one who can run that system with the network cable pulled.

---

## The Architecture: three pillars on two axes

### Axis design (the insight most teams miss)

**Language and jurisdiction are different axes.** An English contract can be governed by Portuguese law; a French notice can bind a Spanish subsidiary. Every document gets both tags at ingestion — language detected, jurisdiction inferred from court headers, citations and governing-law clauses, **human-confirmable** because getting it wrong changes deadlines. Language routes *models and prompts*; jurisdiction routes *rules*.

### Pillar 1 — Sovereign Multimodal Perception (the IDP evolution)

- **VLM-first parsing** with a fully local path: frontier VLM in the connected profile; **Qwen2.5-VL via Ollama** in the sovereign profile; DocTR/PaddleOCR beneath it. Nested tables, stamps, handwriting, multi-language — converted to structured claims without losing layout context.
- **Extraction in the source language** — translation loses the legal terms that matter ("citação" ≠ "summons" in consequence). Canonical English field names, source-language values, assistive translations stored side-by-side, **source always authoritative**.
- **Abstention as a feature**: every field carries calibrated confidence; below threshold, it routes to a human data-entry queue instead of hallucinating. In legal documents, a confident wrong answer is the worst output class that exists.
- **Vectorized memory** (multilingual embeddings — bge-m3 class — with per-language BM25 fallback) so agents recall past contracts, prior notifications from the same court, the company's own policy corpus — cross-lingually: ask in English, retrieve the Portuguese statute.

### Pillar 2 — Deterministic Core + Governed Agent Crew (the reasoning engine)

- **The sacred/deterministic split** — the architectural doctrine that beats pure-LLM competitors: anything with legal consequence (deadline arithmetic, money math, obligation state transitions) is **rule-encoded, tested, versioned code**. Agents feed it; agents never override it.
- **Jurisdiction Packs**: the Deadline Engine is one engine with pluggable rule-packs — `packs/PT/` (dias úteis, férias judiciais, CPC counting rules), `packs/EU/` (regulation deadlines, jurisdiction-uniform), `packs/ES/` next — each pack shipping with **its own test suite of hand-verified deadline cases**. The pack structure *is* the geographic expansion story.
- **Stateful, interruptible workflows** (LangGraph): a ten-minute multi-document workflow checkpoints, pauses on human gates, survives an outage mid-flight, and resumes — store-and-forward queues and circuit breakers included, with every breaker trip logged as an auditable event.
- **Agentic debate where stakes are high**: a Drafting Agent writes; a Red-Team Agent attacks (wrong article? mis-stated amount? missed exception?); iteration until the attack fails or the human is warned. The pattern is proven in my prior systems; here it guards legal drafts.

### Pillar 3 — The Measured Trust Layer (the actual moat)

Every competitor demos capability and hides error rates. Mandate's trust layer makes measurement the product:

- **Per-field extraction F1 vs a hand-built gold set — per language, per tier.**
- **Deadline accuracy vs hand-computed truth, per jurisdiction pack** (a deterministic engine should score ~100%; *proving it* is the point).
- **Citation faithfulness with verifiable spans** — every cited article resolves to a real, linkable source that says what the draft claims.
- **Cross-family LLM judge** auditing draft groundedness, **itself validated against blind human labels (Cohen's κ)** — and reported honestly even when κ is uncomfortable, because that is what makes the number mean something.
- **Conformal-calibrated confidence** on extracted fields — "80% confident" empirically covers ~80%.
- All of it surfaced on a **compliance dashboard an auditor could read**, per model version, over time.

---

## The Resilience Doctrine: the Degradation Ladder

The defining design decision: **the legally dangerous parts never depended on connectivity.** Deadlines compute, obligations track, queues accept, alerts fire — with zero LLMs on earth reachable. The AI layers *accelerate*; they do not *enable*. Formally:

| Tier | Mode | What runs | Quality (measured, published) |
|---|---|---|---|
| **0** | ☁️ Connected | Frontier VLM/LLM (redacted egress) | Best — e.g. extraction F1 ~0.94 |
| **1** | 🔒 Sovereign | Local models via Ollama (Qwen2.5-VL, 7–8B text; EuroLLM/Salamandra benchmarked as EU-native options) | Honest delta published — e.g. ~0.87 |
| **2** | ⚙️ Classical | Local OCR + layout heuristics + regex extractors, TF-IDF retrieval, sklearn classifiers | Lower still — published — human queue absorbs the gap |
| **3** | 📋 Doctrine | **Deterministic core + executable playbooks + humans**: deadlines still compute, intake still queues, versioned response playbooks guide manual drafting | The floor that never falls |

A live **system-mode badge (Tier 0/1/2/3)** sits in the UI. Circuit breakers demote tiers automatically on health-check failure and log the transition. Store-and-forward means nothing is lost, only deferred. **DORA doesn't ask if you have AI; it asks what happens when it fails — Mandate answers with an auditable record of exactly that.**

## The Sovereignty Doctrine (the Vault inheritance)

Sovereign is the **default profile**, not the fallback:

- **One Docker-Compose appliance**: local VLM + LLM (Ollama), local OCR, local vector store, the full pipeline — **zero egress by network policy, enforced, not promised**.
- **Tier-0 cloud burst is the optional upgrade**, gated by PII pseudonymization before any external call, with the redaction step itself logged.
- Encryption at rest, signed model artifacts, offline license/update path — deployable where the internet isn't.
- The pitch line the sovereign market has never heard with receipts: *"Here is the measured quality difference between our air-gapped mode and the frontier cloud — per field, per language. You choose the trade; we publish the delta."*

## Security baseline (day one, not roadmap)

OIDC/JWT auth + RBAC scoped per matter · TLS everywhere · encryption at rest · secrets vaulted · **append-only hash-chained audit log** (a court may one day read it) · **prompt-injection defense as a core threat model** — a served legal notice is *attacker-authored input*: strict tool allowlists, document-derived text never triggers actions directly, output filtering · egress allowlist · dependency auditing · rate limiting · backup + restore drill · a written **threat model in the repo**.

## Multilingual, measured

MVP languages: **pt-PT + English** (es/fr/de architecturally ready via prompt locales and packs). UI localized (pt/en), dates timezone-explicit ("23:59 Europe/Lisbon" on every deadline, always), side-by-side source/translation with source authoritative. And the differentiator nobody else ships: **per-language, per-tier evaluation tables** — because local models degrade unevenly across languages, and publishing that delta is worth more than claiming five languages and measuring none.

---

## Why this wins

- **Against IDP vendors:** they stop at fields; Mandate owns the obligation, the deadline, the draft, and the execution record. Extraction is a commodity subsystem inside it.
- **Against legal-AI copilots (Harvey-class):** cloud-only, English-first, error-rates-undisclosed, and structurally unsellable to the regulated European buyer. Mandate is sovereign-first, multilingual-measured, and publishes its numbers.
- **Against agent platforms:** capability without governance is undeployable in the EU. Mandate's human gates are placed by measured error rates, its evaluation runs at runtime, and its outages are auditable events — that is what an AI-Act/DORA buyer's checklist actually says.
- **Against "we'll add offline later":** resilience retrofitted is a feature; resilience as architecture is a moat. The deterministic core + ladder cannot be bolted on afterward.

## The demo that closes the room

Drop a scanned Portuguese *citação* on the screen. Watch: extraction with source-span highlights → jurisdiction inferred, deadline calendar computed under PT counting rules → response drafted in Portuguese, articles cited with live links → red-team pass → the Approve screen with confidence and groundedness. Then — **pull the network cable** (toggle Tier 0 off, live). The badge flips to 🔒. Drop a second document. The same flow completes on local models, the quality delta displayed honestly, the degradation logged. Thirty seconds that contain the category, the sovereignty, the resilience, and the measurement culture — none of which any competitor can replay.

## Positioning line

> **Mandate — the Obligation Operating System. It reads what your enterprise signed, computes what it owes under the law that governs it, drafts what must be sent, and asks a human before anything happens. In your language. Inside your perimeter. Even when the cloud is gone. With its error rates on the label.**

---

*Hugo Correia — Data Scientist / ML & AI Engineer, Lisbon · linkedin.com/in/hugogncorreia · github.com/hugocorreia123*
