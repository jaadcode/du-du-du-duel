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
        self.cancelled = False

    @discord.ui.button(label="Rejoindre la partie", style=discord.ButtonStyle.success, emoji="✅", row=0)
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
            ephemeral=False,
        )

        all_ids = self.invited_ids | {self.organizer.id}
        if set(self.joined.keys()) >= all_ids:
            self.stop()

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="🚫", row=0)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.organizer.id:
            await interaction.response.send_message(
                "Seul l'organisateur peut annuler la partie !", ephemeral=True
            )
            return
        self.cancelled = True
        self.stop()
        await interaction.response.send_message("🚫 La Roulette Russe a été annulée.")

    async def on_timeout(self):
        self.stop()


class RouletteGameView(discord.ui.View):
    """Vue principale d'un tour : le joueur courant choisit sa cible."""

    def __init__(self, current_player, all_players):
        super().__init__(timeout=60)
        self.current_player = current_player
        self.all_players = all_players
        self.action = None   # "self" ou "other"
        self.target = None

    @discord.ui.button(label="Se tirer dessus", style=discord.ButtonStyle.danger, emoji="🔫", row=0)
    async def shoot_self_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.current_player.id:
            await interaction.response.send_message("C'est pas ton tour !", ephemeral=True)
            return
        self.action = "self"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Tirer sur quelqu'un", style=discord.ButtonStyle.secondary, emoji="🎯", row=0)
    async def shoot_other_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.current_player.id:
            await interaction.response.send_message("C'est pas ton tour !", ephemeral=True)
            return

        others = [p for p in self.all_players if p.id != self.current_player.id]
        target_view = RouletteTargetView(self.current_player, others)
        await interaction.response.send_message(
            "🎯 Qui vises-tu ?",
            view=target_view,
            ephemeral=True,
        )

        await target_view.wait()

        if target_view.selected is not None:
            self.action = "other"
            self.target = target_view.selected
            self.stop()

    async def on_timeout(self):
        self.stop()


