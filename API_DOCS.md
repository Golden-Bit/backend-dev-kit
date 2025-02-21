# **Documentazione Completa: Cognito Authentication & MFA API**

## **Indice**
1. [Descrizione Generale dell’API](#descrizione-generale)  
2. [Architettura e File Principali](#architettura)  
3. [Setup e Avvio dell’Applicazione](#setup)  
4. [Router “User”](#router-user)  
   - Modelli principali  
   - Endpoint di registrazione, autenticazione, gestione attributi, password e altro  
5. [Router “Admin”](#router-admin)  
   - Modello e endpoint di conferma utente e visualizzazione schema attributi  
6. [Router “MFA”](#router-mfa)  
   - Endpoint per SMS/TOTP e flussi di challenge  
7. [Esempi di utilizzo via cURL/Postman](#esempi-di-utilizzo)  
8. [Considerazioni su Sicurezza e Best Practices](#best-practices)  
9. [Errori Comuni e Soluzioni](#errori-comuni)  
10. [Conclusioni](#conclusioni)

---

## 1. <a name="descrizione-generale"></a>Descrizione Generale dell’API

Questa API, sviluppata con **FastAPI**, si integra con **Amazon Cognito** per gestire:

- **Registrazione e conferma** utenti (sia self-service che admin).  
- **Login** (flusso `USER_PASSWORD_AUTH`) con eventuale MFA.  
- **Aggiornamento attributi** (email, telefono, attributi custom).  
- **Gestione password** (cambio password autenticato, forgot/confirm forgot).  
- **Verifica e decodifica token JWT**.  
- **Conferma e visualizzazione dello schema attributi** (via admin).  
- **Configurazione MFA** (abilitazione/disabilitazione SMS e TOTP).  

### Base URL

Se l’applicazione gira in locale sulla porta 8000, l’indirizzo base è:  
```
http://localhost:8000
```

È disponibile la **documentazione Swagger** all’indirizzo:  
```
http://localhost:8000/docs
```
e la **documentazione Redoc** (alternativa) all’indirizzo:  
```
http://localhost:8000/redoc
```

---

## 2. <a name="architettura"></a>Architettura e File Principali

1. **`main.py`**: 
   - Crea l’oggetto `FastAPI`.
   - Include i tre router: `user_router`, `admin_router`, `mfa_router`.
   - Aggiunge eventuali middleware, come `CORSMiddleware`.
   - Avvia il server (con `uvicorn.run`).

2. **`user.py`**: 
   - Contiene il router `user_router` (prefisso `/v1/user`, tag `"User Operations"`).
   - Gestisce gli endpoint di registrazione, autenticazione, gestione attributi, reset password, ecc.

3. **`admin.py`**: 
   - Contiene il router `admin_router` (prefisso `/v1/admin`, tag `"Admin Operations"`).
   - Fornisce endpoint per confermare manualmente un utente (`admin_confirm_sign_up`), visualizzare schema attributi, ecc.

4. **`mfa.py`**:
   - Contiene il router `mfa_router` (prefisso `/v1/user/mfa`, tag `"User MFA"`).
   - Gestisce l’abilitazione/disabilitazione MFA (SMS/TOTP), la “challenge” MFA in fase di login, ecc.

Ogni file definisce le **configurazioni di Cognito** (REGION, CLIENT_ID, CLIENT_SECRET, USER_POOL_ID), più eventuali modelli Pydantic e funzioni di supporto (`get_secret_hash`).

---

## 3. <a name="setup"></a>Setup e Avvio dell’Applicazione

1. **Clona o scarica** i file `main.py`, `user.py`, `admin.py`, `mfa.py` all’interno di un progetto Python.
2. **Installa le dipendenze**:
   ```bash
   pip install fastapi uvicorn boto3 python-jose requests
   ```
3. **Configura** le credenziali AWS (tramite `~/.aws/credentials`, variabili d’ambiente o ruoli IAM).
4. **Verifica** che `REGION`, `CLIENT_ID`, `CLIENT_SECRET`, `USER_POOL_ID` siano impostati correttamente (se diverso, modificali all’inizio di `user.py`, `admin.py`, `mfa.py`).
5. **Avvia** il server:
   ```bash
   python main.py
   ```
   Per ambiente di sviluppo (auto-reload), puoi usare:
   ```bash
   uvicorn main:app --reload
   ```

---

## 4. <a name="router-user"></a>Router “User”

### 4.1. Descrizione Generale del Router “User”

- **Prefisso**: `/v1/user`  
- **Tag**: `"User Operations"`  
- **Scopo**: Fornire endpoint self-service per utenti, come registrazione, login, gestione attributi, reset password.

### 4.2. Modelli Principali

- **SignUpRequest** (registra un nuovo utente)  
- **SignInRequest** (autentica utente con username/password)  
- **ConfirmSignUpRequest** (conferma registrazione con codice)  
- **ResendConfirmationCodeRequest** (rinvia codice conferma)  
- **UserAttribute**, **UpdateAttributesRequest** (gestione attributi standard)  
- **UpdateCustomAttributesRequest** (gestione attributi custom)  
- **AccessTokenRequest** (usato per operazioni che richiedono un token, come `verify-token`, `user-info`)  
- **ForgotPasswordRequest** e **ConfirmForgotPasswordRequest** (reset password)  
- **RefreshTokenRequest** (rinnovo token con `REFRESH_TOKEN_AUTH`)  
- **ChangePasswordRequest** (cambia password autenticato)  
- **VerifyAttributeRequest** e **ConfirmAttributeRequest** (verifica attributo come phone_number o email)

### 4.3. Endpoint Principali

1. **`POST /v1/user/signup`**  
   Registra un utente su Cognito (usa `sign_up`).

2. **`POST /v1/user/signin`**  
   Effettua login (`initiate_auth` con flusso `USER_PASSWORD_AUTH`).

3. **`POST /v1/user/verify-token`**  
   Verifica un token JWT (scaricando JWKS).

4. **`POST /v1/user/confirm-signup-user`**  
   Conferma un utente con codice (self-service).

5. **`POST /v1/user/resend-confirmation-code`**  
   Rinvia codice di conferma.

6. **`POST /v1/user/update-attributes`** e **`POST /v1/user/update-custom-attributes`**  
   Aggiorna attributi standard e custom.

7. **`POST /v1/user/user-info`**  
   Restituisce info utente (attributi).

8. **`POST /v1/user/forgot-password`** e **`POST /v1/user/confirm-forgot-password`**  
   Flusso di reset password.

9. **`POST /v1/user/refresh-token`**  
   Rinnova Access/Id Token con `RefreshToken`.

10. **`POST /v1/user/change-password`**  
   Cambia password sapendo la vecchia (utente autenticato).

11. **`POST /v1/user/verify-user-attribute`** e **`POST /v1/user/confirm-user-attribute`**  
    Verifica attributo (email/telefono) tramite codice Cognito.

---

## 5. <a name="router-admin"></a>Router “Admin”

### 5.1. Descrizione Generale del Router “Admin”

- **Prefisso**: `/v1/admin`  
- **Tag**: `"Admin Operations"`  
- **Scopo**: Fornire endpoint riservati all’amministratore, per confermare utenti manualmente, visualizzare schema attributi, ecc.

### 5.2. Modello Principale

- **AdminConfirmSignUpRequest**: contenente `username` (conferma forzata senza codice).

### 5.3. Endpoint Principali

1. **`POST /v1/admin/confirm-signup`**  
   - Usa `admin_confirm_sign_up` per forzare la conferma di un utente.  
   - Richiede permessi IAM sufficienti.

2. **`GET /v1/admin/attribute-schema`**  
   - Usa `describe_user_pool` per mostrare lo schema attributi (standard + custom).

3. **`POST /v1/admin/update-attribute-schema`**  
   - Restituisce errore 501 perché Cognito **non** supporta la modifica dello schema dopo la creazione.

---

## 6. <a name="router-mfa"></a>Router “MFA”

### 6.1. Descrizione Generale del Router “MFA”

- **Prefisso**: `/v1/user/mfa`  
- **Tag**: `"User MFA"`  
- **Scopo**: Gestione MFA (SMS e TOTP), oltre all’eventuale challenge.

### 6.2. Modelli Principali

1. **EnableSmsMfaRequest**: `(access_token, phone_number)` per abilitare SMS MFA (telefono già verificato).  
2. **DisableMfaRequest**: `(access_token)` per disabilitare SMS/TOTP.  
3. **AssociateSoftwareTokenRequest**: `(access_token)` per associare TOTP e ottenere `SecretCode`.  
4. **VerifySoftwareTokenRequest**: `(access_token, code, friendly_device_name)` per validare TOTP.  
5. **AccessTokenOnlyRequest**: `(access_token)` minimal.  
6. **MfaRespondChallengeRequest**: `(session, challenge_name, username, code)` per rispondere a challenge MFA se Cognito lo richiede in fase di login.

### 6.3. Endpoint Principali

1. **`POST /v1/user/mfa/respond-challenge`**  
   - Risponde a un challenge MFA (`SMS_MFA` o `SOFTWARE_TOKEN_MFA`) dopo `initiate_auth`.

2. **`POST /v1/user/mfa/enable-sms-mfa`**  
   - Abilita SMS MFA (`set_user_mfa_preference` con `SMSMfaSettings`).

3. **`POST /v1/user/mfa/disable-sms-mfa`**  
   - Disabilita SMS MFA.

4. **`POST /v1/user/mfa/associate-software-token`**  
   - Associa un TOTP, restituendo `SecretCode` base32.

5. **`POST /v1/user/mfa/verify-software-token`**  
   - Verifica che il codice TOTP sia corretto.

6. **`POST /v1/user/mfa/enable-software-mfa`** e **`POST /v1/user/mfa/disable-software-mfa`**  
   - Abilita/disabilita TOTP MFA (impostandola come preferita o disattivandola).

---

## 7. <a name="esempi-di-utilizzo"></a>Esempi di Utilizzo via cURL/Postman

### 7.1. Registrazione e Conferma

```bash
# 1) Signup
curl -X POST http://localhost:8000/v1/user/signup \
  -H "Content-Type: application/json" \
  -d '{
    "username":"testuser",
    "password":"Password123!",
    "email":"testuser@example.com"
  }'

# 2) L'utente riceve un codice (via email)
# 3) Conferma
curl -X POST http://localhost:8000/v1/user/confirm-signup-user \
  -H "Content-Type: application/json" \
  -d '{
    "username":"testuser",
    "confirmation_code":"123456"
  }'
```

### 7.2. Login (Sign-in)

```bash
curl -X POST http://localhost:8000/v1/user/signin \
  -H "Content-Type: application/json" \
  -d '{
    "username":"testuser",
    "password":"Password123!"
  }'
```
**Risposta**: conterrà `AccessToken`, `IdToken`, `RefreshToken`.

### 7.3. Aggiornare attributi custom

```bash
curl -X POST http://localhost:8000/v1/user/update-custom-attributes \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJraWQiOiJr... (omissis)",
    "custom_attributes": {
      "custom:department": "IT",
      "custom:role": "Developer"
    }
  }'
```

### 7.4. Gestione MFA (SMS)

```bash
# Abilita SMS MFA, assumendo phone_number già verificato.
curl -X POST http://localhost:8000/v1/user/mfa/enable-sms-mfa \
  -H "Content-Type: application/json" \
  -d '{
    "access_token":"eyJraWQiOiJr...(omissis)",
    "phone_number":"+391234567890"
  }'
```

### 7.5. Conferma Utente in modo Admin

```bash
curl -X POST http://localhost:8000/v1/admin/confirm-signup \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser"}'
```

---

## 8. <a name="best-practices"></a>Considerazioni su Sicurezza e Best Practices

1. **Protezione degli Endpoint Admin**  
   - Gli endpoint `/v1/admin` consentono operazioni sensibili (es. `admin_confirm_sign_up`). Assicurati di implementarli dietro un meccanismo di autorizzazione (ad es. JWT Admin, VPN interna, IP whitelisting).
2. **Gestione dei Token**  
   - Non salvare in chiaro i token JWT. Verifica la firma con **python-jose** o implementa l’endpoint `/verify-token`.
3. **MFA**  
   - Se vuoi **richiedere** MFA, configuralo come “Required” nella User Pool o abilitalo come “Optional” e poi imposta `PreferredMfa` via endpoint.  
   - Usa `Device Tracking` e `ConfirmDevice` se desideri “ricordare” dispositivi e saltare MFA su dispositivi fidati.
4. **Log e Monitoring**  
   - Utilizza CloudWatch per tracciare i log di errori e le chiamate.  
   - Configura allarmi se superi certe soglie di errori (ad es. troppi `NotAuthorizedException`).
5. **Alto traffico**  
   - Se prevedi un traffico elevato, verifica i limiti di Cognito. Sfrutta token e caching delle JWKS.

---

## 9. <a name="errori-comuni"></a>Errori Comuni e Soluzioni

- **`NotAuthorizedException`**: Se il client richiede il `SecretHash` ma non è stato inviato, controlla `get_secret_hash`.
- **`UserNotConfirmedException`**: L’utente non ha completato la conferma → usa `/confirm-signup-user` o `/v1/admin/confirm-signup`.
- **`InvalidParameterException: USER_PASSWORD_AUTH flow not enabled`**: Abilita `USER_PASSWORD_AUTH` nell’App Client.
- **`Modifica schema attributi non supportata`**: Cognito non permette di modificare lo schema dopo la creazione → endpoint `/update-attribute-schema` ritorna 501.

---

## 10. <a name="conclusioni"></a>Conclusioni

Con questa documentazione, disponi di:

- **Un’API completa** che copre registrazione, conferma, login, reset password, gestione attributi, e MFA (SMS/TOTP).  
- **Tre router** separati (`user`, `admin`, `mfa`) per rispettare le responsabilità: self-service vs. admin vs. multi-factor.  
- **Esempi** di chiamate via cURL e linee guida su come installare e lanciare l’applicazione.

Se desideri estendere ulteriormente l’API:

1. **Aggiungi** funzioni avanzate di device tracking (ricorda dispositivi).  
2. **Proteggi** gli endpoint con un sistema di autorizzazione robusto.  
3. **Integra** provider social (Google, Facebook) con Cognito se necessario.  
