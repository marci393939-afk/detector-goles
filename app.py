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
}


def normalizar_texto(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


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
    cell_probs: list[tuple[str, float]] = []
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

    for h in range(max_goals + 1):
        norm_row = []
        for a in range(max_goals + 1):
            p_cell = raw_matrix[h][a] / total_mass if total_mass > 0 else raw_matrix[h][a]
            norm_row.append(p_cell)
            etiqueta = f"{h} - {a}"
            cell_probs.append((etiqueta, p_cell))

            if h > a:
                prob_home += p_cell
            elif h == a:
                prob_draw += p_cell
            else:
                prob_away += p_cell

            if (h + a) >= 3:
                prob_over_25 += p_cell
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
        for sc, pr in top_scores_sorted
    ]
    best_score, best_prob = top_scores_sorted[0]

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
                f"(mínimo requerido: {umbral_poisson:.0f}%)."
            ),
            "racha_home": h_under,
            "racha_away": a_under,
            "prob_poisson": prob_u25_pct,
            "resultado_exacto": resultado_exacto,
        }

    if h_over >= umbral_racha and a_over >= umbral_racha:
        if prob_o25_pct >= umbral_poisson:
            resultado_exacto["exacto_activo"] = False
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
                f"(mínimo requerido: {umbral_poisson:.0f}%)."
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
            f"No ambos equipos alcanzan el {umbral_racha:.0f}% en la misma línea "
            f"(-2.5: {h_under:.1f}% vs {a_under:.1f}% | +2.5: {h_over:.1f}% vs {a_over:.1f}%)."
        ),
        "racha_home": h_under,
        "racha_away": a_under,
        "prob_poisson": max(prob_u25_pct, prob_o25_pct),
        "resultado_exacto": resultado_exacto,
    }


def run_goal_matchup_poisson(
    home_query: str,
    away_query: str,
    country_filter: str | None,
    goal_key: str,
    last_n: int = 10,
    league_avg_per_side: float = 1.30,
    auto_league_avg: bool = True,
    max_lambda: float = 2.80,
    winamax_over25: float | None = None,
    winamax_under25: float | None = None,
    winamax_draw: float | None = None,
) -> dict:
    if not goal_key:
        raise RuntimeError("Falta GOAL_KEY en st.secrets o variables de entorno.")

    home_team = goal_resolve_team(home_query, country_filter, goal_key)
    away_team = goal_resolve_team(away_query, country_filter, goal_key)

    if not home_team:
        raise ValueError(f"No se encontró ningún equipo para '{home_query}'.")
    if not away_team:
        raise ValueError(f"No se encontró ningún equipo para '{away_query}'.")

    home_id = home_team["id"]
    away_id = away_team["id"]
    mismo_equipo = str(home_id) == str(away_id)

    home_stats = goal_summarize_team_goals(
        goal_fetch_team_results(home_id, goal_key, limit=50),
        home_id,
        last_n=last_n,
        prefer_venue="home",
    )
    away_stats = goal_summarize_team_goals(
        goal_fetch_team_results(away_id, goal_key, limit=50),
        away_id,
        last_n=last_n,
        prefer_venue="away",
    )

    manual_base = league_avg_per_side if league_avg_per_side > 0 else 1.30
    if auto_league_avg and home_stats["count"] > 0 and away_stats["count"] > 0:
        observada = (home_stats["total_avg"] + away_stats["total_avg"]) / 4.0
        base = max(0.85, min(1.95, (0.65 * observada) + (0.35 * manual_base)))
    else:
        base = manual_base

    n_h = max(1, home_stats["count"])
    n_a = max(1, away_stats["count"])
    prior_h = 1.5 if n_h >= 10 else 3.0
    prior_a = 1.5 if n_a >= 10 else 3.0

    gf_h_smooth = ((home_stats["gf_avg"] * n_h) + (base * prior_h)) / (n_h + prior_h)
    ga_h_smooth = ((home_stats["ga_avg"] * n_h) + (base * prior_h)) / (n_h + prior_h)
    gf_a_smooth = ((away_stats["gf_avg"] * n_a) + (base * prior_a)) / (n_a + prior_a)
    ga_a_smooth = ((away_stats["ga_avg"] * n_a) + (base * prior_a)) / (n_a + prior_a)

    home_att = gf_h_smooth / base
    home_def = ga_h_smooth / base
    away_att = gf_a_smooth / base
    away_def = ga_a_smooth / base

    raw_lam_home = home_att * away_def * base * 1.05
    raw_lam_away = away_att * home_def * base * 0.96

    cap = max(0.5, float(max_lambda))
    lam_home = min(max(0.20, raw_lam_home), cap)
    lam_away = min(max(0.20, raw_lam_away), cap)

    warnings: list[str] = []
    if mismo_equipo:
        warnings.append(
            f"Local y visitante resueltos como el mismo equipo ({home_team.get('name')})."
        )
    if home_stats["count"] < last_n:
        warnings.append(
            f"{home_team.get('name') or home_query} solo tiene {home_stats['count']} de {last_n} partidos solicitados."
        )
    if away_stats["count"] < last_n:
        warnings.append(
            f"{away_team.get('name') or away_query} solo tiene {away_stats['count']} de {last_n} partidos solicitados."
        )
    if raw_lam_home > cap or raw_lam_away > cap:
        warnings.append(
            f"Lambda acotada al máximo ({cap:.2f}) — sin tope era {raw_lam_home:.3f} / {raw_lam_away:.3f}."
        )

    muestra_insuficiente = home_stats["count"] < 6 or away_stats["count"] < 6

    markets = calculate_poisson_markets(
        lam_home=lam_home,
        lam_away=lam_away,
        winamax_over25=winamax_over25,
        winamax_under25=winamax_under25,
        winamax_draw=winamax_draw,
    )

    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_stats": home_stats,
        "away_stats": away_stats,
        "base_used": round(base, 2),
        "markets": markets,
        "warnings": warnings,
        "mismo_equipo": mismo_equipo,
        "muestra_insuficiente": muestra_insuficiente,
    }


def registrar_analisis_goal(
    home_name: str,
    away_name: str,
    last_n: int,
    m: dict,
    cuota_x: float,
    cuota_o25: float,
    cuota_u25: float,
    pronostico_txt: str,
    exacto_txt: str = "-",
    nota: str = "",
    pais_local: str = "",
    pais_visitante: str = "",
) -> None:
    st.session_state["analisis_log"].append(
        {
            "Local": home_name,
            "País Local": pais_local.strip() or "-",
            "Visitante": away_name,
            "País Visitante": pais_visitante.strip() or "-",
            "Pronóstico": pronostico_txt,
            "Exacto (-2.5)": exacto_txt,
            "Resultado exacto": m["exact_score"],
            "Prob. exacto (%)": m["exact_score_prob"],
            "Partidos (N)": last_n,
            "Goles esp.": m["expected_total_goals"],
            "Prob. O2.5 (%)": round(m["prob_over_25"] * 100, 1),
            "Prob. U2.5 (%)": round(m["prob_under_25"] * 100, 1),
            "Nota": nota.strip(),
        }
    )


def preparar_imagen_ocr(imagen: Image.Image) -> Image.Image:
    img = imagen.convert("RGB")
    w, h = img.size
    if max(w, h) < 1600:
        escala = 1600 / max(w, h)
        img = img.resize((int(w * escala), int(h * escala)), Image.Resampling.LANCZOS)

    gris = ImageOps.grayscale(img)
    gris = ImageEnhance.Contrast(gris).enhance(1.5)
    gris = ImageEnhance.Sharpness(gris).enhance(1.4)
    return gris


@st.cache_data(show_spinner=False)
def ejecutar_ocr_bytes(img_bytes: bytes, psm: int = 11) -> str:
    imagen = Image.open(BytesIO(img_bytes))
    procesada = preparar_imagen_ocr(imagen)
    config = f"--oem 3 --psm {psm}"
    return pytesseract.image_to_string(procesada, lang="spa+eng", config=config)


@st.cache_data(show_spinner=False)
def ejecutar_ocr_digitos_columna(
    img_bytes: bytes, psm: int = 6, umbral_binario: int | None = None
) -> str:
    imagen = Image.open(BytesIO(img_bytes)).convert("RGB")
    w, h = imagen.size

    x_ini = int(w * 0.70)
    x_fin = int(w * 0.99)
    y_ini = int(h * 0.10)
    y_fin = int(h * 0.99)

    recorte = imagen.crop((x_ini, y_ini, x_fin, y_fin))
    rw, rh = recorte.size
    if max(rw, rh) < 2000:
        escala = 2000 / max(rw, rh)
        recorte = recorte.resize(
            (max(1, int(rw * escala)), max(1, int(rh * escala))),
            Image.Resampling.LANCZOS,
        )

    gris = ImageOps.grayscale(recorte)
    gris = ImageEnhance.Contrast(gris).enhance(1.9)
    gris = ImageEnhance.Sharpness(gris).enhance(1.7)

    if umbral_binario is not None:
        gris = gris.point(lambda p: 255 if p > umbral_binario else 0)

    config = f"--oem 3 --psm {psm} -c tessedit_char_whitelist=0123456789"
    return pytesseract.image_to_string(gris, config=config)


