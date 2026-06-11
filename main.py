import streamlit as st
import tempfile
import datetime
import pandas as pd
from pathlib import Path
from inputToOutput import process_sql_file

# --- CONFIGURAZIONE DELLA PAGINA ---
st.set_page_config(page_title="Personal Finance Analyzer", layout="wide", page_icon="💰")


# ==========================================
# 1. FUNZIONI DI CARICAMENTO E CACHING DATA
# ==========================================

@st.cache_data(show_spinner="Elaborazione del database in corso...")
def load_data_from_bytes(file_bytes: bytes) -> dict:
    """
    Scrive i byte in un file temporaneo, lo processa e pulisce il sistema.
    Usa la cache di Streamlit per evitare di rileggere il file ad ogni interazione.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sql") as tmp_file:
        tmp_file.write(file_bytes)
        tmp_path = Path(tmp_file.name)
    
    try:
        data_dict = process_sql_file(tmp_path)
    finally:
        # Garantisce la cancellazione del file temporaneo anche in caso di errore
        tmp_path.unlink(missing_ok=True)
        
    return data_dict


# ==========================================
# 2. BUSINESS LOGIC & TRASFORMAZIONE DATI
# ==========================================

def prepare_chronological_data(df_tx: pd.DataFrame, df_wallets: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """
    Applica i filtri sui segni, calcola il patrimonio cumulativo e 
    restituisce il DataFrame cronologico unito al patrimonio netto reale attuale.
    """
    # Escludo transazioni future (non ancora pagate)
    if "paid" in df_tx.columns:
        df_tx = df_tx[df_tx["paid"] == 1].copy()
        
    df_chronological = df_tx.sort_values(by="data_operazione", ascending=True).copy()
    
    # Forza il valore assoluto per evitare bug di segno (- - = +)
    df_chronological["amount_abs"] = df_chronological["amount"].abs()
    df_chronological["net_amount"] = df_chronological["amount_abs"].where(
        df_chronological["tipo"] == "Entrata", -df_chronological["amount_abs"]
    )
    
    # Somma cumulativa temporanea
    df_chronological["patrimonio_cumulativo_raw"] = df_chronological["net_amount"].cumsum()
    
    # Estrazione Patrimonio Netto Reale (da Wallets)
    patrimonio_netto_attuale = 0.0
    colonne_saldo = [c for c in df_wallets.columns if c.lower() in ["balance", "amount", "current_balance", "saldo", "balance_num"]]
    
    if colonne_saldo and not df_wallets.empty:
        col_scelta = colonne_saldo[0]
        df_wallets[col_scelta] = pd.to_numeric(df_wallets[col_scelta], errors='coerce').fillna(0)
        patrimonio_netto_attuale = df_wallets[col_scelta].sum()
    else:
        if not df_chronological.empty:
            patrimonio_netto_attuale = df_chronological["patrimonio_cumulativo_raw"].iloc[-1]

    # Ricalibrazione asse grafico storico
    if not df_chronological.empty:
        ultimo_valore_raw = df_chronological["patrimonio_cumulativo_raw"].iloc[-1]
        discrepanza_iniziale = patrimonio_netto_attuale - ultimo_valore_raw
        df_chronological["patrimonio_cumulativo"] = df_chronological["patrimonio_cumulativo_raw"] + discrepanza_iniziale
    else:
        df_chronological["patrimonio_cumulativo"] = 0.0
        
    return df_chronological, patrimonio_netto_attuale


def extract_monthly_metrics(df_chrono: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """
    Filtra i dati per il mese corrente o applica il fallback sull'ultimo mese disponibile.
    """
    if df_chrono.empty:
        return pd.DataFrame(), "Nessun Dato"
        
    oggi = datetime.datetime.now()
    df_chrono["anno"] = df_chrono["data_operazione"].dt.year
    df_chrono["mese"] = df_chrono["data_operazione"].dt.month
    
    df_mese = df_chrono[(df_chrono["anno"] == oggi.year) & (df_chrono["mese"] == oggi.month)]
    label_periodo = oggi.strftime("%B %Y")
    
    if df_mese.empty:
        ultimo_record = df_chrono.iloc[-1]
        df_mese = df_chrono[(df_chrono["anno"] == ultimo_record["anno"]) & (df_chrono["mese"] == ultimo_record["mese"])]
        label_periodo = ultimo_record["data_operazione"].strftime("%B %Y")
        
    return df_mese, label_periodo


# ==========================================
# 3. COMPONENTI INTERFACCIA UTENTE (UI)
# ==========================================

def render_kpi_cards(df_mese: pd.DataFrame, patrimonio_totale: float, label_periodo: str):
    """Renderizza le metriche KPI principali in cima alla pagina."""
    st.subheader(f"📊 Indicatori Chiave ({label_periodo})")
    
    entrate_mese = df_mese[df_mese["tipo"] == "Entrata"]["amount_abs"].sum() if not df_mese.empty else 0.0
    uscite_mese = df_mese[df_mese["tipo"] == "Spesa"]["amount_abs"].sum() if not df_mese.empty else 0.0
    cash_flow_mese = entrate_mese - uscite_mese
    tasso_risparmio = (cash_flow_mese / entrate_mese * 100) if entrate_mese > 0 else 0.0

    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        st.metric(
            label="Patrimonio Netto Totale", 
            value=f"€ {patrimonio_totale:,.2f}",
            help="La somma liquida in tempo reale di tutti i tuoi conti correnti, carte e contanti caricati."
        )
    with kpi2:
        st.metric(
            label="Cash Flow Mensile", 
            value=f"€ {cash_flow_mese:,.2f}",
            delta=f"€ {cash_flow_mese:,.2f}",
            help="Entrate meno uscite registrate esclusivamente nel mese di riferimento."
        )
    with kpi3:
        st.metric(
            label="Tasso di Risparmio", 
            value=f"{tasso_risparmio:.1f} %",
            help="Percentuale di entrate che sei riuscito a trattenere al netto delle spese."
        )


def render_net_worth_chart(df_chrono: pd.DataFrame):
    """Mostra il grafico dell'andamento patrimoniale nel tempo."""
    st.markdown("---")
    st.subheader("📈 Andamento del Patrimonio Netto nel Tempo")
    
    df_chart_data = (
        df_chrono.set_index("data_operazione")
        .resample("D")["patrimonio_cumulativo"]
        .last()
        .ffill()
    )
    st.line_chart(df_chart_data, y="patrimonio_cumulativo")


