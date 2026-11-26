"""
FastAPI application entry point: serves static frontend, REST controls, and WebSocket stream.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.db.database import get_connection
from backend.monitor.analyzer import detect_anomalies, export_report_csv, generate_report
from backend.sim.engine import SimulationEngine
from backend.sim.optimizer import run_what_if

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

engine = SimulationEngine(seed=42)
connected_clients: Set[WebSocket] = set()


async def broadcast_snapshot(snapshot: dict) -> None:
    dead: list[WebSocket] = []
    for ws in list(connected_clients):
        try:
            await ws.send_json(snapshot)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.discard(ws)


engine.register_callback(broadcast_snapshot)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.start_loop()
    yield


app = FastAPI(title="PowerMonitorSim", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/state")
async def get_state():
    return engine.get_snapshot()


class SpeedReq(BaseModel):
    speed: int


class ResetReq(BaseModel):
    seed: int | None = None


class ChargerReq(BaseModel):
    charging: bool


@app.post("/api/sim/play")
async def sim_play():
    engine.running = True
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


@app.post("/api/sim/pause")
async def sim_pause():
    engine.running = False
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


@app.post("/api/sim/speed")
async def sim_speed(req: SpeedReq):
    engine.set_speed(req.speed)
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


@app.post("/api/sim/reset")
async def sim_reset(req: ResetReq):
    engine.reset(seed=req.seed)
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


@app.post("/api/device/charger")
async def device_charger(req: ChargerReq):
    engine.device.battery.set_charging(req.charging)
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


class ScreenReq(BaseModel):
    screen_on: bool


class AppActionReq(BaseModel):
    package_name: str
    bucket: str | None = None


@app.post("/api/device/screen")
async def device_screen(req: ScreenReq):
    engine.device.state.screen_on = req.screen_on
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


@app.post("/api/apps/launch")
async def app_launch(req: AppActionReq):
    engine.launch_app(req.package_name)
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


@app.post("/api/apps/kill")
async def app_kill(req: AppActionReq):
    engine.kill_app(req.package_name)
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


@app.post("/api/apps/bucket")
async def app_bucket(req: AppActionReq):
    if req.bucket:
        engine.set_bucket(req.package_name, req.bucket)
    snap = engine.get_snapshot()
    await broadcast_snapshot(snap)
    return snap


@app.get("/api/history/sessions")
async def history_sessions():
    conn = get_connection()
    rows = conn.execute("SELECT id, seed, started_at FROM sessions ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/history/battery")
async def history_battery(session_id: int | None = None):
    conn = get_connection()
    sid = session_id or engine.logger.session_id
    rows = conn.execute(
        "SELECT sim_time_s, level_pct, current_ma, voltage_mv, temperature_c, screen_on, doze_active FROM battery_samples WHERE session_id = ? ORDER BY sim_time_s ASC",
        (sid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/history/events")
async def history_events(session_id: int | None = None):
    conn = get_connection()
    sid = session_id or engine.logger.session_id
    rows = conn.execute(
        "SELECT sim_time_s, package_name, old_state, new_state FROM process_events WHERE session_id = ? ORDER BY id DESC LIMIT 100",
        (sid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/reports/summary")
async def reports_summary():
    rep = generate_report(engine.processes, engine.attribution.get_summary(), engine.sim_time_seconds)
    # Hourly drain pattern (percentage points lost per simulated day/hour) from logged samples
    conn = get_connection()
    rows = conn.execute(
        "SELECT sim_time_s, level_pct, charging_state FROM battery_samples WHERE session_id = ? ORDER BY sim_time_s",
        (engine.logger.session_id,),
    ).fetchall()
    conn.close()
    hourly: dict[tuple[int, int], float] = {}
    for prev, cur in zip(rows, rows[1:]):
        drop = prev["level_pct"] - cur["level_pct"]
        if drop > 0 and cur["charging_state"] != "CHARGING":
            key = (int(cur["sim_time_s"] // 86400) + 1, int(cur["sim_time_s"] % 86400 // 3600))
            hourly[key] = hourly.get(key, 0.0) + drop
    rep["hourly_drain"] = [{"day": d, "hour": h, "drain_pct": round(v, 2)} for (d, h), v in sorted(hourly.items())]
    return rep


@app.get("/api/reports/export.csv")
async def reports_export_csv():
    csv_text = export_report_csv(engine.attribution.get_summary())
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=power_report.csv"},
    )


@app.get("/api/alerts")
async def get_alerts():
    return detect_anomalies(engine.processes, engine.attribution.get_summary())


class OptimizerReq(BaseModel):
    seed: int = 42
    battery_saver: bool = False
    aggressive_doze: bool = True
    restrict_rogue: bool = True
    max_brightness: float = 0.7
    max_cpu_freq_mhz: int = 1800


@app.post("/api/optimizer/run")
async def optimizer_run(req: OptimizerReq):
    return run_what_if(
        seed=req.seed,
        battery_saver=req.battery_saver,
        aggressive_doze=req.aggressive_doze,
        restrict_rogue=req.restrict_rogue,
        max_brightness=req.max_brightness,
        max_cpu_freq_mhz=req.max_cpu_freq_mhz,
    )


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        await ws.send_json(engine.get_snapshot())
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(ws)
    except Exception:
        connected_clients.discard(ws)
