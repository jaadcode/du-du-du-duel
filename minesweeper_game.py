import discord
import asyncio
import random
from datetime import timedelta
from state import active_duels
from rps_game import DuelView, AcceptRevengeView

GRID_SIZE = 5
MINE_COUNT = 5
SAFE_COUNT = GRID_SIZE * GRID_SIZE - MINE_COUNT  # 20


class MinesweeperButton(discord.ui.Button):
    def __init__(self, grid_row: int, grid_col: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="⬜",
            row=grid_row,
        )
        self.grid_row = grid_row
        self.grid_col = grid_col

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_click(interaction, self.grid_row, self.grid_col)


class MinesweeperView(discord.ui.View):
    def __init__(self, player1, player2):
        super().__init__(timeout=300)
        self.player1 = player1
        self.player2 = player2
        self.current_player = random.choice([player1, player2])
        self.loser = None
        self.draw = False

        all_cells = [(r, c) for r in range(GRID_SIZE) for c in range(GRID_SIZE)]
        self.mines: set = set(map(tuple, random.sample(all_cells, MINE_COUNT)))
        self.revealed: set = set()

        self.adjacency: dict = {}
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if (r, c) not in self.mines:
                    self.adjacency[(r, c)] = sum(
                        1
                        for dr in (-1, 0, 1)
                        for dc in (-1, 0, 1)
                        if (dr, dc) != (0, 0) and (r + dr, c + dc) in self.mines
                    )

        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                self.add_item(MinesweeperButton(r, c))

    def _btn(self, row: int, col: int):
        for item in self.children:
            if isinstance(item, MinesweeperButton) and item.grid_row == row and item.grid_col == col:
                return item
        return None

    def get_status_text(self) -> str:
        safe_revealed = sum(1 for c in self.revealed if c not in self.mines)
        return (
            f"💣 **Démineur** — {safe_revealed}/{SAFE_COUNT} cases sûres révélées\n"
            f"Tour de {self.current_player.mention}"
        )

    def _reveal_cell(self, row: int, col: int):
        btn = self._btn(row, col)
        if btn is None:
            return
        adj = self.adjacency.get((row, col), 0)
        btn.label = str(adj) if adj > 0 else "·"
        btn.style = discord.ButtonStyle.secondary
        btn.disabled = True

    def _freeze_grid(self, hit_mine: tuple = None):
        """Disable everything and reveal all mines at game end."""
        for item in self.children:
            if not isinstance(item, MinesweeperButton):
                continue
            r, c = item.grid_row, item.grid_col
            if (r, c) in self.mines:
                item.style = discord.ButtonStyle.danger
                item.label = "💥" if (r, c) == hit_mine else "💣"
            elif (r, c) in self.revealed:
                adj = self.adjacency.get((r, c), 0)
                item.label = str(adj) if adj > 0 else "·"
                item.style = discord.ButtonStyle.secondary
            item.disabled = True

    async def handle_click(self, interaction: discord.Interaction, row: int, col: int):
        if interaction.user.id != self.current_player.id:
            await interaction.response.send_message("C'est pas ton tour !", ephemeral=True)
            return

        if (row, col) in self.revealed:
            await interaction.response.send_message("Cette case est déjà révélée !", ephemeral=True)
            return

        self.revealed.add((row, col))

        if (row, col) in self.mines:
            self.loser = self.current_player
            self._freeze_grid(hit_mine=(row, col))
            await interaction.response.edit_message(
                content=(
                    f"💣 **Démineur**\n"
                    f"💥 **{self.current_player.mention} a déclenché une mine !**"
                ),
                view=self,
            )
            self.stop()
            return

        safe_revealed = sum(1 for c in self.revealed if c not in self.mines)

        if safe_revealed == SAFE_COUNT:
            self.draw = True
            self._freeze_grid()
            await interaction.response.edit_message(
                content=(
                    f"💣 **Démineur** — {safe_revealed}/{SAFE_COUNT} cases sûres révélées\n"
                    f"🎉 **Match nul ! Toutes les cases sûres ont été révélées.**"
                ),
                view=self,
            )
            self.stop()
            return

        self._reveal_cell(row, col)
        self.current_player = (
            self.player2 if self.current_player.id == self.player1.id else self.player1
        )
        await interaction.response.edit_message(
            content=self.get_status_text(),
            view=self,
        )

    async def on_timeout(self):
        self.stop()


