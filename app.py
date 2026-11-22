import math
import re
from io import BytesIO

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
    "HACER UNA APUESTA",
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


def _es_token_basura_ocr(token: str) -> bool:
    """Detecta tokens cortos deformados típicos de iconos mal leídos (ej. 'ESgsS', '_ ad')."""
    limpio = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", token)
    if len(limpio) < 2:
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


def extraer_cuotas_winamax(texto_ocr: str) -> dict[str, str | None]:
    """Busca la fila de WINAMAX y extrae las cuotas 1, X y 2."""
    for linea in texto_ocr.splitlines():
        if "WINAMAX" in linea.upper():
            normalizada = linea.replace(",", ".")
            cuotas: list[str] = []

            for match in re.finditer(r"(?<!\d)\d+\.\d{1,2}(?!\d)", normalizada):
                val = float(match.group(0))
                if 1.05 <= val <= 25.0:
                    cuotas.append(f"{val:.2f}")

            if len(cuotas) < 3:
                for match in re.finditer(r"(?<!\d)\d{3}(?!\d)", normalizada):
                    val = int(match.group(0)) / 100.0
                    texto_val = f"{val:.2f}"
                    if 1.05 <= val <= 25.0 and len(cuotas) < 3:
                        cuotas.append(texto_val)

            if len(cuotas) >= 3:
                c1 = cuotas[0]
                restantes = sorted(cuotas[1:3], key=lambda x: float(x), reverse=True)
                return {
                    "cuota_1": c1,
                    "cuota_x": restantes[0],
                    "cuota_2": restantes[1],
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
        if _es_token_basura_ocr(limpia_parte):
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
    min_edge: float = 0.035,
    min_cuota_over: float = 1.45,
    min_cuota_under: float = 1.35,
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
        "xg
