import json
import math
import os
import re
import unicodedata
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import requests
import streamlit as st


st.set_page_config(
    page_title="Detector de Goles (+2.5 / -2.5)",
    page_icon="⚽",
    layout="centered",
)

API_BASE_URL = "https://v3.football.api-sports.io"
GOAL_API_BASE_URL = "https://api.goal-api.com/v1"
CACHE_PAISES_PATH = Path("equipos_paises.json")
UMBRAL_RACHA_POR_DEFECTO = 60.0
UMBRAL_POISSON_POR_DEFECTO = 58.0

PAISES_BASE_INICIALES = {
    "muranga": "Kenia",
    "murang'a": "Kenia",
    "muranga seal": "Kenia",
    "murang'a seal": "Kenia",
    "kcb": "Kenia",
    "gor mahia": "Kenia",
    "tusker": "Kenia",
    "afc leopards": "Kenia",
    "bandari": "Kenia",
    "kakamega homeboyz": "Kenia",
    "kenya police": "Kenia",
    "kariobangi sharks": "Kenia",
    "sofapaka": "Kenia",
    "ulinzi stars": "Kenia",
    "bidco united": "Kenia",
    "nairobi city stars": "Kenia",
    "post rangers": "Kenia",
    "shabana": "Kenia",
    "mathare united": "Kenia",
    "mara sugar": "Kenia",
    "kolkheti 1913": "Georgia",
    "bolnisi": "Georgia",
    "sioni bolnisi": "Georgia",
    "telavi": "Georgia",
    "samtredia": "Georgia",
    "merani martvili": "Georgia",
    "gareji": "Georgia",
    "fc gareji sagarejo": "Georgia",
    "dusheti": "Georgia",
    "odishi 1919": "Georgia",
    "shturmi": "Georgia",
    "gori": "Georgia",
    "walter ferretti": "Nicaragua",
    "sport sebaco": "Nicaragua",
    "muang loei": "Tailandia",
    "nong bua pitchaya": "Tailandia",
    "kasetsart": "Tailandia",
    "khonkaen utd": "Tailandia",
    "khon kaen united": "Tailandia",
    "nakhon ratchasima": "Tailandia",
    "nakhon ratchasima fc": "Tailandia",
    "songkhla": "Tailandia",
    "police tero": "Tailandia",
    "sukhothai": "Tailandia",
    "al nasr": "Egipto",
    "tersana": "Egipto",
    "svay rieng": "Camboya",
    "machida": "Japón",
    "sao paulo": "Brasil",
    "sao paulo fc": "Brasil",
    "remo": "Brasil",
    "kokand 1912": "Uzbekistán",
    "xorazm urganch": "Uzbekistán",
}

PAISES_OCR_MAPA = {
    "KENIA": "Kenia",
    "KENYA": "Kenia",
    "GEORGIA": "Georgia",
    "NICARAGUA": "Nicaragua",
    "TAILANDIA": "Tailandia",
    "THAILAND": "Tailandia",
    "EGIPTO": "Egipto",
    "EGYPT": "Egipto",
    "ESPANA": "España",
    "ESPAÑA": "España",
    "SPAIN": "España",
    "INGLATERRA": "Inglaterra",
    "ENGLAND": "Inglaterra",
    "FRANCIA": "Francia",
    "FRANCE": "Francia",
    "ALEMANIA": "Alemania",
    "GERMANY": "Alemania",
    "ITALIA": "Italia",
    "ITALY": "Italia",
    "PORTUGAL": "Portugal",
    "ARMENIA": "Armenia",
    "UCRANIA": "Ucrania",
    "UKRAINE": "Ucrania",
    "BRASIL": "Brasil",
    "BRAZIL": "Brasil",
    "ARGENTINA": "Argentina",
    "COLOMBIA": "Colombia",
    "MEXICO": "México",
    "MÉXICO": "México",
    "CHILE": "Chile",
    "PERU": "Perú",
    "PERÚ": "Perú",
    "TURQUIA": "Turquía",
    "TURQUÍA": "Turquía",
    "GRECIA": "Grecia",
    "POLONIA": "Polonia",
    "RUMANIA": "Rumanía",
    "BULGARIA": "Bulgaria",
    "SERBIA": "Serbia",
    "CROACIA": "Croacia",
    "NORUEGA": "Noruega",
    "SUECIA": "Suecia",
    "DINAMARCA": "Dinamarca",
    "FINLANDIA": "Finlandia",
    "JAPON": "Japón",
    "JAPÓN": "Japón",
    "JPN": "Japón",
    "COREA DEL SUR": "Corea del Sur",
    "MARRUECOS": "Marruecos",
    "SUDAFRICA": "Sudáfrica",
    "SUDÁFRICA": "Sudáfrica",
    "NIGERIA": "Nigeria",
    "GHANA": "Ghana",
    "TANZANIA": "Tanzania",
    "UGANDA": "Uganda",
    "ETIOPIA": "Etiopía",
    "ETIOPÍA": "Etiopía",
    "CAMBOYA": "Camboya",
    "CAMBODIA": "Camboya",
    "CAM": "Camboya",
    "UZBEKISTAN": "Uzbekistán",
    "UZBEKISTÁN": "Uzbekistán",
}

