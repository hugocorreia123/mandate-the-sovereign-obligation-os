# Findings

*Mandate — The Sovereign Obligation OS. Twenty phases, 291 tests, three jurisdictions, one live demo and one air-gapped appliance. This is what the work actually taught, including the parts that were embarrassing.*

---

## The finding of findings

Every measurement in this project was wrong the first time.

Not *some*. Every one. The extraction benchmark scored 0.00 because a scorer edit dropped a return statement. The scan-degradation profiles were too gentle for tesseract to notice. The sovereignty verifier called a locked-down box leaky. The judge's score moved *opposite* to quality across four consecutive versions. The scorecard — the module whose entire job is to stop numbers rotting — pinned a number from a six-document run and never noticed. Two of the language-detection rules misclassified whole document types. My own tests were wrong at least five times: I miscounted Spanish *días hábiles*, guessed Easter's cost by eye, wrote an off-by-one on a decade boundary, and wrote a test that failed on its own docstring.

What caught each of them was never care, and never review. **It was always a second instrument disagreeing with the first.**

- The **deterministic checks** caught the judge rating four empty strings as perfect.
- The **judge**, once its evidence pack was fixed, caught a **10× money error** the deterministic checks had waved through — the digits were right and only the words were wrong.
- The **third jurisdiction** caught an architectural assumption two jurisdictions had hidden.
- The **hardening pass** caught a ledger that couldn't answer a question about itself.
- The **scorecard** caught the scorecard.
- **Blind human labels** caught a drafter regression that the LLM judge had passed — and that regression existed because I had overwritten the fix with a stale file.

None of these instruments is reliable. The *disagreements between them* are. That is the thesis of this project, arrived at by accident and then verified twenty times: **measurement is a system, not a step.** A single evaluation, however careful, is a story you tell yourself. Two evaluations that contradict each other are the beginning of knowing something.

---

## 1 · An LLM judge measures whatever you show it

The methodology was imported from two prior projects where it worked (κ = 0.94, κ = 0.95). Here it failed four separate ways, and the failures were more instructive than the successes had been.

**It had substantial agreement and could not detect failure.** Twenty-two drafts, blind-labelled. **κ = 0.615** — "substantial" by textbook convention. The confusion matrix showed why that number was worthless: the judge's `UNGROUNDED` column was **empty**. It had never once used the harshest verdict, and caught **0 of 4** drafts a human called clearly broken. κ rewards agreement on the easy majority; only the marginals expose a collapsed label space.

**Its score moved opposite to quality.** Across four drafter versions the deterministic checks improved monotonically — date errors 3→0, language errors 7→0 — while groundedness *fell*, 0.682 → 0.587.

**A 0.31 swing came from the evidence pack alone.** The cause: the judge was handed an eleven-field extraction *summary* and told it was "the record". Every faithful citation of the source document — the case number, the court, the contract date — scored as an invention. Showing it the actual document moved **the same drafts** from 0.587 to 0.896. Fourteen `invented_fact` complaints fell to two, one of which was the judge flagging **our own mandatory review stamp** as a hallucination.

**It rated four empty strings as GROUNDED** — and we can price that exactly. Its best score of the project, **0.938**, came on a batch where 4 of 24 drafts were `""`. An empty draft makes no false claims, so it is perfectly grounded. With every draft real and all six deterministic checks clean, the same judge scored **0.792**. **Removing 17% empty output cost 0.146 of groundedness: the metric was paying a premium for silence.**

| judge sees | drafts | groundedness |
|---|---|---|
| an 11-field summary | good | 0.587 |
| an 11-field summary | better | 0.625 ↓ |
| **the source document** | *identical* | **0.750** |
| + full batch | identical | 0.833 |
| + stamp isn't an invention | identical | 0.896 |
| + a batch with **4 empty drafts** | worse | **0.938** ↑ |
| + every draft real, all checks clean | **best** | **0.792** ↓ |

**The judge's highest score came on its worst batch and its honest score on its best one.**

*And yet* — once fed properly, it found a real 10× money error (`2.100,68 €` written out as *"duzentos e dez euros"* = 210,68 €) that our own `amount_present` check had passed, because the digits were right and only the words were wrong. That became check number six. **The judge is not useless. It is an instrument with a calibration problem, and an uncalibrated instrument reporting three significant figures is worse than no instrument at all.**

---

## 2 · In perception, the deterministic reader is the dangerous one

Everywhere else in this system, determinism is the safe floor: rules do exactly what they say and nothing more. The perception layer inverts it, and the inversion is worth internalising.

Forty documents rendered as pages and degraded to fax quality (profiles calibrated by sweeping until OCR *began* losing facts — the first attempt was too gentle to measure anything):

| reader | accuracy | abstains | **silently corrupts** | s/page |
|---|---|---|---|---|
| tesseract (offline, free) | 0.255 | 60.2% | **14.3%** | 0.3 |
| Qwen2.5-VL 7B (offline, local) | **0.929** | 6.6% | **0.4%** | 34.6 |

**A 36× reduction in silent corruption, for 115× the latency.** What OCR did to the money and the dates:

