from fastapi import FastAPI

# --- Logging primero ---
from core.logger import LoggerManager
log = LoggerManager(name="main", level="INFO", log_to_file=False).get_logger()
log.info("Aplicación iniciada")

# --- FastAPI app ---
from api.routes import router as api_router
from api.health import router as health_router
from middlewares.payload_limiters import limit_payload_size
from middlewares.rate_limiter import limit_rate_per_phone

app = FastAPI(title="Asistente virtual de Delirio Picante")

# Middlewares
app.middleware("http")(limit_payload_size)
app.middleware("http")(limit_rate_per_phone)

# Routers
app.include_router(health_router, prefix="/api")
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
