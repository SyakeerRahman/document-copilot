import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, threads
from app.config import settings
from app.database.session import create_engine, create_sessionmaker

HTTP_TIMEOUT_SECONDS = 10


def require_selector_loop_on_windows() -> None:
    # psycopg's async mode cannot run on the ProactorEventLoop that plain `uvicorn` uses on Windows.
    # `uvicorn --reload` uses the selector loop. Production runs on Linux and never hits this.
    if sys.platform == "win32" and isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop):
        raise RuntimeError(
            "On Windows, start the API with `uv run uvicorn app.main:app --reload`. "
            "Without --reload uvicorn uses the ProactorEventLoop, which psycopg async does not support."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    require_selector_loop_on_windows()
    engine = create_engine()
    app.state.sessionmaker = create_sessionmaker(engine)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
        app.state.http = http
        yield
    await engine.dispose()


app = FastAPI(title="Document Copilot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads.router)
app.include_router(chat.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
