from __future__ import annotations

from datetime import datetime
from typing import Literal

import discord

from constants import MatchRow
from storage import load_state

PlatformChoice = Literal["PC", "PS4", "X1", "SWITCH"]


def display_name(user: discord.abc.User) -> str:
    return getattr(user, "display_name", user.name)


def new_session_state(user: discord.abc.User, legend: str, session_id: str) -> dict:
    return {
        "user_id": str(user.id),
        "username": display_name(user),
        "current_legend": legend,
        "current_session_id": session_id,
        "match_count": 0,
        "is_active": True,
    }


def active_state_or_message(user_id: int) -> tuple[dict, str | None]:
    state = load_state(user_id)
    if not state or not state.get("is_active") or not state.get("current_legend"):
        return {}, "先に /start してください。"
    return state, None


def build_match_row(
    interaction: discord.Interaction,
    state: dict,
    death_cause: str,
    values: dict[str, int],
) -> tuple[MatchRow, int]:
    match_count = int(state.get("match_count", 0)) + 1
    session_id = str(state["current_session_id"])
    return (
        {
            "date": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "match_id": f"{session_id}-{match_count:03d}",
            "user_id": str(interaction.user.id),
            "username": display_name(interaction.user),
            "legend": str(state["current_legend"]),
            "death_cause": death_cause,
            **values,
        },
        match_count,
    )


def format_match_result(row: MatchRow) -> str:
    return (
        "記録しました\n\n"
        f"キャラ：{row['legend']}\n"
        f"死亡原因：{row['death_cause']}\n"
        f"順位：{row['rank']}位\n"
        f"ダメージ：{row['damage']}\n"

        f"キル：{row['kills']}"
    )


def normal_panel_message(prefix: str | None = None) -> str:
    text = "**次の操作を選択してください。**"
    if prefix:
        return f"{prefix}\n\n{text}"
    return text
