# HARE control plane on dog

Start `./robot/start-control-plane.sh` from this checkout, then open
<http://127.0.0.1:8020/plane>. The launcher loads the ignored `.env.local`.
See [HARE_DEMO.md](HARE_DEMO.md) for the three demos, presenter keys, motion modes,
and hardware fallback, and [AI_TOOLS.md](AI_TOOLS.md) for speech/listening tools.

## Go2 controls with camera vision

This branch combines the existing configurable-IP controls and automatic trick
recovery with the object vision components from
[`muthu` at `36e19e6`](https://github.com/Avoisavo/hackmit2026/tree/36e19e6/robot).

- `/controls`: current driving and trick controls, with live YOLO11s object boxes on
  the camera feed and a raw-video toggle.
- `/vision`: Look & Count, including scene inventory, counting goals and
  optional OpenAI scene checks.
- Both pages share one robot connection. Vision does not issue motion commands.

Start the correct copy from any directory:

```sh
~/dimensional-applications/.venv/bin/python -m uvicorn app:app --app-dir ~/Developer/hackmit2026/robot --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/controls, enter the robot's current IP and connect. The camera
shows object boxes by default. Local detection needs `requirements-vision.txt`
and `robot/models/yolo11s.pt`; detailed scene checks additionally need an OpenAI
API key entered on `/vision` or supplied through `OPENAI_API_KEY`.

See [run.md](run.md) for setup, controls, camera behavior, testing and
troubleshooting. Restart the server after Python changes, then reload the page.
