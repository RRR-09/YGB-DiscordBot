import logging
from argparse import ArgumentParser
from datetime import datetime
from json import load as load_json
from math import floor
from typing import Any, Dict, List, TextIO, Tuple, Union

from nextcord import Guild as DiscordGuild
from nextcord import Intents as DiscordIntents
from nextcord import Message as DiscordMessage
from nextcord import Role as DiscordRole
from nextcord import TextChannel as DiscordChannel
from nextcord import User as DiscordUser
from nextcord import Webhook as DiscordWebhook
from nextcord.ext.commands import Bot as DiscordBot
from pytz import timezone


class BotClass:
    def __init__(self):
        intents = DiscordIntents.default()
        intents.members = True
        intents.guilds = True
        intents.messages = True
        intents.invites = True

        self.client = DiscordBot(command_prefix="/", intents=intents)
        self.logger = logging.getLogger("nextcord")
        self.logger.setLevel(logging.ERROR)
        self.handler = logging.FileHandler(
            filename="nextcord.log", encoding="utf-8", mode="w"
        )
        self.handler.setFormatter(
            logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
        )
        self.logger.addHandler(self.handler)

        self.CFG: Dict[Any, Any] = {}
        self.guild = DiscordGuild
        self.channels: Dict[str, DiscordChannel] = {}
        self.roles: Dict[str, DiscordRole] = {}
        self.ready = False
        do_log("Initialized Discord Client")


def censor_text(text: str, leave_uncensored: int = 4) -> str:
    """
    Censors the second half (excluding the last 'leave_uncensored' number of letters) for the
    string argument 'text'
    """
    return (
        text[: int(len(text) / 2)]
        + str("*" * (int(len(text) / 2) - 4))
        + text[:leave_uncensored]
    )


def get_est_time(datetime_to_convert: datetime = None) -> str:
    """
    Gets the current time (or 'datetime_to_convert' arg, if provided) as datetime and converts it to a
    readable string
    """
    desired_timezone = timezone("America/Toronto")
    if datetime_to_convert is not None:
        input_timezone = timezone("UTC")
        if datetime_to_convert.tzinfo is not None:
            # TODO: Convert datetime tzinfo to pytz accordingly
            do_log("GET_EST_TIME ERROR, PLEASE IMPLEMENT CONVERTER")
            return "ERROR"
        timezoned_datetime = input_timezone.localize(datetime_to_convert)
        output_datetime = timezoned_datetime.astimezone(desired_timezone)
    else:
        output_datetime = datetime.now(desired_timezone)

    return output_datetime.strftime("%Y-%b-%d %I:%M:%S %p EST")


def do_log(message: str):
    print(f"[{get_est_time()}] {message}")


def log_error(error: str):
    if "KeyboardInterrupt" in error:
        raise KeyboardInterrupt
    error_message = f"[{get_est_time()}]\n{error}"
    error_log_filename = "errors.log"
    try:
        with open(error_log_filename, "a") as error_log:
            error_log.write(error_message)
    except FileNotFoundError:
        with open(error_log_filename, "w") as error_log:
            error_message = f"[{get_est_time()}] WARNING: Failed to find existing error log. Writing to new.\n\n{error}"
            error_log.write(error_message)
    do_log(error_message)


def json_eval_object_pairs_hook(ordered_pairs: List[Tuple[Any, Any]]) -> Dict:
    """
    Additional hook for JSON loader to turn any strings into representative datatypes (bool, int,
    float) wherever possible.
    """
    special = {
        "true": True,
        "false": False,
        "null": None,
    }
    result = {}
    for key, value in ordered_pairs:
        if key in special:
            key = special[key]
        else:
            for numeric in int, float:
                try:
                    key = numeric(key)
                except ValueError:
                    continue
                else:
                    break
        result[key] = value
    return result


def json_load_eval(fp_obj: TextIO) -> Dict:
    """
    Loads a JSON file, evaluating any strings to possible variables.
    """
    return load_json(fp_obj, object_pairs_hook=json_eval_object_pairs_hook)


async def get_hook_in_server(
    message: DiscordMessage, hook_user: DiscordUser
) -> Union[DiscordWebhook, None]:
    if type(message.channel) != DiscordChannel:
        return None
    found_hook = None
    hooks = await message.channel.webhooks()
    for h in hooks:
        if h.user is not None and h.user.id == hook_user.id:
            found_hook = h
            break
    if found_hook is None:
        found_hook = await message.channel.create_webhook(name=hook_user.display_name)
    return found_hook


async def get_english_timestamp(time_var: Union[int, float]) -> str:
    """
    Takes in a time, in seconds, and converts it to a readable string representing
    elapsed or remaining time (i.e. "1 day, 2 hours, 3 minutes, 4 seconds")
    """
    original_time = time_var
    seconds_in_minute = 60
    seconds_in_hour = 60 * seconds_in_minute
    seconds_in_day = 24 * seconds_in_hour
    days = floor(time_var / seconds_in_day)
    time_var -= days * seconds_in_day
    hours = floor(time_var / seconds_in_hour)
    time_var -= hours * seconds_in_hour
    minutes = floor(time_var / seconds_in_minute)
    time_var -= minutes * seconds_in_minute
    seconds = round(time_var)
    if minutes == 0:
        return "{} second{}".format(seconds, "s" if seconds != 1 else "")
    if hours == 0:
        return "{} minute{}".format(minutes, "s" if minutes != 1 else "")
    hours_rounded = round(original_time / seconds_in_hour, 1)
    if days == 0:
        return "{} hour{}".format(hours_rounded, "s" if hours_rounded != 1 else "")
    return "{} day{}, {} hour{}".format(
        days, "s" if days != 1 else "", hours_rounded, "s" if hours_rounded != 1 else ""
    )


def load_config_to_bot(bot_instance: BotClass) -> BotClass:
    parser = ArgumentParser(description="Discord bot arguments.")
    parser.add_argument(
        "--config", help="Filepath for the config JSON file", default="config.json"
    )
    args = parser.parse_args()
    try:
        with open(args.config, "r", encoding="utf-8") as config_file:
            loaded_config = json_load_eval(config_file)
    except FileNotFoundError:
        raise FileNotFoundError(f"'{args.config}' not found.")
    for config_key in loaded_config:
        loaded_val = loaded_config[config_key]
        bot_instance.CFG[config_key] = loaded_val
        do_log(
            f"Loaded config setting \n'{config_key}' ({type(loaded_val).__name__})\n{loaded_val} "
        )
    return bot_instance
