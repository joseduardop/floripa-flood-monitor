"""
dataviz.py - dashboard de risco de alagamento (Florianopolis)

le a saida classificada do interpretador em landing/interpretador_risco/treated/
e mostra: mapa das estacoes coloridas por risco, cards por classe,
serie temporal das ultimas 12h e tabela das leituras.

uso:
    streamlit run dataviz.py
"""
import json
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

BASE = Path(__file__).parent
TREATED_DIR = BASE / "landing" / "interpretador_risco" / "treated"

# cor por classe de risco (hex pro texto/cards, rgb pro mapa pydeck)
CORES = {
    "BAIXO": {"hex": "#2ecc71", "rgb": [46, 204, 113]},
    "MEDIO": {"hex": "#f1c40f", "rgb": [241, 196, 15]},
    "ALTO": {"hex": "#e67e22", "rgb": [230, 126, 34]},
    "CRITICO": {"hex": "#c0392b", "rgb": [192, 57, 43]},
}
ORDEM = ["CRITICO", "ALTO", "MEDIO", "BAIXO"]

st.set_page_config(page_title="Monitor de Alagamento - Floripa", page_icon="🌧️", layout="wide")


@st.cache_data(ttl=5)
def carregar():
    # le todos os snapshots treated e monta um dataframe longo (uma linha por estacao/leitura)
    if not TREATED_DIR.exists():
        return pd.DataFrame()
    linhas = []
    for arq in sorted(TREATED_DIR.glob("*.json")):
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ts = pd.to_datetime(d.get("ts_processamento"), utc=True, errors="coerce")
        for r in d.get("resultados", []):
            linhas.append({
                "ts": ts,
                "codestacao": r.get("codestacao"),
                "nome": r.get("nome"),
                "lat": r.get("lat"),
                "lon": r.get("lon"),
                "chuva_1h": r.get("chuva_1h"),
                "chuva_24h": r.get("chuva_24h"),
                "chuva_72h": r.get("chuva_72h"),
                "precip_prev_6h": r.get("precip_prev_6h"),
                "umidade_solo": r.get("umidade_solo"),
                "score": r.get("score_risco"),
                "classe": r.get("classificacao"),
            })
    df = pd.DataFrame(linhas)
    return df.dropna(subset=["ts"]) if not df.empty else df


st.sidebar.title("Monitor de Alagamento")
st.sidebar.caption("Florianopolis / SC")
auto = st.sidebar.toggle("Auto-atualizar", value=True)
intervalo = st.sidebar.slider("Intervalo (s)", 5, 60, 15)
if auto and st_autorefresh:
    st_autorefresh(interval=intervalo * 1000, key="refresh")
elif auto and st_autorefresh is None:
    st.sidebar.warning("instale streamlit-autorefresh para o refresh automatico")

df = carregar()
if df.empty:
    st.title("Risco de Alagamento - Tempo Real")
    st.info("Aguardando a primeira leitura do interpretador...")
    st.stop()

ultimo = df["ts"].max()
atual = df[df["ts"] == ultimo].copy()
ts_local = ultimo.tz_convert("America/Sao_Paulo").strftime("%d/%m/%Y %H:%M:%S")

st.title("Risco de Alagamento - Tempo Real")
st.caption(f"Ultima atualizacao: {ts_local} (BRT)  ·  {len(atual)} estacoes monitoradas")

contagem = atual["classe"].value_counts().to_dict()
for col, classe in zip(st.columns(4), ORDEM):
    cor = CORES[classe]["hex"]
    col.markdown(
        f"""
        <div style="background:{cor};border-radius:12px;padding:16px;text-align:center;color:#fff;">
            <div style="font-size:13px;letter-spacing:1px;opacity:.9;">{classe}</div>
            <div style="font-size:38px;font-weight:700;line-height:1;">{contagem.get(classe, 0)}</div>
            <div style="font-size:12px;opacity:.85;">estacoes</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

col_mapa, col_tab = st.columns([3, 2])

with col_mapa:
    atual["cor"] = atual["classe"].map(lambda c: CORES.get(c, CORES["BAIXO"])["rgb"])
    camada = pdk.Layer(
        "ScatterplotLayer",
        data=atual,
        get_position=["lon", "lat"],
        get_fill_color="cor",
        get_radius=900,
        opacity=0.8,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
        pickable=True,
    )
    vista = pdk.ViewState(latitude=-27.6, longitude=-48.52, zoom=10.2)
    st.pydeck_chart(pdk.Deck(
        layers=[camada],
        initial_view_state=vista,
        map_style=None,
        tooltip={"text": "{nome}\n{classe} (score {score})\nchuva 24h: {chuva_24h} mm"},
    ))

with col_tab:
    tabela = (
        atual[["nome", "classe", "score", "chuva_1h", "chuva_24h", "chuva_72h",
               "precip_prev_6h", "umidade_solo"]]
        .sort_values("score", ascending=False)
        .rename(columns={
            "nome": "Estacao", "classe": "Risco", "score": "Score",
            "chuva_1h": "1h", "chuva_24h": "24h", "chuva_72h": "72h",
            "precip_prev_6h": "prev.6h", "umidade_solo": "solo",
        })
    )
    st.dataframe(tabela, use_container_width=True, hide_index=True)

st.subheader("Ultimas 12h")
janela = df[df["ts"] >= ultimo - pd.Timedelta(hours=12)]
c1, c2 = st.columns(2)
with c1:
    st.caption("Score de risco por estacao")
    st.line_chart(janela.pivot_table(index="ts", columns="nome", values="score"))
with c2:
    st.caption("Chuva acumulada 24h (mm)")
    st.line_chart(janela.pivot_table(index="ts", columns="nome", values="chuva_24h"))
