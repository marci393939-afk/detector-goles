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


def extraer_cuotas_winamax(texto_ocr: str) -> dict[str, float | None]:
    """Busca la fila de WINAMAX y extrae las cuotas 1, X y 2 (con o sin punto decimal)."""
    for linea in texto_ocr.splitlines():
        if "WINAMAX" in linea.upper():
            normalizada = linea.replace(",", ".")
            cuotas: list[float] = []

            for match in re.finditer(r"\b\d+\.\d{2}\b", normalizada):
                val = float(match.group(0))
                if 1.05 <= val <= 25.0:
                    cuotas.append(val)

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
    local = fuente[0] if
