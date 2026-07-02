from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routes.admin import router as admin_router
from app.routes.attendance import router as attendance_router
from app.routes.auth import router as auth_router
from app.routes.register import router as register_router

app = FastAPI(title="NCST Face Recognition Attendance System")


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in ("/", "/login", "/register", "/forgot-password", "/reset-password"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

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


# --- Explicit routes for main pages (both .html and extensionless) ---

@app.get("/", response_class=FileResponse)
async def read_index():
    return FileResponse("frontend/index.html")


@app.get("/login", response_class=FileResponse)
@app.get("/login.html", response_class=FileResponse)
async def read_login():
    return FileResponse("frontend/login.html")


@app.get("/register", response_class=FileResponse)
@app.get("/register.html", response_class=FileResponse)
async def read_register():
    return FileResponse("frontend/register.html")


@app.get("/forgot-password", response_class=FileResponse)
@app.get("/forgot-password.html", response_class=FileResponse)
async def read_forgot_password():
    return FileResponse("frontend/forgot-password.html")


@app.get("/reset-password", response_class=FileResponse)
@app.get("/reset-password.html", response_class=FileResponse)
async def read_reset_password():
    return FileResponse("frontend/reset-password.html")


# --- Static files & catch-all HTML fallback (at the bottom so API routes win) ---

app.mount("/static", StaticFiles(directory="frontend"), name="static")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


def health_check():
    return {"status": "ok"}
