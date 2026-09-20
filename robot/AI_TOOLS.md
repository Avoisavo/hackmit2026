# Go2 AI tool map

The dashboard at `/` (redirects to `/plane`) shows this map and offers a JSON
download. `GET /api/ai/tools` returns the exact strict function schemas used by
`ai_agent.py`, plus the complete manual movement catalogue and component APIs.
The catalogue is authenticated with `X-Control-Token` like the other control APIs.

| AI tool | Arguments (all required) | Effect |
| --- | --- | --- |
| `speak` | `text`: 1–400 printable characters; `reason`: text | ElevenLabs speech through the paired speaker; waits for actual browser playback completion. |
| `listen` | `seconds`: 1–20; `reason`: text | One final Deepgram transcript or a timeout; never listens while speaking. |
| `move_robot` | `direction`: `forward`, `turn_left`, `turn_right`; `seconds`: 0.1–1; `speed`: 0.1–0.3; `reason`: text | Prepare stance, apply a bounded joystick input, then stop. Speed is a joystick fraction, not metres per second. |
| `set_posture` | `posture`: `stand`, `balance`, `lie`; `reason`: text | Use the existing posture controller; finish disarmed. |
| `perform_trick` | `action`: `hello`, `stretch`, `heart`, `content`, `scrape`, `wiggle_hips`, `sit`, `rise_sit`, `dance1`, `dance2`; `reason`: text | Run one supported action, wait its configured duration, finish disarmed. Firmware can refuse an action or mode. |
| `wait` | `seconds`: 0.2–2; `reason`: text | Remain stopped for the requested time. |
| `finish` | `reason`: text | End the camera-agent run and stop. |

`reason` is 1–240 printable characters. No extra arguments are accepted. The AI
receives these seven tools. Flips, held poses and mode changes remain manual.
The HARE presenter demos separately offer the tested forward jump with an explicit
clear-path selection; the camera AI does not receive a jumping tool. Backward and sideways motion remain on the manual joystick;
the camera agent cannot see a clear path behind or beside the robot.

## Dispatch a tool

Use `catalogue["tools"]` as the OpenAI Responses request `tools` field, with
`parallel_tool_calls=False`. Keep credentials, the operator control ID and STOP
epoch in your server-side executor. The model returns only the tool name and
arguments. The existing camera agent already runs that model/tool loop with fresh
Go2 images. This endpoint lets another coordinator use the same actuator guard:

```http
POST /api/ai/call
X-Control-Token: <operator token>
Content-Type: application/json

{
  "name": "move_robot",
  "arguments": {
    "direction": "forward",
    "seconds": 0.3,
    "speed": 0.15,
    "reason": "The operator requested a short step into visible clear space"
  },
  "run_id": "unique_tool_call_0001",
  "control_id": "<ready.control_id from the operator WebSocket>",
  "control_epoch": 12
}
```

The response is an accepted run **snapshot**, not completed motion. Poll
`GET /api/ai/status` until `busy` is false; check the matching `run_id`, `phase`
and `steps[-1].result`. Only an `accepted` result means the command was accepted;
a camera frame or physical check is still needed to assess what moved. Send the
result to the model as `function_call_output` with its original `call_id`.
`finish` ends a model loop in the caller; the single-call endpoint only ends its
own one-tool run.

`run_id` must be 16–80 ASCII letters/digits/underscores/hyphens. Reusing one of the
64 most recently accepted IDs does not replay a movement. A duplicate response
identifies `requested_run_id` and may describe a newer current run; never treat
that newer run's result as the old call's result. This memory resets at server
restart. Do not automatically retry an uncertain motion after restart.

The operator WebSocket is `/ws/control?token=<token>` with the same Origin as the
server. Use the control ID from its `ready` event and the current `stop_epoch`
from `/api/status`. The existing dashboard maintains the required 100 ms zero
input heartbeats **only while focused**. Do not synthesize a headless keepalive
or refresh the epoch to bypass a STOP. Connection/ownership changes or missing
heartbeats reject or interrupt the tool; one owner and one tool run at a time.

For the existing autonomous camera loop, `POST /api/ai/start` accepts `goal`,
`run_id`, `control_id`, and `control_epoch`, and uses the saved OpenAI key. The
single-tool dispatch endpoint itself makes no OpenAI API request.

## Component API table

