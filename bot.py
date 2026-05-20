from __future__ import annotations

import os
import sys

_venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(_venv_python) and os.path.abspath(sys.executable) != os.path.abspath(_venv_python):
    os.execv(_venv_python, [_venv_python] + sys.argv)

import discord
from discord.ext import commands
from dotenv import load_dotenv

from views import NormalSessionView, OtherMenuView, PanelButtonView


class ApexStatsBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        self.add_view(NormalSessionView())
        self.add_view(OtherMenuView())
        self.add_view(PanelButtonView())
        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} guild slash commands.")
            return

        synced = await self.tree.sync()
        print(f"Synced {len(synced)} global slash commands.")


bot = ApexStatsBot()

sys.modules.setdefault("bot", sys.modules["__main__"])
import commands  # noqa: E402 — registers slash commands via @bot.tree.command


def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError(".env に DISCORD_BOT_TOKEN を設定してください。")
    bot.run(token)


if __name__ == "__main__":
    main()
