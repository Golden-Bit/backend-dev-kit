Di seguito trovi una **documentazione dettagliata e professionale** per l'API FastAPI che integra Amazon Cognito per la gestione degli utenti. La documentazione include:

1. **Descrizione generale dell’API**  
2. **Schemi dei modelli di input**  
3. **Endpoint disponibili**, con dettagli su parametri, corpi delle richieste, risposte e possibili errori  
4. **Esempi pratici** di utilizzo tramite chiamate HTTP (ad esempio con `curl` o tool come Postman).

---

# **Cognito Authentication API** 

**Descrizione**  
Questa API permette di gestire le operazioni di autenticazione e autorizzazione degli utenti tramite Amazon Cognito, fornendo endpoints per:  
- Registrazione (Sign-up)  
- Autenticazione (Sign-in)  
- Verifica token JWT  
- Conferma della registrazione (da parte dell’utente o di un amministratore)  
- Invio di un nuovo codice di conferma  
- Aggiornamento attributi, inclusi attributi custom  
- Visualizzazione di informazioni utente  
- Visualizzazione dello schema di attributi della User Pool  

**Base URL**  
Se l’API è eseguita in locale sulla porta 8000, l’indirizzo di base è:  
```
http://localhost:8000
```

**Autore**  
- *[Inserisci il tuo nome o quello dell’organizzazione]*

---

## **1. Schemi dei modelli di input**

### **1.1. SignUpRequest**

```python
class SignUpRequest(BaseModel):
    username: str
    password: str
    email: str
```

**Descrizione**  
- **username**: Nome utente scelto.  
- **password**: Password dell’utente.  
- **email**: Indirizzo email dell’utente.  

**Esempio di body (JSON)**  
```json
{
  "username": "testuser",
  "password": "Password123!",
  "email": "testuser@example.com"
}
```

---

### **1.2. SignInRequest**

```python
class SignInRequest(BaseModel):
    username: str
    password: str
```

**Descrizione**  
- **username**: Nome utente (non necessariamente l’email, a meno che non sia stato configurato come alias).  
- **password**: Password dell’utente.  

**Esempio di body (JSON)**  
```json
{
  "username": "testuser",
  "password": "Password123!"
}
```

---

### **1.3. ConfirmSignUpRequest**

```python
class ConfirmSignUpRequest(BaseModel):
    username: str
    confirmation_code: str
```

**Descrizione**  
- **username**: Nome utente da confermare.  
- **confirmation_code**: Codice di conferma inviato via email/SMS da Cognito.  

**Esempio di body (JSON)**  
```json
{
  "username": "testuser",
  "confirmation_code": "123456"
}
```

---

### **1.4. AdminConfirmSignUpRequest**

```python
class AdminConfirmSignUpRequest(BaseModel):
    username: str
```

**Descrizione**  
- **username**: Nome utente da confermare tramite operazione amministrativa (non necessita di codice di conferma).  

**Esempio di body (JSON)**  
```json
{
  "username": "testuser"
}
```

---

### **1.5. ResendConfirmationCodeRequest**

```python
class ResendConfirmationCodeRequest(BaseModel):
    username: str
```

**Descrizione**  
- **username**: Nome utente per cui inviare nuovamente il codice di conferma.  

**Esempio di body (JSON)**  
```json
{
  "username": "testuser"
}
```

---

### **1.6. UserAttribute**

```python
class UserAttribute(BaseModel):
    Name: str
    Value: str
```

**Descrizione**  
- **Name**: Nome dell’attributo (es. `email`, `phone_number` o `custom:department` se custom).  
- **Value**: Valore dell’attributo.  

**Esempio di body (JSON)**  
```json
{
  "Name": "custom:department",
  "Value": "IT"
}
```

---

### **1.7. UpdateAttributesRequest**

```python
class UpdateAttributesRequest(BaseModel):
    access_token: str
    attributes: List[UserAttribute]
```

**Descrizione**  
- **access_token**: Token di accesso dell’utente, ottenuto dopo il login.  
- **attributes**: Lista di attributi da aggiornare.  

