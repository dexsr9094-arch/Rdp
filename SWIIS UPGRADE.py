import os, sys, io, json, time, random, asyncio, datetime, logging, re
from collections import defaultdict
from datetime import timedelta

import discord, aiohttp
from discord.ext import commands
from discord import Poll

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("zex")

# =====================================================================
# TOKENS — paste your tokens here, one string per account
# =====================================================================
TOKENS = [
    "PASTE_TOKEN_1_HERE",
    "PASTE_TOKEN_2_HERE",
    "PASTE_TOKEN_3_HERE",
]

# =====================================================================
# CONFIG
# =====================================================================
PREFIX = "!"
PERMANENT_OWNER = 1530575319151546370
BOT_OWNER_ID = 1530575319151546370
ACCESS_FILE = ""
DEFAULT_COOLDOWN = 3

if not TOKENS or any(t.startswith("PASTE_TOKEN") for t in TOKENS):
    raise SystemExit("edit the TOKENS list at the top of the file before running")

# =====================================================================
# DATA — extend with your full originals
# =====================================================================
PROTECTED_NAMES = {"rahul"}
colourful_hearts = ["❤️","🧡","💛","💚","💙","💜","🩷","🩵","🤍","🖤","🩶"]

custom_msgs  = [f"{{text}} spam #{i}" for i in range(1, 21)]
custom_msgs2 = [f"{{text}} (❤️)\n" * 20]
custom_msgs3 = [f"『 papa 』{i}" for i in range(1, 16)]
english_msgs = ["hello","hi","o/","gg","lol"] * 3
warn_messages = ["warned","⚠️ warn","caught a warning"]

nc_messages  = ["slave"]
nc_messages2 = ["side pls gulam ke tatte"]
nc_messages3 = ["hijde","kamzor","randi"]

nc_emojis  = ["🌱","☘","🌿"]
nc_emojis2 = ["❤️","🧡","💛","💚","💙","💜","🩷","🩵","🤍","🖤","🩶"]
nc_emojis3 = ["🌑","🌓","🌔","🌕","🌒","🌖","🌗","🌘","🌚"]
nc_emojis69 = ["🌙","🕷","🌌","🦴"]

food_msgs     = ["🍕","🍣","🌮","🍜"]
font_msgs     = ["txt1","txt2","txt3"]
slide_messages  = ["slide1","slide2","slide3"]
target_messages = ["target1","target2","target3"]
dm_messages   = ["hi","hello","yo"]


