import importlib
import inspect
import io
import re
import typing
from collections import deque
from datetime import timedelta

import discord
from PIL import Image, ImageSequence
from discord.ext import commands

from modules.logger import Logger

logger = Logger(debug_enabled=True)
logger.bind(source="Utilities")


def get_key(value: typing.Any, my_dict: dict) -> typing.Any:
    """
    Retrieves the first key in a dictionary corresponding to the provided value.

    Args:
        value (typing.Any): The value for which the corresponding key is to be found.
        my_dict (dict): The dictionary in which to search for the value.

    Returns:
        typing.Any: The key corresponding to the provided value, or None if the value is not found.
    """
    try:
        return list(my_dict.keys())[list(my_dict.values()).index(value)]
    except ValueError:
        return None


def truncate_string(string: str, length: int, replace_newline_with: str = ' ') -> str:
    """
    Truncates a string to a specified length, with the option to replace newline characters with a
    specified string, and appends an ellipsis if the string is longer than the specified length.

    Args:
        string (str): The string to be truncated.
        length (int): The maximum allowed length of the string.
        replace_newline_with (str): The string to replace newline characters with. Defaults to a space.

    Returns:
        str: The truncated string, potentially with newline characters replaced and ellipsis appended.
    """
    string = string.replace('\n', replace_newline_with)
    return (string if len(string) <= length else string[:length - 3] + '...').strip()


def split_messages_by_channel(messages_queue: deque) -> typing.Dict[discord.TextChannel, typing.List[typing.Any]]:
    """
    Splits the queued messages by their destination channels into a dictionary mapping channels to message lists.

    Args:
        messages_queue (deque): A deque containing queued messages.

    Returns:
        dict: A dictionary mapping text channels to corresponding lists of messages to be cloned.
    """
    channel_messages_map = {}
    while messages_queue:
        channel, message = messages_queue.popleft()
        if channel not in channel_messages_map:
            channel_messages_map[channel] = []
        channel_messages_map[channel].append(message)
    return channel_messages_map


def get_bitrate(channel: discord.channel.VocalGuildChannel) -> int | None:
    """
    Returns the bitrate of a Discord vocal guild channel if it's less than or equal to 96000; otherwise, None.

    Args:
        channel (discord.channel.VocalGuildChannel): The vocal guild channel from which to get the bitrate.

    Returns:
        int | None: The bitrate of the channel if it's less than or equal to 96000; otherwise, None.
    """
    return channel.bitrate if channel.bitrate <= 96000 else None


async def get_first_frame(image: discord.Asset) -> bytes:
    """
    Asynchronously retrieves the first frame of an animated Discord Asset as bytes, or the whole image
    if it's not animated.

    Args:
        image (discord.Asset): The Discord Asset from which to get the first frame.

    Returns:
        bytes: The bytes of the first frame of an animated image, or the bytes of the whole image if not animated.
    """
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


def format_time(delta: timedelta) -> str:
    """
    Formats a timedelta object into a readable English string.

    Args:
        delta (timedelta): A timedelta object representing a duration.

    Returns:
        str: A formatted time string in the format "X days Y hours Z minutes W seconds".
             The singular or plural form of words (day/hour/minute/second) is used
             based on their quantity. Only non-zero time units are included.
    """
    years = delta.days // 365
    days = delta.days % 365
    seconds = delta.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    time_parts = [
        ('year', years),
        ("day", days),
        ("hour", hours),
        ("minute", minutes),
        ("second", seconds)
    ]

    return " ".join(f"{value} {name}{('s' if value != 1 else '')}"
                    for name, value in time_parts if value)


def format_description(description: str) -> str:
    """
    Formats a multi-line string into a bulleted list of description lines.

    Args:
        description (str): The original description text.

    Returns:
        str: A formatted string where each line of the original description is
             preceded by a bullet.
    """
    return "\n   ".join(["    - Description:"] + [f"   {line.strip()}" for line in description.split("\n")])


def get_command_info(bot: commands.Bot) -> str:
    """
    Retrieves and formats information about all the commands registered in a bot instance.

    This function inspects the Bot commands and extracts key information such
    as command names, aliases, and descriptions from the docstrings.

    Args:
        bot (commands.Bot): The bot instance.

    Returns:
        str: A formatted string containing information about each command, such as
             command names, aliases, arguments, and descriptions.
    """
    command_info = []
    for command in bot.commands:
        name = command.name
        aliases = command.aliases or []
        args_info = []

        source_lines, _ = inspect.getsourcelines(command.callback)
        source_code = ''.join(source_lines)

        description_match = re.search(r'""".*?"""', source_code, re.DOTALL)
        description = description_match.group(0).strip('"""') if description_match else ""

        defaults = {}
        defaults_match = re.search(r'defaults\s*=\s*\{(.+?)\}', source_code, re.DOTALL)
        if defaults_match:
            defaults_str = defaults_match.group(1)
            defaults = {key.strip('\'"'): value.strip() for key, value in
                        re.findall(r"['\"]([^'\"]+)['\"]\s*:\s*([^\n,]+)", defaults_str)}

        command_str = f"* Command: {name} {f'(aliases: {aliases})' if aliases else ''}\n"
        if description:
            command_str += format_description(description)
        if defaults:
            command_str += "\n    - Arguments:\n"
            for idx, (arg_name, default_value) in enumerate(defaults.items(), start=1):
                if default_value.startswith('str') or default_value.startswith('None'):
                    default_value_str = default_value
                else:
                    default_value_str = default_value.split("|")[0].strip()

                    try:
                        local_scope = {
                            'main': importlib.import_module('main')
                        }
                        default_value_str = str(eval(default_value_str, {}, local_scope))
                    except Exception as e:
                        logger.error(f"Exception in eval command default: {e.__class__.__name__}")
                        pass

                arg_info = f"{arg_name} (default: {default_value_str})"
                args_info.append(arg_info)

            for idx, arg_info in enumerate(args_info, start=1):
                command_str += f"       {idx}. {arg_info}\n"
        command_info.append(command_str)
    return "\n".join(command_info)
