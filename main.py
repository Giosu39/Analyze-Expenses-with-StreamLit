import streamlit as st
import pandas as pd
import json
import plotly.express as px
import os
from inputToOutput import execute
from datetime import timedelta
import datetime
from pathlib import Path
import tempfile
import shutil

# ====================
# CONFIGURAZIONE
# ====================
PERIOD_OPTIONS = ["Sempre", "Ultimo anno", "Anno corrente"]

# ====================
# FUNZIONI DI SUPPORTO
# ====================
def check_and_request_backup(tmp_input: Path) -> bool:
    """Verifica la presenza di un file .mmbackup, se assente richiede upload."""
    tmp_input.mkdir(parents=True, exist_ok=True)
    backup_files = list(tmp_input.glob("*.mmbackup"))

    if backup_files:
        return True

    # Mostro uploader solo se non già caricato
    uploaded_file = st.file_uploader("Carica file .mmbackup", type=["mmbackup"])
    if uploaded_file is not None:
        print("Carico da:", uploaded_file)
        save_path = tmp_input / uploaded_file.name
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            print("Esiste:", Path(uploaded_file).exists())
        # Aggiorno lo stato per ricaricare la pagina senza uploader
        st.session_state["backup_ready"] = True
        st.rerun()
    return False


def load_data(file_path: Path) -> pd.DataFrame:
    """Carica i dati dal file JSON e converte in DataFrame."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    return df

def apply_filters(df: pd.DataFrame, start_date: datetime) -> pd.DataFrame:

    if start_date:
        df = df[df['date'] >= start_date]

    return df

def get_start_date(period: str, df: pd.DataFrame) -> datetime:
     
    oggi = pd.Timestamp.today()

    if period == "Ultimo anno":
        start_date = oggi - timedelta(days=365)
    elif period == "Anno corrente":
        start_date = pd.Timestamp(year=oggi.year, month=1, day=1)
    elif period == "Sempre" and not df.empty:
        start_date = df['date'].min()
    else:
        start_date = None
    
    return start_date

def get_crescita_percentuale(df_unfiltered: pd.DataFrame, saldo_periodo, start_date: datetime) -> str:

    

    # Calcolo saldo iniziale considerando operazioni precedenti al periodo
    df_unfiltered = df_unfiltered.copy()
    df_unfiltered['importo'] = 0.0
    df_unfiltered.loc[df_unfiltered['type'] == "Entrata", 'importo'] = df_unfiltered['value']
    df_unfiltered.loc[df_unfiltered['type'] == "Spesa", 'importo'] = -df_unfiltered['value']
    df_unfiltered = df_unfiltered[df_unfiltered['type'] != "Giroconto"]

    if start_date:
        saldo_iniziale = df_unfiltered[df_unfiltered['date'] <= start_date]['importo'].sum()
    else:
        saldo_iniziale = 0

    saldo_finale = saldo_iniziale + saldo_periodo

    # Calcolo crescita percentuale (gestione caso saldo iniziale = 0)
    if saldo_iniziale != 0:
        crescita_percentuale = ((saldo_finale - saldo_iniziale) / abs(saldo_iniziale)) * 100
        crescita_str = f"{crescita_percentuale:.2f} %"
    else:
        crescita_str = "N/A"

    return crescita_str
    

def show_summary(df: pd.DataFrame, entrate, spese, saldo_periodo):
    """Mostra le metriche principali (Entrate, Spese, Saldo)."""
    col1, col2, col3 = st.columns(3)
    col1.metric("Entrate totali", f"{entrate:,.2f} €")
    col2.metric("Spese totali", f"{spese:,.2f} €")
    col3.metric("Saldo (Entrate - Spese)", f"{saldo_periodo:,.2f} €")


def build_saldo_trend(df: pd.DataFrame, df_unfiltered: pd.DataFrame, start_date: datetime, crescita_percentuale: str):
    """Costruisce il grafico dell'andamento saldo nel tempo."""
    st.subheader("📈 Andamento Saldo Complessivo (" + crescita_percentuale + ")")

    df = df.copy()
    df['importo'] = 0.0
    df.loc[df['type'] == "Entrata", 'importo'] = df['value']
    df.loc[df['type'] == "Spesa", 'importo'] = -df['value']
    df = df[df['type'] != "Giroconto"].sort_values('date')

    df_unfiltered = df_unfiltered.copy()
    df_unfiltered['importo'] = 0.0
    df_unfiltered.loc[df_unfiltered['type'] == "Entrata", 'importo'] = df_unfiltered['value']
    df_unfiltered.loc[df_unfiltered['type'] == "Spesa", 'importo'] = -df_unfiltered['value']
    df_unfiltered = df_unfiltered[df_unfiltered['type'] != "Giroconto"].sort_values('date')

    if start_date:
        saldo_iniziale = df_unfiltered[df_unfiltered['date'] < start_date]['importo'].sum()
        # df = df[df['date'] >= start_date].copy()
    else:
        saldo_iniziale = 0

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

    if "uploaded_file_path" not in st.session_state:
        st.session_state["uploaded_file_path"] = None

    if st.session_state["uploaded_file_path"] is None:
        uploaded_file = st.file_uploader("Carica file .mmbackup", type=["mmbackup"])
        if uploaded_file is not None:
            # Salva temporaneamente il file caricato in un tmp file (streamlit upload è in-memory)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mmbackup") as tmp_file:
                tmp_file.write(uploaded_file.getbuffer())
                st.session_state["uploaded_file_path"] = tmp_file.name
            st.rerun()

    if st.session_state["uploaded_file_path"]:
        # Esegui il processo e mostra dati
        output_file = execute(Path(st.session_state["uploaded_file_path"]))

        # Carica e filtra dati
        df_unfiltered = load_data(output_file)

        # Sidebar filtro "Periodo"
        st.sidebar.header("Filtri")
        periodo = st.sidebar.radio("Seleziona periodo:", options=PERIOD_OPTIONS, index=0, key="filtro_periodo")
        start_date = get_start_date(periodo, df_unfiltered)

        # Applica filtro periodo
        df_filtered = apply_filters(df_unfiltered, start_date)

        # Entrate e Spese nel periodo filtrato
        entrate = df_filtered[df_filtered['type'] == "Entrata"]['value'].sum()
        spese = df_filtered[df_filtered['type'] == "Spesa"]['value'].sum()
        saldo_periodo = entrate - spese

        crescita_percentuale = get_crescita_percentuale(df_unfiltered, saldo_periodo, start_date)

        show_summary(df_filtered, entrate, spese, saldo_periodo)
        build_saldo_trend(df_filtered, df_unfiltered, start_date, crescita_percentuale)
        build_expense_distribution(df_filtered)


if __name__ == "__main__":
    main()