class RouletteTargetSelect(discord.ui.Select):
    def __init__(self, shooter, targets):
        self.shooter = shooter
        self.targets_map = {str(t.id): t for t in targets}
        options = [
            discord.SelectOption(label=t.display_name, value=str(t.id))
            for t in targets
        ]
        super().__init__(placeholder="Choisir une cible...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.shooter.id:
            await interaction.response.send_message("C'est pas ton tour !", ephemeral=True)
            return
        self.view.selected = self.targets_map[self.values[0]]
        self.view.stop()
        await interaction.response.defer()


class RouletteTargetView(discord.ui.View):
    def __init__(self, shooter, targets):
        super().__init__(timeout=30)
        self.selected = None
        self.add_item(RouletteTargetSelect(shooter, targets))

    async def on_timeout(self):
        self.stop()


def _cylinder_display(shots_fired: int) -> str:
    """💨 = chambre vide (déjà tirée), 🔘 = chambre restante."""
    return "💨" * shots_fired + "🔘" * (6 - shots_fired)


async def _apply_death(interaction, victim, timeout_minutes):
    await interaction.followup.send(
        f"💥 **BANG !!** 💥\n\n"
        f"💀 {victim.mention} a pris la balle !\n"
        f"Timeout de **{timeout_minutes} minute(s)** appliqué... RIP 👋"
    )
    try:
        await victim.timeout(timedelta(minutes=timeout_minutes), reason="Éliminé à la Roulette Russe")
        print(f"[DEBUG] {victim.name} timed out via Russian Roulette")
    except discord.Forbidden:
        await interaction.followup.send(f"⚠️ Je peux pas timeout {victim.mention}, faut me donner les perms.")
        print(f"[DEBUG] Failed to timeout {victim.name} - missing permissions")


async def start_roulette_game(interaction, organizer, joined: dict, timeout_minutes: int):
    players = list(joined.values())

    for p in players:
        active_duels[p.id] = True

    current_player = random.choice(players)
    shots_fired = 0  # probabilité du prochain tir = 1 / (6 - shots_fired)

    player_list = " | ".join(p.mention for p in players)
    await interaction.followup.send(
        f"🔫 **LA ROULETTE RUSSE COMMENCE !** 🔫\n\n"
        f"**Joueurs :** {player_list}\n"
        f"**Timeout du perdant :** {timeout_minutes} minute(s)\n\n"
        f"Le revolver a **6 chambres**, une seule balle.\n"
        f"Plus on survit, plus le risque augmente.\n\n"
        f"Le premier joueur désigné est... {current_player.mention} ! 🎯"
    )

    await asyncio.sleep(3)

    victim = None

    while victim is None:
        remaining = 6 - shots_fired
        is_last = remaining == 1

        if is_last:
            await interaction.followup.send(
                f"☠️ **DERNIÈRE CHAMBRE.** La balle est forcément là... quelqu'un va mourir."
            )
            await asyncio.sleep(2)

        game_view = RouletteGameView(current_player, players)
        msg = await interaction.followup.send(
            f"**Barillet :** {_cylinder_display(shots_fired)}\n"
            f"🎯 **{current_player.mention}**, c'est ton tour !\n"
            f"Probabilité : **1/{remaining}**{'  ☠️' if is_last else ''}\n\n"
            f"Que fais-tu ?",
            view=game_view,
        )

        await game_view.wait()

        # Message de suspense (enlève les boutons, crée de la tension)
        if game_view.action is None or game_view.action == "self":
            suspense = f"🔫 *{current_player.display_name} appuie sur la gâchette...*"
        else:
            suspense = f"🎯 *{current_player.display_name} vise...*"

        try:
            await msg.edit(content=suspense, view=None)
        except Exception:
            pass

        await asyncio.sleep(1.5)

        try:
            await msg.delete()
        except Exception:
            pass

        # Timeout → tir forcé sur soi
        if game_view.action is None:
            await interaction.followup.send(
                f"⏰ {current_player.mention} hésite trop... **le revolver part tout seul !**"
            )
            game_view.action = "self"

        shots_fired += 1
        hit = random.randint(1, remaining) == 1

        if shots_fired < 6:
            next_prob = f"**1/{6 - shots_fired}**"
        else:
            next_prob = "**1/1** ☠️ (mort certaine)"

        if game_view.action == "self":
            if hit:
                victim = current_player
                await _apply_death(interaction, victim, timeout_minutes)
            else:
                await interaction.followup.send(
                    f"*click* 😮‍💨 {current_player.mention} a survécu...\n"
                    f"{_cylinder_display(shots_fired)}  →  prochain tir : {next_prob}"
                )
                await asyncio.sleep(1.5)

        else:  # "other"
            target = game_view.target
            if hit:
                victim = target
                await interaction.followup.send(
                    f"💥 **{current_player.mention}** tire sur **{target.mention}** !"
                )
                await asyncio.sleep(1)
                await _apply_death(interaction, victim, timeout_minutes)
            else:
                await interaction.followup.send(
                    f"*click* 😮‍💨 **{current_player.mention}** tire sur **{target.mention}**... et le rate !\n"
                    f"{_cylinder_display(shots_fired)}  →  prochain tir : {next_prob}\n"
                    f"C'est maintenant au tour de {target.mention} 🎯"
                )
                await asyncio.sleep(1.5)
                current_player = target

    for p in players:
        if p.id in active_duels:
            del active_duels[p.id]

    print(f"[DEBUG] Russian Roulette done. Victim: {victim.name}")


class RouletteTimeoutModal(discord.ui.Modal, title="🔫 Timeout du perdant"):
    timeout_input = discord.ui.TextInput(
        label="Durée du timeout (1–30 minutes)",
        placeholder="Ex: 5, 10, 15...",
        required=True,
        max_length=2,
    )

    def __init__(self, organizer, valid_players, setup_message):
        super().__init__()
        self.organizer = organizer
        self.valid_players = valid_players
        self.setup_message = setup_message

    async def on_submit(self, interaction: discord.Interaction):
        try:
            timeout_minutes = int(self.timeout_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "Le timeout doit être un nombre entier !", ephemeral=True
            )
            return

        if not (1 <= timeout_minutes <= 30):
            await interaction.response.send_message(
                "Le timeout doit être entre 1 et 30 minutes.", ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            await self.setup_message.edit(content="🔫 **Roulette Russe en cours...**", view=None)
        except Exception:
            pass

        mentions = " ".join(p.mention for p in self.valid_players)
        join_view = RouletteJoinView(self.organizer, self.valid_players)
        await interaction.followup.send(
            f"🔫 **ROULETTE RUSSE !**\n\n"
            f"{self.organizer.mention} lance une partie de Roulette Russe !\n"
            f"**Joueurs invités :** {mentions}\n"
            f"**Timeout du perdant :** {timeout_minutes} minute(s)\n\n"
            f"Vous avez **60 secondes** pour rejoindre ✅\n"
            f"*(Les absents ne jouent pas — minimum 2 joueurs pour démarrer)*",
            view=join_view,
        )

        await join_view.wait()

        if join_view.cancelled:
            return

        joined_players = join_view.joined
        if len(joined_players) < 2:
            await interaction.followup.send("Pas assez de joueurs (minimum 2). Roulette annulée !")
            return

        await start_roulette_game(interaction, self.organizer, joined_players, timeout_minutes)


class RouletteSetupView(discord.ui.View):
    def __init__(self, organizer):
        super().__init__(timeout=60)
        self.organizer = organizer
        self.players = []

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choisir les autres joueurs (1 à 5)...",
        min_values=1,
        max_values=5,
        row=0,
    )
    async def select_players(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.organizer.id:
            await interaction.response.send_message("C'est pas ta roulette !", ephemeral=True)
            return
        self.players = select.values
        await interaction.response.defer()

    @discord.ui.button(label="Lancer la Roulette 🔫", style=discord.ButtonStyle.danger, row=1)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.organizer.id:
            await interaction.response.send_message("C'est pas ta roulette !", ephemeral=True)
            return

        if not self.players:
            await interaction.response.send_message("Choisis au moins un joueur !", ephemeral=True)
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
        await interaction.response.send_modal(
            RouletteTimeoutModal(self.organizer, valid_players, interaction.message)
        )
