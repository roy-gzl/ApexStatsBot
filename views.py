from __future__ import annotations

import discord

from constants import DEATH_CAUSES, LEGENDS_BY_ROLE, MatchRow
from helpers import (
    active_state_or_message,
    build_match_row,
    display_name,
    format_match_result,
    new_session_state,
    normal_panel_message,
)
from mozambique import (
    MozambiqueApiError,
    build_map_summary,
    build_player_summary,
    build_predator_summary,
    fetch_map_rotation,
    fetch_player_stats,
    fetch_predator,
)
from storage import (
    append_match,
    build_summary_text,
    current_session_rows,
    ensure_user_files,
    generate_session_id,
    load_apex_profile,
    load_state,
    matches_path,
    reset_current_session,
    save_apex_profile,
    save_state,
    update_match,
)

# ------------------------------------------------------- セッション開始 ----


class LegendSelect(discord.ui.Select):
    def __init__(self, mode: str, legends: list[str], placeholder: str) -> None:
        self.mode = mode
        options = [discord.SelectOption(label=legend, value=legend) for legend in legends]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        legend = self.values[0]
        user_id = interaction.user.id
        username = display_name(interaction.user)
        ensure_user_files(user_id)

        if self.mode in {"start", "start_panel"}:
            session_id = generate_session_id(user_id)
            state = new_session_state(interaction.user, legend, session_id)
            save_state(user_id, state)
            await interaction.response.edit_message(
                content=normal_panel_message(f"セッションを開始しました。\n使用キャラ：{legend}\nセッションID：{session_id}"),
                view=NormalSessionView(),
            )
            return

        state = load_state(user_id) or {
            "user_id": str(user_id),
            "username": username,
            "current_session_id": "",
            "match_count": 0,
            "is_active": False,
        }
        if not state.get("is_active"):
            await interaction.response.edit_message(content="先に /start してください。", view=None)
            return
        state["username"] = username
        state["current_legend"] = legend
        save_state(user_id, state)

        if self.mode == "edit_legend":
            edit_row: MatchRow | None = getattr(self.view, "edit_row", None)
            new_edit_row: MatchRow | None = {**edit_row, "legend": legend} if edit_row else None
            defaults = getattr(self.view, "defaults", None)
            panel_interaction = getattr(self.view, "panel_interaction", None)
            current_death = (edit_row or {}).get("death_cause", "不明")
            await interaction.response.edit_message(
                content=f"死亡原因を選択してください。\n現在：{current_death}",
                view=DeathCauseView(panel_interaction=panel_interaction, edit_row=new_edit_row, defaults=defaults),
            )
            return

        state = load_state(user_id) or {
            "user_id": str(user_id),
            "username": username,
            "current_session_id": "",
            "match_count": 0,
            "is_active": False,
        }
        if not state.get("is_active"):
            await interaction.response.edit_message(content="先に /start してください。", view=None)
            return
        state["username"] = username
        state["current_legend"] = legend
        save_state(user_id, state)

        if self.mode == "match_legend":
            panel_interaction = getattr(self.view, "panel_interaction", None)
            await interaction.response.edit_message(
                content="死亡原因を選択してください。",
                view=DeathCauseView(panel_interaction=panel_interaction),
            )
        else:
            await interaction.response.edit_message(
                content=normal_panel_message(f"以降の試合は {legend} として記録します。"),
                view=NormalSessionView(),
            )


class LegendView(discord.ui.View):
    def __init__(
        self,
        mode: str,
        panel_interaction: discord.Interaction | None = None,
        edit_row: MatchRow | None = None,
        defaults: dict | None = None,
    ) -> None:
        super().__init__(timeout=180)
        self.panel_interaction = panel_interaction
        self.edit_row = edit_row
        self.defaults = defaults
        for role, legends in LEGENDS_BY_ROLE.items():
            self.add_item(LegendSelect(mode, legends, f"{role}から選択"))


class LegendConfirmView(discord.ui.View):
    def __init__(self, legend: str, panel_interaction: discord.Interaction) -> None:
        super().__init__(timeout=180)
        self.legend = legend
        self.panel_interaction = panel_interaction

    @discord.ui.button(label="そのまま", style=discord.ButtonStyle.primary)
    async def keep(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            content="死亡原因を選択してください。",
            view=DeathCauseView(panel_interaction=self.panel_interaction),
        )

    @discord.ui.button(label="変更する", style=discord.ButtonStyle.secondary)
    async def change(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            content="使用キャラを選択してください。",
            view=LegendView("match_legend", panel_interaction=self.panel_interaction),
        )


