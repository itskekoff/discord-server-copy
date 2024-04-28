import importlib
import inspect
import re

from discord.ext import commands

from modules.logger import Logger

logger = Logger(debug_enabled=True)
logger.bind(source="Utilities")


def format_description(description: str) -> str:
    return "\n   ".join(["    - Description:"] + [f"   {line.strip()}" for line in description.split("\n")])


def get_command_info(bot: commands.Bot) -> str:
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