# =====================================================================
# HELPERS
# =====================================================================
_URL_RE = re.compile(r"(https?://\S+)")
_FANCY_MAP = {
    "A":"𝐀","B":"𝐁","C":"𝐂","D":"𝐃","E":"𝐄","F":"𝐅","G":"𝐆","H":"𝐇","I":"𝐈",
    "J":"𝐉","K":"𝐊","L":"𝐋","M":"𝐌","N":"𝐍","O":"𝐎","P":"𝐏","Q":"𝐐","R":"𝐑",
    "S":"𝐒","T":"𝐓","U":"𝐔","V":"𝐕","W":"𝐖","X":"𝐗","Y":"𝐘","Z":"𝐙",
    "a":"ᴀ","b":"ʙ","c":"ᴄ","d":"ᴅ","e":"ᴇ","f":"ғ","g":"ɢ","h":"ʜ","i":"ɪ",
    "j":"ᴊ","k":"ᴋ","l":"ʟ","m":"ᴍ","n":"ɴ","o":"ᴏ","p":"ᴘ","q":"ǫ","r":"ʀ",
    "s":"s","t":"ᴛ","u":"ᴜ","v":"ᴠ","w":"ᴡ","x":"x","y":"ʏ","z":"ᴢ",
}
def _fancy_plain(s): return "".join(_FANCY_MAP.get(c, c) for c in s)
def fancy(text):
    if not text: return text
    out, last = [], 0
    for m in _URL_RE.finditer(text):
        out.append(_fancy_plain(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_fancy_plain(text[last:]))
    return "".join(out)

def is_protected(text):
    if not text: return False
    t = text.lower()
    return any(n in t for n in PROTECTED_NAMES)

async def safe_send(channel, content: str):
    content = fancy(str(content))[:2000]
    for _ in range(12):
        try:
            return await channel.send(content)
        except discord.HTTPException as e:
            if e.status == 429:
                await asyncio.sleep(getattr(e, "retry_after", 2.0) + random.uniform(0.05, 0.4))
                continue
            raise
        except Exception:
            await asyncio.sleep(0.8)
    raise RuntimeError("safe_send exhausted")

async def safe_edit(obj, **kw):
    for _ in range(12):
        try:
            return await obj.edit(**kw)
        except discord.HTTPException as e:
            if e.status == 429:
                await asyncio.sleep(getattr(e, "retry_after", 1.5) + random.uniform(0.02, 0.3))
                continue
            raise
        except Exception:
            await asyncio.sleep(0.5)
    raise RuntimeError("safe_edit exhausted")

def _stop(table: dict, key):
    t = table.get(key)
    if t and not t.done(): t.cancel()
    table.pop(key, None)


# =====================================================================
# SHARED ACCESS + COOLDOWNS
# =====================================================================
allowed_ids: set[int] = set()
cooldowns: dict[int, dict[str, float]] = defaultdict(dict)
command_cooldowns = {
    "spam":5,"engspam":5,"customspam":5,"customspam2":5,"gifspam":5,
    "gcnc":3,"gcnc2":3,"gcnc3":3,"gcnc4":3,"slide":4,"warn":3,
    "dmspam":8,"pollspam":6,"onlinespam":5,"stopall":3,"access":2,"unaccess":2,
}

def load_allowed():
    if os.path.exists(ACCESS_FILE):
        try:
            with open(ACCESS_FILE) as f: return set(json.load(f))
        except Exception as e: log.warning("access load: %s", e)
    return {BOT_OWNER_ID, PERMANENT_OWNER}

def save_allowed():
    try:
        with open(ACCESS_FILE, "w") as f: json.dump(list(allowed_ids), f, indent=2)
    except Exception as e: log.warning("access save: %s", e)

def check_cooldown(ctx):
    if ctx.author.id in (BOT_OWNER_ID, PERMANENT_OWNER): return True
    cmd = ctx.command.name
    now = time.time()
    last = cooldowns[ctx.author.id].get(cmd, 0)
    cd = command_cooldowns.get(cmd, DEFAULT_COOLDOWN)
    if now - last < cd:
        return round(cd - (now - last), 1)
    cooldowns[ctx.author.id][cmd] = now
    return True

def cooldown():
    async def pred(ctx):
        r = check_cooldown(ctx)
        if r is not True:
            await ctx.send(f"⏳ {r}s remaining", delete_after=3)
            return False
        return True
    return commands.check(pred)

def is_authorized():
    async def pred(ctx):
        return ctx.author.id in allowed_ids
    return commands.check(pred)


# =====================================================================
# BOT INSTANCE
# =====================================================================
class BotInstance:
    def __init__(self, token: str, index: int):
        self.token = token
        self.index = index
        self.bot = commands.Bot(command_prefix=PREFIX, self_bot=True, help_command=None)
        self.ready = False
        self.user_id = None
        self.username = None
        self.prefix = PREFIX
        self.start_time = datetime.datetime.now()

        self.spam_tasks: dict = {};       self.spam_delay = 0.4
        self.spam_tasks2: dict = {};      self.spam_delay2 = 0.4
        self.kentospam_tasks: dict = {};  self.kentospam_delay = 0.4
        self.custom_spam_tasks: dict = {};self.custom_spam_delay = 0.4
        self.eng_spam_tasks: dict = {};   self.eng_spam_delay = 0.4
        self.warn_tasks: dict = {};       self.warn_delay = 0.8
        self.ghost_tasks: dict = {};      self.ghost_speed = 1.0
        self.slide_tasks: dict = {};      self.last_replied: dict = {}
        self.target_tasks: dict = {};     self.target_last_replied: dict = {}
        self.dm_spam_tasks: dict = {}
        self.poll_spam_tasks: dict = {};  self.poll_spam_delay = 0.4
        self.domain_tasks: dict = {}
        self.gcnc_tasks: dict = {}
        self.hindinc_tasks: dict = {}
        self.longnc_tasks: dict = {}
        self.server_name_tasks: dict = {}
        self.foodnc_tasks: dict = {}
        self.fontnc_tasks: dict = {}
        self.sniped_messages: dict = {}

        self.autofiller_char = ""; self.autofiller_enabled = False
        self.copycat_user = None;  self.copycat_enabled = False
        self.permecho_user = None; self.permecho_enabled = False
        self.global_autoreact: dict = {}
        self.user_autoreact: dict = {}
        self.self_autoreact: dict = {}
        self.stealth_mode = True

        self.pfp_slots: dict = {}
        self.pfp_loop_task = None
        self.pfp_loop_active = False
        self.pfp_delay = 3.0
        self.pic_state = {"slots": {}, "delay": 1.0, "active": False, "current_task": None}

        build_commands(self)
        self._register_events()

    def _register_events(self):
        bot = self.bot
        inst = self

        @bot.event
        async def on_ready():
            inst.ready = True
            inst.user_id = bot.user.id
            inst.username = str(bot.user)
            log.info("[bot%d] online as %s (id=%s)", inst.index, bot.user, bot.user.id)

        @bot.event
        async def on_message(message: discord.Message):
            if message.author.bot: return

            if message.content.startswith(inst.prefix) and message.author.id not in allowed_ids:
                try:
                    r = await message.channel.send(f"{message.author.mention} 𝐓ᴜ 𝐊ꪮ𝐍 𝐇ꪖ𝐈 𝐁ᴋ𝐂")
                    await r.add_reaction("🤣")
                    await asyncio.sleep(2)
                    await message.channel.send("𝗕ᴀᴀ𝗣 𝐊ᴀ 𝗕ᴏ𝐓 𝐔ꜱ𝐄 𝗞ᴀʀᴇɢ𝗔 𝐆ᴜʟ𝐀ᴍ?!🌌")
                except Exception: pass
                return

            if inst.copycat_enabled and inst.copycat_user and message.author.id == inst.copycat_user:
                try: await message.channel.send(message.content)
                except Exception: pass

            if inst.permecho_enabled and inst.permecho_user and message.author.id == inst.permecho_user:
                try: await message.channel.send(message.content)
                except Exception: pass

            mirrored = False
            if (message.author.id in allowed_ids and message.author.id != BOT_OWNER_ID
                    and message.content.startswith(inst.prefix)):
                try:
                    await message.channel.send(message.content)
                    await message.delete()
                    mirrored = True
                except Exception: pass

            cid, uid = message.channel.id, message.author.id
            try:
                if cid in inst.global_autoreact:
                    await message.add_reaction(inst.global_autoreact[cid])
                elif (cid, uid) in inst.user_autoreact:
                    await message.add_reaction(inst.user_autoreact[(cid, uid)])
                elif uid == bot.user.id and cid in inst.self_autoreact:
                    await message.add_reaction(inst.self_autoreact[cid])
            except Exception: pass

            if mirrored: return
            await bot.process_commands(message)

        @bot.event
        async def on_command(ctx):
            if inst.stealth_mode:
                try: await ctx.message.delete()
                except Exception: pass

        @bot.event
        async def on_message_delete(message: discord.Message):
            if message.author.bot: return
            bucket = inst.sniped_messages.setdefault(message.channel.id, [])
            bucket.insert(0, {
                "content": message.content,
                "author": str(message.author),
                "author_id": message.author.id,
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
            })
            del bucket[15:]

    async def start_longspam(self, channel, text):
        cid = channel.id
        _stop(self.spam_tasks, cid)
        async def run():
            idx = 0
            while True:
                try:
                    c = custom_msgs[idx % len(custom_msgs)].replace("{text}", text).replace("@", "＠")
                    idx += 1
                    await safe_send(channel, c)
                except asyncio.CancelledError: break
                except Exception as e: log.debug("longspam: %s", e)
                await asyncio.sleep(self.spam_delay)
        self.spam_tasks[cid] = asyncio.create_task(run())

    async def start_heartspam(self, channel, text):
        cid = channel.id
        _stop(self.spam_tasks2, cid)
        async def run():
            idx = 0
            while True:
                try:
                    c = custom_msgs2[idx % len(custom_msgs2)].replace("{text}", text).replace("@", "＠")
                    idx += 1
                    await safe_send(channel, c)
                except asyncio.CancelledError: break
                except Exception as e: log.debug("heartspam: %s", e)
                await asyncio.sleep(self.spam_delay2)
        self.spam_tasks2[cid] = asyncio.create_task(run())

    async def start_kentospam(self, channel, text):
        cid = channel.id
        _stop(self.kentospam_tasks, cid)
        async def run():
            idx = 0
            while True:
                try:
                    c = custom_msgs3[idx % len(custom_msgs3)].replace("papa", text).replace("@", "＠")
                    idx += 1
                    await safe_send(channel, c)
                except asyncio.CancelledError: break
                except Exception as e: log.debug("kento: %s", e)
                await asyncio.sleep(self.kentospam_delay)
        self.kentospam_tasks[cid] = asyncio.create_task(run())

    async def start_customspam(self, channel, text):
        cid = channel.id
        _stop(self.custom_spam_tasks, cid)
        async def run():
            while True:
                try:
                    heart = random.choice(colourful_hearts)
                    await safe_send(channel, f"{text} ({heart})".replace("@", "＠"))
                except asyncio.CancelledError: break
                except Exception as e: log.debug("customspam: %s", e)
                await asyncio.sleep(self.custom_spam_delay)
        self.custom_spam_tasks[cid] = asyncio.create_task(run())

    async def start_fuga(self, channel, text=""):
        cid = channel.id
        _stop(self.eng_spam_tasks, cid)
        async def run():
            idx = cnt = 0
            while True:
                try:
                    m = english_msgs[idx % len(english_msgs)]
                    body = f"{text} {m}" if text else m
                    cnt += 1; idx += 1
                    await safe_send(channel, f"{body}\n > {cnt:03d}")
                except asyncio.CancelledError: break
                except Exception as e: log.debug("fuga: %s", e)
                await asyncio.sleep(self.eng_spam_delay)
        self.eng_spam_tasks[cid] = asyncio.create_task(run())

    async def start_warn(self, channel, user, amount=10):
        if is_protected(str(user)): return
        key = f"{channel.id}_{user.id}"
        _stop(self.warn_tasks, key)
        async def run():
            try:
                for _ in range(max(1, min(amount, 50))):
                    await safe_send(channel, f"{user.mention} {random.choice(warn_messages)}".replace("@","＠"))
                    await asyncio.sleep(self.warn_delay)
            except asyncio.CancelledError: pass
            finally: self.warn_tasks.pop(key, None)
        self.warn_tasks[key] = asyncio.create_task(run())

    async def start_pollspam(self, channel, question="Poll"):
        cid = channel.id
        _stop(self.poll_spam_tasks, cid)
        async def run():
            n = 0
            while True:
                try:
                    p = Poll(question=f"{question} #{n}", duration=timedelta(hours=1), multiple=False)
                    p.add_answer(text="yes"); p.add_answer(text="no")
                    n += 1
                    await channel.send(poll=p)
                except asyncio.CancelledError: break
                except Exception as e: log.debug("pollspam: %s", e)
                await asyncio.sleep(self.poll_spam_delay)
        self.poll_spam_tasks[cid] = asyncio.create_task(run())

    async def broadcast_invoke(self, cmd: str, channel, args: str, author):
        c = cmd.lower()
        if c == "longspam":     await self.start_longspam(channel, args)
        elif c == "heartspam":  await self.start_heartspam(channel, args)
        elif c == "kentospam":  await self.start_kentospam(channel, args)
        elif c == "customspam": await self.start_customspam(channel, args)
        elif c == "fuga":       await self.start_fuga(channel, args)
        elif c == "pollspam":   await self.start_pollspam(channel, args or "Poll")
        elif c == "warn":
            parts = args.split(maxsplit=1)
            if not parts: return
            try: uid = int(parts[0].strip("<@!>"))
            except ValueError: return
            amt = int(parts[1]) if len(parts) > 1 else 10
            try: u = await self.bot.fetch_user(uid)
            except Exception: return
            await self.start_warn(channel, u, amt)
        else:
            log.warning("broadcast: unknown cmd %s", cmd)

    async def stop_all(self):
        tables = (
            self.spam_tasks, self.spam_tasks2, self.kentospam_tasks,
            self.custom_spam_tasks, self.eng_spam_tasks, self.warn_tasks,
            self.ghost_tasks, self.slide_tasks, self.target_tasks,
            self.dm_spam_tasks, self.poll_spam_tasks, self.domain_tasks,
            self.gcnc_tasks, self.hindinc_tasks, self.longnc_tasks,
            self.server_name_tasks, self.foodnc_tasks, self.fontnc_tasks,
        )
        n = 0
        for t in tables:
            for k, task in list(t.items()):
                if task and not task.done(): task.cancel(); n += 1
                t.pop(k, None)
        try:
            self.pic_state["active"] = False
            if self.pic_state.get("current_task") and not self.pic_state["current_task"].done():
                self.pic_state["current_task"].cancel(); n += 1
        except Exception: pass
        return n


# =====================================================================
# COMMANDS (registered per instance)
# =====================================================================
def build_commands(inst: BotInstance):
    bot = inst.bot

    @bot.command(name="access")
    @is_authorized()
    async def _access(ctx, user: discord.User = None):
        if ctx.author.id not in (BOT_OWNER_ID, PERMANENT_OWNER):
            return await ctx.send("❌ owner only")
        if user is None: return await ctx.send(f"⚠️ `{inst.prefix}access @user`")
        if user.id in allowed_ids: return await ctx.send(f"⚠️ {user.display_name} already has access")
        allowed_ids.add(user.id); save_allowed()
        await ctx.send(f"✅ granted to {user.display_name}")

    @bot.command(name="unaccess")
    async def _unaccess(ctx, *, raw: str):
        if ctx.author.id != BOT_OWNER_ID: return await ctx.send("❌ owner only")
        u = None
        if ctx.message.mentions: u = ctx.message.mentions[0]
        else:
            try: u = await bot.fetch_user(int(raw.strip()))
            except Exception: pass
        if not u: return await ctx.send("❌ user not found")
        if u.id == PERMANENT_OWNER: return await ctx.send("❌ can't remove permanent owner")
        if u.id not in allowed_ids: return await ctx.send(f"{u.mention} has no access")
        allowed_ids.discard(u.id); save_allowed()
        await ctx.send(f"access removed from {u}")

    @bot.command(name="bots")
    @is_authorized()
    async def _bots(ctx):
        lines = ["**Fleet:**"]
        for o in MANAGER.instances:
            status = "🟢" if o.ready else "🔴"
            lines.append(f"{status} bot{o.index}: {o.username or '—'} `{o.user_id or '—'}`")
        await ctx.send("\n".join(lines))

    @bot.command(name="broadcast", aliases=["bc"])
    @is_authorized()
    @cooldown()
    async def _broadcast(ctx, cmd: str, *, args: str = ""):
        cid = ctx.channel.id
        fired = 0
        for o in MANAGER.instances:
            if not o.ready: continue
            ch = o.bot.get_channel(cid)
            if ch is None:
                try: ch = await o.bot.fetch_channel(cid)
                except Exception: continue
            try:
                await o.broadcast_invoke(cmd, ch, args, ctx.author); fired += 1
            except Exception as e:
                log.warning("bc bot%d: %s", o.index, e)
        await ctx.send(f"📡 `{cmd}` → {fired} bot(s)")

    @bot.command(name="changeprefix")
    @is_authorized()
    @cooldown()
    async def _changeprefix(ctx, *, new: str):
        inst.prefix = new.strip(); bot.command_prefix = inst.prefix
        await ctx.send(f"prefix → `{inst.prefix}`")

    @bot.command(name="uptime")
    @is_authorized()
    async def _uptime(ctx):
        d = datetime.datetime.now() - inst.start_time
        h, rem = divmod(d.seconds, 3600); m, s = divmod(rem, 60)
        await ctx.send(f"uptime: **{d.days}d {h}h {m}m {s}s**")

    @bot.command(name="ping")
    @is_authorized()
    async def _ping(ctx):
        await ctx.send(f"pong `{round(bot.latency*1000)}ms`")

    @bot.command(name="status")
    @is_authorized()
    async def _status(ctx):
        await ctx.send(
            f"**bot{inst.index}** {inst.username}\n"
            f"stealth: `{'on' if inst.stealth_mode else 'off'}`\n"
            f"uptime: `{(datetime.datetime.now()-inst.start_time).seconds}s`"
        )

    @bot.command(name="stealth")
    @is_authorized()
    async def _stealth(ctx, mode: str = None):
        if mode is None: return await ctx.send(f"stealth: `{'on' if inst.stealth_mode else 'off'}`")
        inst.stealth_mode = mode.lower() in ("on","true","1","enable")
        await ctx.send(f"stealth → `{'on' if inst.stealth_mode else 'off'}`")

    @bot.command(name="stopall")
    @is_authorized()
    @cooldown()
    async def _stopall(ctx):
        n = await inst.stop_all()
        await ctx.send(f"🛑 stopped {n} tasks")

    @bot.command(name="stopallglobal", aliases=["sg"])
    @is_authorized()
    async def _sg(ctx):
        total = 0
        for o in MANAGER.instances:
            try: total += await o.stop_all()
            except Exception: pass
        await ctx.send(f"🛑 fleet: stopped {total} tasks")

    @bot.command(name="shutdown")
    @is_authorized()
    async def _shutdown(ctx):
        await ctx.send("shutting down this bot…"); await bot.close()

    @bot.command(name="shutdownall")
    @is_authorized()
    async def _shutdownall(ctx):
        await ctx.send("shutting down fleet…")
        for o in MANAGER.instances:
            try: await o.bot.close()
            except Exception: pass

    @bot.command(name="restart")
    @is_authorized()
    async def _restart(ctx):
        await ctx.send("♻️ restarting process…")
        for o in MANAGER.instances:
            try: await o.bot.close()
            except Exception: pass
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @bot.command(name="Longspam")
    @is_authorized()
    @cooldown()
    async def _longspam(ctx, *, text: str):
        await inst.start_longspam(ctx.channel, text); await ctx.message.add_reaction("✅")

    @bot.command(name="Longspamspeed")
    @is_authorized()
    async def _longspamspeed(ctx, d: float):
        inst.spam_delay = max(0.0, d); await ctx.send(f"delay → {inst.spam_delay}s")

    @bot.command(name="Longspamstop")
    @is_authorized()
    async def _longspamstop(ctx):
        _stop(inst.spam_tasks, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="Heartspam")
    @is_authorized()
    @cooldown()
    async def _heartspam(ctx, *, text: str):
        await inst.start_heartspam(ctx.channel, text); await ctx.message.add_reaction("✅")

    @bot.command(name="Heartspamspeed")
    @is_authorized()
    async def _heartspamspeed(ctx, d: float):
        inst.spam_delay2 = max(0.1, d); await ctx.send(f"delay → {inst.spam_delay2}s")

    @bot.command(name="Heartspamstop")
    @is_authorized()
    async def _heartspamstop(ctx):
        _stop(inst.spam_tasks2, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="kentospam")
    @is_authorized()
    @cooldown()
    async def _kentospam(ctx, *, text: str):
        await inst.start_kentospam(ctx.channel, text); await ctx.message.add_reaction("✅")

    @bot.command(name="stopkentospam")
    @is_authorized()
    async def _stopkento(ctx):
        _stop(inst.kentospam_tasks, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="customspam")
    @is_authorized()
    @cooldown()
    async def _customspam(ctx, *, text: str):
        await inst.start_customspam(ctx.channel, text); await ctx.message.add_reaction("✅")

    @bot.command(name="customspamspeed")
    @is_authorized()
    async def _cspd(ctx, d: float):
        inst.custom_spam_delay = max(0.0, d); await ctx.send(f"delay → {inst.custom_spam_delay}s")

    @bot.command(name="customspamstop")
    @is_authorized()
    async def _cstop(ctx):
        _stop(inst.custom_spam_tasks, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="Fuga")
    @is_authorized()
    async def _fuga(ctx, *, text: str = None):
        if ctx.channel.id in inst.eng_spam_tasks and not inst.eng_spam_tasks[ctx.channel.id].done():
            _stop(inst.eng_spam_tasks, ctx.channel.id); return await ctx.send("🛑 fuga stopped")
        await inst.start_fuga(ctx.channel, text or ""); await ctx.message.add_reaction("✅")

    @bot.command(name="Fugaspeed")
    @is_authorized()
    async def _fugaspeed(ctx, d: float):
        inst.eng_spam_delay = max(0.3, d); await ctx.send(f"delay → {inst.eng_spam_delay}s")

    @bot.command(name="StopFuga")
    @is_authorized()
    async def _stopfuga(ctx):
        _stop(inst.eng_spam_tasks, ctx.channel.id); await ctx.send("🔴 fuga stopped")

    @bot.command(name="warn")
    @is_authorized()
    @cooldown()
    async def _warn(ctx, user: discord.User = None, amount: int = 10):
        if user is None: return await ctx.send("⚠️ `!warn @user [amount]`")
        if is_protected(user.display_name): return await ctx.send("**❌ PROTECTED NAME DETECTED**")
        await inst.start_warn(ctx.channel, user, amount)

    @bot.command(name="warnspeed")
    @is_authorized()
    async def _warnspeed(ctx, d: float):
        inst.warn_delay = max(0.3, d); await ctx.send(f"delay → {inst.warn_delay}s")

    @bot.command(name="stopwarn")
    @is_authorized()
    async def _stopwarn(ctx):
        n = 0
        for k, t in list(inst.warn_tasks.items()):
            if t and not t.done(): t.cancel(); n += 1
            inst.warn_tasks.pop(k, None)
        await ctx.send(f"🛑 stopped {n} warn tasks")

    @bot.command(name="dmspam")
    @is_authorized()
    @cooldown()
    async def _dmspam(ctx, user: discord.User):
        _stop(inst.dm_spam_tasks, user.id)
        try: dm = await user.create_dm()
        except Exception: return await ctx.send("cannot DM")
        async def run():
            idx = 0
            while True:
                try:
                    await safe_send(dm, dm_messages[idx % len(dm_messages)]); idx += 1
                except asyncio.CancelledError: break
                except Exception as e: log.debug("dmspam: %s", e)
                await asyncio.sleep(0.4)
        inst.dm_spam_tasks[user.id] = asyncio.create_task(run())
        await ctx.message.add_reaction("✅")

    @bot.command(name="dmstop")
    @is_authorized()
    async def _dmstop(ctx, user: discord.User):
        _stop(inst.dm_spam_tasks, user.id); await ctx.message.add_reaction("✅")

    @bot.command(name="pollspam")
    @is_authorized()
    @cooldown()
    async def _pollspam(ctx, *, q: str = "Poll"):
        await inst.start_pollspam(ctx.channel, q); await ctx.message.add_reaction("✅")

    @bot.command(name="pollspamspeed")
    @is_authorized()
    async def _pollspd(ctx, d: float):
        inst.poll_spam_delay = max(0.5, d); await ctx.send(f"delay → {inst.poll_spam_delay}s")

    @bot.command(name="stoppollspam")
    @is_authorized()
    async def _pollstop(ctx):
        _stop(inst.poll_spam_tasks, ctx.channel.id); await ctx.send("🛑 poll spam stopped")

    async def _nc_loop(target, base, msgs, emojis, table, key, extra=""):
        idx = 0
        try:
            while True:
                try:
                    m = msgs[idx % len(msgs)]
                    e = random.choice(emojis) if emojis else ""
                    idx += 1
                    await safe_edit(target, name=f"{base} {extra} {m} {e}".strip())
                except asyncio.CancelledError: break
                except Exception as e: log.debug("nc: %s", e)
                await asyncio.sleep(0.4)
        finally:
            table.pop(key, None)

    def _start_nc(table, key, target, base, msgs, emojis, extra=""):
        _stop(table, key)
        table[key] = asyncio.create_task(_nc_loop(target, base, msgs, emojis, table, key, extra))

    @bot.command(name="gcnc")
    @is_authorized()
    @cooldown()
    async def _gcnc(ctx, *, msg: str):
        if not isinstance(ctx.channel, discord.GroupChannel):
            return await ctx.message.add_reaction("❌")
        _start_nc(inst.gcnc_tasks, ctx.channel.id, ctx.channel, msg, nc_messages2, nc_emojis2, "-")
        await ctx.message.add_reaction("✅")

    @bot.command(name="gcncstop")
    @is_authorized()
    async def _gcncstop(ctx):
        _stop(inst.gcnc_tasks, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="hindinc")
    @is_authorized()
    @cooldown()
    async def _hindinc(ctx, *, msg: str):
        if not isinstance(ctx.channel, discord.GroupChannel):
            return await ctx.message.add_reaction("❌")
        _start_nc(inst.hindinc_tasks, ctx.channel.id, ctx.channel, msg, nc_messages3, nc_emojis3, "-")
        await ctx.message.add_reaction("✅")

    @bot.command(name="hindincstop")
    @is_authorized()
    async def _hindincstop(ctx):
        _stop(inst.hindinc_tasks, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="longnc")
    @is_authorized()
    @cooldown()
    async def _longnc(ctx, *, msg: str):
        if not isinstance(ctx.channel, discord.GroupChannel):
            return await ctx.message.add_reaction("❌")
        _start_nc(inst.longnc_tasks, ctx.channel.id, ctx.channel, msg, nc_messages, nc_emojis)
        await ctx.message.add_reaction("✅")

    @bot.command(name="longncstop")
    @is_authorized()
    async def _longncstop(ctx):
        _stop(inst.longnc_tasks, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="servernc")
    @is_authorized()
    @cooldown()
    async def _servernc(ctx, *, msg: str):
        if not ctx.guild: return await ctx.message.add_reaction("❌")
        _start_nc(inst.server_name_tasks, ctx.guild.id, ctx.guild, msg, nc_messages, nc_emojis, "-")
        await ctx.message.add_reaction("✅")

    @bot.command(name="serverncstop")
    @is_authorized()
    async def _serverncstop(ctx):
        if not ctx.guild: return await ctx.message.add_reaction("❌")
        _stop(inst.server_name_tasks, ctx.guild.id); await ctx.message.add_reaction("✅")

    @bot.command(name="foodnc")
    @is_authorized()
    async def _foodnc(ctx, *, msg: str = ""):
        if not isinstance(ctx.channel, discord.GroupChannel):
            return await ctx.message.add_reaction("❌")
        _start_nc(inst.foodnc_tasks, ctx.channel.id, ctx.channel, msg, food_msgs, [""], "-")
        await ctx.message.add_reaction("✅")

    @bot.command(name="foodncstop")
    @is_authorized()
    async def _foodncstop(ctx):
        _stop(inst.foodnc_tasks, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="fontnc")
    @is_authorized()
    async def _fontnc(ctx, *, msg: str = ""):
        if not isinstance(ctx.channel, discord.GroupChannel):
            return await ctx.message.add_reaction("❌")
        _start_nc(inst.fontnc_tasks, ctx.channel.id, ctx.channel, msg, font_msgs, [""], "-")
        await ctx.message.add_reaction("✅")

    @bot.command(name="fontncstop")
    @is_authorized()
    async def _fontncstop(ctx):
        _stop(inst.fontnc_tasks, ctx.channel.id); await ctx.message.add_reaction("✅")

    @bot.command(name="autoreact")
    @is_authorized()
    async def _autoreact(ctx, emoji: str):
        inst.global_autoreact[ctx.channel.id] = emoji
        await ctx.send(f"✅ autoreact {emoji}")

    @bot.command(name="stopreact")
    @is_authorized()
    async def _stopreact(ctx):
        inst.global_autoreact.pop(ctx.channel.id, None)
        await ctx.send("🛑 autoreact disabled")

    @bot.command(name="userreact")
    @is_authorized()
    async def _userreact(ctx, user: discord.User, emoji: str):
        inst.user_autoreact[(ctx.channel.id, user.id)] = emoji
        await ctx.send(f"✅ reacting to {user.display_name} with {emoji}")

    @bot.command(name="selfreact")
    @is_authorized()
    async def _selfreact(ctx, emoji: str):
        inst.self_autoreact[ctx.channel.id] = emoji
        await ctx.send(f"✅ self react {emoji}")

    async def _reply_loop(ctx, user, table, last, msgs, delay):
        key = (ctx.channel.id, user.id)
        _stop(table, key); last[key] = set()
        async def run():
            try:
                while True:
                    def check(m):
                        return m.author.id == user.id and m.channel.id == ctx.channel.id and m.author != bot.user
                    msg = await bot.wait_for("message", check=check)
                    if msg.id in last.get(key, set()): continue
                    last[key].add(msg.id)
                    if len(last[key]) > 5000: last[key].clear()
                    try: await msg.reply(random.choice(msgs), mention_author=False)
                    except Exception: await safe_send(msg.channel, random.choice(msgs))
                    await asyncio.sleep(delay)
            except asyncio.CancelledError: pass
            except Exception as e: log.debug("reply_loop: %s", e)
        table[key] = asyncio.create_task(run())
        await ctx.message.add_reaction("✅")
        await ctx.send(f"✅ started on {user.display_name}")

    @bot.command(name="slide")
    @is_authorized()
    @cooldown()
    async def _slide(ctx, user: discord.User):
        await _reply_loop(ctx, user, inst.slide_tasks, inst.last_replied, slide_messages, 0.0)

    @bot.command(name="slidestop")
    @is_authorized()
    async def _slidestop(ctx, user: discord.User):
        _stop(inst.slide_tasks, (ctx.channel.id, user.id)); await ctx.message.add_reaction("✅")

    @bot.command(name="target")
    @is_authorized()
    @cooldown()
    async def _target(ctx, user: discord.User):
        await _reply_loop(ctx, user, inst.target_tasks, inst.target_last_replied, target_messages, 0.35)

    @bot.command(name="targetstop")
    @is_authorized()
    async def _targetstop(ctx, user: discord.User):
        _stop(inst.target_tasks, (ctx.channel.id, user.id)); await ctx.message.add_reaction("✅")

    @bot.command(name="echo")
    @is_authorized()
    @cooldown()
    async def _echo(ctx, user: discord.User = None):
        if user is None: return await ctx.send("⚠️ `!echo @user`")
        inst.copycat_user = user.id; inst.copycat_enabled = True
        await ctx.message.add_reaction("✅")
        await ctx.send(f"🔄 echo → {user.display_name}")

    @bot.command(name="stopecho")
    @is_authorized()
    @cooldown()
    async def _stopecho(ctx):
        inst.copycat_enabled = False; inst.copycat_user = None
        await ctx.message.add_reaction("✅")

    @bot.command(name="permecho")
    @is_authorized()
    @cooldown()
    async def _permecho(ctx, user: discord.User = None):
        if user is None: return await ctx.send("⚠️ `!permecho @user`")
        inst.permecho_user = user.id; inst.permecho_enabled = True
        await ctx.message.add_reaction("✅")
        await ctx.send(f"🔒 permecho → {user.display_name}")

    @bot.command(name="permechostop")
    @is_authorized()
    async def _permechostop(ctx):
        inst.permecho_enabled = False; inst.permecho_user = None
        await ctx.message.add_reaction("✅")

    @bot.command(name="ghost")
    @is_authorized()
    @cooldown()
    async def _ghost(ctx, user: discord.User, *, text: str = "ping"):
        try:
            m = await ctx.send(f"{user.mention} {text}")
            await asyncio.sleep(0.4); await m.delete()
            await ctx.message.add_reaction("✅")
        except Exception: await ctx.send("❌ failed")

    @bot.command(name="ghosttype")
    @is_authorized()
    async def _ghosttype(ctx, count: int, *, msg: str):
        key = ctx.channel.id
        _stop(inst.ghost_tasks, key)
        async def run():
            try:
                for _ in range(count):
                    m = await ctx.send(msg)
                    await asyncio.sleep(inst.ghost_speed)
                    await m.delete()
            except asyncio.CancelledError: pass
            except Exception as e: log.debug("ghosttype: %s", e)
        inst.ghost_tasks[key] = asyncio.create_task(run())
        await ctx.send(f"👻 ghosttype {count}x @ {inst.ghost_speed}s")

    @bot.command(name="stopghosttype")
    @is_authorized()
    async def _stopghosttype(ctx):
        _stop(inst.ghost_tasks, ctx.channel.id); await ctx.send("🛑 stopped")

    @bot.command(name="ghostspeed")
    @is_authorized()
    async def _ghostspeed(ctx, sec: float):
        inst.ghost_speed = max(0.2, sec)
        await ctx.send(f"ghost speed → {inst.ghost_speed}s")

    @bot.command(name="autofiller")
    @is_authorized()
    async def _autofiller(ctx, *, ch: str):
        inst.autofiller_char = ch.strip(); inst.autofiller_enabled = bool(inst.autofiller_char)
        await ctx.message.add_reaction("✅")

    @bot.command(name="removeautofiller")
    @is_authorized()
    async def _rmautofiller(ctx):
        inst.autofiller_enabled = False; inst.autofiller_char = ""
        await ctx.message.add_reaction("✅")

    @bot.command(name="say")
    @is_authorized()
    @cooldown()
    async def _say(ctx, *, text: str):
        if is_protected(text): return await ctx.send("**❌ PROTECTED NAME DETECTED**")
        body = text
        if inst.autofiller_enabled and inst.autofiller_char:
            filler = max(0, 1999 - len(text) - 1)
            if filler: body = inst.autofiller_char * filler + " " + text
        await safe_send(ctx.channel, body)

    @bot.command(name="clear")
    @is_authorized()
    @cooldown()
    async def _clear(ctx, amount: int = 100):
        n = 0
        async for m in ctx.channel.history(limit=amount):
            if m.author.id == bot.user.id:
                try: await m.delete(); n += 1; await asyncio.sleep(0.3)
                except Exception: pass
        await ctx.send(f"✅ cleared {n}", delete_after=3)

    @bot.command(name="quickdelete")
    @is_authorized()
    async def _qd(ctx, *, msg: str):
        m = await ctx.send(msg); await asyncio.sleep(2); await m.delete()

    @bot.command(name="edit")
    @is_authorized()
    async def _edit(ctx, *, text: str):
        async for m in ctx.channel.history(limit=10):
            if m.author.id == bot.user.id:
                try: await m.edit(content=text); return
                except Exception: pass
        await ctx.send("no message to edit")

    @bot.command(name="reverse")
    @is_authorized()
    async def _reverse(ctx, *, text: str):
        await ctx.send(text[::-1])

    @bot.command(name="snipe")
    @is_authorized()
    async def _snipe(ctx, amount: int = 5):
        bucket = inst.sniped_messages.get(ctx.channel.id, [])
        if not bucket: return await ctx.send("❌ nothing sniped")
        amount = max(1, min(amount, 10))
        lines = [f"**🔫 sniped ({len(bucket[:amount])})**", "━"*20]
        for i, m in enumerate(bucket[:amount], 1):
            c = (m["content"] or "*empty*")[:150]
            lines.append(f"**{i}.** `{m['author']}` · `{m['time']}`\n╰ {c}\n")
        await ctx.send("\n".join(lines))

    @bot.command(name="ship")
    @is_authorized()
    async def _ship(ctx, u1: discord.User, u2: discord.User):
        p = random.randint(0, 100)
        e = random.choice(["❤️","💖","💘","💝","💞","💕"])
        await ctx.send(f"💌 {u1.mention} × {u2.mention} → {p}% {e}")

    @bot.command(name="playing")
    @is_authorized()
    @cooldown()
    async def _playing(ctx, *, s: str):
        await bot.change_presence(activity=discord.Game(name=s)); await ctx.send(f"✅ {s}")

    @bot.command(name="watching")
    @is_authorized()
    @cooldown()
    async def _watching(ctx, *, s: str):
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=s))
        await ctx.send(f"✅ {s}")

    @bot.command(name="listening")
    @is_authorized()
    @cooldown()
    async def _listening(ctx, *, s: str):
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=s))
        await ctx.send(f"✅ {s}")

    @bot.command(name="stopactivity")
    @is_authorized()
    async def _stopactivity(ctx):
        await bot.change_presence(activity=None); await ctx.send("✅ cleared")

    @bot.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def _kick(ctx, member: discord.Member, *, reason="no reason"):
        await member.kick(reason=reason); await ctx.send(f"👢 kicked {member.mention}")

    @bot.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def _ban(ctx, member: discord.Member, *, reason="no reason"):
        await member.ban(reason=reason); await ctx.send(f"⛔ banned {member.mention}")

    @bot.command(name="clean")
    @commands.has_permissions(manage_messages=True)
    async def _clean(ctx, amount: int):
        await ctx.channel.purge(limit=amount); await ctx.send(f"🧹 cleared {amount}", delete_after=3)

    @bot.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def _lock(ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 locked")

    @bot.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def _unlock(ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🔓 unlocked")

    @bot.command(name="serverinfo")
    async def _serverinfo(ctx):
        g = ctx.guild
        if not g: return await ctx.send("not in a server")
        await ctx.send(f"📊 {g.name}\nmembers: {g.member_count}\nchannels: {len(g.channels)}")

    @bot.command(name="userinfo")
    async def _userinfo(ctx, u: discord.User):
        await ctx.send(f"👤 {u}\nid: {u.id}")

    @bot.command(name="leaveserver")
    @is_authorized()
    async def _leaveserver(ctx):
        if not ctx.guild: return await ctx.send("❌ not in a server")
        await ctx.send("👋 leaving…"); await ctx.guild.leave()

    @bot.command(name="leavegc")
    @is_authorized()
    async def _leavegc(ctx):
        if not isinstance(ctx.channel, discord.GroupChannel):
            return await ctx.send("❌ not a group chat")
        await ctx.send("👋 leaving…"); await ctx.channel.leave()

    @bot.command(name="nuke")
    @commands.has_permissions(manage_channels=True)
    async def _nuke(ctx):
        ch = ctx.channel
        new = await ch.clone()
        await ch.delete()
        await new.send("💣 nuked and recreated")

    async def _save_slot(ctx, slot):
        if not ctx.message.reference: return await ctx.send("❌ reply to an image")
        try:
            replied = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if not replied.attachments: return await ctx.send("❌ no image")
            async with aiohttp.ClientSession() as s:
                async with s.get(replied.attachments[0].url) as r:
                    if r.status != 200: return await ctx.send("❌ download failed")
                    img = await r.read()
            inst.pic_state["slots"][slot] = img
            inst.pfp_slots[slot] = img
            await ctx.send(f"✅ slot {slot} saved")
        except Exception as e: await ctx.send(f"❌ {str(e)[:200]}")

    for _i in range(1, 11):
        async def _setter(ctx, _n=_i): await _save_slot(ctx, _n)
        _setter.__name__ = f"_set{_i}"
        bot.command(name=f"set{_i}")(is_authorized()(cooldown()(_setter)))

    @bot.command(name="pfp")
    @is_authorized()
    async def _pfp(ctx):
        if not ctx.message.reference: return await ctx.send("❌ reply to an image")
        try:
            replied = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if not replied.attachments: return await ctx.send("❌ no image")
            async with aiohttp.ClientSession() as s:
                async with s.get(replied.attachments[0].url) as r:
                    img = await r.read()
            await bot.user.edit(avatar=img); await ctx.send("✅ pfp changed")
        except Exception as e: await ctx.send(f"❌ {str(e)[:200]}")

    @bot.command(name="pfploop")
    @is_authorized()
    async def _pfploop(ctx):
        if len(inst.pfp_slots) < 2: return await ctx.send("❌ save at least 2 slots")
        if inst.pfp_loop_active: return await ctx.send("⚠️ already running")
        inst.pfp_loop_active = True
        async def loop():
            keys = sorted(inst.pfp_slots.keys()); idx = 0
            while inst.pfp_loop_active:
                try:
                    await bot.user.edit(avatar=inst.pfp_slots[keys[idx % len(keys)]])
                    idx += 1; await asyncio.sleep(inst.pfp_delay)
                except Exception: await asyncio.sleep(3)
        inst.pfp_loop_task = asyncio.create_task(loop())
        await ctx.send(f"🔄 pfp loop ({len(inst.pfp_slots)} slots, {inst.pfp_delay}s)")

    @bot.command(name="stoppfp")
    @is_authorized()
    async def _stoppfp(ctx):
        inst.pfp_loop_active = False
        if inst.pfp_loop_task and not inst.pfp_loop_task.done(): inst.pfp_loop_task.cancel()
        await ctx.send("🛑 pfp loop stopped")

    @bot.command(name="pfpdelay")
    @is_authorized()
    async def _pfpdelay(ctx, sec: float):
        inst.pfp_delay = max(0.0, sec); await ctx.send(f"pfp delay → {inst.pfp_delay}s")

    @bot.command(name="startpic")
    @is_authorized()
    async def _startpic(ctx):
        if not isinstance(ctx.channel, discord.GroupChannel):
            return await ctx.send("❌ group chats only")
        if len(inst.pic_state["slots"]) < 2: return await ctx.send("❌ save 2 images first")
        inst.pic_state["active"] = True
        async def loop():
            keys = sorted(inst.pic_state["slots"].keys())
            while inst.pic_state["active"]:
                for k in keys:
                    if not inst.pic_state["active"]: break
                    try:
                        await ctx.channel.edit(icon=inst.pic_state["slots"][k])
                        await asyncio.sleep(inst.pic_state["delay"] or 1.0)
                    except Exception: await asyncio.sleep(2)
        if inst.pic_state.get("current_task") and not inst.pic_state["current_task"].done():
            inst.pic_state["current_task"].cancel()
        inst.pic_state["current_task"] = asyncio.create_task(loop())
        await ctx.send("🚀 rotation started")

    @bot.command(name="stoppic")
    @is_authorized()
    async def _stoppic(ctx):
        inst.pic_state["active"] = False
        if inst.pic_state.get("current_task") and not inst.pic_state["current_task"].done():
            inst.pic_state["current_task"].cancel()
        await ctx.send("🛑 stopped")

    @bot.command(name="delay")
    @is_authorized()
    async def _delay(ctx, sec: float):
        inst.pic_state["delay"] = max(0.0, sec)
        await ctx.send(f"pic delay → {inst.pic_state['delay']}s")

    @bot.command(name="resetall")
    @is_authorized()
    async def _resetall(ctx):
        inst.pic_state["active"] = False
        if inst.pic_state.get("current_task") and not inst.pic_state["current_task"].done():
            inst.pic_state["current_task"].cancel()
        inst.pic_state["slots"] = {}; inst.pfp_slots.clear()
        await ctx.send("🧹 cleared")

    @bot.command(name="listslots")
    @is_authorized()
    async def _listslots(ctx):
        if not inst.pfp_slots: return await ctx.send("📭 no slots")
        await ctx.send("**slots:** " + ", ".join(str(k) for k in sorted(inst.pfp_slots)))

    @bot.command(name="clearslot")
    @is_authorized()
    async def _clearslot(ctx, slot: int):
        if 1 <= slot <= 10:
            inst.pfp_slots.pop(slot, None); inst.pic_state["slots"].pop(slot, None)
            await ctx.send(f"🗑️ slot {slot} cleared")

    @bot.command(name="copypfp")
    @is_authorized()
    async def _copypfp(ctx, user: discord.User, slot: int = None):
        try:
            b = await user.display_avatar.read()
            if slot:
                if not (1 <= slot <= 10): return await ctx.send("❌ slot 1-10")
                inst.pfp_slots[slot] = b; await ctx.send(f"✅ {user.name} → slot {slot}")
            else:
                await bot.user.edit(avatar=b); await ctx.send(f"✅ {user.name} pfp set")
        except Exception as e: await ctx.send(f"❌ {e}")

    @bot.command(name="showpfp")
    @is_authorized()
    async def _showpfp(ctx, user: discord.User = None):
        user = user or ctx.author
        await ctx.send(user.display_avatar.url)

    @bot.command(name="showbanner")
    @is_authorized()
    async def _showbanner(ctx, user: discord.User = None):
        user = user or ctx.author
        try:
            u = await bot.fetch_user(user.id)
            await ctx.send(u.banner.url if u.banner else "❌ no banner")
        except Exception as e: await ctx.send(f"❌ {e}")

    @bot.command(name="spampfp")
    @is_authorized()
    async def _spampfp(ctx, count: int = 5):
        if not inst.pfp_slots: return await ctx.send("❌ no pfps saved")
        count = max(1, min(count, 15))
        for _ in range(count):
            try:
                k = random.choice(list(inst.pfp_slots.keys()))
                f = discord.File(fp=io.BytesIO(inst.pfp_slots[k]), filename=f"pfp_{k}.png")
                await ctx.send(file=f); await asyncio.sleep(1.2)
            except Exception: await asyncio.sleep(1)

    @bot.command(name="help")
    @is_authorized()
    async def _help(ctx):
        await ctx.send(f"""**bot{inst.index} · prefix `{inst.prefix}`**

**owner:** access, unaccess, bots, broadcast, changeprefix, uptime, ping, status, stealth, stopall, stopallglobal, shutdown, shutdownall, restart
**spam:** Longspam, Heartspam, kentospam, customspam, Fuga, warn, dmspam, pollspam (+ speed/stop)
**nc:** gcnc, hindinc, longnc, servernc, foodnc, fontnc (+ stop)
**react:** autoreact, stopreact, userreact, selfreact
**reply:** slide, target, echo, permecho (+ stop)
**ghost:** ghost, ghosttype, stopghosttype, ghostspeed
**util:** say, clear, quickdelete, edit, reverse, snipe, ship, autofiller
**status:** playing, watching, listening, stopactivity
**mod:** kick, ban, clean, lock, unlock, serverinfo, userinfo, nuke, leaveserver, leavegc
**pfp/pic:** pfp, pfploop, stoppfp, set1–set10, startpic, stoppic, delay, resetall, listslots, clearslot, copypfp, showpfp, showbanner, spampfp""")


# =====================================================================
# MANAGER
# =====================================================================
class Manager:
    def __init__(self):
        self.instances: list[BotInstance] = []

    async def run(self, tokens: list[str]):
        for i, tok in enumerate(tokens):
            self.instances.append(BotInstance(tok, i))
        log.info("starting fleet of %d bots", len(self.instances))
        await asyncio.gather(*(self._run(b) for b in self.instances), return_exceptions=True)

    async def _run(self, inst: BotInstance):
        try:
            await inst.bot.start(inst.token)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("[bot%d] crashed: %s", inst.index, e)


MANAGER = Manager()


# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    allowed_ids = load_allowed()
    allowed_ids.add(PERMANENT_OWNER)
    allowed_ids.add(BOT_OWNER_ID)
    try:
        asyncio.run(MANAGER.run(TOKENS))
    except KeyboardInterrupt:
        log.info("interrupted")