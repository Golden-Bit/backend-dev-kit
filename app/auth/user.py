# user.py

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict
import boto3
import requests
from jose import jwt
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
# Modelli di input per le API (User)
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
    """
    Modello per la richiesta che include l'Access Token di un utente.

    Questo modello è utile quando occorre inviare l'Access Token
    nel body della richiesta (ad esempio, per verificare o recuperare
    informazioni sull'utente).

    Attributes:
        access_token (str): Il token di accesso rilasciato da Cognito.
    """
    access_token: str = Field(
        ...,
        description="Access token rilasciato da Cognito per l'utente."
    )


class ConfirmForgotPasswordRequest(BaseModel):
    """
    Modello per confermare il reset della password tramite codice di conferma.

    Questo modello viene utilizzato nel flusso di recupero password
    dopo che l'utente ha ricevuto il codice di conferma via email o SMS.

    Attributes:
        username (str): Nome utente per il quale confermare il reset della password.
        confirmation_code (str): Codice di conferma inviato da Cognito.
        new_password (str): Nuova password da impostare.
    """
    username: str = Field(
        ...,
        description="Nome utente per cui completare il reset della password."
    )
    confirmation_code: str = Field(
        ...,
        description="Codice di conferma ricevuto via email/SMS da Cognito."
    )
    new_password: str = Field(
        ...,
        description="Nuova password da impostare per l'utente."
    )


class RefreshTokenRequest(BaseModel):
    """
    Modello per rinnovare i token di accesso attraverso il Refresh Token.

    Questo modello viene utilizzato quando l'utente possiede ancora un Refresh Token
    valido e desidera ottenere un nuovo AccessToken e IdToken, ad esempio perché
    l'AccessToken è scaduto.

    Attributes:
        username (str): Nome utente associato al Refresh Token.
        refresh_token (str): Il Refresh Token rilasciato da Cognito.
    """
    username: str = Field(
        ...,
        description="Nome utente per cui effettuare il rinnovo dei token."
    )
    refresh_token: str = Field(
        ...,
        description="Refresh Token ottenuto durante il processo di autenticazione."
    )


class ForgotPasswordRequest(BaseModel):
    """
    Modello per la richiesta di reset password (forgot password).

    Attributes:
        username (str): Nome utente per il quale avviare il recupero password.
    """
    username: str = Field(..., description="Nome utente per il quale avviare il recupero password")


class ChangePasswordRequest(BaseModel):
    """
    Modello per il cambio password di un utente autenticato,
    senza dover passare dal flusso forgot password.

    Attributes:
        access_token (str): L'Access Token dell'utente ottenuto dal login.
        old_password (str): La vecchia password attualmente in uso.
        new_password (str): La nuova password da impostare.
    """
    access_token: str = Field(..., description="Access Token dell'utente autenticato")
    old_password: str = Field(..., description="Vecchia password attualmente in uso")
    new_password: str = Field(..., description="Nuova password da impostare")


from pydantic import BaseModel, Field

class VerifyAttributeRequest(BaseModel):
    """
    Modello per avviare la verifica di un attributo utente in Cognito
    (ad esempio, email o phone_number).

    Attributes:
        access_token (str): Il token di accesso dell'utente autenticato, ottenuto dopo il login.
        attribute_name (str): Il nome dell'attributo da verificare (es. "phone_number" o "email").
    """
    access_token: str = Field(..., description="Access token rilasciato da Cognito per l'utente.")
    attribute_name: str = Field(..., description="Nome dell'attributo, es. 'phone_number' o 'email'.")


class ConfirmAttributeRequest(BaseModel):
    """
    Modello per confermare il codice di verifica inviato da Cognito
    per l'attributo utente (email o phone_number).

    Attributes:
        access_token (str): Il token di accesso dell'utente autenticato.
        attribute_name (str): Nome dell'attributo (es. 'phone_number' o 'email').
        confirmation_code (str): Codice di conferma inviato da Cognito, ricevuto via email/SMS.
    """
    access_token: str = Field(..., description="Access token dell'utente.")
    attribute_name: str = Field(..., description="Nome dell'attributo, es. 'phone_number' o 'email'.")
    confirmation_code: str = Field(..., description="Codice di verifica ricevuto via SMS o email.")


# ---------------------------
# CREAZIONE ROUTER USER
# ---------------------------
user_router = APIRouter(
    prefix="/v1/user",
    tags=["User Operations"]
)

@user_router.post("/signup", summary="Registrazione utente", response_description="Risposta di registrazione da Cognito")
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


@user_router.post("/signin", summary="Autenticazione utente", response_description="Token e informazioni di autenticazione")
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


@user_router.post("/verify-token", summary="Verifica token JWT", response_description="Token decodificato")
async def verify_token(
    access_token_request: AccessTokenRequest = Body(..., description="Payload contenente l'access token dell'utente")
):
    """
    Verifica e decodifica un token JWT emesso da Cognito.

    Scarica il set di chiavi pubbliche (JWKS) e verifica il token utilizzando il CLIENT_ID e l'issuer.

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

        key = next((k for k in jwks if k["kid"] == kid), None)
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


@user_router.post("/confirm-signup-user", summary="Conferma registrazione utente", response_description="Risposta di conferma da Cognito")
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


@user_router.post("/resend-confirmation-code", summary="Invia nuovamente il codice di conferma", response_description="Risposta dall'invio del codice di conferma")
async def resend_confirmation_code(request_data: ResendConfirmationCodeRequest):
    """
    Invia nuovamente il codice di conferma all'utente.

    Utilizza l'operazione resend_confirmation_code di Cognito.
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


