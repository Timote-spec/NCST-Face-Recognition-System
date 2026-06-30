from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routes.admin import router as admin_router
from app.routes.attendance import router as attendance_router
from app.routes.auth import router as auth_router
from app.routes.register import router as register_router

app = FastAPI(title="NCST Face Recognition Attendance System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


app.include_router(auth_router, prefix="/api/v1", tags=["Auth"])
app.include_router(register_router, prefix="/api/v1", tags=["Registration"])
app.include_router(attendance_router, prefix="/api/v1", tags=["Attendance"])
app.include_router(admin_router, prefix="/api/v1", tags=["Admin"])

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", response_class=FileResponse)
async def read_index():
    return FileResponse("frontend/index.html")


@app.get("/login", response_class=FileResponse)
async def read_login():
    return FileResponse("frontend/login.html")


@app.get("/health")
def health_check():
    return {"status": "ok"}
