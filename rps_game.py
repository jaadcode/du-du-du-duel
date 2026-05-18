import discord
import asyncio
from datetime import timedelta
from state import active_duels


class ConfirmHighStakesView(discord.ui.View):
    def __init__(self, challenger, challenged, timeout_minutes):
        super().__init__(timeout=30)
        self.challenger = challenger
        self.challenged = challenged
        self.timeout_minutes = timeout_minutes
        self.confirmed = False

    @discord.ui.button(label="OUI, je confirme !", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("C'est pas ton moment gamin", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.send_message(f"✅ {self.challenged.mention} a confirmé ! Le duel va commencer...")

    @discord.ui.button(label="Non, annuler", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Seul le challengé peut annuler !", ephemeral=True)
            return
        self.confirmed = False
        self.stop()
        await interaction.response.send_message(f"❌ {self.challenged.mention} a annulé le duel.")


class DuelView(discord.ui.View):
    def __init__(self, challenger, challenged, timeout_minutes):
        super().__init__(timeout=300)
        self.challenger = challenger
        self.challenged = challenged
        self.timeout_minutes = timeout_minutes
        self.accepted = False
        self.refused = False
        self.cancelled = False

    @discord.ui.button(label="Accepter le duel", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("C'est pas ton moment gamin", ephemeral=True)
            return

        if self.timeout_minutes > 120:
            confirm_view = ConfirmHighStakesView(self.challenger, self.challenged, self.timeout_minutes)
            await interaction.response.send_message(
                f"⚠️ **ATTENTION {self.challenged.mention} !**\n"
                f"Le timeout est de **{self.timeout_minutes} minutes** ({self.timeout_minutes // 60}h{self.timeout_minutes % 60}min) !\n"
                f"Es-tu SÛR d'accepter ??",
                view=confirm_view,
                ephemeral=False
            )
            await confirm_view.wait()
            if not confirm_view.confirmed:
                self.refused = True
                self.stop()
                return

        self.accepted = True
        self.stop()

        if self.timeout_minutes <= 120:
            await interaction.response.send_message(f"**DU-DU-DU-DUEL!** {self.challenged.mention} a accepté!", ephemeral=False)
        else:
            await interaction.followup.send(f"**DU-DU-DU-DUEL!** {self.challenged.mention} a accepté!", ephemeral=False)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.secondary, emoji="❌")
    async def refuse_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Seul le challengé peut refuser !", ephemeral=True)
            return
        self.refused = True
        self.stop()
        await interaction.response.send_message(f"❌ {self.challenged.mention} a refusé le duel, bébé cadum ! 🐔")

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="🚫")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message("Seul le lanceur peut annuler !", ephemeral=True)
            return
        self.cancelled = True
        self.stop()
        await interaction.response.send_message(f"🚫 {self.challenger.mention} a annulé le duel.")


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
            view=accept_view
        )

        await accept_view.wait()

        if accept_view.accepted:
            if self.loser.id in active_duels:
                del active_duels[self.loser.id]
            if self.winner.id in active_duels:
                del active_duels[self.winner.id]

            try:
                await revenge_msg.delete()
            except:
                pass

            await start_duel_game(interaction, self.loser, self.winner, doubled_timeout, is_revenge=True, original_loser=self.loser)
        else:
            try:
                await self.loser.timeout(timedelta(minutes=self.timeout_minutes), reason=f"A perdu contre {self.winner.display_name}")
                await interaction.followup.send(f"{self.loser.mention} reste timeout pour {self.timeout_minutes} minute(s). 👋")
                print(f"[DEBUG] {self.loser.name} timed out (revenge refused)")
            except discord.Forbidden:
                await interaction.followup.send(f"Je ne peux pas timeout {self.loser.mention}.")
                print(f"[DEBUG] Failed to timeout {self.loser.name} - missing permissions")

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
        await interaction.response.defer()
        await interaction.followup.send(
            f"✅ **{self.challenged.mention} accepte la revanche !**\n"
            f"🔥 **NOUVEAU DUEL !**"
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
    if choice1 == choice2:
        return 0
    wins = {"Pierre": "Ciseaux", "Papier": "Pierre", "Ciseaux": "Papier"}
    return 1 if wins[choice1] == choice2 else 2


async def start_duel_game(interaction, player1, player2, timeout, is_revenge=False, original_loser=None):
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

    print(f"[DEBUG] Deleting {len(messages_to_delete)} intermediate messages...")
    for msg in messages_to_delete:
        try:
            await msg.delete()
        except Exception as e:
            print(f"[DEBUG] Failed to delete message: {e}")

    if not is_revenge:
        revenge_view = RevengeView(loser, winner, timeout, interaction.guild)
        await interaction.followup.send(
            f"🏆 **{winner.mention} GAGNE LE DUEL!** 🏆\n\n"
            f"💀 {loser.mention} va être timeout pour **{timeout} minute(s)**!\n"
            f"Dernière chance... 🔥",
            view=revenge_view
        )

        await revenge_view.wait()

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
        if winner.id == original_loser.id:
            await interaction.followup.send(
                f"🏆 **{winner.mention} GAGNE LA REVANCHE!** 🏆\n\n"
                f"🎉 {winner.mention} s'est racheté ! Personne n'est timeout !\n"
                f"Respect ! 💪"
            )
            print(f"[DEBUG] {winner.name} won revenge - no timeout applied")
        else:
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

    if player1.id in active_duels:
        del active_duels[player1.id]
    if player2.id in active_duels:
        del active_duels[player2.id]
    print(f"[DEBUG] Duel completed and cleaned up")


async def start_rps_challenge(interaction, challenger, opponent, timeout_minutes):
    if challenger.id in active_duels or opponent.id in active_duels:
        await interaction.followup.send("L'un de vous est déjà en duel !", ephemeral=True)
        return

    active_duels[challenger.id] = True
    active_duels[opponent.id] = True

    view = DuelView(challenger, opponent, timeout_minutes)
    await interaction.followup.send(
        f"⚔️ **DUEL CHALLENGE** ⚔️\n"
        f"{challenger.mention} défie {opponent.mention} à un duel de Pierre-Papier-Ciseaux!\n"
        f"**Enjeu:** Le perdant se fait timeout pour **{timeout_minutes} minute(s)**\n"
        f"**Format:** BO3",
        view=view
    )

    print(f"[DEBUG] Waiting for {opponent.name} to accept the duel...")
    await view.wait()

    if view.refused:
        print(f"[DEBUG] {opponent.name} refused the duel")
        del active_duels[challenger.id]
        del active_duels[opponent.id]
        return

    if view.cancelled:
        print(f"[DEBUG] {challenger.name} cancelled the duel")
        del active_duels[challenger.id]
        del active_duels[opponent.id]
        return

    if not view.accepted:
        print(f"[DEBUG] {opponent.name} didn't accept the duel (timeout)")
        await interaction.followup.send(f"{opponent.mention} n'a pas répondu au duel, bébé cadum !")
        del active_duels[challenger.id]
        del active_duels[opponent.id]
        return

    print(f"[DEBUG] Duel accepted! Starting game")
    await start_duel_game(interaction, challenger, opponent, timeout_minutes, is_revenge=False)


class RPSTimeoutModal(discord.ui.Modal, title="⚔️ Durée du timeout"):
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
            await self.setup_message.edit(content="⚔️ **Duel en cours...**", view=None)
        except Exception:
            pass
        await start_rps_challenge(interaction, self.organizer, self.opponent, timeout_minutes)


class RPSSetupView(discord.ui.View):
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

    @discord.ui.button(label="Lancer le duel ⚔️", style=discord.ButtonStyle.danger, row=1)
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
            RPSTimeoutModal(self.organizer, self.opponent, interaction.message)
        )
