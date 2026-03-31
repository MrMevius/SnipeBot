from contextlib import asynccontextmanager

from fastapi import FastAPI

from snipebot.api import router as api_router
from snipebot.core.config import get_settings
from snipebot.core.logging import configure_logging
from snipebot.persistence.db import init_db

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="SnipeBot API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
