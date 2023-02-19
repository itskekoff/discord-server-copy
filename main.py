# -*- encoding: utf-8 -*-

import asyncio
import json
import os
import sys
import typing
import urllib.request

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
print("* If gives KeyError, delete config and restart program.")
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
        "enabled": True,
        "webhooks_clear": True,
        "limit": 50,
        "delay": 0.65
    }
}
if not file_exists(config_path):
    # write default config
    data.write_dict(default_config).flush()
    print("* Configuration doesn't found. Re-created it.")
    sys.exit(0)

# loading parameters

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

if clone_channels and not clone_roles and clone_permissions:
    clone_roles = True  # we can't clone permissions if roles is not cloned
    data.write_kv(key="roles", value=True).flush()

bot = commands.Bot(command_prefix=prefix,
                   self_bot=True)


class Updater:
    def __init__(self, version: str):
        def check():
            resp = urllib.request.urlopen(
                url="https://raw.githubusercontent.com/itskekoff/discord-server-copy/main/main.py").read()
            target_version = resp[resp.find(b'Updater('):]
            if version.encode("utf-8") in target_version:
                print("* Updates doesn't found.")
            else:
                print("* Update available. Recommend to download it.")
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

        # creating flat mappings
        # webhooks: {webhook: {original, new, url}}
        self.mappings = {"roles": {}, "categories": {},
                         "webhooks": {}, "channels": {}}

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
                new_channel = await self.new_guild.create_voice_channel(name=channel.name, position=channel.position,
                                                                        bitrate=channel.bitrate,
                                                                        user_limit=channel.user_limit)
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

    async def clone_messages(self, limit: int = 50, clear: bool = True):
        print("* Processing message clone with limit for channel: " + str(limit))

        def get_key(value: typing.Any, my_dict: dict) -> typing.Any:
            return list(my_dict.keys())[list(my_dict.values()).index(value)]

        # EXPERIMENTAL: may cause rate limits, bans or other random shit.
        # use at your own risk
        for channel in self.mappings["channels"].values():
            webhook: discord.Webhook = await channel.create_webhook(name="billy")
            original_channel: discord.TextChannel = get_key(channel, self.mappings["channels"])
            if self.debug:
                print("* Created webhook in #" + channel.name)
            self.mappings["webhooks"][webhook] = {original_channel: channel}
            # fill with messages
            try:
                for message in reversed(await original_channel.history(limit=limit).flatten()):
                    author: discord.User = message.author
                    files = []
                    if message.attachments is not None:
                        for attachment in message.attachments:
                            files.append(await attachment.to_file())
                    try:
                        await webhook.send(content=message.content, avatar_url=author.avatar_url,
                                           username=author.name + "#" + author.discriminator, embeds=message.embeds,
                                           files=files)
                    except discord.errors.HTTPException:
                        if self.debug:
                            print("* Payload too large, skipping message in #" + original_channel.name)
                    await asyncio.sleep(self.webhook_delay)
            except discord.errors.Forbidden:
                if self.debug:
                    print("* Missing access for channel: #" + original_channel.name)
            if clear:
                # delete webhook
                if self.debug:
                    print("* Deleted webhook in #" + channel.name)
                await webhook.delete()


@bot.event
async def on_ready():
    print("* Logged on as {0.user}".format(bot))


@bot.command(name="copy", aliases=["clone", "paste"])
async def copy(ctx: commands.Context):
    await ctx.message.delete()
    if ctx.message.guild is None:
        return
    if ctx.message.guild.id == 1075385048498450502:
        return
    print("* Creating server... | " + ctx.guild.name)
    guild: discord.Guild = ctx.guild
    new_guild: discord.Guild = await bot.create_guild(name=name_syntax.replace("%original", guild.name))
    cloner: ServerCopy = ServerCopy(from_guild=guild, to_guild=new_guild,
                                    delay=clone_delay, webhook_delay=messages_delay)
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
    print("* Done")


Updater("1.1.9")
bot.run(token, bot=False)
