
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os
from typing import Dict, Any

TOKEN = ""

cfg_file = "configs.json"
cfg = {}

def load_configs():
    # Load the persistent server-specific configuration used by the suggestion system, populate the module-level 'cfg' dictionary, and fall back to an empty mapping on file errors so the bot can continue operating.
    global cfg
    try:
        if os.path.exists(cfg_file):
            with open(cfg_file, 'r') as f:
                cfg = json.load(f)
            print(f"Loaded {len(cfg)} server configs")
        else:
            cfg = {}
            print("No config file found, starting fresh")
    except Exception:
        cfg = {}

def save_configs():
    # Persist the in-memory configuration to disk; swallow write errors to avoid crashing the bot on I/O failures and allow admins to inspect logs.
    try:
        with open(cfg_file, 'w') as f:
            json.dump(cfg, f, indent=2)
        print(f"Saved {len(cfg)} server configs")
    except Exception:
        pass


class SuggestionBot(commands.Bot):
    def __init__(self):
        # Require message content and reaction intents to support the suggestion workflow.
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        super().__init__(command_prefix='!', intents=intents)
        
    async def setup_hook(self):
        # During startup load saved configs and sync slash commands with Discord.
        load_configs()
        await self.tree.sync()
        print(f"Synced commands for {self.user}")
    
    async def on_ready(self):
        # Print ready status and set presence so maintainers can verify the bot is active.
        print(f'{self.user} has landed!')
        print(f'Bot is in {len(self.guilds)} servers')
        
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for suggestions"
            )
        )
    
    # On joining a guild, send a brief welcome that includes quick setup instructions so administrators can configure the suggestion workflow without external docs.
    async def on_guild_join(self, guild):
        print(f"Joined new server: {guild.name}")
        
        ch = None
        
        for c in guild.text_channels:
            if c.name.lower() in ['general', 'welcome', 'bot-commands', 'commands']:
                if c.permissions_for(guild.me).send_messages:
                    ch = c
                    break
        
        if not ch:
            for c in guild.text_channels:
                if c.permissions_for(guild.me).send_messages:
                    ch = c
                    break
        
        if ch:
            # Prepare a welcome embed with concise setup instructions to guide administrators.
            embed = discord.Embed(
                title="🎉 Thanks for adding me!",
                description="I'm here to help manage your server suggestions with an awesome approval workflow!",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="🚀 Quick Setup",
                value="Use `/setup #suggestions #approval #featured 5` to get started instantly!",
                inline=False
            )
            embed.add_field(
                name="📋 What I do:",
                value="• Auto-react 👍 to suggestions\n• Send popular suggestions for approval\n• Create discussion threads\n• DM users when approved",
                inline=False
            )
            embed.add_field(
                name="🔧 Commands:",
                value="• `/setup` - Setup all channels at once\n• `/view_config` - See current settings\n• Individual setup commands available too!",
                inline=False
            )
            embed.set_footer(text="Need help? Check out the commands above!")
            
            try:
                await ch.send(embed=embed)
                print(f"Sent welcome message to {guild.name} in #{ch.name}")
            except Exception as e:
                pass
        else:
            print(f"No available channel found in {guild.name} to send welcome message")

bot = SuggestionBot()

def get_config(gid: int) -> Dict[str, Any]:
    # Return or create a guild-specific config mapping (channel IDs and threshold); keep 'sent_for_approval' as an in-memory set for fast checks and convert to a list before persisting for JSON compatibility.
    gid_str = str(gid)
    if gid_str not in cfg:
        cfg[gid_str] = {
            'suggestion_channel': None,
            'approval_channel': None,
            'featured_channel': None,
            'threshold': 5,
            'sent_for_approval': set()  # Track messages already sent for approval
        }
    # Convert old format to new format if needed
    if 'sug_ch' in cfg[gid_str]:
        cfg[gid_str]['suggestion_channel'] = cfg[gid_str].pop('sug_ch')
    if 'app_ch' in cfg[gid_str]:
        cfg[gid_str]['approval_channel'] = cfg[gid_str].pop('app_ch')
    if 'feat_ch' in cfg[gid_str]:
        cfg[gid_str]['featured_channel'] = cfg[gid_str].pop('feat_ch')
    if 'sent_for_approval' not in cfg[gid_str]:
        cfg[gid_str]['sent_for_approval'] = set()
    return cfg[gid_str]

