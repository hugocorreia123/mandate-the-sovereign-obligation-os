"""Mandate — synthetic corpus + gold set generator (deterministic).

Generates realistic obligation-bearing documents in pt-PT and en, each
paired with ground-truth JSON (the gold set) for the tiered extraction
benchmark. Deterministic under a seed: same seed -> same corpus,
so the benchmark is reproducible forever.

Document types:
  pt  citacao_cpc       — judicial citação (contestation deadline,
                          CPC art. 569.º -> regime cpc_processual)
  pt  notificacao_cpa   — administrative notification (dias úteis,
                          CPA art. 87.º -> regime cpa_uteis)
  pt  renovacao_cc      — contract renewal notice (dias corridos,
                          CC art. 279.º -> regime cc_corridos)
  en  eu_reg_notice     — EU regulatory notice (working days,
                          Reg. 1182/71 -> eu_1182_working_days)
  en  eu_renewal        — renewal notice under EU-governed contract
                          (calendar days -> eu_1182_days)

Honest scope: documents are generated as TEXT (the post-parsing layer).
The extraction benchmark measures schema extraction quality; VLM
parsing of scanned PDFs is a later, separate phase.

Anti-shortcut design: every document embeds DISTRACTORS — a second
date (contract signature), a second amount (custas/fees) — so naive
"grab the first date/amount" extractors measurably fail.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

FIRST = ["Ana", "Bruno", "Carla", "Diogo", "Elsa", "Fábio", "Inês",
         "João", "Marta", "Nuno", "Rita", "Tiago"]
LAST = ["Almeida", "Barbosa", "Costa", "Dias", "Ferreira", "Gomes",
        "Lopes", "Martins", "Oliveira", "Pereira", "Santos", "Silva"]
COMPANIES_PT = ["Lusitânia Construções, Lda.", "TecnoVerde, S.A.",
                "Douro Logística, Lda.", "Atlântico Seguros, S.A.",
                "Minho Têxteis, Lda."]
COMPANIES_EN = ["Northwind Analytics Ltd.", "Baltic Freight GmbH",
                "Iberia Renewables S.A.", "Coral Data Systems B.V."]
COURTS = ["Tribunal Judicial da Comarca de Lisboa — Juízo Central Cível",
          "Tribunal Judicial da Comarca do Porto — Juízo Local Cível",
          "Tribunal Judicial da Comarca de Coimbra — Juízo Central Cível"]
AUTHORITIES_PT = ["Câmara Municipal de Lisboa",
                  "Autoridade Tributária e Aduaneira",
                  "Direção-Geral do Território"]
AUTHORITIES_EN = ["European Data Supervision Board",
                  "EU Market Conduct Authority",
                  "European Maritime Safety Agency"]

MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro",
             "dezembro"]


def _pt_money(x: float) -> str:
    """pt-PT format: 185.435,45 (dots thousands, comma decimals)."""
    return (f"{x:,.2f}".replace(",", "X").replace(".", ",")
            .replace("X", "."))


def _pt_date(d: date) -> str:
    return f"{d.day} de {MONTHS_PT[d.month - 1]} de {d.year}"


def _en_date(d: date) -> str:
    return d.strftime("%d %B %Y")


def _proc(rng) -> str:
    return (f"{rng.randint(100, 9999)}/{rng.randint(24, 26)}."
            f"{rng.randint(0, 9)}T8LSB")


@dataclass
class GoldDoc:
    doc_id: str
    language: str
    doc_type: str
    jurisdiction: str
    regime_id: str
    obligation_type: str
    event_date: str
    deadline_amount: int
    deadline_unit: str
    debtor: str
    creditor: str
    amount_eur: float | None
    legal_basis: str
    text: str


def _person(rng) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def gen_citacao_cpc(rng, i: int) -> GoldDoc:
    court = rng.choice(COURTS)
    debtor = rng.choice(COMPANIES_PT)
    creditor = _person(rng)
    ev = date(2026, rng.randint(1, 11), rng.randint(1, 28))
    signed = ev - timedelta(days=rng.randint(200, 900))
    prazo = rng.choice([10, 15, 30])
    main = round(rng.uniform(5_000, 250_000), 2)
    custas = round(rng.uniform(100, 900), 2)
    proc = _proc(rng)
    text = f"""{court}
