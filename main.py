# -*- encoding: utf-8 -*-

import asyncio
import json
import logging
import os
import sys
import time
import typing
import urllib.request
from datetime import datetime

import discord
from discord.ext import commands
from loguru import logger


def file_exists(file_path: str):
    # check if file exists
    return os.path.exists(file_path)


class LoggerSetup:
    FILE_LOG_FORMAT = "<white>[{time:YYYY-MM-DD HH:mm:ss}</white>] | <level>{level: <8}</level> | <white>{message}</white>"
    CONSOLE_LOG_FORMAT = "<white>{time:HH:mm:ss}</white> | <level>{level: <8}</level> | <white>{message}</white>"

    def __init__(self, debug_enabled: bool = True):
        logger.remove()
        log_file_name = f'{datetime.now().strftime("%d-%m-%Y")}.log'
        log_file_path = log_file_name
        logger.add(log_file_path, format=self.FILE_LOG_FORMAT, level="DEBUG", rotation='1 day')
        logger.add(sys.stderr, colorize=True, format=self.CONSOLE_LOG_FORMAT,
                   level='DEBUG' if debug_enabled else 'INFO')


class Configuration:

    def __init__(self, config_file_path):
        self.config_file_path = config_file_path
        self.config = {}
        self._default_config = {}
        if file_exists(config_file_path):
            with open(self.config_file_path, "r") as config_file_object:
                self.config = json.load(config_file_object)
                config_file_object.close()

    def read(self, key: typing.Any) -> typing.Any:
        if key not in self.config:
            return None
        return self.config[key]

    def write(self, key: typing.Any, value: typing.Any):
        self.config[key] = value
        return self

    def write_dict(self, to_write: dict):
        for key, value in to_write.items():
            self.write(key, value)
        return self

    def flush(self):
        with open(self.config_file_path, "w+") as config_file_object:
            config_file_object.write(json.dumps(self.config, indent=2, ensure_ascii=False))
            config_file_object.close()
        return self

    def set_default(self, default: dict):
        self._default_config = default
        return self

    def write_defaults(self):
        return self.write_dict(self._default_config)


config_path = "config.json"
data: Configuration = Configuration(config_path)
default_config: dict = {
    "token": "Your discord account token",
    "prefix": "cp!",
    "debug": True,
    "new_server_id": 0,
    "clone_settings": {
        "name_syntax": "%original-copy",
        "clone_delay": 0.85,
        "clear_guild": True,
        "icon": True,
        "roles": True,
        "channels": True,
        "overwrites": True,
        "emoji": False,
    },
    "clone_messages": {
        "__comment__": "Clone messages in all channels (last messages). Long limit - long time need to copy",
        "enabled": False,
        "webhooks_clear": True,
        "limit": 8196,
        "delay": 0.65
    },
    "live_update": {
        "__comment__": "Automatically detect new messages and send it via webhook",
        "enabled": False,
        "message_delay": 0.75
    }
}
data.set_default(default_config)

if not file_exists(config_path):
    data.write_defaults().flush()
    logger.error("Configuration doesn't found. Re-created it.")
    sys.exit(0)

register_on_message = False
cloner_instances = []

try:
    token: str = data.read("token")
    prefix: str = data.read("prefix")
    debug: bool = data.read("debug")
    new_server_id: int = data.read("new_server_id")

    clone_settings: dict = data.read("clone_settings")

    name_syntax: str = clone_settings["name_syntax"]
    clone_delay: float = clone_settings["clone_delay"]
    clear_guild: bool = clone_settings["clear_guild"]
    clone_icon: bool = clone_settings["icon"]
    clone_roles: bool = clone_settings["roles"]
    clone_channels: bool = clone_settings["channels"]
    clone_overwrites: bool = clone_settings["overwrites"]
    clone_emojis: bool = clone_settings["emoji"]

    messages_settings: dict = data.read("clone_messages")
    clone_messages: bool = messages_settings["enabled"]
    webhooks_clear: bool = messages_settings["webhooks_clear"]
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
    sys.exit(0)

if clone_channels and not clone_roles and clone_overwrites:
    clone_roles = True
    data.write(key="roles", value=True).flush()

if live_update and not clone_channels:
    logger.error("* Live update disabled because clone channels is disabled.")
    live_update = False


class Updater:
    def __init__(self, version: str):
        resp = urllib.request.urlopen(
            url="https://raw.githubusercontent.com/itskekoff/discord-server-copy/main/main.py").read()
        target_version = resp[resp.find(b'Updater('):]
        if version.encode("utf-8") in target_version:
            logger.info("Updates doesn't found.")
        else:
            logger.warning("Update available. Download it from github.")


