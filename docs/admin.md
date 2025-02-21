# Guida Dettagliata per la Rotta `admin` (Admin Operations)

## 1. Prerequisiti e Configurazioni Iniziali

### 1.1. Account AWS e Cognito

1. **Account AWS**: Possiedi un account AWS con privilegi sufficiente per creare/modificare una **User Pool**.
2. **User Pool**: Assicurati di avere una **User Pool** in Amazon Cognito. Il codice di esempio fa riferimento a:
   - **REGION** = `eu-north-1`
   - **CLIENT_ID** = `7gp9s0b5nli705a97qik32l1mi`
   - **CLIENT_SECRET** = `4l1nfigk9abonrhkoonqnlo769bbs724ja64j8nqniugmsmf0si`
   - **USER_POOL_ID** = `eu-north-1_0dyOzfzna`

Sostituisci o adatta queste variabili se la tua configurazione è diversa.

### 1.2. App Client e Permessi IAM

- Per le **operazioni amministrative**, il backend deve disporre di permessi IAM adeguati a chiamare le API `admin_confirm_sign_up`, `describe_user_pool`, ecc.
- Verifica che il tuo **IAM Role** o **utente IAM** (usato da `boto3`) abbia le politiche necessarie (es. `AmazonCognitoIdentityProviderFullAccess` o equivalente).

---

## 2. Preparare il File `admin.py` e l’Ambiente

1. **Copia** il contenuto di `admin.py` in un file separato (ad esempio in una cartella `routers/`).
2. **Installa** i pacchetti necessari se non l’hai già fatto:
   ```bash
   pip install fastapi uvicorn boto3 python-jose requests
   ```
3. **Configura** le credenziali AWS (ad es. `~/.aws/credentials`) o variabili d’ambiente per permettere a `boto3` di autenticarsi.

### 2.1. Collegare la rotta `admin` a FastAPI

Nel file principale `main.py`, potresti fare:

```python
from fastapi import FastAPI
from admin import admin_router  # router definito in admin.py

app = FastAPI(
    title="My Cognito Admin App",
    version="1.0.0"
)

app.include_router(admin_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

In questo modo, gli endpoint saranno disponibili con il prefisso `/v1/admin`.

---

## 3. Panoramica degli Endpoint in `admin.py`

1. **`POST /v1/admin/confirm-signup`**  
   - **Operazione**: `admin_confirm_sign_up`.  
   - **Scopo**: Confermare un utente che non ha completato da sé la procedura di conferma (oppure forzare la conferma in caso di disguidi).  
   - **Modello**: `AdminConfirmSignUpRequest`, contenente `username`.

2. **`GET /v1/admin/attribute-schema`**  
   - **Operazione**: `describe_user_pool` (permette di vedere la definizione di `SchemaAttributes` della pool).  
   - **Scopo**: Sapere quali attributi (standard e custom) sono previsti nella User Pool.

3. **`POST /v1/admin/update-attribute-schema`**  
   - **Operazione**: fittizia, perché Cognito **non** supporta la modifica dello schema attributi dopo la creazione.  
   - **Scopo**: Mostrare un esempio di come restituire un errore 501 (`Not Implemented`).

---

## 4. Utilizzo Step-by-Step degli Endpoint Principali

### 4.1. Conferma Utente Amministrativa (`/v1/admin/confirm-signup`)

#### 4.1.1. Quando usarlo

1. Un utente si è **registrato**, ma non ha completato la conferma via email/telefono.  
2. Vuoi forzare la conferma a livello di backend (senza codice di verifica).  
3. L’utente è apparso in Cognito come “UNCONFIRMED” e vuoi convertirlo in “CONFIRMED”.

#### 4.1.2. Esempio di chiamata

```bash
curl -X POST http://localhost:8000/v1/admin/confirm-signup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser"
  }'