**Esempio di body (JSON)**  
```json
{
  "access_token": "eyJraWQiOiJr... (omissis)",
  "attributes": [
    {
      "Name": "custom:department",
      "Value": "IT"
    },
    {
      "Name": "custom:role",
      "Value": "Manager"
    }
  ]
}
```

---

### **1.8. UpdateCustomAttributesRequest**

```python
class UpdateCustomAttributesRequest(BaseModel):
    access_token: str
    custom_attributes: Dict[str, str]
```

**Descrizione**  
- **access_token**: Token di accesso dell’utente.  
- **custom_attributes**: Un dizionario `<nome_attributo>: <valore>` dove il nome dell’attributo include il prefisso `custom:`.  

**Esempio di body (JSON)**  
```json
{
  "access_token": "eyJraWQiOiJr... (omissis)",
  "custom_attributes": {
    "custom:department": "Marketing",
    "custom:role": "Manager"
  }
}
```

---

### **1.9. AccessTokenRequest**

```python
class AccessTokenRequest(BaseModel):
    access_token: str
```

**Descrizione**  
- **access_token**: Token di accesso dell’utente (JWT) fornito dopo l’autenticazione.  

**Esempio di body (JSON)**  
```json
{
  "access_token": "eyJraWQiOiJr... (omissis)"
}
```

---

## **2. Endpoint dell’API**

### **2.1. POST `/signup`**

**Descrizione**  
Registra un nuovo utente in Amazon Cognito. Se l’email è configurata come attributo di verifica, l’utente riceverà un codice di conferma.

- **Body**: `SignUpRequest`
- **Risposta**: JSON con il risultato dell’operazione di Cognito.

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/signup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "Password123!",
    "email": "testuser@example.com"
  }'
```

---

### **2.2. POST `/signin`**

**Descrizione**  
Autentica un utente mediante il flusso `USER_PASSWORD_AUTH`.

- **Body**: `SignInRequest`
- **Risposta**: JSON con i token di accesso (AccessToken, IdToken, RefreshToken).

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/signin \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "Password123!"
  }'
```

**Risposta (esempio)**  
```json
{
  "AuthenticationResult": {
    "AccessToken": "...",
    "ExpiresIn": 3600,
    "IdToken": "...",
    "RefreshToken": "...",
    "TokenType": "Bearer"
  }
}
```

---

### **2.3. POST `/verify-token`**

**Descrizione**  
Verifica e decodifica il token JWT emesso da Cognito. Scarica la chiave pubblica (JWKS) corrispondente e valida la firma.

- **Body**: `AccessTokenRequest`
- **Risposta**: JSON contenente il token decodificato (se valido).

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/verify-token \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJraWQiOiJr..."
  }'
```

---

### **2.4. POST `/confirm-signup` (Admin)**

**Descrizione**  
Conferma la registrazione di un utente mediante operazione amministrativa (non richiede codice di conferma).

- **Body**: `AdminConfirmSignUpRequest`
- **Risposta**: JSON con messaggio di conferma.

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/confirm-signup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser"
  }'
```

---

### **2.5. POST `/confirm-signup-user`**

**Descrizione**  
Conferma la registrazione di un utente usando il codice di conferma inviato via email.

- **Body**: `ConfirmSignUpRequest`
- **Risposta**: JSON con il risultato dell’operazione di Cognito.

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/confirm-signup-user \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "confirmation_code": "123456"
  }'
```

---

### **2.6. POST `/resend-confirmation-code`**

**Descrizione**  
Invia nuovamente il codice di conferma all’utente, utile se l’utente non ha ricevuto la prima email o SMS.

- **Body**: `ResendConfirmationCodeRequest`
- **Risposta**: JSON con il risultato dell’operazione di Cognito.

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/resend-confirmation-code \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser"
  }'
```

---

### **2.7. POST `/update-attributes`**

**Descrizione**  
Aggiorna gli attributi di un utente già autenticato. Richiede l’`AccessToken` e la lista di attributi da modificare.

- **Body**: `UpdateAttributesRequest`
- **Risposta**: JSON con il risultato dell’operazione di Cognito.

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/update-attributes \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJraWQiOiJr... (omissis)",
    "attributes": [
      {
        "Name": "custom:department",
        "Value": "IT"
      }
    ]
  }'
