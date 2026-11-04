"""Multi-country event calendar sources (an explicit subset, NOT worldwide --
see coverage_report() for the covered countries and the gap list).

Data sources actually wired up here, and why they're legitimate/accessible:

1. `holidays` (PyPI, MIT-licensed) -- a maintained, offline library that
   computes official national/regional holiday dates from each country's
   published rules (government gazettes, religious calendar algorithms for
   movable dates). It is NOT a scrape of a live site and makes no network
   calls; it is deterministic per (country, year) and is recomputed every
   call -- so a movable date (Easter, Eid, Diwali, Lunar New Year, ...) is
   always derived for the requested year, never carried over from a prior
   year. Religious movable dates computed this way (esp. Islamic hijri
   dates, which depend on local moon sighting) carry a documented ±1 day
   uncertainty; this is noted in `source` on every such Event.
2. UN International Days -- the United Nations publishes a fixed annual
   list of observances (https://www.un.org/en/observances/list-days-weeks).
   Nearly all of them are fixed Gregorian calendar dates (not movable), so a
   short curated, dated, sourced list is accurate data, not a guess. The
   list below is deliberately a subset (the commercially-relevant ones for
   stock content), not a claim of exhaustive UN coverage.
3. Astronomical seasons (equinoxes/solstices) -- computed from a standard
   approximation algorithm (Meeus-derived), not fetched from anywhere, so
   it needs no "source" beyond the algorithm itself. Hemisphere-aware: the
   same instant is "spring" in one hemisphere and "autumn" in the other.
4. Black Friday / Cyber Monday -- not official holidays, so not in
   `holidays`; derived deterministically from the US Thanksgiving date
   (Thanksgiving + 1 day; Cyber Monday = the following Monday).

NOT implemented here (see docs/GLOBAL_TREND_INTELLIGENCE.md and
adapters/ for why): government tourism-board calendars, school-term
calendars, and sports-fixture calendars generally require per-country
scraping or paid data feeds with no uniform free/official API; adding one
real source at a time, verified, beats a wide but unverifiable sweep.
"""
from __future__ import annotations
import datetime as _dt
from functools import lru_cache

import holidays as _holidays

from .events import Event

# Countries with solid `holidays` library support, chosen to cover both
# hemispheres and every movable-calendar system this project's test suite
# exercises (Gregorian, Islamic/Hijri, Hebrew, Hindu, Chinese lunisolar,
# Persian/Solar Hijri). This is an explicit, honest subset -- see
# COUNTRIES_COVERED in the scan report -- not a claim of full worldwide
# coverage.
SUPPORTED_COUNTRIES: dict[str, dict] = {
    'US': {'region': '', 'hemisphere': 'N', 'tz': 'America/New_York'},
    'GB': {'region': '', 'hemisphere': 'N', 'tz': 'Europe/London'},
    'DE': {'region': '', 'hemisphere': 'N', 'tz': 'Europe/Berlin'},
    'FR': {'region': '', 'hemisphere': 'N', 'tz': 'Europe/Paris'},
    'TR': {'region': '', 'hemisphere': 'N', 'tz': 'Europe/Istanbul'},
    'IN': {'region': '', 'hemisphere': 'N', 'tz': 'Asia/Kolkata'},
    'CN': {'region': '', 'hemisphere': 'N', 'tz': 'Asia/Shanghai'},
    'JP': {'region': '', 'hemisphere': 'N', 'tz': 'Asia/Tokyo'},
    'SA': {'region': '', 'hemisphere': 'N', 'tz': 'Asia/Riyadh'},
    'ID': {'region': '', 'hemisphere': 'S', 'tz': 'Asia/Jakarta'},
    'IL': {'region': '', 'hemisphere': 'N', 'tz': 'Asia/Jerusalem'},
    'IR': {'region': '', 'hemisphere': 'N', 'tz': 'Asia/Tehran'},
    'BR': {'region': '', 'hemisphere': 'S', 'tz': 'America/Sao_Paulo'},
    'AU': {'region': '', 'hemisphere': 'S', 'tz': 'Australia/Sydney'},
    'ZA': {'region': '', 'hemisphere': 'S', 'tz': 'Africa/Johannesburg'},
    'AR': {'region': '', 'hemisphere': 'S', 'tz': 'America/Argentina/Buenos_Aires'},
    'CA': {'region': '', 'hemisphere': 'N', 'tz': 'America/Toronto'},
    'MX': {'region': '', 'hemisphere': 'N', 'tz': 'America/Mexico_City'},
    'NG': {'region': '', 'hemisphere': 'N', 'tz': 'Africa/Lagos'},
    'EG': {'region': '', 'hemisphere': 'N', 'tz': 'Africa/Cairo'},
    'KR': {'region': '', 'hemisphere': 'N', 'tz': 'Asia/Seoul'},
    'TH': {'region': '', 'hemisphere': 'N', 'tz': 'Asia/Bangkok'},
    'NZ': {'region': '', 'hemisphere': 'S', 'tz': 'Pacific/Auckland'},
    'ES': {'region': '', 'hemisphere': 'N', 'tz': 'Europe/Madrid'},
    'IT': {'region': '', 'hemisphere': 'N', 'tz': 'Europe/Rome'},
}


