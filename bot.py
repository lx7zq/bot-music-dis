import logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logger.warning("=== NEW VERSION LOADED ===")

import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import gc
import shutil
import stat
import platform
import ctypes
import ctypes.util
import urllib.request
import tarfile
import subprocess
from collections import deque

BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
os.makedirs(BIN_DIR, exist_ok=True)

# ── ffmpeg ─────────────────────────────────────────────────────────────────
def _ensure_ffmpeg() -> str:
    logger.warning("[DIAG] หา ffmpeg...")
    found = shutil.which("ffmpeg")
    if found:
        logger.warning(f"[DIAG] ffmpeg in PATH: {found}")
        return found
    local = os.path.join(BIN_DIR, "ffmpeg")
    # ลบ ffmpeg เก่าทิ้งเพื่อ force re-download version ใหม่
    if os.path.isfile(local) and os.access(local, os.X_OK):
        try:
            result = subprocess.run([local, "-version"], capture_output=True, text=True, timeout=3)
            ver = (result.stdout or "").split("version ")[-1].split(" ")[0] if "version" in (result.stdout or "") else ""
            if not ver.startswith("4."):
                logger.warning(f"[DIAG] ffmpeg version {ver} ไม่ใช่ 4.x — ลบแล้ว re-download")
                os.remove(local)
            else:
                logger.warning(f"[DIAG] ffmpeg local v{ver}: {local}")
                return local
        except Exception:
            pass

    logger.warning("[DIAG] ffmpeg ไม่พบ — กำลัง download...")
    url = "https://johnvansickle.com/ffmpeg/old-releases/ffmpeg-4.4.1-amd64-static.tar.xz"
    tar_path = "/tmp/ffmpeg.tar.xz"
    try:
        urllib.request.urlretrieve(url, tar_path)
        with tarfile.open(tar_path, "r:xz") as t:
            for member in t.getmembers():
                if member.name.endswith("/ffmpeg") and "/" in member.name:
                    member.name = "ffmpeg"
                    t.extract(member, path=BIN_DIR)
                    break
        os.chmod(local, os.stat(local).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        logger.warning(f"[DIAG] ✅ ffmpeg downloaded: {local}")
        return local
    except Exception as e:
        logger.warning(f"[DIAG] ❌ ffmpeg download failed: {e}")
        return "ffmpeg"

# ── opus ───────────────────────────────────────────────────────────────────
def _ensure_opus() -> None:
    if discord.opus.is_loaded():
        logger.warning("[DIAG] ✅ Opus already loaded")
        return

    paths = ["libopus.so.0", "libopus.so", "opus",
             "/usr/lib/x86_64-linux-gnu/libopus.so.0",
             "/usr/lib/aarch64-linux-gnu/libopus.so.0",
             "/usr/local/lib/libopus.so.0"]
    lib = ctypes.util.find_library("opus")
    if lib:
        paths.insert(0, lib)

    for path in paths:
        try:
            discord.opus.load_opus(path)
            logger.warning(f"[DIAG] ✅ Opus loaded: {path}")
            return
        except Exception:
            pass

    # download .deb แล้วแตก .so
    opus_so = os.path.join(BIN_DIR, "libopus.so.0")
    if os.path.isfile(opus_so):
        try:
            discord.opus.load_opus(opus_so)
            logger.warning(f"[DIAG] ✅ Opus loaded from cache: {opus_so}")
            return
        except Exception:
            pass

    logger.warning("[DIAG] Opus ไม่พบ — กำลัง download .deb...")
    deb_url = "http://ftp.debian.org/debian/pool/main/o/opus/libopus0_1.3.1-3_amd64.deb"
    deb_path = "/tmp/libopus0.deb"
    try:
        urllib.request.urlretrieve(deb_url, deb_path)
        # แตก .deb ด้วย Python ล้วนๆ ไม่ใช้ ar command
        with open(deb_path, "rb") as f:
            if f.read(8) != b"!<arch>\n":
                raise ValueError("ไม่ใช่ ar archive")
            while True:
                header = f.read(60)
                if len(header) < 60:
                    break
                name = header[0:16].decode("ascii", errors="replace").strip()
                size = int(header[48:58].decode("ascii").strip())
                data = f.read(size)
                if size % 2 == 1:
                    f.read(1)
                if name.startswith("data.tar"):
                    ext = name.rstrip("/").split(".", 2)[-1]
                    tmp_tar = f"/tmp/opus_data.tar.{ext}"
                    with open(tmp_tar, "wb") as tf:
                        tf.write(data)
                    with tarfile.open(tmp_tar) as t:
                        for member in t.getmembers():
                            if "libopus.so.0" in member.name and not member.islnk() and not member.issym():
                                member.name = "libopus.so.0"
                                t.extract(member, path=BIN_DIR)
                                break
                    break
        os.chmod(opus_so, os.stat(opus_so).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        discord.opus.load_opus(opus_so)
        logger.warning(f"[DIAG] ✅ Opus downloaded & loaded: {opus_so}")
    except Exception as e:
        logger.warning(f"[DIAG] ❌ Opus download failed: {e}")

FFMPEG_PATH = _ensure_ffmpeg()

try:
    import nacl
    logger.warning(f"[DIAG] PyNaCl: {nacl.__version__}")
except ImportError:
    logger.warning("[DIAG] ❌ PyNaCl NOT installed!")

TOKEN = os.environ.get("TOKEN")

YDL_SEARCH = {
    "format": "worstaudio/bestaudio[abr<=64]/bestaudio",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "noplaylist": True,
    "skip_download": True,
    "no_color": True,
    "ignoreerrors": True,
    "no_cache_dir": True,
    "socket_timeout": 15,
}

YDL_STREAM = {
    "format": "worstaudio/bestaudio[abr<=64]/bestaudio",
    "quiet": True,
    "no_warnings": True,
    "source_address": "0.0.0.0",
    "noplaylist": True,
    "skip_download": True,
    "no_color": True,
    "no_cache_dir": True,
    "socket_timeout": 15,
}

FFMPEG_OPTIONS = {
    "executable": FFMPEG_PATH,
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 "
        "-reconnect_delay_max 5 "
        "-nostdin "
    ),
    "options": "-vn -loglevel warning",
}

intents = discord.Intents.none()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

queues: dict[int, deque] = {}
now_playing: dict[int, dict] = {}


def get_queue(guild_id: int) -> deque:
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]


