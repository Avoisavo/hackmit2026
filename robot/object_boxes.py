"""Local object localization and overlays on the exact supplied camera frame."""

import io
import math
import os
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class ObjectBoxError(RuntimeError):
    """A concise detector failure safe to show in the dashboard."""


class ObjectBoxDetector:
    def __init__(self, weights_path: str, confidence: float = .5):
        if (type(confidence) not in (int, float) or not math.isfinite(confidence)
                or not 0 < confidence <= 1):
            raise ValueError("Detector confidence must be a finite number greater than 0 and at most 1.")
        self.weights_path = Path(weights_path).expanduser()
        self.confidence = float(confidence)
        self._model = None
        self._device = "cpu"
        self._lock = threading.Lock()

    def _load(self):
        if self._model is not None:
            return
        if not self.weights_path.is_file():
            raise ObjectBoxError("Object detector weights are missing. Install the configured model first.")
        # Keep library settings and font caches beside the externally stored weights.
        try:
            if "YOLO_CONFIG_DIR" not in os.environ:
                config = self.weights_path.parent / ".ultralytics"
                config.mkdir(parents=True, exist_ok=True)
                os.environ["YOLO_CONFIG_DIR"] = str(config)
            os.environ.setdefault("MPLCONFIGDIR", str(self.weights_path.parent / ".matplotlib"))
            import torch
            from ultralytics import YOLO, YOLOE

            self._device = "mps" if torch.backends.mps.is_available() else "cpu"
            loader = YOLOE if self.weights_path.name.lower().startswith("yoloe-") else YOLO
            self._model = loader(str(self.weights_path), verbose=False)
        except Exception:
            raise ObjectBoxError("The local object detector could not load its model.") from None

    def _predict(self, image):
        options = dict(source=image.copy(), imgsz=640, conf=self.confidence, iou=.6,
                       max_det=30, agnostic_nms=True, nms=True,
                       verbose=False, save=False, stream=False)
        try:
            return self._model.predict(device=self._device, **options)
        except Exception:
            if self._device != "mps":
                raise ObjectBoxError("The local object detector could not analyze this frame.") from None
        # Ultralytics caches a predictor; reset it when changing its device.
        self._device = "cpu"
        try:
            self._model.to("cpu")
            self._model.predictor = None
            return self._model.predict(device="cpu", **options)
        except Exception:
            raise ObjectBoxError("The local object detector could not analyze this frame.") from None

    def detect(self, jpeg: bytes) -> dict:
        """Return only real detector boxes, painted onto this exact decoded JPEG.

        Model imports and loading happen on the first valid frame. This blocking
        method serializes model access; callers should run it in a worker thread.
        No image is written to disk and missing weights are never auto-downloaded.
        """
        try:
            if not isinstance(jpeg, bytes) or not 4 <= len(jpeg) <= 8 * 1024 * 1024:
                raise ValueError("Invalid input size")
            with Image.open(io.BytesIO(jpeg)) as decoded:
                if decoded.format != "JPEG" or decoded.width * decoded.height > 8_000_000:
                    raise ValueError("Invalid image type or dimensions")
                image = decoded.convert("RGB")
        except Exception:
            raise ObjectBoxError("A valid camera JPEG of at most 8 megapixels is required.") from None
        with self._lock:
            self._load()
            results = self._predict(image)
            try:
                if len(results) != 1:
                    raise ValueError("Expected one source frame")
                detections = _detections(results[0], image.width, image.height, self.confidence)
            except Exception:
                raise ObjectBoxError("The local object detector returned invalid boxes.") from None
            device = self._device
        _draw(image, detections)
        output = io.BytesIO()
        image.save(output, "JPEG", quality=88)
        return {"jpeg": output.getvalue(), "detections": detections,
                "width": image.width, "height": image.height, "device": device}


