import math
import re
import unicodedata
from io import BytesIO

import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import streamlit as st


st.set_page_config(
    page_title="Detector de Goles (+2.5 / -2.5)",
    page_icon="⚽",
    layout="centered",
)

UMBRAL_RACHA_POR_DEFECTO = 60.0
UMBRAL_POISSON_OVER_DEFECTO = 58.0
UMBRAL_POISSON_UNDER_DEFECTO = 54.0
MIN_GOLES_ESPERADOS_OVER = 2.85
MAX_GOLES_ESPERADOS_UNDER = 2.45
MIN_EV_PCT_POR_DEFECTO = 0.0
MIN_EV_DESBLOQUEO_RACHA = 8.0

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
    "COLOMBIA",
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
    "PA",
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


def _parsear_marcadores_texto(texto: str) -> list[tuple[int, int]]:
    if not texto or not texto.strip():
        return []
    pares = re.findall(r"\b([0-9])\s*[-–:]\s*([0-9])\b", texto)
    return [(int(a), int(b)) for a, b in pares if int(a) <= 9 and int(b) <= 9][:10]


def _extraer_nombre_equipo_ocr(texto_ocr: str, fallback: str = "") -> str:
    if not texto_ocr:
        return fallback.strip()

    match_cabecera = re.search(
        r"(?:ULTIMOS\s+PARTIDOS|ÚLTIMOS\s+PARTIDOS)\s*[:\-–]?\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\s\-'.]{2,40})",
        texto_ocr,
        flags=re.IGNORECASE,
    )
    if match_cabecera:
        candidato = match_cabecera.group(1).strip().splitlines()[0].strip()
        if len(candidato) >= 2:
            return candidato

    for linea in texto_ocr.splitlines():
        l_strip = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\s\-'.]", "", linea).strip()
        if len(l_strip) < 3 or len(l_strip) > 35:
            continue
        mayus = normalizar_texto(l_strip).upper()
        if any(ruido == mayus or ruido in mayus for ruido in PALABRAS_RUIDO):
            continue
        if re.fullmatch(r"[0-9\s\-:./]+", l_strip):
            continue
        if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{2,4}", l_strip):
            continue
        return l_strip

    return fallback.strip()


def extraer_datos_desde_imagen(imagen: Image.Image) -> dict:
    w, h = imagen.size
    escala = 2 if max(w, h) < 1300 else 1
    base = imagen.convert("RGB")
    if escala > 1:
        base = base.resize((w * escala, h * escala), Image.Resampling.LANCZOS)

    gris = ImageOps.grayscale(base)
    gris = ImageOps.autocontrast(gris)
    gris = ImageEnhance.Contrast(gris).enhance(2.0)

    textos = []
    for cfg in ("--psm 6", "--psm 4", "--psm 11"):
        try:
            txt = pytesseract.image_to_string(gris, lang="spa+eng", config=cfg)
        except Exception:
            try:
                txt = pytesseract.image_to_string(gris, config=cfg)
            except Exception:
                txt = ""
        if txt:
            textos.append(txt)

    texto = "\n".join(textos)
    resultados = _parsear_marcadores_texto(texto)
    equipo_detectado = _extraer_nombre_equipo_ocr(texto)

    return {
        "texto": texto,
        "marcadores": resultados[:10],
        "equipo_detectado": equipo_detectado,
    }


