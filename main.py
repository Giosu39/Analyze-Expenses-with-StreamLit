import streamlit as st
import tempfile
import datetime
import pandas as pd
from pathlib import Path
from inputToOutput import process_sql_file

st.set_page_config(page_title="Personal Finance Analyzer", layout="wide")

def main():
    st.title("🔄 Analisi Finanze Personali (Cashew)")
    st.write("Carica il tuo file di database o backup .sql per visualizzare la tua situazione macroeconomica.")

    if "uploaded_sql_path" not in st.session_state:
        st.session_state["uploaded_sql_path"] = None

    uploaded_file = st.file_uploader(
        "Seleziona un file di backup .sql", 
        type=["sql"], 
        accept_multiple_files=False
    )

    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sql") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            st.session_state["uploaded_sql_path"] = tmp_file.name
        
        st.success(f"✅ File '{uploaded_file.name}' caricato con successo!")
        
        try:
            file_path = Path(st.session_state["uploaded_sql_path"])
            data_dict = process_sql_file(file_path)
            df_tx = data_dict["transactions"]

            # Escludo transazioni future (non ancora pagate)
            if "paid" in df_tx.columns:
                df_tx = df_tx[df_tx["paid"] == 1].copy()

            df_wallets = data_dict["wallets"]
            
            if df_tx.empty:
                st.warning("Il file non contiene transazioni valide.")
                return

            st.markdown("---")
            st.header("🏠 Dashboard: Stato di Salute Finanziaria")
            
            # --- 1. APPLICAZIONE FILTRO DIFENSIVO SUI SEGNI ---
            df_chronological = df_tx.sort_values(by="data_operazione", ascending=True).copy()
            
            # Forziamo il valore assoluto per evitare il bug del doppio meno (- - = +)
            df_chronological["amount_abs"] = df_chronological["amount"].abs()
            df_chronological["net_amount"] = df_chronological["amount_abs"].where(
                df_chronological["tipo"] == "Entrata", -df_chronological["amount_abs"]
            )
            
            # Somma cumulativa temporanea basata solo sui movimenti catastali
            df_chronological["patrimonio_cumulativo_raw"] = df_chronological["net_amount"].cumsum()
            
            # --- 2. ESTRAZIONE PATRIMONIO NETTO REALE (Dalla Tabella Wallets) ---
            # Questo garantisce che il valore sia ESATTAMENTE quello reale dei tuoi conti ad oggi
            patrimonio_netto_attuale = 0.0
            colonne_saldo = [c for c in df_wallets.columns if c.lower() in ["balance", "amount", "current_balance", "saldo", "balance_num"]]
            
            if colonne_saldo and not df_wallets.empty:
                col_scelta = colonne_saldo[0]
                df_wallets[col_scelta] = pd.to_numeric(df_wallets[col_scelta], errors='coerce').fillna(0)
                patrimonio_netto_attuale = df_wallets[col_scelta].sum()
            else:
                # Fallback di emergenza sulle transazioni se la tabella wallet è corrotta
                if not df_chronological.empty:
                    patrimonio_netto_attuale = df_chronological["patrimonio_cumulativo_raw"].iloc[-1]

            # --- 3. RICALIBRAZIONE ASSE GRAFICO STORICO ---
            # Calcoliamo la discrepanza iniziale (es. capitale già esistente all'apertura dell'app)
            if not df_chronological.empty:
                ultimo_valore_raw = df_chronological["patrimonio_cumulativo_raw"].iloc[-1]
                discrepanza_iniziale = patrimonio_netto_attuale - ultimo_valore_raw
                # Sintonizziamo l'andamento storico partendo dal patrimonio reale attuale
                df_chronological["patrimonio_cumulativo"] = df_chronological["patrimonio_cumulativo_raw"] + discrepanza_iniziale
            else:
                df_chronological["patrimonio_cumulativo"] = 0.0

            # --- 4. FILTRO MESE CORRENTE (CON FALLBACK) ---
            oggi = datetime.datetime.now()
            df_chronological["anno"] = df_chronological["data_operazione"].dt.year
            df_chronological["mese"] = df_chronological["data_operazione"].dt.month
            
            df_mese_corrente = df_chronological[
                (df_chronological["anno"] == oggi.year) & (df_chronological["mese"] == oggi.month)
            ]
            label_periodo = oggi.strftime("%B %Y")
            
            if df_mese_corrente.empty and not df_chronological.empty:
                ultimo_record = df_chronological.iloc[-1]
                u_anno = ultimo_record["anno"]
                u_mese = ultimo_record["mese"]
                df_mese_corrente = df_chronological[
                    (df_chronological["anno"] == u_anno) & (df_chronological["mese"] == u_mese)
                ]
                label_periodo = ultimo_record["data_operazione"].strftime("%B %Y")

            # --- 5. CALCOLO METRICHE KPI MENSILI ---
            entrate_mese = df_mese_corrente[df_mese_corrente["tipo"] == "Entrata"]["amount_abs"].sum()
            uscite_mese = df_mese_corrente[df_mese_corrente["tipo"] == "Spesa"]["amount_abs"].sum()
            cash_flow_mese = entrate_mese - uscite_mese
            tasso_risparmio = (cash_flow_mese / entrate_mese * 100) if entrate_mese > 0 else 0.0

            # --- 6. VISUALIZZAZIONE KPI CARDS ---
            st.subheader(f"📊 Indicatori Chiave ({label_periodo})")
            kpi1, kpi2, kpi3 = st.columns(3)
            
            with kpi1:
                st.metric(
                    label="Patrimonio Netto Totale", 
                    value=f"€ {patrimonio_netto_attuale:,.2f}",
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

            # --- 7. GRAFICO DEL PATRIMONIO NETTO STORICO CORRETTO ---
            st.markdown("---")
            st.subheader("📈 Andamento del Patrimonio Netto nel Tempo")
            
            df_chart_data = (
                df_chronological.set_index("data_operazione")
                .resample("D")["patrimonio_cumulativo"]
                .last()
                .ffill()
            )
            
            st.line_chart(df_chart_data, y="patrimonio_cumulativo")

            # --- 8. ANTEPRIMA REGISTRO ---
            st.markdown("---")
            with st.expander("🔍 Visualizza Registro Ultimi Movimenti"):
                colonne_anteprima = [
                    "data_operazione", "name", "amount", "tipo", 
                    "categoria_nome", "sottocategoria_nome", "wallet_nome"
                ]
                colonne_disponibili = [c for c in colonne_anteprima if c in df_tx.columns]
                st.dataframe(df_tx[colonne_disponibili].head(15), use_container_width=True)
                
        except Exception as e:
            st.error(f"❌ Errore durante la lettura e mappatura del file: {e}")

if __name__ == "__main__":
    main()