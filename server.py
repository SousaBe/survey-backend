from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, text
import os

# === CONFIG (vamos definir no Render) ===
DATABASE_URL = os.getenv("DATABASE_URL")  # vem do Supabase (connection string)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL env var.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

app = FastAPI(title="Survey Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

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
        with engine.begin() as conn:
            row = conn.execute(sql, {
                "perfil_2050": payload.perfil_2050,
                "user_agent": payload.user_agent or request.headers.get("user-agent", "")[:512],
                "data": payload.model_dump()["data"]
            }).mappings().first()
        return {"ok": True, "id": str(row["id"]), "submitted_at": row["submitted_at"].isoformat()}
    except Exception:
        # não mostrar detalhes internos para o público
        raise HTTPException(status_code=500, detail="DB insert failed")