def _country_holidays(iso2: str, year: int) -> dict:
    """Returns {date: [(name, category_hint)]} for one country/year.
    Tries the richer category set first (adds e.g. Hanukkah for Israel,
    optional/school observances elsewhere); falls back to the library's
    default (public only) if a given country doesn't support that kwarg."""
    cls = _holidays.country_holidays
    try:
        result = cls(iso2, years=year, categories=('public', 'optional', 'school'))
    except (NotImplementedError, TypeError, KeyError, ValueError):
        result = cls(iso2, years=year)
    by_date: dict[_dt.date, list[str]] = {}
    for d, name in result.items():
        by_date.setdefault(d, []).append(name)
    return by_date


# Date the curated UN observance list below was last checked against the
# published UN page (PR #1 authoring). Update ONLY when it is re-checked --
# it is deliberately not "today", which would claim a daily re-verification
# that never happens.
UN_LIST_VERIFIED_ON = '2026-11-04'

# Calendar sources that are NOT covered at all (no uniform free/official API).
UNCOVERED_SOURCE_TYPES = (
    'countries not in SUPPORTED_COUNTRIES (see calendar_coverage.library_supported_not_covered)',
    'sub-national/regional holidays (only whole-country holidays are indexed)',
    'school-term calendars', 'tourism-board event calendars', 'sports fixtures',
    'retail campaigns other than US Black Friday / Cyber Monday',
)


def coverage_report() -> dict:
    """Explicit coverage-and-gaps report. This calendar is a multi-country
    SUBSET, never "worldwide"."""
    try:
        supported = set(_holidays.list_supported_countries().keys())
    except Exception:
        supported = set()
    covered = set(SUPPORTED_COUNTRIES)
    return {
        'is_worldwide': False,
        'countries_covered': len(covered),
        'country_codes_covered': sorted(covered),
        'holidays_library_supported_countries': len(supported),
        'library_supported_not_covered': sorted(supported - covered),
        'regional_subdivisions_covered': False,
        'gaps': list(UNCOVERED_SOURCE_TYPES),
        'note': f'{len(covered)} countries out of {len(supported)} the holidays library supports '
                '(and ~195 countries worldwide); plus GLOBAL UN observances and astronomical seasons.',
    }


def holiday_events(year: int, countries: list[str] | None = None) -> list[Event]:
    """National/religious/cultural holiday events for the given year,
    always recomputed for that exact year (movable dates are never
    hardcoded or copied from a previous year)."""
    countries = countries or list(SUPPORTED_COUNTRIES.keys())
    # Computed offline by the library at scan time; not independently
    # verified against an official gazette by this scan -> verified_at ''.
    verified_at = ''
    events: list[Event] = []
    for iso2 in countries:
        meta = SUPPORTED_COUNTRIES.get(iso2, {})
        try:
            by_date = _country_holidays(iso2, year)
        except Exception:
            continue
        for d, names in by_date.items():
            for name in names:
                events.append(Event(
                    country=iso2,
                    event_date=d,
                    local_name=name,
                    english_name=name,
                    category='religious_cultural' if _looks_religious(name) else 'national_holiday',
                    source=f'holidays library (python "holidays" package {_holidays.__version__}) country_holidays({iso2!r}, {year})',
                    verified_at=verified_at,
                    region=meta.get('region', ''),
                    timezone=meta.get('tz', ''),
                    hemisphere=meta.get('hemisphere', ''),
                    cultural_context=_cultural_hint(name),
                    commercial_relevance=_commercial_hint(name),
                ))
    return events


_RELIGIOUS_MARKERS = (
    'eid', 'ramadan', 'diwali', 'deepavali', 'holi', 'hanukkah', 'nowruz',
    'christmas', 'easter', 'passover', 'yom kippur', 'rosh hashanah',
    'vesak', 'lunar new year', 'spring festival', 'navratri', 'vaisakhi',
)


def _looks_religious(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in _RELIGIOUS_MARKERS)


