# -*- encoding: utf-8 -*-

import logging
import os
import sys

from datetime import datetime

import discord
from discord.ext import commands

from modules.logger import Logger
from modules.configuration import Configuration, check_missing_keys
from modules.updater import Updater
from modules.utilities import get_command_info

VERSION = "1.4.8"

config_path = "config.json"
data: Configuration = Configuration(config_path)

default_config: dict = {
    "token": "MTIwMjEzNDgzMjk5ODc5NzM0NQ.G9IEZJ.aV4eYEXnwFimufAiLYpYp-YpqRl5UXMksDvMZc",
    "prefix": "cp!",
    "debug": True,
    "clone_settings": {
        "name_syntax": "%original%-copy",
        "clone_delay": 1.337,
        "clear_guild": True,
        "icon": True,
        "banner": True,
        "roles": True,
        "channels": True,
        "overwrites": True,
        "emoji": False,
        "stickers": False,
    },
    "clone_messages": {
        "__comment__": "Clone messages in all channels (last messages). Long limit - long time need to copy",
        "enabled": True,
        "oldest_first": True,
        "webhooks_clear": True,
        "limit": 8196,
        "delay": 0.65,
    },
    "live_update": {
        "__comment__": "Automatically detect new messages and send it via webhook",
        "__comment2__": "Also works with clone_messages (starts sending when channel is fully processed)",
        "enabled": False,
        "process_new_messages": True,
        "message_delay": 0.75,
    },
}

data.set_default(default=default_config)

logger = Logger()
logger.bind(source="Configuration")

if not data.file_exists(config_path):
    data.write_defaults().flush()
    logger.error("Configuration doesn't found. Re-created it.")
    sys.exit(-1)

new_config, missing_keys = check_missing_keys(config_data=data,
                                              default_data=default_config)

if missing_keys:
    logger.error(f"Missing keys {missing_keys} in configuration. Re-created them with default values.")
    logger.error("Restart the program to continue.")
    sys.exit(-1)

config_values = new_config

token, prefix, debug = (
    config_values["token"],
    config_values["prefix"],
    config_values["debug"],
)

clone_settings_values = config_values["clone_settings"]
clone_messages_values = config_values["clone_messages"]
live_update_values = config_values["live_update"]

name_syntax, clone_delay, clear_guild, clone_icon, clone_banner, clone_roles = (
    clone_settings_values["name_syntax"],
    clone_settings_values["clone_delay"],
    clone_settings_values["clear_guild"],
    clone_settings_values["icon"],
    clone_settings_values["banner"],
    clone_settings_values["roles"],
)

clone_channels, clone_overwrites, clone_emojis, clone_stickers = (
    clone_settings_values["channels"],
    clone_settings_values["overwrites"],
    clone_settings_values["emoji"],
    clone_settings_values["stickers"],
)

clone_messages_enabled, clone_oldest_first = (
    clone_messages_values["enabled"],
    clone_messages_values["oldest_first"],
)

messages_webhook_clear, messages_limit, messages_delay = (
    clone_messages_values["webhooks_clear"],
    clone_messages_values["limit"],
    clone_messages_values["delay"],
)

live_update_enabled, process_new_messages_enabled, live_delay = (
    live_update_values["enabled"],
    live_update_values["process_new_messages"],
    live_update_values["message_delay"]
)

logger = Logger(debug_enabled=debug)

if clone_channels and (not clone_roles and clone_overwrites):
    clone_roles = True
    logger.warning("Clone roles enabled because clone overwrites and channels are enabled.")

if live_update_enabled and not clone_channels:
    logger.error("Live update disabled because clone channels is disabled.")
    live_update_enabled = False

if clone_messages_enabled and (messages_limit <= 0):
    clone_messages_enabled = False
    logger.warning("Messages disabled because its limit is zero.")

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, self_bot=True)
bot.remove_command('help')

logger.reset()


@bot.event
async def on_connect():
    logger.success("Logged on as {0.user}".format(bot))

    if len(bot.extensions) > 0:
        return

    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('_'):
            await bot.load_extension(f'cogs.{filename[:-3]}')

    logger.info("Loaded {} extensions, with total of {} commands", len(bot.cogs), len(bot.commands))


@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)


@bot.command(name="help")
async def print_help(ctx: commands.Context):
    """
    Sends this message
    """

    help_message = f"""```\n
* Version: {VERSION}
* Github: github.com/itskekoff/discord-server-copy\n
{get_command_info(bot)}
```
    """
    await ctx.message.edit(content=help_message)


if __name__ == "__main__":
    updater: Updater = Updater(current_version=VERSION, github_repo="itskekoff/discord-server-copy")
    updater.check_for_updates()

    file_handler = logging.FileHandler(f'{datetime.now().strftime("%d-%m-%Y")}-discord.log')
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    logger.info("Logging in discord account...")
    bot.run(token, log_handler=file_handler, log_formatter=formatter)
