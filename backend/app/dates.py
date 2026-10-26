"""Turn deadline wording into a date the scheduler can use, without hiding uncertainty.

status:
  exact               the notes give a specific date ("Oct 27", "2026-10-27", "tomorrow", "next Friday")
  needs_confirmation  a likely date exists but the wording does not pin it ("Friday", "the 20th")
  after_dependency    "once Raj finishes": no date of its own, it follows its dependency
  unknown             no usable date ("UNKNOWN", "soon", "next week", "EOD")
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass

WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
MONTHS = {n.lower(): i for i, n in enumerate(calendar.month_name) if n}
MONTHS.update({n.lower(): i for i, n in enumerate(calendar.month_abbr) if n})
MONTHS["sept"] = 9
_WD = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))


@dataclass
class Deadline:
    date: dt.date | None
    status: str
    note: str


def _safe(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def fmt(d: dt.date) -> str:
    return d.strftime("%a %d %b").replace(" 0", " ")


def normalize(raw: str | None, meeting_date: dt.date) -> Deadline:
    if raw is None or raw.strip() == "" or raw.strip().upper() == "UNKNOWN":
        return Deadline(None, "unknown", "Not stated in the notes.")
    text = raw.lower().strip()
    text = re.sub(r"\(.*?\)", " ", text)  # drop model annotations like "(relative - needs confirmation)"
    text = re.sub(r"\b(by|on|before|until|due|no later than|end of day on)\b", " ", text)
    text = re.sub(r"\b(eod|cob|end of day|close of business|morning|evening|afternoon)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.-")

    if re.search(r"\b(after|once|when|following)\b", text):
        return Deadline(None, "after_dependency", "Starts after its dependency; no date of its own.")

    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if m:
        d = _safe(int(m[1]), int(m[2]), int(m[3]))
        return Deadline(d, "exact", "Date stated in the notes.") if d else Deadline(None, "unknown", f"'{raw}' is not a real date.")

    m = re.search(r"\b(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", text) or \
        re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _MON + r")\.?(?:,?\s+(\d{4}))?\b", text)
    if m:
        if m.group(1).isdigit():
            day, mon = int(m.group(1)), MONTHS[m.group(2)]
        else:
            mon, day = MONTHS[m.group(1)], int(m.group(2))
        year = int(m.group(3)) if m.group(3) else meeting_date.year
        d = _safe(year, mon, day)
        if d and not m.group(3) and (meeting_date - d).days > 60:
            d = _safe(year + 1, mon, day)  # "Jan 5" said in late December
        return Deadline(d, "exact", "Date stated in the notes.") if d else Deadline(None, "unknown", f"'{raw}' is not a real date.")

    if re.search(r"\btoday\b|\btonight\b", text):
        return Deadline(meeting_date, "exact", "'today' = the meeting date.")
    if re.search(r"\bday after tomorrow\b", text):
        return Deadline(meeting_date + dt.timedelta(days=2), "exact", "Two days after the meeting.")
    if re.search(r"\btomorrow\b", text):
        return Deadline(meeting_date + dt.timedelta(days=1), "exact", "'tomorrow' = the day after the meeting.")

    m = re.search(r"\bnext\s+(" + _WD + r")\b", text)
    if m:
        target = WEEKDAYS[m.group(1)]
        d = meeting_date + dt.timedelta(days=(target - meeting_date.weekday()) % 7 or 7)
        return Deadline(d, "exact", "'next <day>' = the first such day after the meeting.")

    m = re.search(r"\b(?:this\s+|coming\s+)?(" + _WD + r")\b", text)
    if m:
        target = WEEKDAYS[m.group(1)]
        d = meeting_date + dt.timedelta(days=(target - meeting_date.weekday()) % 7)
        return Deadline(d, "needs_confirmation", f"'{raw}' most likely means {fmt(d)}; the week is not stated.")

    m = re.search(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b", text)
    if m:
        day = int(m.group(1))
        y, mo = meeting_date.year, meeting_date.month
        for _ in range(13):
            d = _safe(y, mo, day)
            if d and d >= meeting_date:
                return Deadline(d, "needs_confirmation", f"'{raw}' most likely means {fmt(d)}; the month is not stated.")
            mo += 1
            if mo > 12:
                y, mo = y + 1, 1
        return Deadline(None, "unknown", f"'{raw}' is not a real date.")

    return Deadline(None, "unknown", f"'{raw}' is not a specific date.")
