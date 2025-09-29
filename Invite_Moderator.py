import discord
from discord.ext import commands
import re
import aiohttp
import asyncio
import json
import os


TOKEN = ""
config_file = "config.json"

def load_config():
    # Load the list of guild IDs where NSFW invite filtering is enabled; the configuration is a small JSON file that stores an 'active_guilds' list and we return a set for efficient membership checks, falling back to an empty set and creating a default file if the file is missing or cannot be parsed, and we tolerate parse errors so a transient corrupted file does not stop the bot from running.
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                data = json.load(f)
                return set(data.get('active_guilds', []))
        except Exception:
            return set()
    else:
        save_config(set())
        return set()

def save_config(guilds):
    # Persist the active guilds set to disk as JSON; convert the set to a list because JSON cannot represent sets and perform a best-effort write that silently ignores failures so the bot continues running if the file system is unavailable.
    try:
        config_data = {
            'active_guilds': list(guilds)
        }
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        print(f"Config saved with {len(guilds)} active guilds")
    except Exception:
        # Ignore write errors to avoid crashing in production if disk is
        # not writable; administrators can check logs to diagnose.
        pass

INTENTS = discord.Intents.default()
INTENTS.message_content = True

bot = commands.Bot(command_prefix='!', intents=INTENTS)

guilds = load_config()
# List of NSFW keywords to check server names for
KEYWORDS = [
    'adult', 'sex', 'porn', 'xxx', 'nsfw', 'nude', 'naked', 'erotic', 'sexy', 'hot',
    'kinky', 'fetish', 'bdsm', 'kink', 'horny', 'sexual', 'seduction', 'intimate',
    'sensual', 'pleasure', 'desire', 'lust', 'passion', 'naughty', 'dirty',
    
    'boobs', 'tits', 'ass', 'pussy', 'dick', 'cock', 'penis', 'vagina', 'breast',
    'nipple', 'butt', 'booty', 'thigh', 'curves', 'body', 'naked body',
    
    'hookup', 'dating', 'meet', 'chat', 'cam', 'webcam', 'strip', 'masturbate',
    'orgasm', 'climax', 'cumming', 'squirt', 'moan', 'seduce', 'flirt',
    
    '18+', '21+', 'adults only', 'mature', 'age verified', 'legal age',
    
    'onlyfans', 'premium', 'exclusive', 'private', 'vip', 'leaks', 'leaked',
    'content', 'pics', 'videos', 'media', 'gallery', 'collection',
    
    'fuck', 'fucking', 'bang', 'smash', 'breed', 'daddy', 'mommy', 'sugar',
    'escort', 'prostitute', 'whore', 'slut', 'bitch', 'hoe',
    
    'singles', 'lonely', 'horny girls', 'hot girls', 'cute girls', 'teens',
    'milf', 'cougar', 'sugar daddy', 'sugar baby', 'relationship', 'romance',
    
    'strip club', 'cam girl', 'cam boy', 'model', 'amateur', 'professional',
    'uncensored', 'explicit', 'graphic', 'hardcore', 'softcore', 'rated r',
    'x-rated',     'adult entertainment', 'adult content'
]
# TODO: add more keywords if needed
def create_regex_patterns():
    # Build a combined regular expression that matches any NSFW keyword or a leetspeak variant and return a single alternation string for re.search(..., re.IGNORECASE); each keyword appears twice in the pattern (escaped literal and a substituted version with simple character classes like 'a' -> '[a@4]') to detect common obfuscations while keeping the pattern compact.
    patterns = []
    for keyword in KEYWORDS:
        escaped_keyword = re.escape(keyword)
        leet_map = {
            'a': '[a@4]',
            'e': '[e3]',
            'i': '[i1!]',
            'o': '[o0]',
            's': '[s$5]',
            'l': '[l1!]',
            't': '[t7]'
        }
        def leet_sub(ch):
            return leet_map.get(ch.lower(), re.escape(ch))
        substituted = ''.join(leet_sub(ch) for ch in keyword)
        patterns.extend([
            fr'\b{escaped_keyword}\b',
            fr'\b{substituted}\b',
        ])
    # Wrap each alternative in a group and join with '|' so the final
    # pattern can be used directly in re.search.
    return '|'.join(f'({pattern})' for pattern in patterns)

PATTERN = create_regex_patterns()

# Regex patterns for matching various Discord invite link formats
INVITE_PATTERNS = [
    r'(?:https?://)?(?:www\.)?discord\.(?:gg|io|me|li)/[a-zA-Z0-9]+',
    r'(?:https?://)?(?:www\.)?discord\.com/invite/[a-zA-Z0-9]+',
    r'(?:https?://)?(?:www\.)?discordapp\.com/invite/[a-zA-Z0-9]+',
    r'discord\.gg/[a-zA-Z0-9]+',
    r'discord\.io/[a-zA-Z0-9]+',
    r'discord\.me/[a-zA-Z0-9]+',
    r'discord\.li/[a-zA-Z0-9]+',
]

