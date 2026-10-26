"""Demo organization: people, teams and roles.

The notes only contain first names ("Raj"). The roster maps a name to a team, an email
and a login role. Names the roster does not know stay visible as written; they are never
silently matched to someone else.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    email: str
    team: str
    role: str  # "manager" or "employee"


TEAMS = ["Platform", "Product", "Quality", "Finance"]

PEOPLE: list[Person] = [
    Person("u_vishal", "Vishal", "vishal@decisionos.demo", "Leadership", "manager"),
    Person("u_raj", "Raj", "raj@decisionos.demo", "Platform", "employee"),
    Person("u_ravi", "Ravi", "ravi@decisionos.demo", "Platform", "employee"),
    Person("u_asha", "Asha", "asha@decisionos.demo", "Product", "employee"),
    Person("u_priya", "Priya", "priya@decisionos.demo", "Quality", "employee"),
    Person("u_meera", "Meera", "meera@decisionos.demo", "Quality", "employee"),
    Person("u_kavya", "Kavya", "kavya@decisionos.demo", "Finance", "employee"),
]

BY_EMAIL = {p.email: p for p in PEOPLE}
MANAGERS = [p for p in PEOPLE if p.role == "manager"]

# Team names that may appear in notes as the owner ("the finance team").
TEAM_ALIASES = {"platform": "Platform", "product": "Product", "quality": "Quality", "qa": "Quality", "finance": "Finance"}


def find_person(name: str | None) -> Person | None:
    if not name:
        return None
    key = name.strip().lower()
    matches = [p for p in PEOPLE if p.name.lower() == key or p.name.lower() == key.split()[0]]
    return matches[0] if len(matches) == 1 else None


def team_for(owner: str | None) -> str | None:
    p = find_person(owner)
    if p:
        return p.team
    if owner:
        low = owner.lower()
        for alias, team in TEAM_ALIASES.items():
            if alias in low:
                return team
    return None
