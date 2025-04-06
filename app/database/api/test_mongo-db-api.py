import time
import requests
import random
import string

# BASE_URL è l'URL principale della tua API di basso livello (MongoDB FastAPI Backend).
# Se la stai eseguendo in locale sulla porta 8094, assicurati che sia corretto (es. http://localhost:8094).
BASE_URL = "http://localhost:8010"

def random_string(n=8):
    """Genera una stringa casuale di n caratteri minuscoli."""
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(n))

def create_database(db_name):
    """Chiama l'endpoint che crea un nuovo database."""
    payload = {
        "db_name": db_name,
        "host": "mongodb",     # Sostituisci con host corretto, se necessario
        "port": 27017          # Sostituisci con la porta corretta, se necessario
    }
    return requests.post(f"{BASE_URL}/create_database/", json=payload)

def create_collection(db_name, collection_name):
    """Chiama l'endpoint che crea una nuova collezione all'interno di un database."""
    # In questa API, la collezione si passa come parametro GET (params=...)
    return requests.post(f"{BASE_URL}/{db_name}/create_collection/",
                         params={"collection_name": collection_name})

def add_item(db_name, collection_name, item_data):
    """Chiama l'endpoint per aggiungere un documento in una collezione."""
    return requests.post(f"{BASE_URL}/{db_name}/{collection_name}/add_item/", json=item_data)

def get_items(db_name, collection_name, filter_data=None):
    """Chiama l'endpoint per recuperare i documenti da una collezione."""
    # get_items di questa API prevede un body JSON (POST) con il filtro
    if filter_data is None:
        filter_data = {}
    return requests.post(f"{BASE_URL}/{db_name}/get_items/{collection_name}/", json=filter_data)

def delete_database(db_name):
    """Chiama l'endpoint per eliminare un intero database."""
    return requests.delete(f"{BASE_URL}/delete_database/{db_name}/")

def main():
    # Crea nomi random di DB e collezione per non confliggere con altri test
    db_name = "testdb_" + random_string(6)
    collection_name = "testcol_" + random_string(6)

    print(f"--- Inizio test su API di basso livello ---")
    print(f"Database di test: {db_name}")
    print(f"Collezione di test: {collection_name}\n")

    # 1) Crea un DB (se vuoi testare su uno esistente puoi saltare)
    start = time.time()
    resp = create_database(db_name)
    elapsed = time.time() - start
    print(f"[create_database] Tempo: {elapsed:.2f}s | Status code: {resp.status_code} | Risposta: {resp.text}\n")

    # 2) Crea una collezione
    start = time.time()
    resp = create_collection(db_name, collection_name)
    elapsed = time.time() - start
    print(f"[create_collection] Tempo: {elapsed:.2f}s | Status code: {resp.status_code} | Risposta: {resp.text}\n")

    # 3) Aggiungi un documento
    item_data = {
        "field1": random_string(),
        "field2": random.randint(1, 100)
    }
    start = time.time()
    resp = add_item(db_name, collection_name, item_data)
    elapsed = time.time() - start
    print(f"[add_item] Tempo: {elapsed:.2f}s | Status code: {resp.status_code} | Risposta: {resp.text}\n")

    # 4) Recupera i documenti
    start = time.time()
    resp = get_items(db_name, collection_name)
    elapsed = time.time() - start
    print(f"[get_items] Tempo: {elapsed:.2f}s | Status code: {resp.status_code} | Risposta: {resp.text}\n")

    # 5) (Opzionale) Elimina il database per pulire (così non lasciamo troppi DB in giro)
    start = time.time()
    resp = delete_database(db_name)
    elapsed = time.time() - start
    print(f"[delete_database] Tempo: {elapsed:.2f}s | Status code: {resp.status_code} | Risposta: {resp.text}\n")

if __name__ == "__main__":
    main()
