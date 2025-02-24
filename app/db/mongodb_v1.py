from fastapi import APIRouter, HTTPException, status, UploadFile, File, Body
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import requests
import json

# Carica le configurazioni dal file config.json
with open("config.json") as f:
    config_dict = json.load(f)

# URL del servizio MongoDB e dell’autenticazione (basata su Cognito)
MONGO_SERVICE_URL = config_dict["mongodb_service_url"]
AUTH_SERVICE_URL = "http://localhost:8000/v1/user"  # endpoint della nuova API di autenticazione

router = APIRouter(
    prefix="/v2/mongo",
    tags=["MongoDB Management"],
    responses={404: {"description": "Not found"}},
)

# Modello per la creazione del database
class DatabaseCreationRequest(BaseModel):
    db_name: str

# Utility: recupera le informazioni dell'utente passando il token
def get_current_user(token: str) -> Dict[str, Any]:
    try:
        # Invoca l'endpoint di user-info della nuova API di autenticazione
        response = requests.post(f"{AUTH_SERVICE_URL}/user-info", json={"access_token": token})
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Errore nell'autenticazione: " + str(e))

# Utility: verifica se il database è associato all'utente (i metadata sono in un JSON libero)
def verify_user_database(db_name: str, user: Dict[str, Any]):
    # Si assume che i database siano salvati nell'attributo "databases" dell'utente (lista di dict)
    if "databases" not in user or not any(db.get("db_name") == db_name for db in user["databases"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Non sei autorizzato ad accedere a questo database.")

# Utility: aggiorna i metadata dell'utente (in particolare l'attributo custom:databases)
def update_user_databases(token: str, databases: List[Dict[str, Any]]):
    # L'endpoint di update-attributes della nuova API si aspetta:
    # { "access_token": token, "attributes": [ {"Name": "custom:databases", "Value": <JSON string>} ] }
    payload = {
        "access_token": token,
        "attributes": [
            {"Name": "custom:databases", "Value": json.dumps(databases)}
        ]
    }
    update_resp = requests.post(f"{AUTH_SERVICE_URL}/update-attributes", json=payload)
    if update_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore durante l'aggiornamento dei metadata dell'utente.")

# -------------------- Endpoints per la gestione dei database e delle collezioni --------------------

@router.post("/create_user_database/", summary="Crea un nuovo database MongoDB con le proprie credenziali",
             response_description="Database creato con successo")
async def create_user_database(request: DatabaseCreationRequest, token: str):
    """
    Crea un nuovo database MongoDB utilizzando le proprie credenziali.
    Il nome del database viene prefissato con il nome utente ottenuto dall'endpoint di autenticazione.
    Dopo la creazione, il database viene aggiunto ai metadata dell'utente aggiornando l'attributo custom:databases.
    """
    current_user = get_current_user(token)
    username = current_user.get("username")
    prefixed_db_name = f"{username}-{request.db_name}"
    # Utilizziamo host e porta standard
    host = "mongodb"
    port = 27017

    try:
        db_credentials = {"db_name": prefixed_db_name, "host": host, "port": port}
        response = requests.post(f"{MONGO_SERVICE_URL}/create_database/", json=db_credentials)
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore durante la creazione del database")
        # Se il database non è già presente nei metadata dell'utente, lo aggiungiamo
        user_databases = current_user.get("databases", [])
        if not any(db.get("db_name") == prefixed_db_name and db.get("host") == host for db in user_databases):
            user_databases.append({"db_name": prefixed_db_name, "host": host, "port": port})
            # Aggiorna i metadata dell'utente tramite l'endpoint update-attributes
            update_user_databases(token, user_databases)
        return {"message": f"Database '{prefixed_db_name}' creato con successo."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Errore durante la creazione del database: " + str(e))


@router.get("/list_databases/", summary="Ottieni l'elenco dei database dell'utente",
            response_description="Elenco dei database esistenti")
async def list_databases(token: str):
    """
    Recupera l'elenco dei database associati all'utente (metadata).
    """
    current_user = get_current_user(token)
    return {"databases": current_user.get("databases", [])}


@router.post("/{db_name}/create_collection/", summary="Crea una nuova collezione",
             response_description="La collezione è stata creata con successo")
async def create_collection(db_name: str, collection_name: str, token: str):
    """
    Crea una nuova collezione all'interno di un database esistente.
    Verifica che il database appartenga all'utente.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        response = requests.post(f"{MONGO_SERVICE_URL}/{db_name}/create_collection/",
                                 params={"collection_name": collection_name})
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nella creazione della collezione.")
        return {"message": f"Collection '{collection_name}' creata con successo in database '{db_name}'."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nella creazione della collezione: " + str(e))


@router.get("/{db_name}/list_collections/", summary="Elenca le collezioni in un database",
            response_description="Elenco delle collezioni presenti nel database")
async def list_collections(db_name: str, token: str):
    """
    Recupera l'elenco di tutte le collezioni in un database specifico.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        response = requests.get(f"{MONGO_SERVICE_URL}/{db_name}/list_collections/")
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nel recupero delle collezioni.")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nel recupero delle collezioni: " + str(e))


@router.delete("/{db_name}/delete_collection/{collection_name}/", summary="Elimina una collezione esistente",
               response_description="La collezione è stata eliminata con successo")
async def delete_collection(db_name: str, collection_name: str, token: str):
    """
    Elimina una collezione esistente in un database specifico.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        response = requests.delete(f"{MONGO_SERVICE_URL}/{db_name}/delete_collection/{collection_name}/")
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nell'eliminazione della collezione.")
        return {"message": f"Collection '{collection_name}' eliminata con successo da database '{db_name}'."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'eliminazione della collezione: " + str(e))


@router.post("/{db_name}/{collection_name}/upload_schema/", summary="Carica uno o più schemi YAML per una collezione specifica")
async def upload_schema(db_name: str, collection_name: str, files: List[UploadFile] = File(...), token: str = ""):
    """
    Carica uno o più schemi YAML per una collezione specifica in un database.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        files_data = []
        for file in files:
            content = await file.read()
            files_data.append({
                "filename": file.filename,
                "content": content.decode("utf-8")
            })
        response = requests.post(
            f"{MONGO_SERVICE_URL}/upload_schema/{db_name}/{collection_name}/",
            json={"files": files_data}
        )
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore durante il caricamento degli schemi.")
        return {"message": f"Schemi per la collezione '{collection_name}' in database '{db_name}' caricati con successo."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore durante il caricamento degli schemi: " + str(e))


@router.post("/{db_name}/{collection_name}/add_item/", summary="Aggiungi un documento in una collezione convalidato tramite schema")
async def add_item(db_name: str, collection_name: str, data: Dict[str, Any], token: str):
    """
    Aggiunge un nuovo documento in una collezione esistente, convalidato tramite uno schema YAML specifico.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        response = requests.post(
            f"{MONGO_SERVICE_URL}/{db_name}/{collection_name}/add_item/",
            json=data
        )
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nell'aggiunta del documento.")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'aggiunta del documento: " + str(e))


@router.post("/{db_name}/get_items/{collection_name}/", summary="Recupera tutti i documenti di una collezione",
             response_description="Elenco dei documenti nella collezione")
async def get_items(db_name: str, collection_name: str, filter: Optional[Dict[str, Any]] = None, token: str = ""):
    """
    Recupera tutti i documenti di una collezione specifica, con la possibilità di applicare un filtro.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    query = filter if filter is not None else {}
    try:
        response = requests.post(f"{MONGO_SERVICE_URL}/{db_name}/get_items/{collection_name}/", json=query)
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nel recupero dei documenti.")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nel recupero dei documenti: " + str(e))


@router.put("/{db_name}/update_item/{collection_name}/{item_id}/", summary="Aggiorna un documento in una collezione",
            response_description="Il documento è stato aggiornato con successo")
async def update_item(db_name: str, collection_name: str, item_id: str, item: Dict[str, Any], token: str = ""):
    """
    Aggiorna un documento esistente in una collezione.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        response = requests.put(f"{MONGO_SERVICE_URL}/{db_name}/update_item/{collection_name}/{item_id}/", json=item)
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nell'aggiornamento del documento.")
        return {"message": "Documento aggiornato con successo."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'aggiornamento del documento: " + str(e))


@router.delete("/{db_name}/delete_item/{collection_name}/{item_id}/", summary="Elimina un documento in una collezione",
               response_description="Il documento è stato eliminato con successo")
async def delete_item(db_name: str, collection_name: str, item_id: str, token: str = ""):
    """
    Elimina un documento esistente in una collezione.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        response = requests.delete(f"{MONGO_SERVICE_URL}/{db_name}/delete_item/{collection_name}/{item_id}/")
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nell'eliminazione del documento.")
        return {"message": "Documento eliminato con successo."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'eliminazione del documento: " + str(e))


@router.get("/{db_name}/get_item/{collection_name}/{item_id}/", summary="Recupera un documento specifico",
            response_description="Il documento è stato recuperato con successo")
async def get_item(db_name: str, collection_name: str, item_id: str, token: str = ""):
    """
    Recupera un documento specifico in una collezione.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        response = requests.get(f"{MONGO_SERVICE_URL}/{db_name}/get_item/{collection_name}/{item_id}/")
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nel recupero del documento.")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nel recupero del documento: " + str(e))


@router.delete("/delete_database/{db_name}/", summary="Elimina un database esistente",
               response_description="Il database è stato eliminato con successo")
async def delete_database(db_name: str, token: str = ""):
    """
    Elimina un database esistente e rimuove il suo riferimento dai metadata dell'utente.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    try:
        response = requests.delete(f"{MONGO_SERVICE_URL}/delete_database/{db_name}/")
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore durante l'eliminazione del database")
        # Aggiorna i metadata rimuovendo il database eliminato
        updated_databases = [db for db in current_user.get("databases", []) if db.get("db_name") != db_name]
        update_user_databases(token, updated_databases)
        return {"message": f"Database '{db_name}' eliminato con successo e rimosso dai metadata dell'utente."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Errore durante l'eliminazione del database: " + str(e))


@router.post("/{db_name}/search", summary="Ricerca documenti con filtro e paginazione",
             response_description="Risultati della ricerca con parametri di paginazione")
async def search_documents(db_name: str, filter: Optional[Dict[str, Any]] = None, skip: int = 0, size: int = 10, token: str = ""):
    """
    Esegue una ricerca nella collezione specificata in base ad un filtro con paginazione.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user)
    payload = {"filter": filter if filter is not None else {}, "skip": skip, "size": size}
    try:
        response = requests.post(f"{MONGO_SERVICE_URL}/{db_name}/search", json=payload)
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nella ricerca dei documenti.")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nella ricerca dei documenti: " + str(e))
