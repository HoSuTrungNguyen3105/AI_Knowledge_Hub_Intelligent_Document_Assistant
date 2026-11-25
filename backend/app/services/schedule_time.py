"""Pure schedule-time engine for workflow schedules (Scheduler spec §2, §4).

One engine for every schedule kind. Daily, weekly and monthly schedules
are translated to a 5-field cron expression internally; one-time and
interval schedules are computed directly. All math happens in the
schedule's own timezone via :mod:`zoneinfo` and returns timezone-aware
datetimes, so callers never reason about offsets themselves.

Monthly schedules on a day a month does not have (29/30/31) are skipped
for that month — never shifted to the end of the month.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_SEARCH_DAYS = 366 * 5
WEEKDAY_NAMES = {
    1: "Thứ Hai",
    2: "Thứ Ba",
    3: "Thứ Tư",
    4: "Thứ Năm",
    5: "Thứ Sáu",
    6: "Thứ Bảy",
    7: "Chủ Nhật",
}


class ScheduleInvalid(ValueError):
    """The schedule configuration cannot produce valid run times."""


def load_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ScheduleInvalid(f"Unknown timezone: {name!r}") from None


def _parse_field(field: str, low: int, high: int, label: str) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise ScheduleInvalid(f"Empty cron {label} field part")
        step = 1
        base = part
        if "/" in part:
            base, _, step_text = part.partition("/")
            if not step_text.isdigit() or int(step_text) < 1:
                raise ScheduleInvalid(f"Invalid cron {label} step: {part!r}")
            step = int(step_text)
        if base == "*":
            start, end = low, high
        elif "-" in base:
            first, _, last = base.partition("-")
            if not first.isdigit() or not last.isdigit():
                raise ScheduleInvalid(f"Invalid cron {label} range: {part!r}")
            start, end = int(first), int(last)
        elif base.isdigit():
            start = end = int(base)
        else:
            raise ScheduleInvalid(f"Invalid cron {label} value: {part!r}")
        if start < low or end > high or start > end:
            raise ScheduleInvalid(f"Cron {label} out of range: {part!r}")
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expression: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    """Parse a standard 5-field cron expression.

    Returns (minutes, hours, days_of_month, months, days_of_week) with
    days_of_week using cron numbering (0 = Sunday, 7 also Sunday).
    """
    if not isinstance(expression, str):
        raise ScheduleInvalid("Cron expression must be a string")
    fields = expression.split()
    if len(fields) != 5:
        raise ScheduleInvalid("Cron expression must have exactly 5 fields")
    minutes = _parse_field(fields[0], 0, 59, "minute")
    hours = _parse_field(fields[1], 0, 23, "hour")
    doms = _parse_field(fields[2], 1, 31, "day-of-month")
    months = _parse_field(fields[3], 1, 12, "month")
    dows = _parse_field(fields[4], 0, 7, "day-of-week")
    dows = {0 if day == 7 else day for day in dows}
    return minutes, hours, doms, months, dows


def _cron_next(
    parsed: tuple[set[int], set[int], set[int], set[int], set[int]],
    tz: ZoneInfo,
    after: datetime,
    count: int,
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[datetime]:
    minutes, hours, doms, months, dows = parsed
    dom_restricted = doms != set(range(1, 32))
    dow_restricted = dows != set(range(7))
    local_after = after.astimezone(tz)
    day = local_after.date()
    results: list[datetime] = []
    for _ in range(MAX_SEARCH_DAYS):
        if len(results) >= count:
            break
        if day.month in months:
            dom_match = day.day in doms
            dow_match = (day.isoweekday() % 7) in dows
            if dom_restricted and dow_restricted:
                day_match = dom_match or dow_match  # standard cron semantics
            else:
                day_match = dom_match and dow_match
            if day_match:
                for hour in sorted(hours):
                    for minute in sorted(minutes):
                        moment = datetime(
                            day.year, day.month, day.day, hour, minute, tzinfo=tz
                        )
                        if moment <= local_after:
                            continue
                        if start_at is not None and moment < start_at.astimezone(tz):
                            continue
                        if end_at is not None and moment > end_at.astimezone(tz):
                            return results
                        results.append(moment)
                        if len(results) >= count:
                            break
                    if len(results) >= count:
                        break
        day += timedelta(days=1)
    return results


def to_cron(schedule_type: str, config: dict) -> str | None:
    """Translate a structured schedule kind to cron; None for once/interval."""
    if schedule_type == "daily":
        return f"{_minute(config)} {_hour(config)} * * *"
    if schedule_type == "weekly":
        weekdays = config.get("weekdays") or []
        if not weekdays:
            raise ScheduleInvalid("A weekly schedule needs at least one weekday")
        dows = sorted({int(day) % 7 for day in weekdays})
        return f"{_minute(config)} {_hour(config)} * * {','.join(str(d) for d in dows)}"
    if schedule_type == "monthly":
        day = config.get("day_of_month")
        if not isinstance(day, int) or not 1 <= day <= 31:
            raise ScheduleInvalid("A monthly schedule needs day_of_month between 1 and 31")
        return f"{_minute(config)} {_hour(config)} {day} * *"
    if schedule_type == "cron":
        return None  # the caller supplies cron_expression directly
    return None


def _hour(config: dict) -> int:
    hour = config.get("hour")
    if not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ScheduleInvalid("hour must be an integer between 0 and 23")
    return hour


def _minute(config: dict) -> int:
    minute = config.get("minute")
    if not isinstance(minute, int) or not 0 <= minute <= 59:
        raise ScheduleInvalid("minute must be an integer between 0 and 59")
    return minute


def _as_aware(value, tz: ZoneInfo, label: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise ScheduleInvalid(f"{label} is not a valid ISO datetime") from None
    if not isinstance(value, datetime):
        raise ScheduleInvalid(f"{label} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value


def compute_next_runs(
    *,
    schedule_type: str,
    config: dict,
    cron_expression: str | None,
    timezone: str,
    start_at: datetime | None,
    end_at: datetime | None,
    after: datetime,
    count: int = 5,
) -> list[datetime]:
    """Return up to ``count`` run times strictly after ``after``.

    Raises ScheduleInvalid for any configuration that cannot be
    validated (bad cron, bad timezone, missing fields).
    """
    tz = load_tz(timezone)
    if start_at is not None and end_at is not None and end_at <= start_at:
        raise ScheduleInvalid("end_at must be after start_at")
    if schedule_type == "once":
        run_at = _as_aware(config.get("run_at"), tz, "run_at")
        if end_at is not None and run_at > end_at:
            return []
        if start_at is not None and run_at < start_at:
            return []
        return [run_at] if run_at > after else []
    if schedule_type == "interval":
        every = config.get("every")
        unit = config.get("unit")
        if not isinstance(every, int) or every < 1:
            raise ScheduleInvalid("interval needs 'every' as a positive integer")
        if unit not in ("minutes", "hours"):
            raise ScheduleInvalid("interval unit must be 'minutes' or 'hours'")
        delta = timedelta(minutes=every) if unit == "minutes" else timedelta(hours=every)
        anchor = start_at if start_at is not None else after
        anchor = _as_aware(anchor, tz, "start_at")
        if after < anchor:
            first = anchor
        else:
            steps = int((after - anchor) // delta) + 1
            first = anchor + steps * delta
        results = []
        moment = first
        while len(results) < count:
            if end_at is not None and moment > end_at:
                break
            results.append(moment)
            moment += delta
        return results
    if schedule_type == "cron":
        if not cron_expression:
            raise ScheduleInvalid("A cron schedule needs cron_expression")
        expression = cron_expression
    elif schedule_type in ("daily", "weekly", "monthly"):
        expression = to_cron(schedule_type, config)
    else:
        raise ScheduleInvalid(f"Unknown schedule_type: {schedule_type!r}")
    parsed = parse_cron(expression)
    return _cron_next(parsed, tz, after, count, start_at, end_at)


def describe_schedule(
    *,
    schedule_type: str,
    config: dict,
    cron_expression: str | None,
    timezone: str,
) -> str:
    """Human-readable Vietnamese summary of when a schedule fires."""
    if schedule_type == "once":
        tz = load_tz(timezone)
        run_at = _as_aware(config.get("run_at"), tz, "run_at").astimezone(tz)
        text = f"Chạy một lần lúc {run_at:%H:%M} ngày {run_at:%d/%m/%Y}"
    elif schedule_type == "daily":
        text = f"Mỗi ngày lúc {_hour(config):02d}:{_minute(config):02d}"
    elif schedule_type == "weekly":
        names = [WEEKDAY_NAMES[int(day)] for day in config.get("weekdays") or []]
        text = (
            f"Mỗi tuần vào {', '.join(names)} lúc "
            f"{_hour(config):02d}:{_minute(config):02d}"
        )
    elif schedule_type == "monthly":
        day = config.get("day_of_month")
        text = f"Ngày {day} hằng tháng lúc {_hour(config):02d}:{_minute(config):02d}"
        if isinstance(day, int) and day >= 29:
            text += f" (tháng không có ngày {day} sẽ bỏ qua)"
    elif schedule_type == "interval":
        unit = "phút" if config.get("unit") == "minutes" else "giờ"
        text = f"Mỗi {config.get('every')} {unit}"
    elif schedule_type == "cron":
        text = f"Theo biểu thức cron `{cron_expression}`"
    else:
        text = schedule_type
    return f"{text} · Múi giờ {timezone}"


def schedule_warnings(
    *,
    schedule_type: str,
    config: dict,
    end_at: datetime | None,
) -> list[str]:
    warnings: list[str] = []
    if schedule_type == "monthly":
        day = config.get("day_of_month")
        if isinstance(day, int) and day >= 29:
            warnings.append(
                f"Tháng không có ngày {day} sẽ bị bỏ qua, không chạy bù."
            )
    if end_at is not None:
        warnings.append(f"Lịch ngừng hiệu lực sau {end_at:%H:%M %d/%m/%Y}.")
    return warnings
