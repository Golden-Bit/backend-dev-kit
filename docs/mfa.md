# Guida: Abilitare MFA in Cognito e ricordare i dispositivi

## 1. Configurazione iniziale

### 1.1. Creare o identificare la User Pool

1.  Accedi alla [Console AWS](https://console.aws.amazon.com/) e cerca **Amazon Cognito**.
2.  Se hai già una **User Pool**, selezionala; altrimenti, crea una nuova pool (`Create user pool`) e segui la procedura guidata.

### 1.2. Configurare attributi obbligatori

1.  Vai su **Attributes**.
2.  Se vuoi usare **SMS MFA**, assicurati di avere `phone_number` come attributo (non necessariamente obbligatorio, ma devi consentire l’inserimento).
3.  Se vuoi usare **TOTP MFA**, non c’è un attributo extra richiesto. Basta che la pool supporti la funzionalità TOTP (abilitata in “MFA and verifications”).

### 1.3. Impostare la verifica email/telefono (opzionale, ma consigliato)

1.  Su **MFA and verifications**, puoi scegliere come Cognito verificherà email o phone_number.
2.  Se prevedi l’uso di **SMS MFA**, probabilmente vorrai anche poter verificare i numeri di telefono.

----------

## 2. Abilitare MFA

### 2.1. Selezionare la modalità MFA

1.  Nella User Pool, vai in **“MFA and verifications”** (o **“Multi-factor authentication (MFA)”** in base all’interfaccia attuale).
2.  Hai alcune opzioni:
    -   **Off**: MFA disattivata
    -   **Optional**: L’utente può scegliere se abilitare MFA.
    -   **Required**: Tutti gli utenti devono avere MFA. (Richiede di definire almeno un metodo SMS/TOTP)
3.  Seleziona **“Optional”** se vuoi dare all’utente la possibilità di attivare MFA (via SMS o TOTP) solo quando lo desidera.  
    Se scegli **“Required”**, dovrai assicurarti che tutti abbiano un numero di telefono o TOTP configurato.

### 2.2. Abilitare SMS MFA e/o TOTP

1.  Nel riquadro “MFA configuration”, puoi selezionare:
    -   **SMS**: Cognito userà SMS per inviare il codice
    -   **TOTP (Time-based One-Time Password)**: Cognito genererà un secret key base32 per app come Google Authenticator
    -   **Entrambe**: L’utente può decidere quale metodo preferisce.
2.  **Salva** le modifiche.

#### Nota sulle politiche SMS

Se usi SMS MFA, assicurati di avere i **limiti di invio SMS** corretti in AWS, oppure potresti dover configurare Amazon SNS (o un servizio di messaggistica) con un adeguato piano di invio.

----------

## 3. Abilitare il “Device Tracking” (Remembered Devices)

### 3.1. Sezione Device

1.  Sempre nella console Cognito, nella pagina di configurazione della User Pool, cerca la sezione **“Devices”** o **“Device Tracking”**.
2.  Abilita **“Remember Devices”**.
    -   Potresti vedere opzioni come “User Opt-in” (l’utente sceglie se ricordare il dispositivo) o “Always” (i dispositivi vengono sempre ricordati).
3.  Abilita **“Device remembering”** e seleziona la modalità preferita.

### 3.2. Capire come funziona il Device Tracking

1.  Quando un utente effettua il login, Cognito può assegnare un **Device Key** univoco al dispositivo.
2.  Se la pool richiede o consente il tracking, dopo il login, l’app può chiamare l’API **`ConfirmDevice`** per marcare il dispositivo come “confirmed” e “remembered”.
3.  Nei login successivi da quello stesso device, Cognito può decidere di **saltare** la MFA se il dispositivo è riconosciuto e “Trusted” (remembered).

----------

## 4. Implementazione Lato Codice

### 4.1. Passi comuni: SignIn & Challenge

1.  **SignIn** (via `initiate_auth` con `AuthFlow="USER_PASSWORD_AUTH"`).
    
    -   Se l’utente ha **MFA abilitata** e “Required”, Cognito potrebbe rispondere con una **challenge** (`SMS_MFA` o `SOFTWARE_TOKEN_MFA`).
    -   Se il dispositivo è **già ricordato** e l’utente non ha chiesto di forzare MFA, Cognito potrebbe **non** richiedere la challenge.
2.  **RespondToAuthChallenge**:
    
    -   Se c’è una challenge MFA, l’utente inserisce il codice (SMS/TOTP) e tu chiami l’API `respond_to_auth_challenge`, specificando `ChallengeName`, `Session` e il codice.
    -   Cognito risponde con i token finali (`AccessToken`, `IdToken`, `RefreshToken`) se il codice è corretto.
3.  **DeviceKey**:
    
    -   Se la User Pool ha **device tracking** abilitato, Cognito può includere un **DeviceKey** nella risposta (oppure passare la `ChallengeName` = `DEVICE_SRP_AUTH` in alcuni flussi SRP).
    -   Una volta ottenuti i token + `DeviceKey`, l’app può chiamare `ConfirmDevice`.

### 4.2. Chiamata `ConfirmDevice`

Con un endpoint custom, ad esempio:

```python
@app.post("/v1/user/device/confirm-device")
def confirm_device(request_data: ConfirmDeviceRequest):
    """
    Conferma il dispositivo corrente, marcandolo come 'trusted/remembered' in Cognito.
    """
    response = cognito_client.confirm_device(
        AccessToken=request_data.access_token,
        DeviceKey=request_data.device_key,
        DeviceName=request_data.device_name
    )
    return {"message": "Dispositivo confermato e ricordato.", "response": response}

```

-   **device_key**: di solito estratto da un `respond_to_auth_challenge` o un `initiate_auth` con `DEVICE_SRP_AUTH`.
-   Una volta confermato, Cognito “ricorda” quel device.

### 4.3. “Remembered” o “NotRemembered”

Potresti aggiungere un endpoint per **`update_device_status`**:

```python
@app.post("/v1/user/device/update-device-status")
def update_device_status(request_data: UpdateDeviceStatusRequest):
    """
    Cambia lo stato di un dispositivo (remembered/not_remembered).
    """
    response = cognito_client.update_device_status(
        AccessToken=request_data.access_token,
        DeviceKey=request_data.device_key,
        DeviceRememberedStatus="remembered" if request_data.remember_device else "not_remembered"
    )
    return {"message": "Stato del dispositivo aggiornato.", "response": response}

```

-   In questo modo, l’utente può decidere di non ricordare più un certo device.

----------

## 5. Comportamento finale

Quando la **MFA** è configurata e **Device Tracking** è attivo:

1.  **Primo login** da un dispositivo sconosciuto:
    -   Cognito chiederà la MFA (se abilitata/required).
    -   L’utente fornisce il codice.
    -   Successivamente, se abilitato, Cognito può assegnare un `DeviceKey`.
    -   L’app può chiamare `confirm_device` per ricordarlo.
2.  **Login successivi** dallo stesso dispositivo ricordato:
    -   Cognito rileverà il `DeviceKey` associato (in determinati flussi SRP, o tramite i token aggiornati).
    -   Se è trusted, **non chiederà MFA** (a meno che l’utente o l’admin non modifichino le impostazioni).
3.  **Login da un nuovo dispositivo**:
    -   Cognito non riconoscerà quel device.
    -   Chiederà di nuovo la MFA.
    -   Se l’utente preferisce, potrà confermare e ricordare anche quel device.

----------

## 6. Verifiche e Best Practices

1.  **Verificare** che `phone_number` sia effettivamente `verified`:
    -   Se `phone_number` non è verificato, non potrà essere usato per SMS MFA.
2.  **Gestione dei costi SMS**:
    -   Se SMS MFA viene usato spesso, potresti incorrere in costi (Amazon SNS). Considera TOTP come alternativa a costo zero.
3.  **Sessioni prolungate**:
    -   Se imposti un tempo di scadenza lungo per `RefreshToken`, l’utente farà il login meno spesso, e quindi meno richieste MFA.
4.  **Social Login** o identità federate:
    -   Se usi Cognito per l’autenticazione federata, verifica la compatibilità con i provider esterni. L’MFA Cognito si applica solo se l’utente è “nativo” della pool, non se arriva da un IdP esterno che già gestisce MFA (es. Google, Facebook).
5.  **Sicurezza**:
    -   Non “ricordare” dispositivi pubblici/insicuri. L’utente deve confermare solo quelli personali.

----------

## 7. Riepilogo Step-by-Step

1.  **Nella tua User Pool**:
    
    -   **Abilita** MFA “Optional” o “Required”.
    -   Seleziona i metodi (SMS e/o TOTP).
    -   **Abilita** Device Tracking: “Always” o “User Opt-in”.
2.  **Nel tuo Backend**:
    
    -   Implementa endpoint per:
        1.  **Login** (`initiate_auth`, `respond_to_auth_challenge` se serve).
        2.  **MFA**:
            -   **Enable/Disable** MFA (facoltativo se “Optional”).
            -   **SMS**: Abilita se telefono verificato.
            -   **TOTP**: `associate_software_token`, `verify_software_token`, `set_user_mfa_preference`.
        3.  **Device**:
            -   `confirm_device` (per ricordare il dispositivo).
            -   `update_device_status` (passare da remembered a not_remembered e viceversa).
3.  **Test**:
    
    -   Effettua un login da un device **non ricordato** → Vedi se Cognito chiede MFA.
    -   **Registra** il device con `confirm_device`.
    -   Ripeti il login → Verifica che **non** chieda MFA.
4.  **Consegna all’utente**:
    
    -   Un flusso intuitivo dove, dopo il primo login (con MFA), l’app chiede “Vuoi ricordare questo dispositivo?”.
    -   Invia la chiamata `confirm_device`.
    -   Da lì in poi, l’utente salta MFA su quello stesso device.

----------

## 8. Conclusione

1.  **Abilitare MFA** in Cognito → Permette di aggiungere SMS o TOTP per un ulteriore livello di sicurezza.
2.  **Device Tracking** → **Salta** MFA nei login successivi da dispositivi “fidati”.
3.  **Risultato**: Esperienza utente bilanciata tra sicurezza e frizione — MFA solo su nuovi dispositivi o se l’utente sceglie di non ricordarli.

Con questi step, la tua **implementazione MFA** in Amazon Cognito sarà **completa** e **potenziata** dal device tracking, consentendo un flusso di autenticazione robusto e allo stesso tempo comodo per gli utenti.Di seguito trovi una **guida estremamente dettagliata** per abilitare l’autenticazione a più fattori (MFA) in Amazon Cognito e, contemporaneamente, configurare il tracciamento e la memorizzazione dei dispositivi (device tracking). L’obiettivo è **richiedere MFA** agli utenti **solo la prima volta** che accedono da un nuovo dispositivo e, in caso di dispositivi già “fidati”, **saltare** la richiesta MFA.

----------

# Guida: Abilitare MFA in Cognito e ricordare i dispositivi

## 1. Configurazione iniziale

### 1.1. Creare o identificare la User Pool

1.  Accedi alla [Console AWS](https://console.aws.amazon.com/) e cerca **Amazon Cognito**.
2.  Se hai già una **User Pool**, selezionala; altrimenti, crea una nuova pool (`Create user pool`) e segui la procedura guidata.

### 1.2. Configurare attributi obbligatori

1.  Vai su **Attributes**.
2.  Se vuoi usare **SMS MFA**, assicurati di avere `phone_number` come attributo (non necessariamente obbligatorio, ma devi consentire l’inserimento).
3.  Se vuoi usare **TOTP MFA**, non c’è un attributo extra richiesto. Basta che la pool supporti la funzionalità TOTP (abilitata in “MFA and verifications”).

### 1.3. Impostare la verifica email/telefono (opzionale, ma consigliato)

1.  Su **MFA and verifications**, puoi scegliere come Cognito verificherà email o phone_number.
2.  Se prevedi l’uso di **SMS MFA**, probabilmente vorrai anche poter verificare i numeri di telefono.

----------

## 2. Abilitare MFA

### 2.1. Selezionare la modalità MFA

1.  Nella User Pool, vai in **“MFA and verifications”** (o **“Multi-factor authentication (MFA)”** in base all’interfaccia attuale).
2.  Hai alcune opzioni:
    -   **Off**: MFA disattivata
    -   **Optional**: L’utente può scegliere se abilitare MFA.
    -   **Required**: Tutti gli utenti devono avere MFA. (Richiede di definire almeno un metodo SMS/TOTP)
3.  Seleziona **“Optional”** se vuoi dare all’utente la possibilità di attivare MFA (via SMS o TOTP) solo quando lo desidera.  
    Se scegli **“Required”**, dovrai assicurarti che tutti abbiano un numero di telefono o TOTP configurato.

### 2.2. Abilitare SMS MFA e/o TOTP

1.  Nel riquadro “MFA configuration”, puoi selezionare:
    -   **SMS**: Cognito userà SMS per inviare il codice
    -   **TOTP (Time-based One-Time Password)**: Cognito genererà un secret key base32 per app come Google Authenticator
    -   **Entrambe**: L’utente può decidere quale metodo preferisce.
2.  **Salva** le modifiche.

#### Nota sulle politiche SMS

Se usi SMS MFA, assicurati di avere i **limiti di invio SMS** corretti in AWS, oppure potresti dover configurare Amazon SNS (o un servizio di messaggistica) con un adeguato piano di invio.

----------

## 3. Abilitare il “Device Tracking” (Remembered Devices)

### 3.1. Sezione Device

1.  Sempre nella console Cognito, nella pagina di configurazione della User Pool, cerca la sezione **“Devices”** o **“Device Tracking”**.
2.  Abilita **“Remember Devices”**.
    -   Potresti vedere opzioni come “User Opt-in” (l’utente sceglie se ricordare il dispositivo) o “Always” (i dispositivi vengono sempre ricordati).
3.  Abilita **“Device remembering”** e seleziona la modalità preferita.

### 3.2. Capire come funziona il Device Tracking

1.  Quando un utente effettua il login, Cognito può assegnare un **Device Key** univoco al dispositivo.
2.  Se la pool richiede o consente il tracking, dopo il login, l’app può chiamare l’API **`ConfirmDevice`** per marcare il dispositivo come “confirmed” e “remembered”.
3.  Nei login successivi da quello stesso device, Cognito può decidere di **saltare** la MFA se il dispositivo è riconosciuto e “Trusted” (remembered).

----------

## 4. Implementazione Lato Codice

### 4.1. Passi comuni: SignIn & Challenge

1.  **SignIn** (via `initiate_auth` con `AuthFlow="USER_PASSWORD_AUTH"`).
    
    -   Se l’utente ha **MFA abilitata** e “Required”, Cognito potrebbe rispondere con una **challenge** (`SMS_MFA` o `SOFTWARE_TOKEN_MFA`).
    -   Se il dispositivo è **già ricordato** e l’utente non ha chiesto di forzare MFA, Cognito potrebbe **non** richiedere la challenge.
2.  **RespondToAuthChallenge**:
    
    -   Se c’è una challenge MFA, l’utente inserisce il codice (SMS/TOTP) e tu chiami l’API `respond_to_auth_challenge`, specificando `ChallengeName`, `Session` e il codice.
    -   Cognito risponde con i token finali (`AccessToken`, `IdToken`, `RefreshToken`) se il codice è corretto.
3.  **DeviceKey**:
    
    -   Se la User Pool ha **device tracking** abilitato, Cognito può includere un **DeviceKey** nella risposta (oppure passare la `ChallengeName` = `DEVICE_SRP_AUTH` in alcuni flussi SRP).
    -   Una volta ottenuti i token + `DeviceKey`, l’app può chiamare `ConfirmDevice`.

### 4.2. Chiamata `ConfirmDevice`

Con un endpoint custom, ad esempio:

```python
@app.post("/v1/user/device/confirm-device")
def confirm_device(request_data: ConfirmDeviceRequest):
    """
    Conferma il dispositivo corrente, marcandolo come 'trusted/remembered' in Cognito.
    """
    response = cognito_client.confirm_device(
        AccessToken=request_data.access_token,
        DeviceKey=request_data.device_key,
        DeviceName=request_data.device_name
    )
    return {"message": "Dispositivo confermato e ricordato.", "response": response}

```

-   **device_key**: di solito estratto da un `respond_to_auth_challenge` o un `initiate_auth` con `DEVICE_SRP_AUTH`.
-   Una volta confermato, Cognito “ricorda” quel device.

### 4.3. “Remembered” o “NotRemembered”

Potresti aggiungere un endpoint per **`update_device_status`**:

```python
@app.post("/v1/user/device/update-device-status")
def update_device_status(request_data: UpdateDeviceStatusRequest):
    """
    Cambia lo stato di un dispositivo (remembered/not_remembered).
    """
    response = cognito_client.update_device_status(
        AccessToken=request_data.access_token,
        DeviceKey=request_data.device_key,
        DeviceRememberedStatus="remembered" if request_data.remember_device else "not_remembered"
    )
    return {"message": "Stato del dispositivo aggiornato.", "response": response}

```

-   In questo modo, l’utente può decidere di non ricordare più un certo device.

----------

## 5. Comportamento finale

Quando la **MFA** è configurata e **Device Tracking** è attivo:

1.  **Primo login** da un dispositivo sconosciuto:
    -   Cognito chiederà la MFA (se abilitata/required).
    -   L’utente fornisce il codice.
    -   Successivamente, se abilitato, Cognito può assegnare un `DeviceKey`.
    -   L’app può chiamare `confirm_device` per ricordarlo.
2.  **Login successivi** dallo stesso dispositivo ricordato:
    -   Cognito rileverà il `DeviceKey` associato (in determinati flussi SRP, o tramite i token aggiornati).
    -   Se è trusted, **non chiederà MFA** (a meno che l’utente o l’admin non modifichino le impostazioni).
3.  **Login da un nuovo dispositivo**:
    -   Cognito non riconoscerà quel device.
    -   Chiederà di nuovo la MFA.
    -   Se l’utente preferisce, potrà confermare e ricordare anche quel device.

----------

## 6. Verifiche e Best Practices

1.  **Verificare** che `phone_number` sia effettivamente `verified`:
    -   Se `phone_number` non è verificato, non potrà essere usato per SMS MFA.
2.  **Gestione dei costi SMS**:
    -   Se SMS MFA viene usato spesso, potresti incorrere in costi (Amazon SNS). Considera TOTP come alternativa a costo zero.
3.  **Sessioni prolungate**:
    -   Se imposti un tempo di scadenza lungo per `RefreshToken`, l’utente farà il login meno spesso, e quindi meno richieste MFA.
4.  **Social Login** o identità federate:
    -   Se usi Cognito per l’autenticazione federata, verifica la compatibilità con i provider esterni. L’MFA Cognito si applica solo se l’utente è “nativo” della pool, non se arriva da un IdP esterno che già gestisce MFA (es. Google, Facebook).
5.  **Sicurezza**:
    -   Non “ricordare” dispositivi pubblici/insicuri. L’utente deve confermare solo quelli personali.

----------

## 7. Riepilogo Step-by-Step

1.  **Nella tua User Pool**:
    
    -   **Abilita** MFA “Optional” o “Required”.
    -   Seleziona i metodi (SMS e/o TOTP).
    -   **Abilita** Device Tracking: “Always” o “User Opt-in”.
2.  **Nel tuo Backend**:
    
    -   Implementa endpoint per:
        1.  **Login** (`initiate_auth`, `respond_to_auth_challenge` se serve).
        2.  **MFA**:
            -   **Enable/Disable** MFA (facoltativo se “Optional”).
            -   **SMS**: Abilita se telefono verificato.
            -   **TOTP**: `associate_software_token`, `verify_software_token`, `set_user_mfa_preference`.
        3.  **Device**:
            -   `confirm_device` (per ricordare il dispositivo).
            -   `update_device_status` (passare da remembered a not_remembered e viceversa).
3.  **Test**:
    
    -   Effettua un login da un device **non ricordato** → Vedi se Cognito chiede MFA.
    -   **Registra** il device con `confirm_device`.
    -   Ripeti il login → Verifica che **non** chieda MFA.
4.  **Consegna all’utente**:
    
    -   Un flusso intuitivo dove, dopo il primo login (con MFA), l’app chiede “Vuoi ricordare questo dispositivo?”.
    -   Invia la chiamata `confirm_device`.
    -   Da lì in poi, l’utente salta MFA su quello stesso device.

----------

## 8. Conclusione

1.  **Abilitare MFA** in Cognito → Permette di aggiungere SMS o TOTP per un ulteriore livello di sicurezza.
2.  **Device Tracking** → **Salta** MFA nei login successivi da dispositivi “fidati”.
3.  **Risultato**: Esperienza utente bilanciata tra sicurezza e frizione — MFA solo su nuovi dispositivi o se l’utente sceglie di non ricordarli.

Con questi step, la tua **implementazione MFA** in Amazon Cognito sarà **completa** e **potenziata** dal device tracking, consentendo un flusso di autenticazione robusto e allo stesso tempo comodo per gli utenti.