class EditLegendConfirmView(discord.ui.View):
    def __init__(
        self,
        edit_row: MatchRow,
        defaults: dict[str, str],
        panel_interaction: discord.Interaction | None,
    ) -> None:
        super().__init__(timeout=180)
        self.edit_row = edit_row
        self.defaults = defaults
        self.panel_interaction = panel_interaction

    @discord.ui.button(label="そのまま", style=discord.ButtonStyle.primary)
    async def keep(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        current = self.edit_row.get("death_cause", "不明")
        await interaction.response.edit_message(
            content=f"死亡原因を選択してください。\n現在：{current}",
            view=DeathCauseView(panel_interaction=self.panel_interaction, edit_row=self.edit_row, defaults=self.defaults),
        )

    @discord.ui.button(label="変更する", style=discord.ButtonStyle.secondary)
    async def change(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            content="使用キャラを選択してください。",
            view=LegendView("edit_legend", panel_interaction=self.panel_interaction, edit_row=self.edit_row, defaults=self.defaults),
        )


# ------------------------------------------------------------ 試合記録 ----


class DeathCauseSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [discord.SelectOption(label=cause, value=cause) for cause in DEATH_CAUSES]
        super().__init__(placeholder="死亡原因を選択してください", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        edit_row: MatchRow | None = getattr(self.view, "edit_row", None)
        if not edit_row:
            state, error = active_state_or_message(interaction.user.id)
            if error:
                await interaction.response.edit_message(content=error, view=None)
                return
        panel_interaction: discord.Interaction | None = getattr(self.view, "panel_interaction", None)
        defaults: dict | None = getattr(self.view, "defaults", None)
        await interaction.response.send_modal(
            MatchModal(self.values[0], defaults=defaults, edit_row=edit_row, panel_interaction=panel_interaction)
        )


class DeathCauseView(discord.ui.View):
    def __init__(
        self,
        panel_interaction: discord.Interaction | None = None,
        edit_row: MatchRow | None = None,
        defaults: dict[str, str] | None = None,
    ) -> None:
        super().__init__(timeout=180)
        self.panel_interaction = panel_interaction
        self.edit_row = edit_row
        self.defaults = defaults
        self.add_item(DeathCauseSelect())

    @discord.ui.button(label="パネルに戻る", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=normal_panel_message(), view=NormalSessionView())


class MatchModal(discord.ui.Modal):
    def __init__(
        self,
        death_cause: str,
        defaults: dict[str, str] | None = None,
        panel_interaction: discord.Interaction | None = None,
        edit_row: MatchRow | None = None,
    ) -> None:
        title = "試合結果を修正" if edit_row else "試合結果を入力"
        super().__init__(title=title)
        self.death_cause = death_cause
        self.panel_interaction = panel_interaction
        self.edit_row = edit_row
        d = defaults or {}
        self.rank = discord.ui.TextInput(label="順位（1〜20）", placeholder="例: 8", max_length=2, default=d.get("rank", ""))
        self.damage = discord.ui.TextInput(label="ダメージ（0以上）", placeholder="例: 650", max_length=6, default=d.get("damage", ""))
        self.kills = discord.ui.TextInput(label="キル数（0以上）", placeholder="例: 1", max_length=3, default=d.get("kills", ""))
        self.add_item(self.rank)
        self.add_item(self.damage)
        self.add_item(self.kills)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values, error = self._validated_values()
        if error:
            defaults = {
                "rank": str(self.rank.value),
                "damage": str(self.damage.value),
                "kills": str(self.kills.value),
            }
            retry_view = MatchRetryView(self.death_cause, defaults, self.edit_row, self.panel_interaction)
            content = f"⚠ **入力エラー：{error}**\n\n「再入力」ボタンからもう一度入力してください。"
            await interaction.response.defer()
            if self.panel_interaction:
                await self.panel_interaction.edit_original_response(content=content, view=retry_view)
            else:
                await interaction.followup.send(content, view=retry_view, ephemeral=True)
            return

        user_id = interaction.user.id
        state, state_error = active_state_or_message(user_id)
        if state_error:
            await interaction.response.send_message(state_error, ephemeral=True)
            return

        if self.edit_row:
            row = {**self.edit_row, "death_cause": self.death_cause, **values}
            update_match(user_id, str(self.edit_row["match_id"]), row)
        else:
            row, match_count = build_match_row(interaction, state, self.death_cause, values)
            append_match(user_id, row)
            state["username"] = row["username"]
            state["match_count"] = match_count
            save_state(user_id, state)

        await interaction.response.defer()
        content = normal_panel_message(format_match_result(row))
        view = MatchResultView(row, panel_interaction=self.panel_interaction)
        if self.panel_interaction:
            await self.panel_interaction.edit_original_response(content=content, view=view)
        else:
            await interaction.followup.send(content, view=view, ephemeral=True)

    def _validated_values(self) -> tuple[dict[str, int], str | None]:
        try:
            values = {
                "rank": int(str(self.rank.value).strip()),
                "damage": int(str(self.damage.value).strip()),
                "kills": int(str(self.kills.value).strip()),
                "assists": 0,
                "knocks": 0,
            }
        except ValueError:
            return {}, "整数で入力してください"

        if not 1 <= values["rank"] <= 20:
            return {}, "順位は1〜20"
        for key, label in [("damage", "ダメージ"), ("kills", "キル数")]:
            if values[key] < 0:
                return {}, f"{label}は0以上"
        return values, None


class MatchResultView(discord.ui.View):
    def __init__(self, row: MatchRow, panel_interaction: discord.Interaction | None = None) -> None:
        super().__init__(timeout=300)
        self.row = row
        self.panel_interaction = panel_interaction

    @discord.ui.button(label="修正する", style=discord.ButtonStyle.secondary)
    async def edit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        defaults = {
            "rank": str(self.row["rank"]),
            "damage": str(self.row["damage"]),
            "kills": str(self.row["kills"]),
        }
        legend = self.row.get("legend", "？")
        await interaction.response.edit_message(
            content=f"キャラはそのままですか？\n現在：{legend}",
            view=EditLegendConfirmView(self.row, defaults, self.panel_interaction),
        )

    @discord.ui.button(label="パネルへ戻る", style=discord.ButtonStyle.primary)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=normal_panel_message(), view=NormalSessionView())


class MatchRetryView(discord.ui.View):
    def __init__(
        self,
        death_cause: str,
        defaults: dict[str, str],
        edit_row: MatchRow | None,
        panel_interaction: discord.Interaction | None,
    ) -> None:
        super().__init__(timeout=300)
        self.death_cause = death_cause
        self.defaults = defaults
        self.edit_row = edit_row
        self.panel_interaction = panel_interaction

    @discord.ui.button(label="再入力", style=discord.ButtonStyle.primary)
    async def retry(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            MatchModal(self.death_cause, defaults=self.defaults, edit_row=self.edit_row, panel_interaction=self.panel_interaction)
        )

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.panel_interaction:
            await interaction.response.edit_message(content=normal_panel_message(), view=NormalSessionView())
        else:
            await interaction.response.edit_message(content="キャンセルしました。", view=None)


class RecentMatchSelect(discord.ui.Select):
    def __init__(self, rows: list[MatchRow]) -> None:
        self._rows: dict[str, MatchRow] = {row["match_id"]: row for row in rows}
        options = []
        for row in reversed(rows):
            try:
                num = int(row["match_id"].split("-")[-1])
                label = f"#{num} {row['legend']} / {row['rank']}位 / {row['damage']}DMG"
            except (ValueError, KeyError):
                label = row["match_id"]
            options.append(discord.SelectOption(label=label[:100], value=row["match_id"]))
        super().__init__(placeholder="修正する試合を選択してください", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        row = self._rows[self.values[0]]
        defaults = {
            "rank": str(row["rank"]),
            "damage": str(row["damage"]),
            "kills": str(row["kills"]),
        }
        panel_interaction: discord.Interaction | None = getattr(self.view, "panel_interaction", None)
        legend = row.get("legend", "？")
        await interaction.response.edit_message(
            content=f"キャラはそのままですか？\n現在：{legend}",
            view=EditLegendConfirmView(row, defaults, panel_interaction),
        )


class RecentMatchView(discord.ui.View):
    def __init__(self, rows: list[MatchRow], panel_interaction: discord.Interaction | None = None) -> None:
        super().__init__(timeout=180)
        self.panel_interaction = panel_interaction
        self.add_item(RecentMatchSelect(rows))

    @discord.ui.button(label="パネルへ戻る", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=normal_panel_message(), view=NormalSessionView())


# -------------------------------------------------------- 確認ダイアログ ----


class EndSessionView(discord.ui.View):
    def __init__(self, user_id: int) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("この操作はコマンドを実行したユーザーだけが使えます。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="終了する", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        state, error = active_state_or_message(interaction.user.id)
        if error:
            await interaction.response.edit_message(content=error, view=None)
            return
        rows = current_session_rows(interaction.user.id, state.get("current_session_id"))
        text = build_summary_text(rows)
        state["is_active"] = False
        save_state(interaction.user.id, state)
        await interaction.response.edit_message(content=f"{text}\n\nセッションを終了しました。", view=None)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=normal_panel_message(), view=NormalSessionView())


class ResetView(discord.ui.View):
    def __init__(self, user_id: int, session_id: str, return_to_panel: bool = False) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.session_id = session_id
        self.return_to_panel = return_to_panel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("この操作はコマンドを実行したユーザーだけが使えます。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="リセットする", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        reset_current_session(self.user_id, self.session_id)
        state = load_state(self.user_id) or {}
        state["match_count"] = 0
        state["is_active"] = True
        save_state(self.user_id, state)
        if self.return_to_panel:
            await interaction.response.edit_message(
                content=normal_panel_message("現在のセッションをリセットしました。"),
                view=NormalSessionView(),
            )
            return
        await interaction.response.edit_message(content="現在のセッションをリセットしました。", view=None)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.return_to_panel:
            await interaction.response.edit_message(
                content=normal_panel_message("リセットをキャンセルしました。"),
                view=NormalSessionView(),
            )
            return
        await interaction.response.edit_message(content="リセットをキャンセルしました。", view=None)


# ----------------------------------------------------- Apexプロフィール ----


class PlayerNameModal(discord.ui.Modal, title="Apexプロフィール設定"):
    player_name = discord.ui.TextInput(label="Apexのプレイヤー名", placeholder="例: PlayerName", max_length=32)

    def __init__(self, platform: str, return_to_panel: bool = False) -> None:
        super().__init__()
        self.platform = platform
        self.return_to_panel = return_to_panel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        save_apex_profile(
            interaction.user.id,
            {"platform": self.platform, "player_name": str(self.player_name.value).strip()},
        )
        message = f"Apexプロフィールを保存しました。\nプラットフォーム：{self.platform}\nプレイヤー：{self.player_name.value}"
        if self.return_to_panel:
            await interaction.response.defer()
            await interaction.edit_original_response(
                content=normal_panel_message(message),
                view=NormalSessionView(),
            )
            return
        await interaction.response.send_message(message, ephemeral=True)


class PlatformSelect(discord.ui.Select):
    def __init__(self, return_to_panel: bool = False) -> None:
        self.return_to_panel = return_to_panel
        options = [
            discord.SelectOption(label="PC", value="PC", description="Origin / EAアカウント名を使います"),
            discord.SelectOption(label="PlayStation", value="PS4", description="PS4 / PS5"),
            discord.SelectOption(label="Xbox", value="X1"),
            discord.SelectOption(label="Nintendo Switch", value="SWITCH"),
        ]
        super().__init__(placeholder="プラットフォームを選択してください", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PlayerNameModal(self.values[0], return_to_panel=self.return_to_panel))


class PlatformSelectView(discord.ui.View):
    def __init__(self, return_to_panel: bool = False) -> None:
        super().__init__(timeout=180)
        self.add_item(PlatformSelect(return_to_panel=return_to_panel))


# ---------------------------------------------------------- メインパネル ----


class NormalSessionSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="試合を記録", value="match", description="死亡原因と試合結果を入力"),
            discord.SelectOption(label="試合を修正", value="edit_recent", description="直近の試合記録を修正"),
            discord.SelectOption(label="キャラ変更", value="legend", description="以降の試合の使用キャラを変更"),
            discord.SelectOption(label="セッション統計", value="summary", description="現在のセッション統計を表示"),
            discord.SelectOption(label="セッション終了", value="end", description="集計を表示して終了"),
            discord.SelectOption(label="その他", value="other", description="外部API・CSV・リセットなど"),
        ]
        super().__init__(
            custom_id="apex_stats_bot:normal_panel",
            placeholder="操作を選択してください",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        action = self.values[0]

        if action == "match":
            state, error = active_state_or_message(interaction.user.id)
            if error:
                await interaction.response.edit_message(content=error, view=None)
                return
            legend = state.get("current_legend", "？")
            await interaction.response.edit_message(
                content=f"キャラはそのままですか？\n現在：{legend}",
                view=LegendConfirmView(legend, panel_interaction=interaction),
            )
        elif action == "edit_recent":
            state, error = active_state_or_message(interaction.user.id)
            if error:
                await interaction.response.edit_message(content=error, view=None)
                return
            rows = current_session_rows(interaction.user.id, state.get("current_session_id"))
            if not rows:
                await interaction.response.edit_message(content=normal_panel_message("このセッションにまだ試合記録がありません。"), view=NormalSessionView())
                return
            recent = rows[-25:]
            await interaction.response.edit_message(content="修正する試合を選択してください。", view=RecentMatchView(recent, panel_interaction=interaction))
        elif action == "legend":
            state = load_state(interaction.user.id)
            if not state or not state.get("is_active"):
                await interaction.response.edit_message(content="先にセッションを開始してください。", view=None)
                return
            await interaction.response.edit_message(content="使用キャラを選択してください。", view=LegendView("legend_panel"))
        elif action == "summary":
            state, error = active_state_or_message(interaction.user.id)
            if error:
                await interaction.response.edit_message(content=error, view=None)
                return
            rows = current_session_rows(interaction.user.id, state.get("current_session_id"))
            text = build_summary_text(rows)
            await interaction.response.edit_message(content=normal_panel_message(text), view=NormalSessionView())
        elif action == "end":
            state, error = active_state_or_message(interaction.user.id)
            if error:
                await interaction.response.edit_message(content=error, view=None)
                return
            await interaction.response.edit_message(content="セッションを終了しますか？", view=EndSessionView(interaction.user.id))
        elif action == "other":
            await interaction.response.edit_message(content="**次の操作を選択してください。**", view=OtherMenuView())


class NormalSessionView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(NormalSessionSelect())


class OtherMenuSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="CSVエクスポート", value="export", description="自分のmatches.csvを送信"),
            discord.SelectOption(label="セッションリセット", value="reset", description="現在のセッションだけ削除"),
            discord.SelectOption(label="Apexプロフィール設定", value="apex_set", description="Mozambique API用プロフィールを保存"),
            discord.SelectOption(label="Apex統計", value="apex_stats", description="保存済みプロフィールの統計を表示"),
            discord.SelectOption(label="マップローテ", value="apex_map", description="現在と次のマップを表示"),
            discord.SelectOption(label="プレデターRP", value="apex_predator", description="プレデター到達RPを表示"),
            discord.SelectOption(label="通常メニューへ戻る", value="back", description="通常メニューを表示"),
        ]
        super().__init__(
            custom_id="apex_stats_bot:other_panel",
            placeholder="その他の操作を選択してください",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        action = self.values[0]

        if action == "export":
            path = matches_path(interaction.user.id)
            if not path.exists() or path.stat().st_size == 0:
                await interaction.response.edit_message(content=normal_panel_message("まだ記録がありません。"), view=NormalSessionView())
                return
            await interaction.response.defer()
            await interaction.followup.send(file=discord.File(path), ephemeral=True)
            await interaction.edit_original_response(content=normal_panel_message("CSVを送信しました。"), view=NormalSessionView())

        elif action == "reset":
            state, error = active_state_or_message(interaction.user.id)
            if error:
                await interaction.response.edit_message(content=error, view=None)
                return
            session_id = str(state["current_session_id"])
            await interaction.response.edit_message(
                content=f"現在のセッション（{session_id}）の記録を削除します。よろしいですか？",
                view=ResetView(interaction.user.id, session_id, return_to_panel=True),
            )

        elif action == "apex_set":
            await interaction.response.edit_message(content="プラットフォームを選択してください。", view=PlatformSelectView(return_to_panel=True))

        elif action == "apex_stats":
            saved_profile = load_apex_profile(interaction.user.id) or {}
            if not saved_profile.get("platform") or not saved_profile.get("player_name"):
                await interaction.response.edit_message(
                    content=normal_panel_message("先に「Apexプロフィール設定」でプロフィールを保存してください。"),
                    view=NormalSessionView(),
                )
                return
            await interaction.response.defer()
            try:
                profile = await fetch_player_stats(str(saved_profile["platform"]), str(saved_profile["player_name"]))
            except MozambiqueApiError as error:
                await interaction.edit_original_response(content=normal_panel_message(str(error)), view=NormalSessionView())
                return
            text = build_player_summary(profile, str(saved_profile["platform"]), str(saved_profile["player_name"]))
            await interaction.edit_original_response(content=normal_panel_message(text), view=NormalSessionView())

        elif action == "apex_map":
            await interaction.response.defer()
            try:
                rotation = await fetch_map_rotation()
            except MozambiqueApiError as error:
                await interaction.edit_original_response(content=normal_panel_message(str(error)), view=NormalSessionView())
                return
            await interaction.edit_original_response(content=normal_panel_message(build_map_summary(rotation)), view=NormalSessionView())

        elif action == "apex_predator":
            await interaction.response.defer()
            try:
                predator = await fetch_predator()
            except MozambiqueApiError as error:
                await interaction.edit_original_response(content=normal_panel_message(str(error)), view=NormalSessionView())
                return
            await interaction.edit_original_response(content=normal_panel_message(build_predator_summary(predator)), view=NormalSessionView())

        elif action == "back":
            await interaction.response.edit_message(content=normal_panel_message(), view=NormalSessionView())


class OtherMenuView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(OtherMenuSelect())


class NewSessionConfirmView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.button(label="新しく開始", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="使用キャラを選択してください。", view=LegendView("start_panel"))

    @discord.ui.button(label="既存のセッションを継続", style=discord.ButtonStyle.secondary)
    async def resume(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=normal_panel_message(), view=NormalSessionView())


class PanelButtonView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="セッションを開始", style=discord.ButtonStyle.primary, custom_id="apex_stats_bot:open_panel")
    async def open_panel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        state = load_state(interaction.user.id)
        if state and state.get("is_active"):
            session_id = state.get("current_session_id", "")
            legend = state.get("current_legend", "")
            await interaction.response.send_message(
                f"セッション **{session_id}**（{legend}）が進行中です。\n新しく開始すると現在のセッションは終了します。",
                view=NewSessionConfirmView(),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("使用キャラを選択してください。", view=LegendView("start_panel"), ephemeral=True)


# --------------------------------------------------------- action helpers ---
# スラッシュコマンド用（パネルからは呼ばれない）


async def send_normal_panel(interaction: discord.Interaction, prefix: str | None = None) -> None:
    content = normal_panel_message(prefix)
    view = NormalSessionView()
    if interaction.response.is_done():
        await interaction.followup.send(content, view=view, ephemeral=True)
    else:
        await interaction.response.send_message(content, view=view, ephemeral=True)


async def send_summary(interaction: discord.Interaction) -> None:
    state, error = active_state_or_message(interaction.user.id)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    rows = current_session_rows(interaction.user.id, state.get("current_session_id"))
    await interaction.response.send_message(build_summary_text(rows), ephemeral=True)


async def end_session(interaction: discord.Interaction) -> None:
    state, error = active_state_or_message(interaction.user.id)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    rows = current_session_rows(interaction.user.id, state.get("current_session_id"))
    text = build_summary_text(rows)
    state["is_active"] = False
    save_state(interaction.user.id, state)
    await interaction.response.send_message(f"{text}\n\nセッションを終了しました。", ephemeral=True)


async def export_matches(interaction: discord.Interaction) -> None:
    path = matches_path(interaction.user.id)
    if not path.exists() or path.stat().st_size == 0:
        await interaction.response.send_message("まだ記録がありません。", ephemeral=True)
        return
    await interaction.response.send_message(file=discord.File(path), ephemeral=True)


async def confirm_reset(interaction: discord.Interaction) -> None:
    state, error = active_state_or_message(interaction.user.id)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    session_id = str(state["current_session_id"])
    await interaction.response.send_message(
        f"現在のセッション（{session_id}）の記録を削除します。よろしいですか？",
        view=ResetView(interaction.user.id, session_id, return_to_panel=False),
        ephemeral=True,
    )


async def send_apex_stats(interaction: discord.Interaction) -> None:
    saved_profile = load_apex_profile(interaction.user.id) or {}
    target_platform = saved_profile.get("platform")
    target_player = saved_profile.get("player_name")
    if not target_platform or not target_player:
        await interaction.response.send_message(
            "先に /apex_set でApexプロフィールを保存してください。",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True)
    try:
        profile = await fetch_player_stats(str(target_platform), str(target_player))
    except MozambiqueApiError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    await interaction.followup.send(build_player_summary(profile, str(target_platform), str(target_player)), ephemeral=True)


async def send_map_rotation(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        rotation = await fetch_map_rotation()
    except MozambiqueApiError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    await interaction.followup.send(build_map_summary(rotation), ephemeral=True)


async def send_predator(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        predator = await fetch_predator()
    except MozambiqueApiError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    await interaction.followup.send(build_predator_summary(predator), ephemeral=True)
