from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import logging
import os
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

# CORS - Permite o frontend acessar a API
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5000")
ALLOWED_ORIGINS = [
    FRONTEND_URL,
    "http://localhost:5000",
    "http://localhost:3000",
    "http://127.0.0.1:5000",
    "http://127.0.0.1:3000",
]

# Adiciona origens de produção se configuradas
if os.getenv("PRODUCTION_FRONTEND_URL"):
    ALLOWED_ORIGINS.append(os.getenv("PRODUCTION_FRONTEND_URL"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas API
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.post("/trigger-now")
async def trigger_manual():
    """Endpoint para forçar o ciclo manualmente (dev/debug)"""
    await run_daily_cycle()
    return {"status": "Ciclo disparado manualmente"}

# --- Frontend React (Servido como arquivos estáticos) ---
# O frontend buildado fica em /static/dist após o build
STATIC_DIR = Path(__file__).parent.parent / "static" / "dist"

if STATIC_DIR.exists():
    # Serve os assets (JS, CSS, imagens)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    
    # Rota catch-all para o SPA (Single Page Application)
    # Qualquer rota que não seja /api/* retorna o index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Se for uma rota de API, deixa passar (já foi tratada acima)
        if full_path.startswith("api/"):
            return {"error": "Not found"}
        
        # Tenta servir arquivo estático primeiro
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        
        # Caso contrário, retorna index.html (para rotas do React Router)
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        
        return {"error": "Frontend not built"}
else:
    # Fallback: Se o frontend não foi buildado, mostra página simples
    @app.get("/")
    async def root(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})
