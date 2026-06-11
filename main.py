import streamlit as st
import tempfile
import datetime
import pandas as pd
from pathlib import Path
import plotly.express as px
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
    """Dashboard per l'analisi dettagliata e gerarchica delle spese."""
    st.header("🍕 Analisi Dettagliata Spese e Categorie")
    st.write("Identifica dove si concentrano i tuoi deflussi storici sfruttando la regola di Pareto.")

    # 1. Filtriamo solo le uscite (Spese)
    if "tipo" not in df_tx.columns:
        st.error("I dati caricati non contengono la colonna 'tipo'.")
        return
        
    df_spese = df_tx[df_tx["tipo"] == "Spesa"].copy()

    # Escludiamo la categoria "Correzione saldo"
    if "categoria_nome" in df_spese.columns:
        df_spese = df_spese[df_spese["categoria_nome"] != "Correzione saldo"]
    
    if df_spese.empty:
        st.warning("📭 Nessuna spesa registrata nel database per questa analisi.")
        return

    # 2. Preparazione dati ed eliminazione dei valori nulli per Plotly
    df_spese["amount_abs"] = df_spese["amount"].abs()
    df_spese["categoria_nome"] = df_spese["categoria_nome"].fillna("Non Specificata")
    df_spese["sottocategoria_nome"] = df_spese["sottocategoria_nome"].fillna("Generica")

    # 3. Filtro Temporale (Storico vs Anno Specifico)
    st.markdown("---")
    col_filtro1, col_filtro2 = st.columns([1, 1])
    
    with col_filtro1:
        if "data_operazione" in df_spese.columns:
            df_spese["anno"] = df_spese["data_operazione"].dt.year
            anni_disponibili = sorted(df_spese["anno"].dropna().unique(), reverse=True)
            opzioni_periodo = ["Tutto lo Storico"] + [str(a) for a in anni_disponibili]
            periodo_scelto = st.selectbox("📆 Seleziona il periodo temporale:", opzioni_periodo)
            
            if periodo_scelto != "Tutto lo Storico":
                df_spese = df_spese[df_spese["anno"] == int(periodo_scelto)]
        else:
            periodo_scelto = "Tutto lo Storico"

    with col_filtro2:
        tipo_grafico = st.radio(
            "📐 Modello di visualizzazione:", 
            ["Sunburst (Cerchi concentrici)", "Treemap (Rettangoli annidati)"],
            horizontal=True
        )

    st.markdown("---")
    st.subheader(f"📊 Matrice di Distribuzione delle Spese ({periodo_scelto})")
    st.caption("💡 Clicca sulle macro-categorie per esplorare le sotto-categorie nel dettaglio.")

    # 4. Generazione del Grafico Plotly
    path_gerarchia = ["categoria_nome", "sottocategoria_nome"]
    
    if tipo_grafico == "Sunburst (Cerchi concentrici)":
        fig = px.sunburst(
            df_spese,
            path=path_gerarchia,
            values="amount_abs",
            color="categoria_nome",
            color_discrete_sequence=px.colors.qualitative.Safe,
            branchvalues="total"
        )
    else:
        fig = px.treemap(
            df_spese,
            path=path_gerarchia,
            values="amount_abs",
            color="categoria_nome",
            color_discrete_sequence=px.colors.qualitative.Safe
        )

    fig.update_traces(
        textinfo="label+percent parent",
        hovertemplate="<b>%{label}</b><br>Totale: € %{value:,.2f}<br>Quota: %{percentParent:.1%}"
    )
    fig.update_layout(
        margin=dict(t=10, l=10, r=10, b=10),
        height=600
    )

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📈 Tabella di Analisi (Distribuzione Decrescente)"):
        df_summary = (
            df_spese.groupby(["categoria_nome", "sottocategoria_nome"])["amount_abs"]
            .sum()
            .reset_index()
            .sort_values(by="amount_abs", ascending=False)
        )
        df_summary["% sul Totale"] = (df_summary["amount_abs"] / df_summary["amount_abs"].sum()) * 100
        df_summary["% Cumulativa"] = df_summary["% sul Totale"].cumsum()
        
        df_summary.columns = ["Macro Categoria", "Sotto Categoria", "Totale Speso (€)", "% Parziale", "% Cumulativa (Pareto)"]
        st.dataframe(
            df_summary.style.format({
                "Totale Speso (€)": "€ {:,.2f}",
                "% Parziale": "{:.1f}%",
                "% Cumulativa (Pareto)": "{:.1f}%"
            }), 
            use_container_width=True,
            hide_index=True
        )


