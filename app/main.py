from fastapi import FastAPI, HTTPException, Header, Body
from pydantic import BaseModel, Field
from typing import List, Dict
import boto3
import requests
from jose import jwt
import hmac
import hashlib
import base64

app = FastAPI(
    title="Cognito Authentication API",
    description=(
        "API per la gestione degli utenti tramite Amazon Cognito. \n\n"
        "Questa API offre endpoint per la registrazione (signup), autenticazione (signin), "
        "verifica del token JWT, conferma della registrazione (sia lato utente che admin), "
        "invio di un nuovo codice di conferma e aggiornamento degli attributi utente."
    ),
    version="1.0.0"
)

# ---------------------------
# Configurazioni per Cognito
# ---------------------------
REGION = "eu-north-1"  # Regione della User Pool
CLIENT_ID = "..."
CLIENT_SECRET = "..."
USER_POOL_ID = "..."
JWKS_URL = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"

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
# Modelli di input per le API
# ---------------------------

class SignUpRequest(BaseModel):
    """
    Modello per la richiesta di registrazione utente.

    Attributes:
        username (str): Nome utente da registrare.
        password (str): Password dell'utente.
        email (str): Indirizzo email dell'utente.
    """
    username: str = Field(..., description="Nome utente per la registrazione")
    password: str = Field(..., description="Password per l'utente")
    email: str = Field(..., description="Indirizzo email dell'utente")

class SignInRequest(BaseModel):
    """
    Modello per la richiesta di autenticazione utente.

    Attributes:
        username (str): Nome utente.
        password (str): Password dell'utente.
    """
    username: str = Field(..., description="Nome utente per l'autenticazione")
    password: str = Field(..., description="Password dell'utente")

class ConfirmSignUpRequest(BaseModel):
    """
    Modello per la conferma della registrazione tramite codice inviato via email.

    Attributes:
        username (str): Nome utente da confermare.
        confirmation_code (str): Codice di conferma ricevuto via email.
    """
    username: str = Field(..., description="Nome utente da confermare")
    confirmation_code: str = Field(..., description="Codice di conferma ricevuto via email")

class AdminConfirmSignUpRequest(BaseModel):
    """
    Modello per la conferma della registrazione tramite operazione amministrativa.

    Attributes:
        username (str): Nome utente da confermare.
    """
    username: str = Field(..., description="Nome utente da confermare (admin)")

class ResendConfirmationCodeRequest(BaseModel):
    """
    Modello per la richiesta di invio di un nuovo codice di conferma.

    Attributes:
        username (str): Nome utente per cui inviare nuovamente il codice di conferma.
    """
    username: str = Field(..., description="Nome utente per cui inviare il nuovo codice di conferma")

class UserAttribute(BaseModel):
    """
    Modello per un singolo attributo utente.

    Attributes:
        Name (str): Nome dell'attributo (es. 'email', 'phone_number', etc.).
        Value (str): Valore dell'attributo.
    """
    Name: str = Field(..., description="Nome dell'attributo")
    Value: str = Field(..., description="Valore dell'attributo")

class UpdateAttributesRequest(BaseModel):
    """
    Modello per la richiesta di aggiornamento degli attributi utente.

    Attributes:
        access_token (str): Token di accesso dell'utente (ottenuto dopo il login).
        attributes (List[UserAttribute]): Lista degli attributi da aggiornare.
    """
    access_token: str = Field(..., description="Token di accesso dell'utente")
    attributes: List[UserAttribute] = Field(..., description="Lista degli attributi da aggiornare")


class UpdateCustomAttributesRequest(BaseModel):
    """
    Modello per aggiornare attributi customizzati.

    **Nota:** Le chiavi del dizionario devono includere il prefisso 'custom:'.
    """
    access_token: str = Field(..., description="Token di accesso dell'utente")
    custom_attributes: Dict[str, str] = Field(
        ...,
        description=(
            "Dizionario degli attributi customizzati da aggiornare, "
            "ad esempio: { 'custom:department': 'Marketing', 'custom:role': 'Manager' }"
        )
    )


