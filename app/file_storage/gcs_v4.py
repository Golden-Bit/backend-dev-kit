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
    permission_type: Optional[str] = "global"  # "global" oppure "custom"

# Modello per la gestione dei permessi (sia a livello di bucket che di directory)
class PermissionGrantRequest(BaseModel):
    target_username: str
    permission: str  # "read", "write" o "admin"

class PermissionRevokeRequest(BaseModel):
    target_username: str
    permission: str  # "read", "write" o "admin"

# Modello per la creazione di file (upload) con metadati opzionali
class FileUploadRequest(BaseModel):
    folder_path: Optional[str] = None  # Può includere directory e sottodirectory, es. "folder/subfolder"
    custom_metadata: Optional[Dict[str, str]] = None  # Metadati personalizzati da associare al file

# Modello per aggiornare i metadati associati ad un file
class FileMetadataUpdateRequest(BaseModel):
    custom_metadata: Dict[str, str]

# Modello per la ricerca avanzata dei file
class FileSearchRequest(BaseModel):
    prefix: Optional[str] = None  # Per simulare directory
    metadata_filters: Optional[Dict[str, str]] = None  # Filtro sui metadati
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
    Verifica se l'utente ha il permesso richiesto a livello di bucket.
    Il proprietario ha sempre tutti i permessi.
    """
    if bucket_record.get("owner") == current_username:
        return True
    for entry in bucket_record.get("shared_with", []):
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

# Funzioni per la gestione dei permessi a livello di directory

def find_directory_record(bucket_record: Dict[str, Any], directory_path: str) -> Optional[Dict[str, Any]]:
    """
    Cerca il record della directory (o sottodirectory) all'interno del bucket.
    """
    for directory in bucket_record.get("directories", []):
        if directory.get("directory_path") == directory_path:
            return directory
    return None

def check_directory_permission(directory_record: Dict[str, Any], current_username: str, required_permission: str) -> bool:
    """
    Verifica se l'utente ha il permesso richiesto a livello di directory.
    Il proprietario ha sempre tutti i permessi.
    """
    if directory_record.get("owner") == current_username:
        return True
    for entry in directory_record.get("shared_with", []):
        if entry.get("username") == current_username and required_permission in entry.get("permissions", []):
            return True
    return False

def verify_user_directory(bucket_name: str, directory_path: str, user: Dict[str, Any], required_permission: str = "read"):
    """
    Verifica che la directory esista nei metadata del bucket dell'utente e che l'utente abbia il permesso richiesto.
    """
    bucket_record = find_bucket_record(bucket_name, user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Bucket non trovato nei metadata dell'utente.")
    # Se il bucket ha permessi globali, questi prevalgono
    if bucket_record.get("permission_type", "global") == "global":
        if not check_bucket_permission(bucket_record, user.get("username"), required_permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Non sei autorizzato a eseguire operazioni con permesso '{required_permission}' sul bucket.")
    else:
        # Per bucket custom, controlla il permesso specifico della directory
        directory_record = find_directory_record(bucket_record, directory_path)
        if not directory_record or not check_directory_permission(directory_record, user.get("username"), required_permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Non sei autorizzato ad eseguire operazioni con permesso '{required_permission}' sulla directory '{directory_path}'.")

# --------------------------- Endpoints per la gestione dei bucket ---------------------------

@router.post("/create_bucket/", summary="Crea un nuovo bucket in GCS",
             response_description="Bucket creato con successo")
async def create_bucket(request: BucketCreationRequest, token: str):
    """
    Crea un nuovo bucket in Google Cloud Storage. Il nome del bucket viene prefissato con il nome utente.
    I metadata del bucket includono:
      - bucket_name, owner (username), shared_with (lista vuota)
      - permission_type: "global" o "custom"
      - directories: lista vuota (inizialmente)
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
            "permission_type": request.permission_type,
            "shared_with": [],
            "directories": []  # Nessuna directory inizialmente
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
    storage_metadata = [b for b in current_user.get("storage", []) if b.get("bucket_name") != bucket_name]
    update_user_storage(token, storage_metadata)
    return {"message": f"Bucket '{bucket_name}' eliminato con successo e rimosso dai metadata dell'utente."}

# --------------------------- Endpoints per la gestione delle directory ---------------------------

@router.post("/{bucket_name}/create_directory/", summary="Crea una nuova directory",
             response_description="Directory creata con successo")
