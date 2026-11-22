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
    # Alternancia brusca de mayúsculas y minúsculas sin espacios (ej. 'ESgsS')
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

        # Quita etiquetas de streaming sin borrar el resto de la línea
        limpia = re.sub(r"\bSTREAM\b", " ", limpia, flags=re.IGNORECASE)
        limpia = re.sub(r"\s+", " ", limpia).strip(" |")
        if not limpia:
            continue

        # Ignora líneas con guion bajo o fórmulas/igualdades tipo 'FEN = N'
        if "_" in limpia or "=" in limpia:
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

        # Ignora líneas formadas íntegramente por tokens basura sin una palabra limpia
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

            # Primero busca cuotas con dos decimales (ej. 4.80, 1.84)
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
        if _es_token