def fmt_duration(seconds) -> str:
    mins, secs = divmod(int(seconds or 0), 60)
    return f"{mins}:{secs:02d}"


async def fetch_songs(query: str, limit: int = 1) -> list[dict]:
    search_query = query if query.startswith("http") else f"ytsearch{limit}:{query}"

    def _fetch():
        with yt_dlp.YoutubeDL(YDL_SEARCH) as ydl:
            info = ydl.extract_info(search_query, download=False)
            if not info:
                return []
            entries = info.get("entries", [info])
            result = []
            for e in entries:
                if not e:
                    continue
                result.append({
                    "title": e.get("title", "ไม่ทราบชื่อ"),
                    "webpage_url": e.get("webpage_url", ""),
                    "duration": e.get("duration", 0),
                    "thumbnail": e.get("thumbnail", ""),
                })
            return result[:limit]

    try:
        songs = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        gc.collect()
        return songs
    except Exception as e:
        logger.warning(f"fetch_songs error: {e}")
        return []


async def fetch_stream_url(webpage_url: str) -> str:
    def _fetch():
        with yt_dlp.YoutubeDL(YDL_STREAM) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
            if not info:
                raise ValueError("no info")
            url = info.get("url")
            if not url:
                for fmt in (info.get("formats") or []):
                    if fmt.get("url") and fmt.get("acodec") != "none":
                        url = fmt["url"]
                        break
            if not url:
                raise ValueError("no stream url")
            return url

    url = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    gc.collect()
    return url


def build_now_playing_embed(song: dict) -> discord.Embed:
    embed = discord.Embed(
        title="🎵 กำลังเล่น",
        description=f"**{song['title']}**",
        color=0x5865F2,
    )
    if song.get("thumbnail"):
        embed.set_thumbnail(url=song["thumbnail"])
    embed.add_field(name="⏱ ความยาว", value=fmt_duration(song.get("duration")))
    embed.add_field(name="👤 ผู้ขอ", value=song.get("requester", "?"))
    return embed