```

Se l’utente era in stato “UNCONFIRMED”, l’endpoint userà `admin_confirm_sign_up` per confermarlo. Otterrai una risposta simile:

```json
{
  "message": "User testuser confirmed successfully.",
  "response": {
    ... // struttura di risposta di Cognito
  }
}
```

### 4.2. Visualizzare lo Schema degli Attributi (`/v1/admin/attribute-schema`)

#### 4.2.1. Quando usarlo

1. Vuoi **sapere** quali attributi standard (`email`, `phone_number`, `sub`, ecc.) e quali attributi custom (`custom:department`, `custom:role`, ecc.) sono definiti nel tuo User Pool.
2. Necessario se stai sviluppando un **frontend** che mostra/gestisce gli attributi di un utente e devi sapere quali campi esistono.

#### 4.2.2. Esempio di chiamata

```bash
curl -X GET http://localhost:8000/v1/admin/attribute-schema
```

**Possibile risposta**:

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

In questo modo sai che la tua User Pool accetta, ad esempio, `custom:department`.

### 4.3. Modifica dello Schema (`/v1/admin/update-attribute-schema`)

- Cognito **non permette** di modificare (`add`, `remove` o `rename`) gli attributi dopo che la User Pool è stata creata.
- Questo endpoint restituisce un errore 501 (`Not Implemented`) per chiarire che non è supportato.

**Esempio**:

```bash
curl -X POST http://localhost:8000/v1/admin/update-attribute-schema
```
Risposta:
```json
{
  "detail": "Modifica dello schema degli attributi non è supportata da Cognito dopo la creazione del pool."
}
```

---

## 5. Considerazioni su Permessi e Sicurezza

1. **`admin_confirm_sign_up`**: L’API Cognito per confermare un utente in modo amministrativo **richiede** i permessi IAM appropriati. Se la tua applicazione backend usa credenziali con accesso limitato, potresti ricevere un errore `AccessDenied`.
2. **Sicurezza**: Questi endpoint danno **poteri amministrativi** (come confermare un utente). Assicurati di proteggere `/v1/admin/...` con un meccanismo di autorizzazione (es. token admin, ruoli, o un ACL esterno).

---

## 6. Estensioni Possibili

1. **Altri endpoint Admin**: Cognito fornisce operazioni come `admin_disable_user`, `admin_delete_user`, `admin_set_user_password`. Potresti aggiungerle, seguendo lo stesso schema (creare un Pydantic model e un endpoint che chiama la corrispondente API Cognito).
2. **Listare utenti**: `admin_list_users` o `list_users`, se vuoi mostrare e gestire la lista di account in modo amministrativo.
3. **Gestione attributi su utenti**: `admin_update_user_attributes` o `admin_get_user` (se vuoi leggere/aggiornare attributi di un utente da backend, bypassando le logiche self-service).

---

## 7. Esempio di Flusso Admin

- **Scenario**: Un utente si registra ma non conferma l’account. Compare in Cognito come “UNCONFIRMED”.
- **Operazione**: Un admin (o un tool di backoffice) richiama l’endpoint `/v1/admin/confirm-signup`:
  ```bash
  curl -X POST http://localhost:8000/v1/admin/confirm-signup \
    -H "Content-Type: application/json" \
    -d '{"username":"testuser"}'
  ```
- **Risultato**: L’utente `testuser` passa a stato “CONFIRMED” senza inserire codice di verifica. Può quindi fare login.
- **Verifica**: Potresti utilizzare la console Cognito o `/v1/user/signin` per testare se `testuser` è ora autenticabile.

---

## 8. Conclusione e Checklist

1. **Configurazione**: Hai impostato i parametri (`REGION`, `USER_POOL_ID`, `CLIENT_ID`, `CLIENT_SECRET`) correttamente?  
2. **IAM e permessi**: L’utente/ruolo che esegue `admin_confirm_sign_up`, `describe_user_pool`, ecc. possiede i permessi necessari?  
3. **Protezione**: Stai proteggendo gli endpoint admin con un meccanismo di autenticazione e autorizzazione adeguato?  
4. **Estensioni**: Se necessiti di altre operazioni admin (abilitare/disabilitare utente, cancellarlo, ecc.), aggiungi endpoint simili seguendo il pattern riportato.

