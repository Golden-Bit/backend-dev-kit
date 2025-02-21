# social.py

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
import boto3
import hmac
import hashlib
import base64
import urllib.parse

from app.utilities import load_cognito_config  # Carica la config dal file config.py

# Carichiamo la config da config.json
cognito_config = load_cognito_config("app/config.json")
REGION = cognito_config["REGION"]
CLIENT_ID = cognito_config["CLIENT_ID"]
CLIENT_SECRET = cognito_config["CLIENT_SECRET"]
USER_POOL_ID = cognito_config["USER_POOL_ID"]

# Cognito domain (assicurati di configurare un dominio nella user pool, es. "myapp.auth.eu-north-1.amazoncognito.com")
COGNITO_DOMAIN = "myapp.auth.eu-north-1.amazoncognito.com"  # Esempio, da modificare

social_router = APIRouter(
    prefix="/v1/user/social",
    tags=["User Social Login"]
)


class SocialLoginRequest(BaseModel):
    """
    Modello per specificare il provider di social login (es. 'Google', 'Facebook', ecc.).
    """
    provider: str = Field(..., description="Nome del provider (Google, Facebook, Apple, Amazon, etc.)")


@social_router.get("/login", summary="Avvia login con provider terzo (Hosted UI)")
async def social_login(provider: str):
    """
    Esempio di endpoint per reindirizzare l'utente al Hosted UI di Cognito,
    selezionando un provider di federazione (Google, Facebook, etc.).

    Flow: L'utente viene redirectato a Cognito Hosted UI -> login provider -> callback su /callback
    """
    # Esempio: costruiamo l'URL di Hosted UI con querystring
    # Parametri principali: client_id, redirect_uri, response_type=code, identity_provider=...
    # ASSUMIAMO di avere redirect_uri configurata in Cognito come "http://localhost:8000/v1/user/social/callback"

    redirect_uri = "http://localhost:8000/v1/user/social/callback"
    base_auth_url = f"https://{COGNITO_DOMAIN}/oauth2/authorize"

    # identity_provider deve corrispondere al nome del provider configurato in Cognito (es. "Facebook", "Google")
    query_params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "email openid profile",  # Aggiungi scope necessari
        "redirect_uri": redirect_uri,
        "identity_provider": provider  # deve combaciare con la config in Cognito
    }

    url_with_params = base_auth_url + "?" + urllib.parse.urlencode(query_params)
    return RedirectResponse(url_with_params)


@social_router.get("/callback", summary="Callback dopo login con provider terzo")
async def social_callback(code: str, state: str = None):
    """
    Endpoint di callback che Cognito invoca dopo che l'utente ha effettuato
    l'accesso con un provider esterno (Google, Facebook, ecc.) via Hosted UI.

    Il param 'code' è usato per scambiare il token con Cognito.
    """
    # Esempio di come scambiare il code con i token
    token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"
    redirect_uri = "http://localhost:8000/v1/user/social/callback"

    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": redirect_uri
    }
    # Se hai il secret, potresti dover inviare Authorization Basic, oppure form param "client_secret" ...
    # Qui assumiamo che l'App Client non generi segreto. Se lo generasse, occorrerebbe l'header Basic o param client_secret.
    data["client_secret"] = CLIENT_SECRET  # se necessario

    import requests
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = requests.post(token_url, data=data, headers=headers)
        resp.raise_for_status()
        tokens = resp.json()
        # tokens conterrà AccessToken, IdToken, RefreshToken, ...
        return {
            "message": "Login social completato con successo",
            "tokens": tokens
        }
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=str(e))
