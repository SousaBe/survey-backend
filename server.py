import os, json, logging
from typing import Optional, Dict, Any

from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.engine.url import make_url
from sqlalchemy.dialects.postgresql import JSON

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)

# ---------------- Env vars ----------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL")

raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in raw_origins.split(",") if o.strip()]
logging.info("ALLOWED_ORIGINS = %r", ALLOWED_ORIGINS)

# Log seguro da connection string (sem quebrar o arranque)
try:
    u = make_url(DATABASE_URL)
    logging.info("DB -> host=%s port=%s db=%s user=%s",
                 u.host, u.port, u.database, u.username)
except Exception as e:
    logging.warning("Could not parse DATABASE_URL for logging: %s", e)

# ---------------- SQLAlchemy Engine ----------------
# Supabase requer SSL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"},
)

# ---------------- FastAPI app ----------------
app = FastAPI(title="Survey Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # ex.: ["https://sousabe.github.io"]
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Models ----------------
class Submission(BaseModel):
    response_id: str
    submitted_at: str
    user_agent: Optional[str] = None
    perfil_2050: Optional[str] = None
    data: Dict[str, Any]

# ---------------- Health & Debug ----------------
@app.get("/health")
def health():
    return {"ok": True}

# ---------------- Main submit ----------------
from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.dialects.postgresql import JSONB

@app.post("/submit")
async def submit(payload: Submission, request: Request):
    # Inserimos response_id e evitamos duplicados com ON CONFLICT
    sql = text("""
        insert into public.responses (perfil_2050, user_agent, data)
        values (:perfil_2050, :user_agent, :data)
        returning id, submitted_at
    """).bindparams(
        bindparam("data", type_=JSON)   # ← aqui JSON
    )

    try:
        ua = payload.user_agent or request.headers.get("user-agent", "")
        with engine.begin() as conn:
            row = conn.execute(sql, {
                "response_id": payload.response_id,  
                "perfil_2050": payload.perfil_2050,
                "user_agent": ua[:512],
                "data": payload.data,               
            }).mappings().first()

        if row is None:
            # conflito (response_id já existia): tratamos como sucesso idempotente
            return {"ok": True, "duplicate": True}

        return {
            "ok": True,
            "id": str(row["id"]),
            "submitted_at": row["submitted_at"].isoformat(),
        }
    except Exception:
        logging.exception("DB insert failed")
        raise HTTPException(status_code=500, detail="DB insert failed")
