import json
import os

def load_cognito_config(config_path: str = "config.json"):
    """
    Carica la configurazione di Cognito da un file JSON.
    """
    # Determina il percorso assoluto se necessario (opzionale)
    # config_path = os.path.join(os.path.dirname(__file__), config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data