def _overlap(first, second):
    ax, ay, bx, by = first
    cx, cy, dx, dy = second
    intersection = max(0, min(bx, dx) - max(ax, cx)) * max(0, min(by, dy) - max(ay, cy))
    union = (bx - ax) * (by - ay) + (dx - cx) * (dy - cy) - intersection
    return intersection / union if union > 0 else 0


def _detections(result, width, height, minimum_confidence):
    if result.boxes is None:
        return []
    rows = result.boxes.xyxy.cpu().tolist()
    scores = result.boxes.conf.cpu().tolist()
    classes = result.boxes.cls.cpu().tolist()
    if not len(rows) == len(scores) == len(classes):
        raise ValueError("Mismatched box arrays")
    candidates = []
    for row, score, category in zip(rows, scores, classes):
        try:
            if len(row) != 4:
                continue
            x1, y1, x2, y2 = map(float, row)
            confidence = float(score)
            class_id = int(category)
            if (not all(math.isfinite(value) for value in (x1, y1, x2, y2, confidence))
                    or not minimum_confidence <= confidence <= 1 or float(category) != class_id):
                continue
            label = result.names[class_id]
            if not isinstance(label, str):
                continue
            label = " ".join("".join(char if char.isprintable() else " " for char in label).split())
            label = label[:45] + "..." if len(label) > 48 else label
            if not label:
                continue
            x1, x2 = max(0., min(width, x1)), max(0., min(width, x2))
            y1, y2 = max(0., min(height, y1)), max(0., min(height, y2))
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            # Prompt-free models sometimes propose the entire scene as an object.
            # Keep large close objects, but omit boxes covering essentially every pixel.
            if (x2 - x1) * (y2 - y1) > .95 * width * height:
                continue
        except (TypeError, ValueError, OverflowError, IndexError, KeyError):
            continue
        candidates.append({"label": label, "confidence": round(confidence, 4),
                           "xyxy": [round(x1 / width, 6), round(y1 / height, 6),
                                    round(x2 / width, 6), round(y2 / height, 6)]})
    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    kept = []
    for candidate in candidates:
        if any(_overlap(candidate["xyxy"], previous["xyxy"]) > .6 for previous in kept):
            continue
        kept.append(candidate)
        if len(kept) == 30:
            break
    return kept


def _draw(image, detections):
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(12, min(20, round(image.width / 60))))
    colors = [(40, 238, 222), (185, 245, 65), (192, 141, 255)]
    thickness = max(2, round(image.width / 320))
    for index, item in enumerate(detections):
        color = colors[index % len(colors)]
        x1, y1, x2, y2 = item["xyxy"]
        x1, y1 = round(x1 * image.width), round(y1 * image.height)
        x2, y2 = min(image.width - 1, round(x2 * image.width)), min(image.height - 1, round(y2 * image.height))
        draw.rectangle((x1, y1, x2, y2), outline=color, width=max(1, thickness // 2))
        corner = max(2, min(20, (x2 - x1) // 3, (y2 - y1) // 3))
        for x, y, dx, dy in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
            draw.line([(x, y + dy * corner), (x, y), (x + dx * corner, y)], fill=color, width=thickness + 1)
        name = item["label"]
        confidence = f"  {item['confidence']:.0%}"
        while len(name) > 1 and draw.textlength(name + confidence, font=font) > image.width - 12:
            name = name[:-1]
        if len(name) < len(item["label"]) and len(name) > 3:
            name = name[:-3] + "..."
        label = name + confidence
        bounds = draw.textbbox((0, 0), label, font=font)
        chip_width = min(image.width, math.ceil(draw.textlength(label, font=font)) + 12)
        chip_height = min(image.height, bounds[3] - bounds[1] + 10)
        left = max(0, min(x1, image.width - chip_width))
        top = max(0, min(y1 - chip_height, image.height - chip_height))
        draw.rounded_rectangle((left, top, left + chip_width - 1, top + chip_height - 1), radius=4, fill=color)
        draw.text((left + 6, top + 5 - bounds[1]), label, font=font, fill=(10, 22, 29))
