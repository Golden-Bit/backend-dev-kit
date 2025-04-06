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

# --------------------------- Modelli ---------------------------

# Modello per la creazione del database
class DatabaseCreationRequest(BaseModel):
    db_name: str

# Modello per la concessione dei permessi (sia a livello di DB che di collezione)
class PermissionGrantRequest(BaseModel):
    target_username: str
    permission: str  # "read", "write" o "admin"

# Modello per la revoca dei permessi
class PermissionRevokeRequest(BaseModel):
    target_username: str
    permission: str  # "read", "write" o "admin"

# --------------------------- Utility per autenticazione e permessi ---------------------------

def get_current_user(token: str) -> Dict[str, Any]:
    """
    Recupera le informazioni dell'utente tramite l'endpoint /user-info della nuova API di autenticazione.
    """
    try:
        response = requests.post(f"{AUTH_SERVICE_URL}/user-info", json={"access_token": token})
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Errore nell'autenticazione: " + str(e))

def find_database_record(db_name: str, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Cerca il record del database nei metadata dell'utente.
    """
    for db in user.get("databases", []):
        if db.get("db_name") == db_name:
            return db
    return None

def check_db_permission(db_record: Dict[str, Any], current_username: str, required_permission: str) -> bool:
    """
    Verifica se l'utente ha il permesso richiesto a livello di database.
    Il proprietario ha sempre tutti i permessi.
    """
    if db_record.get("owner") == current_username:
        return True
    for entry in db_record.get("shared_with", []):
        if entry.get("username") == current_username and required_permission in entry.get("permissions", []):
            return True
    return False

def verify_user_database(db_name: str, user: Dict[str, Any], required_permission: str = "read"):
    """
    Verifica che il database esista nei metadata e che l'utente abbia il permesso richiesto.
    """
    db_record = find_database_record(db_name, user)
    if not db_record or not check_db_permission(db_record, user.get("username"), required_permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Non sei autorizzato ad eseguire operazioni con permesso '{required_permission}' sul database.")

# Funzioni per la gestione dei permessi a livello di collezione

def find_collection_record(db_record: Dict[str, Any], collection_name: str) -> Optional[Dict[str, Any]]:
    """
    Cerca nel record del database il record relativo alla collezione.
    """
    for coll in db_record.get("collections", []):
        if coll.get("collection_name") == collection_name:
            return coll
    return None

def check_collection_permission(collection_record: Dict[str, Any], current_username: str, required_permission: str) -> bool:
    """
    Verifica se l'utente ha il permesso richiesto a livello di collezione.
    Il proprietario della collezione ha sempre tutti i permessi.
    """
    if collection_record.get("owner") == current_username:
        return True
    for entry in collection_record.get("shared_with", []):
        if entry.get("username") == current_username and required_permission in entry.get("permissions", []):
            return True
    return False

def verify_user_collection(db_name: str, collection_name: str, user: Dict[str, Any], required_permission: str = "read"):
    """
    Verifica che la collezione esista nei metadata del database dell'utente e che l'utente abbia il permesso richiesto.
    """
    db_record = find_database_record(db_name, user)
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Database non trovato nei metadata dell'utente.")
    coll_record = find_collection_record(db_record, collection_name)
    if not coll_record or not check_collection_permission(coll_record, user.get("username"), required_permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Non sei autorizzato ad eseguire operazioni con permesso '{required_permission}' sulla collezione '{collection_name}'.")

def update_user_databases(token: str, databases: List[Dict[str, Any]]):
    """
    Aggiorna i metadata dell'utente relativi ai database (attributo custom:databases).
    """
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

# --------------------------- Endpoints per la gestione dei database e collezioni ---------------------------

@router.post("/create_user_database/", summary="Crea un nuovo database MongoDB con le proprie credenziali",
             response_description="Database creato con successo")
async def create_user_database(request: DatabaseCreationRequest, token: str):
    """
    Crea un nuovo database MongoDB. Il nome viene prefissato con il nome utente.
    Il database viene salvato nei metadata con:
      - owner: username
      - shared_with: lista vuota
      - collections: lista vuota (inizialmente)
    """
    current_user = get_current_user(token)
    username = current_user.get("username")
    prefixed_db_name = f"{username}-{request.db_name}"
    host = "mongodb"
    port = 27017

    try:
        db_credentials = {"db_name": prefixed_db_name, "host": host, "port": port}
        response = requests.post(f"{MONGO_SERVICE_URL}/create_database/", json=db_credentials)
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore durante la creazione del database")
        user_databases = current_user.get("databases", [])
        if not any(db.get("db_name") == prefixed_db_name for db in user_databases):
            new_db = {
                "db_name": prefixed_db_name,
                "host": host,
                "port": port,
                "owner": username,
                "shared_with": [],
                "collections": []  # Inizialmente nessuna collezione
            }
            user_databases.append(new_db)
            update_user_databases(token, user_databases)
        return {"message": f"Database '{prefixed_db_name}' creato con successo."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Errore durante la creazione del database: " + str(e))


@router.get("/list_databases/", summary="Ottieni l'elenco dei database dell'utente",
            response_description="Elenco dei database esistenti")
async def list_databases(token: str):
    """
    Recupera l'elenco dei database (proprietà e condivisi) dall'utente.
    """
    current_user = get_current_user(token)
    return {"databases": current_user.get("databases", [])}


@router.post("/{db_name}/create_collection/", summary="Crea una nuova collezione",
             response_description="Collezione creata con successo")
async def create_collection(db_name: str, collection_name: str, token: str):
    """
    Crea una nuova collezione all'interno di un database.
    Richiede il permesso "write" sul database.
    Dopo la creazione, aggiorna i metadata del database aggiungendo la collezione con:
      - collection_name
      - owner: lo stesso del database
      - shared_with: lista vuota
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="write")
    try:
        response = requests.post(f"{MONGO_SERVICE_URL}/{db_name}/create_collection/",
                                 params={"collection_name": collection_name})
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nella creazione della collezione.")
        # Aggiorna i metadata del database per aggiungere la nuova collezione
        user_databases = current_user.get("databases", [])
        db_record = find_database_record(db_name, current_user)
        if db_record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database non trovato nei metadata.")
        collections = db_record.get("collections", [])
        if not any(coll.get("collection_name") == collection_name for coll in collections):
            new_coll = {"collection_name": collection_name, "owner": current_user.get("username"), "shared_with": []}
            collections.append(new_coll)
            db_record["collections"] = collections
            # Sostituisce il record aggiornato nell'elenco dei database
            for i, db in enumerate(user_databases):
                if db.get("db_name") == db_name:
                    user_databases[i] = db_record
                    break
            update_user_databases(token, user_databases)
        return {"message": f"Collezione '{collection_name}' creata con successo in database '{db_name}'."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nella creazione della collezione: " + str(e))


@router.get("/{db_name}/list_collections/", summary="Elenca le collezioni in un database",
            response_description="Elenco delle collezioni")
async def list_collections(db_name: str, token: str):
    """
    Recupera l'elenco delle collezioni di un database dai metadata dell'utente.
    Richiede il permesso "read".
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="read")
    db_record = find_database_record(db_name, current_user)
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database non trovato nei metadata.")
    return {"collections": db_record.get("collections", [])}


@router.delete("/{db_name}/delete_collection/{collection_name}/", summary="Elimina una collezione",
               response_description="Collezione eliminata con successo")
async def delete_collection(db_name: str, collection_name: str, token: str):
    """
    Elimina una collezione da un database.
    Richiede il permesso "write" sul database.
    Dopo l'eliminazione, aggiorna i metadata rimuovendo il record della collezione.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="write")
    try:
        response = requests.delete(f"{MONGO_SERVICE_URL}/{db_name}/delete_collection/{collection_name}/")
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nell'eliminazione della collezione.")
        user_databases = current_user.get("databases", [])
        db_record = find_database_record(db_name, current_user)
        if db_record:
            collections = db_record.get("collections", [])
            collections = [coll for coll in collections if coll.get("collection_name") != collection_name]
            db_record["collections"] = collections
            for i, db in enumerate(user_databases):
                if db.get("db_name") == db_name:
                    user_databases[i] = db_record
                    break
            update_user_databases(token, user_databases)
        return {"message": f"Collezione '{collection_name}' eliminata con successo da database '{db_name}'."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'eliminazione della collezione: " + str(e))


@router.post("/{db_name}/{collection_name}/add_item/", summary="Aggiungi un documento con schema validato")
async def add_item(db_name: str, collection_name: str, data: Dict[str, Any], token: str):
    """
    Aggiunge un documento in una collezione.
    Richiede il permesso "write" sul database.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="write")
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


@router.post("/{db_name}/get_items/{collection_name}/", summary="Recupera documenti di una collezione",
             response_description="Documenti recuperati")
async def get_items(db_name: str, collection_name: str, filter: Optional[Dict[str, Any]] = None, token: str = ""):
    """
    Recupera i documenti di una collezione con filtro.
    Richiede il permesso "read" sul database.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="read")
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


@router.put("/{db_name}/update_item/{collection_name}/{item_id}/", summary="Aggiorna un documento",
            response_description="Documento aggiornato con successo")
async def update_item(db_name: str, collection_name: str, item_id: str, item: Dict[str, Any], token: str = ""):
    """
    Aggiorna un documento in una collezione.
    Richiede il permesso "write" sul database.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="write")
    try:
        response = requests.put(f"{MONGO_SERVICE_URL}/{db_name}/update_item/{collection_name}/{item_id}/", json=item)
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nell'aggiornamento del documento.")
        return {"message": "Documento aggiornato con successo."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'aggiornamento del documento: " + str(e))


@router.delete("/{db_name}/delete_item/{collection_name}/{item_id}/", summary="Elimina un documento",
               response_description="Documento eliminato con successo")
async def delete_item(db_name: str, collection_name: str, item_id: str, token: str = ""):
    """
    Elimina un documento in una collezione.
    Richiede il permesso "write" sul database.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="write")
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
            response_description="Documento recuperato con successo")