| field | OCR read | truth |
|---|---|---|
| contract value | `121.57` | `121577.23` |
| contract value | `641.49` | `651498.72` |
| claim amount | `647.69` | `141452.69` |
| claim amount | `165435.45` | `185435.45` |
| response deadline | **`0`** days | `30` days |
| event date | `2036-04-23` | `2026-04-23` |

Not one is malformed. Every one parses, validates, and becomes an obligation. **A deadline of zero days. A contract value off by three orders of magnitude.** The reason is one sentence long: **OCR never says "I can't read this."** It guesses, fluently, in the right format. The local vision model behaves like the local text model — it abstains rather than invent — and that is what the 34 seconds buy.

**A second reader is an alarm.** Running both and treating disagreement as doubt flagged **63 of 63** silent corruptions, with zero cases where both readers agreed on the same wrong value.

*Honest counterpart:* the same signal does **not** calibrate the VLM's own confidence. Disagreement means *OCR* is wrong, not the VLM — AUC 0.626 once the tautological "both abstained" cell is excluded from an inflated 0.867, and a hardcoded 0.9 still wins on ECE because the VLM sits on a 93% base rate. One signal, two jobs, only one of which it can do. The flattering number was the easy one to publish.

---

## 3 · The third jurisdiction audits the architecture

Two jurisdictions cannot falsify a design; they can only agree with it. The Spanish pack — the third — found three latent bugs in a week-old engine that 34 passing tests had never touched:

**The engine could not express Spain's rule.** Suspension was only consulted on *continuous* counts. Portugal suspends a continuous count (CPC 138.º) and counts business days without suspension (CPA 87.º), so the design had encoded an accidental assumption: *these two properties never co-occur*. Spain needs **días hábiles AND agosto inhábil** at once (LEC 130.2).

**The deadline expired in the wrong timezone.** `23:59 Europe/Lisbon` printed on a **Madrid** court deadline. Spain is CET, Portugal WET — an hour wrong on a legal filing. Two packs sharing a timezone had hidden a hardcode.

**The trace hid the rule that moved the date.** August shifts a Spanish procedural deadline by a *month*, and the explanation said only "skipping weekends and holidays". An unexplained month is not an audit trail.

Also: **Portuguese and Spanish share two month names.** *Abril* and *agosto* are identical, so every Portuguese citação dated in April or August was classified Spanish. Month-based language detection cannot separate these languages; the disambiguation lives in the other ten.

The pack's own reason to exist is the **August divergence** — same event, same ten days, one country: **9 Sep** (LEC, procedural), **11 Aug** (LPAC, administrative), **7 Aug** (CC, naturales). Three regimes, opposite treatment of the same month, expressed as data rather than code.

---

## 4 · What a calendar app gets wrong about a deadline

An alert measured in calendar days lies about urgency, and the system already knows better — it used the real rule to compute the deadline in the first place.

| | calendar says | the law counts |
|---|---|---|
| PT · 18 days across *férias judiciais* | 18 | **9** |
| ES · six weeks spanning August (LEC) | 42 | **9** |
| ES · **the same six weeks** (LPAC) | 42 | **30** |

Identical dates. A calendar app shows "42 days left" for both Spanish cases. One of them gives you nine working days.

---

## 5 · Confidence: measured where it can be, admitted where it can't

Tier agreement is a free conformity signal — tier-2 is deterministic and offline, so it can always second-opinion whichever tier ran. For the **local** model it works: **AUC 0.996** versus **0.5 for a hardcoded constant**, enabling *400 of 408 fields auto-accepted at 99.8% precision with 8 routed to a human*.

For the **cloud** tier the honest answer is **unmeasurable**. One error in 440 fields is nothing to discriminate against. A confidence signal cannot be validated against errors that do not occur. That is not a good result; it is an *absent* one, and the difference matters.

The signal also **independently rediscovered a known weakness**: `creditor | tiers disagree → 0.167`, reproducing the English party-attribution failure found by hand in a completely different phase, by a completely different mechanism. Two methods, one conclusion, no coordination.

---

## 6 · Sovereignty is a claim you can run

Fourteen phases called this system "sovereign" on the strength of an architectural argument. That is worth nothing to a bank. So the appliance is not trusted, it is **tested, from inside, at runtime**:

```
on the host:      api.groq.com → real response HTTP/1.1 404   ✗ NOT SOVEREIGN
inside the box:   api.groq.com → Network is unreachable        ✓ SOVEREIGN
```

Same code, same command, opposite verdicts — which is the only reason to believe either of them. The bare IPs (`8.8.8.8`, `1.1.1.1`) fail with *Network is unreachable* rather than a DNS error: a routing block, not a resolver policy.

**The verifier's own first run was wrong**, and instructively so: it called a proxied sandbox leaky because a TCP connect *succeeded* — to a deny-proxy that then refused the request. **A route is not egress.** Data leaves at the application layer, so the verdict is taken there.

---

## 7 · The document is written by your adversary

The single most under-appreciated fact in legal AI: **a served notice is attacker-authored input.** The counterparty writes the thing your system reads.

