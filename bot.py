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
now_playing_msg: dict[int, discord.Message] = {}

# ── Vote Skip ──────────────────────────────────────────────────────────────
skip_votes: dict[int, set] = {}
VOTE_SKIP_THRESHOLD = 2

# ── Auto-disconnect ────────────────────────────────────────────────────────
_idle_timers: dict[int, asyncio.Task] = {}
AUTO_DISCONNECT_DELAY = 180

async def _auto_disconnect(guild_id: int, voice_client, delay: int = AUTO_DISCONNECT_DELAY):
    await asyncio.sleep(delay)
    if voice_client and voice_client.is_connected():
        if not voice_client.is_playing() and not voice_client.is_paused():
            logger.warning(f"[AUTO-DC] Guild {guild_id} เงียบนาน {delay}s — กำลังออก...")
            queues.pop(guild_id, None)
            now_playing.pop(guild_id, None)
            await voice_client.disconnect()
            logger.warning(f"[AUTO-DC] Guild {guild_id} ออกแล้ว")

def _reset_idle_timer(ctx):
    guild_id = ctx.guild.id
    if guild_id in _idle_timers:
        _idle_timers[guild_id].cancel()
    if ctx.voice_client and ctx.voice_client.is_connected():
        _idle_timers[guild_id] = asyncio.create_task(
            _auto_disconnect(guild_id, ctx.voice_client)
        )
        logger.warning(f"[AUTO-DC] Guild {guild_id} เริ่มนับ {AUTO_DISCONNECT_DELAY}s")

def _cancel_idle_timer(guild_id: int):
    if guild_id in _idle_timers:
        _idle_timers[guild_id].cancel()
        _idle_timers.pop(guild_id, None)
# ──────────────────────────────────────────────────────────────────────────


def get_queue(guild_id: int) -> deque:
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]


def fmt_duration(seconds) -> str:
    mins, secs = divmod(int(seconds or 0), 60)
    return f"{mins}:{secs:02d}"


def queue_total_duration(queue: deque) -> str:
    total = sum(s.get("duration", 0) for s in queue)
    hours, remainder = divmod(int(total), 3600)
    mins, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


async def fetch_songs(query: str, limit: int = 1, progress_callback=None) -> list[dict]:
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


