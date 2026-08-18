import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Competition:
    id: int
    name: str
    year: str
    group_id: int

COMPETITIONS = {
    'primerafeb': Competition(1, 'Primera FEB 2026/2027', '2026', 1),
    'segundafeb': Competition(2, 'Segunda FEB 2026/2027', '2026', 2),
    'tercerafeb': Competition(3, 'Tercera FEB 2025/2026', '2025', 3),
    'lf2': Competition(9, 'L.F.-2 2026/2027', '2026', 9),
    'copaespaa': Competition(73, 'Copa España 2026/2027', '2026', 73),
}


@dataclass
class EbaGroupSeason:
    """Grupo de la Tercera FEB / Liga EBA en una temporada.

    year:  año de inicio de la temporada (ej. 2025 -> 2025/2026)
    groups: nombre del subgrupo -> id del grupo en el selector web
    """
    year: str
    groups: dict = field(default_factory=dict)


# Grupo E de la Tercera FEB / Liga EBA - últimas 4 temporadas (2022/2023 a 2025/2026)
# Los ids corresponden al selector 'gruposDropDownList' de resultados.aspx
EBA_GROUP_E = {
    '2022': EbaGroupSeason('2022', {'E-A': '80019', 'E-B': '80020'}),
    '2023': EbaGroupSeason('2023', {'E-A': '83112', 'E-B': '83113'}),
    '2024': EbaGroupSeason('2024', {'E-A': '86387', 'E-B': '86388'}),
    '2025': EbaGroupSeason('2025', {'E-A': '88891', 'E-B': '88892'}),
}

def get_competition(name: str) -> Optional[Competition]:
    return COMPETITIONS.get(name.lower())

def parse_game_stats(page_html: str) -> dict:
    return {}