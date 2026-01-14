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
        self.refused = False
        
    @discord.ui.button(label="Accepter le duel", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("C'est pas ton moment gamin", ephemeral=True)
            return
            
        self.accepted = True
        self.stop()
        await interaction.response.send_message(f"**DU-DU-DU-DUEL!** {self.challenged.mention} a accepté!", ephemeral=False)
        
        # Try to play the duel sound if players are in voice
        try:
            challenger_voice = self.challenger.voice
            challenged_voice = self.challenged.voice
            
            voice_channel = None
            if challenger_voice and challenger_voice.channel:
                voice_channel = challenger_voice.channel
                print(f"[DEBUG] Challenger is in voice channel: {voice_channel.name}")
            elif challenged_voice and challenged_voice.channel:
                voice_channel = challenged_voice.channel
                print(f"[DEBUG] Challenged is in voice channel: {voice_channel.name}")
            
            if voice_channel:
                print(f"[DEBUG] Attempting to join voice channel and play sound...")
                voice_client = await voice_channel.connect()
                audio_source = discord.FFmpegPCMAudio('du-du-du-duel.mp3')
                voice_client.play(audio_source)
                
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)
                
                await asyncio.sleep(6)
                await voice_client.disconnect()
                print(f"[DEBUG] Sound played successfully!")
            else:
                print(f"[DEBUG] Neither player is in a voice channel")
        except Exception as e:
            print(f"[DEBUG] Error playing sound: {e}")
    
    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.secondary, emoji="❌")
    async def refuse_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Seul le challengé peut refuser !", ephemeral=True)
            return
        
        self.refused = True
        self.stop()
        await interaction.response.send_message(f"❌ {self.challenged.mention} a refusé le duel, bébé cadum ! 🐔")