```

---

### **2.8. POST `/update-custom-attributes`**

**Descrizione**  
Aggiorna attributi personalizzati (`custom:`) di un utente già autenticato.  
**Nota bene**: Gli attributi custom devono essere definiti in Cognito in fase di configurazione del pool.

- **Body**: `UpdateCustomAttributesRequest`
- **Risposta**: JSON con il risultato dell’operazione di Cognito.

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/update-custom-attributes \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJraWQiOiJr... (omissis)",
    "custom_attributes": {
      "custom:department": "Marketing",
      "custom:role": "Manager"
    }
  }'
```

---

### **2.9. POST `/user-info`**

**Descrizione**  
Recupera tutte le informazioni dell’utente (attributi standard e custom) tramite l’`AccessToken`.

- **Body**: `AccessTokenRequest`
- **Risposta**: JSON contenente gli attributi dell’utente.

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/user-info \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJraWQiOiJr... (omissis)"
  }'
```

**Esempio di risposta (parziale)**  
```json
{
  "Username": "eu-north-1_xxxxxxx:testuser",
  "UserAttributes": [
    {
      "Name": "sub",
      "Value": "e18afc6d-xxxx-xxxx-xxxx-xxxxxxxxxx"
    },
    {
      "Name": "email_verified",
      "Value": "true"
    },
    {
      "Name": "email",
      "Value": "testuser@example.com"
    },
    {
      "Name": "custom:department",
      "Value": "IT"
    }
  ]
}
```

---

### **2.10. GET `/attribute-schema`**

**Descrizione**  
Restituisce lo schema corrente degli attributi definiti nel User Pool (sia standard che custom).

- **Nessun body** richiesto.  
- **Risposta**: JSON contenente un array di attributi (nome, tipo, ecc.).

**Esempio di chiamata**:

```bash
curl -X GET http://localhost:8000/attribute-schema
```

**Esempio di risposta (semplificato)**  
```json
[
  {
    "Name": "sub",
    "AttributeDataType": "String",
    "DeveloperOnlyAttribute": false,
    "Mutable": false,
    "Required": true
  },
  {
    "Name": "email",
    "AttributeDataType": "String",
    "DeveloperOnlyAttribute": false,
    "Mutable": true,
    "Required": false
  },
  {
    "Name": "custom:department",
    "AttributeDataType": "String",
    "DeveloperOnlyAttribute": false,
    "Mutable": true,
    "Required": false
  }
]
```

---

### **2.11. POST `/update-attribute-schema`**

**Descrizione**  
Endpoint di esempio per tentare la modifica dello schema attributi. **Non supportato** da Cognito. Restituisce un errore 501.

**Esempio di chiamata**:

```bash
curl -X POST http://localhost:8000/update-attribute-schema
```

**Risposta**  
```json
{
  "detail": "Modifica dello schema degli attributi non è supportata da Cognito dopo la creazione del pool."
}
```
---

## **3. Considerazioni su Sicurezza e Configurazione**

1. **Credenziali AWS**  
   - Assicurati di configurare correttamente `~/.aws/credentials` o usare variabili d’ambiente/ruoli IAM.
2. **Client Secret**  
   - Qui viene usato `CLIENT_SECRET`. Se non vuoi calcolare il `SecretHash`, puoi disabilitarlo nelle impostazioni del tuo App Client Cognito.
3. **Email univoca**  
   - Se vuoi impedire la registrazione di più utenti con la stessa email, imposta l’email come alias univoco nella sezione “Attributes” del tuo User Pool.
4. **Token e Sicurezza**  
   - I token JWT (Access/IdToken) devono essere gestiti con cura: non esporli in contesti non sicuri e verifica sempre la loro validità e firma.
5. **Conferma dell’utente**  
   - Se un utente non è confermato, non potrà autenticarsi correttamente. Utilizza gli endpoint `/confirm-signup-user` o `/confirm-signup` (admin) per completare il processo.

---

## **4. Setup e Avvio dell’Applicazione**

1. **Installazione dipendenze**  
   ```bash
   pip install fastapi uvicorn boto3 python-jose requests
   ```
2. **Avvio del server**  
   ```bash
   uvicorn main:app --reload
   ```
3. **Accesso alla documentazione Swagger**  
   - Apri `http://localhost:8000/docs` per visualizzare e testare gli endpoint in modo interattivo.

