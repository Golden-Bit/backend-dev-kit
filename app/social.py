from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
import urllib.parse
import requests
from app.utilities import load_cognito_config


# Caricamento della configurazione da un file JSON (config.json) tramite config.py
cognito_config = load_cognito_config("app/config.json")
REGION = cognito_config["REGION"]
CLIENT_ID = cognito_config["CLIENT_ID"]
CLIENT_SECRET = cognito_config["CLIENT_SECRET"]
USER_POOL_ID = cognito_config["USER_POOL_ID"]

# Imposta il dominio Cognito configurato (deve essere definito nella console Cognito)
# Esempio: "myapp.auth.eu-north-1.amazoncognito.com"
COGNITO_DOMAIN = "myapp.auth.eu-north-1.amazoncognito.com"

social_router = APIRouter(
    prefix="/v1/user/social",
    tags=["User Social Login"]
)

class SocialLoginRequest(BaseModel):
    """
    Modello per specificare il provider di social login.

    Attributes:
        provider (str): Nome del provider. Deve corrispondere a quanto configurato in Cognito (es. "Google", "Facebook").
    """
    provider: str = Field(..., description="Nome del provider (Google, Facebook, Apple, Amazon, etc.)")

@social_router.get("/login-redirect", summary="Avvia il login social con redirect", response_description="Reindirizza al Hosted UI di Cognito")
async def social_login_redirect(provider: str):
    """
    Reindirizza l'utente al Cognito Hosted UI per l'autenticazione tramite un provider esterno.

    Query Parameters:
        - provider: Nome del provider (es. "Google", "Facebook"). Deve corrispondere a quanto configurato in Cognito.

    Flow:
        1. Costruisce l'URL di autorizzazione di Cognito con i parametri necessari:
           - client_id, response_type=code, scope, redirect_uri, identity_provider.
        2. Restituisce un RedirectResponse verso l'URL di Hosted UI.
    """
    redirect_uri = "http://localhost:8000/v1/user/social/callback"
    base_auth_url = f"https://{COGNITO_DOMAIN}/oauth2/authorize"
    query_params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid email profile",  # Modifica gli scope secondo le tue necessità
        "redirect_uri": redirect_uri,
        "identity_provider": provider
    }
    url_with_params = base_auth_url + "?" + urllib.parse.urlencode(query_params)
    return RedirectResponse(url_with_params)

@social_router.get("/login-url", summary="Restituisce URL per login social", response_description="URL di login social come stringa")
async def social_login_url(provider: str):
    """
    Restituisce l'URL per il login social (Hosted UI) come JSON, senza eseguire un redirect.

    Query Parameters:
        - provider: Nome del provider (es. "Google", "Facebook").

    Questo endpoint consente al client di ottenere l'URL e poi gestire il redirect lato client.

    Returns:
        JSON contenente "login_url".
    """
    redirect_uri = "http://localhost:8000/v1/user/social/callback"
    base_auth_url = f"https://{COGNITO_DOMAIN}/oauth2/authorize"
    query_params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": redirect_uri,
        "identity_provider": provider
    }
    url_with_params = base_auth_url + "?" + urllib.parse.urlencode(query_params)
    return JSONResponse(content={"login_url": url_with_params})

@social_router.get("/callback", summary="Endpoint di callback per il social login", response_description="Token OAuth2 scambiati con Cognito")
async def social_callback(code: str, state: str = None):
    """
    Endpoint di callback per il login social.

    Dopo che l'utente si è autenticato tramite il provider esterno,
    Cognito reindirizza l'utente a questo endpoint con un parametro 'code'.

    Query Parameters:
        - code: Codice di autorizzazione da scambiare per i token.
        - state: (Opzionale) Parametro di stato per protezione CSRF.

    Flow:
        1. Scambia il codice con Cognito chiamando l'endpoint /oauth2/token.
        2. Restituisce i token (AccessToken, IdToken, RefreshToken) in formato JSON.
    """
    token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"
    redirect_uri = "http://localhost:8000/v1/user/social/callback"
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": redirect_uri,
        "client_secret": CLIENT_SECRET  # Necessario se il client è configurato con secret
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = requests.post(token_url, data=data, headers=headers)
        resp.raise_for_status()
        tokens = resp.json()
        return tokens
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=str(e))
