from mimetypes import guess_type
from re import compile as regex_compile

import nextcord
from aiohttp import ClientSession as AioClientSession
from nextcord.ext import commands

from utils import BotClass


class MediaRate(commands.Cog):
    def __init__(self, bot: BotClass):
        self.bot = bot
        self.url_regex = regex_compile(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
        )

        media_rate_channels = self.bot.CFG.get("media_rate_channels", [])

        if not media_rate_channels:
            print(
                "['media_rate_channels' channels not set, disabling media rating subroutine]"
            )
            return

        self.media_rate_channel_ids = []
        for channel_name in media_rate_channels:
            if channel_name not in self.bot.channels:
                print(
                    f"['{channel_name}' not found, disabling media rating subroutine]"
                )
                return
            self.media_rate_channel_ids.append(self.bot.channels[channel_name].id)

        self.downvote_emoji = self.bot.CFG.get("media_rate_downvote", "👎")
        self.upvote_emoji = self.bot.CFG.get("media_rate_upvote", "👍")

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        if message.channel.id not in self.media_rate_channel_ids:
            return

        has_media = False
        if len(message.attachments) > 0:
            has_media = True
        if not has_media:
            for embed in message.embeds:
                for nullable_property in [embed.video, embed.thumbnail, embed.image]:
                    if nullable_property != nextcord.Embed.Empty:
                        has_media = True
                        break
        if not has_media:
            message_urls = self.url_regex.findall(message.content)

            for url in message_urls:
                mime_type, _ = guess_type(url)
                if (mime_type) and mime_type.startswith(("image", "video", "audio")):
                    has_media = True
                    break

                async with AioClientSession() as session:
                    async with session.get(url) as response:
                        try:
                            body = await response.text()
                            if (
                                "og:image" in body
                                or "og:video" in body
                                or "og:audio" in body
                            ):
                                has_media = True
                                break
                        except Exception:  # nosec
                            continue

        if not has_media:
            return

        await message.add_reaction(self.upvote_emoji)
        await message.add_reaction(self.downvote_emoji)
