import asyncio
import time
from collections import defaultdict

import discord
from discord.ext import commands

import main
from modules.arg_parser import parse_args
from modules.cloner import ServerCopy


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
            "process_new_messages": main.process_new_messages_enabled
        }

        args = parse_args(args_str, defaults)
        guild: discord.Guild = await self.bot.fetch_guild(args["from"]) if args["from"] else ctx.message.guild
        if guild is None and args["from"] is None:
            main.logger.error("Error in clone command: can't find guild to copy")
            return

        start_time = time.time()
        target_name = format_guild_name(target_guild=guild)

        cloner: ServerCopy = ServerCopy(
            from_guild=guild,
            to_guild=None,
            delay=main.clone_delay,
            webhook_delay=main.messages_delay,
            live_update_toggled=args["real_time_messages"],
            process_new_messages=args["process_new_messages"],
            clone_messages_toggled=args["clone_messages"],
            oldest_first=main.clone_oldest_first,
        )
        logger = cloner.logger
        self.cloners.append(cloner)

        if args["new"] is None or await self.bot.fetch_guild(args["new"]) is None:
            logger.info("Creating server...")
            try:
                new_guild: discord.Guild = await self.bot.create_guild(name=target_name)
            except discord.HTTPException:
                logger.error(
                    'Unable to create server automatically. Create it yourself and run command with "new=id" argument')
                return
        else:
            logger.info("Getting server...")
            new_guild: discord.Guild = await self.bot.fetch_guild(args["new"])

        if new_guild is None:
            logger.error("Can't create server. Maybe account invalid or requires captcha?")
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
        if cloner.enabled_community:
            conditions_to_functions[args["clone_channels"]].append(("Processing community settings...",
                                                                    cloner.process_community))
            conditions_to_functions[args["clone_channels"]].append(("Processing community additional channels...",
                                                                    cloner.add_community_channels))
        conditions_to_functions[args["clone_messages"]].append(("Processing server messages...",
                                                                cloner.clone_messages))
        true_conditions = conditions_to_functions[True]

        for message, function in true_conditions:
            logger.info(message)
            await function()

        if not args["real_time_messages"]:
            self.cloners.remove(cloner)

        logger.success(f"Done in {round((time.time() - start_time), 2)} seconds.")


async def setup(bot):
    await bot.add_cog(ClonerCog(bot))
