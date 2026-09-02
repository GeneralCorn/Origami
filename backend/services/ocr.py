"""On-device OCR, kept apart from the vision model.

Until this module existed the VLM did two jobs in one call: read the text
off the screenshot and describe the picture. A 7B vision model transcribes
slowly, drops lines on dense screens, and paraphrases where it cannot read.
Text recognition is a solved, deterministic, local problem, so it moves to
an engine built for it and the VLM keeps only the job that needs a model.

PRODUCT_DIRECTION.md fixes the order of evaluation: the macOS Vision
framework first, because it is on-device, free and already present on the
only platform the app ships for; a PaddleOCR-family engine second, for
machines without it. Both are behind one protocol so the rest of the
pipeline never learns which one ran, beyond the name recorded on every
segment it produces.
"""

import asyncio
import importlib.util
import json
import logging
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from config import OCR_DIR, OCR_ENGINE
from services.images import image_size

logger = logging.getLogger(__name__)

VLM_ENGINE = "vlm"


class OcrError(RuntimeError):
    """The engine ran and could not read the image."""


@dataclass(frozen=True)
class OcrLine:
    """One recognised line with a normalised box, top-left origin."""

    text: str
    confidence: float
    box: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class OcrResult:
    engine: str
    lines: tuple[OcrLine, ...]
    width: int
    height: int
    elapsed_s: float

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())

    @property
    def line_texts(self) -> list[str]:
        return [line.text for line in self.lines if line.text.strip()]

    @property
    def mean_confidence(self) -> float:
        scored = [line.confidence for line in self.lines if line.text.strip()]
        return round(sum(scored) / len(scored), 4) if scored else 0.0

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "width": self.width,
            "height": self.height,
            "elapsed_s": round(self.elapsed_s, 4),
            "mean_confidence": self.mean_confidence,
            "lines": [asdict(line) | {"box": list(line.box)} for line in self.lines],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OcrResult":
        lines = tuple(
            OcrLine(
                text=str(line.get("text", "")),
                confidence=float(line.get("confidence", 0.0)),
                box=tuple(float(v) for v in line.get("box", (0.0, 0.0, 1.0, 1.0))),  # type: ignore[arg-type]
            )
            for line in data.get("lines", [])
        )
        return cls(
            engine=str(data.get("engine", "")),
            lines=lines,
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            elapsed_s=float(data.get("elapsed_s", 0.0)),
        )

    @classmethod
    def from_text(cls, text: str, *, engine: str, width: int = 0, height: int = 0) -> "OcrResult":
        """Wrap text that arrived without boxes, such as a VLM transcription.

        Confidence is zero because the source reported none, and a record
        that says so is more useful than one that guesses.
        """
        lines = tuple(OcrLine(text=part.strip(), confidence=0.0) for part in text.splitlines() if part.strip())
        return cls(engine=engine, lines=lines, width=width, height=height, elapsed_s=0.0)


class OcrEngine(Protocol):
    name: str

    def recognize(self, path: Path) -> OcrResult: ...


def reading_order(lines: list[OcrLine]) -> list[OcrLine]:
    """Sort detections top-to-bottom, then left-to-right within a row.

    Rows are bucketed by the median line height, so two boxes whose
    vertical centres differ by less than most of a line read as one row.
    """
    if len(lines) < 2:
        return list(lines)
    heights = sorted(max(line.box[3] - line.box[1], 1e-6) for line in lines)
    median = heights[len(heights) // 2]
    # Two boxes belong to one row when their centres sit closer than most
    # of a line. Clustering from the top rather than flooring into fixed
    # buckets, so a boundary never splits one row in two.
    tolerance = max(median * 0.7, 1e-6)

    def centre(line: OcrLine) -> float:
        return (line.box[1] + line.box[3]) / 2

    rows: list[list[OcrLine]] = []
    row_centre = 0.0
    for line in sorted(lines, key=centre):
        if rows and abs(centre(line) - row_centre) <= tolerance:
            rows[-1].append(line)
            row_centre = sum(centre(l) for l in rows[-1]) / len(rows[-1])
        else:
            rows.append([line])
            row_centre = centre(line)
    ordered: list[OcrLine] = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda l: l.box[0]))
    return ordered


