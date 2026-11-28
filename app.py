import math
import re
import unicodedata
from io import BytesIO

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

# Factor de ajuste de goles esperados por país normalizado (1.00 = neutro)
FACTOR_PAIS_NORM = {
    "espana": 0.98,
    "inglaterra": 1.03,
    "alemania": 1.05,
    "italia": 0.96,
    "francia": 1.00,
    "portugal": 1.00,
    "paises bajos": 1.05,
    "holanda": 1.05,
    "belgica": 1.02,
    "colombia": 0.95,
    "argentina": 0.94,
    "brasil": 0.96,
    "venezuela": 0.95,
    "chile": 0.98,
    "peru": 0.97,
    "uruguay": 0.95,
    "mexico": 0.99,
    "estados unidos": 1.03,
    "eeuu": 1.03,
    "japon": 0.99,
    "corea del sur": 0.97,
    "australia": 1.03,
    "macedonia del norte": 0.97,
    "polonia": 1.00,
    "otro / general": 1.00,
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

VALORES_POR_DEFECTO = {
    "pais_local_txt": "",
    "pais_visitante_txt": "",
    "gf_local_10": 1.30,
    "gc_local_10": 1.05,
    "gf_vis_10": 1.15,
    "gc_vis_10": 1.15,
    "goles_h2h_prom": 2.30,
    "usar_h2h": False,
    "cuota_over_25_txt": "",
    "cuota_under_25_txt": "",
    "cuota_empate_txt": "",
    "marcador_objetivo": "1-1",
    "cuota_marcador_txt": "",
    "api_info_msg": "",
    "api_warn_msg": "",
}

MARCADORES_COMUNES = [
    "0-0",
    "1-0",
    "0-1",
    "1-1",
    "2-0",
    "0-2",
    "2-1",
    "1-2",
    "2-2",
    "3-1",
    "1-3",
    "3-0",
    "0-3",
]


def parsear_cuota(texto: str) -> float | None:
    """Convierte texto de cuota (con coma o punto) a float válido (> 1.01), o None si está vacío."""
    if not texto or not texto.strip():
        return None
    limpio = texto.strip().replace(",", ".")
    try:
        valor = float(limpio)
        return valor if valor > 1.01 else None
    except ValueError:
        return None


def normalizar_texto(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def obtener_factor_pais(pais: str) -> float:
    clave = normalizar_texto(pais or "")
    if not clave:
        return 1.0
    return FACTOR_PAIS_NORM.get(clave, 1.0)


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


def buscar_equipo_api(nombre: str, api_key: str, pais_filtro: str | None = None) -> dict | None:
    consulta = preparar_nombre_busqueda(nombre)
    pais_limpio = (pais_filtro or "").strip()
    params_base: list[tuple[str, str]] = [("search", consulta)]
    if pais_limpio and normalizar_texto(pais_limpio) not in {"otro", "otro / general", "general"}:
        params_base.append(("country", pais_limpio))

    data = api_get("teams", tuple(params_base), api_key)
    errores = data.get("errors")
    if errores:
        raise RuntimeError(str(errores))

    resultados = data.get("response", [])
    if not resultados and len(params_base) > 1:
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
    for temporada in ("2024", "2023", "2022"):
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


def _rho_ajustado_por_empate(cuota_empate: float | None) -> float:
    """Ajusta el parámetro rho de Dixon-Coles según la cuota de empate (X) en Winamax."""
    rho_base = -0.10
    if not cuota_empate or cuota_empate <= 1.05:
        return rho_base
    prob_imp_empate = 1.0 / cuota_empate
    if prob_imp_empate >= 0.28:
        extra = min(0.08, (prob_imp_empate - 0.28) * 0.45)
        return round(max(-0.18, rho_base - extra), 3)
    if prob_imp_empate <= 0.21:
        suave = min(0.05, (0.21 - prob_imp_empate) * 0.35)
        return round(min(-0.05, rho_base + suave), 3)
    return rho_base


def calcular_xg_moderado(
    gf_local_10: float,
    gc_local_10: float,
    gf_vis_10: float,
    gc_vis_10: float,
    goles_h2h_prom: float | None = None,
    pais_local: str = "",
    pais_visitante: str = "",
    cuota_empate: float | None = None,
    peso_h2h: float = 0.12,
    factor_localia: float = 0.06,
) -> tuple[float, float]:
    """
    Calcula goles esperados moderando extremos, aplicando factor de localía,
    factor por país de los equipos, freno ante defensas sólidas y ponderando H2H.
    """
    gf_l = min(max(gf_local_10, 0.15), 3.8)
    gc_l = min(max(gc_local_10, 0.15), 3.8)
    gf_v = min(max(gf_vis_10, 0.15), 3.8)
    gc_v = min(max(gc_vis_10, 0.15), 3.8)

    xg_local = ((gf_l + gc_v) / 2.0) * (1.0 + factor_localia)
    xg_visitante = ((gf_v + gc_l) / 2.0) * (1.0 - factor_localia)

    fac_pais_l = obtener_factor_pais(pais_local)
    fac_pais_v = obtener_factor_pais(pais_visitante)
    fac_pais_medio = (fac_pais_l + fac_pais_v) / 2.0
    xg_local *= fac_pais_medio
    xg_visitante *= fac_pais_medio

    if min(gc_l, gc_v) < 0.95:
        xg_local *= 0.93
        xg_visitante *= 0.93

    if cuota_empate and cuota_empate > 1.05 and (1.0 / cuota_empate) >= 0.30:
        xg_local *= 0.96
        xg_visitante *= 0.96

    if goles_h2h_prom is not None and goles_h2h_prom > 0:
        h2h_mod = min(max(goles_h2h_prom, 0.5), 5.0)
        total_base = xg_local + xg_visitante
        total_ajustado = ((1.0 - peso_h2h) * total_base) + (peso_h2h * h2h_mod)
        if total_base > 0:
            factor = total_ajustado / total_base
            xg_local *= factor
            xg_visitante *= factor

    return round(max(0.15, xg_local), 2), round(max(0.15, xg_visitante), 2)


def poisson_pmf(k: int, lam: float) -> float:
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)


def _tau_dixon_coles(x: int, y: int, lam_x: float, lam_y: float, rho: float = -0.10) -> float:
    """Ajuste de correlación Dixon-Coles para marcadores bajos (0-0, 1-0, 0-1, 1-1)."""
    if x == 0 and y == 0:
        return max(0.05, 1.0 - (lam_x * lam_y * rho))
    if x == 0 and y == 1:
        return max(0.05, 1.0 + (lam_x * rho))
    if x == 1 and y == 0:
        return max(0.05, 1.0 + (lam_y * rho))
    if x == 1 and y == 1:
        return max(0.05, 1.0 - rho)
    return 1.0


def _calibrar_empate_matriz(
    matriz_bruta: dict[tuple[int, int], float],
    cuota_empate: float | None,
) -> dict[tuple[int, int], float]:
    """
    Si hay cuota de empate (X) válida, mezcla suavemente (25% de peso) la masa de empates
    hacia la probabilidad implícita de empate para afinar marcadores como 0-0, 1-1 o 2-2.
    """
    total = sum(matriz_bruta.values())
    if total <= 0:
        return matriz_bruta

    norm = {k: v / total for k, v in matriz_bruta.items()}
    if not cuota_empate or cuota_empate <= 1.05:
        return norm

    prob_imp_empate = min(0.55, max(0.08, 1.0 / cuota_empate))
    empates_keys = [k for k in norm if k[0] == k[1]]
    no_empates_keys = [k for k in norm if k[0] != k[1]]

    p_emp_actual = sum(norm[k] for k in empates_keys)
    p_no_emp_actual = sum(norm[k] for k in no_empates_keys)

    if p_emp_actual <= 0 or p_no_emp_actual <= 0:
        return norm

    p_emp_obj = (0.75 * p_emp_actual) + (0.25 * prob_imp_empate)
    p_emp_obj = min(0.65, max(0.05, p_emp_obj))
    p_no_emp_obj = 1.0 - p_emp_obj

    esc_emp = p_emp_obj / p_emp_actual
    esc_no_emp = p_no_emp_obj / p_no_emp_actual

    ajustada: dict[tuple[int, int], float] = {}
    for k, p in norm.items():
        ajustada[k] = p * (esc_emp if k[0] == k[1] else esc_no_emp)
    return ajustada


def matriz_marcadores_dixon_coles(
    xg_local: float,
    xg_visitante: float,
    cuota_empate: float | None = None,
    max_goles: int = 6,
) -> dict[tuple[int, int], float]:
    """Devuelve la distribución normalizada de marcadores exactos (i, j) con Dixon-Coles."""
    lam_l = max(0.05, xg_local)
    lam_v = max(0.05, xg_visitante)
    rho = _rho_ajustado_por_empate(cuota_empate)

    probs_l = [poisson_pmf(i, lam_l) for i in range(max_goles + 1)]
    probs_v = [poisson_pmf(j, lam_v) for j in range(max_goles + 1)]

    bruta: dict[tuple[int, int], float] = {}
    for i in range(max_goles + 1):
        for j in range(max_goles + 1):
            tau = _tau_dixon_coles(i, j, lam_l, lam_v, rho=rho)
            bruta[(i, j)] = probs_l[i] * probs_v[j] * tau

    return _calibrar_empate_matriz(bruta, cuota_empate)


def probs_over_under_25(
    xg_local: float,
    xg_visitante: float,
    cuota_empate: float | None = None,
    max_goles: int = 6,
) -> dict[str, float]:
    """Calcula P(-2.5), P(+2.5) y P(Empate) desde la matriz bivariante Dixon-Coles."""
    matriz = matriz_marcadores_dixon_coles(
        xg_local, xg_visitante, cuota_empate=cuota_empate, max_goles=max_goles
    )
    p_under_25_bruta = sum(p for (i, j), p in matriz.items() if i + j <= 2)
    p_empate_bruta = sum(p for (i, j), p in matriz.items() if i == j)

    p_under_25 = min(0.98, max(0.02, p_under_25_bruta))
    p_over_25 = 1.0 - p_under_25
    p_empate = min(0.90, max(0.02, p_empate_bruta))

    return {
        "xg_total": round(max(0.05, xg_local) + max(0.05, xg_visitante), 2),
        "p_under_25": p_under_25,
        "p_over_25": p_over_25,
        "p_empate": p_empate,
        "rho": _rho_ajustado_por_empate(cuota_empate),
    }


def analizar_marcadores_exactos(
    xg_local: float,
    xg_visitante: float,
    cuota_empate: float | None = None,
    marcador_objetivo: str = "1-1",
    cuota_marcador: float | None = None,
) -> dict:
    """Genera top 3 destacados, top 6 marcadores exactos y evaluación opcional de cuota."""
    matriz = matriz_marcadores_dixon_coles(
        xg_local, xg_visitante, cuota_empate=cuota_empate, max_goles=6
    )
    ordenados = sorted(matriz.items(), key=lambda item: item[1], reverse=True)

    top_3 = []
    for rango, ((i, j), p) in enumerate(ordenados[:3], start=1):
        cuota_justa = (1.0 / p) if p > 0.005 else 99.0
        top_3.append(
            {
                "rango": rango,
                "marcador": f"{i} - {j}",
                "prob": round(p * 100, 1),
                "cuota_justa": round(cuota_justa, 2),
                "tipo": "Empate" if i == j else ("-2.5" if i + j <= 2 else "+2.5"),
            }
        )

    top_6 = []
    for (i, j), p in ordenados[:6]:
        cuota_justa = (1.0 / p) if p > 0.005 else 99.0
        top_6.append(
            {
                "Marcador": f"{i} - {j}",
                "Prob. modelo": f"{p * 100:.1f}%",
                "Cuota justa": f"{cuota_justa:.2f}",
                "Tipo": "Empate" if i == j else ("-2.5" if i + j <= 2 else "+2.5"),
            }
        )

    claves = [(0, 0), (1, 1), (1, 0), (0, 1), (2, 1), (1, 2)]
    marcadores_clave = {
        f"{i}-{j}": round(matriz.get((i, j), 0.0) * 100, 1) for i, j in claves
    }

    eval_objetivo = None
    m_limpio = (marcador_objetivo or "").strip().replace(":", "-").replace(" ", "")
    partes_m = m_limpio.split("-")
    if len(partes_m) == 2 and partes_m[0].isdigit() and partes_m[1].isdigit():
        gl, gv = int(partes_m[0]), int(partes_m[1])
        p_obj = matriz.get((gl, gv), 0.0)
        cuota_justa_obj = (1.0 / p_obj) if p_obj > 0.005 else 99.0
        info_obj = {
            "marcador": f"{gl}-{gv}",
            "prob_modelo": round(p_obj * 100, 1),
            "cuota_justa": round(cuota_justa_obj, 2),
            "cuota_winamax": cuota_marcador,
            "ventaja_pct": None,
            "ev": None,
        }
        if cuota_marcador and cuota_marcador > 1.01:
            imp = 1.0 / cuota_marcador
            info_obj["ventaja_pct"] = round((p_obj - imp) * 100, 1)
            info_obj["ev"] = round((p_obj * cuota_marcador) - 1.0, 3)
        eval_objetivo = info_obj

    return {
        "top_3": top_3,
        "top_6": top_6,
        "marcadores_clave": marcadores_clave,
        "eval_objetivo": eval_objetivo,
    }


def evaluar_entrada_25(
    xg_local: float,
    xg_visitante: float,
    cuota_over_25: float | None = None,
    cuota_under_25: float | None = None,
    cuota_empate: float | None = None,
    min_edge: float = 0.06,
    min_cuota_over: float = 1.55,
    min_cuota_under: float = 1.45,
    min_prob_over: float = 0.56,
    min_prob_under: float = 0.58,
) -> dict:
    """Evalúa +2.5 y -2.5 goles exigiendo ventaja, cuota mínima y probabilidad mínima del modelo."""
    probs = probs_over_under_25(xg_local, xg_visitante, cuota_empate=cuota_empate)
    p_over = probs["p_over_25"]
    p_under = probs["p_under_25"]
    p_empate = probs["p_empate"]

    opciones = []
    desglose = []

    if cuota_over_25 and cuota_over_25 > 1.0:
        imp_over = 1.0 / cuota_over_25
        edge_over = p_over - imp_over
        ev_over = (p_over * cuota_over_25) - 1.0
        pasa_over = (
            edge_over >= min_edge
            and cuota_over_25 >= min_cuota_over
            and p_over >= min_prob_over
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
        pasa_under = (
            edge_under >= min_edge
            and cuota_under_25 >= min_cuota_under
            and p_under >= min_prob_under
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

    if cuota_empate and cuota_empate > 1.0:
        imp_empate = 1.0 / cuota_empate
        edge_empate = p_empate - imp_empate
        desglose.append(
            {
                "Mercado": "Empate (X ref.)",
                "Cuota": f"{cuota_empate:.2f}",
                "Prob. modelo": f"{p_empate * 100:.1f}%",
                "Prob. implícita": f"{imp_empate * 100:.1f}%",
                "Ventaja": f"{edge_empate * 100:+.1f}%",
                "Filtro": "Ref.",
            }
        )

    if not opciones:
        motivo = (
            "Introduce al menos una cuota válida de Winamax (+2.5 o -2.5) en la sección 2."
            if not desglose
            else "Ningún mercado supera los filtros de ventaja, probabilidad mínima o cuota mínima."
        )
        return {
            "decision": "NO APOSTAR",
            "motivo": motivo,
            "xg_total": probs["xg_total"],
            "p_over_25": round(p_over * 100, 1),
            "p_under_25": round(p_under * 100, 1),
            "p_empate": round(p_empate * 100, 1),
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
        "p_empate": round(p_empate * 100, 1),
        "desglose": desglose,
    }


def renderizar_resultado(
    resultado: dict,
    partido_label: str,
    xg_l: float,
    xg_v: float,
    info_marcadores: dict,
) -> None:
    """Muestra el veredicto directo, los 3 resultados exactos más potentes y el desglose."""
    st.markdown(f"**Partido:** {partido_label}  |  **xG:** `{xg_l:.2f}` vs `{xg_v:.2f}`")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Goles esperados (xG)", f"{resultado['xg_total']:.2f}")
    r2.metric("Prob. +2.5 goles", f"{resultado['p_over_25']:.1f}%")
    r3.metric("Prob. -2.5 goles", f"{resultado['p_under_25']:.1f}%")
    r4.metric("Prob. Empate (X)", f"{resultado['p_empate']:.1f}%")

    if resultado["decision"] == "APOSTAR":
        st.success(
            f"### ✅ APOSTAR → {resultado['mercado'].upper()}\n"
            f"**Cuota:** `{resultado['cuota']:.2f}` | "
            f"**Ventaja:** `+{resultado['edge']:.1f}%` | "
            f"**EV:** `{resultado['ev']:+.3f}`"
        )
    else:
        st.warning(f"### ⛔ NO APOSTAR\n{resultado['motivo']}")

    st.markdown("#### 🏆 Top 3 resultados exactos más potentes")
    t3_cols = st.columns(3)
    medallas = ["🥇 Top 1", "🥈 Top 2", "🥉 Top 3"]
    for idx, item in enumerate(info_marcadores["top_3"]):
        with t3_cols[idx]:
            st.info(
                f"**{medallas[idx]}: `{item['marcador']}`**\n\n"
                f"Prob.: **{item['prob']:.1f}%**\n\n"
                f"Cuota justa: `{item['cuota_justa']:.2f}` · `{item['tipo']}`"
            )

    if resultado.get("desglose"):
        st.dataframe(resultado["desglose"], width="stretch", hide_index=True)

    st.markdown("#### 🎯 Marcadores clave y Top 6 (Dixon-Coles)")
    claves = info_marcadores["marcadores_clave"]
    k_cols = st.columns(6)
    for idx, (m_label, p_val) in enumerate(claves.items()):
        k_cols[idx].metric(f"Marc. {m_label}", f"{p_val:.1f}%")

    st.dataframe(info_marcadores["top_6"], width="stretch", hide_index=True)

    ev_obj = info_marcadores.get("eval_objetivo")
    if ev_obj:
        txt_obj = (
            f"**Marcador consultado ({ev_obj['marcador']}):** "
            f"Prob. modelo `{ev_obj['prob_modelo']:.1f}%` | "
            f"Cuota justa `{ev_obj['cuota_justa']:.2f}`"
        )
        if ev_obj["cuota_winamax"] is not None and ev_obj["ventaja_pct"] is not None:
            txt_obj += (
                f" | Winamax `{ev_obj['cuota_winamax']:.2f}` | "
                f"Ventaja `{ev_obj['ventaja_pct']:+.1f}%` | "
                f"EV `{ev_obj['ev']:+.3f}`"
            )
        st.info(txt_obj)


if "reset_nonce" not in st.session_state:
    st.session_state["reset_nonce"] = 0

nonce = st.session_state["reset_nonce"]

CLAVES_DINAMICAS = {
    "pais_local_txt",
    "pais_visitante_txt",
    "gf_local_10",
    "gc_local_10",
    "gf_vis_10",
    "gc_vis_10",
    "goles_h2h_prom",
    "usar_h2h",
    "cuota_over_25_txt",
    "cuota_under_25_txt",
    "cuota_empate_txt",
    "marcador_objetivo",
    "cuota_marcador_txt",
}

for clave, valor_ini in VALORES_POR_DEFECTO.items():
    clave_destino = f"{clave}_{nonce}" if clave in CLAVES_DINAMICAS else clave
    if clave_destino not in st.session_state:
        st.session_state[clave_destino] = valor_ini


def limpiar_todo_estado() -> None:
    """Reinicia capturas, equipos, países, cuotas (en blanco), marcadores y promedios."""
    st.session_state["reset_nonce"] = st.session_state.get("reset_nonce", 0) + 1
    nuevo_nonce = st.session_state["reset_nonce"]
    st.session_state["api_info_msg"] = ""
    st.session_state["api_warn_msg"] = ""
    st.session_state["ultimo_auto_fetch"] = ""
    st.session_state[f"equipo_local_input_{nuevo_nonce}"] = ""
    st.session_state[f"equipo_visitante_input_{nuevo_nonce}"] = ""
    st.session_state[f"pais_local_txt_{nuevo_nonce}"] = ""
    st.session_state[f"pais_visitante_txt_{nuevo_nonce}"] = ""
    st.session_state[f"gf_local_10_{nuevo_nonce}"] = VALORES_POR_DEFECTO["gf_local_10"]
    st.session_state[f"gc_local_10_{nuevo_nonce}"] = VALORES_POR_DEFECTO["gc_local_10"]
    st.session_state[f"gf_vis_10_{nuevo_nonce}"] = VALORES_POR_DEFECTO["gf_vis_10"]
    st.session_state[f"gc_vis_10_{nuevo_nonce}"] = VALORES_POR_DEFECTO["gc_vis_10"]
    st.session_state[f"goles_h2h_prom_{nuevo_nonce}"] = VALORES_POR_DEFECTO["goles_h2h_prom"]
    st.session_state[f"usar_h2h_{nuevo_nonce}"] = VALORES_POR_DEFECTO["usar_h2h"]
    st.session_state[f"cuota_over_25_txt_{nuevo_nonce}"] = ""
    st.session_state[f"cuota_under_25_txt_{nuevo_nonce}"] = ""
    st.session_state[f"cuota_empate_txt_{nuevo_nonce}"] = ""
    st.session_state[f"marcador_objetivo_{nuevo_nonce}"] = VALORES_POR_DEFECTO["marcador_objetivo"]
    st.session_state[f"cuota_marcador_txt_{nuevo_nonce}"] = ""


st.title("⚽ Detector de Goles (+2.5 / -2.5)")
st.caption("Dixon-Coles + Top 3 marcadores exactos, país libre y cuota empate (X), 2 capturas OCR y Winamax.")

st.subheader("1. Capturas de partido y últimos 10 partidos (opcional)")
cap_col1, cap_col2 = st.columns(2)
with cap_col1:
    archivo_local = st.file_uploader(
        "Captura 1: Partido / 10 últimos Local",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"uploader_local_{nonce}",
    )
with cap_col2:
    archivo_visitante = st.file_uploader(
        "Captura 2: 10 últimos Visitante",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"uploader_visitante_{nonce}",
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
        "Ventaja mínima sobre cuota (%)", min_value=2.0, max_value=25.0, value=6.0, step=0.5
    )
    min_prob_over_pct = st.slider(
        "Probabilidad mínima del modelo en +2.5 goles (%)",
        min_value=45.0,
        max_value=75.0,
        value=56.0,
        step=1.0,
    )
    min_prob_under_pct = st.slider(
        "Probabilidad mínima del modelo en -2.5 goles (%)",
        min_value=45.0,
        max_value=75.0,
        value=58.0,
        step=1.0,
    )
    min_cuota_over = st.slider(
        "Cuota mínima en +2.5 goles", min_value=1.30, max_value=2.50, value=1.55, step=0.05
    )
    min_cuota_under = st.slider(
        "Cuota mínima en -2.5 goles", min_value=1.30, max_value=3.00, value=1.45, step=0.05
    )

texto_ocr_1 = ""
texto_ocr_2 = ""
local_sugerido = ""
visitante_sugerido = ""
archivo_principal = archivo_local or archivo_visitante

if archivo_local is not None or archivo_visitante is not None:
    prev_cols = st.columns(2)
    with prev_cols[0]:
        if archivo_local is not None:
            img_1 = Image.open(BytesIO(archivo_local.getvalue()))
            st.image(
                img_1,
                caption=f"Captura 1 ({img_1.width}x{img_1.height} px)",
                width="stretch",
            )
            try:
                texto_ocr_1 = ejecutar_ocr_bytes(archivo_local.getvalue(), psm=psm)
            except Exception as exc:
                st.error(f"Error OCR en Captura 1: {exc}")
    with prev_cols[1]:
        if archivo_visitante is not None:
            img_2 = Image.open(BytesIO(archivo_visitante.getvalue()))
            st.image(
                img_2,
                caption=f"Captura 2 ({img_2.width}x{img_2.height} px)",
                width="stretch",
            )
            try:
                texto_ocr_2 = ejecutar_ocr_bytes(archivo_visitante.getvalue(), psm=psm)
            except Exception as exc:
                st.error(f"Error OCR en Captura 2: {exc}")

    if st.button("Reescanear capturas"):
        st.cache_data.clear()

    texto_ocr_combinado = "\n".join(t for t in (texto_ocr_1, texto_ocr_2) if t.strip())
    local_sugerido, visitante_sugerido = sugerir_equipos_candidatos(texto_ocr_combinado)

    with st.expander("Ver texto detectado automáticamente en las capturas"):
        if texto_ocr_1.strip():
            st.markdown("**Captura 1:**")
            st.text(texto_ocr_1)
        if texto_ocr_2.strip():
            st.markdown("**Captura 2:**")
            st.text(texto_ocr_2)
        if not texto_ocr_combinado.strip():
            st.text("No se detectó texto.")

st.subheader("2. Partido, país y cuotas manuales de Winamax")
col1, col2 = st.columns(2)
with col1:
    equipo_local = st.text_input(
        "Equipo Local",
        value=local_sugerido,
        key=f"equipo_local_input_{nonce}",
    )
    pais_local = st.text_input(
        "País Equipo Local",
        placeholder="Ej. Macedonia del Norte",
        key=f"pais_local_txt_{nonce}",
    )
with col2:
    equipo_visitante = st.text_input(
        "Equipo Visitante",
        value=visitante_sugerido,
        key=f"equipo_visitante_input_{nonce}",
    )
    pais_visitante = st.text_input(
        "País Equipo Visitante",
        placeholder="Ej. Macedonia del Norte",
        key=f"pais_visitante_txt_{nonce}",
    )

api_key_activa = obtener_api_key(api_key_input)


def actualizar_estadisticas_desde_api(
    loc: str, vis: str, key: str, p_loc: str, p_vis: str, cur_nonce: int
) -> None:
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
        team_l = buscar_equipo_api(loc, key, pais_filtro=p_loc)
        team_v = buscar_equipo_api(vis, key, pais_filtro=p_vis)

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

        st.session_state[f"gf_local_10_{cur_nonce}"] = float(stats_l["gf_prom"])
        st.session_state[f"gc_local_10_{cur_nonce}"] = float(stats_l["gc_prom"])
        st.session_state[f"gf_vis_10_{cur_nonce}"] = float(stats_v["gf_prom"])
        st.session_state[f"gc_vis_10_{cur_nonce}"] = float(stats_v["gc_prom"])

        h2h = obtener_h2h_api(team_l["id"], team_v["id"], key)
        if h2h and h2h["partidos"] >= 2:
            st.session_state[f"goles_h2h_prom_{cur_nonce}"] = float(h2h["goles_prom"])
            st.session_state[f"usar_h2h_{cur_nonce}"] = True
            h2h_txt = f" | H2H ({h2h['partidos']} partidos): {h2h['goles_prom']:.2f} goles/partido"
        else:
            st.session_state[f"usar_h2h_{cur_nonce}"] = False
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
    archivo_principal is not None
    and auto_fetch
    and api_key_activa
    and equipo_local.strip()
    and equipo_visitante.strip()
):
    id_1 = getattr(archivo_local, "file_id", "") if archivo_local else ""
    id_2 = getattr(archivo_visitante, "file_id", "") if archivo_visitante else ""
    par_id = f"{id_1}_{id_2}_{equipo_local.strip()}_{equipo_visitante.strip()}"
    if st.session_state.get("ultimo_auto_fetch") != par_id:
        with st.spinner("Consultando últimos 10 partidos en API-Football..."):
            actualizar_estadisticas_desde_api(
                equipo_local, equipo_visitante, api_key_activa, pais_local, pais_visitante, nonce
            )
        st.session_state["ultimo_auto_fetch"] = par_id

b_col1, b_col2 = st.columns([2, 1])
with b_col1:
    if st.button("🔄 Buscar promedios reales en API-Football"):
        with st.spinner("Consultando últimos 10 partidos y H2H en API-Football..."):
            actualizar_estadisticas_desde_api(
                equipo_local, equipo_visitante, api_key_activa, pais_local, pais_visitante, nonce
            )
with b_col2:
    st.button("🧹 Limpiar todo", on_click=limpiar_todo_estado)

if st.session_state["api_info_msg"]:
    st.success(st.session_state["api_info_msg"])
if st.session_state["api_warn_msg"]:
    st.warning(st.session_state["api_warn_msg"])

c_over, c_under, c_empate = st.columns(3)
with c_over:
    usar_over = st.checkbox("Evaluar +2.5 goles", value=True)
    cuota_over_txt = st.text_input(
        "Cuota +2.5 (Winamax)",
        placeholder="Ej. 1,75",
        disabled=not usar_over,
        key=f"cuota_over_25_txt_{nonce}",
    )
with c_under:
    usar_under = st.checkbox("Evaluar -2.5 goles", value=True)
    cuota_under_txt = st.text_input(
        "Cuota -2.5 (Winamax)",
        placeholder="Ej. 2,05",
        disabled=not usar_under,
        key=f"cuota_under_25_txt_{nonce}",
    )
with c_empate:
    usar_empate_ref = st.checkbox("Usar cuota empate (X)", value=True)
    cuota_empate_txt = st.text_input(
        "Cuota Empate X (Winamax)",
        placeholder="Ej. 3,20",
        disabled=not usar_empate_ref,
        key=f"cuota_empate_txt_{nonce}",
    )

m_col1, m_col2 = st.columns(2)
with m_col1:
    marcador_objetivo = st.selectbox(
        "Marcador exacto a consultar",
        options=MARCADORES_COMUNES,
        key=f"marcador_objetivo_{nonce}",
    )
with m_col2:
    cuota_marcador_txt = st.text_input(
        "Cuota marcador exacto (opcional)",
        placeholder="Ej. 6,50",
        key=f"cuota_marcador_txt_{nonce}",
    )

cuota_over_25 = parsear_cuota(cuota_over_txt)
cuota_under_25 = parsear_cuota(cuota_under_txt)
cuota_empate = parsear_cuota(cuota_empate_txt)
cuota_marcador = parsear_cuota(cuota_marcador_txt)

with st.expander("3. Promedios (últimos 10 partidos y H2H)"):
    m1, m2 = st.columns(2)
    with m1:
        gf_local_10 = st.number_input(
            "Goles a favor Local (prom. 10)",
            min_value=0.0,
            max_value=6.0,
            step=0.05,
            key=f"gf_local_10_{nonce}",
        )
        gc_local_10 = st.number_input(
            "Goles en contra Local (prom. 10)",
            min_value=0.0,
            max_value=6.0,
            step=0.05,
            key=f"gc_local_10_{nonce}",
        )
    with m2:
        gf_vis_10 = st.number_input(
            "Goles a favor Visitante (prom. 10)",
            min_value=0.0,
            max_value=6.0,
            step=0.05,
            key=f"gf_vis_10_{nonce}",
        )
        gc_vis_10 = st.number_input(
            "Goles en contra Visitante (prom. 10)",
            min_value=0.0,
            max_value=6.0,
            step=0.05,
            key=f"gc_vis_10_{nonce}",
        )

    usar_h2h = st.checkbox("Incluir promedio de goles en H2H", key=f"usar_h2h_{nonce}")
    goles_h2h_prom = None
    if usar_h2h:
        goles_h2h_prom = st.number_input(
            "Promedio goles totales H2H",
            min_value=0.0,
            max_value=8.0,
            step=0.10,
            key=f"goles_h2h_prom_{nonce}",
        )

cuota_x_activa = cuota_empate if usar_empate_ref else None

xg_l, xg_v = calcular_xg_moderado(
    gf_local_10=gf_local_10,
    gc_local_10=gc_local_10,
    gf_vis_10=gf_vis_10,
    gc_vis_10=gc_vis_10,
    goles_h2h_prom=goles_h2h_prom,
    pais_local=pais_local,
    pais_visitante=pais_visitante,
    cuota_empate=cuota_x_activa,
)

resultado_actual = evaluar_entrada_25(
    xg_local=xg_l,
    xg_visitante=xg_v,
    cuota_over_25=cuota_over_25 if usar_over else None,
    cuota_under_25=cuota_under_25 if usar_under else None,
    cuota_empate=cuota_x_activa,
    min_edge=min_edge_pct / 100.0,
    min_cuota_over=min_cuota_over,
    min_cuota_under=min_cuota_under,
    min_prob_over=min_prob_over_pct / 100.0,
    min_prob_under=min_prob_under_pct / 100.0,
)

info_marcadores = analizar_marcadores_exactos(
    xg_local=xg_l,
    xg_visitante=xg_v,
    cuota_empate=cuota_x_activa,
    marcador_objetivo=marcador_objetivo,
    cuota_marcador=cuota_marcador,
)

label_loc = f"{equipo_local or 'Local'}{f' ({pais_local.strip()})' if pais_local.strip() else ''}"
label_vis = f"{equipo_visitante or 'Visitante'}{f' ({pais_visitante.strip()})' if pais_visitante.strip() else ''}"
partido_label = f"{label_loc} vs {label_vis}"

st.divider()
st.subheader("4. Análisis del modelo")
if st.button("Calcular recomendación", type="primary"):
    renderizar_resultado(resultado_actual, partido_label, xg_l, xg_v, info_marcadores)
