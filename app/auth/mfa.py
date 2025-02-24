from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import boto3
import hmac
import hashlib
import base64
import requests

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

cognito_client = boto3.client("cognito-idp", region_name=REGION)

def get_secret_hash(username: str) -> str:
    """
    Calcola il SecretHash richiesto da Cognito, che è la Base64-encoded HMAC-SHA256
    del messaggio (username + CLIENT_ID) firmato con il CLIENT_SECRET.
    """
    message = username + CLIENT_ID
    digest = hmac.new(
        CLIENT_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()

# ----------------------------------------------------------------------------------
# Modelli Pydantic dedicati al MFA Router
# ----------------------------------------------------------------------------------
class EnableSmsMfaRequest(BaseModel):
    """
    Modello per abilitare la MFA via SMS.

    Attributes:
        access_token (str): Token di accesso dell'utente autenticato.
        phone_number (str): Numero di telefono già verificato (in formato E.164, es. +391234567890).
    """
    access_token: str = Field(..., description="Access Token dell'utente autenticato")
    phone_number: str = Field(..., description="Numero di telefono verificato in formato E.164")


class DisableMfaRequest(BaseModel):
    """
    Modello per disabilitare la MFA (sia SMS che TOTP).

    Attributes:
        access_token (str): Token di accesso dell'utente autenticato.
    """
    access_token: str = Field(..., description="Access Token dell'utente")


class AssociateSoftwareTokenRequest(BaseModel):
    """
    Modello per associare un nuovo software token (TOTP) all'utente.

    Attributes:
        access_token (str): Token di accesso dell'utente autenticato.
    """
    access_token: str = Field(..., description="Access Token dell'utente autenticato")


class VerifySoftwareTokenRequest(BaseModel):
    """
    Modello per verificare il codice TOTP generato dall'app authenticator.

    Attributes:
        access_token (str): Token di accesso dell'utente autenticato.
        friendly_device_name (str): Nome del dispositivo, facoltativo.
        code (str): Codice TOTP (ad es. 123456).
    """
    access_token: str = Field(..., description="Access Token dell'utente")
    friendly_device_name: str = Field("", description="Nome del dispositivo (opzionale)")
    code: str = Field(..., description="Codice TOTP generato dall'app (6 cifre, es. 123456)")


class AccessTokenOnlyRequest(BaseModel):
    """
    Modello semplice per le richieste che necessitano solo dell'Access Token.
    """
    access_token: str = Field(..., description="Access Token dell'utente autenticato")


class MfaRespondChallengeRequest(BaseModel):
    """
    Modello per rispondere a un challenge MFA (SMS o TOTP) durante il login.
    """
    session: str = Field(..., description="Session restituita da Cognito dopo initiate_auth")
    challenge_name: str = Field(..., description="Nome del challenge es. 'SMS_MFA' o 'SOFTWARE_TOKEN_MFA'")
    username: str = Field(..., description="Nome utente")
    code: str = Field(..., description="Codice OTP inviato via SMS o generato dall'app TOTP")

# ----------------------------------------------------------------------------------
# Creazione del router per MFA
# ----------------------------------------------------------------------------------
mfa_router = APIRouter(
    prefix="/v1/user/mfa",
    tags=["User MFA"]
)


@mfa_router.post("/respond-challenge", summary="Completa il login MFA rispondendo al challenge")
async def respond_to_mfa_challenge(request_data: MfaRespondChallengeRequest):
    """
    Completa l'autenticazione MFA inviando a Cognito il codice OTP e la Session
    ottenuta dalla chiamata 'initiate_auth' con ChallengeName = 'SMS_MFA' o 'SOFTWARE_TOKEN_MFA'.
    """
    try:
        response = cognito_client.respond_to_auth_challenge(
            ClientId=CLIENT_ID,
            ChallengeName=request_data.challenge_name,
            Session=request_data.session,
            ChallengeResponses={
                "USERNAME": request_data.username,
                "SMS_MFA_CODE": request_data.code  # o "SOFTWARE_TOKEN_MFA_CODE" se TOTP
            }
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@mfa_router.post("/enable-sms-mfa", summary="Abilita SMS MFA per l'utente autenticato")
async def enable_sms_mfa(request_data: EnableSmsMfaRequest):
    """
    Abilita la MFA via SMS per l'utente.

    Cognito richiede che l'utente abbia un numero di telefono verificato.
    """
    # Eventualmente, verifica la formattazione o la presenza di phone_number_verified
    # Cognito si aspetta che phone_number_verified sia True.
    # Se non lo è, potrebbe sollevare un errore.

    try:
        # Imposta SMS come metodo preferito
        response = cognito_client.set_user_mfa_preference(
            SMSMfaSettings={
                "Enabled": True,
                "PreferredMfa": True
            },
            AccessToken=request_data.access_token
        )
        return {"message": "SMS MFA abilitata.", "response": response}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@mfa_router.post("/disable-sms-mfa", summary="Disabilita SMS MFA per l'utente autenticato")
async def disable_sms_mfa(request_data: DisableMfaRequest):
    """
    Disabilita la MFA via SMS per l'utente.
    """
    try:
        response = cognito_client.set_user_mfa_preference(
            SMSMfaSettings={
                "Enabled": False,
                "PreferredMfa": False
            },
            AccessToken=request_data.access_token
        )
        return {"message": "SMS MFA disabilitata.", "response": response}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@mfa_router.post("/associate-software-token", summary="Avvia la procedura di associazione TOTP")
async def associate_software_token(request_data: AssociateSoftwareTokenRequest):
    """
    Avvia la procedura di associazione di un token software (TOTP).
    Cognito restituisce un SecretCode (Base32) che l'utente dovrà inserire in un'app TOTP
    (es. Google Authenticator).
    """
    try:
        response = cognito_client.associate_software_token(
            AccessToken=request_data.access_token
        )
        return {
            "message": "Assegnato SecretCode. Prosegui con verify-software-token.",
            "SecretCode": response.get("SecretCode"),
            "Session": response.get("Session")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@mfa_router.post("/verify-software-token", summary="Verifica il codice TOTP per completare l'associazione")
async def verify_software_token(request_data: VerifySoftwareTokenRequest):
    """
    Verifica che il codice TOTP generato dall'utente corrisponda al SecretCode fornito da Cognito.
    """
    try:
        response = cognito_client.verify_software_token(
            AccessToken=request_data.access_token,
            FriendlyDeviceName=request_data.friendly_device_name,
            UserCode=request_data.code
        )
        return {
            "message": "Software token verificato correttamente.",
            "Status": response.get("Status")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@mfa_router.post("/enable-software-mfa", summary="Abilita TOTP MFA come metodo principale")
async def enable_software_mfa(request_data: AccessTokenOnlyRequest):
    """
    Abilita la MFA TOTP (software) per l'utente,
    impostandola come PreferredMfa. Presuppone che l'utente abbia già
    associato e verificato il token.
    """
    try:
        response = cognito_client.set_user_mfa_preference(
            SoftwareTokenMfaSettings={
                "Enabled": True,
                "PreferredMfa": True
            },
            AccessToken=request_data.access_token
        )
        return {"message": "TOTP MFA (software) abilitata come metodo preferito.", "response": response}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@mfa_router.post("/disable-software-mfa", summary="Disabilita TOTP MFA (software)")
async def disable_software_mfa(request_data: AccessTokenOnlyRequest):
    """
    Disabilita la MFA TOTP per l'utente.
    """
    try:
        response = cognito_client.set_user_mfa_preference(
            SoftwareTokenMfaSettings={
                "Enabled": False,
                "PreferredMfa": False
            },
            AccessToken=request_data.access_token
        )
        return {"message": "TOTP MFA disabilitata.", "response": response}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

