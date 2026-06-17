from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import secrets
import httpx
import os
import json
import hashlib
from datetime import datetime
import base64
from io import BytesIO
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Advanced AI Studio API")

# Create static directory to host generated assets
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Enable CORS securely to accept requests from Netlify and eliminate "Failed to fetch" blockages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Set explicitly to False when allow_origins is wildcard "*"
    allow_methods=["*"],
    allow_headers=["*"], 
)

USERS_FILE = "users.json"

def load_users():
    """Loads users and ensures database schemas remain resilient across environment cycles."""
    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            try: 
                users = json.load(f)
            except: 
                users = {}
    
    # Ensure master administrative bypass profile is established securely
    if "admin" not in users:
        admin_key = f"sk-advanced-admin-{secrets.token_urlsafe(12)}"
        users["admin"] = {
            "name": "System Admin",
            "email": "admin",
            "password_hash": hashlib.sha256("admin".encode()).hexdigest(),
            "projects": {"Master Node": [{"name": "Admin Key", "key": admin_key, "usage": 0}]},
            "is_admin": True,
            "image_limit_tracking": {"date": datetime.now().date().isoformat(), "count": 0}
        }
        save_users(users)
        
    return users

def save_users(users_dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users_dict, f, indent=4)

USERS = load_users()

def get_all_active_keys():
    """Generates an inverted index mapping active API credentials back to associated users."""
    keys = {}
    for email, udata in USERS.items():
        for proj_name, proj_keys in udata.get("projects", {}).items():
            for k in proj_keys:
                keys[k["key"]] = email
    return keys

# ==========================================
# DATA MODELS
# ==========================================
class QueryRequest(BaseModel):
    prompt: str

class MediaRequest(BaseModel):
    prompt: str

class VisionRequest(BaseModel):
    prompt: str
    image_base64: str

class NetlifyAuthRequest(BaseModel):
    email: str
    name: str

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class ProjectRequest(BaseModel):
    email: str
    project_name: str

class KeyRequest(BaseModel):
    email: str
    project_name: str
    key_name: str

class DeleteKeyRequest(BaseModel):
    email: str
    project_name: str
    target_key: str

# ==========================================
# SYSTEM HEALTH & LIMITATION MANAGEMENT
# ==========================================
def check_and_track_image_limit(x_api_key: str):
    """Tracks key usage and restricts non-admins to a maximum of 5 image generations per day."""
    active_keys = get_all_active_keys()
    if not x_api_key or x_api_key not in active_keys:
        raise HTTPException(status_code=403, detail="Invalid or Missing API Key.")
    
    owner = active_keys[x_api_key]
    user_data = USERS.get(owner)
    if not user_data:
        raise HTTPException(status_code=404, detail="User context not found.")
    
    # Increment general usage stats for this key
    for proj_name, keys in user_data.get("projects", {}).items():
        for k in keys:
            if k["key"] == x_api_key:
                k["usage"] = k.get("usage", 0) + 1
                break
                
    # If user is not an admin, enforce the daily limit
    if not user_data.get("is_admin", False):
        today_str = datetime.now().date().isoformat()
        
        limit_data = user_data.get("image_limit_tracking")
        if not limit_data or not isinstance(limit_data, dict):
            limit_data = {"date": today_str, "count": 0}
            
        # Reset limit count if we entered a new day
        if limit_data.get("date") != today_str:
            limit_data = {"date": today_str, "count": 0}
            
        if limit_data.get("count", 0) >= 5:
            raise HTTPException(
                status_code=429, 
                detail="Daily image generation limit reached. Non-admin users are limited to 5 generations per day."
            )
            
        limit_data["count"] = limit_data.get("count", 0) + 1
        user_data["image_limit_tracking"] = limit_data
        
    save_users(USERS)

@app.get("/health")
async def health_check():
    """Silent system health diagnostic checker called by dashboard monitoring routines."""
    return {"status": "online"}

@app.post("/auth/admin-login")
async def admin_local_login(creds: AdminLoginRequest):
    """Bypasses external OAuth requirements to perform localized authentication operations."""
    user = USERS.get(creds.username)
    if not user or user.get("password_hash") != hashlib.sha256(creds.password.encode()).hexdigest():
        raise HTTPException(status_code=401, detail="Invalid administrator credentials.")
    
    return {
        "message": "Admin login authorized.", 
        "name": user.get("name", "Admin"),
        "email": creds.username, 
        "projects": user.get("projects", {}),
        "is_admin": True
    }

