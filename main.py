# -*- encoding: utf-8 -*-

import logging
import os
import sys
import time

from datetime import datetime

import discord
from discord.ext import commands

from modules.logger import Logger
from modules.configuration import Configuration
from modules.updater import Updater
from modules.cloner import ServerCopy

VERSION = "1.3.9"

config_path = "config.json"
data: Configuration = Configuration(config_path)

default_config: dict = {
    "token": "Your discord account token",
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
        "stickers": False
    },
    "clone_messages": {
        "__comment__": "Clone messages in all channels (last messages). Long limit - long time need to copy",
        "enabled": True,
        "__comment_use_queue__": "Clone messages using queue for each channels and caches all messages before sending",
        "use_queue": True,
        "oldest_first": True,
        "__comment_parallel__": "Clone messages for all channels (can be used with queue)",
        "parallel": True,
        "webhooks_clear": True,
        "limit": 8196,
        "delay": 0.65
    },
    "live_update": {
        "__comment__": "Automatically detect new messages and send it via webhook",
        "__comment_2__": "Also works with clone_messages (starts sending when channel is fully processed)",
        "enabled": False,
        "message_delay": 0.75
    }
}
data.set_default(default_config)

cloner_instances = []

logger = Logger()
logger.patch(lambda record: record["extra"].setdefault("server", "MAIN"))

try:
    if not data.file_exists(config_path):
        data.write_defaults().flush()
        logger.error("Configuration doesn't found. Re-created it.")
        sys.exit(-1)
    token: str = data.read("token")
    prefix: str = data.read("prefix")
    debug: bool = data.read("debug")

    logger = Logger(debug_enabled=debug)

    clone_settings: dict = data.read("clone_settings")

    name_syntax: str = clone_settings["name_syntax"]
    clone_delay: float = clone_settings["clone_delay"]
    clear_guild: bool = clone_settings["clear_guild"]
    clone_icon: bool = clone_settings["icon"]
    clone_banner: bool = clone_settings["banner"]
    clone_roles: bool = clone_settings["roles"]
    clone_channels: bool = clone_settings["channels"]
    clone_overwrites: bool = clone_settings["overwrites"]
    clone_emojis: bool = clone_settings["emoji"]
    clone_stickers: bool = clone_settings["stickers"]

    messages_settings: dict = data.read("clone_messages")

    clone_messages: bool = messages_settings["enabled"]
    clone_oldest_first: bool = messages_settings["oldest_first"]
    clone_queue: bool = messages_settings["use_queue"]
    clone_parallel: bool = messages_settings["parallel"]
    messages_webhook_clear: bool = messages_settings["webhooks_clear"]
    messages_limit: int = messages_settings["limit"]
    messages_delay: float = messages_settings["delay"]

    live_settings: dict = data.read("live_update")

    live_update: bool = live_settings["enabled"]
    live_delay: float = live_settings["message_delay"]
except KeyError:
    token = data.read("token")
    os.remove("config.json")
    data.config = {}
    data.write_defaults().flush()
    if "token" not in token:
        logger.debug("Found token in wrong configuration. Saved it.")
    data.write(key="token", value=token).flush()
    logger.error("Something is wrong with configuration. Re-created it with saved token (if present).")
    logger.error("Restart the program to continue.")
    sys.exit(-1)

if clone_channels and (not clone_roles and clone_overwrites):
    clone_roles = True
    logger.warning("Clone roles enabled because clone overwrites and channels are enabled.")

if live_update and not clone_channels:
    logger.error("Live update disabled because clone channels is disabled.")
    live_update = False

if clone_messages and (messages_limit <= 0):
    clone_messages = False
    logger.warning("Messages disabled because its limit is zero.")

bot = commands.Bot(command_prefix=prefix, case_insensitive=True,
                   self_bot=True)


@bot.event
async def on_connect():
    logger.success("Logged on as {0.user}".format(bot))


@bot.event
async def on_message(message: discord.Message):
    if cloner_instances:
        for instance in cloner_instances:
            await instance.on_message(message=message)
    await bot.process_commands(message)


def format_guild_name(target_guild: discord.Guild) -> str:
    return name_syntax.replace("%original%", target_guild.name)


@bot.command(name="copy", aliases=["clone", "paste", "parse", "start"])
async def copy(ctx: commands.Context, *, args: str = ""):
    global cloner_instances
    await ctx.message.delete()
    server_id: int | None = None
    new_server_id: int | None = None
    for arg in args.split():
        key_value = arg.split("=") if "=" in arg else (arg, None)
        key, value = key_value
        if key == "new" and value.isdigit():
            new_server_id = int(value)
        elif key == "id" and value.isdigit():
            server_id = int(value)
    guild: discord.Guild = bot.get_guild(server_id) if server_id else ctx.guild
    if guild is None and server_id is None:
        return

    start_time = time.time()
    target_name = format_guild_name(target_guild=guild)
    cloner: ServerCopy = ServerCopy(from_guild=guild, to_guild=None,
                                    delay=clone_delay, webhook_delay=messages_delay,
                                    live_update_toggled=live_update, enable_queue=clone_queue,
                                    enable_parallel=clone_parallel, oldest_first=clone_oldest_first)
    clone_logger = cloner.logger
    if bot.get_guild(new_server_id) is None:
        clone_logger.info("Creating server...")
        try:
            new_guild: discord.Guild = await bot.create_guild(name=target_name)
        except discord.HTTPException:
            clone_logger.error(
                "Unable to create server automatically. Create it yourself and run command with \"new=id\" argument")
            return
    else:
        clone_logger.info("Getting server...")
        new_guild: discord.Guild = bot.get_guild(new_server_id)

    if new_guild is None:
        clone_logger.error("Can't create server. Maybe account invalid or requires captcha?")
        return

    if new_guild.name is not target_name:
        await new_guild.edit(name=target_name)

    cloner.new_guild = new_guild
    cloner_instances.append(cloner)

    clone_logger.info("Processing modules")

    if clear_guild:
        clone_logger.info("Preparing guild to process...")
        await cloner.prepare_server()
    if clone_icon:
        clone_logger.info("Processing server icon...")
        await cloner.clone_icon()
    if clone_banner:
        clone_logger.info("Processing server banner...")
        await cloner.clone_banner()
    if clone_roles:
        clone_logger.info("Processing server roles...")
        await cloner.clone_roles()
    if clone_channels:
        clone_logger.info("Processing server categories and channels...")
        await cloner.clone_categories(perms=clone_overwrites)
        await cloner.clone_channels(perms=clone_overwrites)
    if clone_emojis:
        clone_logger.info("Processing server emojis...")
        await cloner.clone_emojis()
    if clone_stickers:
        clone_logger.info("Processing stickers...")
        await cloner.clone_stickers()
    if cloner.enabled_community and clone_channels:
        clone_logger.info("Processing community settings & additional channels...")
        await cloner.process_community()
        await cloner.add_community_channels(perms=clone_overwrites)
    if clone_messages:
        clone_logger.info("Processing server messages...")
        await cloner.clone_messages(limit=messages_limit, clear=messages_webhook_clear)
    clone_logger.success(f"Done in {round((time.time() - start_time), 2)} seconds.")


if __name__ == '__main__':
    Updater(current_version=VERSION)
    file_handler = logging.FileHandler(f'{datetime.now().strftime("%d-%m-%Y")}-discord.log')
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    logger.info("Logging in discord account...")
    bot.run(token, log_handler=file_handler, log_formatter=formatter)
