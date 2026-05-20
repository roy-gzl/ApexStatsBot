from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from constants import CSV_FIELDS, MatchRow

DATA_ROOT = Path("data") / "users"


def user_dir(user_id: int | str) -> Path:
    return DATA_ROOT / str(user_id)


def matches_path(user_id: int | str) -> Path:
    return user_dir(user_id) / "matches.csv"


def state_path(user_id: int | str) -> Path:
    return user_dir(user_id) / "session_state.json"


def apex_profile_path(user_id: int | str) -> Path:
    return user_dir(user_id) / "apex_profile.json"


def ensure_user_files(user_id: int | str) -> None:
    directory = user_dir(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = matches_path(user_id)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


def load_state(user_id: int | str) -> dict[str, Any] | None:
    path = state_path(user_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_state(user_id: int | str, state: dict[str, Any]) -> None:
    ensure_user_files(user_id)
    with state_path(user_id).open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_apex_profile(user_id: int | str) -> dict[str, Any] | None:
    path = apex_profile_path(user_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_apex_profile(user_id: int | str, profile: dict[str, Any]) -> None:
    ensure_user_files(user_id)
    with apex_profile_path(user_id).open("w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def read_matches(user_id: int | str) -> list[MatchRow]:
    ensure_user_files(user_id)
    with matches_path(user_id).open("r", newline="", encoding="utf-8") as f:
        return [_coerce_row(row) for row in csv.DictReader(f)]


def append_match(user_id: int | str, row: MatchRow) -> None:
    ensure_user_files(user_id)
    with matches_path(user_id).open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def update_match(user_id: int | str, match_id: str, new_row: MatchRow) -> None:
    rows = read_matches(user_id)
    write_matches(user_id, [new_row if row["match_id"] == match_id else row for row in rows])


def write_matches(user_id: int | str, rows: list[MatchRow]) -> None:
    ensure_user_files(user_id)
    with matches_path(user_id).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def generate_session_id(user_id: int | str, now: datetime | None = None) -> str:
    ensure_user_files(user_id)
    today = (now or datetime.now()).strftime("%Y-%m-%d")
    max_number = 0

    for row in read_matches(user_id):
        session_id = row.get("session_id", "")
        if session_id.startswith(f"{today}-"):
            max_number = max(max_number, _session_number(session_id))

    state = load_state(user_id)
    if state:
        session_id = str(state.get("current_session_id", ""))
        if session_id.startswith(f"{today}-"):
            max_number = max(max_number, _session_number(session_id))

    return f"{today}-{max_number + 1:03d}"


def _session_number(session_id: str) -> int:
    try:
        return int(session_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def current_session_rows(user_id: int | str, session_id: str | None) -> list[MatchRow]:
    if not session_id:
        return []
    return [row for row in read_matches(user_id) if row.get("session_id") == session_id]


def reset_current_session(user_id: int | str, session_id: str) -> int:
    rows = read_matches(user_id)
    kept_rows = [row for row in rows if row.get("session_id") != session_id]
    removed_count = len(rows) - len(kept_rows)
    write_matches(user_id, kept_rows)
    return removed_count


def build_summary_text(rows: list[MatchRow]) -> str:
    if not rows:
        return "今日のApexまとめ\n\nまだこのセッションの試合記録がありません。"

    match_count = len(rows)

    cause_counts = Counter(row["death_cause"] for row in rows)
    legend_groups: dict[str, list[MatchRow]] = defaultdict(list)
    for row in rows:
        legend_groups[row["legend"]].append(row)

    lines = [
        "今日のApexまとめ",
        "",
        f"試合数：{match_count}",
        f"平均順位：{_fmt_float(mean(row['rank'] for row in rows))}位",
        f"平均ダメージ：{round(mean(row['damage'] for row in rows))}",

        f"平均キル：{_fmt_float(mean(row['kills'] for row in rows))}",
        "",
        "使用キャラ：",
    ]

    for legend, legend_rows in sorted(legend_groups.items(), key=lambda item: len(item[1]), reverse=True):
        avg_damage = round(mean(row["damage"] for row in legend_rows))
        kd = sum(row["kills"] for row in legend_rows) / len(legend_rows)
        lines.append(
            f"{legend}：{len(legend_rows)}試合 / 平均DMG {avg_damage} / K/D {_fmt_float(kd)}"
        )

    lines.extend(["", "死亡原因："])
    for cause, count in cause_counts.most_common():
        lines.append(f"{cause}：{count}回")

    return "\n".join(lines)


def _coerce_row(row: dict[str, str]) -> MatchRow:
    return {
        "date": row.get("date", ""),
        "session_id": row.get("session_id", ""),
        "match_id": row.get("match_id", ""),
        "user_id": row.get("user_id", ""),
        "username": row.get("username", ""),
        "legend": row.get("legend", "不明"),
        "death_cause": row.get("death_cause", "不明"),
        "rank": int(row.get("rank") or 0),
        "damage": int(row.get("damage") or 0),

        "kills": int(row.get("kills") or 0),
        "assists": int(row.get("assists") or 0),
        "knocks": int(row.get("knocks") or 0),
    }


def _fmt_float(value: float) -> str:
    return f"{value:.1f}"


def _fmt_signed(value: float | int) -> str:
    if isinstance(value, float):
        formatted = f"{value:+.1f}"
    else:
        formatted = f"{value:+d}"
    return formatted
