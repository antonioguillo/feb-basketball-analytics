"""Identificadores y presentación de nombres de jugador.

Las tablas de ClickHouse no tienen un id de jugador: la FEB solo publica el
nombre en el acta. El identificador de la API se deriva del nombre, así que
esta función es la definición canónica del slug y tiene que ser la misma en
todo lo que genere o resuelva URLs de jugador.
"""
import re
import unicodedata


def _ascii(text: str) -> str:
    return (unicodedata.normalize('NFKD', text)
            .encode('ascii', 'ignore')
            .decode('ascii'))


def player_slug(raw_name: str) -> str:
    """'ORTEGA IBAÑEZ, ALEJANDRO' -> 'ortega-ibanez-alejandro'."""
    slug = re.sub(r'[^a-z0-9]+', '-', _ascii(raw_name or '').lower()).strip('-')
    return slug


def display_name(raw_name: str) -> str:
    """'ORTEGA IBAÑEZ, ALEJANDRO' -> 'Alejandro Ortega Ibañez'.

    El acta escribe 'APELLIDOS, NOMBRE' en mayúsculas. Se pasa a capital
    inicial y se da la vuelta, sin añadir acentos que la fuente no trae.
    """
    name = (raw_name or '').strip()
    if not name:
        return ''
    if ',' in name:
        surname, given = (part.strip() for part in name.split(',', 1))
        return f'{given.title()} {surname.title()}'
    return name.title()