@app.post("/auth/netlify-sync")
async def netlify_sync(user: NetlifyAuthRequest):
    """Maps Netlify authentication identities securely onto internal local workspace assets."""
    email = user.email
    
    if email not in USERS:
        USERS[email] = {
            "name": user.name,
            "email": email,
            "projects": {"Default Project": []},
            "is_admin": False,
            "image_limit_tracking": {"date": datetime.now().date().isoformat(), "count": 0}
        }
        
        # Grant admin status dynamically if email prefix matches
        if email.startswith("admin") or email == "sanja":
            USERS[email]["is_admin"] = True
            
        save_users(USERS)
        
    return {
        "message": "User configuration synced.", 
        "name": USERS[email].get("name", "User"),
        "email": email,
        "projects": USERS[email].get("projects", {}),
        "is_admin": USERS[email].get("is_admin", False)
    }

# ==========================================
# ACCOUNT & KEY MANAGEMENT
# ==========================================
@app.post("/manage/projects/create")
async def create_project(req: ProjectRequest):
    if req.email not in USERS: raise HTTPException(status_code=401, detail="Unauthorized")
    if req.project_name not in USERS[req.email]["projects"]:
        USERS[req.email]["projects"][req.project_name] = []
        save_users(USERS)
    return {"projects": USERS[req.email]["projects"]}

@app.post("/manage/keys/create")
async def create_new_key(req: KeyRequest):
    if req.email not in USERS: raise HTTPException(status_code=401, detail="Unauthorized")
    if req.project_name not in USERS[req.email]["projects"]: raise HTTPException(status_code=404, detail="Workspace project not found.")
        
    new_key = f"sk-advanced-{secrets.token_urlsafe(16)}"
    USERS[req.email]["projects"][req.project_name].append({"name": req.key_name, "key": new_key, "usage": 0})
    save_users(USERS)
    return {"projects": USERS[req.email]["projects"]}

@app.post("/manage/keys/delete")
async def delete_key(req: DeleteKeyRequest):
    if req.email not in USERS: raise HTTPException(status_code=401, detail="Unauthorized")
    if req.project_name in USERS[req.email]["projects"]:
        keys = USERS[req.email]["projects"][req.project_name]
        USERS[req.email]["projects"][req.project_name] = [k for k in keys if k["key"] != req.target_key]
        save_users(USERS)
    return {"projects": USERS[req.email]["projects"]}

@app.post("/manage/admin/stats")
async def get_admin_stats(req: NetlifyAuthRequest):
    """Aggregates transactional telemetry to render high-fidelity statistics charts."""
    if req.email not in USERS or not USERS[req.email].get("is_admin", False): 
        raise HTTPException(status_code=403, detail="Administrative permissions required.")
    stats = {"labels": [], "data": []}
    for email, udata in USERS.items():
        total_usage = sum(k.get("usage", 0) for proj in udata.get("projects", {}).values() for k in proj)
        stats["labels"].append(udata.get("name", email.split("@")[0]))
        stats["data"].append(total_usage)
    return stats

# ==========================================
# NON-BLOCKING ASYNC API LOGIC
# ==========================================
@app.post("/v1/chat")
async def chat_engine(request: QueryRequest, x_api_key: str = Header(None)):
    # Track general usage for the API key
    active_keys = get_all_active_keys()
    if not x_api_key or x_api_key not in active_keys:
        raise HTTPException(status_code=403, detail="Invalid or Missing API Key.")
    owner = active_keys[x_api_key]
    for proj_name, keys in USERS[owner]["projects"].items():
        for k in keys:
            if k["key"] == x_api_key:
                k["usage"] = k.get("usage", 0) + 1
                save_users(USERS)
                break
                
    try:
        # Utilize httpx AsyncClient to allow up to 15 concurrent non-blocking requests to local Ollama
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "http://localhost:11434/api/generate", 
                json={"model": "advanced_ai", "prompt": request.prompt, "stream": False, "keep_alive": "24h"}
            )
            return {"reply": response.json()["response"]}
    except Exception as e:
        return {"reply": f"SYSTEM OFFLINE: Local Ollama engine is not running. API Key verified. Prompt: '{request.prompt}'. Error details: {str(e)}"}

