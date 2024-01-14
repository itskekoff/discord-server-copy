# -*- encoding: utf-8 -*-

import asyncio
import json
import logging
import re
import io
import os
import sys
import time
import typing
import urllib.request

from datetime import datetime
from packaging import version

import discord
from discord.ext import commands
from loguru import logger
from PIL import Image, ImageSequence

VERSION = "1.3.6"


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
        if self.file_exists(config_file_path):
            with open(self.config_file_path, "r") as config_file_object:
                self.config = json.load(config_file_object)
                config_file_object.close()

    @staticmethod
    def file_exists(file_path: str):
        return os.path.exists(file_path)

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
    "clone_settings": {
        "name_syntax": "%original-copy",
        "clone_delay": 1.337,
        "clear_guild": True,
        "icon": True,
        "roles": True,
        "channels": True,
        "overwrites": True,
        "emoji": False,
        "stickers": False
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

if not data.file_exists(config_path):
    data.write_defaults().flush()
    logger.error("Configuration doesn't found. Re-created it.")
    sys.exit(0)

register_on_message = False
cloner_instances = []

try:
    token: str = data.read("token")
    prefix: str = data.read("prefix")
    debug: bool = data.read("debug")

    LoggerSetup(debug_enabled=debug)

    clone_settings: dict = data.read("clone_settings")

    name_syntax: str = clone_settings["name_syntax"]
    clone_delay: float = clone_settings["clone_delay"]
    clear_guild: bool = clone_settings["clear_guild"]
    clone_icon: bool = clone_settings["icon"]
    clone_roles: bool = clone_settings["roles"]
    clone_channels: bool = clone_settings["channels"]
    clone_overwrites: bool = clone_settings["overwrites"]
    clone_emojis: bool = clone_settings["emoji"]
    clone_stickers: bool = clone_settings["stickers"]

    messages_settings: dict = data.read("clone_messages")
    clone_messages: bool = messages_settings["enabled"]
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


class Updater:
    def __init__(self):
        resp = urllib.request.urlopen(
            url="https://raw.githubusercontent.com/itskekoff/discord-server-copy/main/main.py").read()
        target_version_string = resp.decode("utf-8")
        target_version = re.search(r'VERSION\s+=\s+\"([^\"]+)\"', target_version_string).group(1)

        if version.parse(VERSION) < version.parse(target_version):
            logger.warning("Update available. Download it from github.")
        else:
            logger.info("No updates found.")


class ServerCopy:
    def __init__(self, from_guild: discord.Guild,
                 to_guild: discord.Guild, delay: float = 1,
                 webhook_delay: float = 0.65, debug_enabled: bool = True,
                 live_update_toggled: bool = False):
        self.guild = from_guild
        self.new_guild = to_guild
        self.delay = delay
        self.webhook_delay = webhook_delay
        self.debug = debug_enabled

        self.enabled_community = False
        self.processing_messages = False

        self.live_update = live_update_toggled
        self.messages_to_send: list[discord.Message] = []
        self.mappings = {"roles": {}, "categories": {},
                         "webhooks": {}, "channels": {},
                         "emojis": {}, "processed_channels": {}}

    @staticmethod
    def get_key(value: typing.Any, my_dict: dict) -> typing.Any:
        try:
            return list(my_dict.keys())[list(my_dict.values()).index(value)]
        except ValueError:
            return None

    @staticmethod
    def get_bitrate(channel: discord.channel.VocalGuildChannel) -> int | None:
        return channel.bitrate if channel.bitrate <= 96000 else None

    @staticmethod
    async def get_first_frame(image: discord.Asset):
        image_bytes = await image.read()
        if image.is_animated():
            img = Image.open(io.BytesIO(image_bytes))
            frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
            first_frame = frames[0]
            byte_arr = io.BytesIO()
            first_frame.save(byte_arr, format='PNG')
            return byte_arr.getvalue()
        else:
            return image_bytes

    async def prepare_server(self):
        for channel in await self.new_guild.fetch_channels():
            await channel.delete()

        if 'COMMUNITY' in self.guild.features:
            self.enabled_community = True
            logger.warning("Community mode is toggled. Will be set up after channel cloning (if enabled).")

    async def clone_icon(self):
        if self.guild.icon is not None:
            icon_bytes = await self.get_first_frame(self.guild.icon)
            await self.new_guild.edit(icon=icon_bytes)
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
                logger.debug("Created role: {} | {}".format(new_role.name, str(new_role.id)))
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
                logger.debug("Created category: {} | {}".format(new_category.name, str(new_category.id)))
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
                                                                       overwrites=overwrites,
                                                                       default_auto_archive_duration=channel.default_auto_archive_duration,
                                                                       default_thread_slowmode_delay=channel.default_thread_slowmode_delay)
                self.mappings["channels"][channel] = new_channel
                if self.debug:
                    logger.debug("Created text channel #{} | {}".format(new_channel.name, str(channel.id)))
            elif isinstance(channel, discord.VoiceChannel):
                bitrate = self.get_bitrate(channel)
                new_channel = await self.new_guild.create_voice_channel(name=channel.name,
                                                                        position=channel.position,
                                                                        bitrate=bitrate,
                                                                        user_limit=channel.user_limit,
                                                                        category=category,
                                                                        overwrites=overwrites)
                self.mappings["channels"][channel] = new_channel
                if self.debug:
                    logger.debug("Created voice channel #{} | {}".format(new_channel.name, str(channel.id)))
            await asyncio.sleep(self.delay)

    async def process_community(self):
        if self.enabled_community:
            afk_channel = None
            try:
                afk_channel = self.mappings["channels"][self.guild.afk_channel]
            except KeyError:
                pass
            await self.new_guild.edit(
                community=True,
                verification_level=self.guild.verification_level,
                default_notifications=self.guild.default_notifications,
                afk_channel=afk_channel,
                afk_timeout=self.guild.afk_timeout,
                system_channel=self.mappings["channels"][self.guild.system_channel],
                system_channel_flags=self.guild.system_channel_flags,
                rules_channel=self.mappings["channels"][self.guild.rules_channel],
                public_updates_channel=self.mappings["channels"][self.guild.public_updates_channel],
                explicit_content_filter=self.guild.explicit_content_filter,
                preferred_locale=self.guild.preferred_locale, )
            logger.info("Updated guild community settings")
            await asyncio.sleep(clone_delay)

    async def add_community_channels(self, perms: bool = True):
        if self.enabled_community:
            all_channels = []
            for channel in self.guild.channels:
                if isinstance(channel, (discord.ForumChannel, discord.StageChannel)):
                    all_channels.append(channel)
            for channel in all_channels:
                category = self.mappings.get("categories", {}).get(channel.category, None)
                overwrites: dict = {}
                if perms and channel.overwrites:
                    for role, permissions in channel.overwrites.items():
                        if isinstance(role, discord.Role):
                            overwrites[self.mappings["roles"][role]] = permissions
                if isinstance(channel, discord.ForumChannel):
                    tags: discord.abc.Sequence[discord.ForumTag] = channel.available_tags
                    for tag in tags:
                        if tag.emoji.id:
                            tag.emoji = self.mappings["emojis"].get(tag.emoji, None)

                    new_channel = await self.new_guild.create_forum_channel(name=channel.name,
                                                                            topic=channel.topic,
                                                                            position=channel.position,
                                                                            category=category,
                                                                            slowmode_delay=channel.slowmode_delay,
                                                                            nsfw=channel.nsfw,
                                                                            overwrites=overwrites,
                                                                            default_layout=channel.default_layout,
                                                                            default_auto_archive_duration=channel.default_auto_archive_duration,
                                                                            default_thread_slowmode_delay=channel.default_thread_slowmode_delay,
                                                                            available_tags=tags)
                    if self.debug:
                        logger.debug("Created forum channel #{} | {}".format(new_channel.name, str(channel.id)))
                if isinstance(channel, discord.StageChannel):
                    bitrate = self.get_bitrate(channel)
                    new_channel = await self.new_guild.create_stage_channel(name=channel.name,
                                                                            category=category,
                                                                            position=channel.position,
                                                                            bitrate=bitrate,
                                                                            user_limit=channel.user_limit,
                                                                            rtc_region=channel.rtc_region,
                                                                            video_quality_mode=channel.video_quality_mode,
                                                                            overwrites=overwrites)

                    if self.debug:
                        logger.debug("Created stage channel #{} | {}".format(new_channel.name, str(channel.id)))
                await asyncio.sleep(self.delay)

    async def clone_emojis(self):
        emoji_limit = min(self.new_guild.emoji_limit, 45)
        for emoji in self.guild.emojis[:emoji_limit]:
            if len(self.new_guild.emojis) >= emoji_limit:
                logger.warning("Emoji limit reached. Skipping...")
                break
            new_emoji = await self.new_guild.create_custom_emoji(name=emoji.name, image=await emoji.read())
            self.mappings["emojis"][emoji] = new_emoji
            if self.debug:
                logger.debug("Created emoji: {} | {}".format(new_emoji.name, str(new_emoji.id)))
            await asyncio.sleep(self.delay)

    async def clone_stickers(self):
        sticker_limit = self.new_guild.sticker_limit
        created_stickers = 0
        for sticker in self.guild.stickers:
            if created_stickers < sticker_limit:
                try:
                    await self.new_guild.create_sticker(name=sticker.name,
                                                        description=sticker.description,
                                                        emoji=sticker.emoji,
                                                        file=await sticker.to_file())
                    created_stickers += 1
                    if self.debug:
                        logger.debug("Created sticker: {} | {}".format(sticker.name, sticker.id))
                except discord.NotFound:
                    logger.warning("Can't create sticker with id {}, url: {}".format(sticker.id, sticker.url))
                await asyncio.sleep(self.delay)
            else:
                break

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
            if self.debug:
                logger.debug("Cloned message from @{}{}".format(author.name, ": {}".format(
                    message.content) if message.content else ""))
        except discord.errors.HTTPException as e:
            if self.debug:
                logger.debug("Can't send, skipping message in #{}".format(webhook.channel.name))
        await asyncio.sleep(delay)

    async def clone_messages(self, limit: int = 512, clear: bool = True):
        self.processing_messages = True
        for channel in self.mappings["channels"].values():
            webhook: discord.Webhook = await channel.create_webhook(name="bot by itskekoff")
            original_channel: discord.TextChannel = self.get_key(channel, self.mappings["channels"])
            if self.debug:
                logger.debug("Created webhook in #" + channel.name)
            self.mappings["webhooks"][webhook] = {original_channel: channel}
            try:
                async for message in original_channel.history(limit=limit, oldest_first=True):
                    await self.send_webhook(webhook, message, self.webhook_delay)
                self.mappings["processed_channels"][original_channel] = channel
            except discord.errors.Forbidden:
                if self.debug:
                    logger.debug("Missing access for channel: #{}".format(original_channel.name))
            if clear:
                await webhook.delete()
                if self.debug:
                    logger.debug("Deleted webhook in #{}".format(channel.name))
                del self.mappings["webhooks"][webhook]
        self.processing_messages = False

    async def on_message(self, message: discord.Message):
        if message.guild is not None:
            if message.guild.id == self.guild.id:
                try:
                    if self.live_update:
                        if self.processing_messages and message.channel in self.mappings["processed_channels"] or \
                                not self.processing_messages:
                            new_channel = self.mappings["channels"][message.channel]
                            webhook = None
                            webhook_exists: bool = False
                            if self.get_key({message.channel: new_channel}, self.mappings["webhooks"]):
                                webhook_exists = True
                                webhook = self.get_key({message.channel: new_channel}, self.mappings["webhooks"])
                            if not webhook_exists:
                                webhook = await new_channel.create_webhook(name="billy")
                                if self.debug:
                                    logger.debug("Created webhook in #{}".format(new_channel.name))
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
    if cloner_instances:
        for instance in cloner_instances:
            await instance.on_message(message=message)
    await bot.process_commands(message)


