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


st.title("⚽ Detector de Goles (+2.5 / -2.5)")
st.caption("Equipos por captura, cuotas manuales de Winamax y filtro de valor (+2.5 / -2.5).")

st.subheader("1. Captura de partido (opcional)")
archivo = st.file_uploader(
    "Sube una captura del partido para sugerir los equipos",
    type=["png", "jpg", "jpeg", "webp"],
)

with st.expander("Ajustes de lectura y filtros"):
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

if "cuota_over_25_manual" not in st.session_state:
    st.session_state["cuota_over_25_manual"] = 1.44
if "cuota_under_25_manual" not in st.session_state:
    st.session_state["cuota_under_25_manual"] = 2.60

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

st.subheader("3. Promedios reales (últimos 10 partidos y H2H)")
m1, m2 = st.columns(2)
with m1:
    gf_local_10 = st.number_input(
        "Goles a favor Local (prom. 10)", min_value=0.0, max_value=6.0, value=1.40, step=0.05
    )
    gc_local_10 = st.number_input(
        "Goles en contra Local (prom. 10)", min_value=0.0, max_value=6.0, value=1.10, step=0.05
    )
with m2:
    gf_vis_10 = st.number_input(
        "Goles a favor Visitante (prom. 10)", min_value=0.0, max_value=6.0, value=1.20, step=0.05
    )
    gc_vis_10 = st.number_input(
        "Goles en contra Visitante (prom. 10)", min_value=0.0, max_value=6.0, value=1.20, step=0.05
    )

usar_h2h = st.checkbox("Incluir promedio de goles en H2H", value=False)
goles_h2h_prom = None
if usar_h2h:
    goles_h2h_prom = st.number_input(
        "Promedio goles totales H2H", min_value=0.0, max_value=8.0, value=2.40, step=0.10
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
