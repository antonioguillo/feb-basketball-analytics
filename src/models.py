import re
import unicodedata
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


def group_slug(group_name: str) -> str:
    """Nombre de grupo del selector web -> identificador apto para una ruta S3.

    'Liga Regular "E-A"'  -> 'E-A'
    'Liga Regular Unico'  -> 'unico'
    """
    quoted = re.search(r'"([^"]+)"', group_name)
    raw = quoted.group(1) if quoted else group_name.replace('Liga Regular', '')
    # Los nombres traen acentos ('Unico'); se normalizan para que la ruta S3
    # quede en ASCII y sea estable entre sistemas.
    ascii_raw = (unicodedata.normalize('NFKD', raw.strip())
                 .encode('ascii', 'ignore').decode('ascii'))
    slug = re.sub(r'[^A-Za-z0-9]+', '-', ascii_raw).strip('-')
    return slug or 'ungrouped'