@app.post("/v1/vision/analyze")
async def analyze_image(request: VisionRequest, x_api_key: str = Header(None)):
    active_keys = get_all_active_keys()
    if not x_api_key or x_api_key not in active_keys:
        raise HTTPException(status_code=403, detail="Invalid or Missing API Key.")
    owner = active_keys[x_api_key]
    for proj_name, keys in USERS[owner]["projects"].items():
        for k in keys:
            if k["key"] == x_api_key:
                k["usage"] = k.get("usage", 0) + 1
                save_users(USERS)
                break
                
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={"model": "llava", "prompt": request.prompt, "images": [request.image_base64], "stream": False, "keep_alive": "24h"}
            )
            return {"reply": response.json()["response"]}
    except Exception as e:
        return {"reply": f"**VISION ENGINE OFFLINE:** Ensure Ollama is running with the 'llava' model loaded. Error: {str(e)}"}

@app.post("/v1/media/image")
async def generate_image(request: MediaRequest, x_api_key: str = Header(None)):
    """Generates an image via torch/diffusers or custom high-fidelity engine if falling back. Enforces daily limits."""
    check_and_track_image_limit(x_api_key)
    
    # Max Llama Prompt Enhancement Integration
    enhanced_prompt = request.prompt
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            llama_res = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "advanced_ai", 
                    "prompt": f"Enhance this image generation prompt to have maximum visual detail and descriptive power: {request.prompt}. Only return the prompt text without quotes or intros.", 
                    "stream": False
                }
            )
            if llama_res.status_code == 200:
                enhanced_prompt = llama_res.json().get("response", request.prompt).strip()
    except Exception:
        pass # Fallback to original prompt if Llama is busy/offline

    try:
        import torch
        from diffusers import AutoPipelineForText2Image
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        calc_dtype = torch.float16 if device == "cuda" else torch.float32
        calc_variant = "fp16" if device == "cuda" else None

        # Build highly optimized configuration for sdxl-turbo
        pipe = AutoPipelineForText2Image.from_pretrained(
            "stabilityai/sdxl-turbo", 
            torch_dtype=calc_dtype, 
            variant=calc_variant,
            use_safetensors=True
        )
        pipe.to(device)
        
        # CPU optimization parameters for 5050 laptops
        if device == "cpu":
            pipe.enable_attention_slicing()
        
        steps = 4 if device == "cuda" else 2
        guidance = 0.0 if steps <= 2 else 1.0
        
        image = pipe(
            prompt=enhanced_prompt, 
            num_inference_steps=steps, 
            guidance_scale=guidance
        ).images[0]
        
        # Save archive locally
        filename = f"img_{secrets.token_hex(4)}.png"
        image.save(f"static/{filename}")
        
        # Convert image to Base64 to entirely bypass Ngrok warning screen blocking
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        data_url = f"data:image/png;base64,{img_base64}"
        
        del pipe
        if torch.cuda.is_available(): 
            torch.cuda.empty_cache()
            
        return {"status": "success", "url": data_url, "enhanced_prompt": enhanced_prompt}
        
    except Exception as e:
        # Programmatic high-quality abstract canvas generator if diffusers/torch is absent/failing on CPU
        try:
            from PIL import Image, ImageDraw
            import random
            
            img = Image.new("RGB", (800, 800), color=(10, 10, 14))
            draw = ImageDraw.Draw(img)
            
            # Draw beautiful procedural graphics matching prompt
            for _ in range(15):
                color_hue = (random.randint(10, 80), random.randint(40, 150), random.randint(180, 255))
                pos_x0, pos_y0 = random.randint(0, 800), random.randint(0, 800)
                pos_x1, pos_y1 = pos_x0 + random.randint(150, 400), pos_y0 + random.randint(150, 400)
                draw.ellipse([pos_x0, pos_y0, pos_x1, pos_y1], fill=None, outline=color_hue, width=random.randint(2, 6))
            
            # Draw simple text identifier
            text_desc = f"Synthesized pattern: {enhanced_prompt[:35]}..."
            draw.text((40, 370), text_desc, fill=(255, 255, 255))
            draw.text((40, 410), "[Advanced CPU Local Render Engine]", fill=(10, 132, 255))
            
            filename = f"canvas_{secrets.token_hex(4)}.png"
            img.save(f"static/{filename}")
            
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            data_url = f"data:image/png;base64,{img_base64}"
            
            return {"status": "success", "url": data_url, "info": f"Resolved via CPU Engine Fallback. Local model exception: {str(e)}", "enhanced_prompt": enhanced_prompt}
        except Exception as inner_error:
            raise HTTPException(status_code=500, detail=f"Image Engine crash. ({str(inner_error)})")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)