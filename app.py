import math
import re
from io import BytesIO

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import streamlit as st


st.set_page_config(
    page_title="Detector de Goles (+2.5 / -2.5)",
    page_icon="⚽",
    layout="centered",
)

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
    "MAS DE",
    "MENOS DE",
    "AMBOS",
    "FLASHSCORE",
    "PARTIDO",
    "RESUMEN",
    "ESTADISTICAS",
    "BET>",
    "BET365",
    "SPORTIUM",
    "1XBET",
    "APUESTA EN",
    "DISPONIBLES",
    "JORNADA",
    "NUEVA VENTANA",
    "PREMIER LEAGUE",
    "HANDICAP ASIATICO",
}


def preparar_imagen_ocr(imagen: Image.Image) -> Image.Image:
    """Mejora contraste y escala la imagen para facilitar la lectura de Tesseract."""
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


def limpiar_lineas_ocr(texto_ocr: str) -> list[str]:
    """Limpia el texto devuelto por Tesseract y descarta ruido de interfaz."""
    lineas_limpias = []
    for linea in texto_ocr.splitlines():
        limpia = linea.strip()
        if not limpia:
            continue

        # Quita etiquetas de streaming sin borrar el resto de la línea
        limpia = re.sub(r"\bSTREAM\b", " ", limpia, flags=re.IGNORECASE)
        limpia = re.sub(r"\s+", " ", limpia).strip(" |")
        if not limpia:
            continue

        # Ignora fórmulas/igualdades tipo 'FEN = N'
        if "=" in limpia:
            continue

        # Ignora marcadores tipo 0-0, relojes tipo 7:06 o fechas tipo 22.11.2026
        if re.fullmatch(r"\d{1,2}[:.\-]\d{1,2}(?:[:.\-]\d{2,4})?", limpia):
            continue

        # Ignora cabeceras con '@' o filas tipo '1 Xx 2'
        if limpia.startswith("@") or re.fullmatch(r"1\s+[xX]{1,2}\s+2", limpia):
            continue

        mayus = limpia.upper()
        if any(palabra in mayus for palabra in PALABRAS_RUIDO):
            continue

        # Ignora filas compuestas solo por siglas cortas en mayúsculas (ej. 'XN PPK GA')
        tokens = limpia.split()
        if tokens and all(tok.isupper() and len(tok) <= 4 for tok in tokens):
            continue

        letras = sum(c.isalpha() for c in limpia)
        if letras < 2:
            continue

        lineas_limpias.append(limpia)

    return lineas_limpias


def extraer_cuotas_winamax(texto_ocr: str) -> dict[str, float | None]:
    """Busca la fila de WINAMAX y extrae las cuotas 1, X y 2 (con o sin punto decimal)."""
    for linea in texto_ocr.splitlines():
        if "WINAMAX" in linea.upper():
            normalizada = linea.replace(",", ".")
            cuotas: list[float] = []

            # Primero busca cuotas con dos decimales (ej. 4.80, 1.52)
            for match in re.finditer(r"\b\d+\.\d{2}\b", normalizada):
                val = float(match.group(0))
                if 1.05 <= val <= 25.0:
                    cuotas.append(val)

            # Si faltan cuotas, rescata números de 3 dígitos sin punto (ej. 480 -> 4.80, 152 -> 1.52)
            if len(cuotas) < 3:
                for match in re.finditer(r"\b(\d{3})\b", normalizada):
                    val = int(match.group(1)) / 100.0
                    if 1.05 <= val <= 25.0 and val not in cuotas:
                        cuotas.append(round(val, 2))

            if len(cuotas) >= 3:
                return {
                    "cuota_1": cuotas[0],
                    "cuota_x": cuotas[1],
                    "cuota_2": cuotas[2],
                }
            if len(cuotas) == 2:
                return {
                    "cuota_1": cuotas[0],
                    "cuota_x": None,
                    "cuota_2": cuotas[1],
                }
            if len(cuotas) == 1:
                return {
                    "cuota_1": cuotas[0],
                    "cuota_x": None,
                    "cuota_2": None,
                }

    return {"cuota_1": None, "cuota_x": None, "cuota_2": None}


def _extraer_equipos_de_linea(linea: str) -> list[str]:
    partes = re.split(r"\s*(?:>|\bvs\.?\b|\s-\s)\s*", linea, flags=re.IGNORECASE)
    encontrados: list[str] = []
    for parte in partes:
        limpia_parte = parte.strip(" -|>/\\")
        if limpia_parte.isupper() and len(limpia_parte) <= 4:
            continue
        if 2 <= len(limpia_parte) <= 35 and limpia_parte not in encontrados:
            encontrados.append(limpia_parte)
    return encontrados


def sugerir_equipos_candidatos(texto_ocr: str) -> tuple[str, str]:
    """Sugiere equipo local y visitante priorizando líneas con separador de cruce ('>' o 'vs')."""
    lineas = limpiar_lineas_ocr(texto_ocr)
    candidatos_cruce: list[str] = []
    equipos: list[str] = []

    for linea in lineas:
        if "WINAMAX" in linea.upper():
            continue
        if re.search(r"[|{}~<>\\]", linea) and ">" not in linea:
            continue
        if re.search(r"\d", linea):
            continue

        partes_linea = _extraer_equipos_de_linea(linea)
        if ">" in linea or re.search(r"\bvs\.?\b", linea, flags=re.IGNORECASE):
            for eq in partes_linea:
                if eq not in candidatos_cruce:
                    candidatos_cruce.append(eq)

        for eq in partes_linea:
            if eq not in equipos:
                equipos.append(eq)

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
    peso_h2h: float = 0.20,
) -> tuple[float, float]:
    """
    Calcula goles esperados moderando picos extremos con medias de 10 partidos
    y un peso opcional de enfrentamientos directos (H2H).
    """
    gf_l = min(max(gf_local_10, 0.2), 3.8)
    gc_l = min(max(gc_local_10, 0.2), 3.8)
    gf_v = min(max(gf_vis_10, 0.2), 3.8)
    gc_v = min(max(gc_vis_10, 0.2), 3.8)

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


def poisson_pmf(k: int, lam: float) -> float:
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)


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
    min_edge: float = 0.07,
    min_cuota_over: float = 1.60,
    min_cuota_under: float = 1.45,
) -> dict:
    """Evalúa +2.5 y -2.5 goles exigiendo ventaja mínima sobre la cuota."""
    probs = probs_over_under_25(xg_local, xg_visitante)
    p_over = probs["p_over_25"]
    p_under = probs["p_under_25"]

    opciones = []

    if cuota_over_25 and cuota_over_25 > 1.0:
        imp_over = 1.0 / cuota_over_25
        edge_over = p_over - imp_over
        ev_over = (p_over * cuota_over_25) - 1.0
        if edge_over >= min_edge and cuota_over_25 >= min_cuota_over:
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
        if edge_under >= min_edge and cuota_under_25 >= min_cuota_under:
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
            "motivo": "Sin ventaja mínima suficiente o cuota fuera del filtro de seguridad.",
            "xg_total": probs["xg_total"],
            "p
