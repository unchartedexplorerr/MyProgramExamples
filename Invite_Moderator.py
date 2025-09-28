import discord
from discord.ext import commands
import re
import aiohttp
import asyncio
import json
import os


TOKEN = ""
config_file = "config.json"

# This loads the active guilds from a JSON config file
def load_config():
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                data = json.load(f)
                return set(data.get('active_guilds', []))
        except Exception as e:
            return set()
    else:
        save_config(set())
        return set()

# This saves the active guilds to a JSON config file
def save_config(guilds):
    try:
        config_data = {
            'active_guilds': list(guilds)
        }
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        print(f"Config saved with {len(guilds)} active guilds")
    except Exception as e:
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
# This creates regex patterns to match NSFW keywords, including leetspeak variations
def create_regex_patterns():
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

# Bot startup event, sets presence and syncs slash commands
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Loaded {len(guilds)} active guilds from config')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="invites"))
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        pass

# Slash command to activate NSFW invite filtering in a server
@bot.tree.command(name="activate", description="Activate NSFW invite filtering for this server")
async def activate(interaction: discord.Interaction):
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

# Slash command to deactivate filtering
@bot.tree.command(name="deactivate", description="Deactivate NSFW invite filtering for this server")
async def deactivate(interaction: discord.Interaction):
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

# Slash command to check if filtering is active
@bot.tree.command(name="status", description="Check if NSFW invite filtering is active")
async def status(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    is_active = guild_id in guilds
    status_emoji = "🟢" if is_active else "🔴"
    status_text = "**ACTIVE**" if is_active else "**INACTIVE**"
    
    await interaction.response.send_message(f"{status_emoji} NSFW invite filtering is {status_text} in this server.", ephemeral=True)

# This fetches the server name from a Discord invite code using the API
async def get_invite_info(code):
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
    except Exception as e:
        return None

# This extracts invite codes from message text using regex patterns
def extract_invite_codes(text):
    codes = []
    for pattern in INVITE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            code = match.split('/')[-1]
            if code and len(code) >= 3:
                codes.append(code)
    return codes

# This checks if a server name contains NSFW keywords using regex
def is_nsfw_server_name(name):
    if not name:
        return False
    
    return bool(re.search(PATTERN, name, re.IGNORECASE))

# Main event that monitors messages for NSFW invites and deletes them
@bot.event
async def on_message(message):
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
                    await message.delete()
                    
                    warning_msg = await message.channel.send(
                        f"🚫 **{message.author.mention}**, your message was deleted for containing an inappropriate server invite.\n"
                        f"Server: `{name}`"
                    )
                    
                    await asyncio.sleep(5)
                    try:
                        await warning_msg.delete()
                    except:
                        pass
                    
                    print(f"Deleted NSFW invite from {message.author} in {message.guild.name}: {name}")
                    break
                    
                except discord.errors.NotFound:
                    pass
                except discord.errors.Forbidden:
                    pass
                except Exception as e:
                    pass


if __name__ == "__main__":
    bot.run(TOKEN)