Processo n.º {proc}

CITAÇÃO

Fica V. Ex.ª, {debtor}, na qualidade de Ré, citada para, no prazo de
{prazo} dias, contestar, querendo, a ação declarativa de condenação
que lhe move {creditor}, Autor nos presentes autos, na qual peticiona
o pagamento da quantia de € {_pt_money(main)}, acrescida de juros vencidos,
com fundamento no contrato de fornecimento celebrado em
{_pt_date(signed)}.

O prazo conta-se nos termos do artigo 569.º do Código de Processo
Civil, aplicando-se as regras de contagem do artigo 138.º do mesmo
diploma. A presente citação considera-se efetuada em {_pt_date(ev)}.

Custas de citação: € {_pt_money(custas)}.
A Secretaria Judicial"""
    return GoldDoc(f"pt_cit_{i:03d}", "pt", "citacao_cpc", "PT",
                   "cpc_processual", "respond", ev.isoformat(), prazo,
                   "days", debtor, creditor, main,
                   "CPC art. 569.º + art. 138.º", text)


def gen_notificacao_cpa(rng, i: int) -> GoldDoc:
    auth = rng.choice(AUTHORITIES_PT)
    debtor = rng.choice(COMPANIES_PT)
    ev = date(2026, rng.randint(1, 11), rng.randint(1, 28))
    prazo = rng.choice([10, 15, 20])
    fee = round(rng.uniform(250, 4_000), 2)
    ref = f"OF-{rng.randint(2024, 2026)}/{rng.randint(1000, 99999)}"
    text = f"""{auth}
Ofício n.º {ref}

NOTIFICAÇÃO PARA AUDIÊNCIA PRÉVIA

Nos termos e para os efeitos do disposto no artigo 121.º do Código do
Procedimento Administrativo, fica {debtor} notificada para, no prazo
de {prazo} dias úteis, dizer o que se lhe oferecer sobre o projeto de
decisão de indeferimento, podendo juntar documentos.

O prazo conta-se nos termos do artigo 87.º do CPA, iniciando-se no dia
seguinte ao da presente notificação, efetuada em {_pt_date(ev)}.

Taxa devida pelo procedimento: € {_pt_money(fee)}.
O Diretor de Serviços"""
    return GoldDoc(f"pt_cpa_{i:03d}", "pt", "notificacao_cpa", "PT",
                   "cpa_uteis", "respond", ev.isoformat(), prazo,
                   "days", debtor, auth, fee,
                   "CPA art. 121.º + art. 87.º", text)


def gen_renovacao_cc(rng, i: int) -> GoldDoc:
    a = rng.choice(COMPANIES_PT)
    b = _person(rng)
    ev = date(2026, rng.randint(1, 11), rng.randint(1, 28))
    signed = ev - timedelta(days=rng.randint(300, 1200))
    aviso = rng.choice([30, 60, 90])
    renda = round(rng.uniform(800, 6_000), 2)
    text = f"""CARTA DE COMUNICAÇÃO — OPOSIÇÃO À RENOVAÇÃO

Exmo(a). Senhor(a) {b},

Na qualidade de senhoria, vem a {a} comunicar, nos termos do contrato
de arrendamento celebrado em {_pt_date(signed)} e do disposto no
Código Civil, a intenção de não renovação do referido contrato.

Nos termos da cláusula quarta, a oposição à renovação deve ser
comunicada com a antecedência mínima de {aviso} dias relativamente ao
termo do contrato, contando-se o prazo em dias corridos nos termos do
artigo 279.º do Código Civil, a partir da presente comunicação,
rececionada em {_pt_date(ev)}.

