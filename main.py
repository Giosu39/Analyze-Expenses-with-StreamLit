import streamlit as st
import pandas as pd
import json
import matplotlib.pyplot as plt
import plotly.express as px
import seaborn as sns
from inputToOutput import get_output
import datetime

# Reads data from "input" folder and outputs a single transaction file to "/output/output.json"
get_output()

# --------------------
# Caricamento dati
# --------------------
FILE_PATH = "output/output.json"

with open(FILE_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

df = pd.DataFrame(data)
df['date'] = pd.to_datetime(df['date'])

# --------------------
# Sidebar (filtri)
# --------------------
st.sidebar.header("Filtri")
year_filter = st.sidebar.multiselect("Anno", options=df['date'].dt.year.unique(), default=df['date'].dt.year.unique())
type_filter = st.sidebar.multiselect("Tipo movimento", options=df['type'].unique(), default=df['type'].unique())

df_filtered = df[(df['date'].dt.year.isin(year_filter)) & (df['type'].isin(type_filter))]

# --------------------
# Statistiche principali
# --------------------
st.title("📊 Dashboard Finanze Personali")

entrate = df_filtered[df_filtered['type'] == "Entrata"]['value'].sum()
spese = df_filtered[df_filtered['type'] == "Spesa"]['value'].sum()
giroconti = df_filtered[df_filtered['type'] == "Giroconto"]['value'].sum()

saldo = entrate - spese  # base senza giroconti

col1, col2, col3, = st.columns(3)
col1.metric("Entrate totali", f"{entrate:,.2f} €")
col2.metric("Spese totali", f"{spese:,.2f} €")
col3.metric("Saldo (Entrate - Spese)", f"{saldo:,.2f} €")

# --------------------
# Andamento nel tempo
# --------------------
# Copia e pulizia
df_saldo = df.copy()
df_saldo['date'] = pd.to_datetime(df_saldo['date'])
df_saldo['importo'] = 0.0

# Segno corretto
df_saldo.loc[df_saldo['type'] == "Entrata", 'importo'] = df_saldo['value']
df_saldo.loc[df_saldo['type'] == "Spesa", 'importo'] = -df_saldo['value']

# Escludo i giroconti
df_saldo = df_saldo[df_saldo['type'] != "Giroconto"]

# Ordino cronologicamente
df_saldo = df_saldo.sort_values('date')

# Filtri tempo
st.subheader("📈 Andamento Saldo Complessivo")

period = st.radio(
    "Seleziona periodo:",
    options=["Sempre", "Ultimo anno", "Anno corrente"],
    key="filtro_saldo"  # opzionale, se hai più radio
)

oggi = pd.Timestamp.today()

if period == "Ultimo anno":
    start_date = oggi - pd.Timedelta(days=365)
    data_limite = oggi - pd.Timedelta(days=365)
    df_filtered_saldo = df_saldo[df_saldo['date'] >= data_limite]

elif period == "Anno corrente":
    start_date = pd.Timestamp(year=oggi.year, month=1, day=1)
    inizio_anno = pd.Timestamp(year=oggi.year, month=1, day=1)
    df_filtered_saldo = df_saldo[df_saldo['date'] >= inizio_anno]

else:
    # Sempre
    start_date = None  # nessun filtro
    df_filtered_saldo = df_saldo.copy()

# Calcolo saldo iniziale (somma cumulativa prima di start_date)
if start_date:
    saldo_iniziale = df_saldo[df_saldo['date'] < start_date]['importo'].sum()
    df_filtered_saldo = df_saldo[df_saldo['date'] >= start_date].copy()
else:
    saldo_iniziale = 0
    df_filtered_saldo = df_saldo.copy()

# Raggruppo e ordino dopo filtro
df_daily = df_filtered_saldo.groupby('date')['importo'].sum().reset_index()
df_daily = df_daily.sort_values('date')

# Calcolo saldo cumulativo partendo da saldo_iniziale
df_daily['saldo'] = df_daily['importo'].cumsum() + saldo_iniziale

# Mostra grafico
st.line_chart(df_daily.set_index('date')['saldo'])



# --------------------
# Distribuzione per categoria
# --------------------
st.subheader("🗂 Distribuzione delle spese per categoria")

df_spese = df_filtered[df_filtered['type'] == "Spesa"]

if not df_spese.empty:
    spese_categoria = df_spese.groupby("category")['value'].sum().reset_index()

    fig = px.pie(
        spese_categoria,
        values='value',
        names='category',
        hole=0.3,
        title="Distribuzione delle spese per categoria",
    )

    fig.update_traces(
        textinfo='percent+label+value',
        textposition='inside',
        hovertemplate='<b>%{label}</b><br>Totale: %{value:,.2f} €<br>%{percent}',
        textfont_size=14,
        insidetextorientation='radial'
    )

    fig.update_layout(
        showlegend=True,
        legend_title_text="Categoria",
        uniformtext_minsize=12,
        uniformtext_mode='hide'
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.write("Nessuna spesa nel periodo selezionato.")