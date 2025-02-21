# admin.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import boto3
import hmac
import hashlib
import base64

from app.utilities import load_cognito_config

# ---------------------------
# Configurazioni per Cognito
# ---------------------------

# Carica la config
cognito_config = load_cognito_config("app/config.json")

REGION = cognito_config["REGION"]
CLIENT_ID = cognito_config["CLIENT_ID"]
CLIENT_SECRET = cognito_config["CLIENT_SECRET"]
USER_POOL_ID = cognito_config["USER_POOL_ID"]


# Crea il client boto3 per Cognito Identity Provider
cognito_client = boto3.client("cognito-idp", region_name=REGION)

def get_secret_hash(username: str) -> str:
    """
    Calcola il SecretHash richiesto da Cognito, che è la Base64-encoded HMAC-SHA256
    del messaggio (username + CLIENT_ID) firmato con il CLIENT_SECRET.

    Args:
        username (str): Nome utente per il quale calcolare il SecretHash.

    Returns:
        str: Il SecretHash.
    """
    message = username + CLIENT_ID
    digest = hmac.new(
        CLIENT_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()


# ---------------------------
# Modelli di input per le API (Admin)
# ---------------------------
class AdminConfirmSignUpRequest(BaseModel):
    """
    Modello per la conferma della registrazione tramite operazione amministrativa.

    Attributes:
        username (str): Nome utente da confermare (admin).
    """
    username: str = Field(..., description="Nome utente da confermare (admin)")


# ---------------------------
# CREAZIONE ROUTER ADMIN
# ---------------------------
admin_router = APIRouter(
    prefix="/v1/admin",
    tags=["Admin Operations"]
)

@admin_router.post("/confirm-signup", summary="Conferma registrazione utente (Admin)", response_description="Messaggio di conferma")
async def confirm_signup(request_data: AdminConfirmSignUpRequest):
    """
    Conferma la registrazione di un utente tramite operazione amministrativa (admin_confirm_sign_up).

    Args:
        request_data (AdminConfirmSignUpRequest): Contiene il nome utente da confermare.

    Returns:
        dict: Messaggio di conferma in caso di successo.
    """
    try:
        response = cognito_client.admin_confirm_sign_up(
            UserPoolId=USER_POOL_ID,
            Username=request_data.username
        )
        return {"message": f"User {request_data.username} confirmed successfully.", "response": response}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.get("/attribute-schema", summary="Visualizza schema degli attributi", response_description="Schema corrente degli attributi del pool")
async def get_attribute_schema():
    """
    Restituisce lo schema corrente degli attributi definiti nel User Pool.

    Lo schema comprende informazioni su ogni attributo (nome, tipo, se è custom, ecc.).
    """
    import boto3
    cognito_client_local = boto3.client("cognito-idp", region_name=REGION)

    try:
        response = cognito_client_local.describe_user_pool(UserPoolId=USER_POOL_ID)
        if "UserPool" in response and "SchemaAttributes" in response["UserPool"]:
            return response["UserPool"]["SchemaAttributes"]
        else:
            return {"message": "SchemaAttributes non disponibili per questo User Pool."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.post("/update-attribute-schema", summary="Modifica schema degli attributi", response_description="Risposta dall'aggiornamento dello schema")
async def update_attribute_schema():
    """
    Endpoint per aggiornare lo schema degli attributi.

    **ATTENZIONE:** Amazon Cognito **non permette** di modificare lo schema degli attributi
    (cioè la lista degli attributi) dopo la creazione del User Pool.
    Questo endpoint restituisce un errore 501 (Not Implemented).
    """
    raise HTTPException(
        status_code=501,
        detail="Modifica dello schema degli attributi non è supportata da Cognito dopo la creazione del pool."
    )
