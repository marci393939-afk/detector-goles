import json
import math
import os
import re
import unicodedata
from io import BytesIO
from pathlib import Path

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
CACHE_PAISES_PATH = Path("equipos_paises.json")
UMBRAL_RACHA_POR_DEFECTO = 60.0
UMBRAL_POISSON_POR_DEFECTO = 58.0

PAISES_BASE_INICIALES = {
    "muranga": "Kenia",
    "murang'a": "Kenia",
    "muranga seal": "Kenia",
    "murang'a seal": "Kenia",
    "kcb": "Kenia",
    "gor mahia": "Kenia",
    "tusker": "Kenia",
    "afc leopards": "Kenia",
    "bandari": "Kenia",
    "kakamega homeboyz": "Kenia",
    "kenya police": "Kenia",
    "kariobangi sharks": "Kenia",
    "sofapaka": "Kenia",
    "ulinzi stars": "Kenia",
    "bidco united": "Kenia",
    "nairobi city stars": "Kenia",
    "post rangers": "Kenia",
    "shabana": "Kenia",
    "mathare united": "Kenia",
    "mara sugar": "Kenia",
    "kolkheti 1913": "Georgia",
    "bolnisi": "Georgia",
    "sioni bolnisi": "Georgia",
    "telavi": "Georgia",
    "samtredia": "Georgia",
    "merani martvili": "Georgia",
    "gareji": "Georgia",
    "fc gareji sagarejo": "Georgia",
    "dusheti": "Georgia",
    "odishi 1919": "Georgia",
    "shturmi": "Georgia",
    "gori": "Georgia",
    "walter ferretti": "Nicaragua",
    "sport sebaco": "Nicaragua",
    "muang loei": "Tailandia",
    "nong bua pitchaya": "Tailandia",
    "kasetsart": "Tailandia",
    "khonkaen utd": "Tailandia",
    "khon kaen united": "Tailandia",
    "nakhon ratchasima": "Tailandia",
    "nakhon ratchasima fc": "Tailandia",
    "songkhla": "Tailandia",
    "police tero": "Tailandia",
    "sukhothai": "Tailandia",
    "al nasr": "Egipto",
    "tersana": "Egipto",
    "svay rieng": "Camboya",
    "machida": "Japón",
    "sao paulo": "Brasil",
    "sao paulo fc": "Brasil",
    "remo": "Brasil",
    "kokand 1912": "Uzbekistán",
    "xorazm urganch": "Uzbekistán",
}

PAISES_OCR_MAPA = {
    "KENIA": "Kenia",
    "KENYA": "Kenia",
    "GEORGIA": "Georgia",
    "NICARAGUA": "Nicaragua",
    "TAILANDIA": "Tailandia",
    "THAILAND": "Tailandia",
    "EGIPTO": "Egipto",
    "EGYPT": "Egipto",
    "ESPANA": "España",
    "ESPAÑA": "España",
    "SPAIN": "España",
    "INGLATERRA": "Inglaterra",
    "ENGLAND": "Inglaterra",
    "FRANCIA": "Francia",
    "FRANCE": "Francia",
    "ALEMANIA": "Alemania",
    "GERMANY": "Alemania",
    "ITALIA": "Italia",
    "ITALY": "Italia",
    "PORTUGAL": "Portugal",
    "ARMENIA": "Armenia",
    "UCRANIA": "Ucrania",
    "UKRAINE": "Ucrania",
    "BRASIL": "Brasil",
    "BRAZIL": "Brasil",
    "ARGENTINA": "Argentina",
    "COLOMBIA": "Colombia",
    "MEXICO": "México",
    "MÉXICO": "México",
    "CHILE": "Chile",
    "PERU": "Perú",
    "PERÚ": "Perú",
    "TURQUIA": "Turquía",
    "TURQUÍA": "Turquía",
    "GRECIA": "Grecia",
    "POLONIA": "Polonia",
    "RUMANIA": "Rumanía",
    "BULGARIA": "Bulgaria",
    "SERBIA": "Serbia",
    "CROACIA": "Croacia",
    "NORUEGA": "Noruega",
    "SUECIA": "Suecia",
    "DINAMARCA": "Dinamarca",
    "FINLANDIA": "Finlandia",
    "JAPON": "Japón",
    "JAPÓN": "Japón",
    "JPN": "Japón",
    "COREA DEL SUR": "Corea del Sur",
    "MARRUECOS": "Marruecos",
    "SUDAFRICA": "Sudáfrica",
    "SUDÁFRICA": "Sudáfrica",
    "NIGERIA": "Nigeria",
    "GHANA": "Ghana",
    "TANZANIA": "Tanzania",
    "UGANDA": "Uganda",
    "ETIOPIA": "Etiopía",
    "ETIOPÍA": "Etiopía",
    "CAMBOYA": "Camboya",
    "CAMBODIA": "Camboya",
    "CAM": "Camboya",
    "UZBEKISTAN": "Uzbekistán",
    "UZBEKISTÁN": "Uzbekistán",
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
    "celta de vigo": "Celta