def _linea_es_fecha_o_hora(linea: str) -> bool:
    if re.search(r"\b\d{1,2}:\d{2}\b", linea):
        return True
    if re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", linea.strip()):
        return True
    return False


def _linea_es_competicion_o_resultado(linea: str) -> bool:
    limpia = linea.strip().upper()
    if limpia in {"G", "P", "E", "W", "D", "L"}:
        return True
    if re.fullmatch(r"[A-Z]{1,4}\d{1,2}", limpia):
        return True
    return False


def extraer_marcadores_ocr(texto_ocr: str, max_partidos: int = 10) -> list[tuple[int, int]]:
    lineas = [l.strip() for l in (texto_ocr or "").splitlines() if l.strip()]

    pares_inline: list[tuple[int, int]] = []
    for linea in lineas:
        if _linea_es_fecha_o_hora(linea):
            continue
        for match in re.finditer(r"(?<!\d)(\d)\s*[-–—:]\s*(\d)(?!\d)", linea):
            g1, g2 = int(match.group(1)), int(match.group(2))
            if g1 <= 9 and g2 <= 9:
                pares_inline.append((g1, g2))
                if len(pares_inline) >= max_partidos:
                    return pares_inline

    digitos_sueltos: list[int] = []
    for linea in lineas:
        if _linea_es_fecha_o_hora(linea) or _linea_es_competicion_o_resultado(linea):
            continue
        if re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}", linea):
            continue
        m_solitario = re.fullmatch(r"\D*(\d)\D*", linea)
        if m_solitario:
            val = int(m_solitario.group(1))
            if 0 <= val <= 9:
                digitos_sueltos.append(val)

    pares_apilados: list[tuple[int, int]] = []
    for i in range(0, len(digitos_sueltos) - 1, 2):
        pares_apilados.append((digitos_sueltos[i], digitos_sueltos[i + 1]))
        if len(pares_apilados) >= max_partidos:
            break

    if len(pares_apilados) > len(pares_inline):
        return pares_apilados
    return pares_inline


def extraer_marcadores_desde_imagen(
    img_bytes: bytes, psm_preferido: int = 11
) -> tuple[str, list[tuple[int, int]]]:
    texto = ejecutar_ocr_bytes(img_bytes, psm=psm_preferido)
    pares = extraer_marcadores_ocr(texto, max_partidos=10)

    if len(pares) < 10:
        for psm_col in (6, 4):
            for umbral in (None, 185):
                txt_col = ejecutar_ocr_digitos_columna(
                    img_bytes, psm=psm_col, umbral_binario=umbral
                )
                digitos = [int(ch) for ch in re.findall(r"\d", txt_col or "") if int(ch) <= 9]
                pares_col = [
                    (digitos[i], digitos[i + 1])
                    for i in range(0, len(digitos) - 1, 2)
                ][:10]
                if len(pares_col) > len(pares):
                    pares = pares_col
                    if txt_col.strip():
                        etq_u = f"umbral={umbral}" if umbral is not None else "gris"
                        texto = f"{texto}\n--- Columna goles (PSM {psm_col}, {etq_u}) ---\n{txt_col}".strip()
                if len(pares) >= 10:
                    break
            if len(pares) >= 10:
                break

    if len(pares) < 6 and psm_preferido != 6:
        texto_alt = ejecutar_ocr_bytes(img_bytes, psm=6)
        pares_alt = extraer_marcadores_ocr(texto_alt, max_partidos=10)
        if len(pares_alt) > len(pares):
            return texto_alt, pares_alt

    return texto, pares


def parsear_marcadores_texto(texto_marcadores: str, max_partidos: int = 10) -> list[tuple[int, int]]:
    pares: list[tuple[int, int]] = []
    for match in re.finditer(r"(\d+)\s*[-–—:/]\s*(\d+)", texto_marcadores or ""):
        g1 = int(match.group(1))
        g2 = int(match.group(2))
        if g1 <= 15 and g2 <= 15:
            pares.append((g1, g2))
            if len(pares) >= max_partidos:
                break
    return pares


def construir_stats_desde_marcadores(
    marcadores: list[tuple[int, int]],
    equipo_nombre: str,
    es_local_en_proximo: bool = True,
) -> dict:
    n = len(marcadores)
    if n == 0:
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
    over25_count = 0
    rows = []

    for idx, (g1, g2) in enumerate(marcadores):
        gf_real = g1
        ga_real = g2
        total_real = gf_real + ga_real

        if total_real >= 3:
            over25_count += 1

        peso = 0.90**idx
        gf_w_sum += min(gf_real, 5) * peso
        ga_w_sum += min(ga_real, 5) * peso
        w_sum += peso

        rows.append(
            {
                "N.º": idx + 1,
                "Equipo": equipo_nombre or ("Local" if es_local_en_proximo else "Visitante"),
                "Marcador": f"{gf_real} - {ga_real}",
                "GF": gf_real,
                "GC": ga_real,
                "Total": total_real,
                "Línea": "+2.5" if total_real >= 3 else "-2.5",
            }
        )

    gf_avg = gf_w_sum / w_sum if w_sum > 0 else 0.0
    ga_avg = ga_w_sum / w_sum if w_sum > 0 else 0.0
    over_rate = round((over25_count / n) * 100, 1)
    under_rate = round(100.0 - over_rate, 1)

    return {
        "count": n,
        "gf_avg": gf_avg,
        "ga_avg": ga_avg,
        "total_avg": gf_avg + ga_avg,
        "over25_rate": over_rate,
        "under25_rate": under_rate,
        "venue_used": False,
        "matches": rows,
    }


def _es_token_basura_ocr(token: str) -> bool:
    if ":" in token or ";" in token:
        return True
    limpio = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", token)
    if len(limpio) < 2:
        return True
    if len(set(limpio.lower())) == 1:
        return True
    if len(limpio) <= 6 and re.search(r"[A-Z]{2,}[a-z]+[A-Z]|[a-z]+[A-Z]{2,}", limpio):
        return True
    return False


