import os, json, logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL")

# Supabase precisa de SSL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"}
)

app = FastAPI(title="Survey Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- HEALTH ----------
@app.get("/health")
def health():
    return {"ok": True}

# ---------- DEBUG (para isolar problemas) ----------
@app.get("/debug/db")
def dbg_db():
    try:
        with engine.begin() as c:
            r = c.execute(text("select now() as now, current_user as usr, current_database() as db")).mappings().first()
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

# ---------- SUBMIT ----------
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
        data_json = json.dumps(payload.data)              # <- JSON válido
        ua = payload.user_agent or request.headers.get("user-agent", "")
        params = {
            "perfil_2050": payload.perfil_2050,
            "user_agent": ua[:512],
            "data": data_json
        }
        with engine.begin() as conn:
            row = conn.execute(sql, params).mappings().first()
        return {"ok": True, "id": str(row["id"]), "submitted_at": row["submitted_at"].isoformat()}
    except Exception:
        logging.exception("DB insert failed")
        raise HTTPException(status_code=500, detail="DB insert failed")
