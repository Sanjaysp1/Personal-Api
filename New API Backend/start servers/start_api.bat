@echo off
cd /d "C:\Users\sanja\OneDrive\Desktop\New API Backend"
start /b C:/Users/sanja/AppData/Local/Microsoft/WindowsApps/python3.12.exe -m uvicorn advanced_ai_api:app --host 0.0.0.0 --port 8000
exit
*If you double-click this file, it flashes for one second and disappears. Your API is now running silently in the background!*

#### Step 2: Make it Auto-Start When You Turn On the Laptop
1. Press `Windows Key + R` on your keyboard.
2. Type `shell:startup` and press Enter. A folder will open.
3. Right-click your `start_api.bat` file (from Step 1), select **Copy**.
4. Go to the `Startup` folder, right-click, and select **Paste shortcut**. 
*(Now, every time you turn on your laptop, the API turns on automatically).*

#### Step 3: Create the "Off" Switch
If your laptop is getting hot or you want to play a game, you need to turn the API off.
1. On your Desktop, create a new text document named `stop_api.bat`.
2. Edit it and paste this exact code:
```bat
@echo off
taskkill /f /im uvicorn.exe
taskkill /f /im python3.12.exe
echo API Server is now OFF.
pause
*(Double-click this whenever you want to force the API to shut down).*

---

### The Final Step: Connecting Netlify to Your Laptop

If you upload `frontend_portal.html` to Netlify right now, it will look beautiful, but it won't be able to connect to your API if you open it on your phone. Why? Because `http://localhost:8000` means "look inside the current device". 

To make your laptop a **real, global API server**:
1. Download [ngrok](https://ngrok.com/download) (it is free).
2. Open the ngrok terminal and type: `ngrok http 8000`
3. Ngrok will give you a public web address that looks like this: `https://a1b2-c3d4.ngrok-free.app`
4. **Before you upload to Netlify:** Open `frontend_portal.html`, find `const API_BASE_URL = 'http://localhost:8000';` (line 78), and replace `http://localhost:8000` with your new ngrok link.

Now, your laptop is running silently in the background, your frontend is beautifully hosted on Netlify, and anyone in the world can generate API keys through your system!