def render_rolling_cash_flow_chart(df_chrono: pd.DataFrame):
    """Mostra il grafico dei trend depurati dalla stagionalità mediante media mobile."""
    st.markdown("---")
    st.subheader("🔄 Trend del Flusso di Cassa su Media Mobile (Rolling Cash Flow)")
    st.write("Questa vista isola i picchi stagionali (es. tredicesime o scadenze annuali).")

    df_monthly = df_chrono.copy()
    df_monthly["mese_anno"] = df_monthly["data_operazione"].dt.to_period("M")
    
    df_entrate = df_monthly[df_monthly["tipo"] == "Entrata"].groupby("mese_anno")["amount_abs"].sum().rename("Entrate")
    df_uscite = df_monthly[df_monthly["tipo"] == "Spesa"].groupby("mese_anno")["amount_abs"].sum().rename("Uscite")
    
    all_months = pd.period_range(start=df_monthly["mese_anno"].min(), end=df_monthly["mese_anno"].max(), freq="M")
    df_rolling = pd.DataFrame(index=all_months).join(df_entrate, how="left").join(df_uscite, how="left").fillna(0)
    
    finestra_mesi = st.slider(
        "Seleziona la finestra della media mobile (in mesi):", 
        min_value=2, max_value=12, value=12,
        key="rolling_window_slider"
    )
    
    col_entrate_roll = f"Entrate Totali (Media Mobile {finestra_mesi}m)"
    col_uscite_roll = f"Uscite Totali (Media Mobile {finestra_mesi}m)"
    
    df_rolling[col_entrate_roll] = df_rolling["Entrate"].rolling(window=finestra_mesi, min_periods=1).mean()
    df_rolling[col_uscite_roll] = df_rolling["Uscite"].rolling(window=finestra_mesi, min_periods=1).mean()
    
    df_rolling.index = df_rolling.index.to_timestamp()
    st.line_chart(df_rolling[[col_entrate_roll, col_uscite_roll]])


