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

VERSION = "1.4.0"

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
        "stickers": False,
    },
    "clone_messages": {
        "comment": "Clone messages in all channels (last messages). Long limit - long time need to copy",
        "enabled": True,
        "comment_use_queue": "Clone messages using queue for each channels and caches all messages before sending",
        "use_queue": True,
        "oldest_first": True,
        "comment_parallel": "Clone messages for all channels (can be used with queue)",
        "parallel": True,
        "webhooks_clear": True,
        "limit": 8196,
        "delay": 0.65,
    },
    "live_update": {
        "comment": "Automatically detect new messages and send it via webhook",
        "comment_2": "Also works with clone_messages (starts sending when channel is fully processed)",
        "enabled": False,
        "message_delay": 0.75,
    },
}

data.set_default(default=default_config)

logger = Logger()
logger.bind(server="CONFIGURATION")

if not data.file_exists(config_path):
    data.write_defaults().flush()
    logger.error("Configuration doesn't found. Re-created it.")
    sys.exit(-1)


def remove_comments(config_dict: dict):
    keys_to_remove = [key for key in config_dict if "comment" in key]
    for key in keys_to_remove:
        del config_dict[key]
    for value in config_dict.values():
        if isinstance(value, dict):
            remove_comments(value)


def check_missing_keys(
    config_data: Configuration, default_data: dict, path: list = None
) -> tuple[dict, list]:
    if path is None:
        path = []
    missing_elements = []
    updated_config = {}
    for key, default in default_data.items():
        if isinstance(default, dict):
            if config_data.read(path + [key]) is None:
                config_data.write(path + [key], default).flush()
                missing_elements.append(key)
            updated_config[key], missing_path_keys = check_missing_keys(
                config_data, default, path + [key]
            )
            missing_elements += missing_path_keys
        else:
            if config_data.read(path + [key]) is None:
                config_data.write(path + [key], default).flush()
                missing_elements.append(key)
            updated_config[key] = config_data.read(path + [key])
    return updated_config, missing_elements


new_config, missing_keys = check_missing_keys(data, default_config)

if missing_keys:
    logger.error(
        f"Missing keys {missing_keys} in configuration. Re-created them with default values."
    )
    logger.error("Restart the program to continue.")
    sys.exit(-1)

config_values = new_config
remove_comments(config_values)

token, prefix, debug = (
    config_values["token"],
    config_values["prefix"],
    config_values["debug"],
)
clone_settings_values = config_values["clone_settings"]
clone_messages_values = config_values["clone_messages"]
live_update_values = config_values["live_update"]

(
    name_syntax,
    clone_delay,
    clear_guild,
    clone_icon,
    clone_banner,
    clone_roles,
    clone_channels,
    clone_overwrites,
    clone_emojis,
    clone_stickers,
) = clone_settings_values.values()
(
    clone_messages_enabled,
    clone_queue,
    clone_oldest_first,
    clone_parallel,
    messages_webhook_clear,
    messages_limit,
    messages_delay,
) = clone_messages_values.values()
live_update_enabled, live_delay = live_update_values.values()

logger = Logger(debug_enabled=debug)

cloner_instances = []

if clone_channels and (not clone_roles and clone_overwrites):
    clone_roles = True
    logger.warning(
        "Clone roles enabled because clone overwrites and channels are enabled."
    )

if live_update_enabled and not clone_channels:
    logger.error("Live update disabled because clone channels is disabled.")
    live_update_enabled = False

if clone_messages_enabled and (messages_limit <= 0):
    clone_messages_enabled = False
    logger.warning("Messages disabled because its limit is zero.")

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, self_bot=True)

logger.reset()


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
    cloner: ServerCopy = ServerCopy(
        from_guild=guild,
        to_guild=None,
        delay=clone_delay,
        webhook_delay=messages_delay,
        live_update_toggled=live_update_enabled,
        enable_queue=clone_queue,
        enable_parallel=clone_parallel,
        oldest_first=clone_oldest_first,
    )
    clone = cloner.logger
    if bot.get_guild(new_server_id) is None:
        clone.info("Creating server...")
        try:
            new_guild: discord.Guild = await bot.create_guild(name=target_name)
        except discord.HTTPException:
            clone.error(
                'Unable to create server automatically. Create it yourself and run command with "new=id" argument'
            )
            return
    else:
        clone.info("Getting server...")
        new_guild: discord.Guild = bot.get_guild(new_server_id)

    if new_guild is None:
        clone.error("Can't create server. Maybe account invalid or requires captcha?")
        return

    if new_guild.name is not target_name:
        await new_guild.edit(name=target_name)

    cloner.new_guild = new_guild
    cloner_instances.append(cloner)

    clone.info("Processing modules")

    if clear_guild:
        clone.info("Preparing guild to process...")
        await cloner.prepare_server()
    if clone_icon:
        clone.info("Processing server icon...")
        await cloner.clone_icon()
    if clone_banner:
        clone.info("Processing server banner...")
        await cloner.clone_banner()
    if clone_roles:
        clone.info("Processing server roles...")
        await cloner.clone_roles()
    if clone_channels:
        clone.info("Processing server categories and channels...")
        await cloner.clone_categories(perms=clone_overwrites)
        await cloner.clone_channels(perms=clone_overwrites)
    if clone_emojis:
        clone.info("Processing server emojis...")
        await cloner.clone_emojis()
    if clone_stickers:
        clone.info("Processing stickers...")
        await cloner.clone_stickers()
    if cloner.enabled_community and clone_channels:
        clone.info("Processing community settings & additional channels...")
        await cloner.process_community()
        await cloner.add_community_channels(perms=clone_overwrites)
    if live_update_enabled:
        clone.info("Processing server messages...")
        await cloner.clone_messages(limit=messages_limit, clear=messages_webhook_clear)
    clone.success(f"Done in {round((time.time() - start_time), 2)} seconds.")


if __name__ == "__main__":
    Updater(current_version=VERSION)
    file_handler = logging.FileHandler(
        f'{datetime.now().strftime("%d-%m-%Y")}-discord.log'
    )
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    logger.info("Logging in discord account...")
    bot.run(token, log_handler=file_handler, log_formatter=formatter)
