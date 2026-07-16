"""Phase 13 — statutes have a timeline.

The mistake: ask "what does CPC art. 138.º say?", get today's text, and
if the event predates the last amendment, that text is the wrong law —
fluently, correctly cited, and false. This store makes the undated
question unaskable.
"""

from datetime import date

import pytest

from engine import compute_deadline
from pack_eu import EU
from pack_pt import PT
from statute import (NotInForce, StatuteStore, StatuteVersion,
                     UnknownArticle, default_store)


@pytest.fixture()
def s():
    return default_store()


# ------------------------------------------------ the temporal query
def test_the_same_article_returns_different_law_at_different_dates(s):
    """The whole point, in one assertion."""
    modern = s.get("CPC", "138.º", as_of=date(2026, 5, 10))
    assert "138" in modern.citation
    assert modern.valid_from == date(2013, 9, 1)
    # and in 2012 the SAME RULE lived somewhere else entirely
    old = s.get("CPC", "144.º", as_of=date(2012, 5, 10))
    assert old.valid_to == date(2013, 8, 31)
    assert "1961" in old.amended_by


def test_asking_about_a_date_before_enactment_is_refused(s):
    """Not "here's the current text" — refused. Answering would state
    a law that had not been enacted."""
    with pytest.raises(NotInForce) as e:
        s.get("CPC", "138.º", as_of=date(2012, 5, 10))
    assert "did not exist" in str(e.value)
    assert "2013-09-01" in str(e.value)


def test_asking_about_a_repealed_article_is_refused(s):
    with pytest.raises(NotInForce) as e:
        s.get("CPC", "144.º", as_of=date(2026, 1, 1))
    assert "repealed" in str(e.value)


def test_unknown_articles_raise_rather_than_guess(s):
    with pytest.raises(UnknownArticle):
        s.get("CPC", "999.º", as_of=date(2026, 1, 1))


def test_as_of_is_mandatory_and_keyword_only(s):
    """There is deliberately no way to ask for 'the text' without
    saying when — an undated question about a statute is a wrong
    answer waiting to happen."""
    with pytest.raises(TypeError):
        s.get("CPC", "138.º", date(2026, 1, 1))     # positional
    with pytest.raises(TypeError):
        s.get("CPC", "138.º")                        # omitted


def test_boundaries_are_inclusive_on_both_ends(s):
    """The last day of the old law and the first day of the new one."""
    old = s.get("CPC", "144.º", as_of=date(2013, 8, 31))
    assert old.article == "144.º"
    new = s.get("CPC", "138.º", as_of=date(2013, 9, 1))
    assert new.article == "138.º"


def test_an_unamended_statute_resolves_at_any_date_since_1971(s):
    """The control case: a store with a timeline must handle 'never
    changed' as naturally as 'changed twice'."""
    for when in (date(1971, 7, 1), date(1999, 1, 1), date(2026, 7, 1)):
        v = s.get("Reg. 1182/71", "3(4)", as_of=when)
        assert v.valid_to is None
    with pytest.raises(NotInForce):
        s.get("Reg. 1182/71", "3(4)", as_of=date(1971, 6, 30))


def test_history_is_ordered_and_complete(s):
    h = s.history("CPC", "144.º")
    assert len(h) == 1
    assert h[0].valid_from < h[0].valid_to


def test_amended_between_detects_a_reform_inside_a_window(s):
    hits = s.amended_between("CPC", "138.º", date(2013, 8, 1),
                             date(2013, 10, 1))
    assert len(hits) == 1
    assert hits[0].valid_from == date(2013, 9, 1)
    assert s.amended_between("CPC", "138.º", date(2020, 1, 1),
                             date(2020, 12, 31)) == []


def test_in_force_on_is_honest_about_its_window():
    v = StatuteVersion(code="X", article="1", jurisdiction="PT",
                       text="…", valid_from=date(2020, 1, 1),
                       valid_to=date(2020, 12, 31))
    assert v.in_force_on(date(2020, 1, 1)) is True
    assert v.in_force_on(date(2020, 12, 31)) is True
    assert v.in_force_on(date(2019, 12, 31)) is False
    assert v.in_force_on(date(2021, 1, 1)) is False


# --------------------------------------------- engine integration
def test_the_engine_cites_the_law_in_force_on_the_event_date(s):
    r = compute_deadline(PT, "cpc_processual", date(2026, 3, 23), 10,
                         store=s)
    law = [x for x in r.steps if "Law in force" in x]
    assert law and "138.º" in law[0]
    assert "Lei n.º 41/2013" in law[0]


def test_the_engine_refuses_to_cite_a_law_that_did_not_exist_yet(s):
    """A 2012 citação must not be told it is governed by an article
    enacted in 2013."""
    r = compute_deadline(PT, "cpc_processual", date(2012, 5, 10), 10,
                         store=s)
    bad = [x for x in r.steps if "LAW NOT RESOLVED" in x]
    assert bad and "did not exist" in bad[0]
    # the deadline itself still computes — the engine does not fail
    # closed on a citation problem
    assert r.due_date > date(2012, 5, 10)


def test_a_deadline_straddling_a_reform_is_flagged_for_a_human(s):
    """Every case pending on 1 Sep 2013 had a deadline that started
    under one Civil Procedure Code and ended under another. Nothing
    catches that. This does."""
    r = compute_deadline(PT, "cpc_processual", date(2013, 8, 25), 10,
                         store=s)
    warn = [x for x in r.steps if x.startswith("WARNING")]
    assert warn
    assert "AMENDED on 2013-09-01" in warn[0]
    assert "straddles a reform" in warn[0]
    assert "a human must confirm" in warn[0]


def test_no_straddle_warning_when_the_law_was_stable(s):
    r = compute_deadline(EU, "eu_1182_days", date(2026, 1, 12), 10,
                         store=s)
    assert not [x for x in r.steps if x.startswith("WARNING")]
    assert [x for x in r.steps if "Law in force" in x]


def test_the_engine_works_without_a_store_at_all(s):
    """Temporal citation is an enhancement, not a dependency: the
    deterministic core must still run with no statute corpus."""
    a = compute_deadline(PT, "cpc_processual", date(2026, 3, 23), 10)
    b = compute_deadline(PT, "cpc_processual", date(2026, 3, 23), 10,
                         store=s)
    assert a.due_date == b.due_date         # the date never changes
    assert len(b.steps) > len(a.steps)      # only the explanation grows
