from fastapi import APIRouter, HTTPException, status, UploadFile, File, Body
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import requests
import json
from google.cloud import storage

# Carica le configurazioni dal file config.json
with open("config.json") as f:
    config_dict = json.load(f)

# URL dei servizi
GCS_PROJECT = config_dict.get("gcs_project")  # Nome del progetto Google Cloud
AUTH_SERVICE_URL = "http://localhost:8000/v1/user"  # endpoint della nuova API di autenticazione

router = APIRouter(
    prefix="/storage",
    tags=["Google Cloud Storage Management"],
    responses={404: {"description": "Not found"}},
)

# Inizializza il client per Google Cloud Storage
gcs_client = storage.Client(project=GCS_PROJECT)


# --------------------------- Modelli ---------------------------

# Modello per la creazione di un bucket
class BucketCreationRequest(BaseModel):
    bucket_name: str


# Modello per la gestione dei permessi sui bucket
class PermissionGrantRequest(BaseModel):
    target_username: str
    permission: str  # "read", "write", "admin"


class PermissionRevokeRequest(BaseModel):
    target_username: str
    permission: str  # "read", "write", "admin"


# --------------------------- Utility per autenticazione e permessi ---------------------------

def get_current_user(token: str) -> Dict[str, Any]:
    """
    Recupera le informazioni dell'utente tramite la nuova API di autenticazione.
    """
    try:
        response = requests.post(f"{AUTH_SERVICE_URL}/user-info", json={"access_token": token})
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Errore nell'autenticazione: " + str(e))


def find_bucket_record(bucket_name: str, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Cerca nel metadata dell'utente il record relativo al bucket.
    """
    for bucket in user.get("storage", []):
        if bucket.get("bucket_name") == bucket_name:
            return bucket
    return None


def check_bucket_permission(bucket_record: Dict[str, Any], current_username: str, required_permission: str) -> bool:
    """
    Controlla se l'utente corrente ha il permesso richiesto sul bucket.
    Il proprietario ha sempre tutti i permessi.
    """
    if bucket_record.get("owner") == current_username:
        return True
    shared = bucket_record.get("shared_with", [])
    for entry in shared:
        if entry.get("username") == current_username and required_permission in entry.get("permissions", []):
            return True
    return False


def verify_user_bucket(bucket_name: str, user: Dict[str, Any], required_permission: str = "read"):
    """
    Verifica che il bucket sia presente nei metadata dell'utente e che l'utente abbia il permesso richiesto.
    """
    bucket_record = find_bucket_record(bucket_name, user)
    if not bucket_record or not check_bucket_permission(bucket_record, user.get("username"), required_permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Non sei autorizzato ad eseguire operazioni con permesso '{required_permission}' sul bucket.")


def update_user_storage(token: str, storage_metadata: List[Dict[str, Any]]):
    """
    Aggiorna i metadata dell'utente relativi allo storage (attributo custom:storage).
    """
    payload = {
        "access_token": token,
        "attributes": [
            {"Name": "custom:storage", "Value": json.dumps(storage_metadata)}
        ]
    }
    update_resp = requests.post(f"{AUTH_SERVICE_URL}/update-attributes", json=payload)
    if update_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore durante l'aggiornamento dei metadata dell'utente.")


# --------------------------- Endpoints per la gestione dei bucket ---------------------------

@router.post("/create_bucket/", summary="Crea un nuovo bucket in Google Cloud Storage",
             response_description="Bucket creato con successo")
async def create_bucket(request: BucketCreationRequest, token: str):
    """
    Crea un nuovo bucket in GCS. Il nome del bucket viene prefissato con il nome utente.
    I metadata del bucket includono:
      - bucket_name
      - owner: username
      - shared_with: lista vuota (inizialmente)
    I metadata sono salvati nell'attributo custom:storage dell'utente.
    """
    current_user = get_current_user(token)
    username = current_user.get("username")
    prefixed_bucket_name = f"{username}-{request.bucket_name}"

    try:
        bucket = gcs_client.create_bucket(prefixed_bucket_name)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Errore nella creazione del bucket: " + str(e))

    # Aggiorna i metadata dell'utente
    storage_metadata = current_user.get("storage", [])
    if not any(b.get("bucket_name") == prefixed_bucket_name for b in storage_metadata):
        new_bucket = {
            "bucket_name": prefixed_bucket_name,
            "owner": username,
            "shared_with": []
        }
        storage_metadata.append(new_bucket)
        update_user_storage(token, storage_metadata)
    return {"message": f"Bucket '{prefixed_bucket_name}' creato con successo."}


@router.get("/list_buckets/", summary="Elenca i bucket dell'utente",
            response_description="Elenco dei bucket")
async def list_buckets(token: str):
    """
    Recupera l'elenco dei bucket associati all'utente (metadata).
    """
    current_user = get_current_user(token)
    return {"buckets": current_user.get("storage", [])}


@router.delete("/delete_bucket/{bucket_name}/", summary="Elimina un bucket",
               response_description="Bucket eliminato con successo")
async def delete_bucket(bucket_name: str, token: str):
    """
    Elimina un bucket da GCS e rimuove il suo riferimento dai metadata dell'utente.
    Richiede il permesso "write" (solitamente solo il proprietario).
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    try:
        bucket = gcs_client.bucket(bucket_name)
        bucket.delete(force=True)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Errore durante l'eliminazione del bucket: " + str(e))

    # Aggiorna i metadata rimuovendo il bucket eliminato
    storage_metadata = [b for b in current_user.get("storage", []) if b.get("bucket_name") != bucket_name]
    update_user_storage(token, storage_metadata)
    return {"message": f"Bucket '{bucket_name}' eliminato con successo e rimosso dai metadata dell'utente."}


# --------------------------- Endpoints per la gestione dei file ---------------------------

@router.post("/{bucket_name}/upload_file/", summary="Carica un file in un bucket",
             response_description="File caricato con successo")
async def upload_file(bucket_name: str, file: UploadFile = File(...), token: str = ""):
    """
    Carica un file in un bucket specifico.
    Richiede il permesso "write" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    try:
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(file.filename)
        blob.upload_from_file(file.file)
        return {"message": f"File '{file.filename}' caricato con successo in bucket '{bucket_name}'."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nel caricamento del file: " + str(e))


@router.get("/{bucket_name}/list_files/", summary="Elenca i file in un bucket",
            response_description="Elenco dei file")
async def list_files(bucket_name: str, prefix: Optional[str] = None, token: str = ""):
    """
    Recupera l'elenco dei file in un bucket, con possibilità di filtrare per prefisso.
    Richiede il permesso "read" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="read")
    try:
        bucket = gcs_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        files = [{"name": blob.name, "size": blob.size, "updated": blob.updated.isoformat()} for blob in blobs]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nel recupero dei file: " + str(e))


