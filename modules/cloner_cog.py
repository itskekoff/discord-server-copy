import asyncio
import datetime
import time
from collections import defaultdict

import discord
from discord.ext import commands

import main
from modules.arg_parser import parse_args
from modules.cloner import ServerCopy
from modules.utilities import format_time


def format_guild_name(target_guild: discord.Guild) -> str:
    return main.name_syntax.replace("%original%", target_guild.name)


class ClonerCog(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.cloners: list[ServerCopy] = []

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.cloners:
            for cloner in self.cloners:
                await cloner.on_message(message=message)

    @commands.command(name="process")
    async def process(self, ctx: commands.Context, *, args_str: str = ""):
        """
        Manipulates over cloning process
        Can be used while you need to disable bot and re-run clone.
        """
        await ctx.message.delete()

        defaults = {
            "save": True,
            "load": False,
            "start": False,
        }

        args = parse_args(args_str, defaults)

        latest_cloner: ServerCopy = self.cloners[-1]
        if args["save"] or (not args["load"] and not args["start"]):
            latest_cloner.save_state()
        if args["load"]:
            latest_cloner.load_state()
        if args["start"]:
            last_method = latest_cloner.last_executed_method
            cloner_args = latest_cloner.args
            conditions_to_functions = {}

            def append_if_different(condition, logger_message, executing_function):
                if condition and last_method != function.__name__:
                    conditions_to_functions[True] = conditions_to_functions.get(True, [])
                    conditions_to_functions[True].append((logger_message, executing_function))

            append_if_different(cloner_args["clear_guild"], "Preparing guild to process...", cloner.prepare_server)
            append_if_different(cloner_args["clone_icon"], "Processing server icon...", cloner.clone_icon)
            append_if_different(cloner_args["clone_banner"], "Processing server banner...", cloner.clone_banner)
            append_if_different(cloner_args["clone_roles"], "Processing server roles...", cloner.clone_roles)
            append_if_different(cloner_args["clone_channels"], "Processing server categories...",
                                cloner.clone_categories)
            append_if_different(cloner_args["clone_channels"], "Processing server channels...", cloner.clone_channels)
            append_if_different(cloner_args["clone_emojis"], "Processing server emojis...", cloner.clone_emojis)
            append_if_different(cloner_args["clone_stickers"], "Processing stickers...", cloner.clone_stickers)
            append_if_different(cloner_args["clone_messages"], "Processing server messages...", cloner.clone_messages)
            true_conditions = conditions_to_functions[True]

            for message, function in true_conditions:
                logger.info(message)
                await function()

    @commands.command(name="copy", aliases=["clone", "paste", "parse", "start"])
    async def copy(self, ctx: commands.Context, *, args_str: str = ""):
        """
        Clones an entire Discord server, including all messages. Specifies behavior for the optional 'from' and 'new' arguments.

        Main arguments:
        - from (default: None): Specifies the source server ID for cloning. If omitted or set to None,
            the server where the command is executed will be used as the source.
        - new (default: None): Determines the name of the new cloned server. If omitted or set to None,
            a new server with a default name will be created.

        """

        await ctx.message.delete()

        defaults = {
            "from": None,
            "new": None,
            "clear_guild": main.clear_guild,
            "clone_icon": main.clone_icon,
            "clone_banner": main.clone_banner,
            "clone_roles": main.clone_roles,
            "clone_channels": main.clone_channels,
            "clone_emojis": main.clone_emojis,
            "clone_stickers": main.clone_stickers,
            "clone_messages": main.clone_messages_enabled,
            "real_time_messages": main.live_update_enabled,
            "process_new_messages": main.process_new_messages_enabled,
            "disable_fetch_channels": False
        }

        args = parse_args(args_str, defaults)
        guild: discord.Guild = await self.bot.fetch_guild(args["from"]) if args["from"] else ctx.message.guild
        if guild is None and args["from"] is None:
            main.logger.error("Error in clone command: can't find guild to copy")
            return

        start_time = time.time()
        target_name = format_guild_name(target_guild=guild)

        cloner: ServerCopy = ServerCopy(
            bot=self.bot,
            args=args,
            from_guild=guild,
            to_guild=None,
            delay=main.clone_delay,
            webhook_delay=main.messages_delay,
            live_update_toggled=args["real_time_messages"],
            process_new_messages=args["process_new_messages"],
            clone_messages_toggled=args["clone_messages"],
            oldest_first=main.clone_oldest_first,
            disable_fetch_channels=args["disable_fetch_channels"]
        )
        logger = cloner.logger
        self.cloners.append(cloner)

        if args["new"] is None or await self.bot.fetch_guild(args["new"]) is None:
            logger.info("Creating server...")
            try:
                new_guild: discord.Guild = await self.bot.create_guild(name=target_name)
            except discord.HTTPException:
                logger.error("Unable to create server automatically. ")
                logger.error('Create it yourself and run command with "new=id" argument')
                return
        else:
            logger.info("Getting server...")
            new_guild: discord.Guild = await self.bot.fetch_guild(args["new"])

        if new_guild is None:
            logger.error("Can't create server. Maybe account disabled or requires captcha?")
            return

        if new_guild.name is not target_name:
            await new_guild.edit(name=target_name)

        cloner.new_guild = new_guild

        logger.info("Processing modules")

        conditions_to_functions = defaultdict(list)

        await cloner.fetch_required_data()

        conditions_to_functions[args["clear_guild"]].append(("Preparing guild to process...", cloner.prepare_server))
        conditions_to_functions[args["clone_icon"]].append(("Processing server icon...", cloner.clone_icon))
        conditions_to_functions[args["clone_banner"]].append(("Processing server banner...", cloner.clone_banner))
        conditions_to_functions[args["clone_roles"]].append(("Processing server roles...", cloner.clone_roles))
        conditions_to_functions[args["clone_channels"]].append(("Processing server categories...",
                                                                cloner.clone_categories))
        conditions_to_functions[args["clone_channels"]].append(("Processing server channels...",
                                                                cloner.clone_channels))
        conditions_to_functions[args["clone_emojis"]].append(("Processing server emojis...", cloner.clone_emojis))
        conditions_to_functions[args["clone_stickers"]].append(("Processing stickers...", cloner.clone_stickers))
        conditions_to_functions[args["clone_messages"]].append(("Processing server messages...",
                                                                cloner.clone_messages))
        true_conditions = conditions_to_functions[True]

        for message, function in true_conditions:
            logger.info(message)
            await function()

        if not args["real_time_messages"]:
            self.cloners.remove(cloner)

        done_seconds = round((time.time() - start_time), 2)
        logger.success(f"Done in {format_time(datetime.timedelta(seconds=done_seconds))}")


async def setup(bot):
    await bot.add_cog(ClonerCog(bot))