class MinesweeperRevengeView(discord.ui.View):
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
        doubled_timeout = min(self.timeout_minutes * 2, 10080)

        button.disabled = True
        await interaction.response.edit_message(view=self)

        accept_view = AcceptRevengeView(self.loser, self.winner)
        revenge_msg = await interaction.followup.send(
            f"💀 **{self.loser.mention} demande une REVANCHE !**\n"
            f"🔥 **Quitte ou Double** :\n"
            f"• Si {self.loser.mention} **perd** → timeout de **{doubled_timeout} minutes** !\n"
            f"• Si {self.loser.mention} **gagne** → il est libéré, aucune sanction !\n"
            f"• {self.winner.mention} ne risque **RIEN** !\n\n"
            f"{self.winner.mention}, acceptes-tu ?",
            view=accept_view,
        )

        await accept_view.wait()

        if accept_view.accepted:
            if self.loser.id in active_duels:
                del active_duels[self.loser.id]
            if self.winner.id in active_duels:
                del active_duels[self.winner.id]
            try:
                await revenge_msg.delete()
            except Exception:
                pass
            await start_minesweeper_game(
                interaction, self.loser, self.winner, doubled_timeout,
                is_revenge=True, original_loser=self.loser,
            )
        else:
            try:
                await self.loser.timeout(
                    timedelta(minutes=self.timeout_minutes),
                    reason=f"A perdu contre {self.winner.display_name}",
                )
                await interaction.followup.send(
                    f"{self.loser.mention} reste timeout pour {self.timeout_minutes} minute(s). 👋"
                )
            except discord.Forbidden:
                await interaction.followup.send(f"Je ne peux pas timeout {self.loser.mention}.")

    @discord.ui.button(label="Abandonner", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def abandon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.loser.id:
            await interaction.response.send_message("Seul le perdant peut abandonner !", ephemeral=True)
            return

        self.abandoned = True
        self.stop()

        button.disabled = True
        await interaction.response.edit_message(view=self)

        try:
            await self.loser.timeout(
                timedelta(minutes=self.timeout_minutes),
                reason=f"A perdu contre {self.winner.display_name}",
            )
            await interaction.followup.send(
                f"{self.loser.mention} accepte sa défaite. Timeout de {self.timeout_minutes} minute(s) appliqué. 👋"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"{self.loser.mention} accepte sa défaite mais je ne peux pas le timeout."
            )


async def start_minesweeper_game(
    interaction, player1, player2, timeout, is_revenge=False, original_loser=None
):
    active_duels[player1.id] = True
    active_duels[player2.id] = True

    game_view = MinesweeperView(player1, player2)

    await interaction.followup.send(
        content=game_view.get_status_text(),
        view=game_view,
    )

    print(f"[DEBUG] Minesweeper started: {player1.name} vs {player2.name}")
    await game_view.wait()

    # Timeout sans résultat (partie abandonnée)
    if game_view.loser is None and not game_view.draw:
        await interaction.followup.send(
            "⏰ Partie abandonnée (personne n'a joué). Aucun timeout appliqué."
        )
        if player1.id in active_duels:
            del active_duels[player1.id]
        if player2.id in active_duels:
            del active_duels[player2.id]
        return

    if game_view.draw:
        await interaction.followup.send(
            "🎉 **Match nul !** Toutes les cases sûres ont été révélées. Personne n'est timeout."
        )
        del active_duels[player1.id]
        del active_duels[player2.id]
        return

    loser = game_view.loser
    winner = player2 if loser.id == player1.id else player1

    print(f"[DEBUG] Minesweeper over. Winner: {winner.name}, Loser: {loser.name}")

    if not is_revenge:
        revenge_view = MinesweeperRevengeView(loser, winner, timeout, interaction.guild)
        await interaction.followup.send(
            f"💣 **{winner.mention} GAGNE !** 💣\n\n"
            f"💀 {loser.mention} va être timeout pour **{timeout} minute(s)** !\n"
            f"Dernière chance... 🔥",
            view=revenge_view,
        )

        await revenge_view.wait()

        if not revenge_view.revenge_requested:
            try:
                await loser.timeout(
                    timedelta(minutes=timeout),
                    reason=f"A perdu au Démineur contre {winner.display_name}",
                )
                await interaction.followup.send(f"C'est ciao {loser.mention} ! 👋")
                print(f"[DEBUG] {loser.name} timed out (no revenge)")
            except discord.Forbidden:
                await interaction.followup.send(
                    f"⚠️ Je peux pas timeout {loser.mention}. Faut me mettre les perms."
                )
    else:
        if winner.id == original_loser.id:
            await interaction.followup.send(
                f"💣 **{winner.mention} GAGNE LA REVANCHE !** 💣\n\n"
                f"🎉 {winner.mention} s'est racheté ! Personne n'est timeout !\n"
                f"Respect ! 💪"
            )
            print(f"[DEBUG] {winner.name} won minesweeper revenge - no timeout")
        else:
            try:
                await loser.timeout(
                    timedelta(minutes=timeout),
                    reason=f"A perdu la revanche au Démineur contre {winner.display_name}",
                )
                await interaction.followup.send(
                    f"💣 **{winner.mention} GAGNE LA REVANCHE !** 💣\n\n"
                    f"💀 {loser.mention} a été timeout pour **{timeout} minute(s)** !\n"
                    f"Pas de seconde chance cette fois ! 👋"
                )
                print(f"[DEBUG] {loser.name} timed out (revenge lost)")
            except discord.Forbidden:
                await interaction.followup.send(
                    f"💣 **{winner.mention} GAGNE LA REVANCHE !** 💣\n\n"
                    f"⚠️ Je peux pas timeout {loser.mention}. Faut me mettre les perms."
                )

    if player1.id in active_duels:
        del active_duels[player1.id]
    if player2.id in active_duels:
        del active_duels[player2.id]
    print("[DEBUG] Minesweeper cleaned up")


async def start_minesweeper_challenge(interaction, challenger, opponent, timeout_minutes):
    if challenger.id in active_duels or opponent.id in active_duels:
        await interaction.followup.send("L'un de vous est déjà en duel !", ephemeral=True)
        return

    active_duels[challenger.id] = True
    active_duels[opponent.id] = True

    view = DuelView(challenger, opponent, timeout_minutes)
    await interaction.followup.send(
        f"💣 **DÉMINEUR CHALLENGE** 💣\n"
        f"{challenger.mention} défie {opponent.mention} au Démineur !\n"
        f"**Enjeu :** Le perdant se fait timeout pour **{timeout_minutes} minute(s)**\n"
        f"**Format :** Grille 5×5, 5 mines",
        view=view,
    )

    await view.wait()

    if view.refused:
        del active_duels[challenger.id]
        del active_duels[opponent.id]
        return

    if view.cancelled:
        del active_duels[challenger.id]
        del active_duels[opponent.id]
        return

    if not view.accepted:
        await interaction.followup.send(f"{opponent.mention} n'a pas répondu au défi, bébé cadum !")
        del active_duels[challenger.id]
        del active_duels[opponent.id]
        return

    await start_minesweeper_game(interaction, challenger, opponent, timeout_minutes)


class MinesweeperTimeoutModal(discord.ui.Modal, title="💣 Durée du timeout"):
    timeout_input = discord.ui.TextInput(
        label="Durée du timeout (en minutes)",
        placeholder="Ex: 5, 10, 60...  (max 10080 = 1 semaine)",
        required=True,
        max_length=5,
    )

    def __init__(self, organizer, opponent, setup_message):
        super().__init__()
        self.organizer = organizer
        self.opponent = opponent
        self.setup_message = setup_message

    async def on_submit(self, interaction: discord.Interaction):
        try:
            timeout_minutes = int(self.timeout_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "Le timeout doit être un nombre entier !", ephemeral=True
            )
            return

        if not (1 <= timeout_minutes <= 10080):
            await interaction.response.send_message(
                "Le timeout doit être entre 1 et 10080 minutes (1 semaine max).", ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            await self.setup_message.edit(content="💣 **Démineur en cours...**", view=None)
        except Exception:
            pass
        await start_minesweeper_challenge(interaction, self.organizer, self.opponent, timeout_minutes)


class MinesweeperSetupView(discord.ui.View):
    def __init__(self, organizer):
        super().__init__(timeout=60)
        self.organizer = organizer
        self.opponent = None

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choisir un adversaire...",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def select_opponent(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.organizer.id:
            await interaction.response.send_message("C'est pas ton duel !", ephemeral=True)
            return
        self.opponent = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Lancer le Démineur 💣", style=discord.ButtonStyle.success, row=1)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.organizer.id:
            await interaction.response.send_message("C'est pas ton duel !", ephemeral=True)
            return

        if self.opponent is None:
            await interaction.response.send_message("Choisis un adversaire d'abord !", ephemeral=True)
            return

        if self.opponent.id == self.organizer.id:
            await interaction.response.send_message("Tu peux pas te défier toi-même !", ephemeral=True)
            return

        if self.opponent.bot:
            await interaction.response.send_message("C'est un bot hein...", ephemeral=True)
            return

        self.stop()
        await interaction.response.send_modal(
            MinesweeperTimeoutModal(self.organizer, self.opponent, interaction.message)
        )
