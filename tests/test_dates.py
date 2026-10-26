import datetime as dt

from app.dates import normalize

MON = dt.date(2026, 10, 26)


def test_exact_dates():
    assert normalize("Oct 27", MON).date == dt.date(2026, 10, 27)
    assert normalize("27 October", MON).status == "exact"
    assert normalize("2026-11-02", MON).date == dt.date(2026, 11, 2)
    assert normalize("tomorrow", MON).date == dt.date(2026, 10, 27)
    assert normalize("next Friday", MON).date == dt.date(2026, 10, 30)


def test_relative_dates_need_confirmation():
    r = normalize("Friday (relative - needs confirmation)", MON)
    assert r.date == dt.date(2026, 10, 30) and r.status == "needs_confirmation"
    assert normalize("the 20th", MON).date == dt.date(2026, 11, 20)


def test_unknown_and_dependency():
    assert normalize("UNKNOWN", MON).status == "unknown"
    assert normalize("next week", MON).status == "unknown"
    assert normalize("soon", MON).date is None
    assert normalize("After API complete", MON).status == "after_dependency"
    assert normalize("30 Feb", MON).date is None


def test_year_rollover():
    assert normalize("Jan 5", dt.date(2026, 12, 28)).date == dt.date(2027, 1, 5)
