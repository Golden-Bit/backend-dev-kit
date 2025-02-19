Di seguito trovi una **documentazione completa e dettagliata**, in italiano, di tutte le procedure che abbiamo seguito per configurare, integrare e utilizzare Amazon Cognito con un backend Python sviluppato in FastAPI. Questa guida contiene i passaggi step-by-step: dalla creazione di un account AWS, alla configurazione della **User Pool**, fino all’implementazione delle **API** per la gestione di utenti, attributi e token.

---

# Documentazione Dettagliata su Amazon Cognito e Integrazione con FastAPI

## 1. Creazione e Configurazione di un Account AWS

1. **Registrazione su AWS (se necessario)**  
   - Vai su [aws.amazon.com](https://aws.amazon.com/) e crea un account.  
   - Inserisci i dati richiesti (informazioni personali, metodo di pagamento, ecc.).  
   - Al termine, avrai accesso alla console di gestione AWS.

2. **Accesso alla Console di Gestione**  
   - Dirigiti su [console.aws.amazon.com](https://console.aws.amazon.com/).  
   - Assicurati di utilizzare un utente IAM con i permessi necessari (preferibilmente **AdministratorAccess** se stai solamente sperimentando, oppure permessi più granulari se sei in produzione).

---

## 2. Configurazione di Amazon Cognito

### 2.1. Creazione della User Pool

1. **Accedi al servizio Cognito**  
   - Nella barra di ricerca della console AWS, digita “Cognito” e seleziona **Amazon Cognito**.
2. **Creazione di una User Pool**  
   - Clicca su **Manage User Pools** e poi su **Create a user pool**.  
   - Assegna un nome significativo, ad esempio `sxu1it` (oppure un altro nome a piacere).
3. **Configurazione degli attributi**  
   - Durante la procedura guidata, puoi scegliere se abilitare l’email o il numero di telefono come attributi primari.  
   - Se desideri che l’email sia un attributo univoco, puoi abilitare l’opzione che rende l’email un alias univoco.  
   - Puoi anche definire attributi aggiuntivi (custom), ad esempio `custom:department`, `custom:role`, ecc.  
4. **Impostazioni di sicurezza**  
   - Configura la policy delle password (lunghezza minima, complessità, ecc.).  
   - Decidi se abilitare MFA (Multi-Factor Authentication).  
5. **Verifica degli utenti**  
   - Scegli se inviare un codice di verifica via email o SMS per confermare gli utenti.  
   - Verifica di avere correttamente impostato l’indirizzo “FROM” o il servizio Amazon SES se vuoi personalizzare la posta in uscita.
6. **Creazione conclusiva**  
   - Fai clic su **Create Pool**.  
   - Prendi nota del **User Pool ID** e, se necessario, del relativo **ARN**.

### 2.2. Creazione di un App Client

1. **All’interno della User Pool**, vai su **App clients** e seleziona **Add an app client**.  
   - Dai un nome (es. `test_0`).
   - Se vuoi usare flussi server-to-server, puoi **disabilitare** la generazione del client secret, ma se lo abiliti, Cognito richiederà l’invio di un `SecretHash`.
2. **Abilitazione dei flussi di autenticazione**  
   - Assicurati di spuntare **USER_PASSWORD_AUTH** se desideri autenticare gli utenti con username e password (flusso tipico).  
   - Salva e prendi nota del **Client ID** (e del **Client secret**, se l’hai abilitato).
3. **Dominio Cognito (opzionale)**  
   - Se vuoi usare il **Hosted UI** o i flussi OAuth2 integrati, configura un dominio (AWS fornisce un dominio di default `your-domain.auth.region.amazoncognito.com`, oppure ne puoi usare uno personalizzato).

---

## 3. Preparazione dell’Ambiente di Sviluppo Python

1. **Installazione di Python 3**  
   - Assicurati di avere Python 3 installato.  
   - Se usi `venv`, crea e attiva un ambiente virtuale.
2. **Installazione delle librerie necessarie**  
   ```bash
   pip install fastapi uvicorn boto3 python-jose requests
   ```
   - **fastapi**: framework per le nostre API.  
   - **uvicorn**: server ASGI leggero per eseguire l’app.  
   - **boto3**: SDK AWS per Python.  
   - **python-jose**: libreria per lavorare con i token JWT.  
   - **requests**: libreria HTTP per richieste esterne (utilizzata ad esempio per scaricare le JWKS).

3. **Configurazione delle Credenziali AWS**  
   - Crea o modifica il file `~/.aws/credentials` (o usa variabili d’ambiente).  
   - Verifica di avere i permessi necessari per interagire con Cognito (`AmazonCognitoIdentityProviderFullAccess`, o equivalenti).

---

## 4. Integrazione Cognito-Python con FastAPI

### 4.1. Il codice di base

Di seguito riportiamo un **esempio completo** di codice FastAPI che include:

1. **Registrazione (signup)** con calcolo del `SecretHash`.
2. **Autenticazione (signin)** con il flusso `USER_PASSWORD_AUTH`.
3. **Conferma utente** (sia lato utente con codice, sia lato admin).
4. **Resend confirmation code** per rinviare il codice di conferma.
5. **Update degli attributi** (sia standard che custom).
6. **Get user info** con l’access token.  
7. **Verifica dei token JWT**.  
8. **Visualizzazione schema attributi**.  
9. **Tentativo di aggiornamento schema attributi** (non supportato da Cognito).

Salva il seguente codice in un file, ad esempio `main.py`:

```python
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict
import boto3
import requests
from jose import jwt
import hmac
import hashlib
import base64

app = FastAPI(
    title="Cognito User Management API",
    description=(
        "API per la gestione degli utenti tramite Amazon Cognito.\n\n"
        "Questa API offre endpoint per la registrazione, autenticazione, "
        "verifica del token, conferma della registrazione, invio di un nuovo codice di conferma, "
        "aggiornamento degli attributi utente, la visualizzazione delle informazioni utente "
        "e dello schema attributi, e un esempio di endpoint per modificare lo schema (non supportato)."
    ),
    version="1.0.0"
)

# ----------------------------------
# Configurazioni per Amazon Cognito
# ----------------------------------
REGION = "eu-north-1"  # Modifica in base alla tua regione
CLIENT_ID = "7gp9s0b5nli705a97qik32l1mi"
CLIENT_SECRET = "4l1nfigk9abonrhkoonqnlo769bbs724ja64j8nqniugmsmf0si"
USER_POOL_ID = "eu-north-1_0dyOzfzna"
JWKS_URL = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"

# Crea il client boto3 per Cognito Identity Provider
cognito_client = boto3.client("cognito-idp", region_name=REGION)

def get_secret_hash(username: str) -> str:
    """
    Calcola il SecretHash richiesto da Cognito, ovvero la codifica Base64 dell'HMAC-SHA256
    del messaggio (username + CLIENT_ID) firmato con il CLIENT_SECRET.
    """
    message = username + CLIENT_ID
    digest = hmac.new(
        CLIENT_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()

# ----------------------------------
# Modelli di input per gli endpoint
# ----------------------------------
class SignUpRequest(BaseModel):
    username: str = Field(..., description="Nome utente per la registrazione")
    password: str = Field(..., description="Password per l'utente")
    email: str = Field(..., description="Indirizzo email dell'utente")

class SignInRequest(BaseModel):
    username: str = Field(..., description="Nome utente per l'autenticazione")
    password: str = Field(..., description="Password dell'utente")

class ConfirmSignUpRequest(BaseModel):
    username: str = Field(..., description="Nome utente da confermare")
    confirmation_code: str = Field(..., description="Codice di conferma ricevuto via email")

class AdminConfirmSignUpRequest(BaseModel):
    username: str = Field(..., description="Nome utente da confermare (tramite operazione amministrativa)")

class ResendConfirmationCodeRequest(BaseModel):
    username: str = Field(..., description="Nome utente per cui inviare il nuovo codice di conferma")

class UserAttribute(BaseModel):
    Name: str = Field(..., description="Nome dell'attributo (es. 'email' o 'custom:department')")
    Value: str = Field(..., description="Valore dell'attributo")

class UpdateAttributesRequest(BaseModel):
    access_token: str = Field(..., description="Token di accesso dell'utente")
    attributes: List[UserAttribute] = Field(..., description="Lista degli attributi da aggiornare")

class AccessTokenRequest(BaseModel):
    access_token: str = Field(..., description="Access token dell'utente")

# ----------------------------------
# Endpoint (Signup, Signin, ecc.)
# ----------------------------------

@app.post("/signup", summary="Registrazione utente", response_description="Risposta di registrazione da Cognito")
async def signup(request_data: SignUpRequest):
    """
    Registra un nuovo utente in Amazon Cognito inviando username, password e email.
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

@app.post("/confirm-signup", summary="Conferma registrazione utente (Admin)", response_description="Messaggio di conferma")
async def confirm_signup(request_data: AdminConfirmSignUpRequest):
    """
    Conferma la registrazione di un utente tramite operazione amministrativa (admin_confirm_sign_up).
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
    Conferma la registrazione di un utente inserendo il codice di conferma ricevuto via email (confirm_sign_up).
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
    Invia nuovamente il codice di conferma, nel caso l'utente non abbia ricevuto il primo.
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
    Aggiorna gli attributi di un utente autenticato, fornendo il token di accesso e la lista di attributi (Name, Value).
    """
    try:
        response = cognito_client.update_user_attributes(
            AccessToken=request_data.access_token,
            UserAttributes=[attr.dict() for attr in request_data.attributes]
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ----------------------------------
# Endpoint get_user_info: ottiene informazioni utente da AccessToken
# ----------------------------------
@app.get("/user-info", summary="Visualizza informazioni utente", response_description="Informazioni complete dell'utente")
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

# ----------------------------------
# Endpoint per la verifica del token JWT
# ----------------------------------
@app.get("/verify-token", summary="Verifica token JWT", response_description="Token decodificato")
async def verify_token(
    token_input: str = Body(..., description="Il token JWT da decodificare e verificare")
):
    """
    Verifica e decodifica un token JWT emesso da Cognito, scaricando le JWKS pubbliche.
    """
    token = token_input
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

# ----------------------------------
# Endpoint per visualizzare lo schema degli attributi
# ----------------------------------
@app.get("/attribute-schema", summary="Visualizza schema degli attributi", response_description="Schema corrente degli attributi del pool")
async def get_attribute_schema():
    """
    Restituisce lo schema corrente degli attributi definiti nel User Pool
    (standard e custom), utile per capire quali attributi sono disponibili.
    """
    try:
        response = cognito_client.describe_user_pool(UserPoolId=USER_POOL_ID)
        if "UserPool" in response and "SchemaAttributes" in response["UserPool"]:
            return response["UserPool"]["SchemaAttributes"]
        else:
            return {"message": "SchemaAttributes non disponibili per questo User Pool."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ----------------------------------
# Endpoint per "modificare" lo schema degli attributi (non supportato da Cognito)
# ----------------------------------
@app.post("/update-attribute-schema", summary="Modifica schema degli attributi", response_description="Risposta dall'aggiornamento dello schema")
async def update_attribute_schema():
    """
    Endpoint di esempio. Cognito non permette di modificare lo schema degli attributi
    dopo la creazione del User Pool, quindi restituirà un errore 501 (Not Implemented).
    """
    raise HTTPException(
        status_code=501,
        detail="Modifica dello schema degli attributi non è supportata da Cognito dopo la creazione del pool."
    )

# ----------------------------------
# Avvio dell'applicazione
# ----------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

### 4.2. Avvio dell’applicazione

1. **Salva il file** (es. `main.py`).  
2. **Esegui con Uvicorn**:  
   ```bash
   uvicorn main:app --reload
   ```
3. **Test e documentazione Swagger**  
   - Apri il browser all’indirizzo `http://localhost:8000/docs`.  
   - Troverai un’interfaccia interattiva per testare gli endpoint.

---

## 5. Gestione degli Errori Comuni e Debug

1. **`NotAuthorizedException` / `SECRET_HASH was not received`**  
   - Significa che il tuo App Client in Cognito ha un client secret configurato, per cui è necessario calcolare e passare il `SecretHash`.
2. **`InvalidParameterException: USER_PASSWORD_AUTH flow not enabled for this client`**  
   - Devi abilitare il flusso **USER_PASSWORD_AUTH** nelle impostazioni dell’App Client.
3. **`UserNotConfirmedException: User is not confirmed`**  
   - L’utente ha completato il signup ma non ha eseguito la conferma via email o SMS.  
   - Puoi confermare manualmente via `admin_confirm_sign_up` o implementare l’endpoint di conferma con codice.
4. **Email duplicata**  
   - Di default, Cognito non impone l’unicità dell’email. Per forzare l’unicità, devi configurare l’email come alias univoco (oppure usare un trigger pre-sign-up per bloccare iscrizioni con la stessa email).
5. **Attributi custom**  
   - Cognito richiede il prefisso `custom:` per gli attributi non standard. Se vuoi salvare, ad esempio, `department`, devi definirlo come `custom:department` nel pool.

---

## 6. Best Practices & Suggerimenti

1. **Sicurezza delle credenziali AWS**  
   - Non committare le credenziali su repository pubblici.  
   - Preferisci l’uso di ruoli IAM se l’app gira su un servizio AWS (ad es. EC2, ECS, Lambda).
2. **Validazione lato server**  
   - Verifica sempre la lunghezza e la complessità delle password, anche lato backend, soprattutto se gestisci input da fonti non fidate.
3. **Logging e monitoraggio**  
   - Utilizza CloudWatch per monitorare i log di Cognito (in caso di errori).  
   - Considera l’impiego di metriche personalizzate o Amazon Pinpoint se devi analizzare i comportamenti degli utenti.
4. **Scalabilità**  
   - Cognito gestisce automaticamente lo scaling per migliaia/milioni di utenti, ma assicurati di avere un design dell’app scalabile e di ottimizzare la gestione dei token.
5. **Verifica del token JWT**  
   - Nei microservizi, assicurati di verificare i token `AccessToken` e/o `IdToken` mediante la chiave pubblica (JWKS) di Cognito, in modo da prevenire accessi non autorizzati.

---

## 7. Conclusioni

In questa documentazione abbiamo visto:

1. **Come configurare** un account AWS e creare una **User Pool** con Cognito.  
2. **Come creare** un **App Client** e abilitare i flussi di autenticazione desiderati.  
3. **Come integrare** Python (con FastAPI) e **boto3** per eseguire operazioni di registrazione, autenticazione, conferma, reinvio del codice di conferma, aggiornamento attributi e verifica token.  
4. **Come gestire** i token JWT e le possibili problematiche (utenti non confermati, alias email, attributi duplicati, ecc.).  
5. **Come visualizzare** lo schema degli attributi e **perché** Cognito non supporta la modifica dello schema dopo la creazione.

Questo set di endpoint e istruzioni copre le esigenze più comuni per la gestione di utenti in un progetto che sfrutta la potenza e la scalabilità di Amazon Cognito.

---

**Hai ulteriori domande o richieste di approfondimento?** Sentiti libero di chiedere ulteriori chiarimenti su argomenti specifici, flussi di autenticazione avanzati (SRP, OAuth2), integrazione con social login (Google, Facebook, ecc.) o su come personalizzare ulteriormente la User Pool. Buon sviluppo!