async def create_directory(bucket_name: str, directory_path: str = Body(..., embed=True), token: str = ""):
    """
    Crea una nuova directory (o sottodirectory) all'interno di un bucket.
    Questa operazione aggiorna solo i metadata dell'utente, senza operazioni fisiche su GCS.
    Richiede:
      - Se il bucket ha permessi globali, viene verificato a livello di bucket.
      - Se il bucket è custom, non sono previsti permessi globali e la directory verrà gestita individualmente.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    storage_metadata = current_user.get("storage", [])
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bucket non trovato nei metadata.")
    directories = bucket_record.get("directories", [])
    if any(d.get("directory_path") == directory_path for d in directories):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory già esistente.")
    new_directory = {
        "directory_path": directory_path,
        "owner": current_user.get("username"),
        "shared_with": []
    }
    directories.append(new_directory)
    bucket_record["directories"] = directories
    # Aggiorna il record del bucket nei metadata dell'utente
    user_storage = current_user.get("storage", [])
    for i, b in enumerate(user_storage):
        if b.get("bucket_name") == bucket_name:
            user_storage[i] = bucket_record
            break
    update_user_storage(token, user_storage)
    return {"message": f"Directory '{directory_path}' creata con successo in bucket '{bucket_name}'."}

@router.get("/{bucket_name}/list_directories/", summary="Elenca le directory in un bucket",
            response_description="Elenco delle directory")
async def list_directories(bucket_name: str, token: str):
    """
    Recupera l'elenco delle directory (sottodirectory) di un bucket dai metadata dell'utente.
    """
    current_user = get_current_user(token)
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bucket non trovato nei metadata.")
    return {"directories": bucket_record.get("directories", [])}

@router.delete("/{bucket_name}/delete_directory/", summary="Elimina una directory",
               response_description="Directory eliminata con successo")
async def delete_directory(bucket_name: str, directory_path: str = Body(..., embed=True), token: str = ""):
    """
    Elimina una directory dai metadata dell'utente.
    Nota: Questa operazione non elimina fisicamente i file in GCS, ma rimuove solo il record di metadata.
    Richiede il permesso "write" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bucket non trovato nei metadata.")
    directories = bucket_record.get("directories", [])
    new_directories = [d for d in directories if d.get("directory_path") != directory_path]
    if len(new_directories) == len(directories):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directory non trovata.")
    bucket_record["directories"] = new_directories
    user_storage = current_user.get("storage", [])
    for i, b in enumerate(user_storage):
        if b.get("bucket_name") == bucket_name:
            user_storage[i] = bucket_record
            break
    update_user_storage(token, user_storage)
    return {"message": f"Directory '{directory_path}' eliminata con successo da bucket '{bucket_name}'."}

# --------------------------- Endpoints per la gestione dei file ---------------------------

@router.post("/{bucket_name}/upload_file/", summary="Carica un file in un bucket",
             response_description="File caricato con successo")
async def upload_file(bucket_name: str, file: UploadFile = File(...), file_info: FileUploadRequest = Body(...),
                      token: str = ""):
    """
    Carica un file in un bucket.
    Se viene fornito un 'folder_path', il file verrà caricato con nome "folder_path/filename".
    È possibile associare metadati personalizzati al file.
    Richiede il permesso "write" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="write")
    try:
        bucket = gcs_client.bucket(bucket_name)
        # Costruisce il nome del file, includendo il folder_path se presente
        destination_name = f"{file_info.folder_path.rstrip('/')}/{file.filename}" if file_info.folder_path else file.filename
        blob = bucket.blob(destination_name)
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
    È possibile filtrare per 'prefix' per simulare directory e applicare filtri sui metadati.
    Supporta paginazione tramite 'skip' e 'limit'.
    Richiede il permesso "read" sul bucket.
    """
    current_user = get_current_user(token)
    verify_user_bucket(bucket_name, current_user, required_permission="read")
    try:
        bucket = gcs_client.bucket(bucket_name)
        prefix = search.prefix if search and search.prefix else ""
        blobs = list(bucket.list_blobs(prefix=prefix))
        results = []
        for blob in blobs:
            include_blob = True
            if search and search.metadata_filters:
                blob_metadata = blob.metadata or {}
                for key, value in search.metadata_filters.items():
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
        skip = search.skip if search and search.skip else 0
        limit = search.limit if search and search.limit else 10
        return {"files": results[skip:skip + limit], "total": len(results)}
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
        current_metadata = blob.metadata or {}
        current_metadata.update(metadata_update.custom_metadata)
        blob.metadata = current_metadata
        blob.patch()
        return {"message": f"Metadati del file '{file_name}' aggiornati con successo.", "metadata": current_metadata}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Errore nell'aggiornamento dei metadati del file: " + str(e))

# --------------------------- Endpoints per la gestione dei permessi sui bucket ---------------------------

@router.post("/{bucket_name}/grant_permission", summary="Concedi permessi su un bucket",
             response_description="Permesso concesso con successo")
async def grant_bucket_permission(bucket_name: str, permission_req: PermissionGrantRequest, token: str):
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
    return {"message": f"Permesso '{permission_req.permission}' concesso a {permission_req.target_username} sul bucket '{bucket_name}'."}

@router.post("/{bucket_name}/revoke_permission", summary="Revoca permessi su un bucket",
             response_description="Permesso revocato con successo")
async def revoke_bucket_permission(bucket_name: str, permission_req: PermissionRevokeRequest, token: str):
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
    return {"message": f"Permesso '{permission_req.permission}' revocato da {permission_req.target_username} sul bucket '{bucket_name}'."}

@router.get("/{bucket_name}/check_permission", summary="Verifica permesso sul bucket",
            response_description="Permesso verificato")
