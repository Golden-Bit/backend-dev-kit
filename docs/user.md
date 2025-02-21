# **Guida Step-by-Step per l’Uso degli Endpoint della Rotta `User`**

## 1. Prerequisiti e Configurazioni di Base

### 1.1. Account AWS e Cognito

1. **Account AWS**: Assicurati di avere un account AWS con privilegi sufficienti per creare e modificare una **User Pool** in Amazon Cognito.  
2. **User Pool**: Crea o individua una **User Pool**. Nel codice, notiamo che sono stati impostati:
   - **REGIONE** = `eu-north-1`  
   - **CLIENT_ID** = `7gp9s0b5nli705a97qik32l1mi`  
   - **CLIENT_SECRET** = `4l1nfigk9abonrhkoonqnlo769bbs724ja64j8nqniugmsmf0si`  
   - **USER_POOL_ID** = `eu-north-1_0dyOzfzna`

   Dovrai **sostituire** questi valori o **adattarli** se la tua configurazione di Cognito è diversa.

### 1.2. Configurare un App Client (ClientId)

1. All’interno della User Pool, nella sezione **App Clients**, individua o crea un “App client” con le impostazioni necessarie.
2. Se vuoi usare il `SecretHash`, assicurati di abilitare il client secret.  
3. **Abilita** i flussi di autenticazione **USER_PASSWORD_AUTH** se vuoi usare `initiate_auth` con quell’AuthFlow.  
4. Prendi nota di:
   - **ClientId**  
   - **ClientSecret** (se abilitato)

Questi dati devono corrispondere ai valori impostati in **CLIENT_ID** e **CLIENT_SECRET** nel tuo file `user.py`.

### 1.3. Configurare attributi nella User Pool

- Se vuoi che gli utenti abbiano un **email** e/o **phone_number**, assicurati di **abilitare** tali attributi e, a seconda dei casi, impostarli come **alias** per il login o attributi obbligatori.  
- Se desideri **attributi custom**, definiscili nella sezione **Attributes** → **Add custom attribute** (es. `custom:role`, `custom:department`, ecc.).

---

## 2. Preparare il Codice e l’Ambiente

### 2.1. Scaricare/Creare il File `user.py`

1. **Copia** il contenuto di `user.py` nel tuo progetto Python (ad esempio in una cartella chiamata `routers/` o `app/`).
2. **Installa** i requisiti minimi:
   ```bash
   pip install fastapi uvicorn boto3 python-jose requests
   ```
3. **Configura** le credenziali AWS nel tuo ambiente (ad es. `~/.aws/credentials` o tramite variabili d’ambiente) in modo che `boto3` possa autenticarsi e invocare Cognito.

### 2.2. Integrare `user_router` in un’app FastAPI

In genere, avrai un file principale, ad esempio `main.py`, che include:

```python
from fastapi import FastAPI
from user import user_router  # Import del router utente

app = FastAPI(
    title="My Cognito App",
    description="API di test con user_router",
    version="1.0.0"
)

app.include_router(user_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Ora, quando esegui `python main.py`, avrai un server in ascolto sulla porta 8000, e gli endpoint del router `user.py` saranno disponibili con prefisso `/v1/user`.

---

## 3. Panoramica degli Endpoint Disponibili

Nel file `user.py`, osserviamo i seguenti endpoint:

1. **`/signup`** (`POST`): Registrazione utente  
2. **`/signin`** (`POST`): Autenticazione utente (flusso `USER_PASSWORD_AUTH`)  
3. **`/verify-token`** (`POST`): Verifica token JWT  
4. **`/confirm-signup-user`** (`POST`): Conferma registrazione tramite codice di conferma  
5. **`/resend-confirmation-code`** (`POST`): Rinvia il codice di conferma  
6. **`/update-attributes`** (`POST`): Aggiorna attributi utente  
7. **`/update-custom-attributes`** (`POST`): Aggiorna attributi customizzati  
8. **`/user-info`** (`POST`): Visualizza informazioni utente  
9. **`/forgot-password`** (`POST`): Avvia il reset password  
10. **`/confirm-forgot-password`** (`POST`): Conferma il reset password con codice  
11. **`/refresh-token`** (`POST`): Rinnova gli Access/Id token usando il `RefreshToken`  
12. **`/change-password`** (`POST`): Cambia la password (senza passare dal flusso forgot)  
13. **`/verify-user-attribute`** (`POST`): Invia un codice per verificare attributi come email/telefono  
14. **`/confirm-user-attribute`** (`POST`): Conferma l’attributo con il codice ricevuto

---

## 4. Utilizzo Step-by-Step di Alcuni Endpoint

Di seguito, una panoramica di come potresti usare questi endpoint in sequenza. Mostriamo solo alcuni esempi chiave:

### 4.1. Registrare un nuovo utente (`/signup`)

```bash
curl -X POST http://localhost:8000/v1/user/signup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "Password123!",
    "email": "testuser@example.com"
  }'
```

- Se Cognito è configurato per **verificare l’email**, l’utente riceverà un codice via email.

### 4.2. Confermare la registrazione (`/confirm-signup-user`)

```bash
curl -X POST http://localhost:8000/v1/user/confirm-signup-user \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "confirmation_code": "123456"
  }'
```

- Questo endpoint usa `confirm_sign_up` dietro le quinte.
- Se la conferma va a buon fine, l’utente è pronto a loggarsi.

### 4.3. Autenticazione (`/signin`)

```bash
curl -X POST http://localhost:8000/v1/user/signin \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "Password123!"
  }'
