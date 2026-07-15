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


# ------------------------------------------- amounts in words (Ph. 9d)
from pipeline import _no_amount_in_words as words_ok  # noqa: E402


def test_flags_the_real_ten_fold_error_found_by_the_judge():
    """The actual draft: record said 2.100,68 EUR, the draft spelled
    'duzentos e dez euros e 68 cêntimos' (210,68) — off by 10x. The
    digits were right, so amount_present passed it."""
    bad = ("A taxa devida é de € 2.100,68 (duzentos e dez euros e 68 "
           "cêntimos), a regularizar no prazo.")
    assert words_ok(bad) is False


def test_flags_english_amounts_in_words():
    bad = "an administrative fine of EUR 175,195.66 (one hundred " \
          "seventy-five thousand euros) applies."
    assert words_ok(bad) is False


def test_accepts_digits_only():
    good = ("A quantia de € 185.435,45 será contestada no prazo de 10 "
            "dias. O prazo termina em 18 de maio de 2026 (2026-05-18).")
    assert words_ok(good) is True


def test_accepts_english_digits_only():
    good = ("The administrative fine of EUR 347,213.65 is referenced. "
            "The deadline is 30 July 2026 (2026-07-30).")
    assert words_ok(good) is True


def test_does_not_false_positive_on_periods_in_words():
    """'ten days' is a period, not money — must not trip the check."""
    good = "Baltic Freight GmbH will respond within ten days."
    assert words_ok(good) is True


def test_does_not_false_positive_on_prazo_de_dez_dias():
    good = ("O prazo de dez dias conta-se nos termos do artigo 138.º; "
            "a quantia de € 11.501,31 será contestada.")
    assert words_ok(good) is True
