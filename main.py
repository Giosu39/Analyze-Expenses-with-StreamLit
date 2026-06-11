import streamlit as st
import tempfile
from pathlib import Path
from inputToOutput import process_sql_file

st.set_page_config(page_title="Personal Finance Analizer", layout="centered")

def main():
    st.title("🔄 Analisi Finanze Personali (Cashew)")
    st.write("Carica il tuo file di database o backup .sql per iniziare.")

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
            
            st.markdown("---")
            st.subheader("📊 Panoramica dei Dati Caricati")
            
            if df_tx.empty:
                st.warning("Il file non contiene transazioni valide.")
            else:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Transazioni Totali", f"{len(df_tx)}")
                with col2:
                    tot_entrate = df_tx[df_tx["tipo"] == "Entrata"]["amount"].sum()
                    st.metric("Totale Entrate", f"€ {tot_entrate:,.2f}")
                with col3:
                    tot_uscite = df_tx[df_tx["tipo"] == "Spesa"]["amount"].sum()
                    st.metric("Totale Uscite", f"€ {tot_uscite:,.2f}")
                
                st.write("### Anteprima delle Transazioni Mappate")
                # Aggiunta "sottocategoria_nome" alle colonne da mostrare nell'app
                colonne_anteprima = [
                    "data_operazione", "name", "amount", "tipo", 
                    "categoria_nome", "sottocategoria_nome", "wallet_nome"
                ]
                colonne_disponibili = [c for c in colonne_anteprima if c in df_tx.columns]
                
                st.dataframe(df_tx[colonne_disponibili].head(10), use_container_width=True)
                st.info("I dati comprensivi di sotto-categorie sono pronti per essere analizzati graficamente!")
                
        except Exception as e:
            st.error(f"❌ Errore durante la lettura e mappatura del file: {e}")

if __name__ == "__main__":
    main()