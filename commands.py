from __future__ import annotations

import discord
from discord import app_commands

from helpers import PlatformChoice, active_state_or_message, normal_panel_message
from mozambique import MozambiqueApiError, build_player_summary, fetch_player_stats
from storage import load_apex_profile, load_state, save_apex_profile
from views import (
    DeathCauseView,
    LegendConfirmView,
    LegendView,
    NormalSessionView,
    PanelButtonView,
    confirm_reset,
    end_session,
    export_matches,
    send_map_rotation,
    send_predator,
    send_summary,
)

from bot import bot


@bot.tree.command(name="setup", description="パネルボタンをこのチャンネルに設置します（管理者用）")
@app_commands.default_permissions(manage_guild=True)
async def setup(interaction: discord.Interaction) -> None:
    await interaction.channel.send("**ApexStatsBot**\nボタンを押してパネルを開いてください。", view=PanelButtonView())
    await interaction.response.send_message("ボタンを設置しました。", ephemeral=True)


@bot.tree.command(name="panel", description="プルダウン式の操作パネルを表示します")
async def panel(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        normal_panel_message("ApexStatsBot 操作パネル"),
        view=NormalSessionView(),
        ephemeral=True,
    )


@bot.tree.command(name="start", description="Apexの記録セッションを開始します")
async def start(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("使用キャラを選択してください。", view=LegendView("start_panel"), ephemeral=True)


@bot.tree.command(name="match", description="1試合の結果を記録します")
async def match(interaction: discord.Interaction) -> None:
    state, error = active_state_or_message(interaction.user.id)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    legend = state.get("current_legend", "？")
    await interaction.response.send_message(
        f"キャラはそのままですか？\n現在：{legend}",
        view=LegendConfirmView(legend, panel_interaction=interaction),
        ephemeral=True,
    )


@bot.tree.command(name="legend", description="以降の試合で使うキャラを変更します")
async def legend(interaction: discord.Interaction) -> None:
    state = load_state(interaction.user.id)
    if not state or not state.get("is_active"):
        await interaction.response.send_message("先に /start してください。", ephemeral=True)
        return
    await interaction.response.send_message("使用キャラを選択してください。", view=LegendView("legend"), ephemeral=True)


@bot.tree.command(name="summary", description="現在のセッションの統計を表示します")
async def summary(interaction: discord.Interaction) -> None:
    await send_summary(interaction)


@bot.tree.command(name="end", description="現在のセッションを終了し，統計を表示します")
async def end(interaction: discord.Interaction) -> None:
    await end_session(interaction)


@bot.tree.command(name="export", description="自分のmatches.csvを送信します")
async def export(interaction: discord.Interaction) -> None:
    await export_matches(interaction)


@bot.tree.command(name="reset", description="現在のセッションの記録だけをリセットします")
async def reset(interaction: discord.Interaction) -> None:
    await confirm_reset(interaction)


@bot.tree.command(name="apex_set", description="Mozambique APIで使うApexプロフィールを保存します")
@app_commands.describe(platform="プラットフォーム", player_name="Apexのプレイヤー名")
async def apex_set(interaction: discord.Interaction, platform: PlatformChoice, player_name: str) -> None:
    save_apex_profile(interaction.user.id, {"platform": platform, "player_name": player_name})
    await interaction.response.send_message(
        f"Apexプロフィールを保存しました。\nプラットフォーム：{platform}\nプレイヤー：{player_name}",
        ephemeral=True,
    )


@bot.tree.command(name="apex_stats", description="Mozambique APIからApex統計を表示します")
@app_commands.describe(platform="省略すると保存済みプロフィールを使います", player_name="省略すると保存済みプロフィールを使います")
async def apex_stats(
    interaction: discord.Interaction,
    platform: PlatformChoice | None = None,
    player_name: str | None = None,
) -> None:
    saved_profile = load_apex_profile(interaction.user.id) or {}
    target_platform = platform or saved_profile.get("platform")
    target_player = player_name or saved_profile.get("player_name")

    if not target_platform or not target_player:
        await interaction.response.send_message(
            "先に /apex_set でApexプロフィールを保存するか，platform と player_name を指定してください。",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    try:
        profile = await fetch_player_stats(str(target_platform), str(target_player))
    except MozambiqueApiError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return

    await interaction.followup.send(
        build_player_summary(profile, str(target_platform), str(target_player)),
        ephemeral=True,
    )


@bot.tree.command(name="apex_map", description="現在と次のマップローテーションを表示します")
async def apex_map(interaction: discord.Interaction) -> None:
    await send_map_rotation(interaction)


@bot.tree.command(name="apex_predator", description="各プラットフォームのプレデター到達RPを表示します")
async def apex_predator(interaction: discord.Interaction) -> None:
    await send_predator(interaction)