class AccessTokenRequest(BaseModel):
    access_token: str = Field(..., description="Access token dell'utente")


# ---------------------------
# Endpoint API
# ---------------------------

@app.post("/signup", summary="Registrazione utente", response_description="Risposta di registrazione da Cognito")
async def signup(request_data: SignUpRequest):
    """
    Registra un nuovo utente in Amazon Cognito.

    Calcola il SecretHash necessario e invia username, password e email alla User Pool.

    Args:
        request_data (SignUpRequest): Dati di registrazione dell'utente.

    Returns:
        dict: Risposta di Cognito in caso di successo.
    """
    try:
        response = cognito_client.sign_up(
            ClientId=CLIENT_ID,
            Username=request_data.username,
            Password=request_data.password,
            SecretHash=get_secret_hash(request_data.username),
            UserAttributes=[
                {"Name": "email", "Value": request_data.email}
            ]
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/signin", summary="Autenticazione utente", response_description="Token e informazioni di autenticazione")
async def signin(request_data: SignInRequest):
    """
    Autentica un utente utilizzando il flusso USER_PASSWORD_AUTH di Cognito.

    Args:
        request_data (SignInRequest): Dati di autenticazione dell'utente.

    Returns:
        dict: Risposta di Cognito contenente i token di autenticazione.
    """
    try:
        response = cognito_client.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": request_data.username,
                "PASSWORD": request_data.password,
                "SECRET_HASH": get_secret_hash(request_data.username)
            }
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/verify-token", summary="Verifica token JWT", response_description="Token decodificato")
async def verify_token(
        access_token_request: AccessTokenRequest = Body(...,
                                                        description="Payload contenente l'access token dell'utente")
):
    """
    Verifica e decodifica un token JWT emesso da Cognito.

    Scarica il set di chiavi pubbliche (JWKS) e verifica il token utilizzando il CLIENT_ID e l'issuer.

    Args:
        authorization (str): Header di autorizzazione contenente il token.

    Returns:
        dict: Token decodificato in caso di verifica corretta.
    """
    token = access_token_request.access_token
    try:
        jwks = requests.get(JWKS_URL).json()["keys"]
        unverified_headers = jwt.get_unverified_headers(token)
        kid = unverified_headers.get("kid")
        if not kid:
            raise HTTPException(status_code=400, detail="kid non presente nell'header del token.")

        key = next((key for key in jwks if key["kid"] == kid), None)
        if key is None:
            raise HTTPException(status_code=400, detail="Chiave non trovata.")

        decoded_token = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
        )
        return decoded_token
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/confirm-signup", summary="Conferma registrazione utente (Admin)", response_description="Messaggio di conferma")
async def confirm_signup(request_data: AdminConfirmSignUpRequest):
    """
    Conferma la registrazione di un utente tramite operazione amministrativa.

    Questo endpoint utilizza l'operazione admin_confirm_sign_up di Cognito.

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

@app.post("/confirm-signup-user", summary="Conferma registrazione utente", response_description="Risposta di conferma da Cognito")
async def confirm_signup_user(request_data: ConfirmSignUpRequest):
    """
    Conferma la registrazione di un utente tramite codice di conferma.

    L'utente deve fornire il codice ricevuto via email per completare la registrazione.

    Args:
        request_data (ConfirmSignUpRequest): Dati necessari per la conferma.

    Returns:
        dict: Risposta di Cognito in caso di successo.
    """
    try:
        response = cognito_client.confirm_sign_up(
            ClientId=CLIENT_ID,
            Username=request_data.username,
            ConfirmationCode=request_data.confirmation_code,
            SecretHash=get_secret_hash(request_data.username)
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/resend-confirmation-code", summary="Invia nuovamente il codice di conferma", response_description="Risposta dall'invio del codice di conferma")
async def resend_confirmation_code(request_data: ResendConfirmationCodeRequest):
    """
    Invia nuovamente il codice di conferma all'utente.

    Utilizza l'operazione resend_confirmation_code di Cognito.

    Args:
        request_data (ResendConfirmationCodeRequest): Contiene il nome utente per cui inviare il codice.

    Returns:
        dict: Risposta di Cognito in caso di successo.
    """
    try:
        response = cognito_client.resend_confirmation_code(
            ClientId=CLIENT_ID,
            Username=request_data.username,
            SecretHash=get_secret_hash(request_data.username)
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/update-attributes", summary="Aggiorna attributi utente", response_description="Risposta dall'aggiornamento degli attributi")
async def update_attributes(request_data: UpdateAttributesRequest):
    """
    Aggiorna gli attributi associati a un account utente.

    L'utente deve fornire il proprio access token e la lista degli attributi da aggiornare.

    Args:
        request_data (UpdateAttributesRequest): Dati per l'aggiornamento (incluso l'access token e gli attributi).

    Returns:
        dict: Risposta di Cognito in caso di successo.
    """
    try:
        response = cognito_client.update_user_attributes(
            AccessToken=request_data.access_token,
            UserAttributes=[attr.dict() for attr in request_data.attributes]
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/update-custom-attributes", summary="Aggiorna attributi customizzati",
          response_description="Risposta dall'aggiornamento degli attributi customizzati")
async def update_custom_attributes(request_data: UpdateCustomAttributesRequest):
    """
    Aggiorna attributi customizzati per un utente.

    **Nota:** Assicurati che gli attributi custom siano già definiti nella User Pool e che il nome includa il prefisso 'custom:'.

    Esempio di payload:
    {
      "access_token": "<ACCESS_TOKEN>",
      "custom_attributes": {
          "custom:department": "Marketing",
          "custom:role": "Manager"
      }
    }
    """
    try:
        attributes = [{"Name": key, "Value": value} for key, value in request_data.custom_attributes.items()]
        response = cognito_client.update_user_attributes(
            AccessToken=request_data.access_token,
            UserAttributes=attributes
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/user-info", summary="Visualizza informazioni utente", response_description="Informazioni complete dell'utente")
async def get_user_info(
    access_token_request: AccessTokenRequest = Body(..., description="Payload contenente l'access token dell'utente")
):
    """
    Restituisce tutte le informazioni dell'utente (attributi standard e custom)
    utilizzando l'access token fornito nel body della richiesta.
    """
    try:
        response = cognito_client.get_user(AccessToken=access_token_request.access_token)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/attribute-schema", summary="Visualizza schema degli attributi",
         response_description="Schema corrente degli attributi del pool")
async def get_attribute_schema():
    """
    Restituisce lo schema corrente degli attributi definiti nel User Pool.

    Lo schema comprende informazioni su ogni attributo (nome, tipo, se è custom, ecc.).
    """
    try:
        response = cognito_client.describe_user_pool(UserPoolId=USER_POOL_ID)
        if "UserPool" in response and "SchemaAttributes" in response["UserPool"]:
            return response["UserPool"]["SchemaAttributes"]
        else:
            return {"message": "SchemaAttributes non disponibili per questo User Pool."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/update-attribute-schema", summary="Modifica schema degli attributi",
          response_description="Risposta dall'aggiornamento dello schema")
async def update_attribute_schema():
    """
    Endpoint per aggiornare lo schema degli attributi.

    **ATTENZIONE:** Amazon Cognito **non permette** di modificare lo schema degli attributi (cioè la lista degli attributi) dopo la creazione del User Pool.
    Eventuali modifiche allo schema non sono supportate e questo endpoint restituirà un messaggio appropriato.
    """
    raise HTTPException(
        status_code=501,
        detail="Modifica dello schema degli attributi non è supportata da Cognito dopo la creazione del pool."
    )


# ---------------------------
# Avvio dell'applicazione
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
