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
AUTH_SERVICE_URL = "http://localhost:8000/v1/user"  # Endpoint della nuova API di autenticazione

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
    permission: str  # "read", "write" o "admin"


class PermissionRevokeRequest(BaseModel):
    target_username: str
    permission: str  # "read", "write" o "admin"


# Modello per la creazione di file (upload) con metadati opzionali
class FileUploadRequest(BaseModel):
    folder_path: Optional[str] = None  # Es. "cartella1/sottocartella2"
    custom_metadata: Optional[Dict[str, str]] = None  # Metadati personalizzati


# Modello per aggiornare i metadati associati ad un file
class FileMetadataUpdateRequest(BaseModel):
    custom_metadata: Dict[str, str]


# Modello per la ricerca avanzata dei file
class FileSearchRequest(BaseModel):
    prefix: Optional[str] = None  # Per simulare directory
    metadata_filters: Optional[Dict[str, str]] = None  # Filtro sui metadati (chiave: valore)
    skip: Optional[int] = 0
    limit: Optional[int] = 10


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
    Verifica che il bucket esista nei metadata dell'utente e che l'utente abbia il permesso richiesto.
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

@router.post("/create_bucket/", summary="Crea un nuovo bucket in GCS",
             response_description="Bucket creato con successo")
async def create_bucket(request: BucketCreationRequest, token: str):
    """
    Crea un nuovo bucket in Google Cloud Storage. Il nome del bucket viene prefissato con il nome utente.
    I metadata del bucket includono: bucket_name, owner (username) e shared_with (lista vuota).
    I metadata vengono salvati nell'attributo custom:storage dell'utente.
    """
    current_user = get_current_user(token)
    username = current_user.get("username")
    prefixed_bucket_name = f"{username}-{request.bucket_name}"

    try:
        bucket = gcs_client.create_bucket(prefixed_bucket_name)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Errore nella creazione del bucket: " + str(e))

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
    Recupera l'elenco dei bucket (metadata) associati all'utente.
    """
    current_user = get_current_user(token)
    return {"buckets": current_user.get("storage", [])}


@router.delete("/delete_bucket/{bucket_name}/", summary="Elimina un bucket",
               response_description="Bucket eliminato con successo")
async def delete_bucket(bucket_name: str, token: str):
    """
    Elimina un bucket da GCS e rimuove il suo riferimento dai metadata dell'utente.
    Richiede il permesso "write" (tipicamente solo il proprietario).
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    try:
        bucket = gcs_client.bucket(bucket_name)
        bucket.delete(force=True)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Errore durante l'eliminazione del bucket: " + str(e))
    storage_metadata = [b for b in current_user.get("storage", []) if b.get("bucket_name") != bucket_name]
    update_user_storage(token, storage_metadata)
    return {"message": f"Bucket '{bucket_name}' eliminato con successo e rimosso dai metadata dell'utente."}


# --------------------------- Endpoints per la gestione dei file ---------------------------

@router.post("/{bucket_name}/upload_file/", summary="Carica un file in un bucket",
             response_description="File caricato con successo")
