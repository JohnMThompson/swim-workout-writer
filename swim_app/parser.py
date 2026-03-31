from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageOps
import pytesseract

from .locations import get_canonical_locations
from .models import StrokeMapping

DATE_RE = re.compile(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+([A-Z][a-z]{2})\s+(\d{1,2})")
TIME_RANGE_RE = re.compile(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})")
DURATION_RE = re.compile(r"(\d+):(\d{2}):(\d{2})")
DISTANCE_RE = re.compile(r"(\d+)\s*Y[A-Z]?D", re.IGNORECASE)
DISTANCE_LABEL_RE = re.compile(
    r"Distance\s+(\d+)\s*Y[A-Z]?D", re.IGNORECASE
)
STROKE_RE = re.compile(
    r"(Freestyle|Breaststroke|Backstroke|Butterfly|Kickboard)\s*\((\d+)yd\)",
    re.IGNORECASE,
)

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

@dataclass
class ParseResult:
    workout_date: str = ""
    start_time: str = ""
    end_time: str = ""
    duration: int = 0
    total_distance_yards: int = 0
    location: str = ""
    comments: str = ""
    freestyle_distance: int = 0
    breaststroke_distance: int = 0
    backstroke_distance: int = 0
    butterfly_distance: int = 0
    raw_strokes: list[dict[str, str | int]] = field(default_factory=list)
    unknown_strokes: list[str] = field(default_factory=list)
    ocr_text: str = ""

    def to_dict(self) -> dict:
        return {
            "workout_date": self.workout_date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "total_distance_yards": self.total_distance_yards,
            "location": self.location,
            "comments": self.comments,
            "freestyle_distance": self.freestyle_distance,
            "breaststroke_distance": self.breaststroke_distance,
            "backstroke_distance": self.backstroke_distance,
            "butterfly_distance": self.butterfly_distance,
            "raw_strokes": self.raw_strokes,
            "unknown_strokes": self.unknown_strokes,
            "ocr_text": self.ocr_text,
        }


def extract_text(image_path: str | Path) -> str:
    image = Image.open(image_path)
    grayscale = ImageOps.grayscale(image)
    widened = grayscale.resize((grayscale.width * 2, grayscale.height * 2))
    inverted = ImageOps.invert(widened)
    return pytesseract.image_to_string(inverted, config="--psm 6")


def parse_workout(image_path: str | Path, submission_date: date | None = None) -> ParseResult:
    text = extract_text(image_path)
    normalized = " ".join(text.split())
    result = ParseResult(ocr_text=text)

    if match := DATE_RE.search(normalized):
        month = MONTHS[match.group(2)]
        day = int(match.group(3))
        year = (submission_date or date.today()).year
        result.workout_date = date(year, month, day).isoformat()

    if match := TIME_RANGE_RE.search(normalized):
        result.start_time = match.group(1)
        result.end_time = match.group(2)

    durations = DURATION_RE.findall(normalized)
    if durations:
        hours, minutes, seconds = durations[0]
        result.duration = _rounded_minutes(int(hours), int(minutes), int(seconds))

    distances = [int(value) for value in DISTANCE_RE.findall(normalized)]
    if distances:
        result.total_distance_yards = _extract_total_distance(normalized, distances)

    location = _extract_location(normalized)
    if location:
        result.location = location

    _apply_strokes(result, normalized)
    return result


def _extract_location(text: str) -> str:
    normalized_text = _normalize_location_text(text)
    for location in get_canonical_locations():
        if _normalize_location_text(location) in normalized_text:
            return location
    return ""


def _apply_strokes(result: ParseResult, text: str) -> None:
    mappings = {
        mapping.source_label.lower(): mapping.target_stroke.lower()
        for mapping in StrokeMapping.query.all()
    }
    totals = {
        "freestyle": 0,
        "breaststroke": 0,
        "backstroke": 0,
        "butterfly": 0,
    }
    unknown = set()
    for label, yards in STROKE_RE.findall(text):
        clean_label = label.lower()
        result.raw_strokes.append({"label": label, "yards": int(yards)})
        target = mappings.get(clean_label)
        if not target:
            unknown.add(label)
            continue
        totals[target] += int(yards)

    result.freestyle_distance = totals["freestyle"]
    result.breaststroke_distance = totals["breaststroke"]
    result.backstroke_distance = totals["backstroke"]
    result.butterfly_distance = totals["butterfly"]
    result.unknown_strokes = sorted(unknown)


def _extract_total_distance(text: str, distances: list[int]) -> int:
    if match := DISTANCE_LABEL_RE.search(text):
        return int(match.group(1))

    stroke_totals = [int(yards) for _, yards in STROKE_RE.findall(text)]
    if stroke_totals:
        stroke_sum = sum(stroke_totals)
        if stroke_sum in distances:
            return stroke_sum
        if stroke_sum > max(distances):
            return stroke_sum

    return max(distances)


def build_start_datetime(workout_date: str, start_time: str) -> datetime:
    return datetime.strptime(f"{workout_date} {start_time}", "%Y-%m-%d %H:%M")


def _rounded_minutes(hours: int, minutes: int, seconds: int) -> int:
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return int((total_seconds + 30) // 60)


def _normalize_location_text(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())
