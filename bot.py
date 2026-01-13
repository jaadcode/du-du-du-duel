import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import timedelta
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Game state storage
active_duels = {}

class DuelView(discord.ui.View):
    def __init__(self, challenger, challenged, timeout_minutes):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.challenged = challenged
        self.timeout_minutes = timeout_minutes
        self.accepted = False
        
    @discord.ui.button(label="Accepter le duel", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Tu attaques ta propre race ?", ephemeral=True)
            return
            
        self.accepted = True
        self.stop()
        await interaction.response.send_message(f"**DU-DU-DU-DUEL!** {self.challenged.mention} a accepté!", ephemeral=False)

class RPSButton(discord.ui.Button):
    def __init__(self, choice: str, emoji: str):
        super().__init__(label=choice, style=discord.ButtonStyle.primary, emoji=emoji)
        self.choice = choice

    async def callback(self, interaction: discord.Interaction):
        await self.view.make_choice(interaction, self.choice)

class RPSView(discord.ui.View):
    def __init__(self, player1, player2, round_num):
        super().__init__(timeout=30)
        self.player1 = player1
        self.player2 = player2
        self.round_num = round_num
        self.choices = {}
        
        # Add buttons
        self.add_item(RPSButton("Pierre", "🪨"))
        self.add_item(RPSButton("Papier", "📄"))
        self.add_item(RPSButton("Ciseaux", "✂️"))
    
    async def make_choice(self, interaction: discord.Interaction, choice: str):
        user_id = interaction.user.id
        
        print(f"[DEBUG] User {interaction.user.name} (ID: {user_id}) clicked {choice}")
        
        if user_id not in [self.player1.id, self.player2.id]:
            print(f"[DEBUG] User {interaction.user.name} is not part of this duel")
            await interaction.response.send_message("Sur le trottoir les fashions", ephemeral=True)
            return
        
        if user_id in self.choices:
            print(f"[DEBUG] User {interaction.user.name} already made a choice")
            await interaction.response.send_message("Tu as déjà choisi !", ephemeral=True)
            return
        
        self.choices[user_id] = choice
        print(f"[DEBUG] Choice registered for {interaction.user.name}: {choice}. Total choices: {len(self.choices)}/2")
        await interaction.response.send_message(f"Tu as fait {choice}!", ephemeral=True)
        
        # Check if both players chose
        if len(self.choices) == 2:
            print(f"[DEBUG] Both players have chosen! Stopping view...")
            self.stop()

def determine_winner(choice1: str, choice2: str) -> int:
    """Returns 1 if player1 wins, 2 if player2 wins, 0 if tie"""
    if choice1 == choice2:
        return 0
    
    wins = {
        "Pierre": "Ciseaux",
        "Papier": "Pierre",
        "Ciseaux": "Papier"
    }
    
    return 1 if wins[choice1] == choice2 else 2

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'{bot.user} is ready to duel!')
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')

@bot.tree.command(name="duel", description="Challenge ton tipeu au Pierre-Papier-Ciseaux")
@app_commands.describe(
    opponent="Le tipeu qui va prendre son timeout",
    timeout="Durée du timeout (1, 10, 60, ou custom)"
)
async def duel(interaction: discord.Interaction, opponent: discord.Member, timeout: int):
    # Validation
    if opponent.id == interaction.user.id:
        await interaction.response.send_message("Tu peux pas t'auto challenge.", ephemeral=True)
        return
    
    if opponent.bot:
        await interaction.response.send_message("C'est un bot hein...", ephemeral=True)
        return
    
    if timeout < 1 or timeout > 10080:  # Max 1 week
        await interaction.response.send_message("Le timeout doit être entre 1 et 10080 minutes (1 semaine)!", ephemeral=True)
        return
    
    if interaction.user.id in active_duels or opponent.id in active_duels:
        await interaction.response.send_message("L'un de vous est déjà en duel", ephemeral=True)
        return
    
    # Mark players as in duel
    active_duels[interaction.user.id] = True
    active_duels[opponent.id] = True
    
    # Send challenge (PUBLIC)
    view = DuelView(interaction.user, opponent, timeout)
    await interaction.response.send_message(
        f"⚔️ **DUEL CHALLENGE** ⚔️\n"
        f"{interaction.user.mention} défie {opponent.mention} à un duel de Pierre-Papier-Ciseaux!\n"
        f"**Stakes:** Le perdant se fait timeout pour **{timeout} minute(s)**\n"
        f"**Format:** Best of 3",
        view=view
    )
    
    # Wait for acceptance
    print(f"[DEBUG] Waiting for {opponent.name} to accept the duel...")
    await view.wait()
    
    if not view.accepted:
        print(f"[DEBUG] {opponent.name} didn't accept the duel")
        await interaction.followup.send(f"{opponent.mention} n'a pas accepté le duel, bébé cadum !")
        del active_duels[interaction.user.id]
        del active_duels[opponent.id]
        return
    
    print(f"[DEBUG] Duel accepted! Starting game between {player1.name} and {opponent.name}")
    
    # Start the duel
    player1 = interaction.user
    player2 = opponent
    scores = {player1.id: 0, player2.id: 0}
    
    # Store messages to track the conversation
    round_messages = []
    
    for round_num in range(1, 4):
        if scores[player1.id] == 2 or scores[player2.id] == 2:
            break
        
        # Create RPS view for this round
        rps_view = RPSView(player1, player2, round_num)
        round_msg = await interaction.followup.send(
            f"**🎮 ROUND {round_num} 🎮**\n{player1.mention} {player2.mention}\nChoisis ton coup",
            view=rps_view
        )
        round_messages.append(round_msg
    
    # Determine overall winner
    if scores[player1.id] > scores[player2.id]:
        winner = player1
        loser = player2
    else:
        winner = player2
        loser = player1
    
    # Timeout the loser and announce PUBLIC result
    try:
        await loser.timeout(timedelta(minutes=timeout), reason=f"A perdu contre {winner.display_name}")
        await interaction.followup.send(
            f"🏆 **{winner.mention} GAGNE LE DUEL!** 🏆\n\n"
            f"💀 {loser.mention} a été timeout pour **{timeout} minute(s)**!\n"
            f"C'est ciao ! 👋"
        )
    except discord.Forbidden:
        await interaction.followup.send(
            f"🏆 **{winner.mention} GAGNE LE DUEL!** 🏆\n\n"
            f"⚠️ Mais je peux pas le ban, oupsi {loser.mention}. "
            f"Faut me mettre les perms"
        )
    
    # Clean up
    del active_duels[player1.id]
    del active_duels[player2.id]

# Run the bot
# Get token from environment variable
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not found in environment variables. Please check your .env file.")

bot.run(TOKEN)