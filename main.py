import os
import time
import secrets
import asyncio
import qrcode
import io
import base64
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# In-memory storage (For a production app, use Redis)
sessions = {}

def get_qr_base64(url):
    qr = qrcode.make(url)
    buf = io.BytesIO()
    qr.save(buf)
    return base64.b64encode(buf.getvalue()).decode()

async def cleanup_task(session_id: str, delay: int, target: str):
    """Handles the self-destruct logic"""
    await asyncio.sleep(delay)
    if session_id in sessions:
        if target == "file":
            if os.path.exists(sessions[session_id]['file_path']):
                os.remove(sessions[session_id]['file_path'])
            sessions[session_id]['file_path'] = None
            print(f"File for {session_id} deleted.")
        elif target == "session":
            if not sessions[session_id].get('file_path'):
                del sessions[session_id]
                print(f"Session {session_id} expired and deleted.")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Create a new secure session
    session_id = secrets.token_hex(4).upper() # The "Short Code"
    password = secrets.token_urlsafe(8)
    sessions[session_id] = {
        "password": password,
        "file_path": None,
        "created_at": time.time()
    }
    
    # URL for the other device to access
    share_url = f"{request.base_url}join/{session_id}"
    qr_code = get_qr_base64(share_url)
    
    # Start 10-minute countdown to delete session if no file is exchanged
    asyncio.create_task(cleanup_task(session_id, 600, "session"))
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "code": session_id,
        "password": password,
        "qr": qr_code
    })

@app.post("/upload/{session_id}")
async def upload_file(session_id: str, file: UploadFile = File(...), password: str = Form(...)):
    if session_id not in sessions or sessions[session_id]['password'] != password:
        raise HTTPException(status_code=403, detail="Invalid session or password")
    
    file_path = f"temp_{session_id}_{file.filename}"
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    sessions[session_id]['file_path'] = file_path
    
    # Start 5-minute countdown to delete the file
    asyncio.create_task(cleanup_task(session_id, 300, "file"))
    
    return {"message": "File uploaded. It will self-destruct in 5 minutes."}