| Method and route | JSON body | What it does |
| --- | --- | --- |
| `GET /api/ai/tools` | — | Schemas, limits, movement catalogue, component map. |
| `POST /api/ai/call` | Tool call plus control context shown above | Execute one guarded robot tool asynchronously. |
| `GET /api/ai/status` | — | Current tool/model run and results. |
| `POST /api/plane/test` | `{"kind":"tone", "control_id":"…", "control_epoch":12}` | A 0.8 s tone through the enabled browser speaker (Mac → selected speaker), no API key or robot connection. |
| `POST /api/plane/test` | `{"kind":"voice", "control_id":"…", "control_epoch":12}` | Fixed ElevenLabs sentence through the enabled browser speaker. Needs key and voice ID. |
| `POST /api/plane/test` | `{"kind":"microphone", "control_id":"…", "control_epoch":12}` | Listen on the enabled mic (selected microphone → Mac) for 20 s; show Deepgram transcripts without grading or movement. |
| `GET /api/plane/status` | — | Activity, current test, speaker readiness, device and credential readiness (no secrets). |
| `POST /api/plane/face` | `{"name":"Celebrate"}` | Update preview and paired Arduino screen while activity is idle. |
| `POST /api/vision/round` | `{"target_object":"toy blocks", "target_count":3}` | Set the category and count for a standalone camera test. |
| `POST /api/vision/scan` | `{}` | Count the selected category from two current Go2 images; needs OpenAI. |
| `POST /api/stop` | `{}` | Cancel activity, pending motion and sound; disarm. Does not require camera or control context. |

Faces: `Ready`, `Watching`, `Encourage`, `Thinking`, `Go`, `Celebrate`, `Rest`,
`Soft confused`. Component test routes are operator diagnostics, not additional
functions silently added to the AI's movement tool set.

Manual posture/action endpoints and mode compatibility are listed in the JSON
`movements` table and Advanced robot controls at `/controls`. Use the guarded
tool dispatcher for AI movement: the older manual trick endpoints may schedule
automatic recovery and rearm. Never substitute them for a rejected AI tool.

Select the desired microphone and Whammo as the Mac's sound output, then click **Use this
microphone** and **Use this computer’s speaker** in the dashboard. The Go2 Air
installation plays audio through that browser speaker. Tests use the same scoped
device session and playback acknowledgements as the activity. They work without
a robot connection but require current operator control context. STOP cancels
browser playback and invalidates pending speech. Playback completion does not
prove audibility; confirm the tone through Whammo before starting the lesson.

## Audio tools without a robot connection

`POST /api/plane/call` accepts the same `name`, `arguments`, `run_id`,
`control_id`, and `control_epoch` envelope, but only for `speak` and `listen`.
It requires the live focused operator WebSocket, without requiring a Go2 camera.
The autonomous camera-agent loop executes the same functions through
`/api/ai/start`; that loop and `/api/ai/call` retain camera and robot guards.

```json
{
  "name": "speak",
  "arguments": {"text": "Put three blue blocks on the mat.", "reason": "Introduce the block mission"},
  "run_id": "unique_audio_call_0001",
  "control_id": "<current operator WebSocket owner>",
  "control_epoch": 12
}
```

For a microphone call, use `"name":"listen"` and
`"arguments":{"seconds":10,"reason":"Hear one learner answer"}`.
Poll `/api/plane/status` → `audio_tool` for the matching `run_id` and a terminal
`status` (`complete` or `stopped`). Results are `{played:true,
audibility_verified:false,text:...}` or `{heard:true,transcript:...}`; a timeout
returns `{heard:false,transcript:"",timed_out:true}`. Forward that result as the
model's `function_call_output`. Neither a transcript nor playback completion is
proof of a physical block placement. No recording is stored.

Duplicate accepted run IDs do not repeat audio. The duplicate response includes
`requested_run_id`; the current `audio_tool` may belong to a newer call, so match
IDs before consuming a result. Busy operations cannot overlap. STOP invalidates
queued audio and listening windows; a spoken stop also cancels the owning AI run.

## HARE demo coordinator

`POST /api/plane/start` additionally accepts `demo`: `count_check`, `run_play`,
`soft_hands`, `close`, or `backup`; `rehearsal`: boolean; and `motion`: `screen`
or `robot_gestures`, plus the existing control context. All three demos support
event-driven choreography: Content after the five-object mission, five Hellos for
the maths game, and Heart after confirmed gentle care. Demo 2 turns with heading feedback.
Demo 2 can replace its five-Hello celebration with one forward jump when
`jump_clearance:true` explicitly confirms a clear landing area. It defaults to
false and is ignored outside physical Demo 2. Caption rehearsal only permits
screen motion. Poll `demo.action` and `demo.actions_completed` for gesture status.
`demo.movement_reason` explains the current planned movement.

`POST /api/plane/event` accepts `session_id`, unique `event_id`, and `event`:
`count` (with integer `count`), `learner_left`, `bump`, or `gentle`.
These are operator-only presenter cues, not model tools. They cannot override
STOP, substitute for camera evidence, or skip a step. See [HARE_DEMO.md](HARE_DEMO.md).
Use `demo.cues[event].enabled` and `demo.next_step` to render the current controls.
Known but unavailable cues return current state with `demo.cue_feedback.status`
set to `ignored`, without changing the lesson. A gentle cue during its spoken
prompt returns `queued` and runs after playback; STOP discards it. Invalid sessions,
control contexts or unknown cue names still fail validation.

Function schema reference: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling).
