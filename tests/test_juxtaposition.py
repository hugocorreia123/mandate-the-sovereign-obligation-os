"""The date-juxtaposition check — found by blind human labelling.

Three of 22 drafts glued the computed deadline onto the SERVICE date
("citação de 9 de outubro de 2026 (2026-11-09)"), which reads as
though the document was served on the deadline. The LLM critic passed
all three. A mechanical property deserves a mechanical check.
"""

from datetime import date

from pipeline import _date_juxtaposition_ok as ok


def test_flags_deadline_glued_to_the_event_date_pt():
    bad = ("toma conhecimento da notificação de 18 de setembro de "
           "2026 (2026-10-12), nos termos do artigo 121.º")
    assert ok(bad, date(2026, 9, 18), date(2026, 10, 12)) is False


def test_flags_it_for_a_citacao_too():
    bad = ("Reconhecemos a notificação/citação de 9 de outubro de "
           "2026 (2026-11-09), nos termos do artigo 569.º")
    assert ok(bad, date(2026, 10, 9), date(2026, 11, 9)) is False


def test_accepts_a_correct_draft_that_states_both_dates_properly():
    good = ("toma ciência da citação notificada em 8 de maio de 2026 "
            "(2026-05-08). O prazo de 10 dias finda no dia 18 de maio "
            "de 2026 (2026-05-18).")
    assert ok(good, date(2026, 5, 8), date(2026, 5, 18)) is True


def test_no_substring_collision_between_8_and_18_de_maio():
    """'8 de maio de 2026' must not match inside '18 de maio de 2026'
    — a plain substring check confuses the service date with the
    deadline and fails a correct draft."""
    good = "o prazo finda no dia 18 de maio de 2026 (2026-05-18)."
    assert ok(good, date(2026, 5, 8), date(2026, 5, 18)) is True


def test_accepts_english_draft_with_dates_apart():
    good = ("Findings dated 07 April 2026. The applicable deadline "
            "for observations is (2026-04-28), 15 days from receipt.")
    assert ok(good, date(2026, 4, 7), date(2026, 4, 28)) is True


def test_flags_english_juxtaposition():
    bad = "Notice dated 07 April 2026 (2026-04-28) is acknowledged."
    assert ok(bad, date(2026, 4, 7), date(2026, 4, 28)) is False


def test_iso_event_date_next_to_iso_due_date_is_flagged():
    bad = "notification of 2026-07-16 (2026-07-30) refers."
    assert ok(bad, date(2026, 7, 16), date(2026, 7, 30)) is False