async def fetch_playlist_with_progress(query: str, msg: discord.Message, limit: int = 50) -> list[dict]:
    result = []

    def _fetch():
        ydl_opts = {**YDL_SEARCH, "noplaylist": False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if not info:
                return []
            entries = info.get("entries", [info])
            return [e for e in entries if e][:limit]

    try:
        raw = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        total = len(raw)
        for i, e in enumerate(raw, 1):
            result.append({
                "title": e.get("title", "ไม่ทราบชื่อ"),
                "webpage_url": e.get("webpage_url", ""),
                "duration": e.get("duration", 0),
                "thumbnail": e.get("thumbnail", ""),
            })
            if i % 5 == 0 or i == total:
                try:
                    await msg.edit(content=f"˚⋆𐙚 กำลังโหลด Playlist... **{i}/{total}** เพลง ♡")
                except Exception:
                    pass
        gc.collect()
        return result
    except Exception as e:
        logger.warning(f"fetch_playlist error: {e}")
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


# ── Helpers ────────────────────────────────────────────────────────────────

def _is_same_channel(ctx) -> bool:
    vc = ctx.voice_client
    if not vc:
        return False
    return ctx.author.voice and ctx.author.voice.channel == vc.channel


# ── Helper: ลบ now playing message เก่า ───────────────────────────────────

async def _delete_now_playing_msg(guild_id: int):
    """ลบ embed Now Playing เก่าทิ้งเลย"""
    old_msg = now_playing_msg.pop(guild_id, None)
    if old_msg:
        try:
            await old_msg.delete()
        except Exception:
            pass


# ── Embed & View ───────────────────────────────────────────────────────────

def build_now_playing_embed(song: dict, queue: deque | None = None) -> discord.Embed:
    embed = discord.Embed(
        description=f"### ⋆˚𐙚｡ {song['title']} ｡𐙚˚⋆",
        color=0x5865F2,
    )
    embed.add_field(name="☁︎ ความยาว", value=fmt_duration(song.get("duration")), inline=True)
    embed.add_field(name="♡ ผู้ขอ", value=song.get("requester", "?"), inline=True)

    if queue:
        q_list = list(queue)
        if q_list:
            next_song = q_list[0]
            embed.add_field(
                name="⋆ ถัดไป",
                value=f"{next_song['title']} ({fmt_duration(next_song.get('duration'))})",
                inline=False,
            )

    if song.get("thumbnail"):
        embed.set_thumbnail(url=song["thumbnail"])
    embed.set_footer(text="⋆𐙚˚ กำลังเล่นอยู่นะ ♡ • ใช้ปุ่มด้านล่างเพื่อควบคุม ˚𐙚⋆")
    return embed


class MoveChannelView(discord.ui.View):
    def __init__(self, ctx, target_channel, query: str):
        super().__init__(timeout=20)
        self.ctx = ctx
        self.target_channel = target_channel
        self.query = query
        self.answered = False

    @discord.ui.button(label="𐙚˚⋆ ย้ายและเล่นเพลงเลย", style=discord.ButtonStyle.success)
    async def move_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("˚⋆ ไม่ใช่คนสั่งนะ ♡", ephemeral=True)
        self.answered = True
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"𐙚˚⋆ ย้ายไปที่ **{self.target_channel.name}** แล้ว ♡ กำลังโหลดเพลง...", view=self)

        await self.ctx.voice_client.move_to(self.target_channel)

        songs = await fetch_songs(self.query, limit=1 if not self.query.startswith("http") else 50)
        if not songs:
            await self.ctx.send("˚⋆ หาเพลงไม่เจอเลย ♡ ลองใหม่นะ")
            return
        queue = get_queue(self.ctx.guild.id)
        was_playing = self.ctx.voice_client.is_playing() or self.ctx.voice_client.is_paused()
        pos_before = len(queue)
        for s in songs:
            s["requester"] = self.ctx.author.display_name
            queue.append(s)
        if len(songs) > 1:
            await self.ctx.send(f"𐙚˚⋆ เพิ่ม **{len(songs)} เพลง** เข้า Queue แล้วนะ ♡")
        elif was_playing:
            await self.ctx.send(
                f"𐙚˚⋆ เพิ่ม **{songs[0]['title']}** เข้า Queue แล้ว ♡ อยู่ในคิวที่ #{pos_before + 1}")
        if not was_playing:
            played = await _play_next_async(self.ctx, announce=False)
            if played:
                sent = await self.ctx.send(
                    embed=build_now_playing_embed(played, get_queue(self.ctx.guild.id)),
                    view=PlayerView(self.ctx))
                now_playing_msg[self.ctx.guild.id] = sent

    @discord.ui.button(label="˚⋆ ไม่ต้องนะ", style=discord.ButtonStyle.danger)
    async def move_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("˚⋆ ไม่ใช่คนสั่งนะ ♡", ephemeral=True)
        self.answered = True
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="˚⋆ โอเค ยกเลิกแล้วนะ ♡", view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