def resumir_marcadores_equipo(marcadores: list[tuple[int, int]], es_local: bool = True) -> dict | None:
    if not marcadores:
        return None
    n = len(marcadores[:10])
    gf_w = 0.0
    gc_w = 0.0
    w_sum = 0.0
    over_c = 0
    for idx, (g1, g2) in enumerate(marcadores[:10]):
        gf = min(g1 if es_local else g2, 5)
        gc = min(g2 if es_local else g1, 5)
        peso = 0.91**idx
        gf_w += gf * peso
        gc_w += gc * peso
        w_sum += peso
        if (g1 + g2) >= 3:
            over_c += 1
    over_rate = round((over_c / n) * 100, 1)
    under_rate = round(100.0 - over_rate, 1)
    return {
        "partidos": n,
        "count": n,
        "gf_prom": round(gf_w / w_sum, 2),
        "gc_prom": round(gc_w / w_sum, 2),
        "gf_avg": gf_w / w_sum,
        "ga_avg": gc_w / w_sum,
        "over25_rate": over_rate,
        "under25_rate": under_rate,
        "marcadores_usados": [f"{a}-{b}" for a, b in marcadores[:10]],
    }


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
    total_lam = lam_home + lam_away
    if total_lam <= 2.40:
        lam_home_adj = lam_home * 0.92
        lam_away_adj = lam_away * 0.92
        rho = -0.10
    else:
        lam_home_adj = lam_home
        lam_away_adj = lam_away
        rho = -0.07

    prob_home = 0.0
    prob_draw = 0.0
    prob_away = 0.0
    prob_over_25 = 0.0

    cell_probs: list[tuple[str, float, int]] = []
    raw_matrix: list[list[float]] = []
    total_mass = 0.0

    for h in range(max_goals + 1):
        row = []
        p_h = poisson_pmf(h, lam_home_adj)
        for a in range(max_goals + 1):
            p_a = poisson_pmf(a, lam_away_adj)
            tau = 1.0
            if h == 0 and a == 0:
                tau = 1.0 - (lam_home_adj * lam_away_adj * rho)
            elif h == 0 and a == 1:
                tau = 1.0 + (lam_home_adj * rho)
            elif h == 1 and a == 0:
                tau = 1.0 + (lam_away_adj * rho)
            elif h == 1 and a == 1:
                tau = 1.0 - rho

            p_cell = max(0.0, p_h * p_a * max(0.70, min(1.35, tau)))
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
        {"marcador": sc, "prob": round(pr * 100, 1), "cuota_justa": fair_odd(pr)}
        for sc, pr, _ in top_scores_sorted
    ]
    best_score, best_prob, _ = top_scores_sorted[0]

    under_scores_sorted = sorted(under_scores, key=lambda x: x[1], reverse=True)[:3]
    top_under_scores = [
        {"marcador": sc, "prob": round(pr * 100, 1), "cuota_justa": fair_odd(pr)}
        for sc, pr in under_scores_sorted
    ]
    best_under_score, best_under_prob = (
        under_scores_sorted[0] if under_scores_sorted else ("1 - 0", 0.0)
    )

    over_scores_sorted = sorted(over_scores, key=lambda x: x[1], reverse=True)[:3]
    top_over_scores = [
        {"marcador": sc, "prob": round(pr * 100, 1), "cuota_justa": fair_odd(pr)}
        for sc, pr in over_scores_sorted
    ]
    best_over_score, best_over_prob = (
        over_scores_sorted[0] if over_scores_sorted else ("2 - 1", 0.0)
    )

    return {
        "lam_home": round(lam_home_adj, 3),
        "lam_away": round(lam_away_adj, 3),
        "expected_total_goals": round(lam_home_adj + lam_away_adj, 3),
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


def _cumple_racha_o_desbloqueo(
    r_home: float,
    r_away: float,
    prob_pct: float,
    umbral_racha: float,
    umbral_poisson: float,
    ev_info: dict,
    min_ev_pct: float,
    min_ev_desbloqueo: float,
    condicion_goles_ok: bool,
) -> tuple[bool, str]:
    media_racha = (r_home + r_away) / 2.0
    min_racha = min(r_home, r_away)
    ev_val = ev_info.get("ev_pct")

    if not condicion_goles_ok or prob_pct < umbral_poisson:
        return False, "normal"

    if ev_info["tiene_cuota"] and (ev_val is None or ev_val < min_ev_pct):
        return False, "normal"

    if (r_home >= umbral_racha and r_away >= umbral_racha) or (
        media_racha >= 60.0 and min_racha >= 45.0
    ):
        return True, "Racha confirmada"

    if min_racha >= 50.0 and media_racha >= 55.0:
        if ev_info["tiene_cuota"]:
            if ev_val is not None and ev_val >= min_ev_desbloqueo and prob_pct >= (umbral_poisson + 2.0):
                return True, f"Desbloqueo +EV ({ev_val:+.1f}%) y Poisson"
        else:
            if prob_pct >= (umbral_poisson + 6.0):
                return True, "Desbloqueo por Poisson alto"

    return False, "normal"


def seleccionar_pronostico_goal(
    markets: dict,
    cuota_x: float = 0.0,
    cuota_o25: float = 0.0,
    cuota_u25: float = 0.0,
    min_ev_pct: float = MIN_EV_PCT_POR_DEFECTO,
    min_ev_desbloqueo: float = MIN_EV_DESBLOQUEO_RACHA,
    home_stats: dict | None = None,
    away_stats: dict | None = None,
    mismo_equipo: bool = False,
    muestra_insuficiente: bool = False,
    umbral_racha: float = UMBRAL_RACHA_POR_DEFECTO,
    umbral_poisson_over: float = UMBRAL_POISSON_OVER_DEFECTO,
    umbral_poisson_under: float = UMBRAL_POISSON_UNDER_DEFECTO,
    min_goles_over: float = MIN_GOLES_ESPERADOS_OVER,
    max_goles_under: float = MAX_GOLES_ESPERADOS_UNDER,
) -> dict:
    resultado_exacto = {
        "under_marcador": markets.get("under_exact_score", "1 - 0"),
        "under_top3": markets.get("top_under_scores", []),
        "over_marcador": markets.get("over_exact_score", "2 - 1"),
        "over_top3": markets.get("top_over_scores", []),
    }

    h_under = float((home_stats or {}).get("under25_rate", 0.0))
    a_under = float((away_stats or {}).get("under25_rate", 0.0))
    h_over = float((home_stats or {}).get("over25_rate", 0.0))
    a_over = float((away_stats or {}).get("over25_rate", 0.0))

    prob_u25_pct = round(float(markets.get("prob_under_25", 0.0)) * 100, 1)
    prob_o25_pct = round(float(markets.get("prob_over_25", 0.0)) * 100, 1)
    goles_esp = float(markets.get("expected_total_goals", 0.0))

    if mismo_equipo:
        return {
            "apostar": False,
            "pick": "NO APOSTAR",
            "motivo": "Se detectó el mismo equipo para local y visitante.",
            "racha_home": h_under,
            "racha_away": a_under,
            "prob_poisson": prob_u25_pct,
            "via_senal": "",
            "resultado_exacto": resultado_exacto,
        }

    if muestra_insuficiente or not home_stats or not away_stats:
        return {
            "apostar": False,
            "pick": "NO APOSTAR",
            "motivo": "Muestra insuficiente (se requieren al menos 6 partidos por equipo).",
            "racha_home": h_under,
            "racha_away": a_under,
            "prob_poisson": prob_u25_pct,
            "via_senal": "",
            "resultado_exacto": resultado_exacto,
        }

    ev_u25 = evaluar_ev_cuota(markets.get("prob_under_25", 0.0), cuota_u25)
    ev_o25 = evaluar_ev_cuota(markets.get("prob_over_25", 0.0), cuota_o25)

    under_ok, via_under = _cumple_racha_o_desbloqueo(
        r_home=h_under,
        r_away=a_under,
        prob_pct=prob_u25_pct,
        umbral_racha=umbral_racha,
        umbral_poisson=umbral_poisson_under,
        ev_info=ev_u25,
        min_ev_pct=min_ev_pct,
        min_ev_desbloqueo=min_ev_desbloqueo,
        condicion_goles_ok=goles_esp <= max_goles_under,
    )

    over_ok, via_over = _cumple_racha_o_desbloqueo(
        r_home=h_over,
        r_away=a_over,
        prob_pct=prob_o25_pct,
        umbral_racha=umbral_racha,
        umbral_poisson=umbral_poisson_over,
        ev_info=ev_o25,
        min_ev_pct=min_ev_pct,
        min_ev_desbloqueo=min_ev_desbloqueo,
        condicion_goles_ok=goles_esp >= min_goles_over,
    )

    if under_ok and over_ok:
        ventaja_under = (prob_u25_pct - umbral_poisson_under) + (
            (ev_u25["ev_pct"] or 0.0) if ev_u25["tiene_cuota"] else 0.0
        )
        ventaja_over = (prob_o25_pct - umbral_poisson_over) + (
            (ev_o25["ev_pct"] or 0.0) if ev_o25["tiene_cuota"] else 0.0
        )
        if ventaja_under >= ventaja_over:
            over_ok = False
        else:
            under_ok = False

    if under_ok:
        return {
            "apostar": True,
            "pick": "UNDER 2.5 GOLES",
            "cuota": cuota_u25,
            "prob": prob_u25_pct,
            "prob_raw": markets.get("prob_under_25", 0.0),
            "cuota_justa": markets.get("fair_under_25"),
            "racha_home": h_under,
            "racha_away": a_under,
            "prob_poisson": prob_u25_pct,
            "via_senal": via_under,
            "resultado_exacto": resultado_exacto,
        }

    if over_ok:
        return {
            "apostar": True,
            "pick": "OVER 2.5 GOLES",
            "cuota": cuota_o25,
            "prob": prob_o25_pct,
            "prob_raw": markets.get("prob_over_25", 0.0),
            "cuota_justa": markets.get("fair_over_25"),
            "racha_home": h_over,
            "racha_away": a_over,
            "prob_poisson": prob_o25_pct,
            "via_senal": via_over,
            "resultado_exacto": resultado_exacto,
        }

    return {
        "apostar": False,
        "pick": "NO APOSTAR",
        "motivo": (
            f"Sin señal válida: -2.5 ({h_under:.1f}% / {a_under:.1f}% · {prob_u25_pct:.1f}%) | "
            f"+2.5 ({h_over:.1f}% / {a_over:.1f}% · {prob_o25_pct:.1f}% · {goles_esp:.2f} goles)."
        ),
        "racha_home": max(h_under, h_over),
        "racha_away": max(a_under, a_over),
        "prob_poisson": max(prob_u25_pct, prob_o25_pct),
        "via_senal": "",
        "resultado_exacto": resultado_exacto,
    }


def _limpiar_todo() -> None:
    st.session_state["form_nonce"] = st.session_state.get("form_nonce", 0) + 1
    st.session_state["ultimo_analisis"] = None


def main() -> None:
    if "form_nonce" not in st.session_state:
        st.session_state["form_nonce"] = 0
    if "ultimo_analisis" not in st.session_state:
        st.session_state["ultimo_analisis"] = None

    nonce = st.session_state["form_nonce"]

    st.title("⚽ Detector de Goles (+2.5 / -2.5) · Capturas Local y Visitante")

    with st.sidebar:
        st.header("Parámetros del Modelo")
        umbral_racha = st.slider(
            "Umbral racha (%)",
            min_value=50.0,
            max_value=80.0,
            value=UMBRAL_RACHA_POR_DEFECTO,
            step=5.0,
            key=f"umbral_racha_{nonce}",
        )
        umbral_poisson_over = st.slider(
            "Umbral Poisson +2.5 (%)",
            min_value=50.0,
            max_value=75.0,
            value=UMBRAL_POISSON_OVER_DEFECTO,
            step=1.0,
            key=f"umbral_p_over_{nonce}",
        )
        min_goles_over = st.slider(
            "Mín. goles esperados +2.5",
            min_value=2.50,
            max_value=3.60,
            value=MIN_GOLES_ESPERADOS_OVER,
            step=0.05,
            key=f"min_g_over_{nonce}",
        )
        umbral_poisson_under = st.slider(
            "Umbral Poisson -2.5 (%)",
            min_value=48.0,
            max_value=75.0,
            value=UMBRAL_POISSON_UNDER_DEFECTO,
            step=1.0,
            key=f"umbral_p_under_{nonce}",
        )
        max_goles_under = st.slider(
            "Máx. goles esperados -2.5",
            min_value=2.00,
            max_value=2.80,
            value=MAX_GOLES_ESPERADOS_UNDER,
            step=0.05,
            key=f"max_g_under_{nonce}",
        )
        min_ev_pct = st.slider(
            "EV mínimo exigido (%)",
            min_value=-5.0,
            max_value=15.0,
            value=MIN_EV_PCT_POR_DEFECTO,
            step=0.5,
            key=f"min_ev_{nonce}",
        )
        min_ev_desbloqueo = st.slider(
            "EV mín. desbloqueo 50% racha (%)",
            min_value=0.0,
            max_value=20.0,
            value=MIN_EV_DESBLOQUEO_RACHA,
            step=0.5,
            key=f"min_ev_desb_{nonce}",
        )
        media_liga = st.number_input(
            "Media goles/equipo aplicada",
            min_value=0.80,
            max_value=2.50,
            value=1.35,
            step=0.05,
            key=f"media_liga_{nonce}",
        )

    st.markdown("#### 1. Capturas de los últimos 10 partidos (con nombre del equipo)")
    c_img1, c_img2 = st.columns(2)
    with c_img1:
        img_local = st.file_uploader(
            "Captura LOCAL (equipo + 10 últimos partidos)",
            type=["png", "jpg", "jpeg"],
            key=f"img_local_{nonce}",
        )
    with c_img2:
        img_vis = st.file_uploader(
            "Captura VISITANTE (equipo + 10 últimos partidos)",
            type=["png", "jpg", "jpeg"],
            key=f"img_vis_{nonce}",
        )

    st.markdown("#### 2. Nombres de equipos y cuotas de Winamax")
    col_eq1, col_eq2 = st.columns(2)
    with col_eq1:
        local_nombre = st.text_input(
            "Equipo Local",
            placeholder="Opcional si sale claro en la captura",
            key=f"local_nombre_{nonce}",
        )
    with col_eq2:
        visitante_nombre = st.text_input(
            "Equipo Visitante",
            placeholder="Opcional si sale claro en la captura",
            key=f"visitante_nombre_{nonce}",
        )

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        cuota_o25_txt = st.text_input(
            "Cuota Winamax (+2.5)",
            placeholder="Ej: 1.88",
            key=f"cuota_o25_{nonce}",
        )
    with col_c2:
        cuota_u25_txt = st.text_input(
            "Cuota Winamax (-2.5)",
            placeholder="Ej: 1.95",
            key=f"cuota_u25_{nonce}",
        )
    with col_c3:
        cuota_x_txt = st.text_input(
            "Cuota Empate (X)",
            placeholder="Ej: 3.40",
            key=f"cuota_x_{nonce}",
        )

    cuota_o25 = _parsear_cuota_texto(cuota_o25_txt)
    cuota_u25 = _parsear_cuota_texto(cuota_u25_txt)
    cuota_x = _parsear_cuota_texto(cuota_x_txt)

    with st.expander("Corregir o escribir marcadores manualmente (opcional)", expanded=False):
        marcadores_local_txt = st.text_input(
            "Marcadores manuales Local (ej: 2-1, 0-0, 2-2, 0-0, 2-0, 1-1, 0-3, 0-0, 0-0, 3-1)",
            value="",
            key=f"m_local_{nonce}",
        )
        marcadores_vis_txt = st.text_input(
            "Marcadores manuales Visitante (ej: 1-0, 2-1, 0-2, 1-1, 1-0, 0-0, 2-0, 1-2, 0-1, 1-1)",
            value="",
            key=f"m_vis_{nonce}",
        )

    col_b1, col_b2 = st.columns([3, 1])
    with col_b1:
        calcular_pulsado = st.button(
            "Calcular pronóstico y valor (+EV)",
            type="primary",
            use_container_width=True,
        )
    with col_b2:
        st.button(
            "Limpiar todo",
            use_container_width=True,
            on_click=_limpiar_todo,
        )

    if calcular_pulsado:
        m_loc_manual = _parsear_marcadores_texto(marcadores_local_txt)
        m_vis_manual = _parsear_marcadores_texto(marcadores_vis_txt)

        m_loc_ocr: list[tuple[int, int]] = []
        m_vis_ocr: list[tuple[int, int]] = []
        eq_loc_ocr = ""
        eq_vis_ocr = ""

        try:
            if img_local is not None:
                ocr_l = extraer_datos_desde_imagen(Image.open(BytesIO(img_local.getvalue())))
                m_loc_ocr = ocr_l["marcadores"]
                eq_loc_ocr = ocr_l["equipo_detectado"]

            if img_vis is not None:
                ocr_v = extraer_datos_desde_imagen(Image.open(BytesIO(img_vis.getvalue())))
                m_vis_ocr = ocr_v["marcadores"]
                eq_vis_ocr = ocr_v["equipo_detectado"]
        except Exception as exc:
            st.error(f"Error leyendo las capturas OCR: {exc}")
            return

        marcadores_local_final = m_loc_manual if m_loc_manual else m_loc_ocr
        marcadores_vis_final = m_vis_manual if m_vis_manual else m_vis_ocr

        nombre_local_final = local_nombre.strip() or eq_loc_ocr or "Equipo Local"
        nombre_vis_final = visitante_nombre.strip() or eq_vis_ocr or "Equipo Visitante"

        home_stats = resumir_marcadores_equipo(marcadores_local_final, es_local=True)
        away_stats = resumir_marcadores_equipo(marcadores_vis_final, es_local=True)

        if not home_stats or not away_stats:
            st.error(
                "Sube las capturas de Local y Visitante (o introduce los marcadores manualmente) para calcular el partido."
            )
            return

        n_home = int(home_stats.get("partidos", 0))
        n_away = int(away_stats.get("partidos", 0))
        muestra_insuf = n_home < 6 or n_away < 6

        ataque_local = home_stats["gf_prom"] / media_liga
        defensa_vis = away_stats["gc_prom"] / media_liga
        ataque_vis = away_stats["gf_prom"] / media_liga
        defensa_local = home_stats["gc_prom"] / media_liga

        lam_home = max(0.25, min(2.80, ataque_local * defensa_vis * media_liga))
        lam_away = max(0.25, min(2.80, ataque_vis * defensa_local * media_liga))

        markets = calculate_poisson_markets(
            lam_home=lam_home,
            lam_away=lam_away,
            winamax_over25=cuota_o25,
            winamax_under25=cuota_u25,
            winamax_draw=cuota_x,
        )

        pronostico = seleccionar_pronostico_goal(
            markets=markets,
            cuota_x=cuota_x,
            cuota_o25=cuota_o25,
            cuota_u25=cuota_u25,
            min_ev_pct=min_ev_pct,
            min_ev_desbloqueo=min_ev_desbloqueo,
            home_stats=home_stats,
            away_stats=away_stats,
            mismo_equipo=normalizar_texto(nombre_local_final) == normalizar_texto(nombre_vis_final),
            muestra_insuficiente=muestra_insuf,
            umbral_racha=umbral_racha,
            umbral_poisson_over=umbral_poisson_over,
            umbral_poisson_under=umbral_poisson_under,
            min_goles_over=min_goles_over,
            max_goles_under=max_goles_under,
        )

        st.session_state["ultimo_analisis"] = {
            "nombre_local_final": nombre_local_final,
            "nombre_vis_final": nombre_vis_final,
            "eq_loc_ocr": eq_loc_ocr,
            "eq_vis_ocr": eq_vis_ocr,
            "n_home": n_home,
            "n_away": n_away,
            "media_liga": media_liga,
            "home_stats": home_stats,
            "away_stats": away_stats,
            "markets": markets,
            "pronostico": pronostico,
            "cuota_o25": cuota_o25,
            "cuota_u25": cuota_u25,
        }

    analisis = st.session_state.get("ultimo_analisis")
    if analisis:
        nombre_local_final = analisis["nombre_local_final"]
        nombre_vis_final = analisis["nombre_vis_final"]
        eq_loc_ocr = analisis.get("eq_loc_ocr", "")
        eq_vis_ocr = analisis.get("eq_vis_ocr", "")
        n_home = analisis["n_home"]
        n_away = analisis["n_away"]
        media_liga = analisis["media_liga"]
        home_stats = analisis["home_stats"]
        away_stats = analisis["away_stats"]
        markets = analisis["markets"]
        pronostico = analisis["pronostico"]
        cuota_o25 = analisis["cuota_o25"]
        cuota_u25 = analisis["cuota_u25"]

        if not st.session_state.get(f"local_nombre_{nonce}", "").strip() and eq_loc_ocr:
            st.caption(f"Nombre detectado en captura Local: `{eq_loc_ocr}`")
        if not st.session_state.get(f"visitante_nombre_{nonce}", "").strip() and eq_vis_ocr:
            st.caption(f"Nombre detectado en captura Visitante: `{eq_vis_ocr}`")

        if n_home < 10:
            st.warning(f"{nombre_local_final}: se detectaron {n_home} marcadores (ideal: 10).")
        if n_away < 10:
            st.warning(f"{nombre_vis_final}: se detectaron {n_away} marcadores (ideal: 10).")

        st.caption(
            f"Partido: **{nombre_local_final}** vs **{nombre_vis_final}** · "
            f"Partidos analizados: `{n_home}` (Local) / `{n_away}` (Visitante) · "
            f"Media goles/equipo aplicada: `{media_liga:.2f}`"
        )

        m_loc_str = ", ".join(home_stats.get("marcadores_usados") or [])
        m_vis_str = ", ".join(away_stats.get("marcadores_usados") or [])
        st.caption(
            f"Marcadores usados → **{nombre_local_final}:** `{m_loc_str or '-'}` | "
            f"**{nombre_vis_final}:** `{m_vis_str or '-'}`"
        )

        st.info(
            f"**Trayectoria en últimos partidos:** {nombre_local_final} ({n_home} PJ) → "
            f"**-2.5:** `{home_stats['under25_rate']:.1f}%` / **+2.5:** `{home_stats['over25_rate']:.1f}%` | "
            f"{nombre_vis_final} ({n_away} PJ) → "
            f"**-2.5:** `{away_stats['under25_rate']:.1f}%` / **+2.5:** `{away_stats['over25_rate']:.1f}%`"
        )

        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Goles esperados",
            f"{markets['expected_total_goals']:.3f}",
            f"λ {markets['lam_home']:.3f} / {markets['lam_away']:.3f}",
        )
        m2.metric(
            "Prob. Over 2.5",
            f"{markets['prob_over_25'] * 100:.1f}%",
            f"Cuota justa: {markets['fair_over_25']}",
        )
        m3.metric(
            "Prob. Under 2.5",
            f"{markets['prob_under_25'] * 100:.1f}%",
            f"Cuota justa: {markets['fair_under_25']}",
        )

        exactos = pronostico["resultado_exacto"]
        if pronostico["apostar"]:
            es_under = pronostico["pick"] == "UNDER 2.5 GOLES"
            marcador_top = exactos["under_marcador"] if es_under else exactos["over_marcador"]
            top3_txt = _formatear_marcadores_top(
                exactos["under_top3"] if es_under else exactos["over_top3"]
            )
            etiqueta_top = "(-2.5)" if es_under else "(+2.5)"
            cuota_usada = cuota_u25 if es_under else cuota_o25
            cuota_justa_pick = pronostico["cuota_justa"]
            ev_info = evaluar_ev_cuota(pronostico["prob_raw"], cuota_usada)
            via_txt = f" · `{pronostico['via_senal']}`" if pronostico.get("via_senal") else ""

            st.success(
                f"### ✅ SEÑAL ACTIVA → {pronostico['pick']} | EXACTO {etiqueta_top} → `{marcador_top}`{via_txt}\n\n"
                f"**Racha:** Local `{pronostico['racha_home']:.1f}%` · Visitante `{pronostico['racha_away']:.1f}%` | "
                f"**Poisson:** `{pronostico['prob_poisson']:.1f}%` (cuota justa `{cuota_justa_pick}`)\n\n"
                f"**Marcadores exactos {etiqueta_top} más probables:** {top3_txt}"
            )

            c_ev1, c_ev2, c_ev3 = st.columns(3)
            c_ev1.metric(
                f"Cuota Winamax ({pronostico['pick']})",
                f"{cuota_usada:.2f}" if cuota_usada > 0 else "-",
            )
            c_ev2.metric(
                "Cuota justa Poisson",
                f"{cuota_justa_pick:.2f}" if cuota_justa_pick else "-",
            )
            if ev_info["tiene_cuota"]:
                c_ev3.metric("Esperanza (EV)", f"{ev_info['ev_pct']:+.1f}%", ev_info["etiqueta"])
            else:
                c_ev3.metric("Esperanza (EV)", "Introduce cuota", "SIN CUOTA")
        else:
            st.warning(f"**{pronostico['pick']}**: {pronostico['motivo']}")

        with st.expander("Matriz de resultados exactos (% probabilidad)", expanded=False):
            st.dataframe(markets["matrix_df"], use_container_width=True)


if __name__ == "__main__":
    main()
