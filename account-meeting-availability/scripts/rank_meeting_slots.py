#!/usr/bin/env python3
"""Deterministically rank meeting slots from read-only Outlook free/busy data."""

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from email_validation import validate_practical_email


REQUEST_SCHEMA = "account-meeting-availability/free-busy-request"
RESULT_SCHEMA = "account-meeting-availability/free-busy-result"
SCHEMA_VERSION = "1.0"
MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_WINDOW_DAYS = 31
MAX_PARTICIPANTS = 100
MAX_INTERVALS_PER_PARTICIPANT = 1000
PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
PRIVATE_DIRECTORY_MODE = stat.S_IRWXU

RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
WALL_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DAY_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
BUSY_STATUSES = {
    "free",
    "tentative",
    "busy",
    "out_of_office",
    "working_elsewhere",
    "unknown",
}


@dataclass(frozen=True)
class BusyInterval:
    start: datetime
    end: datetime
    status: str


@dataclass(frozen=True)
class WorkingHours:
    days: frozenset[int]
    start: wall_time
    end: wall_time


@dataclass(frozen=True)
class Participant:
    participant_id: str
    email: str
    required: bool
    time_zone_name: str
    time_zone: ZoneInfo
    working_hours: WorkingHours
    busy_intervals: tuple[BusyInterval, ...]


@dataclass(frozen=True)
class RankingRequest:
    request_id: str
    window_start: datetime
    window_end: datetime
    slot_duration_minutes: int
    slot_increment_minutes: int
    max_results: int
    participants: tuple[Participant, ...]
    source_retrieved_at: datetime


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON contains duplicate key '{key}'")
        result[key] = value
    return result