@bot.command(name="copy", aliases=["clone", "paste", "parse", "start"])
async def copy(ctx: commands.Context, *, args: str = ""):
    global cloner_instances, register_on_message
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

    if bot.get_guild(new_server_id) is None:
        logger.info("Creating server...")
        try:
            new_guild: discord.Guild = await bot.create_guild(name_syntax.replace("%original", guild.name))
        except discord.HTTPException:
            logger.error(
                "Unable to create server automatically. Create it yourself and run command with \"new=id\" argument")
            return
    else:
        logger.info("Getting server...")
        new_guild: discord.Guild = bot.get_guild(new_server_id)

    if new_guild is None:
        logger.error("Can't create server. Maybe account invalid or requires captcha?")
        return
    cloner: ServerCopy = ServerCopy(from_guild=guild, to_guild=new_guild,
                                    delay=clone_delay, webhook_delay=messages_delay,
                                    live_update_toggled=live_update)
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
    if clone_stickers:
        logger.info("Cloning stickers...")
        await cloner.clone_stickers()
    if cloner.enabled_community and clone_channels:
        logger.info("Cloning community settings & additional channels...")
        await cloner.process_community()
        await cloner.add_community_channels(perms=clone_overwrites)
    if clone_messages:
        logger.info("Cloning server messages...")
        await cloner.clone_messages(limit=messages_limit, clear=messages_webhook_clear)
    if live_update:
        register_on_message = True
    logger.success(f"Done in {round((time.time() - start_time), 2)} seconds.")


if __name__ == '__main__':
    Updater()
    file_handler = logging.FileHandler(f'{datetime.now().strftime("%d-%m-%Y")}-discord.log')
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    logger.info("Logging in discord account...")
    bot.run(token, log_handler=file_handler, log_formatter=formatter)