@bot.event
async def on_ready():
    # Called once the bot has connected and is ready; set a presence and attempt to sync application commands so slash commands register with Discord while allowing sync failures to be non-fatal.
    print(f'{bot.user} has connected to Discord!')
    print(f'Loaded {len(guilds)} active guilds from config')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="invites"))
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception:
        # If command sync fails (rate limit, permissions), let the bot
        # continue running and surface the issue through logs.
        pass

@bot.tree.command(name="activate", description="Activate NSFW invite filtering for this server")
async def activate(interaction: discord.Interaction):
    # Toggle the filter on for the guild where the command is invoked.
    # Only users with Manage Server / Administrator permissions or the
    # server owner may use this command. The guild id is stored in the
    # in-memory set and persisted to disk.
    if not (interaction.user.guild_permissions.manage_guild or 
            interaction.user.guild_permissions.administrator or 
            interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message("You need 'Manage Server', 'Administrator', or be the server owner to use this command.", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    if guild_id in guilds:
        await interaction.response.send_message(" NSFW invite filtering is already active in this server.", ephemeral=True)
    else:
        guilds.add(guild_id)
        save_config(guilds)
        await interaction.response.send_message(" NSFW invite filtering has been **activated** for this server.\nI will now monitor and delete messages containing NSFW server invites.", ephemeral=True)

@bot.tree.command(name="deactivate", description="Deactivate NSFW invite filtering for this server")
async def deactivate(interaction: discord.Interaction):
    # Turn off filtering for the current guild. Permission checks are the
    # same as for activation. Removing the guild id stops on_message
    # from scanning messages in that server.
    if not (interaction.user.guild_permissions.manage_guild or 
            interaction.user.guild_permissions.administrator or 
            interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message("You need 'Manage Server', 'Administrator', or be the server owner to use this command.", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(" NSFW invite filtering is not active in this server.", ephemeral=True)
    else:
        guilds.remove(guild_id)
        save_config(guilds)
        await interaction.response.send_message(" NSFW invite filtering has been **deactivated** for this server.", ephemeral=True)

@bot.tree.command(name="status", description="Check if NSFW invite filtering is active")
async def status(interaction: discord.Interaction):
    # Inform the user whether the filter is currently enabled for their
    # guild. This reads the in-memory set populated on startup.
    guild_id = interaction.guild.id
    is_active = guild_id in guilds
    status_emoji = "🟢" if is_active else "🔴"
    status_text = "**ACTIVE**" if is_active else "**INACTIVE**"
    
    await interaction.response.send_message(f"{status_emoji} NSFW invite filtering is {status_text} in this server.", ephemeral=True)

async def get_invite_info(code):
    # Query Discord's public invite API to retrieve invite metadata.
    # We only extract the guild name which is sufficient for our
    # keyword-based NSFW heuristic. Any network or API error results in
    # returning None so the caller treats the invite as unknown.
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://discord.com/api/v10/invites/{code}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    guild_name = data.get('guild', {}).get('name', '')
                    return guild_name
                else:
                    return None
    except Exception:
        return None

def extract_invite_codes(text):
    # Run several regexes that match common Discord invite formats and
    # return the trailing path segment for each match (the invite code).
    # Very short tokens are ignored to reduce false positives.
    codes = []
    for pattern in INVITE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            code = match.split('/')[-1]
            if code and len(code) >= 3:
                codes.append(code)
    return codes

def is_nsfw_server_name(name):
    # Heuristic check: return True if the provided guild name matches
    # any of the compiled NSFW keyword alternatives. Empty or missing
    # names return False.
    if not name:
        return False
    
    return bool(re.search(PATTERN, name, re.IGNORECASE))

@bot.event
async def on_message(message):
    # Watch messages in configured guilds and remove invites that point
    # to servers we consider NSFW. The handler skips bots and DMs, only
    # runs in guilds listed in the `guilds` set, extracts invite codes
    # from the message text, asks `get_invite_info` for the target guild
    # name, and then uses `is_nsfw_server_name` to decide whether to
    # delete the message and post a short temporary warning to the
    # channel.
    if message.author.bot or not message.guild:
        return
    
    if message.guild.id not in guilds:
        return
    
    codes = extract_invite_codes(message.content)
    
    if codes:
        for code in codes:
            name = await get_invite_info(code)
            
            if name and is_nsfw_server_name(name):
                try:
                    # Remove the offending message to prevent access to
                    # the invite and notify the author briefly.
                    await message.delete()
                    
                    warning_msg = await message.channel.send(
                        f"🚫 **{message.author.mention}**, your message was deleted for containing an inappropriate server invite.\n"
                        f"Server: `{name}`"
                    )
                    
                    # Keep the notification visible for a short time,
                    # then delete it to keep channels clean.
                    await asyncio.sleep(5)
                    try:
                        await warning_msg.delete()
                    except Exception:
                        pass
                    
                    print(f"Deleted NSFW invite from {message.author} in {message.guild.name}: {name}")
                    break
                    
                except discord.errors.NotFound:
                    # Message already deleted or channel removed.
                    pass
                except discord.errors.Forbidden:
                    # Lacking permissions to delete/send messages.
                    pass
                except Exception:
                    # Catch-all to avoid crashing on unexpected runtime
                    # errors while processing other messages.
                    pass


if __name__ == "__main__":
    bot.run(TOKEN)