def save_config(gid: int, config: Dict[str, Any]):
    # Update the in-memory config for a guild and persist to disk.
    # The function expects the caller to provide a properly formed
    # config dict (channel ids as integers, threshold as int, etc.).
    cfg[str(gid)] = config
    save_configs()

# Provide a `/setup` slash command that configures suggestion, approval, and featured channels plus the thumbs-up threshold for a guild.
@bot.tree.command(name="setup", description="Setup all channels and threshold in one command")
@app_commands.describe(
    suggestion_channel="The channel where users will post suggestions",
    approval_channel="The channel where suggestions will be reviewed", 
    featured_channel="The channel where approved suggestions will be posted",
    threshold="Number of 👍 reactions needed (default: 5)"
)
async def setup(
    interaction: discord.Interaction, 
    suggestion_channel: discord.TextChannel,
    approval_channel: discord.TextChannel,
    featured_channel: discord.TextChannel,
    threshold: int = 5
):
    if not (interaction.user.guild_permissions.manage_guild or 
            interaction.user.guild_permissions.administrator or 
            interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message("❌ You need `Manage Server`, `Administrator`, or be the server owner to use this command!", ephemeral=True)
        return
    
    if threshold < 1:
        await interaction.response.send_message("❌ Threshold must be at least 1!", ephemeral=True)
        return
    
    # Respond immediately to prevent timeout
    embed = discord.Embed(
        title="✅ All Channels Setup Complete!",
        description="Suggestion system is now ready to use!",
        color=discord.Color.green()
    )
    embed.add_field(name="📝 Suggestion Channel", value=suggestion_channel.mention, inline=False)
    embed.add_field(name="⚖️ Approval Channel", value=approval_channel.mention, inline=False)
    embed.add_field(name="⭐ Featured Channel", value=featured_channel.mention, inline=False)
    embed.add_field(name="👍 Thumbs Threshold", value=str(threshold), inline=False)
    
    await interaction.response.send_message(embed=embed)

    # this saves config after responding
    config = get_config(interaction.guild.id)
    config['suggestion_channel'] = suggestion_channel.id
    config['approval_channel'] = approval_channel.id
    config['featured_channel'] = featured_channel.id
    config['threshold'] = threshold
    save_config(interaction.guild.id, config)

# Provide a `/set_threshold` command restricted to administrators to update the number of 👍 reactions required to send a suggestion for approval.
@bot.tree.command(name="set_threshold", description="Set the number of thumbs up needed for approval")
@app_commands.describe(amount="Number of 👍 reactions needed")
async def set_threshold(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need to be an admin to change the threshold!", ephemeral=True)
        return
    
    if amount < 1:
        await interaction.response.send_message("❌ Threshold must be at least 1!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="✅ Threshold Set!",
        description=f"Thumbs up threshold has been set to **{amount}** 👍",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)
    
    config = get_config(interaction.guild.id)
    config['threshold'] = amount
    save_config(interaction.guild.id, config)

# Provide a `/view_config` command to display the current suggestion system settings for the guild, including channel mentions and threshold.
@bot.tree.command(name="view_config", description="View current suggestion system configuration")
async def view_config(interaction: discord.Interaction):
    config = get_config(interaction.guild.id)
    
    sug = f"<#{config['suggestion_channel']}>" if config['suggestion_channel'] else "Not set"
    app = f"<#{config['approval_channel']}>" if config['approval_channel'] else "Not set"
    feat = f"<#{config['featured_channel']}>" if config['featured_channel'] else "Not set"
    
    embed = discord.Embed(
        title="🔧 Suggestion System Configuration",
        color=discord.Color.blue()
    )
    embed.add_field(name="📝 Suggestion Channel", value=sug, inline=False)
    embed.add_field(name="⚖️ Approval Channel", value=app, inline=False)
    embed.add_field(name="⭐ Featured Channel", value=feat, inline=False)
    embed.add_field(name="👍 Thumbs Threshold", value=str(config['threshold']), inline=False)
    
    await interaction.response.send_message(embed=embed)

# Auto-react to new messages posted in the configured suggestion channel with 👍 and 👎 so the community can vote immediately.
@bot.event
async def on_message(msg):
    if msg.author.bot:
        return
    
    config = get_config(msg.guild.id)
    
    if msg.channel.id == config['suggestion_channel']:
        await msg.add_reaction('👍')
        await msg.add_reaction('👎')
        print(f"Added thumbs up and thumbs down reactions to suggestion in {msg.guild.name}")

# When someone adds a reaction, check whether the message in the suggestion channel reached the configured thumbs-up threshold and send it to the approval channel if so.
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    
    config = get_config(reaction.message.guild.id)
    
    # Only process reactions in suggestion channel
    if reaction.message.channel.id != config['suggestion_channel']:
        return
    
    # Check if this message was already sent for approval
    if reaction.message.id in config['sent_for_approval']:
        return
    
    # Only process thumbs up reactions
    if str(reaction.emoji) != '👍':
        return
    
    # Get thumbs up and thumbs down counts
    thumbs_up = 0
    thumbs_down = 0
    
    for react in reaction.message.reactions:
        if str(react.emoji) == '👍':
            thumbs_up = react.count
        elif str(react.emoji) == '👎':
            thumbs_down = react.count
    
    # Check if thumbs up meets threshold and is greater than or equal to thumbs down
    if (thumbs_up >= config['threshold'] and thumbs_up >= thumbs_down):
        # Mark this message as sent for approval to prevent duplicates
        config['sent_for_approval'].add(reaction.message.id)
        save_config(reaction.message.guild.id, config)
        
        await send_to_approval(reaction.message, config)

# Build and send an approval embed to the configured approval channel and attach the ApprovalView so moderators can accept or deny the suggestion.
async def send_to_approval(msg, config):
    app_ch = bot.get_channel(config['approval_channel'])
    if not app_ch:
        return
    
    embed = discord.Embed(
        title="📋 Suggestion Awaiting Approval",
        description=msg.content,
        color=discord.Color.orange(),
        timestamp=msg.created_at
    )
    embed.set_author(
        name=f"{msg.author.display_name}",
        icon_url=msg.author.display_avatar.url
    )
    embed.add_field(
        name="👍 Reactions", 
        value=str(len([r for r in msg.reactions if str(r.emoji) == '👍'])), 
        inline=True
    )
    embed.add_field(
        name="Original Suggestion Message", 
        value=f"[Jump to message]({msg.jump_url})", 
        inline=True
    )
    
    view = ApprovalView(msg, config)
    
    await app_ch.send(embed=embed, view=view)

# ApprovalView provides Approve and Deny buttons for staff; the Approve button opens an ApprovalModal to collect optional admin notes.
class ApprovalView(discord.ui.View):
    def __init__(self, msg, config):
        super().__init__(timeout=None)
        self.msg = msg
        self.config = config
    
    @discord.ui.button(label='Approve', style=discord.ButtonStyle.green)
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need `Manage Messages` permission to approve suggestions!", ephemeral=True)
            return
        
        modal = ApprovalModal(self.msg, self.config, interaction.message)
        await interaction.response.send_modal(modal)
    
    # Deny button, disables everything
    @discord.ui.button(label='Deny', style=discord.ButtonStyle.red)
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need `Manage Messages` permission to deny suggestions!", ephemeral=True)
            return
        
        embed = interaction.message.embeds[0]
        embed.title = "❌ Suggestion Denied"
        embed.color = discord.Color.red()
        embed.add_field(name="Denied by", value=interaction.user.mention, inline=True)
        
        for item in self.children:
            item.disabled = True
            if item.label == 'Deny':
                item.style = discord.ButtonStyle.secondary
                item.label = 'Denied'
        
        await interaction.response.edit_message(embed=embed, view=self)

# ApprovalModal collects an optional admin note when approving a suggestion, posts the approved suggestion to the featured channel, creates a discussion thread, and DMs the suggestion author if possible.
class ApprovalModal(discord.ui.Modal, title='Approve Suggestion'):
    def __init__(self, msg, config, app_msg):
        super().__init__()
        self.msg = msg
        self.config = config
        self.app_msg = app_msg

    note = discord.ui.TextInput(
        label='Admin Note (Optional)',
        placeholder='Enter any additional notes or comments...',
        required=False,
        max_length=500,
        style=discord.TextStyle.paragraph
    )

    # Approve and post to featured
    async def on_submit(self, interaction: discord.Interaction):
        feat_ch = bot.get_channel(self.config['featured_channel'])
        if feat_ch:
            embed = discord.Embed(
                title=" Approved Suggestion",
                description=self.msg.content,
                color=discord.Color.gold(),
                timestamp=self.msg.created_at
            )
            embed.set_author(
                name=f"Suggested by {self.msg.author.display_name}",
                icon_url=self.msg.author.display_avatar.url
            )
            
            if self.note.value:
                embed.add_field(
                    name="📝 Admin Note",
                    value=self.note.value,
                    inline=False
                )
            
            feat_msg = await feat_ch.send(embed=embed)
            
            try:
                thread_name = f"💬 Discussion: {self.msg.content[:50]}{'...' if len(self.msg.content) > 50 else ''}"
                thread = await feat_msg.create_thread(
                    name=thread_name,
                    auto_archive_duration=10080
                )
                
                starter = discord.Embed(
                    title="💭 Discussion Thread",
                    description="Discuss this suggestion here! Share your thoughts, improvements, or related ideas.",
                    color=discord.Color.blue()
                )
                await thread.send(embed=starter)
                print(f"Created discussion thread for suggestion by {self.msg.author.display_name}")
                
            except Exception as e:
                pass
        
        try:
            dm = discord.Embed(
                title="🎉 Your Suggestion Has Been Approved!",
                description=f"Your suggestion in **{interaction.guild.name}** has been approved and featured!",
                color=discord.Color.green(),
                timestamp=self.msg.created_at
            )
            dm.add_field(
                name="Your Suggestion",
                value=self.msg.content[:1000] + ("..." if len(self.msg.content) > 1000 else ""),
                inline=False
            )
            
            if self.note.value:
                dm.add_field(
                    name="Admin Note",
                    value=self.note.value,
                    inline=False
                )
            
            dm.set_footer(text=f"Server: {interaction.guild.name}")
            
            await self.msg.author.send(embed=dm)
            print(f"Sent approval DM to {self.msg.author.display_name}")
            
        except discord.Forbidden:
            pass
        except Exception as e:
            pass
        
        embed = self.app_msg.embeds[0]
        embed.title = "✅ Suggestion Approved"
        embed.color = discord.Color.green()
        embed.add_field(name="Approved by", value=interaction.user.mention, inline=True)
        
        if self.note.value:
            embed.add_field(name="Admin Note", value=self.note.value, inline=False)
        
        view = discord.ui.View()
        approved_btn = discord.ui.Button(
            label='✅ Approved', 
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        view.add_item(approved_btn)
        
        await interaction.response.edit_message(embed=embed, view=view)


if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Invalid token")
    else:
        bot.run(TOKEN)
