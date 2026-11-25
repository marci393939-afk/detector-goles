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
    "Personalizado": ("", "", ""),
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

    for idx, f in enumerate(partidos_ordenados):
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        g_home = goals.get("home")
        g_away = goals.get("away")

        if g_home is None or g_away is None:
            continue

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

    return {
        "partidos": validos,
        "gf_prom": round(gf_total / peso_total, 2),
        "gc_prom": round(gc_total / peso_total, 2),
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


def goal_summarize_team_goals(
    matches: list[dict],
    team_id: str,
    last_n: int = 10,
    prefer_venue: str | None = None,
) -> dict:
    """
    Calcula medias ponderadas por recencia con recorte amplio (5 goles),
    ajuste por condición (Local/Visitante) y tasas reales de Over/Under 2.5.
    """
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
    for h in range(max_goals + 1):
        norm_row = []
        for a in range(max_goals + 1):
            p_cell = raw_matrix[h][a] / total_mass if total_mass > 0 else raw_matrix[h][a]
            norm_row.append(p_cell)
            cell_probs.append((f"{h} - {a}", p_cell))

            if h > a:
                prob_home += p_cell
            elif h == a:
                prob_draw += p_cell
            else:
                prob_away += p_cell

            if (h + a) >= 3:
                prob_over_25 += p_cell
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

    return {
        "lam_home": round(lam_home, 3),
        "lam_away": round(lam_away, 3),
        "expected_total_goals": round(lam_home + lam_away, 3),
        "exact_score": best_score,
        "exact_score_prob": round(max(0.0, best_prob) * 100, 1),
        "exact_score_fair_odd": fair_odd(max(0.0, best_prob)),
        "top_exact_scores": top_exact_scores,
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


def _consistencia_respalda(
    home_stats: dict | None,
    away_stats: dict | None,
    mercado: str,
) -> bool:
    """
    Exige que el historial reciente respalde el mercado en ambos equipos
    para evitar picks apoyados solo en un lado.
    """
    if not home_stats or not away_stats:
        return True
    if home_stats.get("count", 0) < 4 or away_stats.get("count", 0) < 4:
        return True

    if "OVER" in mercado or "+2.5" in mercado:
        h_over = home_stats.get("over25_rate", 0.0)
        a_over = away_stats.get("over25_rate", 0.0)
        return ((h_over + a_over) / 2.0) >= 45.0 and min(h_over, a_over) >= 30.0

    if "UNDER" in mercado or "-2.5" in mercado:
        h_under = home_stats.get("under25_rate", 0.0)
        a_under = away_stats.get("under25_rate", 0.0)
        return ((h_under + a_under) / 2.0) >= 45.0 and min(h_under, a_under) >= 30.0

    return True


def seleccionar_pronostico_goal(
    markets: dict,
    cuota_x: float,
    cuota_o25: float,
    cuota_u25: float,
    min_edge: float = 0.05,
    min_prob_ou: float = 0.56,
    min_prob_under: float = 0.60,
    max_cuota_ou: float = 2.60,
    solo_goles: bool = True,
    home_stats: dict | None = None,
    away_stats: dict | None = None,
    exigir_consistencia: bool = True,
    mismo_equipo: bool = False,
    muestra_insuficiente: bool = False,
) -> dict:
    """
    Evalúa +2.5 / -2.5 goles aplicando un filtro más exigente en -2.5 goles
    y bloqueando cuotas trampa, equipos repetidos o muestras cortas.
    """
    resultado_exacto = {
        "marcador": markets["exact_score"],
        "prob": markets["exact_score_prob"],
        "cuota_justa": markets["exact_score_fair_odd"],
        "top3": markets.get("top_exact_scores", []),
    }

    if mismo_equipo:
        return {
            "apostar": False,
            "pick": "NO APOSTAR",
            "motivo": "Se detectó el mismo equipo para local y visitante. Revisa los nombres o el país.",
            "resultado_exacto": resultado_exacto,
        }

    if muestra_insuficiente:
        return {
            "apostar": False,
            "pick": "NO APOSTAR",
            "motivo": "Muestra insuficiente (se requieren al menos 6 partidos finalizados por equipo).",
            "resultado_exacto": resultado_exacto,
        }

    req_over = min_prob_ou if cuota_o25 < 2.0 else max(0.48, min_prob_ou - 0.08)
    req_under = max(min_prob_under, min_prob_ou) if cuota_u25 < 2.0 else max(0.56, min_prob_under - 0.02)

    candidatos = [
        {
            "pick": "OVER 2.5 GOLES",
            "cuota": cuota_o25,
            "prob": round(markets["prob_over_25"] * 100, 1),
            "prob_raw": markets["prob_over_25"],
            "cuota_justa": markets["fair_over_25"],
            "edge": markets.get("edge_over_25"),
            "min_prob_req": req_over,
            "min_edge_req": min_edge,
            "max_cuota_req": max_cuota_ou,
        },
        {
            "pick": "UNDER 2.5 GOLES",
            "cuota": cuota_u25,
            "prob": round(markets["prob_under_25"] * 100, 1),
            "prob_raw": markets["prob_under_25"],
            "cuota_justa": markets["fair_under_25"],
            "edge": markets.get("edge_under_25"),
            "min_prob_req": req_under,
            "min_edge_req": max(min_edge, 0.05),
            "max_cuota_req": max_cuota_ou,
        },
    ]

    if not solo_goles:
        candidatos.append(
            {
                "pick": "EMPATE (X)",
                "cuota": cuota_x,
                "prob": round(markets["prob_x"] * 100, 1),
                "prob_raw": markets["prob_x"],
                "cuota_justa": markets["fair_x"],
                "edge": markets.get("edge_draw"),
                "min_prob_req": 0.28,
                "min_edge_req": min_edge,
                "max_cuota_req": 99.0,
            }
        )

    validos = []
    for c in candidatos:
        cumple_num = (
            c["edge"] is not None
            and c["edge"] >= c["min_edge_req"]
            and c["prob_raw"] >= c["min_prob_req"]
            and c["cuota"] <= c["max_cuota_req"]
        )
        cumple_hist = (
            True
            if (not exigir_consistencia or "EMPATE" in c["pick"])
            else _consistencia_respalda(home_stats, away_stats, c["pick"])
        )
        if cumple_num and cumple_hist:
            validos.append(c)

    if not validos:
        return {
            "apostar": False,
            "pick": "NO APOSTAR",
            "motivo": (
                f"No pasa el filtro de seguridad (ventaja mín. +{min_edge * 100:.1f}%, "
                f"prob. +2.5 desde {req_over * 100:.0f}% / -2.5 desde {req_under * 100:.0f}%, "
                f"cuota máx. {max_cuota_ou:.2f} y consistencia en ambos equipos)."
            ),
            "resultado_exacto": resultado_exacto,
        }

    mejor = max(validos, key=lambda c: c["edge"])
    return {"apostar": True, "resultado_exacto": resultado_exacto, **mejor}


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
    nota: str = "",
) -> None:
    st.session_state["analisis_log"].append(
        {
            "Local": home_name,
            "Visitante": away_name,
            "Pronóstico": pronostico_txt,
            "Resultado exacto": m["exact_score"],
            "Prob. exacto (%)": m["exact_score_prob"],
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
            "Prob. U2.5 (%)": round(m["prob_under_25"] * 100, 1),
            "Cuota justa U2.5": m["fair_under_25"],
            "Cuota Winamax U2.5": cuota_u25,
            "Edge U2.5 (%)": round((m["edge_under_25"] or 0) * 100, 2),
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
def ejecutar_ocr_bytes(img_bytes: bytes, psm: int = 11) -> str:
    """Ejecuta Tesseract OCR sobre los bytes de la imagen."""
    imagen = Image.open(BytesIO(img_bytes))
    procesada = preparar_imagen_ocr(imagen)
    config = f"--oem 3 --psm {psm}"
    return pytesseract.image_to_string(procesada, lang="spa+eng", config=config)


def _es_token_basura_ocr(token: str) -> bool:
    """Detecta tokens cortos deformados o repeticiones sin sentido."""
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
    """Valida que un candidato parezca un nombre de equipo y no frase de interfaz/ruido."""
    limpio = re.sub(r"\s+", " ", candidato).strip()
    if len(limpio) < 4 or len(limpio) > 30:
        return False
    if re.search(r"[:;{}\[\]~\\]", limpio):
        return False
    norm_upper = normalizar_texto(limpio).upper()
    if any(ruido in norm_upper for ruido in PALABRAS_RUIDO):
        return False
    palabras = limpio.split()
    if len(palabras) > 3:
        return False
    if len(palabras) == 1 and len(re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", palabras[0])) < 4:
        return False
    letras = sum(c.isalpha() for c in limpio)
    if letras < 4:
        return False
    minus = [normalizar_texto(p) for p in palabras]
    if set(minus).issubset(
        {"solo", "para", "nue", "fo", "ussun", "con", "del", "las", "los", "war", "alert"}
    ):
        return False
    return True


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
        if tokens and all(tok.isupper() and len(tok) <= 4 for tok in tokens):
            continue

        if tokens and all(_es_token_basura_ocr(tok) for tok in tokens):
            continue

        letras = sum(c.isalpha() for c in limpia)
        if letras < 3:
            continue

        lineas_limpias.append(limpia)

    return lineas_limpias


def _separar_dos_equipos_en_linea(texto: str) -> list[str]:
    """Divide una línea cuando contiene dos nombres de equipos pegados en horizontal."""
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
    """Sugiere equipo local y visitante válidos o devuelve vacío si el OCR no es fiable."""
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
    """
    Calcula goles esperados moderando extremos con medias de 10 partidos
    y un peso ligero opcional de enfrentamientos directos (H2H).
    """
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
    """Calcula P(-2.5) y P(+2.5) sumando probabilidades de goles totales 0, 1 y 2."""
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
    min_edge: float = 0.05,
    min_prob_ou: float = 0.56,
    min_prob_under: float = 0.60,
    min_cuota_over: float = 1.45,
    min_cuota_under: float = 1.45,
    max_cuota_ou: float = 2.60,
) -> dict:
    """Evalúa +2.5 y -2.5 goles exigiendo mayor colchón en -2.5 y tope de cuota."""
    probs = probs_over_under_25(xg_local, xg_visitante)
    p_over = probs["p_over_25"]
    p_under = probs["p_under_25"]

    opciones = []
    desglose = []

    if cuota_over_25 and cuota_over_25 > 1.0:
        imp_over = 1.0 / cuota_over_25
        edge_over = p_over - imp_over
        ev_over = (p_over * cuota_over_25) - 1.0
        req_over = min_prob_ou if cuota_over_25 < 2.0 else max(0.48, min_prob_ou - 0.08)
        pasa_over = (
            edge_over >= min_edge
            and p_over >= req_over
            and min_cuota_over <= cuota_over_25 <= max_cuota_ou
        )
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
        req_under = (
            max(min_prob_under, min_prob_ou)
            if cuota_under_25 < 2.0
            else max(0.56, min_prob_under - 0.02)
        )
        req_edge_under = max(min_edge, 0.05)
        pasa_under = (
            edge_under >= req_edge_under
            and p_under >= req_under
            and min_cuota_under <= cuota_under_25 <= max_cuota_ou
        )
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
            "motivo": (
                f"Ningún mercado pasa el filtro de seguridad (ventaja mín. +{min_edge * 100:.1f}%, "
                f"prob. +2.5 desde {min_prob_ou * 100:.0f}% / -2.5 desde {min_prob_under * 100:.0f}%, "
                f"cuota máx. {max_cuota_ou:.2f})."
            ),
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
            f"**Prob. modelo:** `{resultado['prob_modelo']:.1f}%` | "
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
    "goal_home_input": "Walter Ferretti",
    "goal_away_input": "Sport Sébaco",
    "goal_country_input": "Nicaragua",
    "ultimo_ocr_goal_file": None,
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor_ini


def _aplicar_preset_goal() -> None:
    seleccion = st.session_state.get("goal_preset_select")
    if seleccion in QUICK_PRESETS_GOAL and seleccion != "Personalizado":
        h, a, c = QUICK_PRESETS_GOAL[seleccion]
        st.session_state["goal_home_input"] = h
        st.session_state["goal_away_input"] = a
        st.session_state["goal_country_input"] = c


def _limpiar_partido_goal() -> None:
    st.session_state["goal_home_input"] = ""
    st.session_state["goal_away_input"] = ""
    st.session_state["goal_country_input"] = ""
    st.session_state["goal_nota_input"] = ""
    st.session_state["ultimo_goal_analisis"] = None
    st.session_state["ultimo_ocr_goal_file"] = None


st.title("⚽ Detector de Goles (+2.5 / -2.5)")
st.caption("Equipos por captura, estadísticas reales vía API-Football (v3) y GOAL API + Poisson.")

tab_poisson, tab_detector, tab_registro = st.tabs(
    ["Análisis Poisson", "Detector (+2.5 / -2.5)", "Registro de análisis"]
)

with tab_poisson:
    st.subheader("Modelo Poisson — GOAL API")
    st.caption("Modelo pensado para análisis prepartido (10 últimos encuentros) con filtros reforzados en -2.5 goles.")
    goal_key_manual = st.text_input(
        "GOAL_KEY (opcional si ya está en Secrets o entorno)",
        type="password",
        key="goal_key_manual_input",
    )
    goal_key_activa = obtener_goal_key(goal_key_manual)

    col_p1, col_p2 = st.columns([3, 1.3])
    col_p1.selectbox(
        "Acceso rápido",
        options=list(QUICK_PRESETS_GOAL.keys()),
        index=1,
        key="goal_preset_select",
        on_change=_aplicar_preset_goal,
    )
    col_p2.markdown("<br>", unsafe_allow_html=True)
    col_p2.button("🧹 Limpiar", key="btn_clear_goal", on_click=_limpiar_partido_goal, width="stretch")

    archivo_goal = st.file_uploader(
        "Sube una captura del partido para sugerir los equipos en Poisson",
        type=["png", "jpg", "jpeg", "webp"],
        key="goal_ocr_uploader",
    )
    psm_goal = st.selectbox(
        "Modo OCR (PSM)",
        options=[11, 6, 4, 3],
        index=0,
        key="goal_ocr_psm",
    )

    if archivo_goal is not None:
        img_bytes_g = archivo_goal.getvalue()
        img_g = Image.open(BytesIO(img_bytes_g))
        st.image(
            img_g,
            caption=f"Captura GOAL ({img_g.width}x{img_g.height} px)",
            width="stretch",
        )
        try:
            texto_ocr_g = ejecutar_ocr_bytes(img_bytes_g, psm=psm_goal)
            loc_ocr_g, vis_ocr_g = sugerir_equipos_candidatos(texto_ocr_g)
            marca_ocr = f"{archivo_goal.file_id}_{psm_goal}"
            if st.session_state.get("ultimo_ocr_goal_file") != marca_ocr:
                st.session_state["goal_home_input"] = loc_ocr_g
                st.session_state["goal_away_input"] = vis_ocr_g
                st.session_state["goal_country_input"] = ""
                st.session_state["ultimo_ocr_goal_file"] = marca_ocr
            with st.expander("Ver texto OCR detectado (GOAL API)"):
                st.text(texto_ocr_g if texto_ocr_g.strip() else "No se detectó texto.")
        except Exception as exc:
            st.error(f"Error al ejecutar OCR: {exc}")

    gc1, gc2, gc3 = st.columns([2, 2, 1.5])
    g_home_input = gc1.text_input("Equipo Local", key="goal_home_input")
    g_away_input = gc2.text_input("Equipo Visitante", key="goal_away_input")
    g_country_input = gc3.text_input("País (opcional)", key="goal_country_input")

    gp1, gp2 = st.columns(2)
    g_last_n = gp1.slider("Últimos partidos", min_value=6, max_value=15, value=10, key="goal_last_n")
    g_league_avg = gp2.number_input(
        "Media base goles/equipo", min_value=0.6, max_value=2.5, value=1.30, step=0.05, key="goal_league_avg"
    )
    g_auto_league = st.checkbox(
        "Adaptar automáticamente la media de goles al ritmo real de ambos equipos",
        value=True,
        key="goal_auto_league",
    )

    go1, go2, go3 = st.columns(3)
    g_cuota_x = go1.number_input(
        "Cuota Empate (X) Winamax", min_value=1.01, max_value=15.0, value=3.90, step=0.05, key="goal_cuota_x"
    )
    g_cuota_o25 = go2.number_input(
        "Cuota Over 2.5 Winamax", min_value=1.01, max_value=10.0, value=2.80, step=0.05, key="goal_cuota_o25"
    )
    g_cuota_u25 = go3.number_input(
        "Cuota Under 2.5 Winamax", min_value=1.01, max_value=10.0, value=1.39, step=0.05, key="goal_cuota_u25"
    )

    gl1, gl2, gl3, gl4 = st.columns(4)
    g_max_lambda = gl1.slider(
        "Límite máximo λ",
        min_value=1.50,
        max_value=4.50,
        value=2.80,
        step=0.10,
        key="goal_max_lambda",
    )
    g_min_edge_pct = gl2.slider(
        "Ventaja mínima (%)",
        min_value=1.0,
        max_value=25.0,
        value=5.0,
        step=0.5,
        key="goal_min_edge_pct",
    )
    g_min_prob_ou = gl3.slider(
        "Prob. mínima +2.5 (%)",
        min_value=45.0,
        max_value=80.0,
        value=56.0,
        step=1.0,
        key="goal_min_prob_ou",
    )
    g_min_prob_under = gl4.slider(
        "Prob. mínima -2.5 (%)",
        min_value=50.0,
        max_value=80.0,
        value=60.0,
        step=1.0,
        key="goal_min_prob_under",
    )
    g_max_cuota_ou = st.slider(
        "Cuota máx. +2.5 / -2.5",
        min_value=2.00,
        max_value=4.00,
        value=2.60,
        step=0.05,
        key="goal_max_cuota_ou",
    )
    gc_f1, gc_f2 = st.columns(2)
    g_solo_goles = gc_f1.checkbox(
        "Priorizar solo mercados de goles (+2.5 / -2.5) en el veredicto",
        value=True,
        key="goal_solo_goles",
    )
    g_exigir_cons = gc_f2.checkbox(
        "Exigir respaldo en % histórico de ambos equipos",
        value=True,
        key="goal_exigir_cons",
    )
    g_nota = st.text_input("Nota rápida (opcional)", key="goal_nota_input")

    if st.button("Calcular probabilidades", type="primary", key="btn_calc_goal_poisson", width="stretch"):
        try:
            res_g = run_goal_matchup_poisson(
                home_query=g_home_input,
                away_query=g_away_input,
                country_filter=g_country_input or None,
                goal_key=goal_key_activa,
                last_n=g_last_n,
                league_avg_per_side=g_league_avg,
                auto_league_avg=g_auto_league,
                max_lambda=g_max_lambda,
                winamax_over25=g_cuota_o25,
                winamax_under25=g_cuota_u25,
                winamax_draw=g_cuota_x,
            )
            st.session_state["ultimo_goal_analisis"] = {
                "res": res_g,
                "last_n": g_last_n,
                "cuota_x": g_cuota_x,
                "cuota_o25": g_cuota_o25,
                "cuota_u25": g_cuota_u25,
                "min_edge": g_min_edge_pct / 100.0,
                "min_prob_ou": g_min_prob_ou / 100.0,
                "min_prob_under": g_min_prob_under / 100.0,
                "max_cuota_ou": g_max_cuota_ou,
                "solo_goles": g_solo_goles,
                "exigir_consistencia": g_exigir_cons,
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
        hs = res_g["home_stats"]
        aws = res_g["away_stats"]
        pron = seleccionar_pronostico_goal(
            markets=mg,
            cuota_x=ultimo_g["cuota_x"],
            cuota_o25=ultimo_g["cuota_o25"],
            cuota_u25=ultimo_g.get("cuota_u25", 1.39),
            min_edge=ultimo_g.get("min_edge", 0.05),
            min_prob_ou=ultimo_g.get("min_prob_ou", 0.56),
            min_prob_under=ultimo_g.get("min_prob_under", 0.60),
            max_cuota_ou=ultimo_g.get("max_cuota_ou", 2.60),
            solo_goles=ultimo_g.get("solo_goles", True),
            home_stats=hs,
            away_stats=aws,
            exigir_consistencia=ultimo_g.get("exigir_consistencia", True),
            mismo_equipo=res_g.get("mismo_equipo", False),
            muestra_insuficiente=res_g.get("muestra_insuficiente", False),
        )
        ex = pron["resultado_exacto"]
        top3_txt = " | ".join(
            f"`{item['marcador']}` ({item['prob']:.1f}%)" for item in ex.get("top3", [])
        )

        for aviso in res_g.get("warnings", []):
            st.warning(f"⚠️ {aviso}")

        st.caption(
            f"Equipos detectados: **{ht.get('name')}** (`{ht.get('country') or 'N/D'}`) "
            f"vs **{at.get('name')}** (`{at.get('country') or 'N/D'}`) · "
            f"Media goles/equipo aplicada: `{res_g.get('base_used', 1.30)}`"
        )

        st.info(
            f"**Consistencia en últimos {ultimo_g['last_n']} partidos:** "
            f"{ht.get('name')} → **+2.5:** `{hs.get('over25_rate', 0)}%` / **-2.5:** `{hs.get('under25_rate', 0)}%` | "
            f"{at.get('name')} → **+2.5:** `{aws.get('over25_rate', 0)}%` / **-2.5:** `{aws.get('under25_rate', 0)}%`"
        )

        gm1, gm2, gm3, gm4 = st.columns(4)
        gm1.metric("Goles esperados", f"{mg['expected_total_goals']}", f"λ {mg['lam_home']} / {mg['lam_away']}")
        gm2.metric("Prob. Empate (X)", f"{mg['prob_x']*100:.1f}%", f"Cuota justa: {mg['fair_x']}")
        gm3.metric("Prob. Over 2.5", f"{mg['prob_over_25']*100:.1f}%", f"Cuota justa: {mg['fair_over_25']}")
        gm4.metric("Prob. Under 2.5", f"{mg['prob_under_25']*100:.1f}%", f"Cuota justa: {mg['fair_under_25']}")

        ge1, ge2, ge3 = st.columns(3)
        ge1.metric("Edge Empate (X)", f"{(mg['edge_draw'] or 0)*100:+.1f}%", f"Winamax: {ultimo_g['cuota_x']:.2f}")
        ge2.metric("Edge Over 2.5", f"{(mg['edge_over_25'] or 0)*100:+.1f}%", f"Winamax: {ultimo_g['cuota_o25']:.2f}")
        ge3.metric(
            "Edge Under 2.5",
            f"{(mg['edge_under_25'] or 0)*100:+.1f}%",
            f"Winamax: {ultimo_g.get('cuota_u25', 1.39):.2f}",
        )

        if pron["apostar"]:
            st.success(
                f"### ✅ PRONÓSTICO → {pron['pick']} | RESULTADO EXACTO → `{ex['marcador']}`\n"
                f"**Cuota Winamax:** `{pron['cuota']:.2f}` | "
                f"**Prob. modelo:** `{pron['prob']:.1f}%` (cuota justa `{pron['cuota_justa']}`) | "
                f"**Ventaja:** `+{pron['edge'] * 100:.1f}%`\n\n"
                f"**Top 3 marcadores exactos:** {top3_txt}"
            )
        else:
            st.warning(
                f"### ⛔ NO APOSTAR | RESULTADO EXACTO MÁS PROBABLE → `{ex['marcador']}`\n"
                f"{pron['motivo']}\n\n"
                f"**Top 3 marcadores exactos:** {top3_txt}"
            )

        if st.button("Guardar en registro", key="btn_save_goal_log", width="stretch"):
            registrar_analisis_goal(
                home_name=ht.get("name") or ultimo_g["home_fallback"],
                away_name=at.get("name") or ultimo_g["away_fallback"],
                last_n=ultimo_g["last_n"],
                m=mg,
                cuota_x=ultimo_g["cuota_x"],
                cuota_o25=ultimo_g["cuota_o25"],
                cuota_u25=ultimo_g.get("cuota_u25", 1.39),
                pronostico_txt=pron["pick"],
                nota=ultimo_g["nota"],
            )
            st.success("Análisis guardado en la pestaña 'Registro de análisis'.")

        with st.expander("Matriz de resultados exactos (% probabilidad)"):
            st.dataframe(mg["matrix_df"], width="stretch")

        with st.expander("Últimos partidos usados en el cálculo"):
            st.write(
                f"**{ht.get('name')}** ({hs['count']} PJ — "
                f"GF pond.: {hs['gf_avg']:.2f} | GC pond.: {hs['ga_avg']:.2f})"
            )
            st.dataframe(pd.DataFrame(hs["matches"]), width="stretch")
            st.write(
                f"**{at.get('name')}** ({aws['count']} PJ — "
                f"GF pond.: {aws['gf_avg']:.2f} | GC pond.: {aws['ga_avg']:.2f})"
            )
            st.dataframe(pd.DataFrame(aws["matches"]), width="stretch")

with tab_detector:
    st.subheader("1. Captura de partido (opcional)")
    archivo = st.file_uploader(
        "Sube una captura del partido para sugerir los equipos",
        type=["png", "jpg", "jpeg", "webp"],
        key="detector_ocr_uploader",
    )

    with st.expander("Ajustes de API-Football, OCR y filtros"):
        api_key_input = st.text_input(
            "API-Football Key (opcional si ya está en st.secrets['API_FOOTBALL_KEY'])",
            type="password",
        )
        auto_fetch = st.checkbox(
            "Buscar promedios automáticamente al subir una captura nueva", value=True
        )
        psm = st.selectbox("Modo de segmentación OCR (PSM)", options=[11, 6, 4, 3], index=0)
        min_edge_pct = st.slider(
            "Ventaja mínima sobre cuota (%)", min_value=1.0, max_value=25.0, value=5.0, step=0.5
        )
        min_prob_det_pct = st.slider(
            "Probabilidad mínima del modelo en +2.5 (%)",
            min_value=45.0,
            max_value=80.0,
            value=56.0,
            step=1.0,
        )
        min_prob_under_det_pct = st.slider(
            "Probabilidad mínima del modelo en -2.5 (%)",
            min_value=50.0,
            max_value=80.0,
            value=60.0,
            step=1.0,
        )
        min_cuota_over = st.slider(
            "Cuota mínima en +2.5 goles", min_value=1.30, max_value=2.50, value=1.45, step=0.05
        )
        min_cuota_under = st.slider(
            "Cuota mínima en -2.5 goles", min_value=1.30, max_value=3.00, value=1.45, step=0.05
        )
        max_cuota_det = st.slider(
            "Cuota máxima en +2.5 / -2.5 goles", min_value=2.00, max_value=4.00, value=2.60, step=0.05
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
        min_prob_ou=min_prob_det_pct / 100.0,
        min_prob_under=min_prob_under_det_pct / 100.0,
        min_cuota_over=min_cuota_over,
        min_cuota_under=min_cuota_under,
        max_cuota_ou=max_cuota_det,
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
            st.rerun(
