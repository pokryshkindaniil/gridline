"""Curated, deterministic identity aliases.

Each entry says: "when SOURCE spells it VARIANT, that is the canonical entity CANONICAL". They are applied only when
the (source, normalised variant) pair matches exactly, so an alias can never leak onto another source or another
spelling. Anything not listed here is NEVER merged automatically; likely duplicates only show up in
`gridline identity-report` for a human to decide (and, if confirmed, to add to this file).

Adding an entry is the only way two differently-spelled records become one entity.
"""

from __future__ import annotations

from dataclasses import dataclass

GTWC = "gt_world_challenge"
WEC = "fia_wec"
F1 = "formula1"


@dataclass(frozen=True)
class DriverAlias:
    first_name: str  # canonical
    last_name: str
    variant: str  # exact source spelling, "First Last"
    sources: tuple[str, ...]
    reason: str

    @property
    def canonical(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True)
class NameAlias:  # teams / manufacturers
    canonical: str
    variant: str
    sources: tuple[str, ...]
    reason: str


DRIVER_ALIASES: tuple[DriverAlias, ...] = (
    DriverAlias("Daniel", "Juncadella", "Dani Juncadella", (GTWC,),
                "Short form used by GTWC; FIA WEC publishes 'Daniel Juncadella' for the same driver."),
    DriverAlias("Nicklas", "Nielsen", "Niclkas Nielsen", (GTWC,),
                "Typo in one GTWC entry list (same car #51, same team, as 'Nicklas Nielsen' at other rounds)."),
    DriverAlias("Jef", "Machiels", "Jeff Machiels", (GTWC,),
                "GTWC spells the same AF Corse #52 driver both ways across rounds; the driver's own spelling is 'Jef'."),
    DriverAlias("Marco", "Sørensen", "Marco Sorensen", (GTWC,),
                "GTWC transliterates the Danish ø as 'o'; FIA WEC publishes 'Marco Sørensen' for the same driver."),
    DriverAlias("Prince Jefri", "Ibrahim", "H.H.Prince Jefri Ibrahim", (GTWC,),
                "GTWC prints the honorific 'H.H.' fused to the name; FIA WEC publishes 'Prince Jefri Ibrahim' for the same driver."),
    DriverAlias("Jonny", "Adam", "Jonathan Adam", (GTWC,),
                "Long form used by GTWC; FIA WEC publishes 'Jonny Adam' for the same driver."),
)

TEAM_ALIASES: dict[str, tuple[NameAlias, ...]] = {  # keyed by series slug: team identity is per series
    "gt-world-challenge-europe": (
        NameAlias("GetSpeed Team Bartone Bros", "GetSpeed Team BartoneBros", (GTWC,),
                  "Spelled without the space in the Paul Ricard entry list only."),
    ),
}

MANUFACTURER_ALIASES: tuple[NameAlias, ...] = ()
