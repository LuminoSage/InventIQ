"""The buying catalogue: the twelve pre-buy options for the Dec 2026 to Feb 2027 season.

Each option is one market (a destination, or a flight route) for one stay window. The economics are
per unit (a room-night or a seat):

* ``hard_cost``     price paid upfront for a hard pre-buy unit, sold or not
* ``allot_cost``    price paid to the supplier only when an allotment unit is sold
* ``allot_fee``     non-refundable holding fee per allotment unit held (None: no allotment offered)
* ``allot_cap``     the most allotment units the supplier will hold
* ``sell_price``    expected selling price to agents
* ``salvage``       what an unsold hard unit recovers through distressed channels (about 15%)
* ``supply_cap``    hard units the connected suppliers can still sell us (0: nothing left)

The figures are synthetic, shaped like a large B2B travel distributor's books.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

TODAY = date(2026, 11, 21)  # the planning date the demo runs on
SEASON = "Dec 2026 to Feb 2027"


@dataclass(frozen=True)
class Event:
    """A demand bump: centred on a day each year, with a width in days and a relative height."""

    name: str
    month: int
    day: int
    width: float
    height: float
    by_year: dict[int, tuple[int, int]] = field(default_factory=dict)  # moving festivals

    def centre(self, year: int) -> date:
        m, d = self.by_year.get(year, (self.month, self.day))
        return date(year, m, d)


DIWALI = {2021: (11, 4), 2022: (10, 24), 2023: (11, 12), 2024: (11, 1), 2025: (10, 21), 2026: (11, 8), 2027: (10, 29)}
CNY = {2021: (2, 12), 2022: (2, 1), 2023: (1, 22), 2024: (2, 10), 2025: (1, 29), 2026: (2, 17), 2027: (2, 6)}


@dataclass(frozen=True)
class Option:
    id: str
    name: str
    product: str
    kind: str  # "hotel" or "flight"
    region: str  # "india" or "international"
    cluster: str  # markets that move together (shared travellers or routes)
    start: date
    nights: int
    peak: float  # expected demand for this window, in units
    noise: float  # log-scale volatility of demand around its expected level
    growth: float  # yearly demand growth
    base: float  # off-season level as a share of peak
    pace_days: float  # booking curve: share on the books at lead L is exp(-L / pace_days)
    hard_cost: float
    sell_price: float
    allot_cost: float | None
    allot_cap: int
    salvage: float
    supply_cap: int
    suppliers: int
    events: tuple[Event, ...]
    image: str | None = None
    image_alt: str = ""
    held: int = 0  # units already held from earlier buys (re-pricing checks these)

    @property
    def unit(self) -> str:
        return "seats" if self.kind == "flight" else "room-nights"

    @property
    def allot_fee(self) -> float:
        return 0.0 if self.allot_cost is None else round(0.03 * self.allot_cost, 2)

    @property
    def dates(self) -> str:
        from datetime import timedelta

        end = self.start + timedelta(days=self.nights)
        if self.start.month == end.month:
            return f"{self.start.day} – {end.day} {end.strftime('%b')}"
        return f"{self.start.day} {self.start.strftime('%b')} – {end.day} {end.strftime('%b')}"

    @property
    def lead_days(self) -> int:
        return (self.start - TODAY).days


E = Event
OPTIONS: tuple[Option, ...] = (
    Option(
        "goa",
        "Goa · New Year week",
        "4-star beach hotels",
        "hotel",
        "india",
        "goa",
        date(2026, 12, 28),
        4,
        560,
        0.17,
        0.12,
        0.22,
        38,
        5800,
        8400,
        6300,
        280,
        900,
        900,
        9,
        (E("New Year", 12, 31, 4, 1.0), E("Christmas", 12, 25, 3, 0.45), E("Diwali", 11, 1, 4, 0.30, DIWALI)),
        "photo-f67088468-500.jpg",
        "Palolem beach in south Goa",
    ),
    Option(
        "dubai",
        "Dubai · Shopping Festival",
        "4-star city hotels",
        "hotel",
        "international",
        "gulf",
        date(2027, 1, 8),
        10,
        900,
        0.16,
        0.10,
        0.30,
        62,
        7200,
        9600,
        7700,
        300,
        1100,
        1400,
        14,
        (E("Shopping Festival", 1, 10, 14, 1.0), E("New Year", 12, 31, 4, 0.4), E("Diwali", 11, 1, 4, 0.2, DIWALI)),
        "photo-f77469743-500.jpg",
        "Dubai Marina towers at night",
    ),
    Option(
        "udaipur",
        "Udaipur · Wedding season",
        "5-star palace hotels",
        "hotel",
        "india",
        "rajasthan",
        date(2027, 2, 5),
        4,
        180,
        0.22,
        0.09,
        0.25,
        70,
        18500,
        24500,
        None,
        0,
        2800,
        260,
        6,
        (
            E("Wedding dates", 2, 7, 6, 1.0),
            E("Wedding dates", 12, 8, 8, 0.8),
            E("Wedding dates", 11, 25, 7, 0.7),
            E("Diwali", 11, 1, 4, 0.4, DIWALI),
        ),
        "photo-f32266775-500.jpg",
        "Lake Pichola in Udaipur at sunset",
    ),
    Option(
        "manali",
        "Manali · Christmas week",
        "3-star hotels",
        "hotel",
        "india",
        "himalaya",
        date(2026, 12, 23),
        4,
        420,
        0.24,
        0.15,
        0.20,
        30,
        2600,
        3900,
        2900,
        200,
        400,
        700,
        11,
        (E("Christmas", 12, 25, 4, 1.0), E("New Year", 12, 31, 3, 0.6), E("Summer", 5, 28, 22, 0.9)),
        "photo-f49215790-500.jpg",
        "Snow on the slopes of Solang valley near Manali",
    ),
    Option(
        "bali",
        "Bali · New Year",
        "4-star resorts",
        "hotel",
        "international",
        "beach-asia",
        date(2026, 12, 29),
        4,
        380,
        0.19,
        0.14,
        0.25,
        55,
        6900,
        9200,
        7400,
        150,
        1000,
        600,
        10,
        (E("New Year", 12, 31, 4, 1.0), E("Christmas", 12, 25, 3, 0.4), E("Summer", 8, 1, 25, 0.6)),
        "photo-f147560727-500.jpg",
        "Rice terraces at Tegallalang in Bali",
    ),
    Option(
        "delgoi",
        "Delhi → Goa seats",
        "Group fare block",
        "flight",
        "india",
        "goa",
        date(2026, 12, 26),
        5,
        650,
        0.15,
        0.10,
        0.30,
        34,
        6400,
        8600,
        6900,
        200,
        1000,
        900,
        4,
        (E("New Year", 12, 29, 5, 1.0), E("Christmas", 12, 24, 3, 0.4), E("Diwali", 11, 1, 4, 0.35, DIWALI)),
    ),
    Option(
        "jaipur",
        "Jaipur · Republic Day weekend",
        "4-star heritage hotels",
        "hotel",
        "india",
        "rajasthan",
        date(2027, 1, 24),
        2,
        300,
        0.20,
        0.11,
        0.30,
        32,
        4200,
        5600,
        4600,
        120,
        600,
        500,
        12,
        (E("Republic Day", 1, 25, 2, 1.0), E("Diwali", 11, 1, 4, 0.5, DIWALI), E("Christmas", 12, 25, 4, 0.5)),
        "photo-f140798068-500.jpg",
        "The pink facade of Hawa Mahal in Jaipur",
    ),
    Option(
        "singapore",
        "Singapore · Chinese New Year",
        "4-star city hotels",
        "hotel",
        "international",
        "east-asia",
        date(2027, 2, 5),
        3,
        260,
        0.30,
        0.04,
        0.45,
        60,
        11800,
        13200,
        12600,
        100,
        1800,
        500,
        15,
        (
            E("Chinese New Year", 2, 6, 3, 1.0, CNY),
            E("Christmas", 12, 25, 4, 0.4),
            E("School holidays", 6, 10, 15, 0.4),
        ),
        "photo-f137548513-500.jpg",
        "Towers on Marina Bay in Singapore",
    ),
    Option(
        "munnar",
        "Munnar · Christmas week",
        "3-star hill resorts",
        "hotel",
        "india",
        "kerala",
        date(2026, 12, 22),
        4,
        240,
        0.21,
        0.10,
        0.25,
        30,
        3100,
        4300,
        3400,
        100,
        500,
        300,
        8,
        (E("Christmas", 12, 24, 4, 1.0), E("Onam", 9, 5, 5, 0.5), E("Summer", 5, 10, 18, 0.5)),
        "photo-f177457317-500.jpg",
        "Tea gardens on the hills of Munnar",
    ),
    Option(
        "srinagar",
        "Srinagar · Snow season",
        "Hotels and houseboats",
        "hotel",
        "india",
        "himalaya",
        date(2027, 1, 10),
        10,
        300,
        0.24,
        0.30,
        0.25,
        40,
        3800,
        5200,
        None,
        0,
        600,
        0,
        2,
        (E("Snow season", 1, 15, 12, 1.0), E("Summer", 6, 1, 30, 1.0)),
        "photo-f170616279-500.jpg",
        "Houseboats on Dal Lake in Srinagar",
    ),
    Option(
        "phuket",
        "Phuket · New Year",
        "4-star beach resorts",
        "hotel",
        "international",
        "beach-asia",
        date(2026, 12, 29),
        4,
        330,
        0.21,
        0.08,
        0.25,
        55,
        6100,
        8200,
        6600,
        150,
        900,
        500,
        9,
        (E("New Year", 12, 31, 4, 1.0), E("Christmas", 12, 25, 3, 0.6), E("Songkran", 4, 13, 3, 0.4)),
        "photo-f80273950-500.jpg",
        "Rocks and clear water at Patong beach in Phuket",
        held=320,
    ),
    Option(
        "bangkok",
        "Bangkok · Business weekdays",
        "3-star city hotels",
        "hotel",
        "international",
        "east-asia",
        date(2027, 1, 12),
        4,
        200,
        0.25,
        0.00,
        0.55,
        45,
        3400,
        3300,
        None,
        0,
        500,
        400,
        7,
        (E("Trade fairs", 1, 14, 10, 1.0), E("Songkran", 4, 13, 3, 0.4)),
        "photo-f137815734-500.jpg",
        "Wat Arun beside the Chao Phraya river in Bangkok",
        held=180,
    ),
)

BY_ID = {o.id: o for o in OPTIONS}

# Risk profiles: how much weight the plan puts on the worst 5% of futures (CVaR) against the mean.
RISK = {
    "cautious": {"label": "Cautious", "cvar_weight": 0.60},
    "balanced": {"label": "Balanced", "cvar_weight": 0.30},
    "bold": {"label": "Bold", "cvar_weight": 0.10},
}
CVAR_ALPHA = 0.05
