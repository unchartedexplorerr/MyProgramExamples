
import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sqlite3

TOKEN = ""


def create_quit_button(callback):
    btn = discord.ui.Button(label='Quit Game', style=discord.ButtonStyle.danger)
    btn.callback = callback
    return btn

def create_rematch_button(callback, label='Rematch'):
    btn = discord.ui.Button(label=label, style=discord.ButtonStyle.success)
    btn.callback = callback
    return btn

# Database setup
def init_db():
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    
    # Table for game results
    c.execute('''CREATE TABLE IF NOT EXISTS game_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        guild_id INTEGER,
        game_type TEXT,
        result TEXT,
        timestamp TEXT,
        points_earned INTEGER
    )''')
    
    # User points and levels
    c.execute('''CREATE TABLE IF NOT EXISTS user_points (
        user_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        total_points INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        draws INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()
    print("Database ready!")

class MiniGameBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.active_games = {}  # Track ongoing games

        
    async def setup_hook(self):
        init_db()
        await self.tree.sync()
        print(f"Commands synced for {self.user}")
    
    async def on_ready(self):
        # Set status
        await self.change_presence(activity=discord.Game("Games"))
        print(f'{self.user} is ready!')
        print(f'Active in {len(self.guilds)} servers')

bot = MiniGameBot()



# Points management
def add_points(user_id, guild_id, points, result):
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    
    # Insert user if not exists
    c.execute('''INSERT OR IGNORE INTO user_points 
                 (user_id, guild_id, total_points, level, wins, losses, draws) 
                 VALUES (?, ?, 0, 1, 0, 0, 0)''', (user_id, guild_id))
    
    # Update points and stats
    if result == 'win':
        c.execute('''UPDATE user_points 
                     SET total_points = total_points + ?, wins = wins + 1 
                     WHERE user_id = ?''', (points, user_id))
    elif result == 'loss':
        c.execute('''UPDATE user_points 
                     SET losses = losses + 1 
                     WHERE user_id = ?''', (user_id,))
    else:  # draw
        c.execute('''UPDATE user_points 
                     SET total_points = total_points + ?, draws = draws + 1 
                     WHERE user_id = ?''', (points//2, user_id))
    
    # Level up check
    c.execute('SELECT total_points FROM user_points WHERE user_id = ?', (user_id,))
    total = c.fetchone()[0]
    new_level = (total // 100) + 1
    c.execute('UPDATE user_points SET level = ? WHERE user_id = ?', (new_level, user_id))
    
    conn.commit()
    conn.close()
    return new_level

def get_user_stats(user_id):
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    c.execute('SELECT * FROM user_points WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result

# Tic Tac Toe game
class TicTacToeView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=300)
        self.p1 = p1  # Player 1
        self.p2 = p2  # Player 2  
        self.current_player = p1
        self.board = [' '] * 9
        self.game_over = False
        
    def check_winner(self):
        # Winning combos
        wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        
        for combo in wins:
            if (self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]] != ' '):
                return self.board[combo[0]]
        
        if ' ' not in self.board:
            return 'tie'
        return None
    
    def get_board_str(self):
        # Create board display
        emojis = []
        for i, cell in enumerate(self.board):
            if cell == 'X':
                emojis.append('❌')
            elif cell == 'O':
                emojis.append('⭕')
            else:
                emojis.append(f'{i+1}️⃣')
        
        # Format with separators
        return f"```\n{emojis[0]} │ {emojis[1]} │ {emojis[2]}\n──┼───┼──\n{emojis[3]} │ {emojis[4]} │ {emojis[5]}\n──┼───┼──\n{emojis[6]} │ {emojis[7]} │ {emojis[8]}\n```"
    
    async def make_move(self, interaction, pos):
        if self.game_over or interaction.user != self.current_player:
            return
            
        if self.board[pos] != ' ':
            await interaction.response.send_message("That position is already taken!", ephemeral=True)
            return
        
        # Place symbol
        symbol = 'X' if self.current_player == self.p1 else 'O'
        self.board[pos] = symbol
        
        winner = self.check_winner()
        embed = discord.Embed(title="🎮 Tic Tac Toe", color=0x00ff00)
        
        if winner:
            self.game_over = True
            if winner == 'tie':
                embed.description = f"It's a tie!\n\n{self.get_board_str()}"
                add_points(self.p1.id, interaction.guild.id, 5, 'draw')
                add_points(self.p2.id, interaction.guild.id, 5, 'draw')
            else:
                winner_user = self.p1 if symbol == 'X' else self.p2
                loser_user = self.p2 if symbol == 'X' else self.p1
                embed.description = f"{winner_user.mention} wins!\n\n{self.get_board_str()}"
                new_level = add_points(winner_user.id, interaction.guild.id, 15, 'win')
                add_points(loser_user.id, interaction.guild.id, 0, 'loss')
                
                if new_level > 1:
                    embed.add_field(name="Level Up!", value=f"{winner_user.mention} is now level {new_level}!")
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
        else:
            self.current_player = self.p2 if self.current_player == self.p1 else self.p1
            embed.description = f"{self.current_player.mention}'s turn\n\n{self.get_board_str()}"
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(emoji='1️⃣', style=discord.ButtonStyle.secondary, row=0)
    async def pos1(self, interaction, button): await self.make_move(interaction, 0)
    
    @discord.ui.button(emoji='2️⃣', style=discord.ButtonStyle.secondary, row=0)
    async def pos2(self, interaction, button): await self.make_move(interaction, 1)
    
    @discord.ui.button(emoji='3️⃣', style=discord.ButtonStyle.secondary, row=0)
    async def pos3(self, interaction, button): await self.make_move(interaction, 2)
    
    @discord.ui.button(emoji='4️⃣', style=discord.ButtonStyle.secondary, row=1)
    async def pos4(self, interaction, button): await self.make_move(interaction, 3)
    
    @discord.ui.button(emoji='5️⃣', style=discord.ButtonStyle.secondary, row=1)
    async def pos5(self, interaction, button): await self.make_move(interaction, 4)
    
    @discord.ui.button(emoji='6️⃣', style=discord.ButtonStyle.secondary, row=1)
    async def pos6(self, interaction, button): await self.make_move(interaction, 5)
    
    @discord.ui.button(emoji='7️⃣', style=discord.ButtonStyle.secondary, row=2)
    async def pos7(self, interaction, button): await self.make_move(interaction, 6)
    
    @discord.ui.button(emoji='8️⃣', style=discord.ButtonStyle.secondary, row=2)
    async def pos8(self, interaction, button): await self.make_move(interaction, 7)
    
    @discord.ui.button(emoji='9️⃣', style=discord.ButtonStyle.secondary, row=2)
    async def pos9(self, interaction, button): await self.make_move(interaction, 8)
    
    @discord.ui.button(label='Quit Game', style=discord.ButtonStyle.danger, row=3)
    async def quit_game(self, interaction, button):
        if interaction.user not in [self.p1, self.p2]:
            await interaction.response.send_message("Only players can quit!", ephemeral=True)
            return
        
        self.game_over = True
        embed = discord.Embed(
            title="🎮 Tic Tac Toe - Game Quit",
            description=f"{interaction.user.mention} quit the game!",
            color=0xff0000
        )
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label='Rematch', style=discord.ButtonStyle.success, row=3)
    async def rematch(self, interaction, button):
        if interaction.user not in [self.p1, self.p2]:
            await interaction.response.send_message("Only players can start rematch!", ephemeral=True)
            return
        
        # create new game
        new_view = TicTacToeView(self.p1, self.p2)
        embed = discord.Embed(
            title="🎮 Tic Tac Toe - Rematch",
            description=f"{self.p1.mention} vs {self.p2.mention}\n\n{self.p1.mention}'s turn (❌)",
            color=0x00ff00
        )
        embed.description += f"\n\n{new_view.get_board_str()}"
        
        await interaction.response.edit_message(embed=embed, view=new_view)

# Tic Tac Toe AI
class TicTacToeAIView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=300)
        self.player = player
        self.board = [' '] * 9
        self.game_over = False
        self.ai = TicTacToeAI()
        
    def check_winner(self):
        wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        
        for combo in wins:
            if (self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]] != ' '):
                return self.board[combo[0]]
        
        if ' ' not in self.board:
            return 'tie'
        return None
    
    def get_board_str(self):
        emojis = []
        for i, cell in enumerate(self.board):
            if cell == 'X':
                emojis.append('❌')
            elif cell == 'O':
                emojis.append('⭕')
            else:
                emojis.append(f'{i+1}️⃣')
        
        # add spacing and separators for bigger AI board
        return f"```\n{emojis[0]} │ {emojis[1]} │ {emojis[2]}\n──┼───┼──\n{emojis[3]} │ {emojis[4]} │ {emojis[5]}\n──┼───┼──\n{emojis[6]} │ {emojis[7]} │ {emojis[8]}\n```"
    
    async def make_move(self, interaction, pos):
        if self.game_over or interaction.user != self.player:
            return
            
        if self.board[pos] != ' ':
            await interaction.response.send_message("Position already taken!", ephemeral=True)
            return
        
        # Place player move
        self.board[pos] = 'X'
        
        winner = self.check_winner()
        if winner:
            await self.end_game(interaction, winner)
            return
        
        # AI move
        ai_move = self.ai.get_best_move(self.board)
        if ai_move is not None:
            self.board[ai_move] = 'O'
        
        winner = self.check_winner()
        if winner:
            await self.end_game(interaction, winner)
        else:
            embed = discord.Embed(
                title="🎮 Tic Tac Toe vs AI",
                description=f"Your turn (❌)\n\n{self.get_board_str()}",
                color=0x00ff00
            )
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def end_game(self, interaction, winner):
        self.game_over = True
        embed = discord.Embed(title="🎮 Tic Tac Toe vs AI", color=0x00ff00)
        
        if winner == 'tie':
            embed.description = f"It's a draw!\n\n{self.get_board_str()}"
            add_points(self.player.id, interaction.guild.id, 8, 'draw')
        elif winner == 'X':
            embed.description = f"{self.player.mention} wins against AI!\n\n{self.get_board_str()}"
            new_level = add_points(self.player.id, interaction.guild.id, 20, 'win')
            if new_level > 1:
                embed.add_field(name="Level Up!", value=f"You reached level {new_level}!")
        else:
            embed.description = f"AI wins! Better luck next time!\n\n{self.get_board_str()}"
            add_points(self.player.id, interaction.guild.id, 0, 'loss')
        
        for item in self.children:
            item.disabled = True
            
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(emoji='1️⃣', style=discord.ButtonStyle.secondary, row=0)
    async def ai_pos1(self, interaction, button): await self.make_move(interaction, 0)
    
    @discord.ui.button(emoji='2️⃣', style=discord.ButtonStyle.secondary, row=0)
    async def ai_pos2(self, interaction, button): await self.make_move(interaction, 1)
    
    @discord.ui.button(emoji='3️⃣', style=discord.ButtonStyle.secondary, row=0)
    async def ai_pos3(self, interaction, button): await self.make_move(interaction, 2)
    
    @discord.ui.button(emoji='4️⃣', style=discord.ButtonStyle.secondary, row=1)
    async def ai_pos4(self, interaction, button): await self.make_move(interaction, 3)
    
    @discord.ui.button(emoji='5️⃣', style=discord.ButtonStyle.secondary, row=1)
    async def ai_pos5(self, interaction, button): await self.make_move(interaction, 4)
    
    @discord.ui.button(emoji='6️⃣', style=discord.ButtonStyle.secondary, row=1)
    async def ai_pos6(self, interaction, button): await self.make_move(interaction, 5)
    
    @discord.ui.button(emoji='7️⃣', style=discord.ButtonStyle.secondary, row=2)
    async def ai_pos7(self, interaction, button): await self.make_move(interaction, 6)
    
    @discord.ui.button(emoji='8️⃣', style=discord.ButtonStyle.secondary, row=2)
    async def ai_pos8(self, interaction, button): await self.make_move(interaction, 7)
    
    @discord.ui.button(emoji='9️⃣', style=discord.ButtonStyle.secondary, row=2)
    async def ai_pos9(self, interaction, button): await self.make_move(interaction, 8)
    
    @discord.ui.button(label='Quit Game', style=discord.ButtonStyle.danger, row=3)
    async def quit_ai_game(self, interaction, button):
        if interaction.user != self.player:
            await interaction.response.send_message("Only the player can quit!", ephemeral=True)
            return
        
        self.game_over = True
        embed = discord.Embed(
            title="🎮 Tic Tac Toe vs AI - Game Quit",
            description=f"{interaction.user.mention} quit the game against AI!",
            color=0xff0000
        )
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label='Rematch vs AI', style=discord.ButtonStyle.success, row=3)
    async def rematch_ai(self, interaction, button):
        if interaction.user != self.player:
            await interaction.response.send_message("Only the player can start rematch!", ephemeral=True)
            return
        
        # create new AI game
        new_view = TicTacToeAIView(self.player)
        embed = discord.Embed(
            title="🎮 Tic Tac Toe vs AI - Rematch",
            description=f"{self.player.mention} vs AI\n\nYour turn (❌)",
            color=0x00ff00
        )
        embed.description += f"\n\n{new_view.get_board_str()}"
        
        await interaction.response.edit_message(embed=embed, view=new_view)

# Rock Paper Scissors
class RPSView(discord.ui.View):
    def __init__(self, challenger, opponent):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.choices = {}
        
    @discord.ui.button(emoji='🪨', label='Rock', style=discord.ButtonStyle.primary)
    async def rock(self, interaction, button):
        await self.make_choice(interaction, 'rock')
    
    @discord.ui.button(emoji='📄', label='Paper', style=discord.ButtonStyle.primary)  
    async def paper(self, interaction, button):
        await self.make_choice(interaction, 'paper')
    
    @discord.ui.button(emoji='✂️', label='Scissors', style=discord.ButtonStyle.primary)
    async def scissors(self, interaction, button):
        await self.make_choice(interaction, 'scissors')
    
    @discord.ui.button(label='Quit Game', style=discord.ButtonStyle.danger, row=1)
    async def quit_rps(self, interaction, button):
        if interaction.user not in [self.challenger, self.opponent]:
            await interaction.response.send_message("Only players can quit!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎮 Rock Paper Scissors - Game Quit",
            description=f"{interaction.user.mention} quit the game!",
            color=0xff0000
        )
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label='Rematch', style=discord.ButtonStyle.success, row=1)
    async def rematch_rps(self, interaction, button):
        if interaction.user not in [self.challenger, self.opponent]:
            await interaction.response.send_message("Only players can start rematch!", ephemeral=True)
            return
        
        # create new RPS game
        new_view = RPSView(self.challenger, self.opponent)
        embed = discord.Embed(
            title="🎮 Rock Paper Scissors - Rematch",
            description=f"{self.challenger.mention} vs {self.opponent.mention}\n\nBoth players make your choices!",
            color=0x00ff00
        )
        
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    async def make_choice(self, interaction, choice):
        if interaction.user not in [self.challenger, self.opponent]:
            await interaction.response.send_message("This game is not for you!", ephemeral=True)
            return
            
        self.choices[interaction.user.id] = choice
        
        if len(self.choices) == 1:
            await interaction.response.send_message(f"Choice locked in! Waiting for opponent...", ephemeral=True)
        else:
            p1_choice = self.choices[self.challenger.id]
            p2_choice = self.choices[self.opponent.id]
            
            result = self.get_winner(p1_choice, p2_choice)
            
            embed = discord.Embed(title="🎮 Rock Paper Scissors Results!", color=0x00ff00)
            embed.add_field(name=f"{self.challenger.display_name}", value=f"{self.get_emoji(p1_choice)} {p1_choice.title()}", inline=True)
            embed.add_field(name="VS", value="⚔️", inline=True)
            embed.add_field(name=f"{self.opponent.display_name}", value=f"{self.get_emoji(p2_choice)} {p2_choice.title()}", inline=True)
            
            if result == 'tie':
                embed.description = "It's a tie!"
                add_points(self.challenger.id, interaction.guild.id, 3, 'draw')
                add_points(self.opponent.id, interaction.guild.id, 3, 'draw')
            elif result == 'p1':
                embed.description = f"{self.challenger.mention} wins!"
                new_level = add_points(self.challenger.id, interaction.guild.id, 10, 'win')
                add_points(self.opponent.id, interaction.guild.id, 0, 'loss')
                if new_level > 1:
                    embed.add_field(name="Level Up!", value=f"{self.challenger.mention} reached level {new_level}!", inline=False)
            else:
                embed.description = f"{self.opponent.mention} wins!"
                new_level = add_points(self.opponent.id, interaction.guild.id, 10, 'win')
                add_points(self.challenger.id, interaction.guild.id, 0, 'loss')
                if new_level > 1:
                    embed.add_field(name="Level Up!", value=f"{self.opponent.mention} reached level {new_level}!", inline=False)
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
                
            await interaction.response.edit_message(embed=embed, view=self)
    
    def get_winner(self, p1, p2):
        if p1 == p2:
            return 'tie'
        
        winning_combos = {
            'rock': 'scissors',
            'paper': 'rock', 
            'scissors': 'paper'
        }
        
        return 'p1' if winning_combos[p1] == p2 else 'p2'
    
    def get_emoji(self, choice):
        emojis = {'rock': '🪨', 'paper': '📄', 'scissors': '✂️'}
        return emojis[choice]

# AI for Tic Tac Toe
class TicTacToeAI:
    def get_best_move(self, board):
        # Check for winning moves
        for i in range(9):
            if board[i] == ' ':
                board[i] = 'O'
                if self.check_winner(board) == 'O':
                    board[i] = ' '
                    return i
                board[i] = ' '
        
        # Block player wins
        for i in range(9):
            if board[i] == ' ':
                board[i] = 'X'
                if self.check_winner(board) == 'X':
                    board[i] = ' '
                    return i
                board[i] = ' '
        
        # Prefer center
        if board[4] == ' ':
            return 4
            
        # Then corners
        corners = [0, 2, 6, 8]
        available_corners = [i for i in corners if board[i] == ' ']
        if available_corners:
            return random.choice(available_corners)
        
        # Any spot
        available = [i for i in range(9) if board[i] == ' ']
        return random.choice(available) if available else None
    
    def check_winner(self, board):
        wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for combo in wins:
            if (board[combo[0]] == board[combo[1]] == board[combo[2]] != ' '):
                return board[combo[0]]
        return None

# Tic Tac Toe command
@bot.tree.command(name="tictactoe", description="Play tic tac toe with another player or AI")
@app_commands.describe(opponent="The player you want to challenge (leave blank for AI)")
async def tictactoe(interaction: discord.Interaction, opponent: discord.Member = None):
    if opponent and opponent.bot and opponent != bot.user:
        await interaction.response.send_message("Cannot challenge other bots!", ephemeral=True)
        return
        
    if opponent == interaction.user:
        await interaction.response.send_message("Cannot play against yourself!", ephemeral=True)
        return
    
    if opponent is None or opponent == bot.user:
        # play against AI
        embed = discord.Embed(
            title="🎮 Tic Tac Toe vs AI", 
            description=f"{interaction.user.mention} vs AI\n\nYour turn (❌)",
            color=0x00ff00
        )
        
        view = TicTacToeAIView(interaction.user)
        embed.description += f"\n\n{view.get_board_str()}"
    else:
        # play against another player
        embed = discord.Embed(
            title="🎮 Tic Tac Toe", 
            description=f"{interaction.user.mention} vs {opponent.mention}\n\n{interaction.user.mention}'s turn (❌)",
            color=0x00ff00
        )
        
        view = TicTacToeView(interaction.user, opponent)
        embed.description += f"\n\n{view.get_board_str()}"
    
    await interaction.response.send_message(embed=embed, view=view)

# RPS command  
@bot.tree.command(name="rps", description="Play rock paper scissors")
@app_commands.describe(opponent="Player to challenge (optional - leave blank to play vs AI)")
async def rps(interaction: discord.Interaction, opponent: discord.Member = None):
    if opponent and opponent.bot and opponent != bot.user:
        await interaction.response.send_message("Cannot challenge other bots!", ephemeral=True)
        return
        
    if opponent == interaction.user:
        await interaction.response.send_message("Cannot play against yourself!", ephemeral=True)
        return
    
    if opponent is None or opponent == bot.user:
        # play against bot
        bot_choice = random.choice(['rock', 'paper', 'scissors'])
        
        embed = discord.Embed(title="🎮 Rock Paper Scissors vs AI", color=0x00ff00)
        embed.description = "Make your choice!"
        
        view = discord.ui.View()
        
        async def bot_game_callback(inter, user_choice):
            if inter.user != interaction.user:
                await inter.response.send_message("Not your game!", ephemeral=True)
                return
                
            result_embed = discord.Embed(title="🎮 RPS Results vs AI!", color=0x00ff00)
            
            emojis = {'rock': '🪨', 'paper': '📄', 'scissors': '✂️'}
            result_embed.add_field(name="You", value=f"{emojis[user_choice]} {user_choice.title()}", inline=True)
            result_embed.add_field(name="VS", value="⚔️", inline=True)  
            result_embed.add_field(name="AI", value=f"{emojis[bot_choice]} {bot_choice.title()}", inline=True)
            
            if user_choice == bot_choice:
                result_embed.description = "It's a tie!"
                add_points(inter.user.id, inter.guild.id, 3, 'draw')
            elif ((user_choice == 'rock' and bot_choice == 'scissors') or 
                  (user_choice == 'paper' and bot_choice == 'rock') or
                  (user_choice == 'scissors' and bot_choice == 'paper')):
                result_embed.description = "You win! 🎉"
                new_level = add_points(inter.user.id, inter.guild.id, 8, 'win')
                if new_level > 1:
                    result_embed.add_field(name="Level Up!", value=f"You reached level {new_level}!", inline=False)
            else:
                result_embed.description = "AI wins!"
                add_points(inter.user.id, inter.guild.id, 0, 'loss')
            
            await inter.response.edit_message(embed=result_embed, view=None)
        
        # create buttons for bot game
        rock_btn = discord.ui.Button(emoji='🪨', label='Rock', style=discord.ButtonStyle.primary)
        paper_btn = discord.ui.Button(emoji='📄', label='Paper', style=discord.ButtonStyle.primary)
        scissors_btn = discord.ui.Button(emoji='✂️', label='Scissors', style=discord.ButtonStyle.primary)
        
        rock_btn.callback = lambda i: bot_game_callback(i, 'rock')
        paper_btn.callback = lambda i: bot_game_callback(i, 'paper')  
        scissors_btn.callback = lambda i: bot_game_callback(i, 'scissors')
        
        # create quit and rematch buttons for AI game
        quit_btn = discord.ui.Button(label='Quit Game', style=discord.ButtonStyle.danger)
        rematch_btn = discord.ui.Button(label='Rematch vs AI', style=discord.ButtonStyle.success)
        
        async def quit_ai_rps(inter):
            if inter.user != interaction.user:
                await inter.response.send_message("Only you can quit!", ephemeral=True)
                return
            
            quit_embed = discord.Embed(
                title="🎮 RPS vs AI - Game Quit",
                description=f"{inter.user.mention} quit the game against AI!",
                color=0xff0000
            )
            await inter.response.edit_message(embed=quit_embed, view=None)
        
        async def rematch_ai_rps(inter):
            if inter.user != interaction.user:
                await inter.response.send_message("Only you can start rematch!", ephemeral=True)
                return
            
            # restart AI game
            new_bot_choice = random.choice(['rock', 'paper', 'scissors'])
            new_embed = discord.Embed(title="🎮 Rock Paper Scissors vs AI - Rematch", color=0x00ff00)
            new_embed.description = "Make your choice!"
            
            new_view = discord.ui.View()
            
            # recreate game buttons with new bot choice
            new_rock_btn = discord.ui.Button(emoji='🪨', label='Rock', style=discord.ButtonStyle.primary)
            new_paper_btn = discord.ui.Button(emoji='📄', label='Paper', style=discord.ButtonStyle.primary)
            new_scissors_btn = discord.ui.Button(emoji='✂️', label='Scissors', style=discord.ButtonStyle.primary)
            
            new_rock_btn.callback = lambda i: bot_game_callback_new(i, 'rock', new_bot_choice)
            new_paper_btn.callback = lambda i: bot_game_callback_new(i, 'paper', new_bot_choice)
            new_scissors_btn.callback = lambda i: bot_game_callback_new(i, 'scissors', new_bot_choice)
            
            # add quit and rematch for new game too
            new_quit_btn = discord.ui.Button(label='Quit Game', style=discord.ButtonStyle.danger)
            new_rematch_btn = discord.ui.Button(label='Rematch vs AI', style=discord.ButtonStyle.success)
            
            new_quit_btn.callback = lambda i: quit_ai_rps(i)
            new_rematch_btn.callback = lambda i: rematch_ai_rps(i)
            
            new_view.add_item(new_rock_btn)
            new_view.add_item(new_paper_btn)
            new_view.add_item(new_scissors_btn)
            new_view.add_item(new_quit_btn)
            new_view.add_item(new_rematch_btn)
            
            await inter.response.edit_message(embed=new_embed, view=new_view)
        
        async def bot_game_callback_new(inter, user_choice, bot_choice_param):
            if inter.user != interaction.user:
                await inter.response.send_message("Not your game!", ephemeral=True)
                return
                
            result_embed = discord.Embed(title="🎮 RPS Results vs AI!", color=0x00ff00)
            
            emojis = {'rock': '🪨', 'paper': '📄', 'scissors': '✂️'}
            result_embed.add_field(name="You", value=f"{emojis[user_choice]} {user_choice.title()}", inline=True)
            result_embed.add_field(name="VS", value="⚔️", inline=True)  
            result_embed.add_field(name="AI", value=f"{emojis[bot_choice_param]} {bot_choice_param.title()}", inline=True)
            
            if user_choice == bot_choice_param:
                result_embed.description = "It's a tie!"
                add_points(inter.user.id, inter.guild.id, 3, 'draw')
            elif ((user_choice == 'rock' and bot_choice_param == 'scissors') or 
                  (user_choice == 'paper' and bot_choice_param == 'rock') or
                  (user_choice == 'scissors' and bot_choice_param == 'paper')):
                result_embed.description = "You win! 🎉"
                new_level = add_points(inter.user.id, inter.guild.id, 8, 'win')
                if new_level > 1:
                    result_embed.add_field(name="Level Up!", value=f"You reached level {new_level}!", inline=False)
            else:
                result_embed.description = "AI wins!"
                add_points(inter.user.id, inter.guild.id, 0, 'loss')
            
            # add rematch button to results
            final_view = discord.ui.View()
            final_rematch_btn = discord.ui.Button(label='Play Again', style=discord.ButtonStyle.success)
            final_rematch_btn.callback = lambda i: rematch_ai_rps(i)
            final_view.add_item(final_rematch_btn)
            
            await inter.response.edit_message(embed=result_embed, view=final_view)
        
        quit_btn.callback = lambda i: quit_ai_rps(i)
        rematch_btn.callback = lambda i: rematch_ai_rps(i)
        
        view.add_item(rock_btn)
        view.add_item(paper_btn)
        view.add_item(scissors_btn)
        view.add_item(quit_btn)
        view.add_item(rematch_btn)
        
        await interaction.response.send_message(embed=embed, view=view)
    else:
        # play against another player
        embed = discord.Embed(
            title="🎮 Rock Paper Scissors",
            description=f"{interaction.user.mention} vs {opponent.mention}\n\nBoth players make your choices!",
            color=0x00ff00
        )
        
        view = RPSView(interaction.user, opponent)
        await interaction.response.send_message(embed=embed, view=view)

# Trivia questions
trivia_questions = {
    "general": [
        {"q": "What's the capital of France?", "a": ["paris"], "wrong": ["london", "berlin", "madrid"]},
        {"q": "How many continents are there?", "a": ["7", "seven"], "wrong": ["6", "8", "5"]},
        {"q": "What's the largest planet in our solar system?", "a": ["jupiter"], "wrong": ["saturn", "earth", "mars"]},
        {"q": "Who painted the Mona Lisa?", "a": ["leonardo da vinci", "da vinci"], "wrong": ["picasso", "van gogh", "michelangelo"]},
        {"q": "What year did World War 2 end?", "a": ["1945"], "wrong": ["1944", "1946", "1943"]},
    ],
    "gaming": [
        {"q": "Which company created Minecraft?", "a": ["mojang"], "wrong": ["microsoft", "sony", "nintendo"]},
        {"q": "What's the main character's name in Zelda?", "a": ["link"], "wrong": ["zelda", "ganon", "mario"]},
        {"q": "Which game features Master Chief?", "a": ["halo"], "wrong": ["destiny", "call of duty", "apex"]},
        {"q": "What year was the first Pokemon game released?", "a": ["1996"], "wrong": ["1995", "1997", "1998"]},
        {"q": "Which company makes the PlayStation?", "a": ["sony"], "wrong": ["microsoft", "nintendo", "valve"]},
    ],
    "science": [
        {"q": "What's the chemical symbol for water?", "a": ["h2o"], "wrong": ["co2", "o2", "h2"]},
        {"q": "How many bones are in the adult human body?", "a": ["206"], "wrong": ["207", "205", "210"]},
        {"q": "What planet is known as the Red Planet?", "a": ["mars"], "wrong": ["venus", "jupiter", "saturn"]},
        {"q": "What gas do plants absorb from the atmosphere?", "a": ["carbon dioxide", "co2"], "wrong": ["oxygen", "nitrogen", "hydrogen"]},
        {"q": "What's the speed of light?", "a": ["299792458", "300000000"], "wrong": ["150000000", "200000000", "250000000"]},
    ]
}

# Trivia command
@bot.tree.command(name="trivia", description="Play trivia game with different categories")
@app_commands.describe(category="Choose trivia category")
@app_commands.choices(category=[
    app_commands.Choice(name="General Knowledge", value="general"),
    app_commands.Choice(name="Gaming", value="gaming"), 
    app_commands.Choice(name="Science", value="science"),
    app_commands.Choice(name="Random Mix", value="random")
])
async def trivia(interaction: discord.Interaction, category: str = "random"):
    if category == "random":
        category = random.choice(list(trivia_questions.keys()))
    
    question = random.choice(trivia_questions[category])
    
    choices = question["wrong"][:3] + [random.choice(question["a"])]
    random.shuffle(choices)
    
    embed = discord.Embed(
        title=f"🧠 Trivia - {category.title()}",
        description=f"**{question['q']}**",
        color=0x3498db
    )
    
    emojis = ["🇦", "🇧", "🇨", "🇩"]
    for i, choice in enumerate(choices):
        embed.add_field(name=f"{emojis[i]} {choice.title()}", value="", inline=False)
    
    embed.set_footer(text="You have 20 seconds to answer!")
    
    view = discord.ui.View(timeout=20)
    
    async def answer_callback(inter, selected_answer):
        if inter.user != interaction.user:
            await inter.response.send_message("This is not your trivia question!", ephemeral=True)
            return
        
        correct_answers = [ans.lower() for ans in question["a"]]
        is_correct = selected_answer.lower() in correct_answers
        
        result_embed = discord.Embed(title="🧠 Trivia Results", color=0x00ff00 if is_correct else 0xff0000)
        
        if is_correct:
            result_embed.description = f"Correct!\n\n**Question:** {question['q']}\n**Your Answer:** {selected_answer}"
            # More points for harder categories
            points = 12 if category != "general" else 8
            new_level = add_points(inter.user.id, inter.guild.id, points, 'win')
            result_embed.add_field(name="Points Earned", value=f"+{points} points", inline=True)
            if new_level > 1:
                result_embed.add_field(name="Level Up!", value=f"You're now level {new_level}!", inline=True)
        else:
            correct_ans = random.choice(question["a"])
            result_embed.description = f"Wrong!\n\n**Question:** {question['q']}\n**Your Answer:** {selected_answer}\n**Correct Answer:** {correct_ans}"
            add_points(inter.user.id, inter.guild.id, 0, 'loss')
        
        await inter.response.edit_message(embed=result_embed, view=None)
    
    # create answer buttons
    for i, choice in enumerate(choices):
        btn = discord.ui.Button(emoji=emojis[i], label=choice.title(), style=discord.ButtonStyle.secondary)
        btn.callback = lambda inter, ans=choice: answer_callback(inter, ans)
        view.add_item(btn)
    
    # add quit and new question buttons
    quit_btn = discord.ui.Button(label='Quit Trivia', style=discord.ButtonStyle.danger)
    new_question_btn = discord.ui.Button(label='New Question', style=discord.ButtonStyle.success)
    
    async def quit_trivia(inter):
        if inter.user != interaction.user:
            await inter.response.send_message("Only you can quit!", ephemeral=True)
            return
        
        quit_embed = discord.Embed(
            title="🧠 Trivia - Game Quit",
            description=f"{inter.user.mention} ended the trivia session!",
            color=0xff0000
        )
        await inter.response.edit_message(embed=quit_embed, view=None)
    
    async def new_trivia_question(inter):
        if inter.user != interaction.user:
            await inter.response.send_message("Only you can get new question!", ephemeral=True)
            return
        
        # generate new question
        new_category = category if category != "random" else random.choice(list(trivia_questions.keys()))
        new_question = random.choice(trivia_questions[new_category])
        new_choices = new_question["wrong"][:3] + [random.choice(new_question["a"])]
        random.shuffle(new_choices)
        
        new_embed = discord.Embed(
            title=f"🧠 Trivia - {new_category.title()}",
            description=f"**{new_question['q']}**",
            color=0x3498db
        )
        
        for i, choice in enumerate(new_choices):
            new_embed.add_field(name=f"{emojis[i]} {choice.title()}", value="", inline=False)
        
        new_embed.set_footer(text="You have 20 seconds to answer!")
        
        # create new view with new question
        new_view = discord.ui.View(timeout=20)
        
        async def new_answer_callback(new_inter, selected_answer):
            if new_inter.user != interaction.user:
                await new_inter.response.send_message("This is not your trivia question!", ephemeral=True)
                return
            
            correct_answers = [ans.lower() for ans in new_question["a"]]
            is_correct = selected_answer.lower() in correct_answers
            
            result_embed = discord.Embed(title="🧠 Trivia Results", color=0x00ff00 if is_correct else 0xff0000)
            
            if is_correct:
                result_embed.description = f"Correct!\n\n**Question:** {new_question['q']}\n**Your Answer:** {selected_answer}"
                points = 12 if new_category != "general" else 8
                new_level = add_points(new_inter.user.id, new_inter.guild.id, points, 'win')
                result_embed.add_field(name="Points Earned", value=f"+{points} points", inline=True)
                if new_level > 1:
                    result_embed.add_field(name="Level Up!", value=f"You're now level {new_level}!", inline=True)
            else:
                correct_ans = random.choice(new_question["a"])
                result_embed.description = f"Wrong!\n\n**Question:** {new_question['q']}\n**Your Answer:** {selected_answer}\n**Correct Answer:** {correct_ans}"
                add_points(new_inter.user.id, new_inter.guild.id, 0, 'loss')
            
            # add play again button
            final_view = discord.ui.View()
            play_again_btn = discord.ui.Button(label='Another Question', style=discord.ButtonStyle.success)
            play_again_btn.callback = lambda i: new_trivia_question(i)
            final_view.add_item(play_again_btn)
            
            await new_inter.response.edit_message(embed=result_embed, view=final_view)
        
        # add answer buttons to new view
        for i, choice in enumerate(new_choices):
            new_btn = discord.ui.Button(emoji=emojis[i], label=choice.title(), style=discord.ButtonStyle.secondary)
            new_btn.callback = lambda new_inter, ans=choice: new_answer_callback(new_inter, ans)
            new_view.add_item(new_btn)
        
        # add quit and new question buttons
        new_quit_btn = discord.ui.Button(label='Quit Trivia', style=discord.ButtonStyle.danger)
        new_question_btn2 = discord.ui.Button(label='New Question', style=discord.ButtonStyle.success)
        
        new_quit_btn.callback = lambda i: quit_trivia(i)
        new_question_btn2.callback = lambda i: new_trivia_question(i)
        
        new_view.add_item(new_quit_btn)
        new_view.add_item(new_question_btn2)
        
        await inter.response.edit_message(embed=new_embed, view=new_view)
    
    quit_btn.callback = lambda i: quit_trivia(i)
    new_question_btn.callback = lambda i: new_trivia_question(i)
    
    view.add_item(quit_btn)
    view.add_item(new_question_btn)
    
    await interaction.response.send_message(embed=embed, view=view)

# Guess number command
@bot.tree.command(name="guess", description="Guess the number game (1-100)")
@app_commands.describe(difficulty="Choose difficulty level")
@app_commands.choices(difficulty=[
    app_commands.Choice(name="Easy (1-50)", value="easy"),
    app_commands.Choice(name="Medium (1-100)", value="medium"),
    app_commands.Choice(name="Hard (1-200)", value="hard")
])
async def guess_number(interaction: discord.Interaction, difficulty: str = "medium"):
    ranges = {"easy": 50, "medium": 100, "hard": 200}
    max_num = ranges[difficulty]
    secret_num = random.randint(1, max_num)
    
    game_id = f"{interaction.user.id}_{interaction.id}"
    bot.active_games[game_id] = {
        'number': secret_num,
        'guesses': 0,
        'max_guesses': 7 if difficulty == "easy" else 6 if difficulty == "medium" else 8,
        'range': max_num,
        'difficulty': difficulty
    }
    
    embed = discord.Embed(
        title=f"🔢 Number Guessing Game - {difficulty.title()}",
        description=f"I'm thinking of a number between 1 and {max_num}!\nYou have {bot.active_games[game_id]['max_guesses']} guesses.",
        color=0xf39c12
    )
    embed.set_footer(text="Type your guess in chat!")
    
    await interaction.response.send_message(embed=embed)
    
    def check(msg):
        return (msg.author == interaction.user and 
                msg.channel == interaction.channel and 
                msg.content.isdigit())
    
    while game_id in bot.active_games:
        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            guess = int(msg.content)
            game_data = bot.active_games[game_id]
            game_data['guesses'] += 1
            
            if guess == game_data['number']:
                # correct guess - calculate points based on guesses and difficulty
                base_points = {"easy": 8, "medium": 12, "hard": 18}
                bonus = max(0, (game_data['max_guesses'] - game_data['guesses']) * 2)
                total_points = base_points[difficulty] + bonus
                
                embed = discord.Embed(
                    title="🎉 You Win!",
                    description=f"Correct! The number was {game_data['number']}\nGuessed in {game_data['guesses']} tries!",
                    color=0x00ff00
                )
                new_level = add_points(interaction.user.id, interaction.guild.id, total_points, 'win')
                embed.add_field(name="Points Earned", value=f"+{total_points} points", inline=True)
                if new_level > 1:
                    embed.add_field(name="Level Up!", value=f"Level {new_level} achieved!", inline=True)
                
                await msg.reply(embed=embed)
                del bot.active_games[game_id]
                break
                
            elif game_data['guesses'] >= game_data['max_guesses']:
                # out of guesses
                embed = discord.Embed(
                    title="😞 Game Over",
                    description=f"You ran out of guesses! The number was {game_data['number']}",
                    color=0xff0000
                )
                add_points(interaction.user.id, interaction.guild.id, 0, 'loss')
                await msg.reply(embed=embed)
                del bot.active_games[game_id]
                break
                
            else:
                # wrong guess - give hint
                remaining = game_data['max_guesses'] - game_data['guesses']
                hint = "higher" if guess < game_data['number'] else "lower"
                
                embed = discord.Embed(
                    title="🔢 Wrong Guess",
                    description=f"Go {hint}! ({remaining} guesses left)",
                    color=0xf39c12
                )
                await msg.reply(embed=embed)
                
        except asyncio.TimeoutError:
            if game_id in bot.active_games:
                embed = discord.Embed(
                    title="⏰ Time's Up",
                    description=f"Game timed out! The number was {bot.active_games[game_id]['number']}",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed)
                del bot.active_games[game_id]
            break

# Stats and leaderboard commands
@bot.tree.command(name="stats", description="Check your gaming stats")
@app_commands.describe(user="Check another user's stats (optional)")
async def stats(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    
    if target.bot:
        await interaction.response.send_message("Bots do not have statistics!", ephemeral=True)
        return
    
    user_data = get_user_stats(target.id)
    
    if not user_data:
        embed = discord.Embed(
            title="📊 Gaming Stats",
            description=f"{target.display_name} hasn't played any games yet!",
            color=0x95a5a6
        )
    else:
        _, _, points, level, wins, losses, draws = user_data
        total_games = wins + losses + draws
        win_rate = round((wins / total_games * 100), 1) if total_games > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Gaming Stats - {target.display_name}",
            color=target.color or 0x3498db
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(name="🏆 Level", value=f"Level {level}", inline=True)
        embed.add_field(name="🎯 Points", value=f"{points:,} pts", inline=True)
        embed.add_field(name="🎮 Games Played", value=f"{total_games}", inline=True)
        
        embed.add_field(name="✅ Wins", value=f"{wins}", inline=True)
        embed.add_field(name="❌ Losses", value=f"{losses}", inline=True)  
        embed.add_field(name="🤝 Draws", value=f"{draws}", inline=True)
        
        embed.add_field(name="📈 Win Rate", value=f"{win_rate}%", inline=True)
        
        # next level progress
        next_level_points = level * 100
        progress = points % 100
        embed.add_field(name="📊 Next Level", value=f"{progress}/100 pts", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Show server gaming leaderboard")
@app_commands.describe(
    sort_by="What to sort the leaderboard by"
)
@app_commands.choices(sort_by=[
    app_commands.Choice(name="Points", value="points"),
    app_commands.Choice(name="Level", value="level"),
    app_commands.Choice(name="Win Rate", value="winrate"),
    app_commands.Choice(name="Total Games", value="games")
])
async def leaderboard(interaction: discord.Interaction, sort_by: str = "points"):
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    
    c.execute('''SELECT user_id, total_points, level, wins, losses, draws 
                 FROM user_points WHERE guild_id = ? 
                 ORDER BY total_points DESC LIMIT 10''', (interaction.guild.id,))
    
    results = c.fetchall()
    conn.close()
    
    if not results:
        await interaction.response.send_message("No one has played games yet in this server!")
        return
    
    # sort results based on choice
    if sort_by == "level":
        results = sorted(results, key=lambda x: x[2], reverse=True)
    elif sort_by == "winrate":
        results = sorted(results, key=lambda x: (x[3] / max(1, x[3] + x[4] + x[5])), reverse=True)
    elif sort_by == "games":
        results = sorted(results, key=lambda x: (x[3] + x[4] + x[5]), reverse=True)
    
    embed = discord.Embed(
        title=f"🏆 Gaming Leaderboard - {sort_by.title()}",
        color=0xf1c40f
    )
    
    leaderboard_text = []
    medals = ["🥇", "🥈", "🥉"]
    
    for i, (user_id, points, level, wins, losses, draws) in enumerate(results):
        user = interaction.guild.get_member(user_id)
        if not user:
            continue
            
        medal = medals[i] if i < 3 else f"`#{i+1}`"
        total_games = wins + losses + draws
        
        if sort_by == "points":
            value = f"{points:,} pts"
        elif sort_by == "level": 
            value = f"Level {level}"
        elif sort_by == "winrate":
            wr = round((wins / max(1, total_games)) * 100, 1)
            value = f"{wr}% WR"
        else:  # games
            value = f"{total_games} games"
        
        leaderboard_text.append(f"{medal} **{user.display_name}** - {value}")
    
    embed.description = "\n".join(leaderboard_text[:10])
    embed.set_footer(text="Keep playing to climb the ranks!")
    
    await interaction.response.send_message(embed=embed)

# Fun commands: 8ball and coin flip
@bot.tree.command(name="8ball", description="Ask the magic 8 ball a question")
@app_commands.describe(question="Your question for the 8 ball")
async def eight_ball(interaction: discord.Interaction, question: str):
    responses = [
        "It is certain", "Without a doubt", "Yes definitely", "You may rely on it",
        "As I see it, yes", "Most likely", "Outlook good", "Yes", "Signs point to yes",
        "Reply hazy, try again", "Ask again later", "Better not tell you now", 
        "Cannot predict now", "Concentrate and ask again", "Don't count on it",
        "My reply is no", "My sources say no", "Outlook not so good", "Very doubtful"
    ]
    
    answer = random.choice(responses)
    
    embed = discord.Embed(
        title="🎱 Magic 8 Ball",
        color=0x9b59b6
    )
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=f"*{answer}*", inline=False)
    
    # small points for using 8ball
    add_points(interaction.user.id, interaction.guild.id, 1, 'draw')
    
    # add play again button
    view = discord.ui.View()
    play_again_btn = discord.ui.Button(label='Ask Again', style=discord.ButtonStyle.success)
    
    async def ask_again(inter):
        if inter.user != interaction.user:
            await inter.response.send_message("Only you can ask again!", ephemeral=True)
            return
        
        new_answer = random.choice(responses)
        new_embed = discord.Embed(title="🎱 Magic 8 Ball", color=0x9b59b6)
        new_embed.add_field(name="Question", value=question, inline=False)
        new_embed.add_field(name="Answer", value=f"*{new_answer}*", inline=False)
        
        add_points(inter.user.id, inter.guild.id, 1, 'draw')
        
        await inter.response.edit_message(embed=new_embed, view=view)
    
    play_again_btn.callback = lambda i: ask_again(i)
    view.add_item(play_again_btn)
    
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="coinflip", description="Flip a coin")
@app_commands.describe(call="Call heads or tails (optional)")
@app_commands.choices(call=[
    app_commands.Choice(name="Heads", value="heads"),
    app_commands.Choice(name="Tails", value="tails")
])
async def coinflip(interaction: discord.Interaction, call: str = None):
    result = random.choice(["heads", "tails"])
    emoji = "🪙" 
    
    embed = discord.Embed(
        title="🪙 Coin Flip",
        color=0xe67e22
    )
    
    if call:
        correct = call.lower() == result
        embed.add_field(name="Your Call", value=call.title(), inline=True)
        embed.add_field(name="Result", value=result.title(), inline=True)
        embed.add_field(name="Outcome", value="✅ Correct!" if correct else "❌ Wrong!", inline=True)
        
        if correct:
            points = add_points(interaction.user.id, interaction.guild.id, 5, 'win')
            embed.add_field(name="Points", value="+5 points", inline=False)
        else:
            add_points(interaction.user.id, interaction.guild.id, 0, 'loss')
    else:
        embed.description = f"The coin landed on **{result.title()}**!"
        add_points(interaction.user.id, interaction.guild.id, 1, 'draw')
    
    # add flip again button
    view = discord.ui.View()
    flip_again_btn = discord.ui.Button(label='Flip Again', style=discord.ButtonStyle.success)
    
    async def flip_again(inter):
        if inter.user != interaction.user:
            await inter.response.send_message("Only you can flip again!", ephemeral=True)
            return
        
        new_result = random.choice(["heads", "tails"])
        new_embed = discord.Embed(title="🪙 Coin Flip", color=0xe67e22)
        
        if call:
            correct = call.lower() == new_result
            new_embed.add_field(name="Your Call", value=call.title(), inline=True)
            new_embed.add_field(name="Result", value=new_result.title(), inline=True)
            new_embed.add_field(name="Outcome", value="✅ Correct!" if correct else "❌ Wrong!", inline=True)
            
            if correct:
                points = add_points(inter.user.id, inter.guild.id, 5, 'win')
                new_embed.add_field(name="Points", value="+5 points", inline=False)
            else:
                add_points(inter.user.id, inter.guild.id, 0, 'loss')
        else:
            new_embed.description = f"The coin landed on **{new_result.title()}**!"
            add_points(inter.user.id, inter.guild.id, 1, 'draw')
        
        await inter.response.edit_message(embed=new_embed, view=view)
    
    flip_again_btn.callback = lambda i: flip_again(i)
    view.add_item(flip_again_btn)
    
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="dice", description="Roll dice")
@app_commands.describe(
    sides="Number of sides on the dice (default: 6)",
    count="Number of dice to roll (default: 1)"
)
async def roll_dice(interaction: discord.Interaction, sides: int = 6, count: int = 1):
    if sides < 2 or sides > 100:
        await interaction.response.send_message("Dice must have between 2-100 sides!", ephemeral=True)
        return
        
    if count < 1 or count > 10:
        await interaction.response.send_message("Please roll between 1-10 dice at once!", ephemeral=True)
        return
    
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    
    embed = discord.Embed(
        title=f"🎲 Dice Roll - {count}d{sides}",
        color=0xe74c3c
    )
    
    if count == 1:
        embed.description = f"You rolled: **{rolls[0]}**"
    else:
        embed.description = f"Rolls: {', '.join(map(str, rolls))}\n**Total: {total}**"
    
    # Bonus points for good rolls
    luck_factor = total / (count * sides)
    if luck_factor >= 0.8:  # very lucky
        points = 8
        embed.add_field(name="Lucky!", value="+8 points", inline=True)
    elif luck_factor >= 0.6:  # pretty good
        points = 4
        embed.add_field(name="Nice!", value="+4 points", inline=True)  
    else:
        points = 1
        
    add_points(interaction.user.id, interaction.guild.id, points, 'draw')
    
    # add roll again button
    view = discord.ui.View()
    roll_again_btn = discord.ui.Button(label='Roll Again', style=discord.ButtonStyle.success)
    
    async def roll_again(inter):
        if inter.user != interaction.user:
            await inter.response.send_message("Only you can roll again!", ephemeral=True)
            return
        
        new_rolls = [random.randint(1, sides) for _ in range(count)]
        new_total = sum(new_rolls)
        
        new_embed = discord.Embed(title=f"🎲 Dice Roll - {count}d{sides}", color=0xe74c3c)
        
        if count == 1:
            new_embed.description = f"You rolled: **{new_rolls[0]}**"
        else:
            new_embed.description = f"Rolls: {', '.join(map(str, new_rolls))}\n**Total: {new_total}**"
        
        # give points based on luck
        luck_factor = new_total / (count * sides)
        if luck_factor >= 0.8:
            points = 8
            new_embed.add_field(name="Lucky!", value="+8 points", inline=True)
        elif luck_factor >= 0.6:
            points = 4
            new_embed.add_field(name="Nice!", value="+4 points", inline=True)  
        else:
            points = 1
            
        add_points(inter.user.id, inter.guild.id, points, 'draw')
        
        await inter.response.edit_message(embed=new_embed, view=view)
    
    roll_again_btn.callback = lambda i: roll_again(i)
    view.add_item(roll_again_btn)
    
    await interaction.response.send_message(embed=embed, view=view)

# Well, at the end, this starts the bot.
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Error starting gaming bot: {e}")
