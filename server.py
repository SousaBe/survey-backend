import os
import json
import logging
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

# ---- LOGGING (para veres o erro real nos Logs do Render) ----
logging.basicConfig(level=logging.INFO)

# === CONFIG ===
DATABASE_URL = os.getenv("DATABASE_URL")  # string do Supabase (pooled, porta 6543)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL env var.")

# sslmode=require é recomendado pelo Supabase
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"}
)

app = FastAPI(title="Survey Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # ex.: https://sousabe.github.io
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Ping de saúde (opcional, útil p/ testar no browser) ----
@app.get("/health")
def health():
    return {"ok": True}

# ---- Modelo do payload ----
class Submission(BaseModel):
    response_id: str
    submitted_at: str
    user_agent: Optional[str] = None
    perfil_2050: Optional[str] = None
    data: Dict[str, Any]

# ---- Endpoint principal ----
@app.post("/submit")
async def submit(payload: Submission, request: Request):
    sql = text("""
        insert into responses (perfil_2050, user_agent, data)
        values (:perfil_2050, :user_agent, :data::jsonb)
        returning id, submitted_at
    """)

    try:
        # 🔴 IMPORTANTE: garantir que 'data' vai como JSON válido (string)
        data_json = json.dumps(payload.data)

        ua = payload.user_agent or request.headers.get("user-agent", "")
        params = {
            "perfil_2050": payload.perfil_2050,
            "user_agent": ua[:512],
            "data": data_json
        }

        with engine.begin() as conn:
            row = conn.execute(sql, params).mappings().first()

        return {
            "ok": True,
            "id": str(row["id"]),
            "submitted_at": row["submitted_at"].isoformat()
        }

    except Exception as e:
        logging.exception("DB insert failed")  # isto aparece nos Logs do Render
        raise HTTPException(status_code=500, detail="DB insert failed")
