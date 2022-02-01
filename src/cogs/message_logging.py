import sqlite3
from asyncio import create_task
from datetime import datetime
from json import dumps as json_dumps
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import nextcord
from nextcord.ext import commands

from utils import BotClass, do_log, get_est_time

MessageColumnsType = Tuple[int, float, int, int, str, Optional[str]]


class MessageLogging(commands.Cog):
    def __init__(self, bot: BotClass):
        self.bot = bot
        self.disabled = False
        if not self.bot.CFG.get("message_log", False):
            print(
                "[message_log set to 'false' or missing from config, disabling message logging subroutine."
            )
            self.disabled = True
            return
        self.loading = True
        self.db_path = Path.cwd() / "data" / "message_log.sqlite"
        self.message_buffer: List[MessageColumnsType] = []
        self.message_buffer_not_empty = False
        self.setup_db()

    def setup_db(self):
        self.db_connection = sqlite3.connect(self.db_path)
        self.db_cursor = self.db_connection.cursor()

        db_table_structure = [
            "CREATE TABLE messages(message_id INTEGER PRIMARY KEY DESC, utc_time REAL, channel_id INTEGER, "
            "author_id INTEGER, message_content TEXT, extra_data TEXT)",
        ]
        new_db = True
        try:
            for query in db_table_structure:
                self.db_cursor.execute(query)
        except Exception:  # nosec
            new_db = False  # TODO: figure out db-exists exception

        if new_db:
            create_task(self.scrape_server_messages())
        else:
            create_task(self.find_channel_checkpoints())

    async def find_channel_checkpoints(self):
        do_log("Identifying what channels to scrape/when to scrape from")
        time_maps = {}
        existing_channels = [
            item[0]
            for item in self.db_cursor.execute(
                "SELECT DISTINCT channel_id FROM MESSAGES"
            ).fetchall()
        ]
        for channel_id in existing_channels:
            channel_object = self.bot.guild.get_channel_or_thread(channel_id)
            if channel_object is None:
                continue  # Channel no longer accessible

            try:
                newest_msg = self.db_cursor.execute(
                    "SELECT * FROM messages WHERE channel_id=:id ORDER BY utc_time DESC LIMIT 1",
                    {"id": channel_id},
                ).fetchone()
                epoch_time = newest_msg[1]
                newest_time = datetime.fromtimestamp(epoch_time)

            except Exception:  # nosec
                continue

            time_maps[channel_id] = {"time": newest_time, "obj": channel_object}

        all_channels = self.bot.guild.threads + self.bot.guild.text_channels
        for channel in all_channels:
            if channel.id not in time_maps:
                time_maps[channel.id] = {"time": None, "obj": channel}

        await self.scrape_server_messages(time_maps)

    async def scrape_server_messages(self, time_maps: Dict[str, Any] | None = None):
        if time_maps is None:
            do_log("No message log database found, scraping full server")
            channels = self.bot.guild.threads + self.bot.guild.text_channels
        else:
            do_log(f"Updating logs for {len(time_maps)} channels")
            channels = [channel["obj"] for channel in time_maps.values()]
        for channel in channels:
            if (
                time_maps is not None
                and time_maps.get(channel.id, {}).get("time") is not None
            ):
                after_datetime = time_maps[channel.id]["time"]
                do_log(
                    f"Scraping messages in #{channel.name} after {get_est_time(after_datetime)}"
                )
            else:
                do_log(f"Scraping all messages in #{channel.name}")
                after_datetime = None

            message_rows: List[MessageColumnsType] = []
            try:
                async for message in channel.history(limit=None, after=after_datetime):
                    row = await self.message_to_db_columns(message)
                    message_rows.append(row)
                    if len(message_rows) % 100 != 0:
                        continue
                    do_log(
                        f"Scraping #{channel.name} ({len(message_rows)} messages processed)"
                    )
            except Exception as e:  # nosec
                do_log(f"Exception when processing #{channel.name} ({e})")
            if not message_rows:
                continue
            do_log(
                f"Committing {len(message_rows)} messages from #{channel.name} to database"
            )
            await self.insert_many_to_db(message_rows)
            do_log(
                f"Committed {len(message_rows)} messages from #{channel.name} to database"
            )
        do_log("Message scraping complete")
        self.loading = False

        if self.message_buffer:
            do_log(f"Committing {len(self.message_buffer)} unprocessed messages")
            await self.insert_many_to_db(self.message_buffer)
            do_log(f"Committed {len(self.message_buffer)} unprocessed messages")
            self.message_buffer = []

        do_log("Message logging ready")

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        if self.disabled:
            return

        message_entry = await self.message_to_db_columns(message)

        if self.loading:
            self.message_buffer.append(message_entry)
            return

        await self.insert_to_db(message_entry)

    async def insert_to_db(self, message_row: MessageColumnsType):
        self.db_cursor.execute(
            "INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?);", message_row
        )
        self.db_connection.commit()

    async def insert_many_to_db(self, message_row_list: List[MessageColumnsType]):
        query = "INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?);"
        self.db_cursor.executemany(query, message_row_list)
        self.db_connection.commit()

    async def message_to_db_columns(
        self, message: nextcord.Message
    ) -> MessageColumnsType:
        extra_data: Dict[str, Any] = {}

        # Prioritizing edge case handling over readability
        if message.reference is not None and message.reference.message_id is not None:
            extra_data["replying_to"] = message.reference.message_id

        attachments = []
        for attachment in message.attachments:
            attachment_obj: Dict[str, Any] = {
                "content_type": None,
                "filename": None,
                "url": None,
            }
            try:
                attachment_obj["content_type"] = attachment.content_type
            except Exception:  # nosec
                pass
            try:
                attachment_obj["filename"] = attachment.filename
            except Exception:  # nosec
                pass
            try:
                attachment_obj["url"] = attachment.url
            except Exception:  # nosec
                pass

            attachments.append(attachment_obj)
        if attachments:
            extra_data["attachments"] = attachments

        embeds = []
        for embed in message.embeds:
            try:
                embeds.append(embed.to_dict())
            except Exception:  # nosec
                pass
        if embeds:
            extra_data["embeds"] = embeds

        stickers = []
        for sticker in message.stickers:
            sticker_obj: Dict[str, Any] = {
                "id": None,
                "name": None,
                "format": None,
                "url": None,
            }
            try:
                sticker_obj["id"] = sticker.id
            except Exception:  # nosec
                pass
            try:
                sticker_obj["name"] = sticker.name
            except Exception:  # nosec
                pass
            try:
                sticker_obj["format"] = sticker.format
            except Exception:  # nosec
                pass
            try:
                sticker_obj["url"] = sticker.url
            except Exception:  # nosec
                pass

            stickers.append(sticker_obj)
        if stickers:
            extra_data["stickers"] = stickers

        extra_data_column = (
            json_dumps(extra_data, separators=(",", ":")) if extra_data else None
        )
        columns = (
            int(message.id),
            float(message.created_at.timestamp()),
            int(message.channel.id),
            int(message.author.id),
            str(message.content),
            extra_data_column,
        )
        return columns