---

## **5. Errori Comuni**

- **`NotAuthorizedException: Client is configured with secret but SECRET_HASH was not received`**  
  Significa che il client Cognito richiede il `SecretHash` ma non è stato inviato. Assicurati di calcolarlo con la funzione `get_secret_hash`.
  
- **`UserNotConfirmedException: User is not confirmed`**  
  L’utente ha completato la registrazione ma non la conferma. Usa `/confirm-signup-user` o `/confirm-signup` (admin) per confermare.

- **`InvalidParameterException: USER_PASSWORD_AUTH flow not enabled for this client`**  
  Nel tuo App Client di Cognito devi abilitare il flusso **`USER_PASSWORD_AUTH`**.

- **`Cannot modify schema attributes`**  
  Cognito non permette la modifica dello schema degli attributi (aggiunta, rimozione o modifica di quelli esistenti) una volta creata la User Pool.

---

## **6. Esempio di Flusso Completo**

**Scenario**: Voglio creare un utente, confermarlo e poi permettergli di autenticarsi e aggiornare attributi custom.

1. **Signup**  
   ```bash
   curl -X POST http://localhost:8000/signup \
     -H "Content-Type: application/json" \
     -d '{
       "username": "testuser",
       "password": "Password123!",
       "email": "testuser@example.com"
     }'
   ```

2. **Conferma (utente)**  
   - L’utente riceverà un codice via email (es. `123456`).  
   - Conferma con:
     ```bash
     curl -X POST http://localhost:8000/confirm-signup-user \
       -H "Content-Type: application/json" \
       -d '{
         "username": "testuser",
         "confirmation_code": "123456"
       }'
     ```

3. **Sign-in**  
   ```bash
   curl -X POST http://localhost:8000/signin \
     -H "Content-Type: application/json" \
     -d '{
       "username": "testuser",
       "password": "Password123!"
     }'
   ```
   - Riceverai `AccessToken`, `IdToken`, `RefreshToken`.

4. **Aggiorna Attributi Custom** (opzionale)  
   ```bash
   curl -X POST http://localhost:8000/update-custom-attributes \
     -H "Content-Type: application/json" \
     -d '{
       "access_token": "eyJraWQiOiJr... (omissis)",
       "custom_attributes": {
         "custom:department": "Marketing"
       }
     }'
   ```

5. **Visualizza Informazioni Utente**  
   ```bash
   curl -X POST http://localhost:8000/user-info \
     -H "Content-Type: application/json" \
     -d '{
       "access_token": "eyJraWQiOiJr... (omissis)"
     }'
   ```

---

## **7. Conclusioni**

Questa API copre i principali casi d’uso di **Cognito** per la gestione degli utenti in un contesto server-to-server (con secret) e fornisce endpoint chiari per:

- Registrazione e autenticazione
- Conferma manuale e via codice
- Aggiornamento attributi standard e custom
- Verifica e decodifica del token JWT
- Visualizzazione dello schema attuale del User Pool

Se desideri estendere l’API con **funzioni avanzate** come il reset password, il social login o l’integrazione con i flussi OAuth2, potrai sfruttare ulteriori operazioni di Cognito (ad esempio [`forgot_password`, `confirm_forgot_password`, ecc.]) e aggiungere endpoint simili a quelli già mostrati. 

Inoltre, per una maggior sicurezza e scalabilità, è consigliabile:

- **Proteggere** gli endpoint sensibili con un sistema di autorizzazione basato sui token JWT verificati.  
- **Utilizzare** ruoli IAM e politiche gestite per minimizzare i rischi derivanti dalla gestione delle credenziali AWS.  
- **Monitorare** i log e l’uso degli endpoint tramite servizi come **Amazon CloudWatch** o tool di observability dedicati.

Con questo hai una panoramica completa e professionale dell’API, pronta per essere integrata in un progetto più ampio. Buon sviluppo!