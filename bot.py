import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from collections import deque

# ==========================================
# ตั้งค่า Bot Token ของคุณที่นี่
# ==========================================

TOKEN = os.environ.get("TOKEN")

# ==========================================
# ตั้งค่า YT-DLP
# ==========================================
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    }],
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# ==========================================
# ตั้งค่า Bot
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# เก็บ queue แยกตาม guild
queues: dict[int, deque] = {}
now_playing: dict[int, dict] = {}


def get_queue(guild_id: int) -> deque:
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]


async def search_and_get_info(query: str) -> list[dict]:
    """ค้นหาและดึงข้อมูลเพลงจาก YouTube"""
    ydl_opts = {
        **YDL_OPTIONS,
        "extract_flat": False,
        "noplaylist": True,
    }

    loop = asyncio.get_event_loop()

    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # ถ้าไม่ใช่ URL ให้ค้นหา
            if not query.startswith("http"):
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if info and "entries" in info and info["entries"]:
                    return [info["entries"][0]]
            else:
                info = ydl.extract_info(query, download=False)
                if "entries" in info:
                    return list(info["entries"])
                return [info]
        return []

    return await loop.run_in_executor(None, _search)


def play_next(ctx):
    """เล่นเพลงถัดไปใน queue"""
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    if queue:
        song = queue.popleft()
        now_playing[guild_id] = song

        source = discord.FFmpegPCMAudio(song["url"], **FFMPEG_OPTIONS)
        ctx.voice_client.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                send_now_playing(ctx, e), bot.loop
            ),
        )
    else:
        now_playing.pop(guild_id, None)


async def send_now_playing(ctx, error=None):
    """ส่งข้อความแสดงเพลงที่กำลังเล่น"""
    if error:
        print(f"Player error: {error}")
    play_next(ctx)


# ==========================================
# Commands
# ==========================================

@bot.event
async def on_ready():
    print(f"✅ บอทพร้อมใช้งาน: {bot.user.name}")
    print(f"🎵 ID: {bot.user.id}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="!help | !play <เพลง>"
        )
    )


@bot.command(name="join", aliases=["เข้ามา", "j"])
async def join(ctx):
    """เข้าร่วม Voice Channel"""
    if not ctx.author.voice:
        return await ctx.send("❌ คุณต้องอยู่ใน Voice Channel ก่อน!")

    channel = ctx.author.voice.channel

    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()

    await ctx.send(f"✅ เข้าร่วม **{channel.name}** แล้ว!")


@bot.command(name="play", aliases=["p", "เล่น"])
async def play(ctx, *, query: str):
    """เล่นเพลงจาก YouTube"""
    if not ctx.author.voice:
        return await ctx.send("❌ คุณต้องอยู่ใน Voice Channel ก่อน!")

    # เข้า voice channel ถ้ายังไม่ได้อยู่
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    async with ctx.typing():
        msg = await ctx.send(f"🔍 กำลังค้นหา **{query}**...")

        songs = await search_and_get_info(query)

        if not songs:
            return await msg.edit(content="❌ ไม่พบเพลงที่ค้นหา")

        queue = get_queue(ctx.guild.id)

        for song in songs:
            if song:
                queue.append({
                    "title": song.get("title", "ไม่ทราบชื่อ"),
                    "url": song.get("url", song.get("webpage_url", "")),
                    "duration": song.get("duration", 0),
                    "thumbnail": song.get("thumbnail", ""),
                    "requester": ctx.author.display_name,
                })

        if len(songs) > 1:
            await msg.edit(content=f"✅ เพิ่ม **{len(songs)} เพลง** เข้า Queue แล้ว!")
        else:
            title = songs[0].get("title", "ไม่ทราบชื่อ") if songs else query
            dur = songs[0].get("duration", 0) if songs else 0
            mins, secs = divmod(int(dur), 60)
            await msg.edit(
                content=f"✅ เพิ่ม **{title}** ({mins}:{secs:02d}) เข้า Queue แล้ว!"
            )

    # เริ่มเล่นถ้าไม่มีเพลงกำลังเล่นอยู่
    if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        play_next(ctx)
        if ctx.guild.id in now_playing:
            song = now_playing[ctx.guild.id]
            embed = discord.Embed(
                title="🎵 กำลังเล่น",
                description=f"**{song['title']}**",
                color=0x5865F2,
            )
            if song.get("thumbnail"):
                embed.set_thumbnail(url=song["thumbnail"])
            embed.add_field(name="ผู้ขอ", value=song["requester"])
            dur = song.get("duration", 0)
            mins, secs = divmod(int(dur), 60)
            embed.add_field(name="ความยาว", value=f"{mins}:{secs:02d}")
            await ctx.send(embed=embed)