KNOWN_GOAL_TEAMS = {
    "walter ferretti": {
        "id": "cmrjf2lag9qkat507x53p82tx",
        "name": "Walter Ferretti",
        "country": "Nicaragua",
    },
    "ferretti": {
        "id": "cmrjf2lag9qkat507x53p82tx",
        "name": "Walter Ferretti",
        "country": "Nicaragua",
    },
    "sport sebaco": {
        "id": "cmrjezgrc8op7t507hqulwamp",
        "name": "Sport Sébaco",
        "country": "Nicaragua",
    },
    "sebaco": {
        "id": "cmrjezgrc8op7t507hqulwamp",
        "name": "Sport Sébaco",
        "country": "Nicaragua",
    },
}

ALIAS_EQUIPOS = {
    "marsella": "Marseille",
    "olympique marsella": "Marseille",
    "olympique de marsella": "Marseille",
    "psg": "Paris Saint Germain",
    "paris sg": "Paris Saint Germain",
    "bayern": "Bayern Munich",
    "bayern munich": "Bayern Munich",
    "inter": "Inter",
    "inter milan": "Inter",
    "ac milan": "AC Milan",
    "milan": "AC Milan",
    "atletico": "Atletico Madrid",
    "atletico madrid": "Atletico Madrid",
    "atletico de madrid": "Atletico Madrid",
    "athletic": "Athletic Club",
    "athletic bilbao": "Athletic Club",
    "betis": "Real Betis",
    "celta": "Celta Vigo",
    "celta de vigo": "Celta Vigo",
    "espanyol": "Espanyol",
    "espanol": "Espanyol",
    "sevilla": "Sevilla",
    "barcelona": "Barcelona",
    "fc barcelona": "Barcelona",
    "real madrid": "Real Madrid",
    "manchester utd": "Manchester United",
    "manchester united": "Manchester United",
    "manchester city": "Manchester City",
    "newcastle": "Newcastle",
    "tottenham": "Tottenham",
    "sporting": "Sporting CP",
    "sporting lisboa": "Sporting CP",
    "oporto": "FC Porto",
    "porto": "FC Porto",
    "benfica": "Benfica",
    "estrasburgo": "Strasbourg",
    "niza": "Nice",
    "lyon": "Lyon",
    "monaco": "Monaco",
    "lille": "Lille",
    "colonia": "FC Koln",
    "maguncia": "FSV Mainz 05",
    "friburgo": "SC Freiburg",
    "eintracht": "Eintracht Frankfurt",
    "dortmund": "Borussia Dortmund",
    "borussia dortmund": "Borussia Dortmund",
    "leverkusen": "Bayer Leverkusen",
    "napoles": "Napoli",
    "napoli": "Napoli",
    "juventus": "Juventus",
    "roma": "AS Roma",
    "lazio": "Lazio",
    "fiorentina": "Fiorentina",
}

PALABRAS_RUIDO = {
    "TIEMPO",
    "STREAM",
    "ANUNCIO",
    "CUOTAS",
    "H2H",
    "CLASIFICACION",
    "CLASIFICACIÓN",
    "ALINEACIONES",
    "ESTAD",
    "ESTADIS",
    "DIRECTO",
    "PREPARTIDO",
    "PROXIMO GOL",
    "PRÓXIMO GOL",
    "MAS DE/MENOS DE",
    "MÁS DE/MENOS DE",
    "MAS DE",
    "MÁS DE",
    "MENOS DE",
    "AMBOS EQUIPOS",
    "AMBOS",
    "FLASHSCORE",
    "PARTIDO",
    "RESUMEN",
    "ESTADISTICAS",
    "ESTADÍSTICAS",
    "BET>",
    "BET365",
    "SPORTIUM",
    "1XBET",
    "WINAMAX",
    "APUESTA EN",
    "DISPONIBLES",
    "JORNADA",
    "NUEVA VENTANA",
    "PREMIER LEAGUE",
    "FIRST LEAGUE",
    "SUPER LEAGUE",
    "ARMENIA",
    "UCRANIA",
    "KENIA",
    "BRASIL",
    "ALERT",
    "ESPANA",
    "ESPAÑA",
    "INGLATERRA",
    "FRANCIA",
    "ALEMANIA",
    "ITALIA",
    "PORTUGAL",
    "HANDICAP ASIATICO",
    "HANDICAP ASIÁTICO",
    "HACER UNA APUESTA",
    "CASA DE APUESTAS",
    "DOBLE OPORTUNID",
    "DOBLE OPORTUNIDAD",
    "RESULTADO EXACTO",
    "MAS SELECCIONES",
    "MÁS SELECCIONES",
    "1ER TIEMPO",
    "2O TIEMPO",
    "2º TIEMPO",
    "FUTBOL",
    "FÚTBOL",
    "SRF",
    "SOLO RESULTADO FINAL",
    "SÓLO RESULTADO FINAL",
    "RESULTADO FINAL",
    "SOLO PARA",
    "SÓLO PARA",
    "TMTM",
    "YOUTH FOOTBALL",
    "BLUE EAGLES",
    "ULTIMOS PARTIDOS",
    "ÚLTIMOS PARTIDOS",
    "GENERAL",
    "LOCAL",
    "VISITANTE",
}


