import discord
from discord import app_commands
from discord.ext import commands
import os
from dotenv import load_dotenv

from state import active_duels
from rps_game import RPSSetupView
from roulette_game import RouletteSetupView

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


class GameSelectView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=30)
        self.user = user

    @discord.ui.button(label="Pierre-Papier-Ciseaux", style=discord.ButtonStyle.primary, emoji="🪨")
    async def rps_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("C'est pas ton /duel !", ephemeral=True)
            return
        self.stop()
        setup_view = RPSSetupView(interaction.user)
        await interaction.response.edit_message(
            content=(
                "**⚔️ Pierre-Papier-Ciseaux**\n"
                "Choisis ton adversaire et le timeout, puis lance le duel :"
            ),
            view=setup_view
        )

    @discord.ui.button(label="Roulette Russe", style=discord.ButtonStyle.danger, emoji="🔫")
    async def roulette_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("C'est pas ton /duel !", ephemeral=True)
            return
        self.stop()
        setup_view = RouletteSetupView(interaction.user)
        await interaction.response.edit_message(
            content=(
                "**🔫 Roulette Russe**\n"
                "Choisis les joueurs (jusqu'à 5) et le timeout du perdant :"
            ),
            view=setup_view
        )


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'{bot.user} is ready to duel!')
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')


@bot.tree.command(name="duel", description="Lance un Pierre-Papier-Ciseaux ou une Roulette Russe !")
async def duel(interaction: discord.Interaction):
    view = GameSelectView(interaction.user)
    await interaction.response.send_message(
        "🎮 **Quel jeu veux-tu lancer ?**",
        view=view
    )


TOKEN = os.getenv('DISCORD_BOT_TOKEN')

if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not found in environment variables. Please check your .env file.")

bot.run(TOKEN)
