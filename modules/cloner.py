import asyncio
import datetime

from collections import deque
from collections.abc import Sequence

import discord
from discord import CategoryChannel
from discord.abc import GuildChannel

import main
from modules.logger import Logger
from modules.utilities import get_first_frame, get_bitrate, truncate_string, split_messages_by_channel, format_time

logger = Logger()


class ServerCopy:
    def __init__(self, bot: discord.Client, from_guild: discord.Guild, to_guild: discord.Guild | None,
                 delay: float = 1, webhook_delay: float = 0.65, debug_enabled: bool = True,
                 live_update_toggled: bool = False, process_new_messages: bool = True,
                 clone_messages_toggled: bool = False, oldest_first: bool = True,
                 disable_fetch_channels: bool = False):
        """
        ServerCopy facilitates cloning of server components from a source guild to a target guild.

        Args:
            bot (discord.Client): Discord bot instance
            from_guild (discord.Guild): The source guild to clone from.
            to_guild (discord.Guild | None): The target guild to clone to.
            delay (float): A delay between operations to prevent rate-limiting.
            webhook_delay (float): A specific delay for operations involving webhooks.
            debug_enabled (bool): Whether to enable debug logging.
            live_update_toggled (bool): If true, enables live update functionality.
            process_new_messages (bool): If true, enables processing new messages when cloning other messages
            clone_messages_toggled (bool): If true, enables cloning of messages from the source guild.
            oldest_first (bool): Determines the order in which messages are cloned.
            disable_fetch_channels (bool): If true, disables guild.fetch_channel() and uses cached one
        """
        self.bot = bot

        self.guild = from_guild
        self.new_guild = to_guild

        self.delay = delay
        self.webhook_delay = webhook_delay

        self.debug = debug_enabled

        self.clone_oldest_first = oldest_first
        self.clone_messages_toggled = clone_messages_toggled
        self.live_update = live_update_toggled
        self.new_messages_enabled = process_new_messages
        self.disable_fetch_channels = disable_fetch_channels

        self.enabled_community = False
        self.processing_messages = False

        self.logger = Logger(debug_enabled=self.debug)
        self.logger.bind(source=self.guild.name)

        self.message_queue = deque()
        self.new_messages_queue = deque()

        self.mappings = {
            "roles": {},  # old_role_id: new_role
            "categories": {},  # old_category_id: new_category
            "webhooks": {},  # new_channel_id: created_webhook
            "channels": {},  # old_channel_id: created_channel
            "emojis": {},  # old_emoji_id: new_emoji
            "fetched_data": {"roles": [], "channels": Sequence[GuildChannel], "emojis": [], "stickers": []},
        }

        self.processed_channels = []

    def find_webhook(self, channel_id: int) -> discord.Webhook | None:
        """Find a webhook in the mappings by channel ID."""
        return self.mappings["webhooks"].get(channel_id)

    def create_channel_log(self, channel_type: str, channel_name: str, channel_id: int):
        """Log the creation of a channel."""
        if self.debug:
            self.logger.debug(f"Created {channel_type} channel #{channel_name} | {channel_id}")

    def create_object_log(self, object_type: str, object_name: str, object_id: int):
        """Log the creation of a server object like roles or emojis."""
        if self.debug:
            self.logger.debug(f"Created {object_type}: {object_name} | {object_id}")

    def create_webhook_log(self, channel_name: str, deleted: bool = False):
        """Log the creation or deletion of a webhook."""
        action = "Deleted" if deleted else "Created"
        if self.debug:
            self.logger.debug(f"{action} webhook in #{channel_name}")

    async def populate_queue(self, limit: int = 512):
        """Populate the message queue with messages from the source guild's channels."""
        for channel_id, new_channel in self.mappings["channels"].items():
            try:
                original_channel: discord.TextChannel = await self.guild.fetch_channel(channel_id)
                async for message in original_channel.history(limit=limit, oldest_first=self.clone_oldest_first):
                    self.message_queue.append((new_channel, message))
            except discord.Forbidden:
                logger.debug(f"Can't fetch channel message history (no permissions): {channel_id}")
                continue

    async def prepare_server(self) -> None:
        """Prepares the target server by cleaning up existing roles, channels, emojis, and stickers."""
        methods = [
            self.new_guild.fetch_roles,
            self.new_guild.fetch_channels,
            self.new_guild.fetch_emojis,
            self.new_guild.fetch_stickers,
        ]

        method_names = ['roles', 'channels', 'emojis', 'stickers']

        if "COMMUNITY" in self.guild.features:
            self.enabled_community = True
            self.logger.warning("Community mode is toggled. Will be set up after channel processing (if enabled).")

        for method_name, method in zip(method_names, methods):
            if self.debug:
                self.logger.debug(f"Processing cleaning method: {method_name}...")
            await self.cleanup_items(await method())

    async def cleanup_items(self, items):
        """Helper method to clean up items like roles, channels, emojis, and stickers."""
        for item in items:
            try:
                await item.delete()
            except discord.HTTPException:
                pass
            await asyncio.sleep(self.delay)

        await self.new_guild.edit(icon=None, banner=None, description=None)

    async def fetch_required_data(self) -> None:
        """
        Fetches all roles, channels, emojis, and stickers from the source guild and stores them in the mappings for later use.
        """
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
        """
        If present, clones the icon from the source guild to the new guild.
        """
        if self.guild.icon:
            icon_bytes = await get_first_frame(self.guild.icon)
            await self.new_guild.edit(icon=icon_bytes)
        await asyncio.sleep(self.delay)

    async def clone_banner(self) -> None:
        """
        If present and the guild has the required features, clones the banner from the source guild to the new guild.
        """
        if self.guild.banner and ("ANIMATED_BANNER" or "BANNER") in self.guild.features:
            if (self.guild.banner.is_animated()
                    and "ANIMATED_BANNER" in self.guild.features):
                banner_bytes = await self.guild.banner.read()
            else:
                banner_bytes = await get_first_frame(self.guild.banner)
            await self.new_guild.edit(banner=banner_bytes)
            await asyncio.sleep(self.delay)

    async def clone_roles(self):
        """
        Clones all roles from the source guild to the new guild, except the implicitly created "@everyone" role.
        """
        roles_create = []
        role: discord.Role
        for role in self.mappings["fetched_data"]["roles"]:
            roles_create.append(role)
            if role.name == "@everyone":
                self.mappings["roles"][role.id] = discord.utils.get(self.new_guild.roles, name="@everyone")

        for role in reversed(roles_create):
            if role.name == "@everyone":
                everyone_role = discord.utils.get(self.new_guild.roles, name="@everyone")
                await everyone_role.edit(name=role.name, colour=role.colour, hoist=role.hoist,
                                         mentionable=role.mentionable, permissions=role.permissions)
                await asyncio.sleep(self.delay)
                continue

            new_role = await self.new_guild.create_role(name=role.name, colour=role.colour, hoist=role.hoist,
                                                        mentionable=role.mentionable, permissions=role.permissions)
            self.mappings["roles"][role.id] = new_role
            self.create_object_log(object_type="role", object_name=new_role.name, object_id=new_role.id)
            await asyncio.sleep(self.delay)

    async def clone_categories(self, perms: bool = True) -> None:
        """
        Clones all category channels from the source guild to the new guild with appropriate permissions and settings.

        Args:
            perms (bool): If set to True, will clone category-specific role permissions. Defaults to True.
        """
        categories = [
            channel for channel in self.mappings["fetched_data"]["channels"]
            if isinstance(channel, CategoryChannel)
        ]

        for category in categories:
            overwrites: dict = {}
            if perms:
                for role, permissions in category.overwrites.items():
                    if isinstance(role, discord.Role):
                        overwrites[self.mappings["roles"][role.id]] = permissions
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
        """
        Clones all channels from the source guild to the new guild, respecting the category hierarchy and permissions.

        Args:
            perms (bool): If set to True, will clone channel-specific role permissions. Defaults to True.
        """
        for channel in self.mappings["fetched_data"]["channels"]:
            if not self.disable_fetch_channels:
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
                        overwrites[self.mappings["roles"][role.id]] = permissions
            if self.debug and overwrites:
                self.logger.debug(f"Got overwrites mapping for channel #{channel.name}")
            if isinstance(channel, discord.TextChannel):
                new_channel = await self.new_guild.create_text_channel(name=channel.name, position=channel.position,
                                                                       topic=channel.topic,
                                                                       slowmode_delay=channel.slowmode_delay,
                                                                       nsfw=channel.nsfw,
                                                                       category=category, overwrites=overwrites,
                                                                       default_auto_archive_duration=channel.default_auto_archive_duration,
                                                                       default_thread_slowmode_delay=channel.default_thread_slowmode_delay)
                self.mappings["channels"][channel.id] = new_channel
                self.create_channel_log(channel_type="text", channel_name=new_channel.name,
                                        channel_id=new_channel.id)
            elif isinstance(channel, discord.VoiceChannel):
                bitrate = get_bitrate(channel)
                new_channel = await self.new_guild.create_voice_channel(name=channel.name, position=channel.position,
                                                                        bitrate=bitrate,
                                                                        user_limit=channel.user_limit,
                                                                        category=category, overwrites=overwrites)
                self.mappings["channels"][channel.id] = new_channel
                self.create_channel_log(channel_type="voice", channel_name=new_channel.name,
                                        channel_id=new_channel.id)
            await asyncio.sleep(self.delay)

    async def process_community(self) -> None:
        """
        Applies community-related settings to the new guild such as AFK settings, verification level, notification settings, and system channel flags.
        """
        if self.enabled_community:
            afk_channel = None
            try:
                afk_channel = self.mappings["channels"][self.guild.afk_channel.id]
            except KeyError:
                pass
            await self.new_guild.edit(community=True, verification_level=self.guild.verification_level,
                                      default_notifications=self.guild.default_notifications, afk_channel=afk_channel,
                                      afk_timeout=self.guild.afk_timeout,
                                      system_channel=self.mappings["channels"][self.guild.system_channel.id],
                                      system_channel_flags=self.guild.system_channel_flags,
                                      rules_channel=self.mappings["channels"][self.guild.rules_channel.id],
                                      public_updates_channel=self.mappings["channels"][
                                          self.guild.public_updates_channel.id],
                                      explicit_content_filter=self.guild.explicit_content_filter,
                                      preferred_locale=self.guild.preferred_locale)
            self.logger.info("Updated guild community settings")
            await asyncio.sleep(self.delay)

    async def add_community_channels(self, perms: bool = True) -> None:
        """
        Creates community-specific channels, such as Forum and Stage channels, in the new guild with appropriate permissions and settings.

        Args:
            perms (bool): If True, clones permissions for the channels as well. Defaults to True.
        """
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
                            overwrites[self.mappings["roles"][role.id]] = permissions
                if isinstance(channel, discord.ForumChannel):
                    tags: discord.abc.Sequence[discord.ForumTag] = channel.available_tags
                    for tag in tags:
                        if tag.emoji.id:
                            tag.emoji = self.mappings["emojis"].get(tag.emoji.id, None)

                    new_channel = await self.new_guild.create_forum_channel(name=channel.name, topic=channel.topic,
                                                                            position=channel.position,
                                                                            category=category,
                                                                            slowmode_delay=channel.slowmode_delay,
                                                                            nsfw=channel.nsfw, overwrites=overwrites,
                                                                            default_layout=channel.default_layout,
                                                                            default_auto_archive_duration=channel.default_auto_archive_duration,
                                                                            default_thread_slowmode_delay=channel.default_thread_slowmode_delay,
                                                                            available_tags=tags)
                    self.mappings["channels"][channel.id] = new_channel
                    self.create_channel_log(channel_type="forum", channel_name=new_channel.name,
                                            channel_id=new_channel.id)
                if isinstance(channel, discord.StageChannel):
                    bitrate = get_bitrate(channel)
                    new_channel = await self.new_guild.create_stage_channel(name=channel.name, category=category,
                                                                            position=channel.position,
                                                                            bitrate=bitrate,
                                                                            user_limit=channel.user_limit,
                                                                            rtc_region=channel.rtc_region,
                                                                            video_quality_mode=channel.video_quality_mode,
                                                                            overwrites=overwrites)
                    self.mappings["channels"][channel.id] = new_channel
                    self.create_channel_log(channel_type="stage", channel_name=new_channel.name,
                                            channel_id=new_channel.id, )
                await asyncio.sleep(self.delay)

    async def clone_emojis(self) -> None:
        """
        Clones emojis from the source guild to the new guild until the emoji limit is reached.
        """
        emoji_limit = min(self.new_guild.emoji_limit, self.new_guild.emoji_limit - 5)
        for emoji in self.mappings["fetched_data"]["emojis"][:emoji_limit]:
            if len(self.new_guild.emojis) >= emoji_limit:
                self.logger.warning("Emoji limit reached. Skipping...")
                break
            new_emoji = await self.new_guild.create_custom_emoji(
                name=emoji.name, image=await emoji.read()
            )
            self.mappings["emojis"][emoji.id] = new_emoji
            self.create_object_log(object_type="emoji", object_name=new_emoji.name, object_id=new_emoji.id)
            await asyncio.sleep(self.delay)

    async def clone_stickers(self) -> None:
        """
        Asynchronously clones stickers from the source guild to the new guild subject to the sticker limit of the new guild.
        """
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

    async def send_webhook(self, webhook: discord.Webhook, message: discord.Message,
                           delay: float = 0.85) -> None:
        """
        Sends a message through the provided webhook, attempting to clone content, attachments, and embeds from the original message.

        Args:
            webhook (discord.Webhook): The webhook through which the message should be sent.
            message (discord.Message): The original message to be cloned.
            delay (float): The delay in seconds before sending the message, to avoid rate limits. Defaults to 0.85.
        """
        author: discord.User = message.author
        files = []
        if message.attachments:
            for attachment in message.attachments:
                try:
                    files.append(await attachment.to_file())
                except discord.NotFound:
                    pass
        creation_time = message.created_at.strftime("%d/%m/%Y %H:%M")
        name: str = f"{author.name}#{author.discriminator} at {creation_time}"
        content = message.content

        for mapping_type, mapping_dict in self.mappings.items():
            if mapping_type not in {"channels", "roles"}:
                continue

            for old_id, new in mapping_dict.items():
                if mapping_type == "channels":
                    old_ref = f"<#{old_id}>"
                    new_ref = f"<#{new.id}>"
                    content = content.replace(
                        f"https://discord.com/channels/{self.guild.id}/{old_id}",
                        f"https://discord.com/channels/{self.new_guild.id}/{new.id}")
                elif mapping_type == "roles":
                    old_ref = f"<@&{old_id}>"
                    new_ref = f"<@&{new.id}>"
                else:
                    continue

                content = content.replace(old_ref, new_ref)
        try:
            await webhook.send(content=content, avatar_url=author.display_avatar.url,
                               username=name, embeds=message.embeds, files=files)
            if self.debug:
                content = (truncate_string(string=message.content, length=32,
                                           replace_newline_with="") if message.content else "")
                content = content.rstrip()
                self.logger.debug(f"Cloned message from {author.name}" + f": {content}" if content else "")
        except discord.HTTPException or discord.Forbidden:
            if self.debug:
                self.logger.debug(
                    "Can't send, skipping message in #{}".format(message.channel.name if message.channel else ""))
        await asyncio.sleep(delay)

    async def clone_messages(self, messages_limit: int = main.messages_limit,
                             clear_webhooks: bool = main.messages_webhook_clear) -> None:
        """
        Asynchronously clones a number of messages specified by messages_limit from the source guild to the new guild.
        If toggle for the cloning feature is turned off, the process is abandoned.

        Args:
            messages_limit (int): The maximum number of messages to clone. Defaults to a value from the main configuration.
            clear_webhooks (bool): A boolean indicating whether to clear webhooks after cloning. Defaults to the configured setting in main.
        """
        if not self.clone_messages_toggled:
            return

        self.processing_messages = True
        await self.populate_queue(messages_limit)

        if self.debug:
            self.logger.debug(f"Collected {len(self.message_queue)} messages")

        total_seconds = len(self.message_queue) * (self.webhook_delay + self.bot.latency)
        remaining_time = datetime.timedelta(seconds=total_seconds)

        self.logger.info(f"Calculated message cloning ETA: {format_time(remaining_time)}")

        await self.clone_messages_from_queue(clear_webhooks=clear_webhooks)

    async def cleanup_after_cloning(self, clear: bool = False) -> None:
        """
        Clears message queue and optionally deletes webhooks after message cloning.

        Args:
            clear (bool): If True, delete all webhooks and clear their mappings after cleaning the queue. Defaults to False.
        """
        self.message_queue.clear()

        if clear:
            for webhook in self.mappings["webhooks"].values():
                await webhook.delete()
                await asyncio.sleep(self.webhook_delay)
            self.mappings["webhooks"].clear()
            self.logger.success(f"Successfully cleaned up after cloning messages")

        self.processing_messages = False

    async def clone_messages_from_queue(self, clear_webhooks: bool = main.messages_webhook_clear) -> None:
        """
        Asynchronously clones messages from the message queue to their respective channels.

        Args:
            clear_webhooks (bool): A boolean indicating whether to clear webhooks after cloning. Defaults to the configured setting in main.
        """
        channel_messages_map = split_messages_by_channel(self.message_queue)
        if channel_messages_map:
            await self._process_messages_channel_map(channel_messages_map)

        if self.new_messages_queue:
            await asyncio.sleep(self.webhook_delay)
            new_messages_map = split_messages_by_channel(self.new_messages_queue)
            if new_messages_map:
                await self._process_messages_channel_map(new_messages_map)

        await self.cleanup_after_cloning(clear=clear_webhooks)

    async def _process_messages_channel_map(self, channel_messages_map):
        """
        Processes messages for each channel in the given map.

        Args:
            channel_messages_map (dict): A dictionary mapping channels to their corresponding message lists.
        """
        while channel_messages_map:
            for channel, messages in list(channel_messages_map.items()):
                if messages:
                    await self._clone_message_with_delay(channel, messages.pop(0))
                    await asyncio.sleep(self.webhook_delay)
                else:
                    self.processed_channels.append(channel.id)
                    del channel_messages_map[channel]

    async def _clone_message_with_delay(self, channel: discord.channel.TextChannel, message: discord.Message) -> None:
        """
        Asynchronously clones a single message to a specific channel using a webhook with delay.

        Args:
            channel (discord.channel.TextChannel): The destination text channel to clone the message to.
            message (discord.Message): The message to be cloned to the channel.
        """
        webhook = self.find_webhook(channel.id)
        if not webhook:
            try:
                webhook = await channel.create_webhook(name="bot by itskekoff")
            except (discord.NotFound, discord.Forbidden) as e:
                if self.debug:
                    self.logger.debug(f"Can't create webhook: " +
                                      ('unknown channel' if isinstance(e, discord.NotFound) else 'missing permissions'))
                return

            await asyncio.sleep(self.webhook_delay)

            self.create_webhook_log(channel_name=channel.name)
            self.mappings["webhooks"][channel.id] = webhook

        try:
            await self.send_webhook(webhook, message)
        except discord.errors.Forbidden:
            if self.debug:
                channel_name_str: str = message.channel.name if message.channel else "unknown"
                self.logger.debug(f"Missing access for channel: #{channel_name_str}")

    async def on_message(self, message: discord.Message):
        """
        Event listener for incoming messages that clones them to a new channel if conditions are met.

        Args:
            message (discord.Message): The message that has been received.
        """
        if message.guild and message.guild.id == self.guild.id:
            try:
                if self.live_update:
                    new_channel = self.mappings["channels"][message.channel.id]

                    if not new_channel:
                        logger.warning("Can't clone message from channel that doesn't exists in new guild")
                        return

                    if self.processing_messages and new_channel.id not in self.processed_channels:
                        if self.new_messages_enabled:
                            self.new_messages_queue.append((new_channel, message))
                        return

                    await self._clone_message_with_delay(channel=new_channel, message=message)
                    await asyncio.sleep(self.webhook_delay)
            except KeyError:
                pass