async def upload_file(bucket_name: str, file: UploadFile = File(...), file_info: FileUploadRequest = Body(...),
                      token: str = ""):
    """
    Carica un file in un bucket specifico.
    - Se viene fornito un 'folder_path', il file verrà caricato con nome "folder_path/filename".
    - È possibile associare metadati personalizzati al file.
    Richiede il permesso "write" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    try:
        bucket = gcs_client.bucket(bucket_name)
        # Costruisce il nome del file includendo il folder_path se presente
        destination_name = f"{file_info.folder_path.rstrip('/')}/{file.filename}" if file_info.folder_path else file.filename
        blob = bucket.blob(destination_name)
        # Se sono stati forniti metadati personalizzati, impostali sul blob
        if file_info.custom_metadata:
            blob.metadata = file_info.custom_metadata
        blob.upload_from_file(file.file)
        return {"message": f"File '{destination_name}' caricato con successo in bucket '{bucket_name}'."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nel caricamento del file: " + str(e))


@router.get("/{bucket_name}/list_files/", summary="Elenca i file in un bucket",
            response_description="Elenco dei file")
async def list_files(bucket_name: str, search: Optional[FileSearchRequest] = Body(None), token: str = ""):
    """
    Recupera l'elenco dei file in un bucket.
    È possibile filtrare per 'prefix' (per simulare directory) e per metadati personalizzati.
    Richiede il permesso "read" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="read")
    try:
        bucket = gcs_client.bucket(bucket_name)
        # Se è specificato un prefix (o directory) lo usiamo per listare i blob
        prefix = search.prefix if search and search.prefix else ""
        blobs = list(bucket.list_blobs(prefix=prefix))
        files = []
        # Applica filtri avanzati sui metadati se specificati
        for blob in blobs:
            include_blob = True
            if search and search.metadata_filters:
                blob_metadata = blob.metadata or {}
                for key, value in search.metadata_filters.items():
                    if blob_metadata.get(key) != value:
                        include_blob = False
                        break
            if include_blob:
                files.append({
                    "name": blob.name,
                    "size": blob.size,
                    "updated": blob.updated.isoformat(),
                    "metadata": blob.metadata
                })
        # Applica skip e limit
        skip = search.skip if search and search.skip else 0
        limit = search.limit if search and search.limit else 10
        return {"files": files[skip:skip + limit], "total": len(files)}
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


@router.put("/{bucket_name}/update_file_metadata/", summary="Aggiorna i metadati di un file",
            response_description="Metadati del file aggiornati con successo")
async def update_file_metadata(bucket_name: str, file_name: str, metadata_update: FileMetadataUpdateRequest,
                               token: str = ""):
    """
    Aggiorna i metadati personalizzati associati ad un file in un bucket.
    Richiede il permesso "write" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    try:
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        # Aggiorna i metadati esistenti con quelli nuovi
        current_metadata = blob.metadata or {}
        current_metadata.update(metadata_update.custom_metadata)
        blob.metadata = current_metadata
        # Esegui un patch per salvare i nuovi metadati
        blob.patch()
        return {"message": f"Metadati del file '{file_name}' aggiornati con successo.", "metadata": current_metadata}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'aggiornamento dei metadati del file: " + str(e))


# --------------------------- Endpoints per la gestione dei permessi ---------------------------

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


# --------------------------- Endpoints per la ricerca avanzata dei file ---------------------------

@router.post("/search_files", summary="Ricerca avanzata dei file",
             response_description="Risultati della ricerca dei file")
async def search_files(search_req: FileSearchRequest, bucket_name: str, token: str):
    """
    Esegue una ricerca avanzata nei file di un bucket, utilizzando:
      - 'prefix': per filtrare per directory/sottocartelle;
      - 'metadata_filters': per filtrare in base a metadati personalizzati.
    Supporta paginazione tramite 'skip' e 'limit'.
    Richiede il permesso "read" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="read")
    try:
        bucket = gcs_client.bucket(bucket_name)
        prefix = search_req.prefix if search_req.prefix else ""
        blobs = list(bucket.list_blobs(prefix=prefix))
        results = []
        for blob in blobs:
            include_blob = True
            if search_req.metadata_filters:
                blob_metadata = blob.metadata or {}
                for key, value in search_req.metadata_filters.items():
                    if blob_metadata.get(key) != value:
                        include_blob = False
                        break
            if include_blob:
                results.append({
                    "name": blob.name,
                    "size": blob.size,
                    "updated": blob.updated.isoformat(),
                    "metadata": blob.metadata
                })
        skip = search_req.skip if search_req.skip else 0
        limit = search_req.limit if search_req.limit else 10
        return {"files": results[skip:skip + limit], "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nella ricerca avanzata dei file: " + str(e))
