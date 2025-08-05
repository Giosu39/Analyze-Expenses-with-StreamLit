import streamlit as st
import pandas as pd
import json
import plotly.express as px
import os
from inputToOutput import execute
from datetime import datetime, timedelta

# ====================
# CONFIGURAZIONE
# ====================
INPUT_DIR = "input"
FILE_PATH = "output/output.json"
PERIOD_OPTIONS = ["Sempre", "Ultimo anno", "Anno corrente"]

# ====================
# FUNZIONI DI SUPPORTO
# ====================
def check_and_request_backup():
    """Verifica la presenza di un file .mmbackup in input/, se assente richiede upload."""
    os.makedirs(INPUT_DIR, exist_ok=True)
    backup_files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".mmbackup")]

    if backup_files:
        return True

    # Mostro uploader solo se non già caricato
    uploaded_file = st.file_uploader("Carica file .mmbackup", type=["mmbackup"])
    if uploaded_file is not None:
        save_path = os.path.join(INPUT_DIR, uploaded_file.name)
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        # Aggiorno lo stato per ricaricare la pagina senza uploader
        st.session_state["backup_ready"] = True
        st.rerun()
    return False


def load_data(file_path: str) -> pd.DataFrame:
    """Carica i dati dal file JSON e converte in DataFrame."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    return df

def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Applica i filtri dalla sidebar e restituisce il DataFrame filtrato."""
    st.sidebar.header("Filtri")
    years = df['date'].dt.year.unique()
    types = df['type'].unique()

    year_filter = st.sidebar.multiselect("Anno", options=years, default=years)
    type_filter = st.sidebar.multiselect("Tipo movimento", options=types, default=types)

    return df[(df['date'].dt.year.isin(year_filter)) & (df['type'].isin(type_filter))]

def show_summary(df: pd.DataFrame):
    """Mostra le metriche principali (Entrate, Spese, Saldo)."""
    entrate = df[df['type'] == "Entrata"]['value'].sum()
    spese = df[df['type'] == "Spesa"]['value'].sum()
    saldo = entrate - spese

    col1, col2, col3 = st.columns(3)
    col1.metric("Entrate totali", f"{entrate:,.2f} €")
    col2.metric("Spese totali", f"{spese:,.2f} €")
    col3.metric("Saldo (Entrate - Spese)", f"{saldo:,.2f} €")

def build_saldo_trend(df: pd.DataFrame):
    """Costruisce il grafico dell'andamento saldo nel tempo."""
    st.subheader("📈 Andamento Saldo Complessivo")
    
    # Prepara dati
    df = df.copy()
    df['importo'] = 0.0
    df.loc[df['type'] == "Entrata", 'importo'] = df['value']
    df.loc[df['type'] == "Spesa", 'importo'] = -df['value']
    df = df[df['type'] != "Giroconto"].sort_values('date')

    # Filtro periodo
    oggi = pd.Timestamp.today()
    period = st.radio("Seleziona periodo:", options=PERIOD_OPTIONS, key="filtro_saldo")

    if period == "Ultimo anno":
        start_date = oggi - timedelta(days=365)
    elif period == "Anno corrente":
        start_date = pd.Timestamp(year=oggi.year, month=1, day=1)
    else:
        start_date = None

    if start_date:
        saldo_iniziale = df[df['date'] < start_date]['importo'].sum()
        df = df[df['date'] >= start_date].copy()
    else:
        saldo_iniziale = 0

    # Cumulativo
    df_daily = df.groupby('date')['importo'].sum().reset_index()
    df_daily['saldo'] = df_daily['importo'].cumsum() + saldo_iniziale

    st.line_chart(df_daily.set_index('date')['saldo'])

def build_expense_distribution(df: pd.DataFrame):
    """Mostra distribuzione spese per categoria."""
    st.subheader("🗂 Distribuzione delle spese per categoria")

    df_spese = df[df['type'] == "Spesa"]
    if df_spese.empty:
        st.write("Nessuna spesa nel periodo selezionato.")
        return

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

# ====================
# MAIN APP
# ====================
def main():
    st.title("📊 Dashboard Finanze Personali")

    # Controllo stato: backup presente?
    if "backup_ready" not in st.session_state:
        st.session_state["backup_ready"] = False

    if not st.session_state["backup_ready"]:
        if not check_and_request_backup():
            st.stop()

    # Genera dati aggiornati
    execute()

    # Carica e filtra dati
    df = load_data(FILE_PATH)
    df_filtered = apply_filters(df)

    # Sezioni
    show_summary(df_filtered)
    build_saldo_trend(df)
    build_expense_distribution(df_filtered)

if __name__ == "__main__":
    main()
