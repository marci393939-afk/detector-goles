import math
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image, ImageOps

st.set_page_config(
    page_title="Detector +2.5 / -2.5 Goles",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
HISTORY_FILE = BASE_DIR / "historial_pronosticos.csv"

# Rutas habituales de Tesseract en Windows (en Linux/Streamlit Cloud se ignora y usa el binario del sistema)
CANDIDATE_TESSERACT = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
]
for candidate in CANDIDATE_TESSERACT:
    if candidate.exists():
        pytesseract.pytesseract.tesseract_cmd = str(candidate)
        break


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def poisson_under_25(lam: float) -> float:
    p_under = poisson_pmf(0, lam) + poisson_pmf(1, lam) + poisson_pmf(2, lam)
    return min(0.99, max(0.01, p_under))


def solve_lambda_from_over_prob(target_over: float) -> float:
    clamped = min(0.95, max(0.05, target_over))
    lo, hi = 0.25, 6.50
    for _ in range(45):
        mid = (lo + hi) / 2.0
        if (1.0 - poisson_under_25(mid)) < clamped:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def ocr_image_auto(img: Image.Image) -> str:
    rgb = img.convert("RGB")
    gray = ImageOps.grayscale(rgb)

    # Si el fondo es oscuro (típico de casas de apuestas y webs de estadísticas), invertimos
    small = gray.resize((64, 64))
    avg_sample = sum(small.getdata()) / (64 * 64)
    if avg_sample < 115:
        gray = ImageOps.invert(gray)

    gray = ImageOps.autocontrast(gray)
    w, h = gray.size
    if w < 1600:
        gray = gray.resize((w * 2, h * 2), Image.Resampling.LANCZOS)

    text_block = pytesseract.image_to_string(gray, config="--psm 6")
    text_sparse = pytesseract.image_to_string(gray, config="--psm 11")
    return f"{text_block}\n{text_sparse}".strip()


def _parse_decimal_odds_from_chunk(chunk: str) -> list[float]:
    if not chunk:
        return []
    # Evita fechas tipo 21.11.2026 o horas tipo 13:30
    cleaned = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", " ", chunk)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}\b", " ", cleaned)

    matches = re.findall(r"(?<![A-Za-z0-9./-])\d{1,2}[.,]\d{2}(?![A-Za-z0-9./-])", cleaned)
    odds = []
    seen = set()
    for m in matches:
        val = float(m.replace(",", "."))
        if 1.01 <= val <= 50.0:
            key = f"{val:.2f}"
            if key not in seen:
                seen.add(key)
                odds.append(val)
    return odds


def extract_winamax_odds(text: str) -> list[float]:
    """Extrae exclusivamente las cuotas de Winamax."""
    if not text:
        return []

    winamax_pattern = re.compile(r"\b(winamax|wlnamax|w1namax|win\s*a\s*max)\b", re.IGNORECASE)
    other_bookies_pattern = re.compile(
        r"\b(bet365|sportium|codere|william\s*hill|bwin|betfair|888sport|marathonbet|luckia|kirolbet|paf|versus|zebet|unibet)\b",
        re.IGNORECASE,
    )

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for idx, line in enumerate(lines):
        if winamax_pattern.search(line):
            collected: list[float] = []
            for follow in lines[idx : idx + 10]:
                if follow != line and other_bookies_pattern.search(follow):
                    break
                collected.extend(_parse_decimal_odds_from_chunk(follow))
                dedup = []
                seen = set()
                for val in collected:
                    key = f"{val:.2f}"
                    if key not in seen:
                        seen.add(key)
                        dedup.append(val)
                if len(dedup) >= 3:
                    return dedup[:5]

    return []