class ServerCopy:
    def __init__(self, from_guild: discord.Guild,
                 to_guild: discord.Guild, delay: float = 1,
                 webhook_delay: float = 0.65, debug_enabled: bool = True):
        self.guild = from_guild
        self.new_guild = to_guild
        self.delay = delay
        self.webhook_delay = webhook_delay
        self.debug = debug_enabled

        self.processing_messages = False
        self.messages_to_send: list[discord.Message] = []
        self.mappings = {"roles": {}, "categories": {},
                         "webhooks": {}, "channels": {},
                         "messages": {}}

    @staticmethod
    def get_key(value: typing.Any, my_dict: dict) -> typing.Any:
        try:
            return list(my_dict.keys())[list(my_dict.values()).index(value)]
        except ValueError:
            return None

    async def prepare_server(self):
        for channel in await self.new_guild.fetch_channels():
            await channel.delete()

    async def clone_icon(self):
        if self.guild.icon is not None:
            await self.new_guild.edit(icon=await self.guild.icon.read())
            if self.guild.banner is not None:
                await self.new_guild.edit(banner=await self.guild.banner.read())
            await asyncio.sleep(self.delay)

    async def clone_roles(self):
        roles_create = []
        role: discord.Role
        for role in self.guild.roles:
            if role.name != "@everyone":
                roles_create.append(role)
            else:
                self.mappings["roles"][role] = discord.utils.get(self.new_guild.roles, name="@everyone")
        for role in reversed(roles_create):
            new_role = await self.new_guild.create_role(name=role.name, colour=role.colour,
                                                        hoist=role.hoist, mentionable=role.mentionable,
                                                        permissions=role.permissions)
            self.mappings["roles"][role] = new_role
            if self.debug:
                logger.debug("Created role: " + str(new_role.id) + " | " + new_role.name)
            await asyncio.sleep(self.delay)

    async def clone_categories(self, perms: bool = True):
        for category in self.guild.categories:
            overwrites: dict = {}
            if perms:
                for role, permissions in category.overwrites.items():
                    if isinstance(role, discord.Role):
                        overwrites[self.mappings["roles"][role]] = permissions
            new_category = await self.new_guild.create_category(name=category.name, position=category.position,
                                                                overwrites=overwrites)
            self.mappings["categories"][category] = new_category
            if self.debug:
                logger.debug("Created category: " + str(new_category.id) + " | " + new_category.name)
            await asyncio.sleep(self.delay)

    async def clone_channels(self, perms: bool = True):
        for channel in self.guild.channels:
            category = self.mappings.get("categories", {}).get(channel.category, None)
            overwrites: dict = {}
            if perms:
                for role, permissions in channel.overwrites.items():
                    if isinstance(role, discord.Role):
                        overwrites[self.mappings["roles"][role]] = permissions
            if isinstance(channel, discord.TextChannel):
                new_channel = await self.new_guild.create_text_channel(name=channel.name,
                                                                       position=channel.position,
                                                                       topic=channel.topic,
                                                                       slowmode_delay=channel.slowmode_delay,
                                                                       nsfw=channel.nsfw,
                                                                       category=category,
                                                                       overwrites=overwrites)
                self.mappings["channels"][channel] = new_channel
                if self.debug:
                    logger.debug("Created text channel " + str(channel.id) + " | " + new_channel.name)
            elif isinstance(channel, discord.VoiceChannel):
                bitrate = channel.bitrate if channel.bitrate <= 96000 else None
                new_channel = await self.new_guild.create_voice_channel(name=channel.name,
                                                                        position=channel.position,
                                                                        bitrate=bitrate,
                                                                        user_limit=channel.user_limit,
                                                                        category=category,
                                                                        overwrites=overwrites)
                if self.debug:
                    logger.debug("Created voice channel " + str(channel.id) + " | " + new_channel.name)
            await asyncio.sleep(self.delay)

    async def clone_emojis(self):
        for emoji in self.guild.emojis:
            if self.debug:
                logger.debug("Created emoji: " + str(emoji.id) + " | " + emoji.name)
            await self.new_guild.create_custom_emoji(name=emoji.name, image=await emoji.read())
            await asyncio.sleep(self.delay)

    async def send_webhook(self, webhook: discord.Webhook, message: discord.Message,
                           delay: float = 0.85):
        author: discord.User = message.author
        files = []
        if message.attachments is not None:
            for attachment in message.attachments:
                files.append(await attachment.to_file())
        creation_time = message.created_at.strftime('%d/%m/%Y %H:%M')
        name: str = f"{author.name}#{author.discriminator} at {creation_time}"
        try:
            await webhook.send(content=message.content, avatar_url=author.display_avatar.url,
                               username=name, embeds=message.embeds,
                               files=files)
        except discord.errors.HTTPException:
            if self.debug:
                logger.debug("Can't send, skipping message in #" + webhook.channel.name)
        await asyncio.sleep(delay)

    async def clone_messages(self, limit: int = 512, clear: bool = True):
        self.processing_messages: bool = True
        for channel in self.mappings["channels"].values():
            webhook: discord.Webhook = await channel.create_webhook(name="billy")
            original_channel: discord.TextChannel = self.get_key(channel, self.mappings["channels"])
            if self.debug:
                logger.debug("Created webhook in #" + channel.name)
            self.mappings["webhooks"][webhook] = {original_channel: channel}
            try:
                async for message in original_channel.history(limit=limit, oldest_first=True):
                    self.mappings["messages"][message] = original_channel
                    await self.send_webhook(webhook, message, self.webhook_delay)
            except discord.errors.Forbidden:
                if self.debug:
                    logger.debug("Missing access for channel: #" + original_channel.name)
            if clear:
                if self.debug:
                    logger.debug("Deleted webhook in #" + channel.name)
                await webhook.delete()

    async def on_message(self, message: discord.Message):
        if message.guild is not None:
            if message.guild.id == self.guild.id:
                try:
                    new_channel = self.mappings["channels"][message.channel]
                    webhook = None
                    webhook_exists: bool = False
                    if self.get_key({message.channel: new_channel}, self.mappings["webhooks"]):
                        webhook_exists = True
                        webhook = self.get_key({message.channel: new_channel}, self.mappings["webhooks"])
                    if not webhook_exists:
                        webhook = await new_channel.create_webhook(name="billy")
                        if self.debug:
                            logger.debug("Created webhook in #" + new_channel.name)
                        self.mappings["webhooks"][webhook] = {message.channel: new_channel}
                    await self.send_webhook(webhook, message, live_delay)
                except KeyError:
                    pass


