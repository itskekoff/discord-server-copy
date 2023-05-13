# -*- encoding: utf-8 -*-

import asyncio
import datetime
import json
import os
import sys
import typing
import urllib.request
import configparser

import discord
from discord.ext import commands


def file_exists(file_path: str):
    # check if file exists
    return os.path.exists(file_path)


class Configuration:

    def __init__(self, config_file_path) -> None:
        self.config_file_path = config_file_path
        self.config = {}
        if file_exists(config_file_path):
            with open(self.config_file_path, "r") as config_file_object:
                self.config = json.load(config_file_object)
                config_file_object.close()

    def read(self, key: typing.Any):
        return self.config[key]

    def write_kv(self, key: typing.Any, value: typing.Any):
        self.config[key] = value
        return self

    def write_dict(self, to_write: dict):
        self.config = self.config | to_write
        return self

    def flush(self):
        with open(self.config_file_path, "w") as config_file_object:
            config_file_object.write(json.dumps(self.config, indent=2, ensure_ascii=False))
            config_file_object.close()
        return self


config_path = "config.json"
data: Configuration = Configuration(config_path)
default_config: dict = {
    "token": "Your discord account token",
    "prefix": "cp!",
    "clone_settings": {
        "name_syntax": "%original-copy",
        "clone_delay": 0.85,
        "icon": True,
        "roles": True,
        "channels": True,
        "permissions": True,
        "emoji": True,
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
if not file_exists(config_path):
    data.write_dict(default_config).flush()
    print("* Configuration doesn't found. Re-created it.")
    sys.exit(0)

# loading parameters
register_on_message = False
cloner_instances = []

token: str = data.read("token")
prefix: str = data.read("prefix")

clone_settings: dict = data.read("clone_settings")

name_syntax: str = clone_settings["name_syntax"]
clone_delay: float = clone_settings["clone_delay"]
clone_icon: bool = clone_settings["icon"]  # icon also enables banner clone
clone_roles: bool = clone_settings["roles"]
clone_channels: bool = clone_settings["channels"]
clone_permissions: bool = clone_settings["permissions"]
clone_emojis: bool = clone_settings["emoji"]

messages_settings: dict = data.read("clone_messages")
clone_messages: bool = messages_settings["enabled"]
webhooks_clear: bool = messages_settings["webhooks_clear"]
messages_limit: int = messages_settings["limit"]
messages_delay: float = messages_settings["delay"]

live_settings: dict = data.read("live_update")
live_update: bool = live_settings["enabled"]
live_delay: float = live_settings["message_delay"]

if clone_channels and not clone_roles and clone_permissions:
    clone_roles = True  # we can't clone permissions if roles is not cloned
    data.write_kv(key="roles", value=True).flush()

if live_update and not clone_channels:
    print("* Live update disabled because clone channels is disabled.")
    live_update = False


class Updater:
    def __init__(self, version: str):
        def check():
            resp = urllib.request.urlopen(
                url="https://raw.githubusercontent.com/itskekoff/discord-server-copy/main/main.py").read()
            target_version = resp[resp.find(b'Updater('):]
            if version.encode("utf-8") in target_version:
                print("* Updates doesn't found.")
            else:
                print("* Update available.")

        check()


class ServerCopy:
    def __init__(self, from_guild: discord.Guild,
                 to_guild: discord.Guild, delay: float = 1,
                 webhook_delay: float = 0.65, debug: bool = True):
        self.guild = from_guild
        self.new_guild = to_guild
        self.delay = delay
        self.webhook_delay = webhook_delay
        self.debug = debug

        self.processing_messages = False
        self.messages_to_send: list[discord.Message] = []
        # creating flat mappings
        # webhooks: {webhook: {original, new, url}}
        self.mappings = {"roles": {}, "categories": {},
                         "webhooks": {}, "channels": {},
                         "messages": {}}

    @staticmethod
    def get_key(value: typing.Any, my_dict: dict) -> typing.Any:
        try:
            return list(my_dict.keys())[list(my_dict.values()).index(value)]
        except ValueError:
            return None

    async def clear_server(self):
        print("* Preparing guild to process...")
        # clearing server using .fetch_channels()
        for channel in await self.new_guild.fetch_channels():
            await channel.delete()

    async def clone_icon(self):
        print("* Processing icon clone")
        if self.guild.icon is not None:
            # copying icon (can doesn't copy transparent color)
            await self.new_guild.edit(icon=await self.guild.icon_url.read())
            if self.guild.banner is not None:
                await self.new_guild.edit(banner=await self.guild.banner_url.read())
            await asyncio.sleep(self.delay)

    async def clone_roles(self, perms: bool = True):
        print("* Processing role clone")
        # creat list of roles to create
        roles_create = []
        role: discord.Role
        for role in self.guild.roles:
            if role.name != "@everyone":
                # doesn't append role @everyone because it already exists in any guild
                roles_create.append(role)
            else:
                # add role id to mappings for permission overwrites
                self.mappings["roles"][role] = discord.utils.get(self.new_guild.roles, name="@everyone")
        for role in reversed(roles_create):
            # create role, append to mappings [role = new role]
            new_role = await self.new_guild.create_role(name=role.name, colour=role.colour,
                                                        hoist=role.hoist, mentionable=role.mentionable)
            if perms:
                await new_role.edit(permissions=role.permissions)
            self.mappings["roles"][role] = new_role
            if self.debug:
                print("* " + str(new_role.id) + " | " + new_role.name)
            await asyncio.sleep(self.delay)

    async def clone_categories(self, perms: bool = True):
        print("* Processing categories clone")
        for category in self.guild.categories:
            # process overwrites to category
            overwrites: dict = {}
            if perms:
                for role, permissions in category.overwrites.items():
                    if isinstance(role, discord.Member):
                        continue  # we can't add permission overwrites to members that doesn't joined guild
                    # adding permission overwrites from new role in mappings by original role
                    overwrites[self.mappings["roles"][role]] = permissions
            # creating category, adding to categories mappings [category = new category]
            new_category = await self.new_guild.create_category(name=category.name, position=category.position)
            if overwrites:
                await new_category.edit(overwrites=overwrites)
            self.mappings["categories"][category] = new_category
            if self.debug:
                print("* " + str(new_category.id) + " | " + new_category.name)
            await asyncio.sleep(self.delay)

    async def clone_channels(self, perms: bool = True):
        print("* Processing channels clone")
        for channel in self.guild.channels:
            # getting overwrites for channel
            overwrites: dict = {}
            if perms:
                for role, permissions in channel.overwrites.items():
                    if isinstance(role, discord.Member):
                        continue  # we can't add permission overwrites to members that doesn't joined guild
                    overwrites[self.mappings["roles"][role]] = permissions
            if isinstance(channel, discord.TextChannel):
                # if text channel, create text channel
                new_channel = await self.new_guild.create_text_channel(name=channel.name, position=channel.position,
                                                                       topic=channel.topic,
                                                                       slowmode_delay=channel.slowmode_delay,
                                                                       nsfw=channel.nsfw)
                # add channel to mappings for webhook message copier
                self.mappings["channels"][channel] = new_channel
                if overwrites:
                    await new_channel.edit(overwrites=overwrites)
                if self.debug:
                    print("* " + str(channel.category_id) + " | " + new_channel.name)
                if channel.category is not None:
                    # if channel category is not none, edit new channel category.
                    await new_channel.edit(category=self.mappings["categories"][channel.category])

            elif isinstance(channel, discord.VoiceChannel):
                # if voice channel, create voice channel
                bitrate = channel.bitrate if channel.bitrate <= 96000 else None
                new_channel = await self.new_guild.create_voice_channel(name=channel.name, position=channel.position,
                                                                        bitrate=bitrate, user_limit=channel.user_limit)
                if overwrites:
                    await new_channel.edit(overwrites=overwrites)
                if self.debug:
                    print("* " + str(channel.category_id) + " | " + new_channel.name)
                if channel.category is not None:
                    # if channel category is not none, edit new channel category.
                    await new_channel.edit(category=self.mappings["categories"][channel.category])
            elif isinstance(channel, discord.StageChannel):
                # if stage channel, create stage channel
                new_channel = await self.new_guild.create_stage_channel(name=channel.name, topic=channel.topic,
                                                                        position=channel.position)
                if self.debug:
                    print("* " + str(new_channel.id) + " | " + new_channel.name)
                if channel.category is not None:
                    # if channel category is not none, edit new channel category.
                    await new_channel.edit(category=self.mappings["categories"][channel.category])
            await asyncio.sleep(self.delay)

    async def clone_emojis(self):
        print("* Processing emoji clone")
        for emoji in self.guild.emojis:
            if self.debug:
                print("* " + str(emoji.id) + " | " + emoji.name)
            # cloning emoji using same name and url
            await self.new_guild.create_custom_emoji(name=emoji.name, image=await emoji.url.read())
            await asyncio.sleep(self.delay)

    async def send_webhook(self, webhook: discord.Webhook, message: discord.Message,
                           delay: float = 0.85):
        author: discord.User = message.author
        files = []
        if message.attachments is not None:
            for attachment in message.attachments:
                files.append(await attachment.to_file())
        now = datetime.datetime.now()
        current_time = now.strftime('%d/%m/%Y %H:%M')
        name: str = f"{author.name}#{author.discriminator} at {current_time}"
        try:
            await webhook.send(content=message.content, avatar_url=author.avatar_url,
                               username=name, embeds=message.embeds,
                               files=files)
        except discord.errors.HTTPException:
            if self.debug:
                print("* Can't send, skipping message in #" + webhook.channel.name)
        await asyncio.sleep(delay)

    async def clone_messages(self, limit: int = 512, clear: bool = True):
        print("* Processing message clone with limit for channel: " + str(limit))
        self.processing_messages: bool = True
        for channel in self.mappings["channels"].values():
            webhook: discord.Webhook = await channel.create_webhook(name="billy")
            original_channel: discord.TextChannel = self.get_key(channel, self.mappings["channels"])
            if self.debug:
                print("* Created webhook in #" + channel.name)
            self.mappings["webhooks"][webhook] = {original_channel: channel}
            # fill with messages
            try:
                for message in reversed(await original_channel.history(limit=limit).flatten()):
                    self.mappings["messages"][message] = original_channel
                    await self.send_webhook(webhook, message, self.webhook_delay)
            except discord.errors.Forbidden:
                if self.debug:
                    print("* Missing access for channel: #" + original_channel.name)
            if clear:
                # delete webhook
                if self.debug:
                    print("* Deleted webhook in #" + channel.name)
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
                        # create webhook and append to mappings
                        webhook = await new_channel.create_webhook(name="billy")
                        if self.debug:
                            print("* Created webhook in #" + new_channel.name)
                        self.mappings["webhooks"][webhook] = {message.channel: new_channel}
                    await self.send_webhook(webhook, message, live_delay)
                except KeyError:
                    pass


bot = commands.Bot(command_prefix=prefix, case_insensitive=True,
                   self_bot=True)


@bot.event
async def on_connect():
    print("* Logged on as {0.user}".format(bot))


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
    guild: discord.Guild = bot.get_guild(id=server_id) if server_id else ctx.message.guild
    if guild is None and server_id is None:
        return

    print("* Creating server... | " + guild.name)
    new_guild: discord.Guild = await bot.create_guild(name=name_syntax.replace("%original", guild.name))
    cloner: ServerCopy = ServerCopy(from_guild=guild, to_guild=new_guild,
                                    delay=clone_delay, webhook_delay=messages_delay)
    cloner_instances.append(cloner)
    print("* Processing modules")
    await cloner.clear_server()
    if clone_icon:
        await cloner.clone_icon()
    if clone_roles:
        await cloner.clone_roles(perms=clone_permissions)
    if clone_channels:
        await cloner.clone_categories(perms=clone_permissions)
        await cloner.clone_channels(perms=clone_permissions)
    if clone_emojis:
        await cloner.clone_emojis()
    if clone_messages:
        await cloner.clone_messages(limit=messages_limit, clear=webhooks_clear)
    if live_update:
        register_on_message = True
    print("* Done")


Updater("1.2.8")
bot.run(token)
