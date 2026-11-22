import math
import os
import re
import unicodedata
from io import BytesIO

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

QUICK_PRESETS_GOAL = {
    "Walter Ferretti vs Sport Sébaco": ("Walter Ferretti", "Sport Sébaco", "Nicaragua"),
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
    "ALINEACIONES",
    "ESTAD",
    "ESTADIS",
    "DIRECTO",
    "PREPARTIDO",
    "PROXIMO GOL",
    "MAS DE/MENOS DE",
    "AMBOS",
    "FLASHSCORE",
    "PARTIDO",
    "RESUMEN",
    "ESTADISTICAS",
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
    "HANDICAP ASIATICO",
    "HACER UNA APUESTA",
    "CASA DE APUESTAS",
    "DOBLE OPORTUNID",
    "RESULTADO EXACTO",
    "MAS SELECCIONES",
    "MÁS SELECCIONES",
}


def normalizar_texto(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


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

    gf_total = 0
    gc_total = 0
    validos = 0

    for f in partidos_ordenados:
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        g_home = goals.get("home")
        g_away = goals.get("away")

        if g_home is None or g_away is None:
            continue

        if home_id == team_id:
            gf_total += int(g_home)
            gc_total += int(g_away)
            validos += 1
        elif away_id == team_id:
            gf_total += int(g_away)
            gc_total += int(g_home)
            validos += 1

    if validos == 0:
        return None

    return {
        "partidos": validos,
        "gf_prom": round(gf_total / validos, 2),
        "gc_prom": round(gc_total / validos, 2),
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
            total_goles += int(g_home) + int(g_away)
            validos += 1

    if validos == 0:
        return None

    return {
        "partidos": validos,
        "goles_prom": round(total_goles / validos, 2),
    }


# --- FUNCIONES GOAL API + POISSON ---
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


def goal_summarize_team_goals(matches: list[dict], team_id: str, last_n: int = 10) -> dict:
    subset = matches[:last_n]
    if not subset:
        return {"count": 0, "gf_avg": 0.0, "ga_avg": 0.0, "total_avg": 0.0, "matches": []}

    gf_total = 0
    ga_total = 0
    rows = []

    for m in subset:
        hg = int(m["homeTeamFtScore"])
        ag = int(m["awayTeamFtScore"])
        is_home = m.get("homeTeamId") == team_id
        gf = hg if is_home else ag
        ga = ag if is_home else hg

        gf_total += gf
        ga_total += ga
        rows.append(
            {
                "Fecha": m.get("matchDate"),
                "Competición": m.get("leagueName"),
                "Local": m.get("homeTeamName"),
                "Visitante": m.get("awayTeamName"),
                "Marcador": f"{hg} - {ag}",
                "GF": gf,
                "GC": ga,
                "Total": hg + ag,
            }
        )

    n = len(subset)
    return {
        "count": n,
        "gf_avg": gf_total / n,
        "ga_avg": ga_total / n,
        "total_avg": (gf_total + ga_total) / n,
        "matches": rows,
    }


def poisson_pmf(k: int, lam: float) -> float:
    return (math.exp(-lam) * (lam**k)) / math.factorial(k)


def calculate_poisson_markets(
    lam_home: float,
    lam_away: float,
    max_goals: int = 6,
    winamax_over25: float | None = None,
    winamax_draw: float | None = None,
) -> dict:
    prob_home = 0.0
    prob_draw = 0.0
    prob_away = 0.0
    prob_over_25 = 0.0

    matrix = []
    for h in range(max_goals + 1):
        row = []
        p_h = poisson_pmf(h, lam_home)
        for a in range(max_goals + 1):
            p_a = poisson_pmf(a, lam_away)
            p_cell = p_h * p_a
            row.append(p_cell)

            if h > a:
                prob_home += p_cell
            elif h == a:
                prob_draw += p_cell
            else:
                prob_away += p_cell

            if (h + a) >= 3:
                prob_over_25 += p_cell
        matrix.append(row)

    prob_under_25 = max(0.0, 1.0 - prob_over_25)

    def fair_odd(p: float) -> float | None:
        return round(1.0 / p, 2) if p > 0 else None

    def edge(p: float, odd: float | None) -> float | None:
        if not odd or odd <= 1.0:
            return None
        return round((p * odd) - 1.0, 4)

    return {
        "lam_home": round(lam_home, 3),
        "lam_away": round(lam_away, 3),
        "expected_total_goals": round(lam_home + lam_away, 3),
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
        "matrix_df": pd.DataFrame(
            [[round(val * 100, 1) for val in r] for r in matrix],
            index=[f"Local {i}" for i in range(max_goals + 1)],
            columns=[f"Visit {j}" for j in range(max_goals + 1)],
        ),
    }


def run_goal_matchup_poisson(
    home_query: str,
    away_query: str,
    country_filter: str | None,
    goal_key: str,
    last_n: int = 10,
    league_avg_per_side: float = 1.35,
    winamax_over25: float | None = None,
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

    home_stats = goal_summarize_team_goals(
        goal_fetch_team_results(home_id, goal_key, limit=50), home_id, last_n=last_n
    )
    away_stats = goal_summarize_team_goals(
        goal_fetch_team_results(away_id, goal_key, limit=50), away_id, last_n=last_n
    )

    base = league_avg_per_side if league_avg_per_side > 0 else 1.35
    home_att = (home_stats["gf_avg"] / base) if home_stats["gf_avg"] > 0 else 1.0
    home_def = (home_stats["ga_avg"] / base) if home_stats["ga_avg"] > 0 else 1.0

    away_att = (away_stats["gf_avg"] / base) if away_stats["gf_avg"] > 0 else 1.0
    away_def = (away_stats["ga_avg"] / base) if away_stats["ga_avg"] > 0 else 1.0

    lam_home = home_att * away_def * base
    lam_away = away_att * home_def * base

    markets = calculate_poisson_markets(
        lam_home=lam_home,
        lam_away=lam_away,
        winamax_over25=winamax_over25,
        winamax_draw=winamax_draw,
    )

    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_stats": home_stats,
        "away_stats": away_stats,
        "markets": markets,
    }


def registrar_analisis_goal(
    home_name: str,
    away_name: str,
    last_n: int,
    m: dict,
    cuota_x: float,
    cuota_o25: float,
    nota: str = "",
) -> None:
    st.session_state["analisis_log"].append(
        {
            "Local": home_name,
            "Visitante": away_name,
            "Partidos (N)": last_n,
            "Goles esp.": m["expected_total_goals"],
            "Prob. X (%)": round(m["prob_x"] * 100, 1),
            "Cuota justa X": m["fair_x"],
            "Cuota Winamax X": cuota_x,
            "Edge X (%)": round((m["edge_draw"] or 0) * 100, 2),
            "Prob. O2.5 (%)": round(m["prob_over_25"] * 100, 1),
            "Cuota justa O2.5": m["fair_over_25"],
            "Cuota Winamax O2.5": cuota_o25,
            "Edge O2.5 (%)": round((m["edge_over_25"] or 0) * 100, 2),
            "Nota": nota.strip(),
        }
    )


def preparar_imagen_ocr(imagen: Image.Image) -> Image.Image:
    """Mejora escala y contraste para facilitar la lectura de nombres de equipos."""
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
def ejecutar_ocr_bytes(img_bytes: bytes, psm: int = 6) -> str:
    """Ejecuta Tesseract OCR sobre los bytes de la imagen."""
    imagen = Image.open(BytesIO(img_bytes))
    procesada = preparar_imagen_ocr(imagen)
    config = f"--oem 3 --psm {psm}"
    return pytesseract.image_to_string(procesada, lang="spa+eng", config=config)


def _es_token_basura_ocr(token: str) -> bool:
    """Detecta tokens cortos deformados o repeticiones sin sentido."""
    limpio = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", token)
    if len(limpio) < 2:
        return True
    if len(set(limpio.lower())) == 1:
        return True
    if len(limpio) <= 6 and re.search(r"[A-Z]{2,}[a-z]+[A-Z]|[a-z]+[A-Z]{2,}", limpio):
        return True
    return False


def limpiar_lineas_ocr(texto_ocr: str) -> list[str]:
    """Limpia el texto devuelto por Tesseract y descarta ruido de interfaz."""
    lineas_limpias = []
    for linea in texto_ocr.splitlines():
        limpia = linea.strip()
        if not limpia:
            continue

        limpia = re.sub(r"\bSTREAM\b", " ", limpia, flags=re.IGNORECASE)
        limpia = re.sub(r"\s+", " ", limpia).strip(" |")
        if not limpia:
            continue

        if "_" in limpia or "=" in limpia:
            continue

        if re.fullmatch(r"\d{1,2}[:.\-]\d{1,2}(?:[:.\-]\d{2,4})?", limpia):
            continue

        if limpia.startswith("@") or re.fullmatch(r"1\s+[xX]{1,2}\s+2", limpia):
            continue

        mayus = limpia.upper()
        if any(palabra in mayus for palabra in PALABRAS_RUIDO):
            continue

        tokens = limpia.split()
        if tokens and all(tok.isupper() and len(tok) <= 4 for tok in tokens):
            continue

        if tokens and all(_es_token_basura_ocr(tok) for tok in tokens):
            continue

        letras = sum(c.isalpha() for c in limpia)
        if letras < 2:
            continue

        lineas_limpias.append(limpia)

    return lineas_limpias


def _extraer_equipos_de_linea(linea: str) -> list[str]:
    partes = re.split(
        r"\s*(?:>|\bvs\.?\b|\s-\s|\d{1,2}:\d{2})\s*", linea, flags=re.IGNORECASE
    )
    encontrados: list[str] = []
    for parte in partes:
        limpia_parte = re.sub(r"\b\d+\b", "", parte).strip(" -|>/\\")
        limpia_parte = re.sub(r"\s+", " ", limpia_parte).strip()
        if limpia_parte.isupper() and len(limpia_parte) <= 4:
            continue
        if _es_token_basura_ocr(limpia_parte):
            continue
        if 2 <= len(limpia_parte) <= 35 and limpia_parte not in encontrados:
            encontrados.append(limpia_parte)
    return encontrados


def sugerir_equipos_candidatos(texto_ocr: str) -> tuple[str, str]:
    """Sugiere equipo local y visitante priorizando líneas con cruce, marcador o 'vs'."""
    lineas = limpiar_lineas_ocr(texto_ocr)
    candidatos_cruce: list[str] = []
    equipos: list[str] = []

    for linea in lineas:
        if re.search(r"[|{}~<>\\]", linea) and ">" not in linea:
            continue

        es_cruce = bool(
            ">" in linea
            or re.search(r"\bvs\.?\b", linea, flags=re.IGNORECASE)
            or re.search(r"\b\d{1,2}:\d{2}\b", linea)
        )

        if not es_cruce and re.search(r"\d", linea):
            continue

        partes_linea = _extraer_equipos_de_linea(linea)
        if es_cruce and len(partes_linea) >= 2:
            for eq in partes_linea:
                if eq not in candidatos_cruce:
                    candidatos_cruce.append(eq)

        for eq in partes_linea:
            if eq not in equipos:
                equipos.append(eq)

    if not candidatos_cruce and len(equipos) == 1:
        palabras = equipos[0].split()
        if len(palabras) == 2 and all(len(p) >= 3 and p[0].isupper() for p in palabras):
            return palabras[0], palabras[1]

    fuente = candidatos_cruce if len(candidatos_cruce) >= 2 else equipos
    local = fuente[0] if len(fuente) >= 1 else ""
    visitante = fuente[1] if len(fuente) >= 2 else ""
    return local, visitante


def calcular_xg_moderado(
    gf_local_10: float,
    gc_local_10: float,
    gf_vis_10: float,
    gc_vis_10: float,
    goles_h2h_prom: float | None = None,
    peso_h2h: float = 0.15,
) -> tuple[float, float]:
    """
    Calcula goles esperados moderando extremos con medias de 10 partidos
    y un peso ligero opcional de enfrentamientos directos (H2H).
    """
    gf_l = min(max(gf_local_10, 0.15), 4.2)
    gc_l = min(max(gc_local_10, 0.15), 4.2)
    gf_v = min(max(gf_vis_10, 0.15), 4.2)
    gc_v = min(max(gc_vis_10, 0.15), 4.2)

    xg_local = (gf_l + gc_v) / 2.0
    xg_visitante = (gf_v + gc_l) / 2.0

    if goles_h2h_prom is not None and goles_h2h_prom > 0:
        h2h_mod = min(max(goles_h2h_prom, 0.4), 5.5)
        total_base = xg_local + xg_visitante
        total_ajustado = ((1.0 - peso_h2h) * total_base) + (peso_h2h * h2h_mod)
        if total_base > 0:
            factor = total_ajustado / total_base
            xg_local *= factor
            xg_visitante *= factor

    return round(max(0.15, xg_local), 2), round(max(0.15, xg_visitante), 2)


def probs_over_under_25(xg_local: float, xg_visitante: float) -> dict[str, float]:
    """Calcula P(-2.5) y P(+2.5) sumando probabilidades de goles totales 0, 1 y 2."""
    total_xg = max(0.05, xg_local + xg_visitante)
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
    min_edge: float = 0.05,
    min_cuota_over: float = 1.45,
    min_cuota_under: float = 1.45,
) -> dict:
    """Evalúa +2.5 y -2.5 goles exigiendo ventaja mínima sobre la cuota."""
    probs = probs_over_under_25(xg_local, xg_visitante)
    p_over = probs["p_over_25"]
    p_under = probs["p_under_25"]

    opciones = []
    desglose = []

    if cuota_over_25 and cuota_over_25 > 1.0:
        imp_over = 1.0 / cuota_over_25
        edge_over = p_over - imp_over
        ev_over = (p_over * cuota_over_25) - 1.0
        pasa_over = edge_over >= min_edge and cuota_over_25 >= min_cuota_over
        desglose.append(
            {
                "Mercado": "+2.5 goles",
                "Cuota": f"{cuota_over_25:.2f}",
                "Prob. modelo": f"{p_over * 100:.1f}%",
                "Prob. implícita": f"{imp_over * 100:.1f}%",
                "Ventaja": f"{edge_over * 100:+.1f}%",
                "Filtro": "OK" if pasa_over else "No",
            }
        )
        if pasa_over:
            opciones.append(
                {
                    "mercado": "+2.5 goles",
                    "cuota": cuota_over_25,
                    "prob_modelo": round(p_over * 100, 1),
                    "prob_implicita": round(imp_over * 100, 1),
                    "edge": round(edge_over * 100, 1),
                    "ev": round(ev_over, 3),
                }
            )

    if cuota_under_25 and cuota_under_25 > 1.0:
        imp_under = 1.0 / cuota_under_25
        edge_under = p_under - imp_under
        ev_under = (p_under * cuota_under_25) - 1.0
        pasa_under = edge_under >= min_edge and cuota_under_25 >= min_cuota_under
        desglose.append(
            {
                "Mercado": "-2.5 goles",
                "Cuota": f"{cuota_under_25:.2f}",
                "Prob. modelo": f"{p_under * 100:.1f}%",
                "Prob. implícita": f"{imp_under * 100:.1f}%",
                "Ventaja": f"{edge_under * 100:+.1f}%",
                "Filtro": "OK" if pasa_under else "No",
            }
        )
        if pasa_under:
            opciones.append(
                {
                    "mercado": "-2.5 goles",
                    "cuota": cuota_under_25,
                    "prob_modelo": round(p_under * 100, 1),
                    "prob_implicita": round(imp_under * 100, 1),
                    "edge": round(edge_under * 100, 1),
                    "ev": round(ev_under, 3),
                }
            )

    if not opciones:
        return {
            "decision": "NO APOSTAR",
            "motivo": "Ningún mercado supera el umbral mínimo de ventaja o cuota.",
            "xg_total": probs["xg_total"],
            "p_over_25": round(p_over * 100, 1),
            "p_under_25": round(p_under * 100, 1),
            "desglose": desglose,
        }

    mejor = max(opciones, key=lambda x: x["ev"])
    return {
        "decision": "APOSTAR",
        "mercado": mejor["mercado"],
        "cuota": mejor["cuota"],
        "prob_modelo": mejor["prob_modelo"],
        "prob_implicita": mejor["prob_implicita"],
        "edge": mejor["edge"],
        "ev": mejor["ev"],
        "xg_total": probs["xg_total"],
        "p_over_25": round(p_over * 100, 1),
        "p_under_25": round(p_under * 100, 1),
        "desglose": desglose,
    }


def renderizar_resultado(resultado: dict, partido_label: str) -> None:
    """Muestra el veredicto directo (+2.5 goles, -2.5 goles o NO APOSTAR) y métricas."""
    st.markdown(f"**Partido:** {partido_label}")

    r1, r2, r3 = st.columns(3)
    r1.metric("Goles esperados (xG)", f"{resultado['xg_total']:.2f}")
    r2.metric("Prob. +2.5 goles", f"{resultado['p_over_25']:.1f}%")
    r3.metric("Prob. -2.5 goles", f"{resultado['p_under_25']:.1f}%")

    if resultado["decision"] == "APOSTAR":
        st.success(
            f"### ✅ APOSTAR → {resultado['mercado'].upper()}\n"
            f"**Cuota:** `{resultado['cuota']:.2f}` | "
            f"**Ventaja:** `+{resultado['edge']:.1f}%` | "
            f"**EV:** `{resultado['ev']:+.3f}`"
        )
    else:
        st.warning(f"### ⛔ NO APOSTAR\n{resultado['motivo']}")

    if resultado.get("desglose"):
        st.dataframe(resultado["desglose"], width="stretch", hide_index=True)


for clave, valor_ini in {
    "gf_local_10": 1.40,
    "gc_local_10": 1.10,
    "gf_vis_10": 1.20,
    "gc_vis_10": 1.20,
    "goles_h2h_prom": 2.40,
    "usar_h2h": False,
    "cuota_over_25_manual": 1.55,
    "cuota_under_25_manual": 2.35,
    "api_info_msg": "",
    "api_warn_msg": "",
    "analisis_log": [],
    "ultimo_goal_analisis": None,
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor_ini


st.title("⚽ Detector de Goles (+2.5 / -2.5)")
st.caption("Equipos por captura, estadísticas reales vía API-Football (v3) y GOAL API + Poisson.")

tab_poisson, tab_detector, tab_registro = st.tabs(
    ["Análisis Poisson", "Detector (+2.5 / -2.5)", "Registro de análisis"]
)

with tab_poisson:
    st.subheader("Modelo Poisson — GOAL API")
    goal_key_manual = st.text_input(
        "GOAL_KEY (opcional si ya está en Secrets o entorno)",
        type="password",
        key="goal_key_manual_input",
    )
    goal_key_activa = obtener_goal_key(goal_key_manual)

    preset = st.selectbox(
        "Acceso rápido",
        options=["Personalizado"] + list(QUICK_PRESETS_GOAL.keys()),
        index=1,
        key="goal_preset_select",
    )
    def_home, def_away, def_country = QUICK_PRESETS_GOAL.get(preset, ("", "", ""))

    gc1, gc2, gc3 = st.columns([2, 2, 1.5])
    g_home_input = gc1.text_input("Equipo Local", value=def_home, key="goal_home_input")
    g_away_input = gc2.text_input("Equipo Visitante", value=def_away, key="goal_away_input")
    g_country_input = gc3.text_input("País (opcional)", value=def_country, key="goal_country_input")

    gp1, gp2, gp3, gp4 = st.columns(4)
    g_last_n = gp1.slider("Últimos partidos", min_value=5, max_value=20, value=10, key="goal_last_n")
    g_league_avg = gp2.number_input(
        "Media goles/equipo", min_value=0.6, max_value=2.5, value=1.35, step=0.05, key="goal_league_avg"
    )
    g_cuota_x = gp3.number_input(
        "Cuota Empate (X) Winamax", min_value=1.01, max_value=15.0, value=3.20, step=0.05, key="goal_cuota_x"
    )
    g_cuota_o25 = gp4.number_input(
        "Cuota Over 2.5 Winamax", min_value=1.01, max_value=10.0, value=1.95, step=0.05, key="goal_cuota_o25"
    )

    g_nota = st.text_input("Nota rápida (opcional)", key="goal_nota_input")

    if st.button("Calcular probabilidades", type="primary", key="btn_calc_goal_poisson"):
        try:
            res_g = run_goal_matchup_poisson(
                home_query=g_home_input,
                away_query=g_away_input,
                country_filter=g_country_input or None,
                goal_key=goal_key_activa,
                last_n=g_last_n,
                league_avg_per_side=g_league_avg,
                winamax_over25=g_cuota_o25,
                winamax_draw=g_cuota_x,
            )
            st.session_state["ultimo_goal_analisis"] = {
                "res": res_g,
                "last_n": g_last_n,
                "cuota_x": g_cuota_x,
                "cuota_o25": g_cuota_o25,
                "nota": g_nota,
                "home_fallback": g_home_input,
                "away_fallback": g_away_input,
            }
        except Exception as exc:
            st.error(f"Error al calcular en GOAL API: {exc}")

    ultimo_g = st.session_state.get("ultimo_goal_analisis")
    if ultimo_g:
        res_g = ultimo_g["res"]
        ht = res_g["home_team"]
        at = res_g["away_team"]
        mg = res_g["markets"]

        st.caption(
            f"Equipos detectados: **{ht.get('name')}** (`{ht.get('country') or 'N/D'}`) "
            f"vs **{at.get('name')}** (`{at.get('country') or 'N/D'}`)"
        )

        gm1, gm2, gm3, gm4 = st.columns(4)
        gm1.metric("Goles esperados", f"{mg['expected_total_goals']}", f"λ {mg['lam_home']} / {mg['lam_away']}")
        gm2.metric("Prob. Empate (X)", f"{mg['prob_x']*100:.1f}%", f"Cuota justa: {mg['fair_x']}")
        gm3.metric("Prob. Over 2.5", f"{mg['prob_over_25']*100:.1f}%", f"Cuota justa: {mg['fair_over_25']}")
        gm4.metric(
            "Edge Over 2.5 / X",
            f"{(mg['edge_over_25'] or 0)*100:+.1f}%",
            f"X: {(mg['edge_draw'] or 0)*100:+.1f}%",
        )

        if st.button("Guardar en registro", key="btn_save_goal_log"):
            registrar_analisis_goal(
                home_name=ht.get("name") or ultimo_g["home_fallback"],
                away_name=at.get("name") or ultimo_g["away_fallback"],
                last_n=ultimo_g["last_n"],
                m=mg,
                cuota_x=ultimo_g["cuota_x"],
                cuota_o25=ultimo_g["cuota_o25"],
                nota=ultimo_g["nota"],
            )
            st.success("Análisis guardado en la pestaña 'Registro de análisis'.")

        with st.expander("Matriz de resultados exactos (% probabilidad)"):
            st.dataframe(mg["matrix_df"], width="stretch")

        with st.expander("Últimos partidos usados en el cálculo"):
            st.write(
                f"**{ht.get('name')}** "
                f"(GF media: {res_g['home_stats']['gf_avg']:.2f} | GC media: {res_g['home_stats']['ga_avg']:.2f})"
            )
            st.dataframe(pd.DataFrame(res_g["home_stats"]["matches"]), width="stretch")
            st.write(
                f"**{at.get('name')}** "
                f"(GF media: {res_g['away_stats']['gf_avg']:.2f} | GC media: {res_g['away_stats']['ga_avg']:.2f})"
            )
            st.dataframe(pd.DataFrame(res_g["away_stats"]["matches"]), width="stretch")

with tab_detector:
    st.subheader("1. Captura de partido (opcional)")
    archivo = st.file_uploader(
        "Sube una captura del partido para sugerir los equipos",
        type=["png", "jpg", "jpeg", "webp"],
    )

    with st.expander("Ajustes de API-Football, OCR y filtros"):
        api_key_input = st.text_input(
            "API-Football Key (opcional si ya está en st.secrets['API_FOOTBALL_KEY'])",
            type="password",
        )
        auto_fetch = st.checkbox(
            "Buscar promedios automáticamente al subir una captura nueva", value=True
        )
        psm = st.selectbox("Modo de segmentación OCR (PSM)", options=[6, 4, 11, 3], index=0)
        min_edge_pct = st.slider(
            "Ventaja mínima sobre cuota (%)", min_value=1.0, max_value=25.0, value=5.0, step=0.5
        )
        min_cuota_over = st.slider(
            "Cuota mínima en +2.5 goles", min_value=1.30, max_value=2.50, value=1.45, step=0.05
        )
        min_cuota_under = st.slider(
            "Cuota mínima en -2.5 goles", min_value=1.30, max_value=3.00, value=1.45, step=0.05
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
        except Exception as exc:
            st.error(f"Error al ejecutar OCR: {exc}")

        with st.expander("Ver texto detectado automáticamente en la captura"):
            st.text(texto_ocr if texto_ocr.strip() else "No se detectó texto.")

    st.subheader("2. Partido y cuotas manuales de Winamax")
    col1, col2 = st.columns(2)
    with col1:
        equipo_local = st.text_input("Equipo Local", value=local_sugerido, key="equipo_local_input")
    with col2:
        equipo_visitante = st.text_input(
            "Equipo Visitante", value=visitante_sugerido, key="equipo_visitante_input"
        )

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
            st.session_state["api_warn_msg"] = "Introduce ambos equipos antes de buscar estadísticas."
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

            h2h = obtener_h2h_api(team_l["id"], team_v["id"], key)
            if h2h and h2h["partidos"] >= 2:
                st.session_state["goles_h2h_prom"] = float(h2h["goles_prom"])
                st.session_state["usar_h2h"] = True
                h2h_txt = f" | H2H ({h2h['partidos']} partidos): {h2h['goles_prom']:.2f} goles/partido"
            else:
                st.session_state["usar_h2h"] = False
                h2h_txt = " | H2H sin datos suficientes"

            st.session_state["api_info_msg"] = (
                f"Datos cargados: **{team_l['name']}** ({stats_l['partidos']} PJ: "
                f"GF {stats_l['gf_prom']:.2f}, GC {stats_l['gc_prom']:.2f}) vs "
                f"**{team_v['name']}** ({stats_v['partidos']} PJ: "
                f"GF {stats_v['gf_prom']:.2f}, GC {stats_v['gc_prom']:.2f}){h2h_txt}"
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
                actualizar_estadisticas_desde_api(equipo_local, equipo_visitante, api_key_activa)
            st.session_state["ultimo_auto_fetch"] = par_id

    if st.button("🔄 Buscar promedios reales en API-Football"):
        with st.spinner("Consultando últimos 10 partidos y H2H en API-Football..."):
            actualizar_estadisticas_desde_api(equipo_local, equipo_visitante, api_key_activa)

    if st.session_state["api_info_msg"]:
        st.success(st.session_state["api_info_msg"])
    if st.session_state["api_warn_msg"]:
        st.warning(st.session_state["api_warn_msg"])

    c_over, c_under = st.columns(2)
    with c_over:
        usar_over = st.checkbox("Evaluar +2.5 goles", value=True)
        cuota_over_25 = st.number_input(
            "Cuota +2.5 (Winamax)",
            min_value=1.01,
            max_value=20.00,
            step=0.01,
            format="%.2f",
            disabled=not usar_over,
            key="cuota_over_25_manual",
        )
    with c_under:
        usar_under = st.checkbox("Evaluar -2.5 goles", value=True)
        cuota_under_25 = st.number_input(
            "Cuota -2.5 (Winamax)",
            min_value=1.01,
            max_value=20.00,
            step=0.01,
            format="%.2f",
            disabled=not usar_under,
            key="cuota_under_25_manual",
        )

    st.subheader("3. Promedios (últimos 10 partidos y H2H)")
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
        cuota_over_25=cuota_over_25 if usar_over else None,
        cuota_under_25=cuota_under_25 if usar_under else None,
        min_edge=min_edge_pct / 100.0,
        min_cuota_over=min_cuota_over,
        min_cuota_under=min_cuota_under,
    )

    partido_label = f"{equipo_local or 'Local'} vs {equipo_visitante or 'Visitante'}"

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