class PlayerView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(emoji="⏮", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message("˚⋆ ยังไม่มีเพลงเล่นอยู่นะ ♡", ephemeral=True)
        guild_id = self.ctx.guild.id
        current = now_playing.get(guild_id)
        if current:
            get_queue(guild_id).appendleft(current)
            vc.stop()
        await interaction.response.send_message("𐙚˚⋆ เริ่มเพลงนี้ใหม่แล้วนะ ♡", ephemeral=True)

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.primary, row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if not vc:
            return await interaction.response.send_message("˚⋆ ยังไม่มีเพลงเล่นอยู่นะ ♡", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            button.emoji = "▶️"
            await interaction.response.edit_message(view=self)
        elif vc.is_paused():
            vc.resume()
            button.emoji = "⏸"
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("˚⋆ ยังไม่มีเพลงเล่นอยู่นะ ♡", ephemeral=True)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.primary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            return await interaction.response.send_message("˚⋆ ยังไม่มีเพลงเล่นอยู่นะ ♡", ephemeral=True)

        guild_id = self.ctx.guild.id
        current = now_playing.get(guild_id, {})
        requester = current.get("requester", "")
        user_name = interaction.user.display_name

        if user_name == requester:
            skip_votes.pop(guild_id, None)
            await interaction.response.send_message("𐙚˚⋆ ข้ามเพลงแล้วนะ ♡", ephemeral=True)
            vc.stop()
            return

        human_members = [m for m in vc.channel.members if not m.bot]
        if len(human_members) < VOTE_SKIP_THRESHOLD:
            skip_votes.pop(guild_id, None)
            await interaction.response.send_message("𐙚˚⋆ ข้ามเพลงแล้วนะ ♡", ephemeral=True)
            vc.stop()
            return

        votes = skip_votes.setdefault(guild_id, set())
        votes.add(interaction.user.id)
        needed = max(VOTE_SKIP_THRESHOLD, len(human_members) // 2 + 1)
        if len(votes) >= needed:
            skip_votes.pop(guild_id, None)
            await interaction.response.send_message(
                f"⏭ Vote skip ผ่าน ({len(votes)}/{needed}) — ข้ามเพลงแล้ว!", ephemeral=False)
            vc.stop()
        else:
            await interaction.response.send_message(
                f"𐙚˚⋆ โหวตข้ามเพลง **{len(votes)}/{needed}** โหวต", ephemeral=False)

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger, row=0)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.ctx.guild.id
        queues[guild_id] = deque()
        now_playing.pop(guild_id, None)
        skip_votes.pop(guild_id, None)
        vc = self.ctx.voice_client
        if vc:
            vc.stop()
        # ลบข้อความ now playing นี้เลย
        await interaction.response.defer()
        await _delete_now_playing_msg(guild_id)
        _reset_idle_timer(self.ctx)
        await self.ctx.send("𐙚˚⋆ หยุดและล้าง Queue แล้วนะ ♡")

    @discord.ui.button(emoji="📋", style=discord.ButtonStyle.secondary, row=0)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = get_queue(self.ctx.guild.id)
        if not queue:
            return await interaction.response.send_message("📋 ˚⋆ ยังไม่มีเพลงเลยนะ ⋆˚", ephemeral=True)
        lines = [f"`{i}.` {s['title']} ({fmt_duration(s.get('duration'))})"
                 for i, s in enumerate(list(queue)[:10], 1)]
        if len(queue) > 10:
            lines.append(f"...และอีก {len(queue)-10} เพลง")
        total_dur = queue_total_duration(queue)
        lines.append(f"\n♡ รวม {len(queue)} เพลง • {total_dur}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

# ──────────────────────────────────────────────────────────────────────────


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
                return await interaction.response.send_message("˚⋆ ไม่ใช่คนค้นหาอะ ♡", ephemeral=True)
            song = dict(self.results[index])
            song["requester"] = self.ctx.author.display_name
            queue = get_queue(self.ctx.guild.id)
            queue.append(song)
            pos = len(queue)

            for item in self.children:
                item.disabled = True

            vc = self.ctx.voice_client
            if vc and (vc.is_playing() or vc.is_paused()):
                await interaction.response.edit_message(
                    content=f"𐙚˚⋆ เพิ่ม **{song['title']}** เข้า Queue แล้ว ♡ อยู่ในคิวที่ #{pos}",
                    view=self)
            else:
                await interaction.response.edit_message(
                    content=f"𐙚˚⋆ เพิ่ม **{song['title']}** เข้า Queue แล้วนะ ♡", view=self)
                if vc:
                    await _play_next_async(self.ctx, announce=True)
        return callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


async def _play_next_async(ctx, announce: bool = True, keep_msg: bool = False) -> dict | None:
    """
    keep_msg=True → อย่าลบ now_playing_msg เก่า (ใช้ตอนเพลงแรกที่ caller จะ edit msg เองหลังจากนี้)
    """
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    if not ctx.voice_client or not ctx.voice_client.is_connected():
        return None

    if not queue:
        now_playing.pop(guild_id, None)
        skip_votes.pop(guild_id, None)
        # ── queue หมด: ลบ embed เก่าทิ้ง ──────────────────────────────
        if not keep_msg:
            await _delete_now_playing_msg(guild_id)
        # ──────────────────────────────────────────────────────────────
        _reset_idle_timer(ctx)
        return None

    _cancel_idle_timer(guild_id)
    skip_votes.pop(guild_id, None)

    # ── เปลี่ยนเพลง: ลบ embed เก่าทิ้ง ───────────────────────────────
    if not keep_msg:
        await _delete_now_playing_msg(guild_id)
    # ──────────────────────────────────────────────────────────────────

    song = queue.popleft()
    now_playing[guild_id] = song

    logger.warning(f"[PLAY] โหลด: {song['title']}")

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

        actual_path = None
        for ext in ["opus", "webm", "m4a", "mp3", "ogg"]:
            p = tmp_path.replace(".opus", f".{ext}")
            if os.path.exists(p):
                actual_path = p
                break
        if not actual_path and os.path.exists(tmp_path.replace(".opus", "")):
            actual_path = tmp_path.replace(".opus", "")

        if not actual_path:
            raise FileNotFoundError("ไม่พบไฟล์ที่ download")

        logger.warning(f"[PLAY] downloaded: {actual_path} ({os.path.getsize(actual_path)} bytes)")
    except Exception as e:
        logger.warning(f"[PLAY] ❌ download error: {e}")
        await ctx.send(f"❌ โหลดเพลง **{song['title']}** ไม่ได้ ข้ามไปเพลงถัดไป...")
        return await _play_next_async(ctx, announce=announce)

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
        asyncio.run_coroutine_threadsafe(_play_next_async(ctx, announce=True), bot.loop)

    ctx.voice_client.play(source, after=after_play)
    logger.warning(f"[PLAY] is_playing={ctx.voice_client.is_playing()}")

    if announce:
        sent = await ctx.send(
            embed=build_now_playing_embed(song, get_queue(guild_id)),
            view=PlayerView(ctx),
        )
        now_playing_msg[guild_id] = sent

    gc.collect()
    return song


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
        type=discord.ActivityType.listening, name="˚⋆𐙚 !play <ชื่อเพลง> ♡"))


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    vc = member.guild.voice_client
    if not vc or not vc.channel:
        return
    human_members = [m for m in vc.channel.members if not m.bot]
    if len(human_members) == 0:
        logger.warning(f"[AUTO-DC] ไม่มีคนใน channel — เริ่มนับ {AUTO_DISCONNECT_DELAY}s")
        guild_id = member.guild.id
        if guild_id in _idle_timers:
            _idle_timers[guild_id].cancel()
        _idle_timers[guild_id] = asyncio.create_task(
            _auto_disconnect(guild_id, vc)
        )
    else:
        if vc.is_playing() or vc.is_paused():
            _cancel_idle_timer(member.guild.id)


@bot.command(name="join", aliases=["j", "เข้ามา"])
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("˚⋆ เข้า Voice Channel ก่อนนะ ♡")
    ch = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(ch)
    else:
        await ch.connect(reconnect=True, self_deaf=False, self_mute=False)
    await ctx.send(f"𐙚˚⋆ เข้าร่วม **{ch.name}** แล้วนะ ♡")


@bot.command(name="play", aliases=["p", "เล่น"])
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("˚⋆ เข้า Voice Channel ก่อนนะ ♡")

    if ctx.voice_client and not _is_same_channel(ctx):
        target = ctx.author.voice.channel
        prompt = await ctx.send(
            f"⚠️ บอทกำลังเล่นอยู่ใน **{ctx.voice_client.channel.name}** "
            f"— จะย้ายไปที่ **{target.name}** ไหม?",
            view=MoveChannelView(ctx, target, query),
        )
        return

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect(reconnect=True, self_deaf=False, self_mute=False)

    _cancel_idle_timer(ctx.guild.id)

    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    # Radio/Mix (list=RD...) และ start_radio ไม่ใช่ playlist จริง — treat เป็นเพลงเดี่ยว
    _is_radio = "list=RD" in query or "start_radio=1" in query
    is_playlist = (query.startswith("http")
                   and not _is_radio
                   and ("list=" in query or "/playlist" in query))
    msg = await ctx.send(f"⋆˚𐙚 กำลังหาเพลง **{query}** อยู่นะ ♡")

    try:
        if is_playlist:
            songs = await fetch_playlist_with_progress(query, msg, limit=50)
        else:
            songs = await fetch_songs(query, limit=1 if (not query.startswith("http") or _is_radio) else 50)
    except Exception as e:
        return await msg.edit(content=f"❌ เกิดข้อผิดพลาด: {e}")

    if not songs:
        return await msg.edit(content="˚⋆ หาเพลงไม่เจอเลย ♡ ลองใหม่นะ")

    queue = get_queue(ctx.guild.id)
    was_playing = (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()
                   or ctx.guild.id in now_playing)
    pos_before = len(queue)

    for s in songs:
        s["requester"] = ctx.author.display_name
        queue.append(s)

    if len(songs) > 1:
        await msg.edit(content=f"𐙚˚⋆ เพิ่ม **{len(songs)} เพลง** เข้า Queue แล้วนะ ♡")
    elif was_playing:
        pos = pos_before + 1
        await msg.edit(
            content=f"✅ เพิ่ม **{songs[0]['title']}** ({fmt_duration(songs[0].get('duration'))}) "
                    f"เข้า Queue แล้ว — อยู่ในคิวที่ #{pos}"
        )
    else:
        # ── เพลงแรก: keep_msg=True เพื่อไม่ให้ _play_next_async ลบ msg ──
        played = await _play_next_async(ctx, announce=False, keep_msg=True)
        if played:
            await msg.edit(
                content=None,
                embed=build_now_playing_embed(played, get_queue(ctx.guild.id)),
                view=PlayerView(ctx),
            )
            now_playing_msg[ctx.guild.id] = msg  # set หลัง edit เท่านั้น
        return

    if not was_playing:
        await _play_next_async(ctx, announce=False)


@bot.command(name="search", aliases=["ค้นหา", "หา"])
async def search(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("˚⋆ เข้า Voice Channel ก่อนนะ ♡")
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect(reconnect=True, self_deaf=False, self_mute=False)

    msg = await ctx.send(f"⋆˚𐙚 กำลังหาเพลง **{query}** อยู่นะ ♡")
    results = await fetch_songs(query, limit=5)
    if not results:
        return await msg.edit(content="˚⋆ หาเพลงไม่เจอเลย ♡ ลองใหม่นะ")

    lines = [f"`{i+1}.` **{r['title']}** ({fmt_duration(r.get('duration'))})"
             for i, r in enumerate(results)]
    embed = discord.Embed(title=f"⋆˚ ผลค้นหา ˚⋆ • {query}",
                          description="\n".join(lines), color=0x5865F2)
    embed.set_footer(text="♡ กดเลือกเพลงที่ชอบได้เลย ˚⋆ (หมดเวลา 30 วิ)")
    await msg.edit(content=None, embed=embed, view=SearchView(ctx, results))


@bot.command(name="pause", aliases=["หยุด"])
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("𐙚˚⋆ หยุดชั่วคราวแล้วนะ ♡")
    else:
        await ctx.send("˚⋆ ยังไม่มีเพลงเล่นอยู่นะ ♡อยู่")


@bot.command(name="resume", aliases=["เล่นต่อ"])
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("𐙚˚⋆ เล่นต่อแล้วนะ ♡")
    else:
        await ctx.send("˚⋆ ไม่มีเพลงที่หยุดอยู่เลย ♡")


@bot.command(name="skip", aliases=["s", "ข้าม"])
async def skip(ctx):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send("˚⋆ ยังไม่มีเพลงเล่นอยู่นะ ♡อยู่")

    guild_id = ctx.guild.id
    current = now_playing.get(guild_id, {})
    requester = current.get("requester", "")

    if ctx.author.display_name == requester:
        skip_votes.pop(guild_id, None)
        vc.stop()
        return await ctx.send("𐙚˚⋆ ข้ามเพลงแล้วนะ ♡")

    human_members = [m for m in vc.channel.members if not m.bot]
    needed = max(VOTE_SKIP_THRESHOLD, len(human_members) // 2 + 1)

    if len(human_members) < VOTE_SKIP_THRESHOLD:
        skip_votes.pop(guild_id, None)
        vc.stop()
        return await ctx.send("𐙚˚⋆ ข้ามเพลงแล้วนะ ♡")

    votes = skip_votes.setdefault(guild_id, set())
    votes.add(ctx.author.id)

    if len(votes) >= needed:
        skip_votes.pop(guild_id, None)
        vc.stop()
        await ctx.send(f"⏭ Vote skip ผ่าน ({len(votes)}/{needed}) — ข้ามเพลงแล้ว!")
    else:
        await ctx.send(f"𐙚˚⋆ โหวตข้ามเพลง **{len(votes)}/{needed}** โหวต")


async def _disable_now_playing_msg(guild_id: int, footer: str = "⋆𐙚˚ หยุดแล้วนะ ♡"):
    """เดิมใช้ disable buttons — เปลี่ยนเป็นลบทิ้งเลย"""
    await _delete_now_playing_msg(guild_id)


@bot.command(name="stop", aliases=["หยุดเลย"])
async def stop(ctx):
    queues[ctx.guild.id] = deque()
    now_playing.pop(ctx.guild.id, None)
    skip_votes.pop(ctx.guild.id, None)
    if ctx.voice_client:
        ctx.voice_client.stop()
    await _delete_now_playing_msg(ctx.guild.id)
    _reset_idle_timer(ctx)
    await ctx.send("𐙚˚⋆ หยุดเล่นและล้าง Queue แล้วนะ ♡")


@bot.command(name="queue", aliases=["q", "คิว"])
async def show_queue(ctx):
    queue = get_queue(ctx.guild.id)
    embed = discord.Embed(title="⋆˚𐙚 Queue เพลง 𐙚˚⋆", color=0x5865F2)

    if ctx.guild.id in now_playing:
        s = now_playing[ctx.guild.id]
        embed.add_field(name="𐙚 กำลังเล่น",
                        value=f"**{s['title']}** ({fmt_duration(s.get('duration'))}) — {s.get('requester','?')}",
                        inline=False)
    if not queue:
        embed.add_field(name="˚⋆ ยังไม่มีเพลงเลยนะ ⋆˚", value="ลอง `!play` เพื่อเพิ่มเพลงได้เลย ♡", inline=False)
    else:
        lines = [f"`{i}.` **{s['title']}** ({fmt_duration(s.get('duration'))}) — {s.get('requester','?')}"
                 for i, s in enumerate(list(queue)[:10], 1)]
        if len(queue) > 10:
            lines.append(f"...และอีก {len(queue)-10} เพลง")
        total_dur = queue_total_duration(queue)
        embed.add_field(
            name=f"รายการถัดไป ({len(queue)} เพลง • รวม {total_dur})",
            value="\n".join(lines),
            inline=False,
        )
    await ctx.send(embed=embed)


@bot.command(name="nowplaying", aliases=["np", "กำลังเล่น"])
async def now_playing_cmd(ctx):
    if ctx.guild.id not in now_playing:
        return await ctx.send("˚⋆ ยังไม่มีเพลงเล่นอยู่นะ ♡อยู่")
    await ctx.send(
        embed=build_now_playing_embed(now_playing[ctx.guild.id], get_queue(ctx.guild.id)),
        view=PlayerView(ctx),
    )


@bot.command(name="clear", aliases=["ล้างคิว"])
async def clear_queue(ctx):
    queues[ctx.guild.id] = deque()
    await ctx.send("𐙚˚⋆ ล้าง Queue แล้วนะ ♡")


@bot.command(name="leave", aliases=["ออก", "dc"])
async def leave(ctx):
    if ctx.voice_client:
        _cancel_idle_timer(ctx.guild.id)
        await _delete_now_playing_msg(ctx.guild.id)
        queues.pop(ctx.guild.id, None)
        now_playing.pop(ctx.guild.id, None)
        skip_votes.pop(ctx.guild.id, None)
        await ctx.voice_client.disconnect()
        await ctx.send("𐙚˚⋆ บ๊ายบาย ♡")
    else:
        await ctx.send("˚⋆ บอทไม่ได้อยู่ใน Voice Channel นะ ♡")


@bot.command(name="volume", aliases=["vol", "เสียง"])
async def volume(ctx, vol: int):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        return await ctx.send("˚⋆ ยังไม่มีเพลงเล่นอยู่นะ ♡อยู่")
    if not 0 <= vol <= 100:
        return await ctx.send("˚⋆ ใส่ตัวเลข 0-100 นะ ♡")
    if hasattr(ctx.voice_client.source, "volume"):
        ctx.voice_client.source.volume = vol / 100
        await ctx.send(f"𐙚˚⋆ ปรับเสียงเป็น **{vol}%** แล้วนะ ♡")
    else:
        await ctx.send("˚⋆ ปรับเสียงในโหมดนี้ไม่ได้นะ ♡")


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