import os, json, logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)

# ---------------- Config -----------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL")

# CORS: lista sem espaços
raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in raw_origins.split(",") if o.strip()]
logging.info("ALLOWED_ORIGINS = %r", ALLOWED_ORIGINS)

# Só para veres nos logs a que BD ligaste (sem password)
u = urlparse(DATABASE_URL)
logging.info("DB -> host=%s port=%s db=%s user=%s",
             u.hostname, u.port, (u.path or "/").lstrip("/"), u.username)

# ---------------- Engine -----------------
# Supabase requer SSL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"},
)

# ---------------- App --------------------
app = FastAPI(title="Survey Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # ex.: ["https://sousabe.github.io", ...]
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Health & Debug ----------
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/debug/db")
def dbg_db():
    try:
        with engine.begin() as c:
            r = c.execute(
                text("select now() as now, current_user as usr, current_database() as db")
            ).mappings().first()
        return {"ok": True, **dict(r)}
    except Exception:
        logging.exception("DB check failed")
        raise HTTPException(status_code=500, detail="DB check failed")

@app.post("/debug/insert")
def dbg_insert():
    try:
        with engine.begin() as c:
            r = c.execute(text("""
                insert into responses (perfil_2050, user_agent, data)
                values ('dbg', 'manual', '{}'::jsonb)
                returning id
            """)).mappings().first()
        return {"ok": True, "id": str(r["id"])}
    except Exception:
        logging.exception("Debug insert failed")
        raise HTTPException(status_code=500, detail="Debug insert failed")

# ---------- Modelo & Submit ----------
class Submission(BaseModel):
    response_id: str
    submitted_at: str
    user_agent: Optional[str] = None
    perfil_2050: Optional[str] = None
    data: Dict[str, Any]

@app.post("/submit")
async def submit(payload: Submission, request: Request):
    sql = text("""
        insert into responses (perfil_2050, user_agent, data)
        values (:perfil_2050, :user_agent, :data::jsonb)
        returning id, submitted_at
    """)
    try:
        data_json = json.dumps(payload.data)  # garantir JSON válido
        ua = payload.user_agent or request.headers.get("user-agent", "")

        with engine.begin() as conn:
            row = conn.execute(sql, {
                "perfil_2050": payload.perfil_2050,
                "user_agent": ua[:512],
                "data": data_json
            }).mappings().first()

        return {"ok": True,
                "id": str(row["id"]),
                "submitted_at": row["submitted_at"].isoformat()}
    except Exception:
        logging.exception("DB insert failed")
        raise HTTPException(status_code=500, detail="DB insert failed")

