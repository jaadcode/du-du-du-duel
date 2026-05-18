import discord
import asyncio
import random
from datetime import timedelta
from state import active_duels


class RouletteJoinView(discord.ui.View):
    def __init__(self, organizer, invited_players):
        super().__init__(timeout=60)
        self.organizer = organizer
        self.invited_ids = {p.id for p in invited_players}
        self.joined = {organizer.id: organizer}
        self.message = None

    @discord.ui.button(label="Rejoindre la partie", style=discord.ButtonStyle.success, emoji="✅")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id

        if uid not in self.invited_ids and uid != self.organizer.id:
            await interaction.response.send_message("T'es pas invité !", ephemeral=True)
            return

        if uid in self.joined:
            await interaction.response.send_message("T'es déjà dans la partie !", ephemeral=True)
            return

        self.joined[uid] = interaction.user
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} a chargé le revolver...",
            ephemeral=False
        )

        all_ids = self.invited_ids | {self.organizer.id}
        if set(self.joined.keys()) >= all_ids:
            self.stop()

    async def on_timeout(self):
        self.stop()


class RouletteTriggerView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=30)
        self.player = player
        self.triggered = False

    @discord.ui.button(label="Appuyer sur la gâchette", style=discord.ButtonStyle.danger, emoji="🔫")
    async def trigger_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("C'est pas ton tour !", ephemeral=True)
            return

        self.triggered = True
        self.stop()
        await interaction.response.defer()

    async def on_timeout(self):
        self.stop()


async def start_roulette_game(interaction, organizer, joined: dict, timeout_minutes: int):
    players = list(joined.values())
    random.shuffle(players)

    for p in players:
        active_duels[p.id] = True

    order_text = " → ".join(p.mention for p in players)
    await interaction.followup.send(
        f"🔫 **LA ROULETTE RUSSE COMMENCE !** 🔫\n\n"
        f"**Joueurs :** {order_text}\n"
        f"**Ordre aléatoire :** {order_text}\n"
        f"**Risque :** 1 chance sur 6 à chaque tour (probabilité fixe)\n"
        f"**Sanction :** Timeout de **{timeout_minutes} minute(s)** pour le perdant\n\n"
        f"Que le meilleur survive... 💀"
    )

    await asyncio.sleep(3)

    victim = None
    rounds_played = 0
    max_rounds = 25  # safety valve, statistically almost impossible to reach

    while victim is None and rounds_played < max_rounds:
        rounds_played += 1
        for player in players:
            trigger_view = RouletteTriggerView(player)
            msg = await interaction.followup.send(
                f"🎯 **{player.mention}**, c'est ton tour...\n"
                f"Prends le revolver et appuie sur la gâchette.",
                view=trigger_view
            )

            await trigger_view.wait()

            try:
                await msg.delete()
            except Exception:
                pass

            shot = random.randint(1, 6) == 1

            if shot:
                victim = player
                await interaction.followup.send(
                    f"💥 **BANG !!** 💥\n\n"
                    f"💀 {player.mention} a pris la balle !\n"
                    f"Timeout de **{timeout_minutes} minute(s)** appliqué... RIP 👋"
                )
                try:
                    await player.timeout(
                        timedelta(minutes=timeout_minutes),
                        reason="Éliminé à la Roulette Russe"
                    )
                    print(f"[DEBUG] {player.name} timed out via Russian Roulette")
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"⚠️ Je peux pas timeout {player.mention}, faut me donner les perms."
                    )
                    print(f"[DEBUG] Failed to timeout {player.name} - missing permissions")
                break
            else:
                await interaction.followup.send(
                    f"*click* 😮‍💨 {player.mention} a survécu... pour cette fois."
                )
                await asyncio.sleep(1.5)

    if victim is None:
        await interaction.followup.send(
            "🍀 Personne n'est mort après tous ces tours... la balle a disparu ?"
        )

    for p in players:
        if p.id in active_duels:
            del active_duels[p.id]

    print(f"[DEBUG] Russian Roulette done. Victim: {victim.name if victim else 'None'}")


class RouletteSetupView(discord.ui.View):
    def __init__(self, organizer):
        super().__init__(timeout=60)
        self.organizer = organizer
        self.players = []
        self.timeout_minutes = None

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choisir les autres joueurs (1 à 5)...",
        min_values=1,
        max_values=5,
        row=0
    )
    async def select_players(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.organizer.id:
            await interaction.response.send_message("C'est pas ta roulette !", ephemeral=True)
            return
        self.players = select.values
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Choisir le timeout du perdant (1–30 min)...",
        options=[
            discord.SelectOption(label="1 minute", value="1"),
            discord.SelectOption(label="2 minutes", value="2"),
            discord.SelectOption(label="5 minutes", value="5"),
            discord.SelectOption(label="10 minutes", value="10"),
            discord.SelectOption(label="15 minutes", value="15"),
            discord.SelectOption(label="20 minutes", value="20"),
            discord.SelectOption(label="30 minutes", value="30"),
        ],
        row=1
    )
    async def select_timeout(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.organizer.id:
            await interaction.response.send_message("C'est pas ta roulette !", ephemeral=True)
            return
        self.timeout_minutes = int(select.values[0])
        await interaction.response.defer()

    @discord.ui.button(label="Lancer la Roulette 🔫", style=discord.ButtonStyle.danger, row=2)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.organizer.id:
            await interaction.response.send_message("C'est pas ta roulette !", ephemeral=True)
            return

        if not self.players:
            await interaction.response.send_message("Choisis au moins un joueur !", ephemeral=True)
            return

        if self.timeout_minutes is None:
            await interaction.response.send_message("Choisis un timeout d'abord !", ephemeral=True)
            return

        valid_players = [p for p in self.players if not p.bot and p.id != self.organizer.id]

        if not valid_players:
            await interaction.response.send_message(
                "Aucun joueur valide (pas de bots, pas toi-même) !", ephemeral=True
            )
            return

        all_participants = valid_players + [self.organizer]
        for p in all_participants:
            if p.id in active_duels:
                await interaction.response.send_message(
                    f"{p.mention} est déjà en duel !", ephemeral=True
                )
                return

        self.stop()
        await interaction.response.edit_message(content="🔫 **Roulette Russe en cours...**", view=None)

        mentions = " ".join(p.mention for p in valid_players)
        join_view = RouletteJoinView(self.organizer, valid_players)
        await interaction.followup.send(
            f"🔫 **ROULETTE RUSSE !**\n\n"
            f"{self.organizer.mention} lance une partie de Roulette Russe !\n"
            f"**Joueurs invités :** {mentions}\n"
            f"**Timeout du perdant :** {self.timeout_minutes} minute(s)\n\n"
            f"Vous avez **60 secondes** pour rejoindre ✅\n"
            f"*(Les absents ne jouent pas — minimum 2 joueurs pour démarrer)*",
            view=join_view
        )

        await join_view.wait()

        joined_players = join_view.joined

        if len(joined_players) < 2:
            await interaction.followup.send(
                "Pas assez de joueurs (minimum 2). Roulette annulée !"
            )
            return

        await start_roulette_game(interaction, self.organizer, joined_players, self.timeout_minutes)