def _require_object(value, context: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _require_keys(
    value: dict,
    *,
    required: set[str],
    optional=None,
    context: str,
) -> None:
    optional = optional or set()
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise ValueError(f"{context} is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{context} has unsupported field(s): {', '.join(unknown)}")


def _require_string(value, context: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{context} exceeds {max_length} characters")
    return normalized


def _require_integer(value, context: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{context} must be an integer from {minimum} to {maximum}")
    return value


def parse_rfc3339(value, context: str) -> datetime:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        raise ValueError(f"{context} must be an RFC 3339 timestamp with an explicit offset")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{context} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{context} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def parse_wall_time(value, context: str) -> wall_time:
    if not isinstance(value, str) or not WALL_TIME_RE.fullmatch(value):
        raise ValueError(f"{context} must use 24-hour HH:MM format")
    hour, minute = (int(part) for part in value.split(":", 1))
    return wall_time(hour=hour, minute=minute)


def format_utc(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    timespec = "microseconds" if normalized.microsecond else "seconds"
    return normalized.isoformat(timespec=timespec).replace("+00:00", "Z")


def format_local(value: datetime, zone: ZoneInfo) -> str:
    normalized = value.astimezone(zone)
    timespec = "microseconds" if normalized.microsecond else "seconds"
    return normalized.isoformat(timespec=timespec)


def _parse_working_hours(value, context: str) -> WorkingHours:
    payload = _require_object(value, context)
    _require_keys(
        payload,
        required={"days", "start", "end"},
        context=context,
    )
    days_value = payload["days"]
    if not isinstance(days_value, list) or not days_value:
        raise ValueError(f"{context}.days must be a non-empty array")
    day_indexes = []
    for index, day in enumerate(days_value):
        if not isinstance(day, str) or day not in DAY_TO_INDEX:
            raise ValueError(f"{context}.days[{index}] is not a supported weekday")
        day_indexes.append(DAY_TO_INDEX[day])
    if len(set(day_indexes)) != len(day_indexes):
        raise ValueError(f"{context}.days cannot contain duplicates")

    start = parse_wall_time(payload["start"], f"{context}.start")
    end = parse_wall_time(payload["end"], f"{context}.end")
    if end <= start:
        raise ValueError(f"{context} must end after it starts; overnight hours are not supported")
    return WorkingHours(frozenset(day_indexes), start, end)


def _parse_busy_intervals(value, context: str) -> tuple[BusyInterval, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    if len(value) > MAX_INTERVALS_PER_PARTICIPANT:
        raise ValueError(
            f"{context} exceeds the limit of {MAX_INTERVALS_PER_PARTICIPANT} intervals"
        )
    intervals = []
    for index, raw_interval in enumerate(value):
        interval_context = f"{context}[{index}]"
        interval = _require_object(raw_interval, interval_context)
        _require_keys(
            interval,
            required={"start", "end", "status"},
            context=interval_context,
        )
        start = parse_rfc3339(interval["start"], f"{interval_context}.start")
        end = parse_rfc3339(interval["end"], f"{interval_context}.end")
        if end <= start:
            raise ValueError(f"{interval_context}.end must be after start")
        status = interval["status"]
        if not isinstance(status, str) or status not in BUSY_STATUSES:
            raise ValueError(
                f"{interval_context}.status must be one of {', '.join(sorted(BUSY_STATUSES))}"
            )
        intervals.append(BusyInterval(start, end, status))
    return tuple(sorted(intervals, key=lambda item: (item.start, item.end, item.status)))


def parse_request(payload) -> RankingRequest:
    request = _require_object(payload, "request")
    _require_keys(
        request,
        required={
            "schema",
            "schema_version",
            "request_id",
            "window",
            "slot_duration_minutes",
            "slot_increment_minutes",
            "max_results",
            "participants",
            "source",
        },
        context="request",
    )
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError(f"request.schema must be '{REQUEST_SCHEMA}'")
    if request["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported request schema_version '{request['schema_version']}'; "
            f"this CLI supports '{SCHEMA_VERSION}'"
        )
    request_id = _require_string(request["request_id"], "request.request_id", max_length=128)

    window = _require_object(request["window"], "request.window")
    _require_keys(window, required={"start", "end"}, context="request.window")
    window_start = parse_rfc3339(window["start"], "request.window.start")
    window_end = parse_rfc3339(window["end"], "request.window.end")
    if window_end <= window_start:
        raise ValueError("request.window.end must be after start")
    if window_end - window_start > timedelta(days=MAX_WINDOW_DAYS):
        raise ValueError(f"request.window cannot exceed {MAX_WINDOW_DAYS} days")

    duration = _require_integer(
        request["slot_duration_minutes"],
        "request.slot_duration_minutes",
        minimum=5,
        maximum=1440,
    )
    increment = _require_integer(
        request["slot_increment_minutes"],
        "request.slot_increment_minutes",
        minimum=5,
        maximum=1440,
    )
    max_results = _require_integer(
        request["max_results"], "request.max_results", minimum=1, maximum=100
    )

    source = _require_object(request["source"], "request.source")
    _require_keys(
        source,
        required={"provider", "retrieval_mode", "retrieved_at"},
        context="request.source",
    )
    if source["provider"] != "outlook":
        raise ValueError("request.source.provider must be 'outlook'")
    if source["retrieval_mode"] != "read-only":
        raise ValueError("request.source.retrieval_mode must be 'read-only'")
    source_retrieved_at = parse_rfc3339(
        source["retrieved_at"], "request.source.retrieved_at"
    )

    participants_value = request["participants"]
    if not isinstance(participants_value, list) or not participants_value:
        raise ValueError("request.participants must be a non-empty array")
    if len(participants_value) > MAX_PARTICIPANTS:
        raise ValueError(f"request.participants exceeds the limit of {MAX_PARTICIPANTS}")

    participants = []
    seen_ids: set[str] = set()
    seen_emails: set[str] = set()
    for index, raw_participant in enumerate(participants_value):
        context = f"request.participants[{index}]"
        participant = _require_object(raw_participant, context)
        _require_keys(
            participant,
            required={
                "id",
                "email",
                "required",
                "time_zone",
                "working_hours",
                "busy_intervals",
            },
            context=context,
        )
        participant_id = _require_string(participant["id"], f"{context}.id", max_length=128)
        if participant_id in seen_ids:
            raise ValueError(f"duplicate participant id '{participant_id}'")
        seen_ids.add(participant_id)

        try:
            email = validate_practical_email(participant["email"])
        except ValueError as exc:
            raise ValueError(f"{context}.email: {exc}") from exc
        email_key = email.casefold()
        if email_key in seen_emails:
            raise ValueError(f"duplicate participant email '{email}'")
        seen_emails.add(email_key)

        if type(participant["required"]) is not bool:
            raise ValueError(f"{context}.required must be true or false")
        time_zone_name = _require_string(
            participant["time_zone"], f"{context}.time_zone", max_length=128
        )
        try:
            time_zone_value = ZoneInfo(time_zone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"{context}.time_zone is not an installed IANA time zone") from exc

        participants.append(
            Participant(
                participant_id=participant_id,
                email=email,
                required=participant["required"],
                time_zone_name=time_zone_name,
                time_zone=time_zone_value,
                working_hours=_parse_working_hours(
                    participant["working_hours"], f"{context}.working_hours"
                ),
                busy_intervals=_parse_busy_intervals(
                    participant["busy_intervals"], f"{context}.busy_intervals"
                ),
            )
        )

    if not any(participant.required for participant in participants):
        raise ValueError("request.participants must include at least one required participant")

    return RankingRequest(
        request_id=request_id,
        window_start=window_start,
        window_end=window_end,
        slot_duration_minutes=duration,
        slot_increment_minutes=increment,
        max_results=max_results,
        participants=tuple(participants),
        source_retrieved_at=source_retrieved_at,
    )


def _overlaps(start: datetime, end: datetime, interval: BusyInterval) -> bool:
    return start < interval.end and interval.start < end


def _inside_working_hours(participant: Participant, start: datetime, end: datetime) -> bool:
    local_start = start.astimezone(participant.time_zone)
    local_end = end.astimezone(participant.time_zone)
    if local_start.date() != local_end.date():
        return False
    if local_start.weekday() not in participant.working_hours.days:
        return False
    start_time = local_start.timetz().replace(tzinfo=None)
    end_time = local_end.timetz().replace(tzinfo=None)
    return (
        start_time >= participant.working_hours.start
        and end_time <= participant.working_hours.end
    )


def participant_is_available(participant: Participant, start: datetime, end: datetime) -> bool:
    if not _inside_working_hours(participant, start, end):
        return False
    return not any(
        interval.status != "free" and _overlaps(start, end, interval)
        for interval in participant.busy_intervals
    )


def rank_request(payload) -> dict:
    request = parse_request(payload)
    duration = timedelta(minutes=request.slot_duration_minutes)
    increment = timedelta(minutes=request.slot_increment_minutes)
    required = [participant for participant in request.participants if participant.required]
    optional = [participant for participant in request.participants if not participant.required]

    candidates = []
    cursor = request.window_start
    while cursor + duration <= request.window_end:
        end = cursor + duration
        if all(participant_is_available(participant, cursor, end) for participant in required):
            optional_available = [
                participant.participant_id
                for participant in optional
                if participant_is_available(participant, cursor, end)
            ]
            optional_unavailable = [
                participant.participant_id
                for participant in optional
                if participant.participant_id not in optional_available
            ]
            local_times = [
                {
                    "participant_id": participant.participant_id,
                    "time_zone": participant.time_zone_name,
                    "start": format_local(cursor, participant.time_zone),
                    "end": format_local(end, participant.time_zone),
                }
                for participant in request.participants
            ]
            candidates.append(
                {
                    "start": format_utc(cursor),
                    "end": format_utc(end),
                    "optional_available_count": len(optional_available),
                    "optional_available_participant_ids": optional_available,
                    "optional_unavailable_participant_ids": optional_unavailable,
                    "local_times": local_times,
                    "_sort_start": cursor,
                }
            )
        cursor += increment

    candidates.sort(key=lambda slot: (-slot["optional_available_count"], slot["_sort_start"]))
    eligible_slot_count = len(candidates)
    ranked_slots = []
    for rank, candidate in enumerate(candidates[: request.max_results], start=1):
        candidate = dict(candidate)
        candidate.pop("_sort_start")
        candidate["rank"] = rank
        ranked_slots.append(
            {
                "rank": candidate["rank"],
                "start": candidate["start"],
                "end": candidate["end"],
                "optional_available_count": candidate["optional_available_count"],
                "optional_available_participant_ids": candidate[
                    "optional_available_participant_ids"
                ],
                "optional_unavailable_participant_ids": candidate[
                    "optional_unavailable_participant_ids"
                ],
                "local_times": candidate["local_times"],
            }
        )

    status = "ranked" if ranked_slots else "no_common_slot"
    reason = (
        None
        if ranked_slots
        else "No slot satisfies every required participant's working hours and free/busy intervals."
    )
    return {
        "schema": RESULT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "request_id": request.request_id,
        "status": status,
        "reason": reason,
        "search_window": {
            "start": format_utc(request.window_start),
            "end": format_utc(request.window_end),
        },
        "slot_duration_minutes": request.slot_duration_minutes,
        "slot_increment_minutes": request.slot_increment_minutes,
        "required_participant_ids": [participant.participant_id for participant in required],
        "optional_participant_ids": [participant.participant_id for participant in optional],
        "eligible_slot_count": eligible_slot_count,
        "ranked_slots": ranked_slots,
        "source": {
            "provider": "outlook",
            "retrieval_mode": "read-only",
            "retrieved_at": format_utc(request.source_retrieved_at),
        },
    }


def read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds the {MAX_INPUT_BYTES}-byte limit")
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc


def write_json(path: Path, payload: dict) -> None:
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIRECTORY_MODE)
    if not parent_existed:
        os.chmod(path.parent, PRIVATE_DIRECTORY_MODE)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        os.chmod(temporary_name, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, PRIVATE_FILE_MODE)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank meeting slots from normalized, read-only Outlook free/busy intervals."
    )
    parser.add_argument("request", type=Path, help="Version 1.0 free/busy request JSON")
    parser.add_argument("--output", "-o", type=Path, help="Write result JSON instead of stdout")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        request_path = args.request.expanduser()
        if args.output and request_path.resolve() == args.output.expanduser().resolve():
            raise ValueError("output path must not overwrite the input request")
        result = rank_request(read_json(request_path))
        if args.output:
            output = args.output.expanduser()
            write_json(output, result)
            print(f"Ranked slot result: {output}")
        else:
            print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