def _es_candidato_equipo_valido(candidato: str) -> bool:
    limpio = re.sub(r"\s+", " ", candidato).strip()
    if len(limpio) < 3 or len(limpio) > 30:
        return False
    if re.search(r"[:;{}\[\]~\\]", limpio):
        return False
    norm_upper = normalizar_texto(limpio).upper()
    if any(ruido in norm_upper for ruido in PALABRAS_RUIDO):
        return False
    palabras = limpio.split()
    if len(palabras) > 3:
        return False
    if len(palabras) == 1 and len(re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", palabras[0])) < 3:
        return False
    letras = sum(c.isalpha() for c in limpio)
    if letras < 3:
        return False
    minus = [normalizar_texto(p) for p in palabras]
    if set(minus).issubset(
        {"solo", "para", "nue", "fo", "ussun", "con", "del", "las", "los", "war", "alert"}
    ):
        return False
    return True


def limpiar_lineas_ocr(texto_ocr: str) -> list[str]:
    lineas_limpias = []
    for linea in texto_ocr.splitlines():
        limpia = linea.strip()
        if not limpia:
            continue

        limpia = re.sub(r"\bSTREAM\b", " ", limpia, flags=re.IGNORECASE)
        limpia = re.sub(r"\s+", " ", limpia).strip(" |")
        if not limpia:
            continue

        if "_" in limpia or "=" in limpia or ":" in limpia:
            continue

        if re.fullmatch(r"\d{1,2}[:.\-]\d{1,2}(?:[:.\-]\d{2,4})?", limpia):
            continue

        if limpia.startswith("@") or re.fullmatch(r"1\s+[xX]{1,2}\s+2", limpia):
            continue

        mayus = limpia.upper()
        if any(palabra in mayus for palabra in PALABRAS_RUIDO):
            continue

        tokens = limpia.split()
        if tokens and all(tok.isupper() and len(tok) <= 4 for tok in tokens) and len(tokens) > 1:
            continue

        if tokens and all(_es_token_basura_ocr(tok) for tok in tokens):
            continue

        letras = sum(c.isalpha() for c in limpia)
        if letras < 3:
            continue

        lineas_limpias.append(limpia)

    return lineas_limpias


def _separar_dos_equipos_en_linea(texto: str) -> list[str]:
    limpio = re.sub(r"\s+", " ", texto).strip()
    if not limpio:
        return []

    sufijos_club = {
        "fc",
        "cf",
        "cd",
        "ud",
        "sc",
        "ac",
        "fk",
        "sk",
        "bk",
        "jk",
        "afc",
        "bfc",
        "cfc",
        "united",
        "city",
        "athletic",
        "rovers",
        "wanderers",
        "albion",
        "town",
        "county",
        "real",
        "sporting",
        "atletico",
        "atlético",
        "deportivo",
        "racing",
        "club",
        "soccer",
        "andarers",
    }

    palabras = limpio.split()
    n = len(palabras)
    if n < 2:
        return [limpio]

    if n >= 4 and all(re.match(r"^[A-ZÁÉÍÓÚÜÑ]", p) for p in palabras):
        mitad = n // 2
        izq = " ".join(palabras[:mitad]).strip()
        der = " ".join(palabras[mitad:]).strip()
        if len(izq) >= 3 and len(der) >= 3:
            return [izq, der]

    for idx in range(1, n):
        izq = " ".join(palabras[:idx]).strip()
        der = " ".join(palabras[idx:]).strip()
        tok_izq = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", palabras[idx - 1]).lower()
        tok_der = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", palabras[idx]).lower()

        es_corte_club = tok_izq in sufijos_club or tok_der in {
            "fc",
            "cf",
            "cd",
            "ud",
            "sc",
            "ac",
            "real",
            "sporting",
            "club",
        }
        es_corte_par = (
            n in (2, 3)
            and all(re.match(r"^[A-ZÁÉÍÓÚÜÑ]", p) for p in palabras)
            and idx == 1
        )

        if (
            len(izq) >= 3
            and len(der) >= 3
            and not _es_token_basura_ocr(izq)
            and not _es_token_basura_ocr(der)
            and (es_corte_club or es_corte_par)
        ):
            return [izq, der]

    return [limpio]


def _extraer_equipos_de_linea(linea: str) -> list[str]:
    partes = re.split(
        r"\s*(?:>|\bvs\.?\b|\s-\s|\d{1,2}:\d{2})\s*", linea, flags=re.IGNORECASE
    )
    encontrados: list[str] = []
    for parte in partes:
        limpia_parte = re.sub(r"\s+", " ", parte).strip(" -|>/\\")
        if not limpia_parte:
            continue
        for sub_eq in _separar_dos_equipos_en_linea(limpia_parte):
            if _es_candidato_equipo_valido(sub_eq) and sub_eq not in encontrados:
                encontrados.append(sub_eq)
    return encontrados


def sugerir_equipos_candidatos(texto_ocr: str) -> tuple[str, str]:
    lineas = limpiar_lineas_ocr(texto_ocr)
    candidatos_cruce: list[str] = []
    equipos: list[str] = []

    for linea in lineas:
        if re.search(r"[|{}~<>\\:]", linea) and ">" not in linea:
            continue

        es_cruce = bool(
            ">" in linea
            or re.search(r"\bvs\.?\b", linea, flags=re.IGNORECASE)
            or re.search(r"\b\d{1,2}:\d{2}\b", linea)
        )

        if not es_cruce and re.search(r"\d{3,}", linea):
            continue

        partes_linea = _extraer_equipos_de_linea(linea)
        if es_cruce and len(partes_linea) >= 2:
            for eq in partes_linea:
                if eq not in candidatos_cruce:
                    candidatos_cruce.append(eq)

        for eq in partes_linea:
            if eq not in equipos:
                equipos.append(eq)

    if len(equipos) == 1:
        separados = _separar_dos_equipos_en_linea(equipos[0])
        if len(separados) == 2 and all(_es_candidato_equipo_valido(x) for x in separados):
            return separados[0], separados[1]

    fuente = candidatos_cruce if len(candidatos_cruce) >= 2 else equipos
    local = fuente[0] if len(fuente) >= 1 and _es_candidato_equipo_valido(fuente[0]) else ""
    visitante = (
        fuente[1] if len(fuente) >= 2 and _es_candidato_equipo_valido(fuente[1]) else ""
    )
    return local, visitante


def calcular_xg_moderado(
    gf_local_10: float,
    gc_local_10: float,
    gf_vis_10: float,
    gc_vis_10: float,
    goles_h2h_prom: float | None = None,
    peso_h2h: float = 0.12,
) -> tuple[float, float]:
    gf_l = min(max(gf_local_10, 0.20), 4.2)
    gc_l = min(max(gc_local_10, 0.20), 4.2)
    gf_v = min(max(gf_vis_10, 0.20), 4.2)
    gc_v = min(max(gc_vis_10, 0.20), 4.2)

    xg_local = ((gf_l + gc_v) / 2.0) * 1.04
    xg_visitante = ((gf_v + gc_l) / 2.0) * 0.96

    if goles_h2h_prom is not None and goles_h2h_prom > 0:
        h2h_mod = min(max(goles_h2h_prom, 0.5), 5.0)
        total_base = xg_local + xg_visitante
        total_ajustado = ((1.0 - peso_h2h) * total_base) + (peso_h2h * h2h_mod)
        if total_base > 0:
            factor = total_ajustado / total_base
            xg_local *= factor
            xg_visitante *= factor

    return round(min(2.80, max(0.20, xg_local)), 2), round(min(2.80, max(0.20, xg_visitante)), 2)


def probs_over_under_25(xg_local: float, xg_visitante: float) -> dict[str, float]:
    total_xg = max(0.10, xg_local + xg_visitante)
    p_0 = poisson_pmf(0, total_xg)
    p_1 = poisson_pmf(1, total_xg)
    p_2 = poisson_pmf(2, total_xg)

    p_under_25 = min(0.99, max(0.01, p_0 + p_1 + p_2))
    p_over_25 = 1.0 - p_under_25

    return {
        "xg_total": round(total_xg, 2),
        "p_under_25": p_under_25,
        "p_over_25": p_over_25,
    }


def evaluar_entrada_25(
    xg_local: float,
    xg_visitante: float,
    cuota_over_25: float | None = None,
    cuota_under_25: float | None = None,
    under25_rate_local: float | None = None,
    under25_rate_vis: float | None = None,
    over25_rate_local: float | None = None,
    over25_rate_vis: float | None = None,
    umbral_racha: float = UMBRAL_RACHA_POR_DEFECTO,
    umbral_poisson: float = UMBRAL_POISSON_POR_DEFECTO,
) -> dict:
    probs = probs_over_under_25(xg_local, xg_visitante)
    xg_total = probs["xg_total"]
    p_over = probs["p_over_25"]
    p_under = probs["p_under_25"]
    p_over_pct = round(p_over * 100, 1)
    p_under_pct = round(p_under * 100, 1)

    u_l = float(under25_rate_local or 0.0)
    u_v = float(under25_rate_vis or 0.0)
    o_l = float(over25_rate_local or 0.0)
    o_v = float(over25_rate_vis or 0.0)

    desglose = [
        {
            "Línea": "-2.5 goles",
            "Local (10 PJ)": f"{u_l:.1f}%",
            "Visitante (10 PJ)": f"{u_v:.1f}%",
            "Poisson": f"{p_under_pct:.1f}%",
            f"Racha>={umbral_racha:.0f}% + Pois>={umbral_poisson:.0f}%": (
                "OK"
                if (u_l >= umbral_racha and u_v >= umbral_racha and p_under_pct >= umbral_poisson)
                else "No"
            ),
        },
        {
            "Línea": "+2.5 goles",
            "Local (10 PJ)": f"{o_l:.1f}%",
            "Visitante (10 PJ)": f"{o_v:.1f}%",
            "Poisson": f"{p_over_pct:.1f}%",
            f"Racha>={umbral_racha:.0f}% + Pois>={umbral_poisson:.0f}%": (
                "OK"
                if (o_l >= umbral_racha and o_v >= umbral_racha and p_over_pct >= umbral_poisson)
                else "No"
            ),
        },
    ]

    if u_l >= umbral_racha and u_v >= umbral_racha and p_under_pct >= umbral_poisson:
        return {
            "decision": "APOSTAR",
            "mercado": "-2.5 goles",
            "racha_local": u_l,
            "racha_vis": u_v,
            "prob_poisson": p_under_pct,
            "xg_total": xg_total,
            "p_over_25": p_over_pct,
            "p_under_25": p_under_pct,
            "desglose": desglose,
        }

    if o_l >= umbral_racha and o_v >= umbral_racha and p_over_pct >= umbral_poisson:
        return {
            "decision": "APOSTAR",
            "mercado": "+2.5 goles",
            "racha_local": o_l,
            "racha_vis": o_v,
            "prob_poisson": p_over_pct,
            "xg_total": xg_total,
            "p_over_25": p_over_pct,
            "p_under_25": p_under_pct,
            "desglose": desglose,
        }

    if u_l >= umbral_racha and u_v >= umbral_racha:
        motivo = (
            f"Cumple racha -2.5 ({u_l:.1f}% vs {u_v:.1f}%), pero Poisson es {p_under_pct:.1f}% "
            f"(mínimo {umbral_poisson:.0f}%)."
        )
    elif o_l >= umbral_racha and o_v >= umbral_racha:
        motivo = (
            f"Cumple racha +2.5 ({o_l:.1f}% vs {o_v:.1f}%), pero Poisson es {p_over_pct:.1f}% "
            f"(mínimo {umbral_poisson:.0f}%)."
        )
    else:
        motivo = (
            f"No ambos equipos alcanzan el {umbral_racha:.0f}% en la misma línea "
            f"(-2.5: {u_l:.1f}% vs {u_v:.1f}% | +2.5: {o_l:.1f}% vs {o_v:.1f}%)."
        )

    return {
        "decision": "NO APOSTAR",
        "motivo": motivo,
        "xg_total": xg_total,
        "p_over_25": p_over_pct,
        "p_under_25": p_under_pct,
        "desglose": desglose,
    }


def renderizar_resultado(resultado: dict, partido_label: str) -> None:
    st.markdown(f"**Partido:** {partido_label}")

    r1, r2, r3 = st.columns(3)
    r1.metric("Goles esperados (xG)", f"{resultado['xg_total']:.2f}")
    r2.metric("Prob. +2.5 goles", f"{resultado['p_over_25']:.1f}%")
    r3.metric("Prob. -2.5 goles", f"{resultado['p_under_25']:.1f}%")

    if resultado["decision"] == "APOSTAR":
        st.success(
            f"### ✅ APOSTAR → {resultado['mercado'].upper()}\n"
            f"**Racha en 10 PJ:** Local `{resultado['racha_local']:.1f}%` · Visitante `{resultado['racha_vis']:.1f}%` | "
            f"**Poisson:** `{resultado['prob_poisson']:.1f}%`"
        )
    else:
        st.warning(f"### ⛔ NO APOSTAR\n{resultado['motivo']}")

    if resultado.get("desglose"):
        st.dataframe(resultado["desglose"], width="stretch", hide_index=True)


def _parsear_lote_partidos(texto_lote: str) -> list[tuple[str, str]]:
    filas: list[tuple[str, str]] = []
    for raw in (texto_lote or "").splitlines():
        linea = raw.strip()
        if not linea or linea.startswith("#"):
            continue
        cruce_txt = linea.split("|")[0].strip()
        m_cruce = re.split(r"\s+(?:vs\.?|-)\s+", cruce_txt, maxsplit=1, flags=re.IGNORECASE)
        if len(m_cruce) != 2 or not m_cruce[0].strip() or not m_cruce[1].strip():
            continue
        filas.append((m_cruce[0].strip(), m_cruce[1].strip()))
    return filas


for clave, valor_ini in {
    "gf_local_10": 1.40,
    "gc_local_10": 1.10,
    "gf_vis_10": 1.20,
    "gc_vis_10": 1.20,
    "under25_local_10": 60.0,
    "under25_vis_10": 60.0,
    "goles_h2h_prom": 2.40,
    "usar_h2h": False,
    "api_info_msg": "",
    "api_warn_msg": "",
    "analisis_log": [],
    "ultimo_goal_analisis": None,
    "goal_home_input": "",
    "goal_away_input": "",
    "goal_pais_comun_input": "",
    "goal_home_country_input": "",
    "goal_away_country_input": "",
    "goal_country_input": "",
    "goal_nota_input": "",
    "pais_ocr_detectado": "",
    "pais_status_msg": "",
    "ultimo_ocr_partido_file": None,
    "ultimo_ocr_local_10_file": None,
    "ultimo_ocr_vis_10_file": None,
    "ultimo_auto_fetch": None,
    "marcadores_local_10_txt": "",
    "marcadores_vis_10_txt": "",
    "lote_partidos_texto": "",
    "det_pais_local_input": "",
    "det_pais_vis_input": "",
    "uploader_reset_id": 0,
    "cache_paises_equipos": cargar_cache_paises(),
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor_ini


def _limpiar_partido_goal() -> None:
    st.session_state["uploader_reset_id"] = int(st.session_state.get("uploader_reset_id", 0)) + 1
    st.session_state["goal_home_input"] = ""
    st.session_state["goal_away_input"] = ""
    st.session_state["goal_pais_comun_input"] = ""
    st.session_state["goal_home_country_input"] = ""
    st.session_state["goal_away_country_input"] = ""
    st.session_state["goal_country_input"] = ""
    st.session_state["goal_nota_input"] = ""
    st.session_state["pais_ocr_detectado"] = ""
    st.session_state["pais_status_msg"] = ""
    st.session_state["marcadores_local_10_txt"] = ""
    st.session_state["marcadores_vis_10_txt"] = ""
    st.session_state["ultimo_goal_analisis"] = None
    st.session_state["ultimo_ocr_partido_file"] = None
    st.session_state["ultimo_ocr_local_10_file"] = None
    st.session_state["ultimo_ocr_vis_10_file"] = None
    st.session_state["ultimo_auto_fetch"] = None
    st.session_state["equipo_local_input"] = ""
    st.session_state["equipo_visitante_input"] = ""
    st.session_state["det_pais_local_input"] = ""
    st.session_state["det_pais_vis_input"] = ""
    st.session_state["api_info_msg"] = ""
    st.session_state["api_warn_msg"] = ""
    st.session_state["gf_local_10"] = 1.40
    st.session_state["gc_local_10"] = 1.10
    st.session_state["gf_vis_10"] = 1.20
    st.session_state["gc_vis_10"] = 1.20
    st.session_state["under25_local_10"] = 60.0
    st.session_state["under25_vis_10"] = 60.0
    st.session_state["goles_h2h_prom"] = 2.40
    st.session_state["usar_h2h"] = False


def _aplicar_pais_comun_cb() -> None:
    pais_ref = (
        st.session_state.get("goal_pais_comun_input")
        or st.session_state.get("goal_home_country_input")
        or st.session_state.get("goal_away_country_input")
        or ""
    ).strip()
    if not pais_ref:
        st.session_state["pais_status_msg"] = "warn:Escribe un país antes de aplicarlo."
        return
    st.session_state["goal_pais_comun_input"] = pais_ref
    st.session_state["goal_home_country_input"] = pais_ref
    st.session_state["goal_away_country_input"] = pais_ref
    loc_act = st.session_state.get("goal_home_input", "").strip()
    vis_act = st.session_state.get("goal_away_input", "").strip()
    if loc_act:
        guardar_equipo_pais(loc_act, pais_ref)
    if vis_act:
        guardar_equipo_pais(vis_act, pais_ref)
    st.session_state["pais_status_msg"] = f"ok:País '{pais_ref}' aplicado a ambos equipos."


def _guardar_paises_cb() -> None:
    comun = st.session_state.get("goal_pais_comun_input", "").strip()
    pais_l = (st.session_state.get("goal_home_country_input") or comun).strip()
    pais_v = (st.session_state.get("goal_away_country_input") or comun).strip()
    loc_act = st.session_state.get("goal_home_input", "").strip()
    vis_act = st.session_state.get("goal_away_input", "").strip()

    guardado = False
    if loc_act and pais_l:
        guardar_equipo_pais(loc_act, pais_l)
        st.session_state["goal_home_country_input"] = pais_l
        guardado = True
    if vis_act and pais_v:
        guardar_equipo_pais(vis_act, pais_v)
        st.session_state["goal_away_country_input"] = pais_v
        guardado = True

    if guardado:
        st.session_state["pais_status_msg"] = "ok:País guardado en memoria local para los equipos."
    else:
        st.session_state["pais_status_msg"] = "warn:Introduce al menos un equipo y su país para guardarlo."


def _calcular_desde_capturas_3(
    home_nombre: str,
    away_nombre: str,
    marcadores_l: list[tuple[int, int]],
    marcadores_v: list[tuple[int, int]],
    league_avg_per_side: float,
    auto_league_avg: bool,
    max_lambda: float,
    pais_comun_manual: str = "",
    pais_local_manual: str = "",
    pais_vis_manual: str = "",
    pais_ocr_hint: str = "",
) -> dict:
    loc_limpio = (home_nombre or "Local").strip() or "Local"
    vis_limpio = (away_nombre or "Visitante").strip() or "Visitante"
    mismo_equipo = normalizar_texto(loc_limpio) == normalizar_texto(vis_limpio)

    comun_limpio = (pais_comun_manual or "").strip()
    pais_loc = (pais_local_manual or "").strip() or comun_limpio or consultar_pais_equipo(loc_limpio)
    pais_vis = (pais_vis_manual or "").strip() or comun_limpio or consultar_pais_equipo(vis_limpio)

    if pais_ocr_hint:
        if not pais_loc:
            pais_loc = pais_ocr_hint
        if not pais_vis:
            pais_vis = pais_ocr_hint

    if pais_loc:
        guardar_equipo_pais(loc_limpio, pais_loc)
    if pais_vis:
        guardar_equipo_pais(vis_limpio, pais_vis)

    hs = construir_stats_desde_marcadores(marcadores_l, loc_limpio, es_local_en_proximo=True)
    aws = construir_stats_desde_marcadores(marcadores_v, vis_limpio, es_local_en_proximo=False)

    manual_base = league_avg_per_side if league_avg_per_side > 0 else 1.30
    if auto_league_avg and hs["count"] > 0 and aws["count"] > 0:
        observada = (hs["total_avg"] + aws["total_avg"]) / 4.0
        base = max(0.85, min(1.95, (0.65 * observada) + (0.35 * manual_base)))
    else:
        base = manual_base

    n_h = max(1, hs["count"])
    n_a = max(1, aws["count"])
    prior_h = 1.5 if n_h >= 10 else 3.0
    prior_a = 1.5 if n_a >= 10 else 3.0

    gf_h_smooth = ((hs["gf_avg"] * n_h) + (base * prior_h)) / (n_h + prior_h)
    ga_h_smooth = ((hs["ga_avg"] * n_h) + (base * prior_h)) / (n_h + prior_h)
    gf_a_smooth = ((aws["gf_avg"] * n_a) + (base * prior_a)) / (n_a + prior_a)
    ga_a_smooth = ((aws["ga_avg"] * n_a) + (base * prior_a)) / (n_a + prior_a)

    raw_lam_home = ((gf_h_smooth / base) * (ga_a_smooth / base)) * base * 1.05
    raw_lam_away = ((gf_a_smooth / base) * (ga_h_smooth / base)) * base * 0.96

    cap = max(0.5, float(max_lambda))
    lam_home = min(max(0.20, raw_lam_home), cap)
    lam_away = min(max(0.20, raw_lam_away), cap)

    warnings: list[str] = []
    if mismo_equipo:
        warnings.append("Local y visitante tienen el mismo nombre.")
    if hs["count"] < 10:
        warnings.append(f"{loc_limpio}: se detectaron {hs['count']} marcadores (ideal: 10).")
    if aws["count"] < 10:
        warnings.append(f"{vis_limpio}: se detectaron {aws['count']} marcadores (ideal: 10).")

    muestra_insuficiente = hs["count"] < 6 or aws["count"] < 6
    markets = calculate_poisson_markets(lam_home=lam_home, lam_away=lam_away)

    return {
        "home_team": {"name": loc_limpio, "country": pais_loc},
        "away_team": {"name": vis_limpio, "country": pais_vis},
        "home_stats": hs,
        "away_stats": aws,
        "base_used": round(base, 2),
        "markets": markets,
        "warnings": warnings,
        "mismo_equipo": mismo_equipo,
        "muestra_insuficiente": muestra_insuficiente,
    }


reset_id = int(st.session_state.get("uploader_reset_id", 0))

st.title("⚽ Detector de Goles (+2.5 / -2.5)")
st.caption("3 capturas manuales (partido + 10 últimos del local + 10 últimos del visitante) · Filtro híbrido Racha + Poisson.")

tab_poisson, tab_lote, tab_detector, tab_registro = st.tabs(
    ["Análisis Poisson", "Evaluador rápido", "Detector (+2.5 / -2.5)", "Registro de análisis"]
)

with tab_poisson:
    st.subheader("Análisis con 3 capturas manuales")
    st.caption(
        "Sube: 1) captura del partido, 2) últimos 10 partidos del local y 3) últimos 10 partidos del visitante."
    )

    col_top_l, col_top_r = st.columns([3.5, 1.2])
    col_top_l.markdown("**Paso 1 · Captura del partido**")
    col_top_r.button(
        "🧹 Limpiar",
        key="btn_clear_goal",
        on_click=_limpiar_partido_goal,
        width="stretch",
    )

    psm_goal = st.selectbox(
        "Modo OCR (PSM)",
        options=[11, 6, 4, 3],
        index=0,
        key="goal_ocr_psm",
    )

    archivo_partido = st.file_uploader(
        "1. Captura del partido a analizar",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"ocr_partido_uploader_{reset_id}",
    )
    if archivo_partido is not None:
        img_p_bytes = archivo_partido.getvalue()
        img_p = Image.open(BytesIO(img_p_bytes))
        st.image(
            img_p,
            caption=f"1. Partido ({img_p.width}x{img_p.height} px)",
            width="stretch",
        )
        try:
            txt_p = ejecutar_ocr_bytes(img_p_bytes, psm=psm_goal)
            loc_ocr, vis_ocr = sugerir_equipos_candidatos(txt_p)
            pais_p = detectar_pais_en_ocr(txt_p)
            marca_p = f"{archivo_partido.file_id}_{psm_goal}"
            if st.session_state.get("ultimo_ocr_partido_file") != marca_p:
                if loc_ocr:
                    st.session_state["goal_home_input"] = loc_ocr
                if vis_ocr:
                    st.session_state["goal_away_input"] = vis_ocr
                if pais_p:
                    st.session_state["pais_ocr_detectado"] = pais_p
                    if not st.session_state.get("goal_pais_comun_input", "").strip():
                        st.session_state["goal_pais_comun_input"] = pais_p
                    if loc_ocr:
                        guardar_equipo_pais(loc_ocr, pais_p)
                    if vis_ocr:
                        guardar_equipo_pais(vis_ocr, pais_p)
                pais_l_cache = consultar_pais_equipo(loc_ocr) or pais_p
                pais_v_cache = consultar_pais_equipo(vis_ocr) or pais_p
                if pais_l_cache and not st.session_state.get("goal_home_country_input", "").strip():
                    st.session_state["goal_home_country_input"] = pais_l_cache
                if pais_v_cache and not st.session_state.get("goal_away_country_input", "").strip():
                    st.session_state["goal_away_country_input"] = pais_v_cache
                st.session_state["ultimo_ocr_partido_file"] = marca_p
            with st.expander("Ver texto OCR — Captura 1 (Partido)"):
                st.text(txt_p if txt_p.strip() else "No se detectó texto.")
        except Exception as exc:
            st.error(f"Error al leer captura del partido: {exc}")

    gc1, gc2 = st.columns(2)
    g_home_input = gc1.text_input("Equipo Local", key="goal_home_input")
    g_away_input = gc2.text_input("Equipo Visitante", key="goal_away_input")

    if g_home_input.strip() and not st.session_state.get("goal_home_country_input", "").strip():
        pais_auto_l = consultar_pais_equipo(g_home_input)
        if pais_auto_l:
            st.session_state["goal_home_country_input"] = pais_auto_l
    if g_away_input.strip() and not st.session_state.get("goal_away_country_input", "").strip():
        pais_auto_v = consultar_pais_equipo(g_away_input)
        if pais_auto_v:
            st.session_state["goal_away_country_input"] = pais_auto_v

    with st.container(border=True):
        st.markdown("**🌍 País de los equipos de la captura**")
        g_pais_comun = st.text_input(
            "País común (si ambos juegan en el mismo país)",
            placeholder="Ej.: Egipto, España, Kenia, Nicaragua...",
            key="goal_pais_comun_input",
        )
        pc1, pc2 = st.columns(2)
        g_home_country = pc1.text_input(
            "País del Equipo Local",
            placeholder="Ej.: Egipto",
            key="goal_home_country_input",
        )
        g_away_country = pc2.text_input(
            "País del Equipo Visitante",
            placeholder="Ej.: Egipto",
            key="goal_away_country_input",
        )

        pb1, pb2 = st.columns(2)
        pb1.button(
            "📋 Aplicar país común a ambos",
            key="btn_apply_common_country",
            on_click=_aplicar_pais_comun_cb,
            width="stretch",
        )
        pb2.button(
            "💾 Guardar país en memoria local",
            key="btn_save_countries_main",
            on_click=_guardar_paises_cb,
            width="stretch",
        )

        status_pais = st.session_state.get("pais_status_msg", "")
        if status_pais.startswith("ok:"):
            st.success(status_pais[3:])
        elif status_pais.startswith("warn:"):
            st.warning(status_pais[5:])

    pais_l_preview = (
        g_home_country.strip()
        or g_pais_comun.strip()
        or consultar_pais_equipo(g_home_input)
    )
    pais_v_preview = (
        g_away_country.strip()
        or g_pais_comun.strip()
        or consultar_pais_equipo(g_away_input)
    )
    if g_home_input.strip() or g_away_input.strip():
        etq_l = f"**{g_home_input or 'Local'}** (`{pais_l_preview or 'Sin país'}`)"
        etq_v = f"**{g_away_input or 'Visitante'}** (`{pais_v_preview or 'Sin país'}`)"
        if (
            pais_l_preview
            and pais_v_preview
            and normalizar_texto(pais_l_preview) == normalizar_texto(pais_v_preview)
        ):
            st.caption(f"🌍 Verificación: {etq_l} vs {etq_v} · ✅ Ambos de **{pais_l_preview}**")
        else:
            st.caption(f"🌍 Verificación: {etq_l} vs {etq_v}")

    st.markdown("**Paso 2 · Captura de los últimos 10 partidos del Equipo Local**")
    archivo_local_10 = st.file_uploader(
        "2. Últimos 10 partidos — Local",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"ocr_local_10_uploader_{reset_id}",
    )
    if archivo_local_10 is not None:
        img_l_bytes = archivo_local_10.getvalue()
        img_l = Image.open(BytesIO(img_l_bytes))
        st.image(
            img_l,
            caption=f"2. Últimos 10 Local ({img_l.width}x{img_l.height} px)",
            width="stretch",
        )
        try:
            txt_l, pares_l = extraer_marcadores_desde_imagen(img_l_bytes, psm_preferido=psm_goal)
            pais_l_ocr = detectar_pais_en_ocr(txt_l)
            if pais_l_ocr and g_home_input.strip():
                guardar_equipo_pais(g_home_input, pais_l_ocr)
            marca_l = f"{archivo_local_10.file_id}_{psm_goal}"
            if st.session_state.get("ultimo_ocr_local_10_file") != marca_l:
                st.session_state["marcadores_local_10_txt"] = ", ".join(
                    f"{a}-{b}" for a, b in pares_l
                )
                st.session_state["ultimo_ocr_local_10_file"] = marca_l
            with st.expander("Ver texto OCR — Captura 2 (10 últimos Local)"):
                st.text(txt_l if txt_l.strip() else "No se detectó texto.")
        except Exception as exc:
            st.error(f"Error al leer captura del local: {exc}")

    st.text_area(
        "Marcadores detectados Local (puedes corregir o escribir a mano, ej.: 1-0, 2-1, 0-0)",
        height=72,
        key="marcadores_local_10_txt",
    )

    st.markdown("**Paso 3 · Captura de los últimos 10 partidos del Equipo Visitante**")
    archivo_vis_10 = st.file_uploader(
        "3. Últimos 10 partidos — Visitante",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"ocr_vis_10_uploader_{reset_id}",
    )
    if archivo_vis_10 is not None:
        img_v_bytes = archivo_vis_10.getvalue()
        img_v = Image.open(BytesIO(img_v_bytes))
        st.image(
            img_v,
            caption=f"3. Últimos 10 Visitante ({img_v.width}x{img_v.height} px)",
            width="stretch",
        )
        try:
            txt_v, pares_v = extraer_marcadores_desde_imagen(img_v_bytes, psm_preferido=psm_goal)
            pais_v_ocr = detectar_pais_en_ocr(txt_v)
            if pais_v_ocr and g_away_input.strip():
                guardar_equipo_pais(g_away_input, pais_v_ocr)
            marca_v = f"{archivo_vis_10.file_id}_{psm_goal}"
            if st.session_state.get("ultimo_ocr_vis_10_file") != marca_v:
                st.session_state["marcadores_vis_10_txt"] = ", ".join(
                    f"{a}-{b}" for a, b in pares_v
                )
                st.session_state["ultimo_ocr_vis_10_file"] = marca_v
            with st.expander("Ver texto OCR — Captura 3 (10 últimos Visitante)"):
                st.text(txt_v if txt_v.strip() else "No se detectó texto.")
        except Exception as exc:
            st.error(f"Error al leer captura del visitante: {exc}")

    st.text_area(
        "Marcadores detectados Visitante (puedes corregir o escribir a mano, ej.: 0-1, 1-1, 2-0)",
        height=72,
        key="marcadores_vis_10_txt",
    )

    with st.expander("Ajustes avanzados del modelo"):
        gp1, gp2 = st.columns(2)
        g_league_avg = gp1.number_input(
            "Media base goles/equipo",
            min_value=0.6,
            max_value=2.5,
            value=1.30,
            step=0.05,
            key="goal_league_avg",
        )
        g_auto_league = gp2.checkbox(
            "Adaptar media al ritmo real de ambos",
            value=True,
            key="goal_auto_league",
        )
        g_max_lambda = st.slider(
            "Límite máximo λ",
            min_value=1.50,
            max_value=4.50,
            value=2.80,
            step=0.10,
            key="goal_max_lambda",
        )
        g_umbral_poisson = st.slider(
            "Probabilidad mínima Poisson (%)",
            min_value=50.0,
            max_value=75.0,
            value=UMBRAL_POISSON_POR_DEFECTO,
            step=1.0,
            key="goal_umbral_poisson",
        )

    g_nota = st.text_input("Nota rápida (opcional)", key="goal_nota_input")

    if st.button(
        "Calcular pronóstico desde las 3 capturas",
        type="primary",
        key="btn_calc_goal_poisson",
        width="stretch",
    ):
        try:
            pares_loc = parsear_marcadores_texto(
                st.session_state.get("marcadores_local_10_txt", ""), max_partidos=10
            )
            pares_vis = parsear_marcadores_texto(
                st.session_state.get("marcadores_vis_10_txt", ""), max_partidos=10
            )
            if not pares_loc or not pares_vis:
                st.error(
                    "Necesitas marcadores válidos (formato ej. 1-0, 2-1) en ambos equipos para calcular."
                )
            else:
                res_g = _calcular_desde_capturas_3(
                    home_nombre=g_home_input,
                    away_nombre=g_away_input,
                    marcadores_l=pares_loc,
                    marcadores_v=pares_vis,
                    league_avg_per_side=g_league_avg,
                    auto_league_avg=g_auto_league,
                    max_lambda=g_max_lambda,
                    pais_comun_manual=g_pais_comun,
                    pais_local_manual=g_home_country,
                    pais_vis_manual=g_away_country,
                    pais_ocr_hint=st.session_state.get("pais_ocr_detectado", ""),
                )
                st.session_state["ultimo_goal_analisis"] = {
                    "res": res_g,
                    "last_n": max(len(pares_loc), len(pares_vis)),
                    "nota": g_nota,
                    "home_fallback": g_home_input or "Local",
                    "away_fallback": g_away_input or "Visitante",
                    "umbral_poisson": float(st.session_state.get("goal_umbral_poisson", UMBRAL_POISSON_POR_DEFECTO)),
                }
        except Exception as exc:
            st.error(f"Error al calcular pronóstico: {exc}")

    ultimo_g = st.session_state.get("ultimo_goal_analisis")
    if ultimo_g:
        res_g = ultimo_g["res"]
        ht = res_g["home_team"]
        at = res_g["away_team"]
        mg = res_g["markets"]
        hs = res_g["home_stats"]
        aws = res_g["away_stats"]
        umbral_p_act = float(ultimo_g.get("umbral_poisson", UMBRAL_POISSON_POR_DEFECTO))
        pron = seleccionar_pronostico_goal(
            markets=mg,
            home_stats=hs,
            away_stats=aws,
            exigir_consistencia=True,
            mismo_equipo=res_g.get("mismo_equipo", False),
            muestra_insuficiente=res_g.get("muestra_insuficiente", False),
            umbral_racha=UMBRAL_RACHA_POR_DEFECTO,
            umbral_poisson=umbral_p_act,
        )
        ex = pron.get("resultado_exacto", {})
        top3_txt = " | ".join(
            f"`{item['marcador']}` ({item['prob']:.1f}%)" for item in ex.get("top3", [])
        )
        under_top3_txt = " | ".join(
            f"`{item['marcador']}` ({item['prob']:.1f}%)" for item in ex.get("under_top3", [])
        )

        for aviso in res_g.get("warnings", []):
            st.warning(f"⚠️ {aviso}")

        pais_loc_res = (
            g_home_country.strip() or g_pais_comun.strip() or ht.get("country") or ""
        ).strip()
        pais_vis_res = (
            g_away_country.strip() or g_pais_comun.strip() or at.get("country") or ""
        ).strip()
        etq_pais_l = pais_loc_res if pais_loc_res else "País sin confirmar"
        etq_pais_v = pais_vis_res if pais_vis_res else "País sin confirmar"

        if (
            pais_loc_res
            and pais_vis_res
            and normalizar_texto(pais_loc_res) == normalizar_texto(pais_vis_res)
        ):
            estado_pais_txt = f"✅ Ambos equipos son de **{pais_loc_res}**"
        elif pais_loc_res and pais_vis_res:
            estado_pais_txt = f"⚠️ Países distintos (`{pais_loc_res}` vs `{pais_vis_res}`)"
        else:
            estado_pais_txt = "⚠️ País pendiente de confirmar"

        st.caption(
            f"Partido: **{ht.get('name')}** ({etq_pais_l}) vs **{at.get('name')}** ({etq_pais_v}) · "
            f"{estado_pais_txt} · "
            f"Partidos analizados: `{hs['count']}` (Local) / `{aws['count']}` (Visitante) · "
            f"Media goles/equipo aplicada: `{res_g.get('base_used', 1.30)}`"
        )

        st.info(
            f"**Trayectoria en últimos partidos:** "
            f"{ht.get('name')} ({hs['count']} PJ) → **-2.5:** `{hs.get('under25_rate', 0)}%` / **+2.5:** `{hs.get('over25_rate', 0)}%` | "
            f"{at.get('name')} ({aws['count']} PJ) → **-2.5:** `{aws.get('under25_rate', 0)}%` / **+2.5:** `{aws.get('over25_rate', 0)}%`"
        )

        gm1, gm2, gm3 = st.columns(3)
        gm1.metric(
            "Goles esperados",
            f"{mg['expected_total_goals']}",
            f"λ {mg['lam_home']} / {mg['lam_away']}",
        )
        gm2.metric(
            "Prob. Over 2.5",
            f"{mg['prob_over_25']*100:.1f}%",
            f"Cuota justa: {mg['fair_over_25']}",
        )
        gm3.metric(
            "Prob. Under 2.5",
            f"{mg['prob_under_25']*100:.1f}%",
            f"Cuota justa: {mg['fair_under_25']}",
        )

        r_home_val = float(pron.get("racha_home", hs.get("under25_rate", 0.0)))
        r_away_val = float(pron.get("racha_away", aws.get("under25_rate", 0.0)))
        prob_val = float(pron.get("prob", 0.0))
        cuota_justa_val = pron.get("cuota_justa", "-")
        under_marcador_val = ex.get("under_marcador", "-")

        exacto_recomendado_txt = "-"
        if pron.get("apostar") and pron.get("pick") == "UNDER 2.5 GOLES":
            exacto_recomendado_txt = under_marcador_val
            st.success(
                f"### ✅ DOBLE CONFIRMACIÓN → {pron['pick']} | EXACTO (-2.5) → `{under_marcador_val}`\n"
                f"**Racha ≥ {UMBRAL_RACHA_POR_DEFECTO:.0f}%:** Local `{r_home_val:.1f}%` · Visitante `{r_away_val:.1f}%` | "
                f"**Poisson:** `{prob_val:.1f}%` (≥ {umbral_p_act:.0f}% · cuota justa `{cuota_justa_val}`)\n\n"
                f"**Marcadores exactos (-2.5) más probables:** {under_top3_txt}"
            )
        elif pron.get("apostar") and pron.get("pick") == "OVER 2.5 GOLES":
            st.success(
                f"### ✅ DOBLE CONFIRMACIÓN → {pron['pick']} (sin exacto; solo en -2.5 goles)\n"
                f"**Racha ≥ {UMBRAL_RACHA_POR_DEFECTO:.0f}%:** Local `{r_home_val:.1f}%` · Visitante `{r_away_val:.1f}%` | "
                f"**Poisson:** `{prob_val:.1f}%` (≥ {umbral_p_act:.0f}% · cuota justa `{cuota_justa_val}`)\n\n"
                f"*Referencia general marcadores:* {top3_txt}"
            )
        elif pron.get("senal_parcial"):
            st.warning(
                f"### ⚠️ SEÑAL PARCIAL (SOLO RACHA)\n"
                f"{pron.get('motivo', '')}\n\n"
                f"*Referencia general marcadores:* {top3_txt}"
            )
        else:
            st.warning(
                f"### ⛔ NO APOSTAR\n"
                f"{pron.get('motivo', '')}\n\n"
                f"*Referencia general marcadores:* {top3_txt}"
            )

        if st.button("Guardar en registro", key="btn_save_goal_log", width="stretch"):
            registrar_analisis_goal(
                home_name=ht.get("name") or ultimo_g["home_fallback"],
                away_name=at.get("name") or ultimo_g["away_fallback"],
                last_n=ultimo_g["last_n"],
                m=mg,
                cuota_x=0.0,
                cuota_o25=0.0,
                cuota_u25=0.0,
                pronostico_txt=pron.get("pick", "NO APOSTAR"),
                exacto_txt=exacto_recomendado_txt,
                nota=ultimo_g["nota"],
                pais_local=pais_loc_res,
                pais_visitante=pais_vis_res,
            )
            st.success("Análisis guardado en la pestaña 'Registro de análisis'.")

        with st.expander("Matriz de resultados exactos (% probabilidad)"):
            st.dataframe(mg["matrix_df"], width="stretch")

        with st.expander("Partidos usados en el cálculo"):
            st.write(
                f"**{ht.get('name')}** ({hs['count']} PJ — "
                f"GF pond.: {hs['gf_avg']:.2f} | GC pond.: {hs['ga_avg']:.2f})"
            )
            st.dataframe(pd.DataFrame(hs["matches"]), width="stretch", hide_index=True)
            st.write(
                f"**{at.get('name')}** ({aws['count']} PJ — "
                f"GF pond.: {aws['gf_avg']:.2f} | GC pond.: {aws['ga_avg']:.2f})"
            )
            st.dataframe(pd.DataFrame(aws["matches"]), width="stretch", hide_index=True)

with tab_lote:
    st.subheader("Evaluador rápido de varios partidos")
    st.caption(
        "Pega un partido por línea (`Local vs Visitante`). Evalúa Racha ≥ 60 % + Poisson ≥ 58 % y muestra exacto solo en `-2.5 goles`."
    )
    goal_key_manual = st.text_input(
        "GOAL_KEY (opcional si ya está en Secrets o entorno)",
        type="password",
        key="goal_key_manual_input",
    )
    goal_key_activa = obtener_goal_key(goal_key_manual)

    lote_country = st.text_input(
        "País común (opcional, deja vacío para búsqueda global)",
        key="lote_country_input",
    )
    lote_texto = st.text_area(
        "Partidos a revisar",
        height=150,
        placeholder="Monterrey vs Club América\nToluca vs Atlas",
        key="lote_partidos_texto",
    )

    if st.button("Analizar lote", type="primary", key="btn_analizar_lote", width="stretch"):
        pares = _parsear_lote_partidos(lote_texto)
        if not pares:
            st.warning("Introduce al menos una línea válida con formato `Local vs Visitante`.")
        elif not goal_key_activa:
            st.error("Falta GOAL_KEY en st.secrets o variables de entorno.")
        else:
            resumen_lote = []
            for loc_q, vis_q in pares:
                try:
                    r_p = run_goal_matchup_poisson(
                        home_query=loc_q,
                        away_query=vis_q,
                        country_filter=lote_country or None,
                        goal_key=goal_key_activa,
                        last_n=10,
                    )
                    sel_p = seleccionar_pronostico_goal(
                        markets=r_p["markets"],
                        home_stats=r_p["home_stats"],
                        away_stats=r_p["away_stats"],
                        exigir_consistencia=True,
                        mismo_equipo=r_p.get("mismo_equipo", False),
                        muestra_insuficiente=r_p.get("muestra_insuficiente", False),
                        umbral_racha=UMBRAL_RACHA_POR_DEFECTO,
                        umbral_poisson=UMBRAL_POISSON_POR_DEFECTO,
                    )
                    ex_p = sel_p.get("resultado_exacto", {})
                    exacto_col = (
                        ex_p.get("under_marcador", "-")
                        if (sel_p.get("apostar") and sel_p.get("pick") == "UNDER 2.5 GOLES")
                        else "-"
                    )
                    resumen_lote.append(
                        {
                            "Partido": f"{r_p['home_team'].get('name')} vs {r_p['away_team'].get('name')}",
                            "-2.5 (10 PJ)": f"{r_p['home_stats'].get('under25_rate', 0)}% / {r_p['away_stats'].get('under25_rate', 0)}%",
                            "+2.5 (10 PJ)": f"{r_p['home_stats'].get('over25_rate', 0)}% / {r_p['away_stats'].get('over25_rate', 0)}%",
                            "Poisson": f"{sel_p.get('prob_poisson', 0.0):.1f}%",
                            "Decisión": "✅ APOSTAR" if sel_p.get("apostar") else ("⚠️ Parcial" if sel_p.get("senal_parcial") else "⛔ NO"),
                            "Pick": sel_p.get("pick", "NO APOSTAR"),
                            "Exacto (-2.5)": exacto_col,
                        }
                    )
                except Exception as exc_l:
                    resumen_lote.append(
                        {
                            "Partido": f"{loc_q} vs {vis_q}",
                            "-2.5 (10 PJ)": "-",
                            "+2.5 (10 PJ)": "-",
                            "Poisson": "-",
                            "Decisión": "⚠️ Error",
                            "Pick": str(exc_l),
                            "Exacto (-2.5)": "-",
                        }
                    )
            st.dataframe(pd.DataFrame(resumen_lote), width="stretch", hide_index=True)

with tab_detector:
    st.subheader("1. Captura de partido (opcional)")
    archivo = st.file_uploader(
        "Sube una captura del partido para sugerir los equipos",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"detector_ocr_uploader_{reset_id}",
    )

    with st.expander("Ajustes de API-Football y OCR"):
        api_key_input = st.text_input(
            "API-Football Key (opcional si ya está en st.secrets['API_FOOTBALL_KEY'])",
            type="password",
        )
        auto_fetch = st.checkbox(
            "Buscar promedios automáticamente al subir una captura nueva", value=True
        )
        psm = st.selectbox(
            "Modo de segmentación OCR (PSM)", options=[11, 6, 4, 3], index=0
        )

    texto_ocr = ""
    local_sugerido = ""
    visitante_sugerido = ""

    if archivo is not None:
        img_bytes = archivo.getvalue()
        imagen_original = Image.open(BytesIO(img_bytes))
        st.image(
            imagen_original,
            caption=f"Captura cargada ({imagen_original.width}x{imagen_original.height} px)",
            width="stretch",
        )

        if st.button("Reescanear captura"):
            st.cache_data.clear()

        try:
            texto_ocr = ejecutar_ocr_bytes(img_bytes, psm=psm)
            local_sugerido, visitante_sugerido = sugerir_equipos_candidatos(texto_ocr)
            pais_det = detectar_pais_en_ocr(texto_ocr)
            if local_sugerido and not st.session_state.get("det_pais_local_input", "").strip():
                st.session_state["det_pais_local_input"] = (
                    consultar_pais_equipo(local_sugerido) or pais_det
                )
            if visitante_sugerido and not st.session_state.get("det_pais_vis_input", "").strip():
                st.session_state["det_pais_vis_input"] = (
                    consultar_pais_equipo(visitante_sugerido) or pais_det
                )
        except Exception as exc:
            st.error(f"Error al ejecutar OCR: {exc}")

        with st.expander("Ver texto detectado automáticamente en la captura"):
            st.text(texto_ocr if texto_ocr.strip() else "No se detectó texto.")

    st.subheader("2. Partido y país de los equipos")
    col1, col2 = st.columns(2)
    with col1:
        equipo_local = st.text_input(
            "Equipo Local", value=local_sugerido, key="equipo_local_input"
        )
        det_pais_local = st.text_input(
            "País Local",
            placeholder="Ej.: España, Egipto...",
            key="det_pais_local_input",
        )
    with col2:
        equipo_visitante = st.text_input(
            "Equipo Visitante", value=visitante_sugerido, key="equipo_visitante_input"
        )
        det_pais_vis = st.text_input(
            "País Visitante",
            placeholder="Ej.: España, Egipto...",
            key="det_pais_vis_input",
        )

    if st.button("💾 Guardar país de estos equipos", key="btn_save_det_countries"):
        if equipo_local.strip() and det_pais_local.strip():
            guardar_equipo_pais(equipo_local, det_pais_local)
        if equipo_visitante.strip() and det_pais_vis.strip():
            guardar_equipo_pais(equipo_visitante, det_pais_vis)
        st.success("Países guardados en memoria local.")

    api_key_activa = obtener_api_key(api_key_input)

    def actualizar_estadisticas_desde_api(loc: str, vis: str, key: str) -> None:
        st.session_state["api_info_msg"] = ""
        st.session_state["api_warn_msg"] = ""

        if not key:
            st.session_state["api_warn_msg"] = (
                "Falta la clave de API-Football (añádela en Secrets como API_FOOTBALL_KEY o en Ajustes)."
            )
            return

        if not loc.strip() or not vis.strip():
            st.session_state["api_warn_msg"] = (
                "Introduce ambos equipos antes de buscar estadísticas."
            )
            return

        try:
            team_l = buscar_equipo_api(loc, key)
            team_v = buscar_equipo_api(vis, key)

            if not team_l or not team_v:
                no_encontrado = loc if not team_l else vis
                st.session_state["api_warn_msg"] = (
                    f"No se encontró '{no_encontrado}' en API-Football. Revisa el nombre o rellena los promedios a mano."
                )
                return

            stats_l = obtener_promedios_10_api(team_l["id"], key)
            stats_v = obtener_promedios_10_api(team_v["id"], key)

            if not stats_l or not stats_v:
                st.session_state["api_warn_msg"] = (
                    "API-Football no devolvió partidos finalizados recientes para uno de los equipos."
                )
                return

            st.session_state["gf_local_10"] = float(stats_l["gf_prom"])
            st.session_state["gc_local_10"] = float(stats_l["gc_prom"])
            st.session_state["gf_vis_10"] = float(stats_v["gf_prom"])
            st.session_state["gc_vis_10"] = float(stats_v["gc_prom"])
            st.session_state["under25_local_10"] = float(stats_l["under25_rate"])
            st.session_state["under25_vis_10"] = float(stats_v["under25_rate"])

            if team_l.get("country"):
                guardar_equipo_pais(team_l["name"], team_l["country"])
            if team_v.get("country"):
                guardar_equipo_pais(team_v["name"], team_v["country"])

            h2h = obtener_h2h_api(team_l["id"], team_v["id"], key)
            if h2h and h2h["partidos"] >= 2:
                st.session_state["goles_h2h_prom"] = float(h2h["goles_prom"])
                st.session_state["usar_h2h"] = True
                h2h_txt = (
                    f" | H2H ({h2h['partidos']} partidos): {h2h['goles_prom']:.2f} goles/partido"
                )
            else:
                st.session_state["usar_h2h"] = False
                h2h_txt = " | H2H sin datos suficientes"

            st.session_state["api_info_msg"] = (
                f"Datos cargados: **{team_l['name']}** ({stats_l['partidos']} PJ: "
                f"-2.5 {stats_l['under25_rate']:.1f}%, GF {stats_l['gf_prom']:.2f}, GC {stats_l['gc_prom']:.2f}) vs "
                f"**{team_v['name']}** ({stats_v['partidos']} PJ: "
                f"-2.5 {stats_v['under25_rate']:.1f}%, GF {stats_v['gf_prom']:.2f}, GC {stats_v['gc_prom']:.2f}){h2h_txt}"
            )
        except Exception as exc:
            st.session_state["api_warn_msg"] = f"Error al consultar API-Football: {exc}"

    if (
        archivo is not None
        and auto_fetch
        and api_key_activa
        and equipo_local.strip()
        and equipo_visitante.strip()
    ):
        par_id = f"{archivo.file_id}_{equipo_local.strip()}_{equipo_visitante.strip()}"
        if st.session_state.get("ultimo_auto_fetch") != par_id:
            with st.spinner("Consultando últimos 10 partidos en API-Football..."):
                actualizar_estadisticas_desde_api(
                    equipo_local, equipo_visitante, api_key_activa
                )
            st.session_state["ultimo_auto_fetch"] = par_id

    if st.button("🔄 Buscar promedios reales en API-Football"):
        with st.spinner("Consultando últimos 10 partidos y H2H en API-Football..."):
            actualizar_estadisticas_desde_api(equipo_local, equipo_visitante, api_key_activa)

    if st.session_state["api_info_msg"]:
        st.success(st.session_state["api_info_msg"])
    if st.session_state["api_warn_msg"]:
        st.warning(st.session_state["api_warn_msg"])

    st.subheader("3. Trayectoria y promedios (últimos 10 partidos)")
    r_col1, r_col2 = st.columns(2)
    with r_col1:
        under25_local_10 = st.number_input(
            "% -2.5 goles Local (últimos 10)",
            min_value=0.0,
            max_value=100.0,
            step=5.0,
            key="under25_local_10",
        )
    with r_col2:
        under25_vis_10 = st.number_input(
            "% -2.5 goles Visitante (últimos 10)",
            min_value=0.0,
            max_value=100.0,
            step=5.0,
            key="under25_vis_10",
        )

    m1, m2 = st.columns(2)
    with m1:
        gf_local_10 = st.number_input(
            "Goles a favor Local (prom. 10)",
            min_value=0.0,
            max_value=6.0,
            step=0.05,
            key="gf_local_10",
        )
        gc_local_10 = st.number_input(
            "Goles en contra Local (prom. 10)",
            min_value=0.0,
            max_value=6.0,
            step=0.05,
            key="gc_local_10",
        )
    with m2:
        gf_vis_10 = st.number_input(
            "Goles a favor Visitante (prom. 10)",
            min_value=0.0,
            max_value=6.0,
            step=0.05,
            key="gf_vis_10",
        )
        gc_vis_10 = st.number_input(
            "Goles en contra Visitante (prom. 10)",
            min_value=0.0,
            max_value=6.0,
            step=0.05,
            key="gc_vis_10",
        )

    usar_h2h = st.checkbox("Incluir promedio de goles en H2H", key="usar_h2h")
    goles_h2h_prom = None
    if usar_h2h:
        goles_h2h_prom = st.number_input(
            "Promedio goles totales H2H",
            min_value=0.0,
            max_value=8.0,
            step=0.10,
            key="goles_h2h_prom",
        )

    xg_l, xg_v = calcular_xg_moderado(
        gf_local_10=gf_local_10,
        gc_local_10=gc_local_10,
        gf_vis_10=gf_vis_10,
        gc_vis_10=gc_vis_10,
        goles_h2h_prom=goles_h2h_prom,
    )

    resultado_actual = evaluar_entrada_25(
        xg_local=xg_l,
        xg_visitante=xg_v,
        under25_rate_local=under25_local_10,
        under25_rate_vis=under25_vis_10,
        over25_rate_local=round(100.0 - float(under25_local_10), 1),
        over25_rate_vis=round(100.0 - float(under25_vis_10), 1),
        umbral_racha=UMBRAL_RACHA_POR_DEFECTO,
        umbral_poisson=UMBRAL_POISSON_POR_DEFECTO,
    )

    p_l_lbl = f" ({det_pais_local.strip()})" if det_pais_local.strip() else ""
    p_v_lbl = f" ({det_pais_vis.strip()})" if det_pais_vis.strip() else ""
    partido_label = f"{equipo_local or 'Local'}{p_l_lbl} vs {equipo_visitante or 'Visitante'}{p_v_lbl}"

    st.divider()
    st.subheader("4. Análisis del modelo")
    if st.button("Calcular recomendación", type="primary"):
        renderizar_resultado(resultado_actual, partido_label)

with tab_registro:
    st.subheader("Partidos evaluados en esta sesión")
    log_data = st.session_state["analisis_log"]

    if not log_data:
        st.info(
            "Todavía no has guardado ningún análisis. Calcula uno en 'Análisis Poisson' y pulsa 'Guardar en registro'."
        )
    else:
        df_log = pd.DataFrame(log_data)
        st.dataframe(df_log, width="stretch")

        col_d1, col_d2 = st.columns([1, 1])
        csv_bytes = df_log.to_csv(index=False).encode("utf-8")
        col_d1.download_button(
            "Descargar CSV",
            data=csv_bytes,
            file_name="analisis_poisson_winamax.csv",
            mime="text/csv",
        )
        if col_d2.button("Limpiar tabla"):
            st.session_state["analisis_log"] = []
            st.rerun()