def page_seasonality_heatmap(df_tx: pd.DataFrame):
    """Dashboard per l'analisi della stagionalità pluriennale delle spese con calcolo Sinking Fund."""
    st.header("📅 Heatmap della Stagionalità Pluriennale")
    st.write("Individua a colpo d'occhio i mesi dell'anno storicamente più dispendiosi e calcola la tua strategia di accantonamento.")

    if "tipo" not in df_tx.columns or "data_operazione" not in df_tx.columns:
        st.error("I dati caricati non dispongono delle colonne necessarie per l'analisi temporale.")
        return

    # Filtro uscite (escluse correzioni di saldo)
    df_spese = df_tx[df_tx["tipo"] == "Spesa"].copy()
    if "categoria_nome" in df_spese.columns:
        df_spese = df_spese[df_spese["categoria_nome"] != "Correzione saldo"]

    if df_spese.empty:
        st.warning("📭 Nessuna spesa registrata nel database per questa analisi.")
        return

    # Estrazione Anno e Mese
    df_spese["amount_abs"] = df_spese["amount"].abs()
    df_spese["anno"] = df_spese["data_operazione"].dt.year
    df_spese["mese"] = df_spese["data_operazione"].dt.month

    # Creazione della matrice Pivot (Righe: Anni, Colonne: Mesi)
    df_grid = df_spese.groupby(["anno", "mese"])["amount_abs"].sum().unstack(fill_value=0)

    # Forza la presenza di tutti i 12 mesi per consistenza del layout grafico
    for m in range(1, 13):
        if m not in df_grid.columns:
            df_grid[m] = 0.0
    df_grid = df_grid[range(1, 13)]
    
    # Ordina gli anni in modo decrescente (l'anno più recente in alto nella Heatmap)
    df_grid = df_grid.sort_index(ascending=False)

    nomi_mesi = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

    st.markdown("---")
    st.subheader("🟩 Matrix View: Intensità delle Spese Mensili")
    st.caption("💡 Più la cella tende al rosso intenso, più le uscite in quel mese sono state elevate.")

    # Generazione Heatmap Plotly Express
    fig = px.imshow(
        df_grid,
        labels=dict(x="Mese", y="Anno", color="Spese Totali (€)"),
        x=nomi_mesi,
        y=[str(a) for a in df_grid.index],
        color_continuous_scale="RdYlGn_r",  # Scala invertita: Verde=Basso, Rosso=Alto
        text_auto=",.0f"  # Mostra i valori interi formattati dentro le celle
    )

    fig.update_layout(
        height=280 + (len(df_grid) * 45),
        margin=dict(t=10, b=10, l=10, r=10),
        coloraxis_colorbar=dict(title="Spese €")
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # --- LOGICA CALCOLO AUTOMATICO ACCANTONAMENTO (SINKING FUND) ---
    st.markdown("---")
    st.subheader("💡 Analisi Predittiva & Strategia di Accantonamento")
    st.write("Algoritmo di protezione dagli shock stagionali basato sul tuo comportamento storico.")

    # Calcoliamo la media storica per ogni singolo mese (es. la media di tutti i Dicembri passati)
    medie_mensili_storiche = df_grid.mean(axis=0)
    # Calcoliamo la spesa media mensile globale flat
    spesa_media_globale = medie_mensili_storiche.mean()

    # Identifichiamo i mesi critici (quelli che superano stabilmente la media globale)
    mesi_critici = medie_mensili_storiche[medie_mensili_storiche > spesa_media_globale]
    
    if not mesi_critici.empty:
        # L'eccesso annuale totale accumulato nei mesi di picco rispetto alla baseline
        eccesso_totale_annuo = (mesi_critici - spesa_media_globale).sum()
        # Quota mensile costante da salvare per coprire l'eccesso
        quota_mensile_consigliata = eccesso_totale_annuo / 12
        
        col1, col2 = st.columns([4, 3])
        
        with col1:
            st.markdown("##### 📌 I tuoi mesi di picco ricorrenti:")
            for m_idx, spesa_media_mese in mesi_critici.items():
                nome_m = nomi_mesi[m_idx - 1]
                delta_media = spesa_media_mese - spesa_media_globale
                st.write(f"• **{nome_m}**: Spesa storica media di € {spesa_media_mese:,.2f} (*+€ {delta_media:,.2f}* sopra la media)")
                
        with col2:
            st.metric(
                label="Buffer Mensile Consigliato (Sinking Fund)", 
                value=f"€ {quota_mensile_consigliata:,.2f}",
                help="Soldi da mettere da parte ogni mese per neutralizzare completamente l'impatto dei mesi rossi."
            )
            st.info(
                f"📊 **Come interpretare il dato:** La tua spesa media flat è di **€ {spesa_media_globale:,.2f}/mese**. "
                f"Tuttavia, a causa della stagionalità, i mesi critici ti causano un sovraccarico complessivo di **€ {eccesso_totale_annuo:,.2f}** all'anno. "
                f"Se accumuli stabilmente **€ {quota_mensile_consigliata:,.2f}** al mese, azzererai lo shock sui tuoi conti."
            )
    else:
        st.success("🎉 Complimenti! Le tue uscite storiche sono perfettamente bilanciate mese per mese. Non si registrano picchi stagionali anomali.")


# ==========================================
# 5. MAIN APPLICATION ROUTER
# ==========================================

def main():
    st.title("🔄 Analisi Finanze Personali (Cashew)")
    st.write("Carica il tuo file di backup per sbloccare i tuoi pannelli di analisi.")

    uploaded_file = st.file_uploader("Seleziona un file di backup .sql", type=["sql"])

    if uploaded_file is not None:
        try:
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
                "🍕 Analisi Categorie": lambda: page_category_analysis(df_tx),
                "📅 Stagionalità Pluriennale": lambda: page_seasonality_heatmap(df_tx),
                "🔮 Budget & Previsioni (Futura)": lambda: st.info("Work in progress! In arrivo...")
            }
            
            scelta_pagina = st.sidebar.radio("Seleziona la Dashboard da visualizzare:", list(PAGINE.keys()))
            
            st.markdown("---")
            PAGINE[scelta_pagina]()

        except Exception as e:
            st.error(f"❌ Errore durante l'elaborazione: {e}")

if __name__ == "__main__":
    main()