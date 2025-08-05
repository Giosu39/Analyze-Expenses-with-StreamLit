import json
import sqlite3
import zipfile
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil


# ==============================
# MODELLI
# ==============================
class Transaction:
    """Rappresenta una transazione o un trasferimento di denaro."""

    def __init__(self, type_: str, date: str, value: float,
                 account: str = "", category: str = "",
                 from_account: str = "", to_account: str = ""):
        self.type = type_
        self.date = date
        self.value = value
        self.account = account
        self.category = category
        self.from_account = from_account
        self.to_account = to_account


class TransactionEncoder(json.JSONEncoder):
    """Encoder JSON custom per oggetti Transaction."""

    def default(self, obj):
        if isinstance(obj, Transaction):
            return obj.__dict__
        return super().default(obj)


# ==============================
# FUNZIONI DI SUPPORTO
# ==============================
def extract_mmbackup(input_folder: Path, extract_folder: Path) -> Optional[Path]:
    """Trova ed estrae il file .mmbackup come archivio zip."""
    mmbackup_files = list(input_folder.glob("*.mmbackup"))

    if not mmbackup_files:
        print('⚠️ Nessun file .mmbackup trovato. Verranno usati i file JSON già presenti in "input".')
        return None

    mmbackup_file = mmbackup_files[0]
    zip_file = mmbackup_file.with_suffix(".zip")

    mmbackup_file.rename(zip_file)
    print(f"File rinominato: {mmbackup_file} -> {zip_file}")

    extract_folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        zip_ref.extractall(extract_folder)
        print(f"File estratti in: {extract_folder}")

    return extract_folder / "myFinance.db"


def export_db_to_json(db_path: Path, output_folder: Path) -> None:
    """Esporta tutte le tabelle di un database SQLite in file JSON."""
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} non trovato.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]

    output_folder.mkdir(exist_ok=True)

    for table_name in tables:
        cursor.execute(f'SELECT * FROM "{table_name}"')
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        data = [dict(zip(columns, row)) for row in rows]
        json_path = output_folder / f"{table_name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"Tabella '{table_name}' esportata in {json_path}")

    conn.close()
    print("✅ Esportazione completata.")


def load_json(path: Path) -> Any:
    """Carica un file JSON e restituisce il contenuto."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_transaction_list(
    account: List[Dict], transaction: List[Dict], transfer: List[Dict], 
    sync_link: List[Dict], category: List[Dict]
) -> List[Transaction]:
    """Crea la lista di Transaction a partire dai dati grezzi."""
    
    category_map = {c['uid']: c for c in category}
    account_map = {a['uid']: a for a in account}

    sync_maps = {
        "Account": {s['entityUid']: s for s in sync_link if s.get('otherType') == 'Account'},
        "Category": {s['entityUid']: s for s in sync_link if s.get('otherType') == 'Category'},
        "FromAccount": {s['entityUid']: s for s in sync_link if s.get('otherType') == 'FromAccount'},
        "ToAccount": {s['entityUid']: s for s in sync_link if s.get('otherType') == 'ToAccount'}
    }

    output_transactions: List[Transaction] = []

    for t in transaction:
        if t['isRemoved']:
            continue
        tid = t['uid']
        acc = account_map[sync_maps["Account"][tid]['otherUid']]
        if acc['ignoreInBalance']:
            continue

        value = int(t['amountInDefaultCurrency']) / 100
        category_title = category_map.get(
            sync_maps["Category"].get(tid, {}).get('otherUid'),
            {"title": "Regolazione saldo"}
        )['title']

        tx_type = "Spesa" if t['type'] == 'Expense' else "Entrata"
        output_transactions.append(Transaction(tx_type, t['date'], value, acc['title'], category_title))

    for tr in transfer:
        if tr['isRemoved']:
            continue
        tid = tr['uid']
        value = int(tr['fromAmount']) / 100
        from_acc = account_map[sync_maps["FromAccount"][tid]['otherUid']]['title']
        to_acc = account_map[sync_maps["ToAccount"][tid]['otherUid']]['title']

        output_transactions.append(Transaction("Giroconto", tr['date'], value, from_account=from_acc, to_account=to_acc))

    return sorted(output_transactions, key=lambda t: t.date)


def save_transactions(transactions: List[Transaction], output_folder: Path) -> Path:
    """Salva la lista delle transazioni in un file JSON."""
    output_folder.mkdir(exist_ok=True)
    output_file = output_folder / "output.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(transactions, f, ensure_ascii=False, indent=4, cls=TransactionEncoder)

    print(f"💾 File salvato in: {output_file}")
    return output_file


# ==============================
# MAIN FUNCTION / EXECUTE WHOLE PROCESS
# ==============================
def execute(uploaded_file: Path) -> Path:
    """
    Esegue l'intero processo a partire da un file .mmbackup dato come Path.
    Usa cartelle temporanee isolate per input/output.
    Restituisce il path del file JSON output.
    """

    # Crea una directory temporanea
    temp_dir = Path(tempfile.mkdtemp())
    input_folder = temp_dir / "input"
    extract_folder = temp_dir / "estratto"
    output_folder = temp_dir / "output"

    input_folder.mkdir()
    output_folder.mkdir()

    # Copia il file .mmbackup nella cartella temporanea di input
    shutil.copy(uploaded_file, input_folder / uploaded_file.name)

    # Esegui l’estrazione e trasformazione dal file .mmbackup copiato
    db_path = extract_mmbackup(input_folder, extract_folder)
    if db_path:
        export_db_to_json(db_path, input_folder)

    # Carica i JSON da input_folder
    account = load_json(input_folder / "account.json")
    transaction = load_json(input_folder / "transaction.json")
    transfer = load_json(input_folder / "transfer.json")
    sync_link = load_json(input_folder / "sync_link.json")
    category = load_json(input_folder / "category.json")

    # Costruisci la lista di transazioni
    transactions = build_transaction_list(account, transaction, transfer, sync_link, category)

    # Salva output json
    output_file = save_transactions(transactions, output_folder)

    return output_file