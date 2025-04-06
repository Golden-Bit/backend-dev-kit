# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import dei router esistenti
from app.authentication.api.user import user_router
from app.authentication.api.admin import admin_router
from app.authentication.api.mfa import mfa_router
from app.authentication.api.social import social_router

app = FastAPI(
    title="Cognito Authentication and MFA API",
    description=(
        "Questa applicazione si basa su FastAPI per la gestione degli utenti tramite Amazon Cognito.\n\n"
        "**Struttura dei router**:\n"
        "- **User Router** (`/v1/user`): Endpoint per operazioni self-service, "
        "come registrazione, autenticazione, recupero password, aggiornamento attributi e così via.\n\n"
        "- **Admin Router** (`/v1/admin`): Endpoint riservati a operazioni amministrative, "
        "come conferma manuale delle registrazioni e visualizzazione/aggiornamento (se possibile) dello schema attributi.\n\n"
        "- **MFA Router** (`/v1/user/mfa`): Endpoint dedicati alla configurazione e gestione "
        "dell'autenticazione a due fattori (MFA), sia via SMS che TOTP (es. Google Authenticator).\n\n"
        "- **Social Router** (`/v1/user/social`): Endpoint per il login federato con provider terzi "
        "(ad es. Google, Facebook, Apple, Amazon), sfruttando il Hosted UI di Cognito.\n\n"
        "**Principali funzionalità**:\n"
        "1. **Registrazione e Autenticazione**: Signup (con conferma), Signin, gestione token.\n"
        "2. **Recupero Password**: Forgot password con conferma (email/SMS) e nuovo set di password.\n"
        "3. **Aggiornamento Attributi**: Standard (email, phone) e custom (prefisso 'custom:').\n"
        "4. **Admin**: Conferma utente, gestione schema attributi.\n"
        "5. **MFA**: Abilitazione e disabilitazione di SMS e TOTP.\n"
        "6. **Social/Federation**: Accesso tramite provider esterni (Google, Facebook, ecc.) "
        "con flusso di callback e scambio del 'code'.\n\n"
        "Per maggiori dettagli, esplora la sezione **Docs** all'indirizzo `/docs` e la sezione **Redoc** all'indirizzo `/redoc`."
    ),
    version="1.0.0",
)

# Inclusione dei router esistenti
app.include_router(user_router)
app.include_router(admin_router)
app.include_router(mfa_router)
app.include_router(social_router)

# Configurazione CORS (se necessaria)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permetti tutte le origini (in produzione, limitale)
    allow_credentials=True,
    allow_methods=["*"],  # Permetti tutti i metodi (GET, POST, OPTIONS, ecc.)
    allow_headers=["*"],  # Permetti tutti gli headers
)

if __name__ == "__main__":
    import uvicorn
    # Esegui l'app su 0.0.0.0:8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
