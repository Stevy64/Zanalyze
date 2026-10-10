"""Service de calcul : mêmes routes et même paquet que Zanalyze Engine."""
from fastapi import FastAPI
from engine.api_analyse import router
from engine.moteur import VERSION_MOTEUR

app = FastAPI(title='Zanalyze Engine — calcul', version=VERSION_MOTEUR)
app.include_router(router)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'zanalyze-engine', 'version': VERSION_MOTEUR}