bot = commands.Bot(command_prefix=prefix, case_insensitive=True,
                   self_bot=True)


@bot.event
async def on_connect():
    logger.success("Logged on as {0.user}".format(bot))


@bot.event
async def on_message(message: discord.Message):
    if register_on_message and cloner_instances:
        for instance in cloner_instances:
            await instance.on_message(message=message)
    await bot.process_commands(message)


@bot.command(name="copy", aliases=["clone", "paste", "parse", "start"])
async def copy(ctx: commands.Context, server_id: int = None):
    global cloner_instances, register_on_message
    await ctx.message.delete()
    guild: discord.Guild = bot.get_guild(server_id) if server_id else ctx.message.guild
    if guild is None and server_id is None:
        return
    start_time = time.time()

    if bot.get_guild(new_server_id) is None:
        logger.info("Creating server...")
        try:
            new_guild: discord.Guild = await bot.create_guild(name_syntax.replace("%original", guild.name))
        except:
            logger.error(
                "Unable to create server automaticly. Сreate it yourself and enter its id in the config \"new_server_id\"")
    else:
        logger.info("Getting server...")
        new_guild: discord.Guild = bot.get_guild(new_server_id)

    cloner: ServerCopy = ServerCopy(from_guild=guild, to_guild=new_guild,
                                    delay=clone_delay, webhook_delay=messages_delay
                                    )
    cloner_instances.append(cloner)
    logger.info("Processing modules")
    if clear_guild:
        logger.info("Preparing guild to process...")
        await cloner.prepare_server()
    if clone_icon:
        logger.info("Cloning server icon...")
        await cloner.clone_icon()
    if clone_roles:
        logger.info("Cloning server roles...")
        await cloner.clone_roles()
    if clone_channels:
        logger.info("Cloning server categories and channels...")
        await cloner.clone_categories(perms=clone_overwrites)
        await cloner.clone_channels(perms=clone_overwrites)
    if clone_emojis:
        logger.info("Cloning server emojis...")
        await cloner.clone_emojis()
    if clone_messages:
        logger.info("Cloning server messages...")
        await cloner.clone_messages(limit=messages_limit, clear=webhooks_clear)
    if live_update:
        register_on_message = True
    logger.success(f"Done in {round((time.time() - start_time), 2)} seconds.")


if __name__ == '__main__':
    LoggerSetup(debug_enabled=debug)
    Updater("1.3.3")
    file_handler = logging.FileHandler(f'{datetime.now().strftime("%d-%m-%Y")}-discord.log')
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    bot.run(token, log_handler=file_handler, log_formatter=formatter)
