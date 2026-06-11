import sqlite3
import pandas as pd
from pathlib import Path

def process_sql_file(file_path: Path) -> dict:
    """
    Legge un file esportato da Cashew (sia esso un database SQLite reale o un dump SQL testuale),
    mappa le tabelle principali (transactions, categories, wallets) includendo le sotto-categorie,
    e restituisce un dizionario con i DataFrame pronti per l'analisi.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Il file {file_path} non esiste.")
    
    # Verifica dei "Magic Bytes" per capire se è un database SQLite binario o uno script di testo
    with open(file_path, "rb") as f:
        header = f.read(15)
    
    if header.startswith(b"SQLite format 3"):
        conn = sqlite3.connect(str(file_path))
    else:
        conn = sqlite3.connect(":memory:")
        try:
            sql_text = file_path.read_text(encoding="utf-8")
            conn.executescript(sql_text)
        except Exception as e:
            conn.close()
            raise ValueError(f"Impossibile eseguire lo script SQL testuale: {e}")
            
    try:
        df_transactions = pd.read_sql_query("SELECT * FROM transactions", conn)
        
        try:
            df_categories = pd.read_sql_query("SELECT * FROM categories", conn)
        except Exception:
            df_categories = pd.DataFrame(columns=["category_pk", "name"])
            
        try:
            df_wallets = pd.read_sql_query("SELECT * FROM wallets", conn)
        except Exception:
            df_wallets = pd.DataFrame(columns=["wallet_pk", "name"])
            
    finally:
        conn.close()
        
    if df_transactions.empty:
        return {"transactions": df_transactions, "categories": df_categories, "wallets": df_wallets}
        
    # 1. Conversione delle date (timestamp Unix in secondi)
    if "date_created" in df_transactions.columns:
        df_transactions["data_operazione"] = pd.to_datetime(
            df_transactions["date_created"], unit="s", errors="coerce"
        )
    
    # 2. Mappatura del tipo di transazione (0 = Spesa, 1 = Entrata)
    if "income" in df_transactions.columns:
        df_transactions["tipo"] = df_transactions["income"].map({0: "Spesa", 1: "Entrata"})
        
    # 3. Unione (Merge) per recuperare la Categoria Principale
    if not df_categories.empty and "category_fk" in df_transactions.columns:
        df_transactions = df_transactions.merge(
            df_categories[["category_pk", "name"]].rename(columns={"name": "categoria_nome"}),
            left_on="category_fk",
            right_on="category_pk",
            how="left"
        ).drop(columns=["category_pk"], errors="ignore")
        
    # 4. Unione (Merge) per recuperare la Sotto-categoria (sub_category_fk)
    if not df_categories.empty and "sub_category_fk" in df_transactions.columns:
        df_transactions = df_transactions.merge(
            df_categories[["category_pk", "name"]].rename(columns={"name": "sottocategoria_nome"}),
            left_on="sub_category_fk",
            right_on="category_pk",
            how="left"
        ).drop(columns=["category_pk"], errors="ignore")
        
    # 5. Unione (Merge) con i Wallet (Conti)
    if not df_wallets.empty and "wallet_fk" in df_transactions.columns:
        df_transactions = df_transactions.merge(
            df_wallets[["wallet_pk", "name"]].rename(columns={"name": "wallet_nome"}),
            left_on="wallet_fk",
            right_on="wallet_pk",
            how="left"
        ).drop(columns=["wallet_pk"], errors="ignore")
        
    if "data_operazione" in df_transactions.columns:
        df_transactions = df_transactions.sort_values(by="data_operazione", ascending=False)
        
    return {
        "transactions": df_transactions,
        "categories": df_categories,
        "wallets": df_wallets
    }