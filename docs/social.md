# **Social Router**

- **Prefisso**: `/v1/user/social`
- **Tag**: `User Social Login`  
- **Scopo**: Consentire l’**autenticazione** tramite provider esterni (Google, Facebook, Apple, Amazon, e altri IdP configurati in Cognito).  
- **Principali Flussi**:  
  1. **Redirezione** al Hosted UI di Cognito con identity_provider specificato.  
  2. **Callback** su un endpoint che scambia il `code` OAuth con i token (Access/Id/Refresh).

---

## 1. Descrizione Generale

Molte applicazioni desiderano consentire agli utenti di effettuare il login con account di terze parti (Google, Facebook, Apple, Amazon, etc.). In **Amazon Cognito**, questo si implementa:

1. **Configurando** l’Identity Provider nella console Cognito.  
2. **Abilitando** il Hosted UI e impostando un dominio personalizzato (es. `myapp.auth.eu-north-1.amazoncognito.com`).  
3. **Registrando** gli URL di callback (ad es. `http://localhost:8000/v1/user/social/callback`) come “Allowed callback URLs”.

Il **Social Router** si aggancia a questi flussi: un utente effettua una chiamata a un endpoint come `/login`, viene redirectato su Hosted UI e, dopo aver completato l’accesso col provider, Cognito rimanda al callback (`/callback`) dove l’API scambia `code` con i token.

---

## 2. Modelli Principali

All’interno di `social.py` (o file analogo), potresti usare:

### 2.1. `SocialLoginRequest` (opzionale)

```python
class SocialLoginRequest(BaseModel):
    """
    Modello per specificare il provider di social login
    (es. 'Google', 'Facebook', 'Amazon', 'Apple').
    """
    provider: str = Field(..., description="Nome del provider. Deve combaciare con quanto configurato in Cognito.")
```

**Descrizione**  
- **provider**: Nome del provider esterno (Google, Facebook, Apple, Amazon…) che dev’essere già configurato in Cognito come Identity Provider.  
- Potresti non usare questo modello se preferisci passare `provider` via query param (`?provider=Google`).

---

## 3. Endpoint Principali

### 3.1. `GET /v1/user/social/login`

**Descrizione**  
- Avvia il flusso di login federato con un provider specifico, costruendo l’URL del **Hosted UI** di Cognito e reindirizzando l’utente lì.  
- Parametri: `provider` (es. “Google”, “Facebook”).  
- Risposta: un **redirect** a Cognito Hosted UI con i parametri OAuth (`response_type=code`, `redirect_uri=...`, ecc.).

**Esempio**  
```bash
curl -X GET "http://localhost:8000/v1/user/social/login?provider=Google"
```
Verrà ritornata una `RedirectResponse` verso l’URL `https://<your-domain>.auth.<region>.amazoncognito.com/oauth2/authorize?...`.

**Nota**: L’utente completerà la procedura di login sul sito del provider (Google/Facebook). Cognito otterrà un `code` e reindirizzerà su `/callback`.

---

### 3.2. `GET /v1/user/social/callback`

**Descrizione**  
- Endpoint di **callback** che Cognito invoca dopo il login esterno.  
- Riceve `code` e `state` nella query string (`?code=XYZ&state=...`).  
- Scambia il `code` con i **token** (`AccessToken`, `IdToken`, `RefreshToken`) chiamando `oauth2/token` su Cognito.  
- Restituisce i token in JSON (oppure un redirect a una pagina interna dell’app, a seconda della tua logica).

**Esempio**  
Quando Cognito reindirizza:
```bash
GET /v1/user/social/callback?code=abc123&state=someState
```
L’endpoint fa una POST a:  
```
https://<your-domain>.auth.<region>.amazoncognito.com/oauth2/token
```
con `grant_type=authorization_code`, `client_id`, `client_secret` (se necessario), `redirect_uri`. Ottenuti i token, risponde:

