import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Competition:
    """Competición del selector de feb.es.

    id:       valor del parámetro `g=` en resultados.aspx
    name:     nombre tal y como lo publica la web
    year:     temporada por defecto (año de inicio)
    group_id: se conserva por compatibilidad; coincide con `id`
    category: 'senior' para las categorías absolutas, 'base' para las de
              formación y 'copa' para las eliminatorias sueltas. El histórico
              de scouting solo interesa en las absolutas.
    """
    id: int
    name: str
    year: str
    group_id: int
    category: str = 'senior'


# Catálogo completo del índice de competiciones de feb.es. Las claves son las
# mismas que usa la propia web en el parámetro `nm=`, para que un enlace de la
# web se traduzca directamente a un comando de este proyecto.
COMPETITIONS = {
    # --- categorías absolutas: las que tienen play-by-play y carta de tiros ---
    'primerafeb':   Competition(1,  'Primera FEB',   '2026', 1),
    'segundafeb':   Competition(2,  'Segunda FEB',   '2026', 2),
    'tercerafeb':   Competition(3,  'Tercera FEB',   '2026', 3),
    'lfendesa':     Competition(4,  'LF Endesa',     '2026', 4),
    'lf2':          Competition(9,  'L.F.-2',        '2026', 9),
    'lfchallenge':  Competition(67, 'LF Challenge',  '2026', 67),
    # --- eliminatorias y fases finales ---
    'copaespaa':        Competition(73, 'Copa España',                '2026', 73, 'copa'),
    'minicopalfendesa': Competition(55, 'Minicopa LF Endesa',         '2025', 55, 'copa'),
    'fasefinal1divisinfemenin': Competition(44, 'Fase Final 1ª División Femenina',
                                            '2025', 44, 'copa'),
    'ligau':            Competition(74, 'Liga U',                     '2025', 74, 'copa'),
    # --- categorías de formación ---
    'cespclubesjrmasc':   Competition(21, 'C. Esp. Clubes Junior Masc.',   '2025', 21, 'base'),
    'cespclubesjrfem':    Competition(22, 'C. Esp. Clubes Junior Fem.',    '2025', 22, 'base'),
    'cespclubescadmasc':  Competition(35, 'C. Esp. Clubes Cadete Masc.',   '2025', 35, 'base'),
    'cespclubescadfem':   Competition(36, 'C. Esp. Clubes Cadete Fem.',    '2025', 36, 'base'),
    'cespclubesinfmasc':  Competition(37, 'C. Esp. Clubes Infantil Masc.', '2025', 37, 'base'),
    'cespclubesinffem':   Competition(38, 'C. Esp. Clubes Infantil Fem.',  '2025', 38, 'base'),
    'cespclubesminimasc': Competition(71, 'C. Esp. Clubes Mini Masc.',     '2025', 71, 'base'),
    'cespclubesminifem':  Competition(72, 'C. Esp. Clubes Mini Fem.',      '2025', 72, 'base'),
    'cessaaminimas':      Competition(19, 'CE SSAA Mini Masc.',            '2025', 19, 'base'),
    'cessaaminifem':      Competition(20, 'CE SSAA Mini Fem.',             '2025', 20, 'base'),
    'cessaainfantilmas':  Competition(25, 'CE SSAA Infantil Masc.',        '2025', 25, 'base'),
    'cessaainfantilfem':  Competition(26, 'CE SSAA Infantil Fem.',         '2025', 26, 'base'),
    'cessaacadetemas':    Competition(40, 'CE SSAA Cadete Masc.',          '2025', 40, 'base'),
    'cessaacadetefem':    Competition(41, 'CE SSAA Cadete Fem.',           '2025', 41, 'base'),
}

# Las seis competiciones absolutas, que son las que alimentan el scouting.
# Comprobado sobre las temporadas 2021-2025: todas tienen play-by-play y carta
# de tiros en la API interna.
SENIOR_COMPETITIONS = [key for key, c in COMPETITIONS.items() if c.category == 'senior']


def competitions_by_category(category: str = 'senior') -> list:
    return [key for key, c in COMPETITIONS.items() if c.category == category]


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