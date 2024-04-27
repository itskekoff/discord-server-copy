import asyncio
import io
import typing

from collections import deque
from collections.abc import Sequence

import discord
from discord import CategoryChannel
from discord.abc import GuildChannel

import main
from modules.logger import Logger

from PIL import Image, ImageSequence

logger = Logger()


class ServerCopy:
    def __init__(
            self,
            from_guild: discord.Guild,
            to_guild: discord.Guild | None,
            delay: float = 1,
            webhook_delay: float = 0.65,
            debug_enabled: bool = True,
            live_update_toggled: bool = False,
            clone_messages_toggled: bool = False,
            oldest_first: bool = True,
    ):
        self.guild = from_guild
        self.new_guild = to_guild
        self.delay = delay
        self.webhook_delay = webhook_delay
        self.debug = debug_enabled

        self.clone_oldest_first = oldest_first
        self.clone_messages_toggled = clone_messages_toggled
        self.live_update = live_update_toggled

        self.enabled_community = False
        self.processing_messages = False

        self.logger = Logger(debug_enabled=self.debug)
        self.logger.bind(server=self.guild.name, length=8)

        self.message_queue = deque()

        self.mappings = {
            "roles": {},
            "categories": {},
            "webhooks": {},
            "channels": {},
            "emojis": {},
            "processed_channels": {},
            "fetched_data": {"roles": [], "channels": Sequence[GuildChannel], "emojis": [], "stickers": []},
        }

    @staticmethod
    def get_key(value: typing.Any, my_dict: dict) -> typing.Any:
        try:
            return list(my_dict.keys())[list(my_dict.values()).index(value)]
        except ValueError:
            return None

    @staticmethod
    def truncate_string(string: str, length: int) -> str:
        string = string.replace("\n", " ")
        if len(string) > length:
            return string[:length] + "..."
        else:
            return string

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
            first_frame.save(byte_arr, format="PNG")
            return byte_arr.getvalue()
        else:
            return image_bytes

    def find_webhook(self, channel_obj: GuildChannel) -> discord.Webhook | None:
        for webhook, channel_to_webhook_mapping in self.mappings["webhooks"].items():
            for channel_obj, matched_channel in channel_to_webhook_mapping.items():
                if channel_obj == channel_obj:
                    return webhook
        return None

    def create_channel_log(self, channel_type: str, channel_name: str, channel_id: int):
        if self.debug:
            self.logger.debug(
                f"Created {channel_type} channel #{channel_name} | {str(channel_id)}"
            )

    def create_object_log(self, object_type: str, object_name: str, object_id: int):
        if self.debug:
            self.logger.debug(
                f"Created {object_type}: {object_name} | {str(object_id)}"
            )

    def create_webhook_log(self, channel_name: str, deleted: bool = False):
        if self.debug:
            if deleted:
                self.logger.debug(f"Deleted webhook in #{channel_name}")
                return
            self.logger.debug(f"Created webhook in #{channel_name}")

    async def populate_queue(self, limit: int = 512):
        for channel in self.mappings["channels"].values():
            original_channel: discord.TextChannel = self.get_key(channel, self.mappings["channels"])
            async for message in original_channel.history(limit=limit, oldest_first=self.clone_oldest_first):
                self.message_queue.append((channel, message))

    async def prepare_server(self) -> None:
        methods = [
            self.new_guild.fetch_roles,
            self.new_guild.fetch_channels,
            self.new_guild.fetch_emojis,
            self.new_guild.fetch_stickers,
        ]

        for method in methods:
            method_name = method.__name__.split("_")[-1]
            if self.debug:
                self.logger.debug(f"Processing cleaning method: {method_name}...")
            for item in await method():
                try:
                    await item.delete()
                except discord.HTTPException:
                    pass
                await asyncio.sleep(self.delay)

        await self.new_guild.edit(icon=None, banner=None, description=None)

        if "COMMUNITY" in self.guild.features:
            self.enabled_community = True
            self.logger.warning(
                "Community mode is toggled. Will be set up after channel processing (if enabled)."
            )

    async def fetch_required_data(self) -> None:
        self.logger.info("Fetching all required data (this can take a few minutes)")

        entities = ['roles', 'channels', 'emojis', 'stickers']
        fetch_methods = {
            'roles': self.guild.fetch_roles,
            'channels': self.guild.fetch_channels,
            'emojis': self.guild.fetch_emojis,
            'stickers': self.guild.fetch_stickers
        }

        for entity in entities:
            self.mappings["fetched_data"][entity] = await fetch_methods[entity]() if not getattr(self.guild,
                                                                                                 entity) else getattr(
                self.guild, entity)

    async def clone_icon(self) -> None:
        if self.guild.icon:
            icon_bytes = await self.get_first_frame(self.guild.icon)
            await self.new_guild.edit(icon=icon_bytes)
        await asyncio.sleep(self.delay)

    async def clone_banner(self) -> None:
        if self.guild.banner and ("ANIMATED_BANNER" or "BANNER") in self.guild.features:
            if (
                    self.guild.banner.is_animated()
                    and "ANIMATED_BANNER" in self.guild.features
            ):
                banner_bytes = await self.guild.banner.read()
            else:
                banner_bytes = await self.get_first_frame(self.guild.banner)
            await self.new_guild.edit(banner=banner_bytes)
            await asyncio.sleep(self.delay)

    async def clone_roles(self):
        roles_create = []
        role: discord.Role
        for role in self.mappings["fetched_data"]["roles"]:
            if role.name != "@everyone":
                roles_create.append(role)
            else:
                self.mappings["roles"][role] = discord.utils.get(
                    self.new_guild.roles, name="@everyone"
                )
        for role in reversed(roles_create):
            new_role = await self.new_guild.create_role(
                name=role.name,
                colour=role.colour,
                hoist=role.hoist,
                mentionable=role.mentionable,
                permissions=role.permissions,
            )
            self.mappings["roles"][role] = new_role
            self.create_object_log(
                object_type="role", object_name=new_role.name, object_id=new_role.id
            )
            await asyncio.sleep(self.delay)

    async def clone_categories(self, perms: bool = True) -> None:
        categories = [
            channel for channel in self.mappings["fetched_data"]["channels"]
            if isinstance(channel, CategoryChannel)
        ]

        for category in categories:
            overwrites: dict = {}
            if perms:
                for role, permissions in category.overwrites.items():
                    if isinstance(role, discord.Role):
                        overwrites[self.mappings["roles"][role]] = permissions
            new_category = await self.new_guild.create_category(
                name=category.name, position=category.position, overwrites=overwrites
            )
            self.mappings["categories"][category.id] = new_category
            self.create_object_log(
                object_type="category",
                object_name=new_category.name,
                object_id=new_category.id,
            )
            await asyncio.sleep(self.delay)

    async def clone_channels(self, perms: bool = True) -> None:
        for channel in self.mappings["fetched_data"]["channels"]:
            try:
                channel = await self.guild.fetch_channel(channel.id)
            except discord.Forbidden:
                logger.debug(f"Can't fetch channel {channel.name} | {channel.id}")
                continue

            category = None
            if channel.category_id is not None:
                category = self.mappings["categories"][channel.category_id]

            overwrites: dict = {}
            if perms:
                for role, permissions in channel.overwrites.items():
                    if isinstance(role, discord.Role):
                        overwrites[self.mappings["roles"][role]] = permissions
            if self.debug and overwrites:
                self.logger.debug(f"Got overwrites mapping for channel #{channel.name}")
            if isinstance(channel, discord.TextChannel):
                new_channel = await self.new_guild.create_text_channel(
                    name=channel.name,
                    position=channel.position,
                    topic=channel.topic,
                    slowmode_delay=channel.slowmode_delay,
                    nsfw=channel.nsfw,
                    category=category,
                    overwrites=overwrites,
                    default_auto_archive_duration=channel.default_auto_archive_duration,
                    default_thread_slowmode_delay=channel.default_thread_slowmode_delay,
                )
                self.mappings["channels"][channel] = new_channel
                self.create_channel_log(
                    channel_type="text",
                    channel_name=new_channel.name,
                    channel_id=new_channel.id,
                )
            elif isinstance(channel, discord.VoiceChannel):
                bitrate = self.get_bitrate(channel)
                new_channel = await self.new_guild.create_voice_channel(
                    name=channel.name,
                    position=channel.position,
                    bitrate=bitrate,
                    user_limit=channel.user_limit,
                    category=category,
                    overwrites=overwrites,
                )
                self.mappings["channels"][channel] = new_channel
                self.create_channel_log(
                    channel_type="voice",
                    channel_name=new_channel.name,
                    channel_id=new_channel.id,
                )
            await asyncio.sleep(self.delay)

    async def process_community(self) -> None:
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
                public_updates_channel=self.mappings["channels"][
                    self.guild.public_updates_channel
                ],
                explicit_content_filter=self.guild.explicit_content_filter,
                preferred_locale=self.guild.preferred_locale,
            )
            self.logger.info("Updated guild community settings")
            await asyncio.sleep(self.delay)

    async def add_community_channels(self, perms: bool = True) -> None:
        if self.enabled_community:
            all_channels = []
            for channel in self.mappings["fetched_data"]["channels"]:
                if isinstance(channel, (discord.ForumChannel, discord.StageChannel)):
                    all_channels.append(channel)
            for channel in all_channels:
                category = self.mappings["categories"][channel.category_id]
                overwrites: dict = {}
                if perms and channel.overwrites:
                    for role, permissions in channel.overwrites.items():
                        if isinstance(role, discord.Role):
                            overwrites[self.mappings["roles"][role]] = permissions
                if isinstance(channel, discord.ForumChannel):
                    tags: discord.abc.Sequence[discord.ForumTag] = (
                        channel.available_tags
                    )
                    for tag in tags:
                        if tag.emoji.id:
                            tag.emoji = self.mappings["emojis"].get(tag.emoji, None)

                    new_channel = await self.new_guild.create_forum_channel(
                        name=channel.name,
                        topic=channel.topic,
                        position=channel.position,
                        category=category,
                        slowmode_delay=channel.slowmode_delay,
                        nsfw=channel.nsfw,
                        overwrites=overwrites,
                        default_layout=channel.default_layout,
                        default_auto_archive_duration=channel.default_auto_archive_duration,
                        default_thread_slowmode_delay=channel.default_thread_slowmode_delay,
                        available_tags=tags,
                    )
                    self.mappings["channels"][channel] = new_channel
                    self.create_channel_log(
                        channel_type="forum",
                        channel_name=new_channel.name,
                        channel_id=new_channel.id,
                    )
                if isinstance(channel, discord.StageChannel):
                    bitrate = self.get_bitrate(channel)
                    new_channel = await self.new_guild.create_stage_channel(
                        name=channel.name,
                        category=category,
                        position=channel.position,
                        bitrate=bitrate,
                        user_limit=channel.user_limit,
                        rtc_region=channel.rtc_region,
                        video_quality_mode=channel.video_quality_mode,
                        overwrites=overwrites,
                    )
                    self.mappings["channels"][channel] = new_channel
                    self.create_channel_log(
                        channel_type="stage",
                        channel_name=new_channel.name,
                        channel_id=new_channel.id,
                    )
                await asyncio.sleep(self.delay)

    async def clone_emojis(self) -> None:
        emoji_limit = min(self.new_guild.emoji_limit, self.new_guild.emoji_limit - 5)
        for emoji in self.mappings["fetched_data"]["emojis"][:emoji_limit]:
            if len(self.new_guild.emojis) >= emoji_limit:
                self.logger.warning("Emoji limit reached. Skipping...")
                break
            new_emoji = await self.new_guild.create_custom_emoji(
                name=emoji.name, image=await emoji.read()
            )
            self.mappings["emojis"][emoji] = new_emoji
            self.create_object_log(
                object_type="emoji", object_name=new_emoji.name, object_id=new_emoji.id
            )
            await asyncio.sleep(self.delay)

    async def clone_stickers(self) -> None:
        sticker_limit = self.new_guild.sticker_limit
        created_stickers = 0
        for sticker in self.mappings["fetched_data"]["stickers"]:
            if created_stickers < sticker_limit:
                try:
                    new_sticker = await self.new_guild.create_sticker(
                        name=sticker.name,
                        description=sticker.description,
                        emoji=sticker.emoji,
                        file=await sticker.to_file(),
                    )
                    created_stickers += 1
                    self.create_object_log(
                        object_type="sticker",
                        object_name=new_sticker.name,
                        object_id=new_sticker.id,
                    )
                except discord.NotFound:
                    self.logger.warning("Can't create sticker with id {}, url: {}".format(sticker.id, sticker.url))
                await asyncio.sleep(self.delay)
            else:
                break

    async def send_webhook(self,
                           webhook: discord.Webhook,
                           message: discord.Message,
                           delay: float = 0.85) -> None:
        author: discord.User = message.author
        files = []
        if message.attachments:
            for attachment in message.attachments:
                files.append(await attachment.to_file())
        creation_time = message.created_at.strftime("%d/%m/%Y %H:%M")
        name: str = f"{author.name}#{author.discriminator} at {creation_time}"
        content = message.content

        for mapping_type, mapping_dict in self.mappings.items():
            if mapping_type not in {"channels", "roles"}:
                continue

            for old, new in mapping_dict.items():
                if mapping_type == "channels" and isinstance(old, GuildChannel) and isinstance(new, GuildChannel):
                    old_ref = f"<#{old.id}>"
                    new_ref = f"<#{new.id}>"
                elif mapping_type == "roles" and isinstance(old, discord.Role) and isinstance(new, discord.Role):
                    old_ref = f"<@&{old.id}>"
                    new_ref = f"<@&{new.id}>"
                else:
                    continue

                content = content.replace(old_ref, new_ref)

        try:
            await webhook.send(
                content=content,
                avatar_url=author.display_avatar.url,
                username=name,
                embeds=message.embeds,
                files=files,
            )
            if self.debug:
                content = (
                    self.truncate_string(string=message.content, length=32)
                    if message.content
                    else ""
                )

                self.logger.debug(f"Cloned message from @{author.name}: {content}")
        except discord.errors.HTTPException:
            if self.debug:
                self.logger.debug("Can't send, skipping message in #{}".format(webhook.channel.name))
        await asyncio.sleep(delay)

    async def clone_messages(self, messages_limit: int = main.messages_limit,
                             clear_webhooks: bool = main.messages_webhook_clear) -> None:
        if not self.clone_messages_toggled:
            return

        self.processing_messages = True
        await self.populate_queue(messages_limit)

        if self.debug:
            self.logger.debug(f"Collected {len(self.message_queue)} messages")

        await self.clone_messages_from_queue(clear_webhooks=clear_webhooks)

    async def cleanup_after_cloning(self, clear: bool = False) -> None:
        self.message_queue.clear()

        if clear:
            for webhook in self.mappings["webhooks"].values():
                await webhook.delete()
                await asyncio.sleep(self.webhook_delay)
            self.mappings["webhooks"].clear()

            self.logger.debug(f"Successfully cleaned up")
        self.processing_messages = False

    async def clone_messages_from_queue(self, clear_webhooks: bool = main.messages_webhook_clear) -> None:
        channel_messages_map = self._split_messages_by_channel()
        tasks = []
        for channel, messages in channel_messages_map.items():
            tasks.append(asyncio.create_task(self._clone_messages_for_channel(channel, messages)))

        if tasks:
            await asyncio.gather(*tasks)

        await self.cleanup_after_cloning(clear=clear_webhooks)

    def _split_messages_by_channel(self) -> typing.Dict[discord.channel.TextChannel, typing.List[typing.Any]]:
        channel_messages_map = {}
        while self.message_queue:
            channel, message = self.message_queue.popleft()
            if channel not in channel_messages_map:
                channel_messages_map[channel] = []
            channel_messages_map[channel].append(message)
        return channel_messages_map

    async def _clone_messages_for_channel(self,
                                          channel: discord.channel.TextChannel,
                                          messages: typing.List[discord.Message]) -> None:
        webhook = self.find_webhook(channel)
        if not webhook:
            webhook = await channel.create_webhook(name="bot by itskekoff")
            await asyncio.sleep(self.webhook_delay)

            self.create_webhook_log(channel_name=channel.name)
            self.mappings["webhooks"][channel] = webhook

        for message in messages:
            await asyncio.sleep(self.webhook_delay)
            try:
                await self.send_webhook(webhook, message)
                self.mappings["processed_channels"][message.channel] = channel
            except discord.errors.Forbidden:
                if self.debug:
                    self.logger.debug(f"Missing access for channel: #{message.channel.name}")

    async def on_message(self, message: discord.Message):
        if message.guild and message.guild.id == self.guild.id:
            if self.processing_messages:
                return
            try:
                if self.live_update:
                    new_channel = self.mappings["channels"][message.channel]

                    webhook: discord.Webhook = self.find_webhook(new_channel)

                    if not webhook:
                        webhook: discord.Webhook = await new_channel.create_webhook(name="bot by itskekoff")
                        await asyncio.sleep(self.webhook_delay)

                        self.create_webhook_log(channel_name=new_channel.name)
                        self.mappings["webhooks"][webhook] = {message.channel: new_channel}
                    await self.send_webhook(webhook, message, self.webhook_delay)
            except KeyError:
                pass