def normalizar_texto(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _parsear_cuota_texto(valor: str | float | int | None) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = str(valor).strip().replace(",", ".")
    limpio = re.sub(r"[^0-9.]", "", limpio)
    if not limpio:
        return 0.0
    try:
        return float(limpio)
    except ValueError:
        return 0.0


def _clave_equipo_cache(nombre: str) -> str:
    norm = normalizar_texto(nombre)
    norm = re.sub(r"['’`]", "", norm)
    norm = re.sub(r"\([a-z]{2,4}\)", "", norm)
    norm = re.sub(r"^(?:fc|cf|cd|ud|rcd|ca|ac|as|sc|ss|us|fk|sk|afc)\s+", "", norm)
    norm = re.sub(r"\s+(?:fc|cf|sad|sc|fk|sk|afc)$", "", norm)
    return norm.strip()


def cargar_cache_paises() -> dict[str, str]:
    mapa = {_clave_equipo_cache(k): v for k, v in PAISES_BASE_INICIALES.items()}
    if CACHE_PAISES_PATH.exists():
        try:
            datos = json.loads(CACHE_PAISES_PATH.read_text(encoding="utf-8"))
            if isinstance(datos, dict):
                for k, v in datos.items():
                    clave = _clave_equipo_cache(str(k))
                    if clave and str(v).strip():
                        mapa[clave] = str(v).strip()
        except Exception:
            pass
    return mapa


def guardar_equipo_pais(nombre_equipo: str, pais: str) -> None:
    clave = _clave_equipo_cache(nombre_equipo)
    pais_limpio = (pais or "").strip()
    if not clave or not pais_limpio:
        return
    datos_actuales: dict[str, str] = {}
    if CACHE_PAISES_PATH.exists():
        try:
            leido = json.loads(CACHE_PAISES_PATH.read_text(encoding="utf-8"))
            if isinstance(leido, dict):
                datos_actuales = leido
        except Exception:
            datos_actuales = {}
    datos_actuales[clave] = pais_limpio
    try:
        CACHE_PAISES_PATH.write_text(
            json.dumps(datos_actuales, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        pass
    st.session_state["cache_paises_equipos"] = cargar_cache_paises()


def consultar_pais_equipo(nombre_equipo: str) -> str:
    clave = _clave_equipo_cache(nombre_equipo)
    if not clave:
        return ""
    mapa = st.session_state.get("cache_paises_equipos") or cargar_cache_paises()
    if clave in mapa:
        return mapa[clave]
    for k_guardada, v_pais in mapa.items():
        if len(clave) >= 4 and (clave in k_guardada or k_guardada in clave):
            return v_pais
    return ""


def detectar_pais_en_ocr(texto_ocr: str) -> str:
    if not texto_ocr:
        return ""
    texto_norm = normalizar_texto(texto_ocr).upper()
    for clave_pais, nombre_bonito in PAISES_OCR_MAPA.items():
        clave_norm = normalizar_texto(clave_pais).upper()
        if re.search(rf"\b{re.escape(clave_norm)}\b", texto_norm):
            return nombre_bonito
    return ""


def preparar_nombre_busqueda(nombre: str) -> str:
    clave = normalizar_texto(nombre)
    if clave in ALIAS_EQUIPOS:
        return ALIAS_EQUIPOS[clave]
    limpio = re.sub(r"^(?:fc|cf|cd|ud|rcd|ca|ac|as|sc|ss|us)\s+", "", clave)
    limpio = re.sub(r"\s+(?:fc|cf|sad)$", "", limpio)
    if limpio in ALIAS_EQUIPOS:
        return ALIAS_EQUIPOS[limpio]
    return nombre.strip()


def obtener_api_key(key_manual: str) -> str:
    if key_manual and key_manual.strip():
        return key_manual.strip()
    try:
        return st.secrets.get("API_FOOTBALL_KEY", "").strip()
    except Exception:
        return ""


def obtener_goal_key(key_manual: str = "") -> str:
    if key_manual and key_manual.strip():
        return key_manual.strip()
    if os.getenv("GOAL_KEY"):
        return os.getenv("GOAL_KEY", "").strip()
    try:
        return str(st.secrets.get("GOAL_KEY", "")).strip()
    except Exception:
        return ""


def evaluar_ev_cuota(prob_raw: float | None, cuota_winamax: float | None) -> dict:
    if not cuota_winamax or cuota_winamax <= 1.0 or not prob_raw or prob_raw <= 0.0:
        return {
            "tiene_cuota": False,
            "es_ev_positivo": False,
            "ev_pct": None,
            "cuota_winamax": cuota_winamax if cuota_winamax and cuota_winamax > 1.0 else None,
            "etiqueta": "SIN CUOTA",
        }
    ev_ratio = (float(prob_raw) * float(cuota_winamax)) - 1.0
    ev_pct = round(ev_ratio * 100.0, 1)
    es_pos = ev_ratio > 0.0
    return {
        "tiene_cuota": True,
        "es_ev_positivo": es_pos,
        "ev_pct": ev_pct,
        "cuota_winamax": round(float(cuota_winamax), 2),
        "etiqueta": "VALOR (+EV)" if es_pos else "SIN VALOR (-EV)",
    }


def _formatear_marcadores_top(items: list[dict], limite: int = 3) -> str:
    partes = []
    for item in (items or [])[:limite]:
        cj = item.get("cuota_justa")
        cj_txt = f" · cj {float(cj):.2f}" if cj else ""
        partes.append(f"`{item['marcador']}` ({item['prob']:.1f}%{cj_txt})")
    return " | ".join(partes)


@st.cache_data(ttl=3600, show_spinner=False)
def api_get(endpoint: str, params_items: tuple[tuple[str, str], ...], api_key: str) -> dict:
    headers = {"x-apisports-key": api_key}
    resp = requests.get(
        f"{API_BASE_URL}/{endpoint}",
        headers=headers,
        params=dict(params_items),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _fecha_partido(fixture_item: dict) -> str:
    return str(fixture_item.get("fixture", {}).get("date") or "")


def buscar_equipo_api(nombre: str, api_key: str) -> dict | None:
    consulta = preparar_nombre_busqueda(nombre)
    data = api_get("teams", (("search", consulta),), api_key)
    errores = data.get("errors")
    if errores:
        raise RuntimeError(str(errores))

    resultados = data.get("response", [])
    if not resultados and consulta != nombre.strip():
        data = api_get("teams", (("search", nombre.strip()),), api_key)
        errores = data.get("errors")
        if errores:
            raise RuntimeError(str(errores))
        resultados = data.get("response", [])

    if not resultados:
        return None

    objetivo = normalizar_texto(consulta)
    for item in resultados:
        team = item.get("team", {})
        if normalizar_texto(team.get("name", "")) == objetivo:
            return team

    for item in resultados:
        team = item.get("team", {})
        if not team.get("national", False):
            return team

    return resultados[0].get("team")


def obtener_promedios_10_api(team_id: int, api_key: str) -> dict | None:
    partidos: list[dict] = []
    for temporada in ("2026", "2025"):
        data = api_get(
            "fixtures",
            (("team", str(team_id)), ("season", temporada), ("status", "FT")),
            api_key,
        )
        errores = data.get("errors")
        if errores:
            raise RuntimeError(str(errores))
        lote = data.get("response", [])
        if lote:
            partidos.extend(lote)
        if len(partidos) >= 10:
            break

    if not partidos:
        return None

    partidos_ordenados = sorted(partidos, key=_fecha_partido, reverse=True)[:10]

    gf_total = 0.0
    gc_total = 0.0
    peso_total = 0.0
    validos = 0
    under25_count = 0

    for idx, f in enumerate(partidos_ordenados):
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        g_home = goals.get("home")
        g_away = goals.get("away")

        if g_home is None or g_away is None:
            continue

        total_goles = int(g_home) + int(g_away)
        if total_goles < 3:
            under25_count += 1

        peso = 0.92**idx
        if home_id == team_id:
            gf_c = min(int(g_home), 5)
            gc_c = min(int(g_away), 5)
            gf_total += gf_c * peso
            gc_total += gc_c * peso
            peso_total += peso
            validos += 1
        elif away_id == team_id:
            gf_c = min(int(g_away), 5)
            gc_c = min(int(g_home), 5)
            gf_total += gf_c * peso
            gc_total += gc_c * peso
            peso_total += peso
            validos += 1

    if validos == 0 or peso_total == 0:
        return None

    under_rate = round((under25_count / validos) * 100, 1)
    over_rate = round(100.0 - under_rate, 1)

    return {
        "partidos": validos,
        "gf_prom": round(gf_total / peso_total, 2),
        "gc_prom": round(gc_total / peso_total, 2),
        "under25_rate": under_rate,
        "over25_rate": over_rate,
    }


def obtener_h2h_api(team_local_id: int, team_vis_id: int, api_key: str) -> dict | None:
    data = api_get(
        "fixtures/headtohead",
        (("h2h", f"{team_local_id}-{team_vis_id}"), ("status", "FT")),
        api_key,
    )
    errores = data.get("errors")
    if errores:
        return None

    partidos = data.get("response", [])
    if not partidos:
        return None

    partidos_ordenados = sorted(partidos, key=_fecha_partido, reverse=True)[:6]

    total_goles = 0
    validos = 0
    for f in partidos_ordenados:
        goals = f.get("goals", {})
        g_home = goals.get("home")
        g_away = goals.get("away")
        if g_home is not None and g_away is not None:
            total_goles += min(int(g_home) + int(g_away), 6)
            validos += 1

    if validos == 0:
        return None

    return {
        "partidos": validos,
        "goles_prom": round(total_goles / validos, 2),
    }


@st.cache_data(ttl=86400, show_spinner=False)
def goal_search_teams_cached(query: str, country: str | None, goal_key: str) -> list[dict]:
    clean_query = query.strip()
    if not clean_query or not goal_key:
        return []

    headers = {"Authorization": f"Bearer {goal_key}"}
    candidatos_busqueda = [clean_query]
    sin_tilde = normalizar_texto(clean_query)
    if sin_tilde and sin_tilde != clean_query.lower():
        candidatos_busqueda.append(sin_tilde)

    items: list[dict] = []
    for termino in candidatos_busqueda:
        for limite in (20, 10):
            resp = requests.get(
                f"{GOAL_API_BASE_URL}/teams",
                headers=headers,
                params={"search": termino, "limit": limite},
                timeout=15,
            )
            if resp.status_code == 400:
                continue
            resp.raise_for_status()
            items = resp.json().get("data", [])
            if items:
                break
        if items:
            break

    if country and country.strip():
        c_norm = normalizar_texto(country)
        filtrados = [
            t
            for t in items
            if c_norm in normalizar_texto(str(t.get("country") or t.get("countryName") or ""))
        ]
        if filtrados:
            return filtrados

    return items


def goal_resolve_team(name: str, country: str | None, goal_key: str) -> dict | None:
    clave_norm = normalizar_texto(name)
    if clave_norm in KNOWN_GOAL_TEAMS:
        return KNOWN_GOAL_TEAMS[clave_norm]

    candidates = goal_search_teams_cached(name, country, goal_key)
    if not candidates and country:
        candidates = goal_search_teams_cached(name, None, goal_key)

    if not candidates:
        return None

    target_lower = clave_norm

    def score_candidate(team: dict) -> tuple:
        t_name = normalizar_texto(team.get("name") or "")
        is_youth_or_women = any(
            tag in t_name for tag in ["u20", "u19", "u17", "u23", "women", "w "]
        )
        exact_match = t_name == target_lower
        starts_match = t_name.startswith(target_lower)
        total_fixtures = (
            (team.get("_count", {}).get("homeFixtures") or 0)
            + (team.get("_count", {}).get("awayFixtures") or 0)
        )
        return (
            0 if exact_match else (1 if starts_match else 2),
            1 if is_youth_or_women else 0,
            -total_fixtures,
        )

    return sorted(candidates, key=score_candidate)[0]


@st.cache_data(ttl=3600, show_spinner=False)
def goal_fetch_team_results(team_id: str, goal_key: str, limit: int = 50) -> list[dict]:
    resp = requests.get(
        f"{GOAL_API_BASE_URL}/results",
        headers={"Authorization": f"Bearer {goal_key}"},
        params={"teamId": team_id, "limit": limit, "offset": 0},
        timeout=15,
    )
    resp.raise_for_status()
    payload = resp.json()

    matches = [
        m
        for m in payload.get("data", [])
        if m.get("matchStatus") == "FINISHED"
        and m.get("homeTeamFtScore") is not None
        and m.get("awayTeamFtScore") is not None
    ]
    matches.sort(
        key=lambda m: (m.get("matchDate", ""), m.get("matchTime", "")),
        reverse=True,
    )
    return matches


def goal_summarize_team_goals(
    matches: list[dict],
    team_id: str,
    last_n: int = 10,
    prefer_venue: str | None = None,
) -> dict:
    subset = matches[:last_n]
    if not subset:
        return {
            "count": 0,
            "gf_avg": 0.0,
            "ga_avg": 0.0,
            "total_avg": 0.0,
            "over25_rate": 0.0,
            "under25_rate": 0.0,
            "venue_used": False,
            "matches": [],
        }

    gf_w_sum = 0.0
    ga_w_sum = 0.0
    w_sum = 0.0

    venue_gf_sum = 0.0
    venue_ga_sum = 0.0
    venue_count = 0

    over25_count = 0
    rows = []

    for idx, m in enumerate(subset):
        hg = int(m["homeTeamFtScore"])
        ag = int(m["awayTeamFtScore"])
        is_home = m.get("homeTeamId") == team_id
        gf_real = hg if is_home else ag
        ga_real = ag if is_home else hg
        total_real = hg + ag

        if total_real >= 3:
            over25_count += 1

        gf_mod = min(gf_real, 5)
        ga_mod = min(ga_real, 5)

        peso = 0.90**idx
        gf_w_sum += gf_mod * peso
        ga_w_sum += ga_mod * peso
        w_sum += peso

        if (prefer_venue == "home" and is_home) or (prefer_venue == "away" and not is_home):
            venue_gf_sum += gf_mod
            venue_ga_sum += ga_mod
            venue_count += 1

        rows.append(
            {
                "Fecha": m.get("matchDate"),
                "Competición": m.get("leagueName"),
                "Cond.": "Local" if is_home else "Visit.",
                "Local": m.get("homeTeamName"),
                "Visitante": m.get("awayTeamName"),
                "Marcador": f"{hg} - {ag}",
                "GF": gf_real,
                "GC": ga_real,
                "Total": total_real,
            }
        )

    n = len(subset)
    gf_general = gf_w_sum / w_sum
    ga_general = ga_w_sum / w_sum

    venue_used = False
    if prefer_venue in ("home", "away") and venue_count >= 3:
        gf_venue = venue_gf_sum / venue_count
        ga_venue = venue_ga_sum / venue_count
        gf_final = (0.60 * gf_general) + (0.40 * gf_venue)
        ga_final = (0.60 * ga_general) + (0.40 * ga_venue)
        venue_used = True
    else:
        gf_final = gf_general
        ga_final = ga_general

    over_rate = round((over25_count / n) * 100, 1)
    under_rate = round(100.0 - over_rate, 1)

    return {
        "count": n,
        "gf_avg": gf_final,
        "ga_avg": ga_final,
        "total_avg": gf_final + ga_final,
        "over25_rate": over_rate,
        "under25_rate": under_rate,
        "venue_used": venue_used,
        "matches": rows,
    }


def poisson_pmf(k: int, lam: float) -> float:
    return (math.exp(-lam) * (lam**k)) / math.factorial(k)


def calculate_poisson_markets(
    lam_home: float,
    lam_away: float,
    max_goals: int = 6,
    winamax_over25: float | None = None,
    winamax_under25: float | None = None,
    winamax_draw: float | None = None,
) -> dict:
    prob_home = 0.0
    prob_draw = 0.0
    prob_away = 0.0
    prob_over_25 = 0.0

    rho = -0.07
    cell_probs: list[tuple[str, float, int]] = []
    raw_matrix: list[list[float]] = []
    total_mass = 0.0

    for h in range(max_goals + 1):
        row = []
        p_h = poisson_pmf(h, lam_home)
        for a in range(max_goals + 1):
            p_a = poisson_pmf(a, lam_away)
            tau = 1.0
            if h == 0 and a == 0:
                tau = 1.0 - (lam_home * lam_away * rho)
            elif h == 0 and a == 1:
                tau = 1.0 + (lam_home * rho)
            elif h == 1 and a == 0:
                tau = 1.0 + (lam_away * rho)
            elif h == 1 and a == 1:
                tau = 1.0 - rho

            p_cell = max(0.0, p_h * p_a * max(0.70, min(1.30, tau)))
            row.append(p_cell)
            total_mass += p_cell
        raw_matrix.append(row)

    matrix: list[list[float]] = []
    under_scores: list[tuple[str, float]] = []
    over_scores: list[tuple[str, float]] = []

    for h in range(max_goals + 1):
        norm_row = []
        for a in range(max_goals + 1):
            p_cell = raw_matrix[h][a] / total_mass if total_mass > 0 else raw_matrix[h][a]
            norm_row.append(p_cell)
            etiqueta = f"{h} - {a}"
            cell_probs.append((etiqueta, p_cell, h + a))

            if h > a:
                prob_home += p_cell
            elif h == a:
                prob_draw += p_cell
            else:
                prob_away += p_cell

            if (h + a) >= 3:
                prob_over_25 += p_cell
                over_scores.append((etiqueta, p_cell))
            else:
                under_scores.append((etiqueta, p_cell))
        matrix.append(norm_row)

    prob_under_25 = max(0.0, 1.0 - prob_over_25)

    def fair_odd(p: float) -> float | None:
        return round(1.0 / p, 2) if p > 0 else None

    def edge(p: float, odd: float | None) -> float | None:
        if not odd or odd <= 1.0:
            return None
        return round((p * odd) - 1.0, 4)

    top_scores_sorted = sorted(cell_probs, key=lambda x: x[1], reverse=True)[:3]
    top_exact_scores = [
        {
            "marcador": sc,
            "prob": round(pr * 100, 1),
            "cuota_justa": fair_odd(pr),
        }
        for sc, pr, _ in top_scores_sorted
    ]
    best_score, best_prob, _ = top_scores_sorted[0]

    under_scores_sorted = sorted(under_scores, key=lambda x: x[1], reverse=True)[:3]
    top_under_scores = [
        {
            "marcador": sc,
            "prob": round(pr * 100, 1),
            "cuota_justa": fair_odd(pr),
        }
        for sc, pr in under_scores_sorted
    ]
    best_under_score, best_under_prob = (
        under_scores_sorted[0] if under_scores_sorted else ("1 - 0", 0.0)
    )

    over_scores_sorted = sorted(over_scores, key=lambda x: x[1], reverse=True)[:3]
    top_over_scores = [
        {
            "marcador": sc,
            "prob": round(pr * 100, 1),
            "cuota_justa": fair_odd(pr),
        }
        for sc, pr in over_scores_sorted
    ]
    best_over_score, best_over_prob = (
        over_scores_sorted[0] if over_scores_sorted else ("2 - 1", 0.0)
    )

    return {
        "lam_home": round(lam_home, 3),
        "lam_away": round(lam_away, 3),
        "expected_total_goals": round(lam_home + lam_away, 3),
        "exact_score": best_score,
        "exact_score_prob": round(max(0.0, best_prob) * 100, 1),
        "exact_score_fair_odd": fair_odd(max(0.0, best_prob)),
        "top_exact_scores": top_exact_scores,
        "under_exact_score": best_under_score,
        "under_exact_score_prob": round(max(0.0, best_under_prob) * 100, 1),
        "under_exact_score_fair_odd": fair_odd(max(0.0, best_under_prob)),
        "top_under_scores": top_under_scores,
        "over_exact_score": best_over_score,
        "over_exact_score_prob": round(max(0.0, best_over_prob) * 100, 1),
        "over_exact_score_fair_odd": fair_odd(max(0.0, best_over_prob)),
        "top_over_scores": top_over_scores,
        "prob_1": round(prob_home, 4),
        "prob_x": round(prob_draw, 4),
        "prob_2": round(prob_away, 4),
        "fair_1": fair_odd(prob_home),
        "fair_x": fair_odd(prob_draw),
        "fair_2": fair_odd(prob_away),
        "prob_over_25": round(prob_over_25, 4),
        "prob_under_25": round(prob_under_25, 4),
        "fair_over_25": fair_odd(prob_over_25),
        "fair_under_25": fair_odd(prob_under_25),
        "edge_draw": edge(prob_draw, winamax_draw),
        "edge_over_25": edge(prob_over_25, winamax_over25),
        "edge_under_25": edge(prob_under_25, winamax_under25),
        "matrix_df": pd.DataFrame(
            [[round(val * 100, 1) for val in r] for r in matrix],
            index=[f"Local {i}" for i in range(max_goals + 1)],
            columns=[f"Visit {j}" for j in range(max_goals + 1)],
        ),
    }


def seleccionar_pronostico_goal(
    markets: dict,
    cuota_x: float = 0.0,
    cuota_o25: float = 0.0,
    cuota_u25: float = 0.0,
    min_edge: float = 0.0,
    min_prob_ou: float = 0.0,
    min_prob_under: float = 0.0,
    max_cuota_ou: float = 99.0,
    solo_goles: bool = True,
    home_stats: dict | None = None,
    away_stats: dict | None = None,
    exigir_consistencia: bool = True,
    mismo_equipo: bool = False,
    muestra_insuficiente: bool = False,
    umbral_racha: float = UMBRAL_RACHA_POR_DEFECTO,
    umbral_poisson: float = UMBRAL_POISSON_POR_DEFECTO,
) -> dict:
    resultado_exacto = {
        "marcador": markets.get("exact_score", "1 - 0"),
        "prob": markets.get("exact_score_prob", 0.0),
        "cuota_justa": markets.get("exact_score_fair_odd"),
        "top3": markets.get("top_exact_scores", []),
        "under_marcador": markets.get("under_exact_score", "1 - 0"),
        "under_prob": markets.get("under_exact_score_prob", 0.0),
        "under_cuota_justa": markets.get("under_exact_score_fair_odd"),
        "under_top3": markets.get("top_under_scores", []),
        "over_marcador": markets.get("over_exact_score", "2 - 1"),
        "over_prob": markets.get("over_exact_score_prob", 0.0),
        "over_cuota_justa": markets.get("over_exact_score_fair_odd"),
        "over_top3": markets.get("top_over_scores", []),
        "exacto_activo": False,
    }

    h_under = float((home_stats or {}).get("under25_rate", 0.0))
    a_under = float((away_stats or {}).get("under25_rate", 0.0))
    h_over = float((home_stats or {}).get("over25_rate", 0.0))
    a_over = float((away_stats or {}).get("over25_rate", 0.0))

    prob_u25_pct = round(float(markets.get("prob_under_25", 0.0)) * 100, 1)
    prob_o25_pct = round(float(markets.get("prob_over_25", 0.0)) * 100, 1)

    if mismo_equipo:
        return {
            "apostar": False,
            "senal_parcial": False,
            "pick": "NO APOSTAR",
            "motivo": "Se detectó el mismo equipo para local y visitante. Revisa los nombres o el país.",
            "racha_home": h_under,
            "racha_away": a_under,
            "prob_poisson": prob_u25_pct,
            "resultado_exacto": resultado_exacto,
        }

    if muestra_insuficiente or not home_stats or not away_stats:
        return {
            "apostar": False,
            "senal_parcial": False,
            "pick": "NO APOSTAR",
            "motivo": "Muestra insuficiente (se requieren al menos 6 partidos por equipo).",
            "racha_home": h_under,
            "racha_away": a_under,
            "prob_poisson": prob_u25_pct,
            "resultado_exacto": resultado_exacto,
        }

    if h_under >= umbral_racha and a_under >= umbral_racha:
        if prob_u25_pct >= umbral_poisson:
            resultado_exacto["exacto_activo"] = True
            return {
                "apostar": True,
                "senal_parcial": False,
                "pick": "UNDER 2.5 GOLES",
                "cuota": cuota_u25,
                "prob": prob_u25_pct,
                "prob_raw": markets.get("prob_under_25", 0.0),
                "cuota_justa": markets.get("fair_under_25"),
                "edge": markets.get("edge_under_25") or 0.0,
                "racha_home": h_under,
                "racha_away": a_under,
                "prob_poisson": prob_u25_pct,
                "resultado_exacto": resultado_exacto,
            }
        return {
            "apostar": False,
            "senal_parcial": True,
            "pick": "NO APOSTAR",
            "motivo": (
                f"Cumple racha -2.5 ({h_under:.1f}% vs {a_under:.1f}%), pero Poisson marca {prob_u25_pct:.1f}% "
                f"(mínimo requerido: {umbral_poisson:.1f}%)."
            ),
            "racha_home": h_under,
            "racha_away": a_under,
            "prob_poisson": prob_u25_pct,
            "resultado_exacto": resultado_exacto,
        }

    if h_over >= umbral_racha and a_over >= umbral_racha:
        if prob_o25_pct >= umbral_poisson:
            resultado_exacto["exacto_activo"] = True
            return {
                "apostar": True,
                "senal_parcial": False,
                "pick": "OVER 2.5 GOLES",
                "cuota": cuota_o25,
                "prob": prob_o25_pct,
                "prob_raw": markets.get("prob_over_25", 0.0),
                "cuota_justa": markets.get("fair_over_25"),
                "edge": markets.get("edge_over_25") or 0.0,
                "racha_home": h_over,
                "racha_away": a_over,
                "prob_poisson": prob_o25_pct,
                "resultado_exacto": resultado_exacto,
            }
        return {
            "apostar": False,
            "senal_parcial": True,
            "pick": "NO APOSTAR",
            "motivo": (
                f"Cumple racha +2.5 ({h_over:.1f}% vs {a_over:.1f}%), pero Poisson marca {prob_o25_pct:.1f}% "
                f"(mínimo requerido: {umbral_poisson:.1f}%)."
            ),
            "racha_home": h_over,
            "racha_away": a_over,
            "prob_poisson": prob_o25_pct,
            "resultado_exacto": resultado_exacto,
        }

    return {
        "apostar": False,
        "senal_parcial": False,
        "pick": "NO APOSTAR",
        "motivo": (
            f"No hay doble confirmación de racha (>={umbral_racha:.0f}%): "
            f"-2.5 ({h_under:.1f}% / {a_under:.1f}%) | +2.5 ({h_over:.1f}% / {a_over:.1f}%)."
        ),
        "racha_home": max(h_under, h_over),
        "racha_away": max(a_under, a_over),
        "prob_poisson": max(prob_u25_pct, prob_o25_pct),
        "resultado_exacto": resultado_exacto,
    }