@router.get("/{bucket_name}/download_file/", summary="Scarica un file",
            response_description="URL per il download del file")
async def download_file(bucket_name: str, file_name: str, token: str = ""):
    """
    Genera un URL temporaneo per scaricare un file dal bucket.
    Richiede il permesso "read" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="read")
    try:
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        url = blob.generate_signed_url(version="v4", expiration=3600, method="GET")
        return {"download_url": url}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nella generazione dell'URL di download: " + str(e))


@router.delete("/{bucket_name}/delete_file/", summary="Elimina un file",
               response_description="File eliminato con successo")
async def delete_file(bucket_name: str, file_name: str, token: str = ""):
    """
    Elimina un file da un bucket.
    Richiede il permesso "write" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    try:
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        blob.delete()
        return {"message": f"File '{file_name}' eliminato con successo da bucket '{bucket_name}'."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'eliminazione del file: " + str(e))


# -------------------- Endpoints per la gestione dei permessi --------------------

@router.post("/{bucket_name}/grant_permission", summary="Concedi permessi su un bucket",
             response_description="Permesso concesso con successo")
async def grant_permission(bucket_name: str, permission_req: PermissionGrantRequest, token: str):
    """
    Concede un permesso (read, write, admin) a un altro utente sul bucket.
    Solo il proprietario può concedere permessi.
    """
    current_user = get_current_user(token)
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Bucket non trovato nei metadata dell'utente.")
    if bucket_record.get("owner") != current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo il proprietario può concedere permessi.")
    shared = bucket_record.get("shared_with", [])
    for entry in shared:
        if entry.get("username") == permission_req.target_username:
            if permission_req.permission not in entry.get("permissions", []):
                entry.setdefault("permissions", []).append(permission_req.permission)
            break
    else:
        shared.append({"username": permission_req.target_username, "permissions": [permission_req.permission]})
    bucket_record["shared_with"] = shared
    user_storage = current_user.get("storage", [])
    for i, b in enumerate(user_storage):
        if b.get("bucket_name") == bucket_name:
            user_storage[i] = bucket_record
            break
    update_user_storage(token, user_storage)
    return {
        "message": f"Permesso '{permission_req.permission}' concesso a {permission_req.target_username} per il bucket '{bucket_name}'."}


@router.post("/{bucket_name}/revoke_permission", summary="Revoca permessi su un bucket",
             response_description="Permesso revocato con successo")
async def revoke_permission(bucket_name: str, permission_req: PermissionRevokeRequest, token: str):
    """
    Revoca un permesso (read, write, admin) da un altro utente sul bucket.
    Solo il proprietario può revocare i permessi.
    """
    current_user = get_current_user(token)
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Bucket non trovato nei metadata dell'utente.")
    if bucket_record.get("owner") != current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo il proprietario può revocare i permessi.")
    shared = bucket_record.get("shared_with", [])
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
    bucket_record["shared_with"] = shared
    user_storage = current_user.get("storage", [])
    for i, b in enumerate(user_storage):
        if b.get("bucket_name") == bucket_name:
            user_storage[i] = bucket_record
            break
    update_user_storage(token, user_storage)
    return {
        "message": f"Permesso '{permission_req.permission}' revocato da {permission_req.target_username} per il bucket '{bucket_name}'."}


@router.get("/{bucket_name}/check_permission", summary="Verifica permesso su un bucket",
            response_description="Permesso verificato")
async def check_permission(bucket_name: str, required_permission: str, token: str):
    """
    Verifica se l'utente (con il token fornito) possiede il permesso specificato sul bucket.
    """
    current_user = get_current_user(token)
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Bucket non trovato nei metadata.")
    has_perm = check_bucket_permission(bucket_record, current_user.get("username"), required_permission)
    return {"bucket_name": bucket_name, "has_permission": has_perm, "required_permission": required_permission}
