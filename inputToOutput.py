import json
import os
import zipfile
import sqlite3
import glob

class Transaction:
    def __init__(self, type_, date, value, account, category, fromAccount, toAccount):
        self.type = type_
        self.date = date
        self.value = value
        self.account = account
        self.category = category
        self.fromAccount = fromAccount
        self.toAccount = toAccount

class TransactionEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Transaction):
            return {
                "type": obj.type,
                "date": obj.date,
                "value": obj.value,
                "account": obj.account,
                "category": obj.category,
                "fromAccount": obj.fromAccount,
                "toAccount": obj.toAccount
            }
        return super().default(obj)


def get_output():

    # 1. Trova dinamicamente il file .mmbackup nella cartella input
    input_folder = "input"
    mmbackup_files = glob.glob(os.path.join(input_folder, "*.mmbackup"))

    if not mmbackup_files:
        print('Nessun file .mmbackup trovato, procedo dando per scontato che ci siano già i file .json nella cartella "input"')
        print('Se desideri un ricalcolo di tutto, per un avvio pulito, cancella i file nella cartella "input" e mettici dentro solo il file con estensione .mmbackup')
    else:
        mmbackup_file = mmbackup_files[0]
        zip_file = mmbackup_file.replace(".mmbackup", ".zip")

        # Rinomina il file
        os.rename(mmbackup_file, zip_file)
        print(f"File rinominato: {mmbackup_file} -> {zip_file}")

        # 2. Estrai il contenuto
        extract_folder = "estratto"
        os.makedirs(extract_folder, exist_ok=True)

        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall(extract_folder)
            print(f"File estratti nella cartella '{extract_folder}'")

        # 3. Cerca il file myFinance.db
        db_path = os.path.join(extract_folder, "myFinance.db")
        if not os.path.exists(db_path):
            raise FileNotFoundError("myFinance.db non trovato nell'archivio estratto.")

        # 4. Connessione al database e export tabelle
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        output_folder = "input"
        os.makedirs(output_folder, exist_ok=True)

        for (table_name,) in tables:
            # Usa virgolette doppie per proteggere i nomi delle tabelle
            cursor.execute(f'SELECT * FROM "{table_name}"')
            colonne = [desc[0] for desc in cursor.description]
            righe = cursor.fetchall()

            dati_tabella = [dict(zip(colonne, riga)) for riga in righe]

            json_path = os.path.join(output_folder, f"{table_name}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(dati_tabella, f, ensure_ascii=False, indent=4)

            print(f"Tabella '{table_name}' esportata in {json_path}")


        conn.close()
        print("✅ Esportazione completata.")


    with open('./input/account.json') as file:
        account = json.load(file)
    with open('./input/transaction.json') as file:
        transaction = json.load(file)
    with open('./input/transfer.json') as file:
        transfer = json.load(file)
    with open('./input/sync_link.json') as file:
        sync_link = json.load(file)
    with open('./input/category.json') as file:
        category = json.load(file)

    category_map = {item['uid']: item for item in category}
    account_map = {item['uid']: item for item in account}
    transaction_account_map = {item['entityUid']: item for item in sync_link if item.get('otherType') == 'Account'}
    transaction_category_map = {item['entityUid']: item for item in sync_link if item.get('otherType') == 'Category'}
    transfer_from_account_map = {item['entityUid']: item for item in sync_link if item.get('otherType') == 'FromAccount'}
    transfer_to_account_map = {item['entityUid']: item for item in sync_link if item.get('otherType') == 'ToAccount'}

    outputTransactions = [] # One unique JSON for every transaction & transfer

    for t in transaction:
        if t['isRemoved'] == 1:
            continue
        transactionId = t['uid']

        value = int(t['amountInDefaultCurrency']) / 100 # Output example: "10.50"
        date = t['date'] # Output format: "YYYY-MM-DD"
        account = account_map[transaction_account_map[transactionId]['otherUid']]
        if account['ignoreInBalance'] == 1:
            continue

        account_title = account['title']
        if t['uid'] in transaction_category_map:
            category = category_map[transaction_category_map[t['uid']]['otherUid']]['title']
        else:
            category = "Regolazione saldo"        
        
        if (t['type'] == 'Expense'):
            outputTransactions.append(Transaction('Spesa', date, value, account_title, category, '', ''))
        elif (t['type'] == 'Income'):
            outputTransactions.append(Transaction('Entrata', date, value, account_title, category, '', ''))


    for t in transfer:
        if t['isRemoved'] == 1:
            continue
        transferId = t['uid']
        value = int(t['fromAmount']) / 100 # Output example: "10.50"
        date = t['date'] # Output format: "YYYY-MM-DD"
        from_account = account_map[transfer_from_account_map[transferId]['otherUid']]['title']
        to_account = account_map[transfer_to_account_map[transferId]['otherUid']]['title']
        outputTransactions.append(Transaction('Giroconto', date, value, '', '', from_account, to_account))

    # Sort by date
    outputTransactions.sort(key=lambda t: t.date)
        
    # Percorso della cartella di output
    cartella_output = "output"
    os.makedirs(cartella_output, exist_ok=True)  # Crea la cartella se non esiste
        
    # Percorso del file
    percorso_file = os.path.join(cartella_output, "output.json")

    # Scrittura della lista come JSON
    with open(percorso_file, "w", encoding="utf-8") as f:
        json.dump(outputTransactions, f, ensure_ascii=False, indent=4, cls=TransactionEncoder)

    print(f"File salvato in: {percorso_file}")