@bot.command(name="pause", aliases=["หยุด"])
async def pause(ctx):
    """หยุดชั่วคราว"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ หยุดชั่วคราวแล้ว")
    else:
        await ctx.send("❌ ไม่มีเพลงกำลังเล่นอยู่")


@bot.command(name="resume", aliases=["เล่นต่อ"])
async def resume(ctx):
    """เล่นต่อ"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ เล่นต่อแล้ว")
    else:
        await ctx.send("❌ ไม่มีเพลงที่หยุดอยู่")


@bot.command(name="skip", aliases=["s", "ข้าม"])
async def skip(ctx):
    """ข้ามเพลง"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ ข้ามเพลงแล้ว")
    else:
        await ctx.send("❌ ไม่มีเพลงกำลังเล่นอยู่")


@bot.command(name="stop", aliases=["หยุดเลย"])
async def stop(ctx):
    """หยุดเล่นและล้าง Queue"""
    guild_id = ctx.guild.id
    queues[guild_id] = deque()
    now_playing.pop(guild_id, None)

    if ctx.voice_client:
        ctx.voice_client.stop()

    await ctx.send("⏹ หยุดเล่นและล้าง Queue แล้ว")


@bot.command(name="queue", aliases=["q", "คิว"])
async def show_queue(ctx):
    """แสดง Queue เพลง"""
    queue = get_queue(ctx.guild.id)
    guild_id = ctx.guild.id

    embed = discord.Embed(title="🎶 Queue เพลง", color=0x5865F2)

    # เพลงที่กำลังเล่น
    if guild_id in now_playing:
        song = now_playing[guild_id]
        embed.add_field(
            name="🎵 กำลังเล่น",
            value=f"**{song['title']}** — {song['requester']}",
            inline=False,
        )

    if not queue:
        embed.add_field(name="Queue ว่างเปล่า", value="ใช้ `!play` เพื่อเพิ่มเพลง", inline=False)
    else:
        lines = []
        for i, song in enumerate(list(queue)[:10], 1):
            dur = song.get("duration", 0)
            mins, secs = divmod(int(dur), 60)
            lines.append(f"`{i}.` **{song['title']}** ({mins}:{secs:02d}) — {song['requester']}")

        if len(queue) > 10:
            lines.append(f"\n...และอีก {len(queue) - 10} เพลง")

        embed.add_field(name=f"รายการถัดไป ({len(queue)} เพลง)", value="\n".join(lines), inline=False)

    await ctx.send(embed=embed)


@bot.command(name="nowplaying", aliases=["np", "กำลังเล่น"])
async def now_playing_cmd(ctx):
    """แสดงเพลงที่กำลังเล่น"""
    guild_id = ctx.guild.id

    if guild_id not in now_playing:
        return await ctx.send("❌ ไม่มีเพลงกำลังเล่นอยู่")

    song = now_playing[guild_id]
    embed = discord.Embed(
        title="🎵 กำลังเล่น",
        description=f"**{song['title']}**",
        color=0x5865F2,
    )
    if song.get("thumbnail"):
        embed.set_thumbnail(url=song["thumbnail"])
    embed.add_field(name="ผู้ขอ", value=song["requester"])
    await ctx.send(embed=embed)


@bot.command(name="clear", aliases=["ล้างคิว"])
async def clear_queue(ctx):
    """ล้าง Queue"""
    queues[ctx.guild.id] = deque()
    await ctx.send("🗑 ล้าง Queue แล้ว")


@bot.command(name="leave", aliases=["ออก", "dc"])
async def leave(ctx):
    """ออกจาก Voice Channel"""
    if ctx.voice_client:
        queues.pop(ctx.guild.id, None)
        now_playing.pop(ctx.guild.id, None)
        await ctx.voice_client.disconnect()
        await ctx.send("👋 ออกจาก Voice Channel แล้ว")
    else:
        await ctx.send("❌ บอทไม่ได้อยู่ใน Voice Channel")


@bot.command(name="volume", aliases=["vol", "เสียง"])
async def volume(ctx, vol: int):
    """ปรับระดับเสียง (0-100)"""
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        return await ctx.send("❌ ไม่มีเพลงกำลังเล่นอยู่")

    if not 0 <= vol <= 100:
        return await ctx.send("❌ ระดับเสียงต้องอยู่ระหว่าง 0-100")

    ctx.voice_client.source.volume = vol / 100
    await ctx.send(f"🔊 ปรับเสียงเป็น **{vol}%**")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ กรุณาใส่ข้อมูลให้ครบ: `{error.param.name}`")
    else:
        print(f"Error: {error}")


if __name__ == "__main__":
    bot.run(TOKEN)
