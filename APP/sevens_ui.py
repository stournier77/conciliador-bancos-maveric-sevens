"""Estilo visual común Sevens; no modifica cálculos ni formatos del Excel."""
from pathlib import Path
import base64
import html
import streamlit as st

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def apply_design():
    st.markdown((ASSETS / "sevens.css").read_text(encoding="utf-8"), unsafe_allow_html=True)


def header(name, subtitle):
    st.markdown(f'''<div class="sevens-hero"><div class="sevens-eyebrow">SEVENS TRAVEL / CONCILIACIONES</div>
<h1>Conciliador {html.escape(name)}</h1><p>{html.escape(subtitle)}</p></div>''', unsafe_allow_html=True)


def file_heading(text):
    st.markdown(f'<div class="sevens-file-heading">{html.escape(text)}</div>', unsafe_allow_html=True)


def footer():
    logo = ASSETS / "sevens_logo.png"
    if logo.exists():
        encoded = base64.b64encode(logo.read_bytes()).decode("ascii")
        content = f'<img src="data:image/png;base64,{encoded}" alt="Sevens Travel" class="sevens-logo">'
    else:
        content = '<span class="sevens-wordmark">SEVENS <small>TRAVEL</small></span>'
    st.markdown(f'<footer class="sevens-footer">{content}</footer>', unsafe_allow_html=True)


def sidebar_brand(name):
    encoded = base64.b64encode((ASSETS / "app_icon.png").read_bytes()).decode("ascii")
    st.markdown(f'''<div class="sevens-sidebar-brand"><img src="data:image/png;base64,{encoded}" alt="Conciliador {html.escape(name)}"><span>CONCILIADOR {html.escape(name.upper())}</span></div>''', unsafe_allow_html=True)


def sidebar_info(name, version, date):
    st.markdown(f'''<div class="sevens-device-card"><div class="sevens-device-row"><span>Equipo</span><strong>{html.escape(name)}</strong></div><div class="sevens-device-row"><span>Versión</span><strong>{html.escape(version)}</strong></div><div class="sevens-device-date">Creada el {html.escape(date)}</div></div>''', unsafe_allow_html=True)