```

- Se le credenziali sono corrette, Cognito restituirà `AccessToken`, `IdToken`, `RefreshToken`.

### 4.4. Verifica token JWT (`/verify-token`)

Se vuoi controllare la validità di un `AccessToken` (o `IdToken`):

```bash
curl -X POST http://localhost:8000/v1/user/verify-token \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJraWQiOiJ..."
  }'
```

- L’endpoint scarica la chiave pubblica (JWKS) e verifica la firma.

### 4.5. Aggiornare attributi standard (`/update-attributes`)

```bash
curl -X POST http://localhost:8000/v1/user/update-attributes \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJraWQiOi...",
    "attributes": [
      {"Name":"phone_number","Value":"+391234567890"}
    ]
  }'
```

- Cognito aggiornerà `phone_number`. Se è configurato per la verifica, dovrai poi usare `/verify-user-attribute` e `/confirm-user-attribute`.

### 4.6. Verificare attributo (es. phone_number)

1. **`/verify-user-attribute`**: Invia codice di verifica

   ```bash
   curl -X POST http://localhost:8000/v1/user/verify-user-attribute \
   -H "Content-Type: application/json" \
   -d '{
     "access_token": "eyJraWQiOi...",
     "attribute_name": "phone_number"
   }'
   ```

   Cognito invierà un SMS con un codice.

2. **`/confirm-user-attribute`**: Conferma il codice

   ```bash
   curl -X POST http://localhost:8000/v1/user/confirm-user-attribute \
   -H "Content-Type: application/json" \
   -d '{
     "access_token": "eyJraWQiOi...",
     "attribute_name": "phone_number",
     "confirmation_code": "123456"
   }'
   ```

   Se corretto, Cognito setta `phone_number_verified=true`.

### 4.7. Reset password (`/forgot-password` e `/confirm-forgot-password`)

1. **`/forgot-password`**:

   ```bash
   curl -X POST http://localhost:8000/v1/user/forgot-password \
   -H "Content-Type: application/json" \
   -d '{
     "username": "testuser"
   }'
   ```

   Cognito invierà un codice (via email o SMS).

2. **`/confirm-forgot-password`**:

   ```bash
   curl -X POST http://localhost:8000/v1/user/confirm-forgot-password \
   -H "Content-Type: application/json" \
   -d '{
     "username": "testuser",
     "confirmation_code": "123456",
     "new_password": "NuovaPassword2023!"
   }'
   ```

   Se corretto, la password verrà impostata a `NuovaPassword2023!`.

### 4.8. Cambiare password utente autenticato (`/change-password`)

Se l’utente è già autenticato ed ha l’`AccessToken`, può cambiare la password senza passare dal forgot:

```bash
curl -X POST http://localhost:8000/v1/user/change-password \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJraWQiOi...",
    "old_password": "Password123!",
    "new_password": "NewSecret123!"
  }'
```

---

## 5. Considerazioni Avanzate

### 5.1. MFA (Autenticazione a due fattori)

- Il router `user.py`, di base, non implementa endpoint dedicati a **abilitazione/disabilitazione** della MFA (SMS o TOTP). Per quello puoi usare un router aggiuntivo (es. `mfa.py`).  
- **Se la tua User Pool ha** MFA “Required” o “Optional”, potresti dover gestire i challenge MFA in `signin` (Cognito risponderebbe con `"ChallengeName": "SMS_MFA"` o `"SOFTWARE_TOKEN_MFA"`). L’endpoint di base `signin` non gestisce la `respond_to_auth_challenge`, quindi dovresti estendere o creare un endpoint dedicato al challenge.

### 5.2. Device Tracking e Remembered Devices

- Se vuoi **ricordare** i dispositivi per saltare MFA in login futuri, devi **abilitare device tracking** nella console Cognito e usare endpoint come `ConfirmDevice`, `ListDevices`, `UpdateDeviceStatus`. Non sono inclusi nel `user.py` di default, ma potresti aggiungerli in un file dedicato (`device.py`).

### 5.3. Social Login o Federazione

- Se usi Cognito con un **Identity Provider esterno** (Google, Facebook, SAML, ecc.), il flusso di login potrebbe bypassare alcuni endpoint (signup, signin) e delegare la fase di autenticazione all’IdP.  
- In tal caso, molte di queste API (es. `signup`) non verranno usate.

---

## 6. Conclusione e Checklist

1. **Configurazione Cognito**:
   - User Pool correttamente impostata (alias, attributi, email/phone).  
   - App Client con i flussi desiderati (`USER_PASSWORD_AUTH` se user e password diretta).  
   - Credenziali AWS per `boto3`.

2. **File `user.py`**:
   - Importato in `main.py` e connesso via `app.include_router(user_router)`.  
   - Variabili globali (`CLIENT_ID`, `CLIENT_SECRET`, `REGION`, `USER_POOL_ID`) impostate correttamente.

3. **Test**:
   - Prova l’endpoint `/signup` e `/confirm-signup-user`.  
   - Poi `/signin`.  
   - Verifica `/verify-token` e `/user-info`.  
   - Se tutto funziona, l’integrazione con Cognito è corretta.

4. **Estensioni**:  
   - Per MFA → Endpoint aggiuntivi (un file `mfa.py`) dedicati a `enable/disable SMS`, TOTP, e la `respond_to_auth_challenge`.  
   - Per device tracking → Endpoint `confirm_device`, `update_device_status`.