**Prompt injection cannot move a deadline** — not because we detect it (we do, and report it), but structurally: the document supplies *inputs*, and the deadline is computed by deterministic code from those inputs. An injected corpus document produces an **identical due date**. Detection is the shallow defence; the structural one carries the weight, because a pattern list is always incomplete.

**But the same fact enabled a denial of service.** The engine counts day by day. `prazo de 1000000000 dias` cost **six minutes of CPU per document** — an attack that consists of typing a big number. Now refused in 0.0000s: no deadline in these jurisdictions is a decade long, so an implausible period is a misread number or a hostile document, and it routes to a human.

The hardening pass found two more before a line of it was written: an **empty document crashed the extractor**, and `verify_chain()` **raised on an empty ledger** — a fresh system could not answer *"is my chain intact?"*, and the app carried a workaround for it rather than a fix.

---

## 8 · Prompt specification is engineering

Cloud extraction climbed **v1 0.83 → v2 0.94 → v3 1.00**, and not one gain came from luck or from a bigger model. Every v1 miss was a **specification bug of mine**:

- `obligation_type` defined as the document's *topic* rather than the debtor's *action* — 8 of 8 administrative notices mislabelled;
- `creditor` conflated with the court;
- `legal_basis` ambiguous between the clause that creates the obligation and the statute that governs its period.

Each was found by dumping the model's disagreements and **reading them**. The local model's weaknesses were localised the same way — and it exposed a contradiction I had written into my own schema (`amount_eur: not fees/taxa`, while the CPA gold answer *is* the taxa). The 32B ignored the contradiction and matched gold; the 7B obeyed it literally and abstained. **A smaller model is a stricter reader of your specification, which makes it a better proofreader of your thinking.**

---

## 9 · The mistakes, and what caught each one

| the mistake | whose | what caught it |
|---|---|---|
| A scorer edit dropped the default `return`, scoring every field 0.00 | mine | the numbers were absurd |
| Sampled only English documents, nearly published a wrong conclusion about scan damage | mine | the sample was alphabetical — noticed by re-reading the code |
| Shipped a stale `agents.py` and **silently reverted a fix** the user had made | mine | **blind human labelling**, three phases later |
| Degradation profiles too gentle to measure anything (clean 0.887 → fax 0.868) | mine | sweeping the parameters instead of trusting them |
| Sovereignty verifier: TCP connect to a deny-proxy read as egress | mine | running it against a real proxied network |
| Scorecard pinned a groundedness from a **6-document** run | mine | comparing it to the number I remembered |
| A test that failed on its own docstring containing the word "webhook" | mine | it went red |
| Miscounted Spanish *días hábiles*; guessed Easter's cost; off-by-one on a decade | mine | hand-walking the calendar, twice |
| Judge evidence pack starved of the source document | mine | the score falling as quality rose |
| `EUR None` in a prompt → the model wrote "no amount is due" | mine | the judge, once it could see |

Ten entries. Every one is mine, and every one was caught by an instrument rather than by care. That is not humility for its own sake — it is the argument for the architecture. **The system is built out of things that check each other, because nothing in it, including the person who built it, can be trusted to be right the first time.**

---

## What this system would need before it touched a real matter

Stated plainly, because a limitations section that reads like marketing is a lie:

- **The corpus is synthetic.** Realistic templates, rendered and degraded — not photographs of genuine filings.
- **The jurisdiction packs are a source-cited engineering implementation, not legal advice.** They document their exclusions (municipal holidays, *dilação*, the ≥6-month CPC exception, art. 139.º grace days, autonomous Spanish calendars). A qualified lawyer must review every encoded rule.
- **The statute timeline is a fixture.** Real articles, real reform dates, simplified texts. Production needs a verified DRE/BOE/EUR-Lex feed. *The mechanism is the contribution; the corpus is a fixture.*
- **No κ describes the current judge.** The 0.615 was measured against the pre-fix harness and is retained as evidence of failure, not as validation. A post-fix κ needs a fresh blind-labelling round.
- **n = 40 documents, n = 24 drafts, n = 22 labels.** Directional, not definitive.
- **Tier-2 scores 1.00 because it is anchored to the corpus templates** — a ceiling, not a claim that regex beats language models on real documents.

---

## The shape of the thing

**The LLM proposes; the engine computes.** Anything with legal consequence — deadline arithmetic, obligation state, the audit trail — is deterministic, tested, source-cited code. Courts do not accept *"the model estimated."*

**Sovereign by default, resilient by architecture.** The dangerous parts never depended on connectivity, so an outage is a quality dial rather than a failure — and it is logged as an auditable event, because DORA does not ask whether you use AI, it asks what happened when it failed.

**And every number here is an output, not a claim.** The scorecard regenerates each one from committed evidence on every commit, and CI fails when one drifts. A claim nothing re-checks has already started rotting — which is, in the end, the only thing this project really discovered.

---

*Hugo Correia — Data Scientist · ML & AI Engineer, Lisbon*
*[Live demo](https://mandate-sovereign-obligation-os.streamlit.app/) · [Code](https://github.com/hugocorreia123/mandate-the-sovereign-obligation-os) · [Threat model](THREAT_MODEL.md)*