async def get_item(db_name: str, collection_name: str, item_id: str, token: str = ""):
    """
    Recupera un documento specifico in una collezione.
    Richiede il permesso "read" sul database.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="read")
    try:
        response = requests.get(f"{MONGO_SERVICE_URL}/{db_name}/get_item/{collection_name}/{item_id}/")
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore nel recupero del documento.")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nel recupero del documento: " + str(e))


@router.delete("/delete_database/{db_name}/", summary="Elimina un database",
               response_description="Database eliminato con successo")
async def delete_database(db_name: str, token: str = ""):
    """
    Elimina un database e rimuove il suo riferimento dai metadata dell'utente.
    Richiede il permesso "write" (solitamente solo il proprietario).
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="write")
    try:
        response = requests.delete(f"{MONGO_SERVICE_URL}/delete_database/{db_name}/")
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Errore durante l'eliminazione del database")
        updated_databases = [db for db in current_user.get("databases", []) if db.get("db_name") != db_name]
        update_user_databases(token, updated_databases)
        return {"message": f"Database '{db_name}' eliminato con successo e rimosso dai metadata dell'utente."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Errore durante l'eliminazione del database: " + str(e))


@router.post("/{db_name}/search", summary="Ricerca documenti con filtro e paginazione",
             response_description="Risultati della ricerca")
async def search_documents(db_name: str, filter: Optional[Dict[str, Any]] = None, skip: int = 0, size: int = 10, token: str = ""):
    """
    Esegue una ricerca nella collezione in base a un filtro con paginazione.
    Richiede il permesso "read" sul database.
    """
    current_user = get_current_user(token)
    verify_user_database(db_name, current_user, required_permission="read")
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


# -------------------- Endpoints per la gestione dei permessi sui database --------------------

@router.post("/{db_name}/grant_permission", summary="Concedi permessi sul database",
             response_description="Permesso concesso con successo")
async def grant_db_permission(db_name: str, permission_req: PermissionGrantRequest, token: str):
    """
    Concede un permesso (read, write, admin) a un altro utente sul database.
    Solo il proprietario può concedere permessi.
    """
    current_user = get_current_user(token)
    db_record = find_database_record(db_name, current_user)
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Database non trovato nei metadata dell'utente.")
    if db_record.get("owner") != current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo il proprietario può concedere permessi.")
    shared = db_record.get("shared_with", [])
    for entry in shared:
        if entry.get("username") == permission_req.target_username:
            if permission_req.permission not in entry.get("permissions", []):
                entry.setdefault("permissions", []).append(permission_req.permission)
            break
    else:
        shared.append({"username": permission_req.target_username, "permissions": [permission_req.permission]})
    db_record["shared_with"] = shared
    user_databases = current_user.get("databases", [])
    for i, db in enumerate(user_databases):
        if db.get("db_name") == db_name:
            user_databases[i] = db_record
            break
    update_user_databases(token, user_databases)
    return {"message": f"Permesso '{permission_req.permission}' concesso a {permission_req.target_username} sul database '{db_name}'."}

@router.post("/{db_name}/revoke_permission", summary="Revoca permessi sul database",
             response_description="Permesso revocato con successo")
async def revoke_db_permission(db_name: str, permission_req: PermissionRevokeRequest, token: str):
    """
    Revoca un permesso (read, write, admin) da un altro utente sul database.
    Solo il proprietario può revocare i permessi.
    """
    current_user = get_current_user(token)
    db_record = find_database_record(db_name, current_user)
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Database non trovato nei metadata dell'utente.")
    if db_record.get("owner") != current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo il proprietario può revocare i permessi.")
    shared = db_record.get("shared_with", [])
    for entry in shared:
        if entry.get("username") == permission_req.target_username:
            if permission_req.permission in entry.get("permissions", []):
                entry["permissions"].remove(permission_req.permission)
            if not entry["permissions"]:
                shared.remove(entry)
            break
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Utente target non trovato nei permessi condivisi.")
    db_record["shared_with"] = shared
    user_databases = current_user.get("databases", [])
    for i, db in enumerate(user_databases):
        if db.get("db_name") == db_name:
            user_databases[i] = db_record
            break
    update_user_databases(token, user_databases)
    return {"message": f"Permesso '{permission_req.permission}' revocato da {permission_req.target_username} sul database '{db_name}'."}

@router.get("/{db_name}/check_permission", summary="Verifica permesso sul database",
            response_description="Permesso verificato")
async def check_db_permission_endpoint(db_name: str, required_permission: str, token: str):
    """
    Verifica se l'utente (con il token fornito) possiede il permesso specificato sul database.
    """
    current_user = get_current_user(token)
    db_record = find_database_record(db_name, current_user)
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Database non trovato nei metadata.")
    has_perm = check_db_permission(db_record, current_user.get("username"), required_permission)
    return {"db_name": db_name, "has_permission": has_perm, "required_permission": required_permission}


# -------------------- Endpoints per la gestione dei permessi sulle collezioni --------------------

@router.post("/{db_name}/{collection_name}/grant_permission", summary="Concedi permessi sulla collezione",
             response_description="Permesso concesso con successo")
async def grant_collection_permission(db_name: str, collection_name: str, permission_req: PermissionGrantRequest, token: str):
    """
    Concede un permesso (read, write, admin) a un altro utente su una specifica collezione.
    Solo il proprietario della collezione può concedere permessi.
    """
    current_user = get_current_user(token)
    db_record = find_database_record(db_name, current_user)
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database non trovato nei metadata.")
    coll_record = find_collection_record(db_record, collection_name)
    if not coll_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collezione non trovata nei metadata.")
    if coll_record.get("owner") != current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo il proprietario della collezione può concedere permessi.")
    shared = coll_record.get("shared_with", [])
    for entry in shared:
        if entry.get("username") == permission_req.target_username:
            if permission_req.permission not in entry.get("permissions", []):
                entry.setdefault("permissions", []).append(permission_req.permission)
            break
    else:
        shared.append({"username": permission_req.target_username, "permissions": [permission_req.permission]})
    coll_record["shared_with"] = shared
    # Aggiorna il record della collezione all'interno del database
    db_record.setdefault("collections", [])
    for i, coll in enumerate(db_record["collections"]):
        if coll.get("collection_name") == collection_name:
            db_record["collections"][i] = coll_record
            break
    user_databases = current_user.get("databases", [])
    for i, db in enumerate(user_databases):
        if db.get("db_name") == db_name:
            user_databases[i] = db_record
            break
    update_user_databases(token, user_databases)
    return {"message": f"Permesso '{permission_req.permission}' concesso a {permission_req.target_username} sulla collezione '{collection_name}' del database '{db_name}'."}

@router.post("/{db_name}/{collection_name}/revoke_permission", summary="Revoca permessi sulla collezione",
             response_description="Permesso revocato con successo")
async def revoke_collection_permission(db_name: str, collection_name: str, permission_req: PermissionRevokeRequest, token: str):
    """
    Revoca un permesso (read, write, admin) da un altro utente su una specifica collezione.
    Solo il proprietario della collezione può revocare i permessi.
    """
    current_user = get_current_user(token)
    db_record = find_database_record(db_name, current_user)
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database non trovato nei metadata.")
    coll_record = find_collection_record(db_record, collection_name)
    if not coll_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collezione non trovata nei metadata.")
    if coll_record.get("owner") != current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo il proprietario della collezione può revocare i permessi.")
    shared = coll_record.get("shared_with", [])
    for entry in shared:
        if entry.get("username") == permission_req.target_username:
            if permission_req.permission in entry.get("permissions", []):
                entry["permissions"].remove(permission_req.permission)
            if not entry["permissions"]:
                shared.remove(entry)
            break
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Utente target non trovato nei permessi condivisi della collezione.")
    coll_record["shared_with"] = shared
    for i, coll in enumerate(db_record.get("collections", [])):
        if coll.get("collection_name") == collection_name:
            db_record["collections"][i] = coll_record
            break
    user_databases = current_user.get("databases", [])
    for i, db in enumerate(user_databases):
        if db.get("db_name") == db_name:
            user_databases[i] = db_record
            break
    update_user_databases(token, user_databases)
    return {"message": f"Permesso '{permission_req.permission}' revocato da {permission_req.target_username} sulla collezione '{collection_name}' del database '{db_name}'."}

@router.get("/{db_name}/{collection_name}/check_permission", summary="Verifica permesso sulla collezione",
            response_description="Permesso verificato")
async def check_collection_permission_endpoint(db_name: str, collection_name: str, required_permission: str, token: str):
    """
    Verifica se l'utente (con il token fornito) possiede il permesso specificato sulla collezione.
    """
    current_user = get_current_user(token)
    db_record = find_database_record(db_name, current_user)
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database non trovato nei metadata.")
    coll_record = find_collection_record(db_record, collection_name)
    if not coll_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collezione non trovata nei metadata.")
    has_perm = check_collection_permission(coll_record, current_user.get("username"), required_permission)
    return {"db_name": db_name, "collection_name": collection_name, "has_permission": has_perm, "required_permission": required_permission}
