import streamlit as st
import tempfile
from pathlib import Path

# Configurazione della pagina
st.set_page_config(page_title="Upload Reset", layout="centered")

def main():
    st.title("🔄 Reset Applicazione")
    st.write("Carica un file di database in formato .sql per iniziare.")

    # Inizializzazione dello stato della sessione per salvare il percorso del file
    if "uploaded_sql_path" not in st.session_state:
        st.session_state["uploaded_sql_path"] = None

    # Interfaccia di caricamento (accetta SOLO file .sql)
    uploaded_file = st.file_uploader(
        "Seleziona un file di backup .sql", 
        type=["sql"], 
        accept_multiple_files=False
    )

    if uploaded_file is not None:
        # Salvataggio del file in una posizione temporanea sul server
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sql") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            st.session_state["uploaded_sql_path"] = tmp_file.name
        
        # Feedback visivo dell'avvenuto caricamento
        st.success(f"✅ File '{uploaded_file.name}' caricato con successo!")
        st.info("Al momento l'applicazione è resettata: non verrà eseguita alcuna elaborazione successiva.")
        
        # Mostra il percorso temporaneo del file (utile per implementazioni future)
        st.text_view = st.code(f"Path temporaneo: {st.session_state['uploaded_sql_path']}", language="text")

if __name__ == "__main__":
    main()