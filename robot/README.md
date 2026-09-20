# Go2 controls and object vision

This local Python service owns one Go2 WebRTC connection. `/` controls the robot;
`/vision` reuses its built-in camera for specific object names and a counting game.
The vision service does not issue motion commands.

## Run

Use Python 3.12 and run from the repository root:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r robot/requirements-vision.txt
mkdir -p robot/models
curl --fail --location https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11s.pt --output robot/models/yolo11s.pt
ROBOT_IP=<robot-ip> .venv/bin/python -m uvicorn app:app --app-dir robot --host 127.0.0.1 --port 8000 --no-access-log
```

Keep one server/robot client open. Visit `http://127.0.0.1:8000/`, connect the robot,
then open **camera object recognition**. Enter an OpenAI key in the password field
under **OpenAI connection**; it stays in server memory until shutdown. Alternatively,
supply `OPENAI_API_KEY` from an existing secret manager. Do not put a key in browser
code, shell commands, Git, or logs. `OPENAI_VISION_MODEL` overrides `gpt-4.1-mini`.

**Check this scene** sends two fresh images to OpenAI and displays item names and
counts. **Start auto-check** repeats after an 8-second pause between scans, at most
30 scans per batch. Each scan makes two image requests. Hiding/leaving the page
stops sampling; a request already in flight finishes but cannot publish after stop.
Images are not written to disk by this feature. They are sent to OpenAI for analysis.

**Object boxes** is on by default on both pages. A local YOLO11s detector draws
colored rectangles, labels, and confidence on the exact frame it analyzed, at up
to 10 frames/second. The model uses common object categories; it does not recognize
every possible object. OpenAI's detailed scene inventory is separate. A single
worker serves all viewers, using the latest camera frame and discarding stale
results after disconnect/reconnect. Predictions below 50% confidence are hidden.
Turn boxes off to restore raw video.
`GO2_DETECTOR_WEIGHTS` can point to a checkpoint outside the repository. Model
files and Python caches are ignored by Git. The broader YOLOE prompt-free model
was evaluated on this robot view and rejected because its labels were inaccurate.
YOLO11n also confused an overhead staircase with an airplane; the stronger YOLO11s
removed that false label on three live sample frames while retaining people/chairs.

Drive from the controls page while watching its boxed camera view. Switching
tabs/windows disarms driving. After a server restart, use **Refresh control
session**, then **Enable movement** when ready. Refresh never arms automatically.
Only one controls tab can own driving. If this tab reports that another dashboard
owns control, use that existing tab or close the other controls tabs and click
**Reconnect this tab**. A rejected tab cannot enable movement, and its background
events do not stop the owning tab. The explicit **STOP** button still stops globally.
Tricks pause driving. After the trick finishes and the robot is back in its normal
standing pose, use **Resume driving** beside the tricks, then press a fresh movement
key. Sitting or balancing tricks may need their corresponding exit/rise command
first. A held key from before Resume cannot start motion through auto-repeat.

The activity accepts an object description such as `red toy cars` and a goal from
1–20. It grades numeric answers locally, using two clear agreeing target counts.
Camera counts remain estimates; clutter, occlusion, and the wide-angle lens can
cause mistakes. Unknown or stale counts cannot grade an answer. Correctly answering
“how many more” is distinct from physically completing the arrangement.

## Voice and expression integration

ZW/HB can poll `GET /api/vision/status` from a process on the same Mac. All API
requests require `X-Control-Token`, the current page's `token` variable. The token
changes on restart. Never create another WebRTC connection to obtain camera data.
The service is bound to localhost, so teammates' other computers cannot call it
directly. No voice, Arduino, or parent-stream transport is included here.

| Endpoint | Body / purpose |
| --- | --- |
| `POST /api/vision/round` | `{"target_object":"toy cars","target_count":3}` |
| `POST /api/vision/scan` | `{}` — one scan |
| `POST /api/vision/start` | `{}` — bounded automatic sampling |
| `POST /api/vision/stop` | `{}` — stop sampling |
| `POST /api/vision/answer` | `{"answer":1,"round_id":"<current>","observation_id":12}` |

Status includes `observation.objects` (`label`, `count`), `observation_fresh`,
`observation.stable`, `lesson.suggested_speech`, and `last_event` with `event`
(`happy`/`try_again`), `correct`, `task_complete`, and `event_id`. `round_id` is a
string; `observation_id` is an integer or null. Bind an answer to the IDs of the
question actually presented, not IDs fetched after the child answered. A changed
scene/round returns 409. Recount rather than treating that response as a wrong answer.
Deduplicate prompts by observation ID and answer feedback by event ID. Always check
freshness; it can expire without a revision change.

## Offline tests

```sh
.venv/bin/python -m pip install -r robot/requirements-dev.txt
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s robot/tests -v
node --test robot/tests/*.test.cjs
```

Tests use fake camera/provider/robot transports and do not contact hardware or OpenAI.
