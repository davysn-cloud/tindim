from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging
from app.config import settings
from app.services.scheduler import start_scheduler, run_daily_cycle
from app.api.v1.router import api_router

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Templates
templates = Jinja2Templates(directory="app/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Iniciando InsightFlow Finance...")
    start_scheduler()
    yield
    # Shutdown
    logger.info("Desligando aplicação...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Rotas API
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/trigger-now")
async def trigger_manual():
    """Endpoint para forçar o ciclo manualmente (dev/debug)"""
    await run_daily_cycle()
    return {"status": "Ciclo disparado manualmente"}
