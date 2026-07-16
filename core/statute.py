"""Mandate — Phase 13: statutes have a timeline.

The mistake this module exists to prevent:

    "What does CPC art. 138.º say?"  ->  today's text.

If the event happened before the last amendment, today's text is the
WRONG LAW for that case — and nothing about the answer looks wrong. It
is fluent, correctly cited, and false. Legal RAG systems retrieve the
current text by default, which silently misstates the law for every
historical matter.

A statute is not a document. It is a SEQUENCE of texts, each in force
between two dates. The only meaningful question is:

    "What did CPC art. 138.º say ON THE DATE OF THE EVENT?"

So `get()` REQUIRES an as_of date. There is no way to ask this store
for "the current text" by accident — the temporal question is the only
question it answers, and asking about a date before the article existed
raises rather than falling back to a later version.

DATA CAVEAT: the version texts and in-force dates below are
ILLUSTRATIVE — they demonstrate the mechanism on real articles, but
they are a simplified engineering reconstruction, NOT an authoritative
consolidation. Real deployment requires a verified feed (DRE, BOE,
EUR-Lex) and a lawyer's review. The mechanism is the contribution; the
corpus is a fixture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


class NotInForce(Exception):
    """No version of this article was in force on that date."""


class UnknownArticle(Exception):
    """This store has never heard of that article."""


@dataclass(frozen=True)
class StatuteVersion:
    """One text of one article, in force between two dates."""
    code: str                       # "CPC", "LEC", "Reg. 1182/71"
    article: str                    # "138.º"
    jurisdiction: str               # PT | ES | EU
    text: str
    valid_from: date
    valid_to: Optional[date] = None   # None = still in force
    amended_by: str = ""              # the instrument that made it so
    note: str = ""

    def in_force_on(self, d: date) -> bool:
        if d < self.valid_from:
            return False
        return self.valid_to is None or d <= self.valid_to

    @property
    def citation(self) -> str:
        window = (f"in force from {self.valid_from.isoformat()}"
                  + (f" to {self.valid_to.isoformat()}"
                     if self.valid_to else " (current)"))
        return f"{self.code}, art. {self.article} — {window}"


@dataclass
class StatuteStore:
    versions: list[StatuteVersion] = field(default_factory=list)

    def add(self, v: StatuteVersion) -> "StatuteStore":
        self.versions.append(v)
        return self

    def history(self, code: str, article: str) -> list[StatuteVersion]:
        out = [v for v in self.versions
               if v.code == code and v.article == article]
        return sorted(out, key=lambda v: v.valid_from)

    def get(self, code: str, article: str, *,
            as_of: date) -> StatuteVersion:
        """The text in force ON as_of. The date is mandatory.

        Note the keyword-only `as_of`: there is deliberately no way to
        ask this store for "the text" without saying when. That is the
        entire point — an undated question about a statute is a
        question with a wrong answer waiting to happen.
        """
        hist = self.history(code, article)
        if not hist:
            raise UnknownArticle(f"{code} art. {article}")
        for v in hist:
            if v.in_force_on(as_of):
                return v
        first, last = hist[0], hist[-1]
        if as_of < first.valid_from:
            raise NotInForce(
                f"{code} art. {article} did not exist on "
                f"{as_of.isoformat()} — the earliest version entered "
                f"into force on {first.valid_from.isoformat()}"
                + (f" ({first.amended_by})" if first.amended_by else "")
                + ". Refusing to answer with a later text: that would "
                  "state a law that had not been enacted.")
        raise NotInForce(
            f"{code} art. {article} was repealed on "
            f"{last.valid_to.isoformat()}; nothing was in force on "
            f"{as_of.isoformat()}.")

    def amended_between(self, code: str, article: str,
                        start: date, end: date) -> list[StatuteVersion]:
        """Did this article change between two dates? Used to warn
        when an obligation's event and its deadline straddle a reform."""
        return [v for v in self.history(code, article)
                if start < v.valid_from <= end]


# =====================================================================
# ILLUSTRATIVE FIXTURE — see the DATA CAVEAT in the module docstring.
# Real articles, real reform dates, simplified texts.
# =====================================================================
def default_store() -> StatuteStore:
    s = StatuteStore()

    # ---- PT · CPC: the 2013 reform (Lei 41/2013) ------------------
    s.add(StatuteVersion(
        code="CPC", article="144.º", jurisdiction="PT",
        text=("[CPC 1961] Os prazos processuais são contínuos, "
              "suspendendo-se, no entanto, durante as férias "
              "judiciais, salvo se a sua duração for igual ou "
              "superior a seis meses ou se tratar de actos a "
              "praticar em processos que a lei considere urgentes."),
        valid_from=date(1961, 12, 28), valid_to=date(2013, 8, 31),
        amended_by="Código de Processo Civil de 1961",
        note="the counting rule lived at art. 144.º before the reform"))
    s.add(StatuteVersion(
        code="CPC", article="138.º", jurisdiction="PT",
        text=("O prazo processual, estabelecido por lei ou fixado por "
              "despacho do juiz, é contínuo, suspendendo-se, no "
              "entanto, durante as férias judiciais, salvo se a sua "
              "duração for igual ou superior a seis meses ou se "
              "tratar de actos a praticar em processos que a lei "
              "considere urgentes."),
        valid_from=date(2013, 9, 1), valid_to=None,
        amended_by="Lei n.º 41/2013, de 26 de junho (novo CPC)",
        note=("the same rule, renumbered 144.º -> 138.º. A system "
              "citing '138.º' for a 2012 event cites an article that "
              "did not yet exist.")))

    # ---- ES · LEC art. 130 ---------------------------------------
    s.add(StatuteVersion(
        code="LEC", article="130", jurisdiction="ES",
        text=("Las actuaciones judiciales habrán de practicarse en "
              "días y horas hábiles. Son días inhábiles a efectos "
              "procesales los sábados y domingos, los días 24 y 31 de "
              "diciembre, los días de fiesta nacional y los festivos "
              "a efectos laborales... Los días del mes de agosto "
              "serán inhábiles para todas las actuaciones judiciales, "
              "salvo las que se declaren urgentes."),
        valid_from=date(2001, 1, 8), valid_to=None,
        amended_by="Ley 1/2000, de Enjuiciamiento Civil"))

    # ---- EU · Reg. 1182/71: never amended (the control) -----------
    s.add(StatuteVersion(
        code="Reg. 1182/71", article="3(4)", jurisdiction="EU",
        text=("Where the last day of a period expressed otherwise than "
              "in hours is a public holiday, Sunday or Saturday, the "
              "period shall end with the expiry of the last hour of "
              "the following working day."),
        valid_from=date(1971, 7, 1), valid_to=None,
        amended_by="Regulation (EEC, Euratom) No 1182/71",
        note=("unamended for fifty years — the control case: a store "
              "with a timeline must handle 'never changed' as "
              "naturally as 'changed twice'")))
    return s