# ── Engines ───────────────────────────────────────────────────────


class AppleVisionEngine:
    """VNRecognizeTextRequest through PyObjC. macOS only.

    Written against Apple's documented API and the ocrmac and RhetTbull
    reference wrappers rather than run on a Mac from this branch, so treat
    the adapter as [UNVERIFIED] until the smoke test in tests/test_ocr.py
    has passed on real hardware; see docs/SCREENSHOT_PIPELINE.md.
    """

    name = "apple_vision"

    @staticmethod
    def available() -> bool:
        return sys.platform == "darwin" and importlib.util.find_spec("Vision") is not None

    def recognize(self, path: Path) -> OcrResult:  # pragma: no cover - needs macOS
        import Vision  # type: ignore[import-not-found]

        started = time.perf_counter()
        width, height = image_size(path)
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(path.read_bytes(), None)
        if handler is None:
            raise OcrError(f"Vision could not decode {path.name}")

        request = Vision.VNRecognizeTextRequest.alloc().init()
        # 0 is VNRequestTextRecognitionLevelAccurate. Fast is for live video.
        request.setRecognitionLevel_(getattr(Vision, "VNRequestTextRecognitionLevelAccurate", 0))
        request.setUsesLanguageCorrection_(True)
        if request.respondsToSelector_("setAutomaticallyDetectsLanguage:"):
            request.setAutomaticallyDetectsLanguage_(True)

        outcome = handler.performRequests_error_([request], None)
        # PyObjC returns (ok, error) for the out-param signature on recent
        # bridges and a bare bool on older ones.
        ok, error = outcome if isinstance(outcome, tuple) else (outcome, None)
        if not ok:
            raise OcrError(f"Vision text request failed: {error}")

        lines: list[OcrLine] = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue
            candidate = candidates[0]
            text = str(candidate.string()).strip()
            if not text:
                continue
            # Vision boxes are normalised with the origin at the bottom left.
            box = observation.boundingBox()
            x, y = float(box.origin.x), float(box.origin.y)
            w, h = float(box.size.width), float(box.size.height)
            lines.append(OcrLine(
                text=text,
                confidence=float(candidate.confidence()),
                box=(x, 1.0 - (y + h), x + w, 1.0 - y),
            ))
        # Vision already returns reading order; the sort is a no-op on a
        # single column and a repair on the rare interleaved result.
        return OcrResult(
            engine=self.name,
            lines=tuple(lines),
            width=width,
            height=height,
            elapsed_s=time.perf_counter() - started,
        )


class RapidOcrEngine:
    """PP-OCRv6 through RapidOCR on ONNX Runtime. Every platform.

    The weights ship inside the wheel, so the first call costs about a
    third of a second of model loading and nothing is downloaded. The
    engine object is shared because each holds three ONNX sessions.
    """

    name = "rapidocr"
    _instance = None
    _lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("rapidocr") is not None

    @classmethod
    def _engine(cls):
        with cls._lock:
            if cls._instance is None:
                # RapidOCR logs every model it opens at INFO, in colour.
                for name in ("RapidOCR", "rapidocr"):
                    logging.getLogger(name).setLevel(logging.WARNING)
                from rapidocr import RapidOCR  # type: ignore[import-not-found]

                cls._instance = RapidOCR()
            return cls._instance

    def recognize(self, path: Path) -> OcrResult:
        started = time.perf_counter()
        output = self._engine()(str(path))
        width, height = image_size(path)
        img = getattr(output, "img", None)
        if (not width or not height) and img is not None and getattr(img, "shape", None):
            height, width = int(img.shape[0]), int(img.shape[1])

        lines: list[OcrLine] = []
        texts = getattr(output, "txts", None) or ()
        scores = getattr(output, "scores", None) or ()
        boxes = getattr(output, "boxes", None)
        boxes = list(boxes) if boxes is not None else []
        for index, text in enumerate(texts):
            text = str(text).strip()
            if not text:
                continue
            score = float(scores[index]) if index < len(scores) else 0.0
            box = (0.0, 0.0, 1.0, 1.0)
            if index < len(boxes) and width and height:
                xs = [float(point[0]) for point in boxes[index]]
                ys = [float(point[1]) for point in boxes[index]]
                box = (
                    max(0.0, min(xs) / width), max(0.0, min(ys) / height),
                    min(1.0, max(xs) / width), min(1.0, max(ys) / height),
                )
            lines.append(OcrLine(text=text, confidence=score, box=box))

        return OcrResult(
            engine=self.name,
            lines=tuple(reading_order(lines)),
            width=width,
            height=height,
            elapsed_s=time.perf_counter() - started,
        )