async def check_bucket_permission_endpoint(bucket_name: str, required_permission: str, token: str):
    """
    Verifica se l'utente possiede il permesso specificato sul bucket.
    """
    current_user = get_current_user(token)
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Bucket non trovato nei metadata.")
    has_perm = check_bucket_permission(bucket_record, current_user.get("username"), required_permission)
    return {"bucket_name": bucket_name, "has_permission": has_perm, "required_permission": required_permission}

# --------------------------- Endpoints per la gestione dei permessi sulle directory ---------------------------

@router.post("/{bucket_name}/grant_directory_permission", summary="Concedi permessi su una directory",
             response_description="Permesso concesso con successo")
async def grant_directory_permission(bucket_name: str, directory_path: str = Body(..., embed=True),
                                     permission_req: PermissionGrantRequest = Body(...),
                                     token: str = ""):
    """
    Concede un permesso (read, write, admin) a un altro utente su una specifica directory all'interno di un bucket.
    Solo il proprietario della directory può concedere permessi.
    """
    current_user = get_current_user(token)
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bucket non trovato nei metadata.")
    # Verifica che il bucket sia in modalità "custom" per gestire permessi specifici sulle directory
    if bucket_record.get("permission_type", "global") != "custom":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Il bucket non supporta permessi custom sulle directory.")
    directory_record = find_directory_record(bucket_record, directory_path)
    if not directory_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directory non trovata nei metadata.")
    if directory_record.get("owner") != current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo il proprietario della directory può concedere permessi.")
    shared = directory_record.get("shared_with", [])
    for entry in shared:
        if entry.get("username") == permission_req.target_username:
            if permission_req.permission not in entry.get("permissions", []):
                entry.setdefault("permissions", []).append(permission_req.permission)
            break
    else:
        shared.append({"username": permission_req.target_username, "permissions": [permission_req.permission]})
    directory_record["shared_with"] = shared
    # Aggiorna il record della directory nel bucket
    directories = bucket_record.get("directories", [])
    for i, d in enumerate(directories):
        if d.get("directory_path") == directory_path:
            directories[i] = directory_record
            break
    bucket_record["directories"] = directories
    user_storage = current_user.get("storage", [])
    for i, b in enumerate(user_storage):
        if b.get("bucket_name") == bucket_name:
            user_storage[i] = bucket_record
            break
    update_user_storage(token, user_storage)
    return {"message": f"Permesso '{permission_req.permission}' concesso a {permission_req.target_username} sulla directory '{directory_path}' nel bucket '{bucket_name}'."}

@router.post("/{bucket_name}/revoke_directory_permission", summary="Revoca permessi su una directory",
             response_description="Permesso revocato con successo")
async def revoke_directory_permission(bucket_name: str, directory_path: str = Body(..., embed=True),
                                      permission_req: PermissionRevokeRequest = Body(...),
                                      token: str = ""):
    """
    Revoca un permesso (read, write, admin) da un altro utente su una specifica directory.
    Solo il proprietario della directory può revocare i permessi.
    """
    current_user = get_current_user(token)
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bucket non trovato nei metadata.")
    if bucket_record.get("permission_type", "global") != "custom":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Il bucket non supporta permessi custom sulle directory.")
    directory_record = find_directory_record(bucket_record, directory_path)
    if not directory_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directory non trovata nei metadata.")
    if directory_record.get("owner") != current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo il proprietario della directory può revocare i permessi.")
    shared = directory_record.get("shared_with", [])
    for entry in shared:
        if entry.get("username") == permission_req.target_username:
            if permission_req.permission in entry.get("permissions", []):
                entry["permissions"].remove(permission_req.permission)
            if not entry["permissions"]:
                shared.remove(entry)
            break
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Utente target non trovato nei permessi condivisi della directory.")
    directory_record["shared_with"] = shared
    directories = bucket_record.get("directories", [])
    for i, d in enumerate(directories):
        if d.get("directory_path") == directory_path:
            directories[i] = directory_record
            break
    bucket_record["directories"] = directories
    user_storage = current_user.get("storage", [])
    for i, b in enumerate(user_storage):
        if b.get("bucket_name") == bucket_name:
            user_storage[i] = bucket_record
            break
    update_user_storage(token, user_storage)
    return {"message": f"Permesso '{permission_req.permission}' revocato da {permission_req.target_username} sulla directory '{directory_path}' nel bucket '{bucket_name}'."}

@router.get("/{bucket_name}/check_directory_permission", summary="Verifica permesso su una directory",
            response_description="Permesso verificato")
async def check_directory_permission_endpoint(bucket_name: str, directory_path: str, required_permission: str, token: str):
    """
    Verifica se l'utente possiede il permesso specificato sulla directory.
    """
    current_user = get_current_user(token)
    bucket_record = find_bucket_record(bucket_name, current_user)
    if not bucket_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bucket non trovato nei metadata.")
    directory_record = find_directory_record(bucket_record, directory_path)
    if not directory_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directory non trovata nei metadata.")
    has_perm = check_directory_permission(directory_record, current_user.get("username"), required_permission)
    return {"bucket_name": bucket_name, "directory_path": directory_path, "has_permission": has_perm, "required_permission": required_permission}
