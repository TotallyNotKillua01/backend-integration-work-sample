from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field

DB_PATH = Path(__file__).with_name("sample.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
KIT_PATTERN = re.compile(r"^KIT-[A-Z0-9]{8}$")

app = FastAPI(
    title="Wellness Kit Backend Integration Sample",
    version="1.0.0",
    description=(
        "A synthetic backend sample demonstrating customer registration, kit linking, "
        "processing status, report generation, validation, and dashboard delivery."
    ),
)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with closing(connect()) as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()


class CustomerCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=100)


class KitRegister(BaseModel):
    kit_code: str
    customer_id: int = Field(gt=0)


class KitStatusUpdate(BaseModel):
    status: Literal["registered", "received", "processing", "completed"]


class ProcessingJobCreate(BaseModel):
    kit_id: int = Field(gt=0)
    pipeline_version: str = Field(min_length=1, max_length=30)


class ProcessingJobUpdate(BaseModel):
    status: Literal["queued", "running", "succeeded", "failed"]


class ReportCreate(BaseModel):
    kit_id: int = Field(gt=0)
    report_version: str = Field(min_length=1, max_length=30)
    summary: str = Field(min_length=10, max_length=500)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/customers", status_code=201)
def create_customer(payload: CustomerCreate) -> dict:
    try:
        with closing(connect()) as conn:
            cur = conn.execute(
                "INSERT INTO customers (email, full_name) VALUES (?, ?)",
                (str(payload.email).lower(), payload.full_name.strip()),
            )
            conn.commit()
            return {"id": cur.lastrowid, **payload.model_dump()}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Email already exists")


@app.post("/kits/register", status_code=201)
def register_kit(payload: KitRegister) -> dict:
    kit_code = payload.kit_code.strip().upper()
    if not KIT_PATTERN.match(kit_code):
        raise HTTPException(
            status_code=422,
            detail="kit_code must match KIT-XXXXXXXX using letters/numbers",
        )

    with closing(connect()) as conn:
        customer = conn.execute(
            "SELECT id FROM customers WHERE id = ?", (payload.customer_id,)
        ).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        try:
            cur = conn.execute(
                "INSERT INTO kits (kit_code, customer_id) VALUES (?, ?)",
                (kit_code, payload.customer_id),
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "kit_code": kit_code,
                "customer_id": payload.customer_id,
                "status": "registered",
            }
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Kit already registered")


@app.patch("/kits/{kit_id}/status")
def update_kit_status(kit_id: int, payload: KitStatusUpdate) -> dict:
    with closing(connect()) as conn:
        cur = conn.execute(
            "UPDATE kits SET status = ? WHERE id = ?", (payload.status, kit_id)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Kit not found")
        conn.commit()
        return {"kit_id": kit_id, "status": payload.status}


@app.post("/processing-jobs", status_code=201)
def create_processing_job(payload: ProcessingJobCreate) -> dict:
    with closing(connect()) as conn:
        kit = conn.execute("SELECT id FROM kits WHERE id = ?", (payload.kit_id,)).fetchone()
        if not kit:
            raise HTTPException(status_code=404, detail="Kit not found")
        try:
            cur = conn.execute(
                "INSERT INTO processing_jobs (kit_id, pipeline_version) VALUES (?, ?)",
                (payload.kit_id, payload.pipeline_version),
            )
            conn.execute("UPDATE kits SET status = 'processing' WHERE id = ?", (payload.kit_id,))
            conn.commit()
            return {
                "id": cur.lastrowid,
                "kit_id": payload.kit_id,
                "pipeline_version": payload.pipeline_version,
                "status": "queued",
            }
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Processing job already exists for kit")


@app.patch("/processing-jobs/{job_id}")
def update_processing_job(job_id: int, payload: ProcessingJobUpdate) -> dict:
    with closing(connect()) as conn:
        job = conn.execute(
            "SELECT id, kit_id FROM processing_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Processing job not found")

        conn.execute(
            "UPDATE processing_jobs SET status = ? WHERE id = ?",
            (payload.status, job_id),
        )
        if payload.status == "succeeded":
            conn.execute("UPDATE kits SET status = 'completed' WHERE id = ?", (job["kit_id"],))
        conn.commit()
        return {"job_id": job_id, "status": payload.status}


@app.post("/reports", status_code=201)
def create_report(payload: ReportCreate) -> dict:
    with closing(connect()) as conn:
        kit = conn.execute(
            "SELECT id, status FROM kits WHERE id = ?", (payload.kit_id,)
        ).fetchone()
        if not kit:
            raise HTTPException(status_code=404, detail="Kit not found")
        if kit["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail="Report can only be generated after kit processing is completed",
            )
        try:
            cur = conn.execute(
                "INSERT INTO reports (kit_id, report_version, summary) VALUES (?, ?, ?)",
                (payload.kit_id, payload.report_version, payload.summary.strip()),
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "kit_id": payload.kit_id,
                "report_version": payload.report_version,
                "summary": payload.summary,
            }
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Report already exists for kit")


@app.get("/customers/{customer_id}/dashboard")
def customer_dashboard(customer_id: int) -> dict:
    with closing(connect()) as conn:
        customer = conn.execute(
            "SELECT id, email, full_name FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        rows = conn.execute(
            """
            SELECT k.id AS kit_id, k.kit_code, k.status,
                   pj.status AS processing_status,
                   r.id AS report_id, r.report_version
            FROM kits k
            LEFT JOIN processing_jobs pj ON pj.kit_id = k.id
            LEFT JOIN reports r ON r.kit_id = k.id
            WHERE k.customer_id = ?
            ORDER BY k.id DESC
            """,
            (customer_id,),
        ).fetchall()

        return {
            "customer": dict(customer),
            "kits": [dict(row) for row in rows],
        }
