from fastapi import APIRouter

from snipebot.persistence.db import check_db_ready

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str | bool]:
    db_ready = check_db_ready()
    return {
        "status": "ok" if db_ready else "degraded",
        "db_ready": db_ready,
    }