def extract_teams_from_text(text: str) -> tuple[str, str]:
    if not text:
        return "", ""

    known_teams = [
        ("Manchester City", [r"\bmanchester\s+city\b", r"\bciudad\s+de\s+manchester\b"]),
        ("Fulham", [r"\bfulham\b"]),
    ]
    found_known = []
    for canonical, patterns in known_teams:
        if any(re.search(p, text, flags=re.IGNORECASE) for p in patterns):
            found_known.append(canonical)
    if len(found_known) >= 2:
        return found_known[0], found_known[1]

    ignore_words = {
        "winamax", "flashscore", "besoccer", "cuotas", "resultado", "final",
        "goles", "mas", "más", "menos", "empate", "local", "visitante",
        "hoy", "directo", "previa", "estadisticas", "estadísticas", "apuestas",
        "1x2", "2.5", "+2.5", "-2.5", "over", "under", "liga", "copa",
        "bet365", "sportium", "codere", "bwin", "betfair", "stream", "alineaciones",
        "clasificacion", "clasificación", "noticias", "video", "vídeo", "h2h",
        "futbol", "fútbol", "inglaterra", "espana", "españa", "premier", "league",
        "jornada", "partido", "resumen", "videoprevia", "anuncio", "mostrar",
        "integra", "íntegra", "nueva", "ventana", "handicap", "asiatico", "asiático",
        "ambos", "equipos", "marcaran", "marcarán", "hacer", "una", "apuesta",
        "categoria", "categoría", "ciudad", "vivo", "uve", "city"
    }

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    candidates = []
    for line in lines:
        if any(ch in line for ch in (">", "/", ":", "@", "|", "(", ")", "[", "]")):
            continue
        clean = re.sub(r"\b\d{1,2}[.,]\d{2}\b", " ", line)
        clean = re.sub(r"[^A-Za-zÀ-ÿ\s]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        low = clean.lower()
        words = low.split()
        if not clean or len(clean) < 4 or len(words) < 1 or len(words) > 4:
            continue
        if any(w in ignore_words for w in words):
            continue
        if clean not in candidates:
            candidates.append(clean)

    if len(candidates) >= 2:
        return candidates[0], candidates[1]
    if len(candidates) == 1:
        return candidates[0], ""
    return "", ""


def calculate_model(
    o1: float | None,
    ox: float | None,
    o2: float | None,
    o_over: float | None,
    o_under: float | None,
    live_score: str,
) -> dict | None:
    has_1x2 = all(v is not None and v > 1.0 for v in (o1, ox, o2))
    has_line = all(v is not None and v > 1.0 for v in (o_over, o_under))

    if not has_1x2 and not has_line:
        return None

    if has_line:
        inv_over = 1.0 / o_over
        inv_under = 1.0 / o_under
        total = inv_over + inv_under
        p_over = inv_over / total
        p_under = inv_under / total
        lam = solve_lambda_from_over_prob(p_over)
    else:
        i1, ix, i2 = 1.0 / o1, 1.0 / ox, 1.0 / o2
        tot = i1 + ix + i2
        p1, px, p2 = i1 / tot, ix / tot, i2 / tot
        balance = 1.0 - abs(p1 - p2) * 0.45 - px * 0.35
        lam = min(4.20, max(1.25, 2.35 + (balance - 0.55) * 1.40))

        m_score = re.search(r"(\d+)\s*[-–]\s*(\d+)", live_score or "")
        if m_score:
            goals_now = int(m_score.group(1)) + int(m_score.group(2))
            rem = max(0, 3 - goals_now)
            lam = max(lam, goals_now + 0.40) if goals_now >= 3 else (goals_now + rem * 0.58)

        p_under = poisson_under_25(lam)
        p_over = 1.0 - p_under

    is_over = p_over >= p_under
    verdict = "+2.5 GOLES" if is_over else "-2.5 GOLES"
    chosen_prob = p_over if is_over else p_under
    fair_odd = (1.0 / chosen_prob) if chosen_prob > 0 else 0.0

    return {
        "verdict": verdict,
        "p_over": p_over,
        "p_under": p_under,
        "lambda": lam,
        "fair_odd": fair_odd,
    }


def save_to_history(row: dict) -> None:
    df_new = pd.DataFrame([row])
    if HISTORY_FILE.exists():
        df_old = pd.read_csv(HISTORY_FILE)
        df_all = pd.concat([df_new, df_old], ignore_index=True)
    else:
        df_all = df_new
    df_all.to_csv(HISTORY_FILE, index=False)


def apply_ocr_to_state(img: Image.Image) -> None:
    raw_text = ocr_image_auto(img)
    st.session_state["ocr_text"] = raw_text
    h_det, a_det = extract_teams_from_text(raw_text)
    odds_winamax = extract_winamax_odds(raw_text)

    st.session_state["home_team"] = h_det
    st.session_state["away_team"] = a_det
    st.session_state["odd_1"] = float(odds_winamax[0]) if len(odds_winamax) >= 1 else 0.0
    st.session_state["odd_x"] = float(odds_winamax[1]) if len(odds_winamax) >= 2 else 0.0
    st.session_state["odd_2"] = float(odds_winamax[2]) if len(odds_winamax) >= 3 else 0.0
    st.session_state["odd_over"] = float(odds_winamax[3]) if len(odds_winamax) >= 5 else 0.0
    st.session_state["odd_under"] = float(odds_winamax[4]) if len(odds_winamax) >= 5 else 0.0
    st.session_state["winamax_found"] = len(odds_winamax) >= 3
    st.session_state["ocr_error"] = ""


def process_new_capture(img: Image.Image, label: str, force: bool = False) -> None:
    if not force and st.session_state.get("last_processed_label") == label:
        return
    st.session_state["last_processed_label"] = label
    try:
        apply_ocr_to_state(img)
    except Exception as exc:
        st.session_state["ocr_error"] = str(exc)


st.title("Detector 1X2 a +2.5 / -2.5 Goles")
st.caption("Detección automática de cuotas de Winamax desde la captura + cálculo Poisson.")

col_left, col_right = st.columns([1.35, 1.0], gap="large")

with col_left:
    st.subheader("1. Cargar captura del partido")
    source_mode = st.radio(
        "Origen de la captura",
        ["Subir archivo", "Última imagen de una carpeta"],
        horizontal=True,
    )

    loaded_img: Image.Image | None = None
    loaded_label = ""

    if source_mode == "Subir archivo":
        uploaded = st.file_uploader(
            "Selecciona tu captura (PNG, JPG, WEBP)",
            type=["png", "jpg", "jpeg", "webp"],
        )
        if uploaded is not None:
            loaded_img = Image.open(uploaded)
            loaded_label = f"{uploaded.name}_{uploaded.size}"
    else:
        default_dir = str(Path.home() / "Pictures")
        watch_dir = st.text_input("Ruta de la carpeta de capturas", value=default_dir)
        if os.path.isdir(watch_dir):
            imgs = [
                p for p in Path(watch_dir).iterdir()
                if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
            imgs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            if imgs:
                latest = imgs[0]
                st.info(f"Imagen más reciente: **{latest.name}**")
                loaded_img = Image.open(latest)
                loaded_label = f"{latest.name}_{latest.stat().st_mtime}"
            else:
                st.warning("No se encontraron imágenes en esa carpeta.")
        else:
            st.warning("La carpeta indicada no existe.")

    if loaded_img is not None:
        process_new_capture(loaded_img, loaded_label)
        st.image(
            loaded_img,
            caption=f"Captura analizada ({loaded_img.width}x{loaded_img.height} px)",
            use_container_width=True,
        )
        if st.button("Reescanear captura automáticamente"):
            process_new_capture(loaded_img, loaded_label, force=True)
            st.rerun()
        if st.session_state.get("winamax_found") is False:
            st.warning(
                "No se detectaron cuotas de Winamax en esta captura. "
                "Las cuotas se han dejado en 0.00 para no usar las de otras casas."
            )

    if st.session_state.get("ocr_error"):
        st.error(f"Error al ejecutar Tesseract OCR: {st.session_state['ocr_error']}")

    with st.expander("Ver texto detectado automáticamente en la captura"):
        st.text(st.session_state.get("ocr_text", "(Sin texto leído aún)"))

    st.subheader("2. Partido y cuotas de Winamax")
    c1, c2, c3 = st.columns(3)
    home_team = c1.text_input("Equipo Local", value=st.session_state.get("home_team", ""))
    away_team = c2.text_input("Equipo Visitante", value=st.session_state.get("away_team", ""))
    live_score = c3.text_input(
        "Marcador en vivo (opcional)",
        value=st.session_state.get("live_score", ""),
        placeholder="Ej. 0-0",
    )

    q1, qx, q2 = st.columns(3)
    odd_1 = q1.number_input(
        "Cuota 1 (Winamax)",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        value=float(st.session_state.get("odd_1", 0.0)),
    )
    odd_x = qx.number_input(
        "Cuota X (Winamax)",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        value=float(st.session_state.get("odd_x", 0.0)),
    )
    odd_2 = q2.number_input(
        "Cuota 2 (Winamax)",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        value=float(st.session_state.get("odd_2", 0.0)),
    )

    qo, qu = st.columns(2)
    odd_over = qo.number_input(
        "Cuota +2.5 Goles (Winamax, opcional)",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        value=float(st.session_state.get("odd_over", 0.0)),
    )
    odd_under = qu.number_input(
        "Cuota -2.5 Goles (Winamax, opcional)",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        value=float(st.session_state.get("odd_under", 0.0)),
    )

with col_right:
    st.subheader("3. Veredicto Final")
    res = calculate_model(
        odd_1 if odd_1 > 1 else None,
        odd_x if odd_x > 1 else None,
        odd_2 if odd_2 > 1 else None,
        odd_over if odd_over > 1 else None,
        odd_under if odd_under > 1 else None,
        live_score,
    )

    if res is None:
        st.info("Sube una captura con cuotas de **Winamax** (**1 / X / 2** o **+2.5 / -2.5**) para calcular el veredicto.")
    else:
        st.success(f"### Recomendación: {res['verdict']}")
        m1, m2 = st.columns(2)
        m1.metric("Prob. +2.5 Goles", f"{res['p_over'] * 100:.1f}%")
        m2.metric("Prob. -2.5 Goles", f"{res['p_under'] * 100:.1f}%")
        m3, m4 = st.columns(2)
        m3.metric("Goles Esperados (λ)", f"{res['lambda']:.2f}")
        m4.metric("Cuota Justa", f"@{res['fair_odd']:.2f}")

        match_name = f"{home_team.strip()} vs {away_team.strip()}".strip(" vs") or "Partido sin nombre"
        if st.button("Guardar pronóstico en historial CSV", type="primary"):
            save_to_history({
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "partido": match_name,
                "1X2": f"{odd_1:.2f} / {odd_x:.2f} / {odd_2:.2f}",
                "lambda": round(res["lambda"], 2),
                "prob_over25": f"{res['p_over'] * 100:.1f}%",
                "prob_under25": f"{res['p_under'] * 100:.1f}%",
                "veredicto": res["verdict"],
            })
            st.toast("Pronóstico guardado en historial_pronosticos.csv")

st.divider()
st.subheader("4. Historial guardado")
if HISTORY_FILE.exists():
    st.dataframe(pd.read_csv(HISTORY_FILE), use_container_width=True)
else:
    st.caption("Aún no hay pronósticos guardados en `historial_pronosticos.csv`.")