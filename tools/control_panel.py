#!/usr/bin/env python3
"""A FastAPI control panel for the rabbit face. Run it on your laptop.

It runs here, not on the board. The UNO Q browns out under load, so the board
only runs the face. This talks to it over the reverse tunnel or over Wi-Fi.

    ./.venv/bin/uvicorn tools.control_panel:app --port 9000
    open http://127.0.0.1:9000

Point it somewhere else with:
    BOARD_URL=http://10.254.159.201:8080 ./.venv/bin/uvicorn tools.control_panel:app --port 9000
"""
import os

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

BOARD_URL = os.environ.get("BOARD_URL", "http://127.0.0.1:8080").rstrip("/")

# The eight names the demo uses. server.py maps them onto rabbit moods.
DEMO_FACES = [
    ("Ready", "1", "Waiting. The resting face."),
    ("Watching", "2", "Looking down at the mat."),
    ("Encourage", "3", "Try again. You are close."),
    ("Thinking", "4", "Working out what comes next."),
    ("Go", "5", "Movement mission. Hop."),
    ("Celebrate", "6", "Correct answer."),
    ("Rest", "7", "Break time."),
    ("Soft confused", "8", "Too hard a touch, or a wrong answer."),
]

# The ten raw rabbit moods underneath. Useful for tuning, not for the demo.
RAW_MOODS = ["neutral", "happy", "excited", "curious", "sad",
             "sleepy", "surprised", "angry", "love", "boot"]

app = FastAPI(title="HARE control panel")


class Emote(BaseModel):
    name: str
    hold: float = 0


@app.get("/api/health")
async def health():
    """Ask the board how it is. Also proves the tunnel is up."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{BOARD_URL}/health")
        return JSONResponse({"ok": True, "board": BOARD_URL, "data": r.json()})
    except Exception as exc:
        return JSONResponse({"ok": False, "board": BOARD_URL, "error": str(exc)}, status_code=502)


@app.post("/api/emote")
async def emote(body: Emote):
    """Send one face to the board."""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(f"{BOARD_URL}/emote", json={"name": body.name, "hold": body.hold})
        return JSONResponse(r.json(), status_code=r.status_code)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)


@app.get("/", response_class=HTMLResponse)
async def index():
    demo = "".join(
        f'<button class="face" data-name="{n}" data-key="{k}">'
        f'<kbd>{k}</kbd><span class="n">{n}</span><span class="d">{d}</span></button>'
        for n, k, d in DEMO_FACES
    )
    raw = "".join(f'<button class="raw" data-name="{m}">{m}</button>' for m in RAW_MOODS)
    return HTML.replace("{{DEMO}}", demo).replace("{{RAW}}", raw).replace("{{BOARD}}", BOARD_URL)


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HARE control</title>
<style>
:root{--bg:#0d0f12;--card:#171a1f;--line:#272c34;--fg:#eef1f5;--dim:#8b93a1;
      --accent:#ffc24b;--ok:#3ddc84;--bad:#ff6b5e;--radius:14px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,-apple-system,"SF Pro Text",system-ui,sans-serif;
     padding:24px;max-width:960px;margin:0 auto}
header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:4px}
h1{font-size:22px;letter-spacing:-.01em}
.sub{color:var(--dim);font-size:13px}
#bar{display:flex;align-items:center;gap:10px;margin:18px 0 26px;padding:12px 16px;
     background:var(--card);border:1px solid var(--line);border-radius:var(--radius)}
#dot{width:10px;height:10px;border-radius:50%;background:var(--dim);flex:none}
#dot.ok{background:var(--ok)}#dot.bad{background:var(--bad)}
#stat{font-size:13px;color:var(--dim);font-family:ui-monospace,Menlo,monospace;
      overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.14em;color:var(--dim);margin:26px 0 12px}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.face{display:flex;flex-direction:column;align-items:flex-start;gap:3px;text-align:left;
      padding:16px;background:var(--card);color:var(--fg);border:1px solid var(--line);
      border-radius:var(--radius);cursor:pointer;transition:border-color .12s,transform .06s}
.face:hover{border-color:var(--accent)}
.face:active{transform:translateY(1px)}
.face.hit{border-color:var(--accent);background:#211d15}
.face kbd{font:11px ui-monospace,Menlo,monospace;color:var(--accent);border:1px solid var(--line);
          border-radius:5px;padding:1px 6px;margin-bottom:4px}
.face .n{font-size:16px;font-weight:600}
.face .d{font-size:12px;color:var(--dim)}
#raws{display:flex;flex-wrap:wrap;gap:8px}
.raw{padding:8px 13px;background:transparent;color:var(--dim);border:1px solid var(--line);
     border-radius:9px;cursor:pointer;font-size:13px}
.raw:hover{color:var(--fg);border-color:var(--accent)}
#hold{display:flex;align-items:center;gap:10px;color:var(--dim);font-size:13px;margin-top:20px}
#hold input{width:190px;accent-color:var(--accent)}
#log{margin-top:22px;font:12px ui-monospace,Menlo,monospace;color:var(--dim);
     background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
     padding:12px 14px;height:132px;overflow:auto}
@media(max-width:560px){body{padding:16px}#grid{grid-template-columns:1fr}}
</style></head><body>
<header><h1>HARE control</h1><span class="sub">{{BOARD}}</span></header>
<div id="bar"><span id="dot"></span><span id="stat">checking the board...</span></div>

<h2>Demo faces &mdash; press 1 to 8</h2>
<div id="grid">{{DEMO}}</div>

<div id="hold"><label for="h">hold</label>
  <input id="h" type="range" min="0" max="10" step="1" value="0">
  <output id="hv">stays until the next face</output></div>

<h2>Raw moods</h2>
<div id="raws">{{RAW}}</div>

<h2>Log</h2><div id="log"></div>

<script>
const $=s=>document.querySelector(s), log=$('#log');
let hold=0;

function say(msg,bad){
  const t=new Date().toTimeString().slice(0,8);
  log.insertAdjacentHTML('afterbegin',
    `<div style="color:${bad?'var(--bad)':'var(--dim)'}">${t}  ${msg}</div>`);
}

$('#h').addEventListener('input',e=>{
  hold=Number(e.target.value);
  $('#hv').textContent = hold ? hold+' seconds, then back to Ready' : 'stays until the next face';
});

async function send(name,btn){
  if(btn){btn.classList.add('hit');setTimeout(()=>btn.classList.remove('hit'),260);}
  try{
    const r=await fetch('/api/emote',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,hold})});
    const d=await r.json();
    say(d.ok===false ? `${name} FAILED - ${d.error||'board said no'}` : `${name}  hold=${hold}s`, d.ok===false);
  }catch(e){ say(`${name} FAILED - ${e.message}`,true); }
}

document.querySelectorAll('.face,.raw').forEach(b=>
  b.addEventListener('click',()=>send(b.dataset.name,b.classList.contains('face')?b:null)));

addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT') return;
  const b=document.querySelector(`.face[data-key="${e.key}"]`);
  if(b){ e.preventDefault(); send(b.dataset.name,b); }
});

async function poll(){
  try{
    const r=await fetch('/api/health'), d=await r.json();
    if(d.ok){ $('#dot').className='ok';
      $('#stat').textContent=`${d.data.version}  -  ${d.data.faces} screen(s) connected`; }
    else { $('#dot').className='bad'; $('#stat').textContent=`board unreachable - ${d.error}`; }
  }catch(e){ $('#dot').className='bad'; $('#stat').textContent='panel cannot reach the board'; }
}
poll(); setInterval(poll,4000);
say('panel ready');
</script></body></html>"""