Renda mensal em vigor: € {_pt_money(renda)}.
Com os melhores cumprimentos,
{a}"""
    return GoldDoc(f"pt_ren_{i:03d}", "pt", "renovacao_cc", "PT",
                   "cc_corridos", "notify", ev.isoformat(), aviso,
                   "days", a, b, renda, "CC art. 279.º", text)


def gen_eu_reg_notice(rng, i: int) -> GoldDoc:
    auth = rng.choice(AUTHORITIES_EN)
    debtor = rng.choice(COMPANIES_EN)
    ev = date(2026, rng.randint(1, 11), rng.randint(1, 28))
    filed = ev - timedelta(days=rng.randint(30, 200))
    prazo = rng.choice([10, 15, 20])
    fine = round(rng.uniform(10_000, 400_000), 2)
    ref = f"CASE-{rng.randint(2025, 2026)}-{rng.randint(100, 999)}"
    text = f"""{auth}
Reference: {ref}

NOTICE OF PRELIMINARY FINDINGS

Dear Sir or Madam,

Further to the proceedings opened on {_en_date(filed)}, {debtor} is
hereby invited to submit written observations on the preliminary
findings within {prazo} working days of receipt of this notice.

The period shall be calculated in accordance with Regulation (EEC,
Euratom) No 1182/71. This notice is deemed received on {_en_date(ev)}.

The preliminary findings envisage an administrative fine of up to
EUR {fine:,.2f}.

Head of Unit"""
    return GoldDoc(f"en_reg_{i:03d}", "en", "eu_reg_notice", "EU",
                   "eu_1182_working_days", "respond", ev.isoformat(),
                   prazo, "days", debtor, auth, fine,
                   "Reg. 1182/71", text)


def gen_eu_renewal(rng, i: int) -> GoldDoc:
    a = rng.choice(COMPANIES_EN)
    b = rng.choice(COMPANIES_EN)
    while b == a:
        b = rng.choice(COMPANIES_EN)
    ev = date(2026, rng.randint(1, 11), rng.randint(1, 28))
    signed = ev - timedelta(days=rng.randint(300, 1000))
    notice = rng.choice([30, 60, 90])
    val = round(rng.uniform(20_000, 900_000), 2)
    text = f"""NON-RENEWAL NOTICE

From: {a}
To: {b}

Pursuant to clause 11.2 of the Master Services Agreement executed on
{_en_date(signed)}, we hereby give notice of our intention not to
renew the Agreement.

Per clause 11.2, such notice must be delivered no fewer than {notice}
calendar days prior to the end of the current term, the period being
computed under Regulation (EEC, Euratom) No 1182/71 from the date of
receipt of this notice, being {_en_date(ev)}.

Current annual contract value: EUR {val:,.2f}.

Authorised signatory, {a}"""
    return GoldDoc(f"en_ren_{i:03d}", "en", "eu_renewal", "EU",
                   "eu_1182_days", "notify", ev.isoformat(), notice,
                   "days", a, b, val, "Reg. 1182/71", text)


GENERATORS = [gen_citacao_cpc, gen_notificacao_cpa, gen_renovacao_cc,
              gen_eu_reg_notice, gen_eu_renewal]


def generate_corpus(out_dir: str | Path, n_per_type: int = 8,
                    seed: int = 42) -> list[GoldDoc]:
    rng = random.Random(seed)
    out = Path(out_dir)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    gold: list[GoldDoc] = []
    for gen in GENERATORS:
        for i in range(n_per_type):
            gold.append(gen(rng, i))
    for g in gold:
        (out / "docs" / f"{g.doc_id}.txt").write_text(g.text)
    gold_json = [
        {k: v for k, v in g.__dict__.items() if k != "text"}
        for g in gold]
    (out / "gold.json").write_text(json.dumps(gold_json, indent=2,
                                              ensure_ascii=False))
    return gold


if __name__ == "__main__":
    docs = generate_corpus("data/corpus", n_per_type=8, seed=42)
    langs = {}
    for d in docs:
        langs[d.language] = langs.get(d.language, 0) + 1
    print(f"generated {len(docs)} docs -> data/corpus "
          f"(per language: {langs})")