@user_router.post("/update-attributes", summary="Aggiorna attributi utente", response_description="Risposta dall'aggiornamento degli attributi")
async def update_attributes(request_data: UpdateAttributesRequest):
    """
    Aggiorna gli attributi associati a un account utente.

    L'utente deve fornire il proprio access token e la lista degli attributi da aggiornare.
    """
    try:
        response = cognito_client.update_user_attributes(
            AccessToken=request_data.access_token,
            UserAttributes=[attr.dict() for attr in request_data.attributes]
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_router.post("/update-custom-attributes", summary="Aggiorna attributi customizzati", response_description="Risposta dall'aggiornamento degli attributi customizzati")
async def update_custom_attributes(request_data: UpdateCustomAttributesRequest):
    """
    Aggiorna attributi customizzati per un utente.

    **Nota:** Assicurati che gli attributi custom siano già definiti nella User Pool e che il nome includa il prefisso 'custom:'.
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


@user_router.post("/user-info", summary="Visualizza informazioni utente", response_description="Informazioni complete dell'utente")
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


@user_router.post("/forgot-password", summary="Avvia il recupero password")
async def forgot_password(request_data: ForgotPasswordRequest):
    """
    Avvia il processo di reset password per un utente,
    inviando un codice di conferma via email/SMS.
    """
    try:
        response = cognito_client.forgot_password(
            ClientId=CLIENT_ID,
            Username=request_data.username,
            SecretHash=get_secret_hash(request_data.username)
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_router.post("/confirm-forgot-password", summary="Conferma il reset della password")
async def confirm_forgot_password(request_data: ConfirmForgotPasswordRequest):
    """
    Completa il processo di reset password,
    impostando la nuova password dopo l'inserimento del codice di conferma.
    """
    try:
        response = cognito_client.confirm_forgot_password(
            ClientId=CLIENT_ID,
            Username=request_data.username,
            ConfirmationCode=request_data.confirmation_code,
            Password=request_data.new_password,
            SecretHash=get_secret_hash(request_data.username)
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_router.post("/refresh-token", summary="Rinnova i token di accesso")
async def refresh_token(request_data: RefreshTokenRequest):
    """
    Esegue l'autenticazione con il flusso REFRESH_TOKEN_AUTH,
    restituendo nuovi Access/Id token.
    """
    try:
        response = cognito_client.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={
                "REFRESH_TOKEN": request_data.refresh_token,
                "SECRET_HASH": get_secret_hash(request_data.username)
            }
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_router.post("/change-password", summary="Cambia la password dell'utente autenticato")
async def change_password(request_data: ChangePasswordRequest):
    """
    Permette a un utente autenticato di cambiare la propria password,
    fornendo l'Access Token, la vecchia password e la nuova password.

    Se l'operazione ha successo, Cognito restituirà un messaggio di conferma.
    In caso di errore (es. vecchia password errata, token scaduto), verrà sollevata un'eccezione.
    """
    try:
        response = cognito_client.change_password(
            PreviousPassword=request_data.old_password,
            ProposedPassword=request_data.new_password,
            AccessToken=request_data.access_token
        )
        return {"message": "Password cambiata con successo.", "response": response}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_router.post("/verify-user-attribute")
def verify_user_attribute(request_data: VerifyAttributeRequest):
    """
    Invia un codice di verifica (email o phone_number) a un utente.

    Cognito utilizza l'endpoint get_user_attribute_verification_code per recapitare un codice
    all'utente (via SMS se phone_number, via email se email).

    Args:
        request_data (VerifyAttributeRequest): Contiene l'AccessToken e l'attributo da verificare.

    Returns:
        dict: Risposta di Cognito contenente le informazioni sull'invio del codice.
    """
    try:
        response = cognito_client.get_user_attribute_verification_code(
            AccessToken=request_data.access_token,
            AttributeName=request_data.attribute_name
        )
        return {
            "message": f"Codice di verifica inviato per l'attributo '{request_data.attribute_name}'",
            "response": response
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_router.post("/confirm-user-attribute")
def confirm_user_attribute(request_data: ConfirmAttributeRequest):
    """
    Conferma il codice di verifica per l'attributo utente (email o phone_number).

    Args:
        request_data (ConfirmAttributeRequest): Contiene l'AccessToken, l'attributo da confermare e il codice ricevuto.

    Returns:
        dict: Risposta di Cognito con l'esito della conferma.
    """
    try:
        response = cognito_client.verify_user_attribute(
            AccessToken=request_data.access_token,
            AttributeName=request_data.attribute_name,
            Code=request_data.confirmation_code
        )
        return {
            "message": f"Attributo '{request_data.attribute_name}' verificato con successo.",
            "response": response
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