async def _play_next_async(ctx) -> dict | None:
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    if not ctx.voice_client or not ctx.voice_client.is_connected():
        return None
    if not queue:
        now_playing.pop(guild_id, None)
        return None

    song = queue.popleft()
    now_playing[guild_id] = song

    logger.warning(f"[PLAY] โหลด: {song['title']}")

    # download เป็นไฟล์ก่อนแล้วค่อยเล่น (หลีกเลี่ยง ffmpeg stream ที่ segfault)
    tmp_path = f"/tmp/song_{guild_id}.opus"
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        ydl_opts = {
            "format": "bestaudio[ext=opus]/bestaudio[ext=webm]/bestaudio",
            "outtmpl": tmp_path.replace(".opus", ""),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
        }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([song["webpage_url"]])

        await asyncio.get_event_loop().run_in_executor(None, _download)

        # หาไฟล์ที่ download มา (extension อาจต่างกัน)
        actual_path = None
        for ext in ["opus", "webm", "m4a", "mp3", "ogg"]:
            p = tmp_path.replace(".opus", f".{ext}")
            if os.path.exists(p):
                actual_path = p
                break
        # yt-dlp อาจไม่ใส่ extension
        if not actual_path and os.path.exists(tmp_path.replace(".opus", "")):
            actual_path = tmp_path.replace(".opus", "")

        if not actual_path:
            raise FileNotFoundError("ไม่พบไฟล์ที่ download")

        logger.warning(f"[PLAY] downloaded: {actual_path} ({os.path.getsize(actual_path)} bytes)")
    except Exception as e:
        logger.warning(f"[PLAY] ❌ download error: {e}")
        await ctx.send(f"❌ โหลดเพลง **{song['title']}** ไม่ได้ ข้ามไปเพลงถัดไป...")
        return await _play_next_async(ctx)

    try:
        ffmpeg_audio = discord.FFmpegPCMAudio(actual_path, executable=FFMPEG_PATH)
        source = discord.PCMVolumeTransformer(ffmpeg_audio, volume=0.5)
        logger.warning("[PLAY] FFmpegPCMAudio OK")
    except Exception as e:
        logger.warning(f"[PLAY] ❌ FFmpegPCMAudio error: {e}")
        await ctx.send(f"❌ FFmpeg error: {e}")
        return None

    def after_play(error):
        if error:
            logger.warning(f"[PLAY] ❌ after error: {error}")
        try:
            if os.path.exists(actual_path):
                os.remove(actual_path)
        except Exception:
            pass
        asyncio.run_coroutine_threadsafe(_play_next_async(ctx), bot.loop)

    ctx.voice_client.play(source, after=after_play)
    logger.warning(f"[PLAY] is_playing={ctx.voice_client.is_playing()}")
    gc.collect()
    return song