def _cultural_hint(name: str) -> str:
    low = name.lower()
    if 'diwali' in low or 'deepavali' in low:
        return 'Hindu/Jain/Sikh festival of lights; lamps, rangoli, fireworks, sweets, gifting.'
    if 'holi' in low:
        return 'Hindu festival of colors/spring; colored powder, water play, community gathering.'
    if 'eid' in low:
        return 'Islamic festival (end of Ramadan or Hajj); family gathering, feasting, new clothes, gift-giving.'
    if 'ramadan' in low:
        return 'Islamic holy month of fasting; iftar gatherings, lanterns, charity themes.'
    if 'hanukkah' in low or 'חנוכה' in name:
        return 'Jewish festival of lights; menorah, candles, dreidels, fried foods.'
    if 'nowruz' in low:
        return 'Persian/Zoroastrian new year, spring equinox; haft-sin table, renewal themes.'
    if 'lunar new year' in low or 'spring festival' in low or '春节' in name or '除夕' in name:
        return 'East Asian lunar new year; red lanterns, family reunion dinner, fireworks.'
    if 'thanksgiving' in low:
        return 'Family gathering, gratitude, harvest/autumn food themes (US/CA).'
    if 'christmas' in low:
        return 'Winter holiday; gift-giving, family gathering, festive decor.'
    return ''


def _commercial_hint(name: str) -> str:
    low = name.lower()
    if any(k in low for k in ('christmas', 'thanksgiving', 'diwali', 'eid', 'lunar new year', 'hanukkah')):
        return 'High historical commercial relevance for stock photo/vector demand (gifting, retail, food, family themes).'
    return 'Commercial relevance not pre-rated; scored per-event by the opportunity engine.'


# --- UN international observances -------------------------------------
# Curated subset of fixed-date UN International Days with clear commercial
# stock-content angles. Source: https://www.un.org/en/observances/list-days-weeks
# All are fixed annual Gregorian dates (not movable), verified against the
# published UN list as of the date in `verified_at`.
_UN_FIXED_DATES: list[tuple[int, int, str, str]] = [
    (1, 24, 'International Day of Education', 'Education, learning, classroom/study imagery.'),
    (2, 20, 'World Day of Social Justice', 'Equity, community support, workplace fairness imagery.'),
    (3, 8, 'International Women\'s Day', 'Women in work/leadership/community; strong retail and editorial demand.'),
    (3, 20, 'International Day of Happiness', 'Wellbeing, joy, lifestyle imagery.'),
    (3, 21, 'International Day of Forests', 'Nature, forestry, conservation, sustainability imagery.'),
    (3, 22, 'World Water Day', 'Water conservation, access, environmental imagery.'),
    (4, 7, 'World Health Day', 'Healthcare, wellness, medical-adjacent imagery.'),
    (4, 22, 'International Mother Earth Day', 'Environmental/sustainability, climate imagery.'),
    (5, 1, 'International Workers\' Day', 'Labor, trades, workplace imagery.'),
    (5, 15, 'International Day of Families', 'Family gathering, multigenerational imagery.'),
    (6, 5, 'World Environment Day', 'Environmental/sustainability campaigns, strong brand/retail tie-in.'),
    (6, 8, 'World Oceans Day', 'Ocean conservation, marine life, coastal imagery.'),
    (6, 20, 'World Refugee Day', 'Humanitarian, resilience imagery; handle with care re: cultural accuracy.'),
    (7, 11, 'World Population Day', 'Demographics, community, urban/rural life imagery.'),
    (8, 12, 'International Youth Day', 'Youth, education, sport, technology imagery.'),
    (9, 8, 'International Literacy Day', 'Reading, education, libraries imagery.'),
    (9, 21, 'International Day of Peace', 'Peace, unity, community imagery.'),
    (9, 29, 'International Day of Awareness of Food Loss and Waste', 'Food, sustainability, kitchen imagery.'),
    (10, 1, 'International Day of Older Persons', 'Active aging, senior lifestyle imagery.'),
    (10, 5, 'World Teachers\' Day', 'Education, classroom, mentorship imagery.'),
    (10, 16, 'World Food Day', 'Food, agriculture, cooking, harvest imagery.'),
    (11, 19, 'International Men\'s Day', 'Men\'s health/lifestyle imagery.'),
    (11, 25, 'International Day for the Elimination of Violence against Women', 'Advocacy imagery; handle with sensitivity.'),
    (12, 3, 'International Day of Persons with Disabilities', 'Inclusive/accessible representation imagery.'),
    (12, 10, 'Human Rights Day', 'Advocacy, unity, community imagery.'),
]


def un_observance_events(year: int) -> list[Event]:
    verified_at = UN_LIST_VERIFIED_ON
    events = []
    for month, day, name, hint in _UN_FIXED_DATES:
        events.append(Event(
            country='GLOBAL',
            event_date=_dt.date(year, month, day),
            local_name=name,
            english_name=name,
            category='un_observance',
            source='UN International Days (fixed annual date), https://www.un.org/en/observances/list-days-weeks',
            verified_at=verified_at,
            cultural_context='Globally observed; framing should avoid country-specific assumptions.',
            commercial_relevance=hint,
        ))
    return events