```json
{
  "message": "Login social completato con successo",
  "tokens": {
    "access_token": "...",
    "id_token": "...",
    "refresh_token": "...",
    "token_type": "Bearer",
    "expires_in": 3600
  }
}
```

---

## 4. Flusso di Autenticazione Federata

1. **L’utente chiama** `GET /v1/user/social/login?provider=Google`.  
2. **API** costruisce l’URL su Cognito Hosted UI e **redirecta** l’utente.  
3. **Utente** effettua login con Google su Hosted UI.  
4. **Cognito** reindirizza su `/v1/user/social/callback?code=...`.  
5. **API** scambia `code` con i token.  
6. **Risposta**: fornisce i token al client (o reindirizza altrove).

---

## 5. Parametri e Configurazione Cognito

Per usare efficacemente questo router:

1. **Configura** un dominio per la User Pool (es. `myapp.auth.eu-north-1.amazoncognito.com`).  
2. **Abilita** “Identity providers” esterni (Google, Facebook, Apple, Amazon, OIDC generico, SAML, ecc.).  
3. **Aggiungi** in “App client settings” → “Callback URLs” l’URL `http://localhost:8000/v1/user/social/callback` (o la callback in produzione).
4. **Abilita** i flussi OAuth (`Authorization code grant`) e definisci i **scope** (`email`, `openid`, `profile`, ecc.).
5. **CLIENT_SECRET**: Se il client ha un segreto, l’endpoint `/callback` deve usare l’autenticazione (ad esempio via `client_secret` in POST o `Authorization: Basic ...`).

---

## 6. Esempio di Codice Minimale del Router

**Mostrato solo in documentazione** (si suppone stia in `social.py`):

```python
@social_router.get("/login")
async def social_login(provider: str):
    # Costruisce URL di Hosted UI
    # ...
    return RedirectResponse(url_with_params)

@social_router.get("/callback")
async def social_callback(code: str, state: str = None):
    # Scambia code con i token
    # ...
    return {
      "message": "Login social completato",
      "tokens": tokens
    }
```

---

## 7. Possibili Personalizzazioni

- **Stato**: Potresti generare un `state` random per prevenire attacchi CSRF.  
- **Redirect Finale**: Anziché restituire i token in JSON, potresti reindirizzare l’utente a un client web con `#access_token=...` (o altre logiche).  
- **Persistenza**: Se vuoi salvare i token, puoi metterli in un cookie, o in un DB, ecc.  
- **Provider Param**: Potresti usare un body JSON, un query param, o endpoint separati (`/login/google`, `/login/facebook`).

---

## 8. Esempio di Utilizzo via cURL

Anche se è insolito usare `curl` per un redirect-based flow, ecco un esempio:

```bash
curl -i "http://localhost:8000/v1/user/social/login?provider=Google"
```
Riceverai un redirect 307/302 verso l’URL di Cognito. Se segui i redirect con `curl -L`, dovresti vedere la pagina Hosted UI (HTML). In ambiente browser, l’utente visualizza la pagina di login del provider.

---

## 9. Considerazioni su Sicurezza e Best Practices

- **HTTPS**: Usa sempre HTTPS in produzione. Il redirect_uri deve essere in HTTPS su un dominio sicuro.  
- **Protezione** del callback: Verifica `state` se hai generato un token anti-CSRF.  
- **Ruoli e Permessi**: Configura i provider social in Cognito in modo appropriato, definendo i param di client ID/secret (es. Google OAuth).  
- **Tokens**: Il client dovrà poi gestire `AccessToken` e `IdToken` come per qualsiasi utente Cognito nativo.

---

## 10. Conclusioni

Il **Social Router** arricchisce l’API con la possibilità di **autenticare** gli utenti via Google, Facebook, Apple o altri provider. Lavora in **cooperazione** con la configurazione di Cognito (Hosted UI) e si integra con i token e gli attributi degli utenti come un normale utente Cognito nativo. 

