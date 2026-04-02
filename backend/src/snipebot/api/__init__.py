from fastapi import APIRouter

from .health import router as health_router
from .watchlist import router as watchlist_router

router = APIRouter()
router.include_router(health_router)
router.include_router(watchlist_router)