class PlayerView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if not vc:
            return await interaction.response.send_message("❌ ไม่มีเพลงกำลังเล่น", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            button.emoji = "▶️"
            await interaction.response.edit_message(view=self)
        elif vc.is_paused():
            vc.resume()
            button.emoji = "⏸"
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("❌ ไม่มีเพลงกำลังเล่น", ephemeral=True)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭ ข้ามเพลงแล้ว", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ไม่มีเพลงกำลังเล่น", ephemeral=True)

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.ctx.guild.id
        queues[guild_id] = deque()
        now_playing.pop(guild_id, None)
        vc = self.ctx.voice_client
        if vc:
            vc.stop()
        await interaction.response.send_message("⏹ หยุดและล้าง Queue แล้ว", ephemeral=True)

    @discord.ui.button(emoji="📋", style=discord.ButtonStyle.secondary)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = get_queue(self.ctx.guild.id)
        if not queue:
            return await interaction.response.send_message("📋 Queue ว่างเปล่า", ephemeral=True)
        lines = [f"`{i}.` {s['title']} ({fmt_duration(s.get('duration'))})"
                 for i, s in enumerate(list(queue)[:10], 1)]
        if len(queue) > 10:
            lines.append(f"...และอีก {len(queue)-10} เพลง")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class SearchView(discord.ui.View):
    def __init__(self, ctx, results: list[dict]):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.results = results
        for i, song in enumerate(results[:5]):
            title_short = song["title"][:50] + "…" if len(song["title"]) > 50 else song["title"]
            btn = discord.ui.Button(
                label=f"{i+1}. {title_short}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"search_{i}",
                row=i,
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                return await interaction.response.send_message("❌ ไม่ใช่คนค้นหา", ephemeral=True)
            song = dict(self.results[index])
            song["requester"] = self.ctx.author.display_name
            get_queue(self.ctx.guild.id).append(song)
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(
                content=f"✅ เพิ่ม **{song['title']}** เข้า Queue แล้ว!", view=self)
            vc = self.ctx.voice_client
            if vc and not vc.is_playing() and not vc.is_paused():
                played = await _play_next_async(self.ctx)
                if played:
                    await self.ctx.send(embed=build_now_playing_embed(played), view=PlayerView(self.ctx))
        return callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


@bot.event
async def on_ready():
    logger.warning(f"[READY] Bot: {bot.user.name} ({bot.user.id})")
    logger.warning(f"[READY] discord.py: {discord.__version__}")
    _ensure_opus()
    logger.warning(f"[READY] Opus loaded: {discord.opus.is_loaded()}")
    try:
        result = subprocess.run([FFMPEG_PATH, "-version"], capture_output=True, text=True, timeout=5)
        first_line = (result.stdout or result.stderr).splitlines()[0]
        logger.warning(f"[DIAG] ffmpeg test: {first_line}")
    except Exception as e:
        logger.warning(f"[DIAG] ffmpeg test failed: {e}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="!play <เพลง>"))


@bot.command(name="join", aliases=["j", "เข้ามา"])
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ คุณต้องอยู่ใน Voice Channel ก่อน!")
    ch = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(ch)
    else:
        await ch.connect(reconnect=True, self_deaf=False, self_mute=False)
    await ctx.send(f"✅ เข้าร่วม **{ch.name}** แล้ว!")


@bot.command(name="play", aliases=["p", "เล่น"])
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("❌ คุณต้องอยู่ใน Voice Channel ก่อน!")
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect(reconnect=True, self_deaf=False, self_mute=False)

    msg = await ctx.send(f"🔍 กำลังค้นหา **{query}**...")
    try:
        songs = await fetch_songs(query, limit=1 if not query.startswith("http") else 50)
    except Exception as e:
        return await msg.edit(content=f"❌ เกิดข้อผิดพลาด: {e}")

    if not songs:
        return await msg.edit(content="❌ ไม่พบเพลงที่ค้นหา")

    queue = get_queue(ctx.guild.id)
    for s in songs:
        s["requester"] = ctx.author.display_name
        queue.append(s)

    if len(songs) > 1:
        await msg.edit(content=f"✅ เพิ่ม **{len(songs)} เพลง** เข้า Queue แล้ว!")
    else:
        await msg.edit(content=f"✅ เพิ่ม **{songs[0]['title']}** ({fmt_duration(songs[0].get('duration'))}) เข้า Queue แล้ว!")

    if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        played = await _play_next_async(ctx)
        if played:
            await ctx.send(embed=build_now_playing_embed(played), view=PlayerView(ctx))


@bot.command(name="search", aliases=["ค้นหา", "หา"])
async def search(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("❌ คุณต้องอยู่ใน Voice Channel ก่อน!")
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect(reconnect=True, self_deaf=False, self_mute=False)

    msg = await ctx.send(f"🔍 กำลังค้นหา **{query}**...")
    results = await fetch_songs(query, limit=5)
    if not results:
        return await msg.edit(content="❌ ไม่พบเพลงที่ค้นหา")

    lines = [f"`{i+1}.` **{r['title']}** ({fmt_duration(r.get('duration'))})"
             for i, r in enumerate(results)]
    embed = discord.Embed(title=f"🔍 ผลค้นหา: {query}",
                          description="\n".join(lines), color=0x5865F2)
    embed.set_footer(text="กดปุ่มด้านล่างเพื่อเลือกเพลง (หมดเวลา 30 วิ)")
    await msg.edit(content=None, embed=embed, view=SearchView(ctx, results))


@bot.command(name="pause", aliases=["หยุด"])
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ หยุดชั่วคราวแล้ว")
    else:
        await ctx.send("❌ ไม่มีเพลงกำลังเล่นอยู่")


@bot.command(name="resume", aliases=["เล่นต่อ"])
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ เล่นต่อแล้ว")
    else:
        await ctx.send("❌ ไม่มีเพลงที่หยุดอยู่")


@bot.command(name="skip", aliases=["s", "ข้าม"])
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ ข้ามเพลงแล้ว")
    else:
        await ctx.send("❌ ไม่มีเพลงกำลังเล่นอยู่")


@bot.command(name="stop", aliases=["หยุดเลย"])
async def stop(ctx):
    queues[ctx.guild.id] = deque()
    now_playing.pop(ctx.guild.id, None)
    if ctx.voice_client:
        ctx.voice_client.stop()
    await ctx.send("⏹ หยุดเล่นและล้าง Queue แล้ว")


@bot.command(name="queue", aliases=["q", "คิว"])
async def show_queue(ctx):
    queue = get_queue(ctx.guild.id)
    embed = discord.Embed(title="🎶 Queue เพลง", color=0x5865F2)
    if ctx.guild.id in now_playing:
        s = now_playing[ctx.guild.id]
        embed.add_field(name="🎵 กำลังเล่น",
                        value=f"**{s['title']}** ({fmt_duration(s.get('duration'))}) — {s.get('requester','?')}",
                        inline=False)
    if not queue:
        embed.add_field(name="Queue ว่างเปล่า", value="ใช้ `!play` เพื่อเพิ่มเพลง", inline=False)
    else:
        lines = [f"`{i}.` **{s['title']}** ({fmt_duration(s.get('duration'))}) — {s.get('requester','?')}"
                 for i, s in enumerate(list(queue)[:10], 1)]
        if len(queue) > 10:
            lines.append(f"...และอีก {len(queue)-10} เพลง")
        embed.add_field(name=f"รายการถัดไป ({len(queue)} เพลง)", value="\n".join(lines), inline=False)
    await ctx.send(embed=embed)


@bot.command(name="nowplaying", aliases=["np", "กำลังเล่น"])
async def now_playing_cmd(ctx):
    if ctx.guild.id not in now_playing:
        return await ctx.send("❌ ไม่มีเพลงกำลังเล่นอยู่")
    await ctx.send(embed=build_now_playing_embed(now_playing[ctx.guild.id]), view=PlayerView(ctx))


@bot.command(name="clear", aliases=["ล้างคิว"])
async def clear_queue(ctx):
    queues[ctx.guild.id] = deque()
    await ctx.send("🗑 ล้าง Queue แล้ว")


@bot.command(name="leave", aliases=["ออก", "dc"])
async def leave(ctx):
    if ctx.voice_client:
        queues.pop(ctx.guild.id, None)
        now_playing.pop(ctx.guild.id, None)
        await ctx.voice_client.disconnect()
        await ctx.send("👋 ออกจาก Voice Channel แล้ว")
    else:
        await ctx.send("❌ บอทไม่ได้อยู่ใน Voice Channel")


@bot.command(name="volume", aliases=["vol", "เสียง"])
async def volume(ctx, vol: int):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        return await ctx.send("❌ ไม่มีเพลงกำลังเล่นอยู่")
    if not 0 <= vol <= 100:
        return await ctx.send("❌ ระดับเสียงต้องอยู่ระหว่าง 0-100")
    if hasattr(ctx.voice_client.source, "volume"):
        ctx.voice_client.source.volume = vol / 100
        await ctx.send(f"🔊 ปรับเสียงเป็น **{vol}%**")
    else:
        await ctx.send("⚠️ ไม่สามารถปรับเสียงในโหมดนี้ได้")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ กรุณาใส่ข้อมูลให้ครบ: `{error.param.name}`")
    else:
        logger.warning(f"Command error: {error}")


if __name__ == "__main__":
    bot.run(TOKEN)