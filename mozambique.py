from __future__ import annotations

import os
import time
from typing import Any

import aiohttp

MOZAMBIQUE_BASE_URL = "https://api.mozambiquehe.re"

_cache: dict[str, tuple[Any, float]] = {}
_CACHE_TTL = 120


class MozambiqueApiError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


async def fetch_player_stats(platform: str, player_name: str) -> dict[str, Any]:
    return await _get(
        "/bridge",
        {
            "player": player_name,
            "platform": platform,
            "version": "5",
            "merge": "1",
        },
    )


async def fetch_map_rotation() -> dict[str, Any]:
    return await _cached_get("/maprotation", {"version": "2"})


async def fetch_predator() -> dict[str, Any]:
    return await _cached_get("/predator", {})


async def _cached_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    cached = _cache.get(path)
    if cached is not None:
        data, ts = cached
        if time.time() - ts < _CACHE_TTL:
            return data
    data = await _get(path, params)
    _cache[path] = (data, time.time())
    return data


async def _get(path: str, params: dict[str, str]) -> dict[str, Any]:
    api_key = os.getenv("MOZAMBIQUE_API_KEY")
    if not api_key:
        raise MozambiqueApiError(".env に MOZAMBIQUE_API_KEY を設定してください。")

    request_params = {"auth": api_key, **params}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MOZAMBIQUE_BASE_URL}{path}", params=request_params) as response:
            if response.status == 200:
                return await response.json(content_type=None)
            if response.status == 403:
                raise MozambiqueApiError("Mozambique APIキーが無効，または許可されていません。", response.status)
            if response.status == 404:
                raise MozambiqueApiError("指定した情報が見つかりませんでした。", response.status)
            if response.status == 429:
                raise MozambiqueApiError("Mozambique APIのレート制限に達しました。少し待ってから再実行してください。", response.status)

            body = await response.text()
            raise MozambiqueApiError(f"Mozambique APIでエラーが発生しました: {response.status} {body[:200]}", response.status)


def build_player_summary(data: dict[str, Any], platform: str, player_name: str) -> str:
    global_stats = data.get("global") or {}
    total_stats = data.get("total") or {}
    name = global_stats.get("name") or player_name
    uid = global_stats.get("uid")
    level = global_stats.get("level")
    rank = global_stats.get("rank") or {}
    rank_name = rank.get("rankName")
    rank_score = rank.get("rankScore")

    kills = _find_stat_value(total_stats, ["kills"])
    damage = _find_stat_value(total_stats, ["damage"])
    wins = _find_stat_value(total_stats, ["wins"])
    deaths = _find_stat_value(total_stats, ["deaths"])
    kd = _calculate_kd(kills, deaths)
    selected_legend = _selected_legend_name(data)

    lines = [
        "Apex Legends Stats",
        "",
        f"プレイヤー：{name}",
        f"プラットフォーム：{platform}",
    ]
    if uid:
        lines.append(f"UID：{uid}")
    if level is not None:
        lines.append(f"レベル：{level}")
    if rank_name or rank_score is not None:
        rank_text = f"{rank_name or 'Unknown'} / {rank_score}" if rank_score is not None else str(rank_name)
        lines.append(f"ランク：{rank_text}")
    if selected_legend:
        lines.append(f"選択中レジェンド：{selected_legend}")
    if kills is not None:
        lines.append(f"キル：{kills}")
    if damage is not None:
        lines.append(f"ダメージ：{damage}")
    if wins is not None:
        lines.append(f"勝利数：{wins}")
    if kd is not None:
        lines.append(f"KD：{kd:.2f}")
    else:
        lines.append("KD：取得不可")

    return "\n".join(lines)


def build_map_summary(data: dict[str, Any]) -> str:
    lines = ["マップローテーション", ""]
    mode_labels = {
        "battle_royale": "カジュアルBR",
        "ranked": "ランク",
        "ltm": "LTM",
        "arenas": "アリーナ",
        "arenasRanked": "ランクアリーナ",
        "control": "コントロール",
    }

    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        current = value.get("current")
        next_map = value.get("next")
        if not isinstance(current, dict):
            continue

        label = mode_labels.get(key, key)
        current_name = current.get("map") or current.get("readableDate_start") or "不明"
        remaining = current.get("remainingTimer")
        next_name = next_map.get("map") if isinstance(next_map, dict) else None
        line = f"{label}：{current_name}"
        if remaining:
            line += f"（残り {remaining}）"
        if next_name:
            line += f" / 次：{next_name}"
        lines.append(line)

    if len(lines) == 2:
        lines.append("表示できるマップ情報がありませんでした。")
    lines.extend(["", "Data from apexlegendsstatus.com"])
    return "\n".join(lines)


def build_predator_summary(data: dict[str, Any]) -> str:
    lines = ["プレデター到達RP", ""]
    platform_labels = {
        "PC": "PC",
        "PS4": "PlayStation",
        "X1": "Xbox",
        "SWITCH": "Switch",
    }

    for key, label in platform_labels.items():
        value = data.get(key)
        if not isinstance(value, dict):
            continue
        rp = value.get("val")
        masters = value.get("totalMastersAndPreds")
        if rp is None and masters is None:
            continue
        line = f"{label}：{rp} RP"
        if masters is not None:
            line += f" / Master+Pred {masters}人"
        lines.append(line)

    if len(lines) == 2:
        lines.append("表示できるプレデター情報がありませんでした。")
    lines.extend(["", "Data from apexlegendsstatus.com"])
    return "\n".join(lines)


def _find_stat_value(stats: dict[str, Any], keys: list[str]) -> int | float | str | None:
    lowered_keys = {key.lower() for key in keys}
    for key, value in stats.items():
        if key.lower() in lowered_keys:
            return _extract_value(value)
        if isinstance(value, dict) and str(value.get("name", "")).lower() in lowered_keys:
            return _extract_value(value)
    return None


def _extract_value(value: Any) -> int | float | str | None:
    if isinstance(value, dict):
        return value.get("value") or value.get("total") or value.get("displayValue")
    return value


def _calculate_kd(kills: Any, deaths: Any) -> float | None:
    try:
        kills_number = float(kills)
        deaths_number = float(deaths)
    except (TypeError, ValueError):
        return None
    if deaths_number <= 0:
        return None
    return kills_number / deaths_number


def _selected_legend_name(data: dict[str, Any]) -> str | None:
    legends = data.get("legends") or {}
    selected = legends.get("selected") or {}
    if not isinstance(selected, dict) or not selected:
        return None
    return next(iter(selected.keys()))
