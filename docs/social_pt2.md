## 1. Panoramica del Social Router

Il **Social Router** è stato creato per gestire il flusso di autenticazione federata tramite provider terzi (come Google, Facebook, Apple, ecc.) utilizzando il Hosted UI di Amazon Cognito. Il flusso tipico prevede due fasi principali:

1. **Redirezione al Hosted UI**: l'utente viene reindirizzato a Cognito, dove potrà scegliere il provider configurato (es. Google).  
2. **Callback**: dopo l'autenticazione sul provider, Cognito reindirizza l'utente a un URL di callback predefinito, dove il codice di autorizzazione (`code`) viene scambiato per i token (AccessToken, IdToken, RefreshToken).

---

## 2. Spiegazione del Codice del Social Router

Il file `social.py` contiene il seguente codice (vedi l’esempio precedente). Ecco i punti chiave:

### 2.1. Caricamento della Configurazione

```python
from config import load_cognito_config
cognito_config = load_cognito_config("config.json")
REGION = cognito_config["REGION"]
CLIENT_ID = cognito_config["CLIENT_ID"]
CLIENT_SECRET = cognito_config["CLIENT_SECRET"]
USER_POOL_ID = cognito_config["USER_POOL_ID"]
```

**Cosa fa:**  
- Carica le impostazioni di Amazon Cognito da un file JSON (`config.json`).
- Imposta variabili come `REGION`, `CLIENT_ID`, ecc. Queste variabili sono utilizzate per costruire l’URL del Hosted UI e per effettuare scambi di token.

### 2.2. Definizione del Dominio Cognito

```python
COGNITO_DOMAIN = "myapp.authentication.eu-north-1.amazoncognito.com"
```

**Cosa fa:**  
- Imposta il dominio del tuo Hosted UI di Cognito.  
- **Nota:** In un ambiente di produzione, questo dominio sarà il dominio personalizzato configurato nella User Pool. Non sarà "localhost" ma un dominio pubblico (es. `login.myapp.com` o `myapp.auth.eu-north-1.amazoncognito.com`).

### 2.3. Endpoint per il Login Social

#### 2.3.1. `/login`

```python
@social_router.get("/login", summary="Avvia il login social con redirect", response_description="Reindirizza al Hosted UI di Cognito")
async def social_login(provider: str):
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
    return RedirectResponse(url_with_params)
```

**Funzionamento:**  
- **Input**: Un parametro di query `provider` che indica il provider scelto (es. `Google` o `Facebook`).
- **Processo**:
  - Imposta un `redirect_uri`, l’URL a cui Cognito invierà la risposta dopo l’autenticazione.  
    > In ambiente di produzione, questo valore dovrà essere un URL pubblico (es. `https://login.myapp.com/v1/user/social/callback`).
  - Costruisce l’URL base per il flusso OAuth2 di Cognito usando il dominio (ad esempio, `https://myapp.auth.eu-north-1.amazoncognito.com/oauth2/authorize`).
  - Aggiunge alla query string i parametri richiesti: `client_id`, `response_type` (impostato su `"code"`), `scope` (es. `"openid email profile"`), `redirect_uri`, e `identity_provider`.
- **Output**: Restituisce un **RedirectResponse** che indirizza il browser al Hosted UI di Cognito.  
- **Adattamento per Produzione**: Sostituisci il valore di `redirect_uri` con l'URL pubblico configurato nella tua User Pool.

#### 2.3.2. `/login-url`

```python
@social_router.get("/login-url", summary="Restituisce URL per login social", response_description="URL di login social come stringa")
async def social_login_url(provider: str):
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
```

**Funzionamento:**  
- Simile a `/login`, ma anziché reindirizzare automaticamente, restituisce un oggetto JSON con il campo `login_url`.
- Questo approccio è utile se si desidera gestire il redirect lato client (ad esempio, in un'applicazione SPA).

#### 2.3.3. `/callback`

```python
@social_router.get("/callback", summary="Endpoint di callback per il social login", response_description="Token OAuth2 scambiati con Cognito")
async def social_callback(code: str, state: str = None):
    token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"
    redirect_uri = "http://localhost:8000/v1/user/social/callback"
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": redirect_uri,
        "client_secret": CLIENT_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = requests.post(token_url, data=data, headers=headers)
        resp.raise_for_status()
        tokens = resp.json()
        return tokens
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Funzionamento:**  
- **Input**: Riceve nella query string il parametro `code` (e opzionalmente `state`), che Cognito invia dopo il login sul provider.
- **Processo**:
  - Costruisce l’URL per scambiare il codice con i token (`/oauth2/token`).
  - Imposta i parametri della richiesta POST: `grant_type` (impostato su `"authorization_code"`), `client_id`, `code`, `redirect_uri` (lo stesso usato nel login) e `client_secret`.
  - Effettua una chiamata POST a Cognito per ottenere i token.
- **Output**: Restituisce i token (AccessToken, IdToken, RefreshToken) in formato JSON.
- **Adattamento per Produzione**: Assicurati che il `redirect_uri` sia lo stesso configurato in Cognito per il tuo ambiente (es. `https://login.myapp.com/v1/user/social/callback`).

---

## 3. Generalizzazione a un Ambiente Diverso da Localhost

Quando passi dall'ambiente di sviluppo (localhost) a quello di produzione, devi considerare:

- **Redirect URI**:  
  - Sostituisci `"http://localhost:8000/v1/user/social/callback"` con l’URL pubblico configurato nella tua User Pool (es. `"https://login.myapp.com/v1/user/social/callback"`).  
  - Assicurati che questo URL sia incluso nella sezione "Allowed Callback URLs" della User Pool.

- **Dominio Cognito**:  
  - Se utilizzi un dominio personalizzato (es. `"login.myapp.com"`), imposta `COGNITO_DOMAIN` di conseguenza.  
  - In ambienti di produzione, è consigliabile usare HTTPS per la sicurezza.

- **Configurazione dei Provider**:  
  - I provider esterni (Google, Facebook, ecc.) richiedono che il redirect URI sia esatto.  
  - Aggiorna le configurazioni dei provider esterni nella console Cognito con l’URL di callback corretto.

- **Sicurezza e CORS**:  
  - In produzione, restringi le origini consentite nel middleware CORS invece di usare `allow_origins=["*"]`.

---

## 4. Riassunto del Flusso Social Login

1. **Inizio**: L'utente visita l'endpoint `/v1/user/social/login?provider=Google` (o un altro provider).  
   - Il server costruisce l'URL per il Hosted UI di Cognito e reindirizza l'utente.
2. **Hosted UI**: L'utente esegue il login tramite il provider scelto.
3. **Callback**: Cognito reindirizza l'utente all'endpoint `/v1/user/social/callback` con un parametro `code`.
4. **Scambio Code → Token**: L'endpoint `/callback` scambia il `code` con i token OAuth2 (Access, ID, Refresh) chiamando l'endpoint `/oauth2/token` di Cognito.
5. **Risultato**: L'utente riceve i token che possono essere usati per accedere ad altri endpoint dell’API.

---

## 5. Conclusioni

Il **Social Router** integra il flusso di autenticazione federata in modo trasparente:
- **Redirect**: L’utente viene indirizzato al Cognito Hosted UI, dove può autenticarsi con provider esterni.
- **Callback**: Dopo l’autenticazione, l’endpoint `/callback` gestisce lo scambio del codice con i token.
- **Adattamento**: I valori di `redirect_uri` e `COGNITO_DOMAIN` devono essere aggiornati per l’ambiente di produzione, assicurando coerenza con le impostazioni della User Pool.
