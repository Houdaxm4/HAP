from fastapi import APIRouter

from app.api.routes import analyses, chat, health, websocket

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(analyses.router, prefix="/analyses", tags=["analyses"])
api_router.include_router(chat.router, prefix="/analyses", tags=["chat"])
api_router.include_router(websocket.router, tags=["websocket"])