class RevengeView(discord.ui.View):
    def __init__(self, loser, winner, timeout_minutes, guild):
        super().__init__(timeout=30)
        self.loser = loser
        self.winner = winner
        self.timeout_minutes = timeout_minutes
        self.guild = guild
        self.revenge_requested = False
        self.abandoned = False
        
    @discord.ui.button(label="Revanche ! (Quitte ou double)", style=discord.ButtonStyle.danger, emoji="🔥")
    async def revenge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.loser.id:
            await interaction.response.send_message("Seul le perdant peut demander une revanche !", ephemeral=True)
            return
        
        self.revenge_requested = True
        
        # Calculate doubled timeout, capped at 1 week
        doubled_timeout = min(self.timeout_minutes * 2, 10080)
        
        # Disable the button
        button.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Send challenge to winner
        accept_view = AcceptRevengeView(self.loser, self.winner)
        await interaction.followup.send(
            f"💀 **{self.loser.mention} demande une REVANCHE !**\n"
            f"🔥 **Quitte ou Double** : Le perdant prendra **{doubled_timeout} minutes** de timeout !\n"
            f"{self.winner.mention}, acceptes-tu ?",
            view=accept_view
        )
        
        # Wait for winner's response
        await accept_view.wait()
        
        if accept_view.accepted:
            # Remove from active duels temporarily (if they exist)
            if self.loser.id in active_duels:
                del active_duels[self.loser.id]
            if self.winner.id in active_duels:
                del active_duels[self.winner.id]
            
            # Start new duel with doubled timeout (capped)
            await start_duel_game(interaction, self.loser, self.winner, doubled_timeout, is_revenge=True)
        else:
            # Revenge refused, apply original timeout
            try:
                await self.loser.timeout(timedelta(minutes=self.timeout_minutes), reason=f"A perdu contre {self.winner.display_name}")
                await interaction.followup.send(f"{self.winner.mention} a refusé la revanche. {self.loser.mention} reste timeout pour {self.timeout_minutes} minute(s). 👋")
                print(f"[DEBUG] {self.loser.name} timed out (revenge refused)")
            except discord.Forbidden:
                await interaction.followup.send(f"{self.winner.mention} a refusé la revanche mais je ne peux pas timeout {self.loser.mention}.")
                print(f"[DEBUG] Failed to timeout {self.loser.name} - missing permissions")
    
    @discord.ui.button(label="Abandonner", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def abandon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.loser.id:
            await interaction.response.send_message("Seul le perdant peut abandonner !", ephemeral=True)
            return
        
        self.abandoned = True
        self.stop()
        
        # Disable the button
        button.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Apply timeout
        try:
            await self.loser.timeout(timedelta(minutes=self.timeout_minutes), reason=f"A perdu contre {self.winner.display_name}")
            await interaction.followup.send(f"{self.loser.mention} accepte sa défaite. Timeout de {self.timeout_minutes} minute(s) appliqué. 👋")
            print(f"[DEBUG] {self.loser.name} abandoned (accepted defeat)")
        except discord.Forbidden:
            await interaction.followup.send(f"{self.loser.mention} accepte sa défaite mais je ne peux pas le timeout.")
            print(f"[DEBUG] Failed to timeout {self.loser.name} - missing permissions")

class AcceptRevengeView(discord.ui.View):
    def __init__(self, challenger, challenged):
        super().__init__(timeout=30)
        self.challenger = challenger
        self.challenged = challenged
        self.accepted = False
        
    @discord.ui.button(label="Accepter la revanche", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Seul le gagnant peut accepter la revanche !", ephemeral=True)
            return
        
        self.accepted = True
        self.stop()
        await interaction.response.send_message(
            f"✅ **{self.challenged.mention} accepte la revanche !**\n"
            f"🔥 Le timeout de {self.challenger.mention} est annulé. **NOUVEAU DUEL !**"
        )
    
    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.secondary, emoji="❌")
    async def refuse_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Seul le gagnant peut refuser la revanche !", ephemeral=True)
            return
        
        self.accepted = False
        self.stop()
        await interaction.response.send_message(f"❌ {self.challenged.mention} refuse la revanche.")

class RPSButton(discord.ui.Button):
    def __init__(self, choice: str, emoji: str):
        super().__init__(label=choice, style=discord.ButtonStyle.primary, emoji=emoji)
        self.choice = choice

    async def callback(self, interaction: discord.Interaction):
        await self.view.make_choice(interaction, self.choice)

class RPSView(discord.ui.View):
    def __init__(self, player1, player2, round_num):
        super().__init__(timeout=None)
        self.player1 = player1
        self.player2 = player2
        self.round_num = round_num
        self.choices = {}
        print(f"[DEBUG] RPSView created for round {round_num}")
        
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

async def start_duel_game(interaction, player1, player2, timeout, is_revenge=False):
    """Main game loop - can be called for initial duel or revenge"""
    
    # Mark players as in duel (only if not already marked)
    if player1.id not in active_duels:
        active_duels[player1.id] = True
    if player2.id not in active_duels:
        active_duels[player2.id] = True
    
    print(f"[DEBUG] Starting game between {player1.name} and {player2.name} (Revenge: {is_revenge})")
    
    scores = {player1.id: 0, player2.id: 0}
    round_num = 1
    messages_to_delete = []
    
    while round_num <= 3:
        print(f"[DEBUG] === Starting round {round_num} ===")
        
        if scores[player1.id] == 2 or scores[player2.id] == 2:
            print(f"[DEBUG] Game over! Score: {scores[player1.id]}-{scores[player2.id]}")
            break
        
        rps_view = RPSView(player1, player2, round_num)
        
        print(f"[DEBUG] Sending round message with buttons...")
        round_msg = await interaction.followup.send(
            f"**🎮 ROUND {round_num} 🎮**\nChoisis ton coup",
            view=rps_view
        )
        messages_to_delete.append(round_msg)
        print(f"[DEBUG] Round message sent. Now waiting for players...")
        
        await rps_view.wait()
        print(f"[DEBUG] View.wait() completed!")
        
        print(f"[DEBUG] Choices received: {len(rps_view.choices)} out of 2")
        
        if len(rps_view.choices) != 2:
            print(f"[DEBUG] Not enough choices - canceling duel")
            await interaction.followup.send("⏰ Trop tard, duel reporté")
            del active_duels[player1.id]
            del active_duels[player2.id]
            return
        
        p1_choice = rps_view.choices[player1.id]
        p2_choice = rps_view.choices[player2.id]
        
        print(f"[DEBUG] {player1.name} chose {p1_choice}, {player2.name} chose {p2_choice}")
        
        result = determine_winner(p1_choice, p2_choice)
        
        result_text = f"{player1.mention} a choisi {p1_choice}\n{player2.mention} a choisi {p2_choice}\n\n"
        
        if result == 0:
            result_text += "**Egalité !**"
            print(f"[DEBUG] Round {round_num} - TIE! Replaying same round")
        elif result == 1:
            scores[player1.id] += 1
            result_text += f"**{player1.mention} gagne ce round !**"
            print(f"[DEBUG] Round {round_num} - {player1.name} wins! Score: {scores[player1.id]}-{scores[player2.id]}")
            round_num += 1
        else:
            scores[player2.id] += 1
            result_text += f"**{player2.mention} gagne ce round !**"
            print(f"[DEBUG] Round {round_num} - {player2.name} wins! Score: {scores[player1.id]}-{scores[player2.id]}")
            round_num += 1
        
        result_text += f"\n\n**Score: {player1.display_name} {scores[player1.id]} - {scores[player2.id]} {player2.display_name}**"
        
        result_msg = await interaction.followup.send(result_text)
        messages_to_delete.append(result_msg)
        print(f"[DEBUG] Result sent. Waiting 2 seconds before next round...")
        await asyncio.sleep(2)
    
    print(f"[DEBUG] All rounds completed. Final score: {scores[player1.id]}-{scores[player2.id]}")
    
    if scores[player1.id] > scores[player2.id]:
        winner = player1
        loser = player2
    else:
        winner = player2
        loser = player1
    
    print(f"[DEBUG] Winner: {winner.name}, Loser: {loser.name}")
    
    # Delete intermediate messages
    print(f"[DEBUG] Deleting {len(messages_to_delete)} intermediate messages...")
    for msg in messages_to_delete:
        try:
            await msg.delete()
        except Exception as e:
            print(f"[DEBUG] Failed to delete message: {e}")
    
    # Offer revenge option first (only if not already a revenge match)
    if not is_revenge:
        revenge_view = RevengeView(loser, winner, timeout, interaction.guild)
        await interaction.followup.send(
            f"🏆 **{winner.mention} GAGNE LE DUEL!** 🏆\n\n"
            f"💀 {loser.mention} va être timeout pour **{timeout} minute(s)**!\n"
            f"Dernière chance... 🔥",
            view=revenge_view
        )
        
        # Wait for revenge decision
        await revenge_view.wait()
        
        # If no revenge requested, apply timeout
        if not revenge_view.revenge_requested:
            try:
                await loser.timeout(timedelta(minutes=timeout), reason=f"A perdu contre {winner.display_name}")
                await interaction.followup.send(f"C'est ciao {loser.mention}! 👋")
                print(f"[DEBUG] {loser.name} timed out successfully (no revenge)")
            except discord.Forbidden:
                await interaction.followup.send(
                    f"⚠️ Mais je peux pas le ban, oupsi {loser.mention}. "
                    f"Faut me mettre les perms"
                )
                print(f"[DEBUG] Failed to timeout {loser.name} - missing permissions")
    else:
        # For revenge matches, timeout immediately (no second chance)
        try:
            await loser.timeout(timedelta(minutes=timeout), reason=f"A perdu la revanche contre {winner.display_name}")
            await interaction.followup.send(
                f"🏆 **{winner.mention} GAGNE LA REVANCHE!** 🏆\n\n"
                f"💀 {loser.mention} a été timeout pour **{timeout} minute(s)**!\n"
                f"Pas de seconde chance cette fois ! 👋"
            )
            print(f"[DEBUG] {loser.name} timed out successfully (revenge lost)")
        except discord.Forbidden:
            await interaction.followup.send(
                f"🏆 **{winner.mention} GAGNE LA REVANCHE!** 🏆\n\n"
                f"⚠️ Mais je peux pas le ban, oupsi {loser.mention}. "
                f"Faut me mettre les perms"
            )
            print(f"[DEBUG] Failed to timeout {loser.name} - missing permissions")
    
    # Clean up
    if player1.id in active_duels:
        del active_duels[player1.id]
    if player2.id in active_duels:
        del active_duels[player2.id]
    print(f"[DEBUG] Duel completed and cleaned up")

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
    
    if timeout < 1 or timeout > 10080:
        await interaction.response.send_message("Le timeout doit être entre 1 et 10080 minutes (1 semaine)!", ephemeral=True)
        return
    
    if interaction.user.id in active_duels or opponent.id in active_duels:
        await interaction.response.send_message("L'un de vous est déjà en duel", ephemeral=True)
        return
    
    # Mark players as in duel
    active_duels[interaction.user.id] = True
    active_duels[opponent.id] = True
    
    # Send challenge
    view = DuelView(interaction.user, opponent, timeout)
    await interaction.response.send_message(
        f"⚔️ **DUEL CHALLENGE** ⚔️\n"
        f"{interaction.user.mention} défie {opponent.mention} à un duel de Pierre-Papier-Ciseaux!\n"
        f"**Enjeu:** Le perdant se fait timeout pour **{timeout} minute(s)**\n"
        f"**Format:** BO3",
        view=view
    )
    
    # Wait for acceptance
    print(f"[DEBUG] Waiting for {opponent.name} to accept the duel...")
    await view.wait()
    
    if view.refused:
        print(f"[DEBUG] {opponent.name} refused the duel")
        await interaction.followup.send(f"{opponent.mention} a refusé le duel, bébé cadum ! 🐔")
        del active_duels[interaction.user.id]
        del active_duels[opponent.id]
        return
    
    if not view.accepted:
        print(f"[DEBUG] {opponent.name} didn't accept the duel (timeout)")
        await interaction.followup.send(f"{opponent.mention} n'a pas répondu au duel, bébé cadum !")
        del active_duels[interaction.user.id]
        del active_duels[opponent.id]
        return
    
    print(f"[DEBUG] Duel accepted! Starting game")
    
    # Start the game
    await start_duel_game(interaction, interaction.user, opponent, timeout, is_revenge=False)

# Run the bot
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not found in environment variables. Please check your .env file.")

bot.run(TOKEN)