def render_transactions_preview(df_tx: pd.DataFrame):
    """Mostra la tabella espandibile degli ultimi movimenti."""
    st.markdown("---")
    with st.expander("🔍 Visualizza Registro Ultimi Movimenti"):
        colonne_anteprima = ["data_operazione", "name", "amount", "tipo", "categoria_nome", "sottocategoria_nome", "wallet_nome"]
        colonne_disponibili = [c for c in colonne_anteprima if c in df_tx.columns]
        st.dataframe(df_tx[colonne_disponibili].head(15), use_container_width=True)


# ==========================================
# 4. DASHBOARDS COMPLETE (PAGINE)
# ==========================================

def page_macro_overview(df_tx: pd.DataFrame, df_wallets: pd.DataFrame):
    """Dashboard principale attuale (Stato di salute finanziaria)."""
    st.header("🏠 Dashboard: Stato di Salute Finanziaria")
    
    df_chrono, patrimonio_attuale = prepare_chronological_data(df_tx, df_wallets)
    
    if df_chrono.empty:
        st.warning("Nessun dato cronologico disponibile.")
        return
        
    df_mese, label_periodo = extract_monthly_metrics(df_chrono)
    
    # Render dei singoli blocchi visivi
    render_kpi_cards(df_mese, patrimonio_attuale, label_periodo)
    render_net_worth_chart(df_chrono)
    render_rolling_cash_flow_chart(df_chrono)
    render_transactions_preview(df_tx)


def page_category_analysis(df_tx: pd.DataFrame):
    """Esempio di una nuova dashboard futura."""
    st.header("🍕 Analisi Dettagliata Spese e Categorie")
    st.write("Qui potrai inserire grafici a torta, scomposizioni delle sotto-categorie, ecc.")
    # Esempio rapido: st.bar_chart(df_tx.groupby("categoria_nome")["amount"].sum())


# ==========================================
# 5. MAIN APPLICATION ROUTER
# ==========================================

def main():
    st.title("🔄 Analisi Finanze Personali (Cashew)")
    st.write("Carica il tuo file di backup per sbloccare i tuoi pannelli di analisi.")

    uploaded_file = st.file_uploader("Seleziona un file di backup .sql", type=["sql"])

    if uploaded_file is not None:
        try:
            # Caricamento centralizzato con cache (legge i byte dal file uploader)
            file_bytes = uploaded_file.getvalue()
            data_dict = load_data_from_bytes(file_bytes)
            
            df_tx = data_dict["transactions"]
            df_wallets = data_dict["wallets"]

            if df_tx.empty:
                st.warning("Il file caricato non contiene transazioni valide.")
                return

            # --- ROUTING DELLE DASHBOARD (SIDEBAR) ---
            st.sidebar.header("🧭 Navigazione")
            PAGINE = {
                "🏠 Panoramica Generale": lambda: page_macro_overview(df_tx, df_wallets),
                "🍕 Analisi Categorie (Futura)": lambda: page_category_analysis(df_tx),
                "🔮 Budget & Previsioni (Futura)": lambda: st.info("Work in progress! In arrivo...")
            }
            
            scelta_pagina = st.sidebar.radio("Seleziona la Dashboard da visualizzare:", list(PAGINE.keys()))
            
            st.markdown("---")
            # Esegue la funzione associata alla pagina selezionata
            PAGINE[scelta_pagina]()

        except Exception as e:
            st.error(f"❌ Errore durante l'elaborazione: {e}")

if __name__ == "__main__":
    main()