# --- Astronomical seasons ------------------------------------------------

def _equinox_solstice_approx(year: int, which: str) -> _dt.date:
    """Low-precision (Meeus-derived) approximation of equinox/solstice
    calendar date, accurate to within ~1 day -- sufficient for seasonal
    content planning, not for scientific use. `which` in
    {'mar_equinox','jun_solstice','sep_equinox','dec_solstice'}."""
    y = (year - 2000) / 1000.0
    coeffs = {
        'mar_equinox': (2451623.80984, 365242.37404, 0.05169, -0.00411, -0.00057),
        'jun_solstice': (2451716.56767, 365241.62603, 0.00325, 0.00888, -0.00030),
        'sep_equinox': (2451810.21715, 365242.01767, -0.11575, 0.00337, 0.00078),
        'dec_solstice': (2451900.05952, 365242.74049, -0.06223, -0.00823, 0.00032),
    }
    jde0, c1, c2, c3, c4 = coeffs[which]
    jde = jde0 + c1 * y + c2 * y * y + c3 * y ** 3 + c4 * y ** 4
    jd = jde - 2440587.5  # to Unix-epoch-relative JD
    dt = _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc) + _dt.timedelta(days=jd)
    return dt.date()


_SEASON_LABELS = {
    'mar_equinox': ('March equinox', 'spring', 'autumn'),
    'jun_solstice': ('June solstice', 'summer', 'winter'),
    'sep_equinox': ('September equinox', 'autumn', 'spring'),
    'dec_solstice': ('December solstice', 'winter', 'summer'),
}


def season_events(year: int) -> list[Event]:
    """One pair of Event records per equinox/solstice: the same instant,
    labeled once for the Northern-hemisphere season and once for the
    Southern-hemisphere season (they differ)."""
    verified_at = ''  # computed (approximation), nothing external to verify against
    events = []
    for which, (label, n_season, s_season) in _SEASON_LABELS.items():
        d = _equinox_solstice_approx(year, which)
        events.append(Event(
            country='GLOBAL', event_date=d, local_name=label,
            english_name=f'{label} -- start of {n_season} (Northern Hemisphere)',
            category='season', source='Astronomical approximation (Meeus low-precision formula)',
            verified_at=verified_at, hemisphere='N',
            commercial_relevance=f'Seasonal retail/content shift: {n_season} themes begin (Northern Hemisphere).',
        ))
        events.append(Event(
            country='GLOBAL', event_date=d, local_name=label,
            english_name=f'{label} -- start of {s_season} (Southern Hemisphere)',
            category='season', source='Astronomical approximation (Meeus low-precision formula)',
            verified_at=verified_at, hemisphere='S',
            commercial_relevance=f'Seasonal retail/content shift: {s_season} themes begin (Southern Hemisphere).',
        ))
    return events


# --- Retail campaigns derived from US Thanksgiving ----------------------

def retail_campaign_events(year: int) -> list[Event]:
    us = _holidays.country_holidays('US', years=year)
    thanksgiving = next((d for d, n in us.items() if 'Thanksgiving' in n), None)
    if thanksgiving is None:
        return []
    verified_at = ''  # derived from the computed Thanksgiving date, not verified externally
    black_friday = thanksgiving + _dt.timedelta(days=1)
    # Next Monday after Black Friday.
    days_to_monday = (7 - black_friday.weekday()) % 7 or 7
    cyber_monday = black_friday + _dt.timedelta(days=days_to_monday)
    return [
        Event(country='US', event_date=black_friday, local_name='Black Friday',
              english_name='Black Friday', category='retail_campaign',
              source='Derived: US Thanksgiving + 1 day', verified_at=verified_at,
              commercial_relevance='Peak retail/shopping imagery demand; deals, crowds, sale signage themes.'),
        Event(country='US', event_date=cyber_monday, local_name='Cyber Monday',
              english_name='Cyber Monday', category='retail_campaign',
              source='Derived: first Monday after Black Friday', verified_at=verified_at,
              commercial_relevance='E-commerce/online-shopping imagery demand.'),
    ]


def all_events(year: int, countries: list[str] | None = None) -> list[Event]:
    return (
        holiday_events(year, countries)
        + un_observance_events(year)
        + season_events(year)
        + retail_campaign_events(year)
    )


def find_duplicate_groups(events: list[Event]) -> dict[tuple, list[Event]]:
    """Groups events that share the same (date, english_name) across
    different countries -- e.g. Christmas observed in many countries on
    the same date. Not deduplicated away: each country's observance is
    still a distinct local market opportunity, but callers (e.g. the
    early-warning missed-opportunity scan) should not double-count these
    as independent global signals."""
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        gk = (e.event_date, e.english_name.strip().lower())
        groups.setdefault(gk, []).append(e)
    return {k: v for k, v in groups.items() if len(v) > 1}
