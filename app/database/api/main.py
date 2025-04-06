from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.database.api.mongodb_v1 import router as mongo_router_v1
#from app.database.api.mongodb_v2 import router as mongo_router_v2


# Create the FastAPI application instance
app = FastAPI(
    title="DB Management Service",
    description=(
        "API per la gestione di database MongoDB, collezioni e documenti. "
        "L'autenticazione è basata su una nuova API (su AWS Cognito) che gestisce i metadata degli utenti "
        "e garantisce l'accesso sicuro ai database."
    ),
    version="1.0.0",
    root_path="/database"
)

# Configure CORS to allow all origins, credentials, methods, and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         # Allow requests from all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the MongoDB management router in the application
app.include_router(mongo_router_v1)
#app.include_router(mongo_router_v2)

# Additional routers (e.g., authentication routes) can be included here if needed
# from app.auth_route import router as auth_router
# app.include_router(auth_router)

if __name__ == "__main__":
    # Run the application using uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
