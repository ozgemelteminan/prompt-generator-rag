from fastapi import APIRouter

from app.api.v1.routes.documents import router as documents_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.prompts import router as prompts_router
from app.api.v1.routes.rag import router as rag_router
from app.api.v1.routes.retrieval import router as retrieval_router
from app.api.v1.routes.usage import router as usage_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(documents_router)
api_router.include_router(prompts_router)
api_router.include_router(retrieval_router)
api_router.include_router(rag_router)
api_router.include_router(usage_router)