_ENGINES: dict[str, type] = {
    AppleVisionEngine.name: AppleVisionEngine,
    RapidOcrEngine.name: RapidOcrEngine,
}
_AUTO_ORDER = (AppleVisionEngine.name, RapidOcrEngine.name)


def resolve_engine(preference: str | None = None) -> OcrEngine | None:
    """The engine ORIGAMI_OCR_ENGINE asks for, or None when text must come from the VLM."""
    wanted = (preference if preference is not None else OCR_ENGINE).strip().lower()
    if wanted in ("off", "none", "vlm"):
        return None
    order = _AUTO_ORDER if wanted == "auto" else (wanted,)
    for name in order:
        engine_cls = _ENGINES.get(name)
        if engine_cls is None:
            logger.warning("Unknown OCR engine %r; known: %s", name, ", ".join(_ENGINES))
            continue
        if engine_cls.available():
            return engine_cls()
    if wanted != "auto":
        logger.warning("OCR engine %r requested but not available on this machine", wanted)
    else:
        logger.info("No on-device OCR engine available; screenshot text will come from the VLM")
    return None


_engine_lock = threading.Lock()
_engine: OcrEngine | None = None
_engine_resolved = False


def current_engine() -> OcrEngine | None:
    """The process-wide engine, resolved once."""
    global _engine, _engine_resolved
    with _engine_lock:
        if not _engine_resolved:
            _engine = resolve_engine()
            _engine_resolved = True
        return _engine


def override_engine(engine: OcrEngine | None, *, resolved: bool = True) -> None:
    """Pin the engine (tests, and a future settings screen). resolved=False re-resolves lazily."""
    global _engine, _engine_resolved
    with _engine_lock:
        _engine = engine
        _engine_resolved = resolved


def engine_name() -> str | None:
    engine = current_engine()
    return engine.name if engine else None


# OCR is CPU-bound and a batch of screenshots arrives at once. Two at a time
# keeps the event loop free and leaves a core for the embedder.
_ocr_semaphore = asyncio.Semaphore(2)


async def recognize(path: Path) -> OcrResult | None:
    """Read the text in one image off the event loop. None when no engine is configured."""
    engine = current_engine()
    if engine is None:
        return None
    async with _ocr_semaphore:
        result = await asyncio.to_thread(engine.recognize, path)
    logger.info(
        "OCR %s: %d lines in %.2fs via %s (mean confidence %.2f)",
        path.name, len(result.lines), result.elapsed_s, result.engine, result.mean_confidence,
    )
    return result


# ── The extraction record ─────────────────────────────────────────
#
# One JSON file per screenshot under OCR_DIR. It is what the pipeline
# learned from the image in a form a person can read and a rebuild can
# re-index without running OCR or the VLM again.


def record_path(screenshot_name: str) -> Path:
    path = (OCR_DIR / f"{screenshot_name}.json").resolve()
    if path.parent != OCR_DIR.resolve():
        raise ValueError(f"Invalid screenshot name: {screenshot_name!r}")
    return path


def save_record(screenshot_name: str, record: dict) -> Path:
    path = record_path(screenshot_name)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_record(screenshot_name: str) -> dict | None:
    path = record_path(screenshot_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unreadable OCR record for %s: %s", screenshot_name, exc)
        return None


def delete_record(screenshot_name: str) -> bool:
    path = record_path(screenshot_name)
    if path.exists():
        path.unlink()
        return True
    return False
