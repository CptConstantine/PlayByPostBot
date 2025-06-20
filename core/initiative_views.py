import discord
from discord import ui, SelectOption
from data import repo
from core.models import BaseInitiativeView
from core.initiative_types import GenericInitiative, PopcornInitiative

class GenericInitiativeView(BaseInitiativeView):
    """
    View for generic initiative: End Turn button, shows current participant.
    """
    def __init__(self, guild_id, channel_id, initiative: GenericInitiative):
        super().__init__(guild_id, channel_id, initiative)
        self.gm_ids = repo.get_gm_ids(guild_id)
        self.allowed_ids = list(self.gm_ids) # Only GM can start initiative
        
        if not initiative.is_started:
            self.add_item(StartInitiativeButton(self))
        else:
            # Find the owner ID of the current participant and add it to allowed_ids
            current_participant = next((p for p in initiative.participants 
                                      if p.id == initiative.current), None)
            
            if current_participant and current_participant.owner_id:
                self.allowed_ids.append(current_participant.owner_id)  # Add owner ID instead of character ID
                
            self.add_item(EndTurnButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the current participant's owner or GM to interact
        return str(interaction.user.id) in self.allowed_ids

    async def update_view(self, interaction: discord.Interaction):
        new_view = GenericInitiativeView(self.guild_id, self.channel_id, self.initiative)
        if not self.initiative.is_started:
            await interaction.response.send_message(
                content="GM: Press Start to begin initiative.",
                view=new_view
            )
        elif not self.initiative.participants:
            await interaction.response.send_message(
                content="No participants in initiative.",
                view=None
            )
        else:
            name = self.initiative.get_participant_name(self.initiative.current)
            await interaction.response.send_message(
                content=f"🔔 It's now **{name}**'s turn! (Round {self.initiative.round_number})",
                view=new_view
            )

class StartInitiativeButton(ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="Start Initiative", style=discord.ButtonStyle.success)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # Retrieve the initiative dict from the repo
        initiative_data = repo.get_initiative(self.parent_view.guild_id, self.parent_view.channel_id)
        initiative = GenericInitiative.from_dict(initiative_data["initiative_state"])
        initiative.is_started = True
        initiative.current_index = 0
        self.parent_view.initiative = initiative
        repo.update_initiative_state(self.parent_view.guild_id, self.parent_view.channel_id, initiative.to_dict())
        await self.parent_view.update_view(interaction)

class EndTurnButton(ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="End Turn", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        initiative = self.parent_view.initiative
        initiative.advance_turn()
        repo.update_initiative_state(self.parent_view.guild_id, self.parent_view.channel_id, initiative.to_dict())
        await self.parent_view.update_view(interaction)

class PopcornInitiativeView(BaseInitiativeView):
    """
    Handles both the initial GM pick and the ongoing popcorn initiative.
    """
    def __init__(self, guild_id, channel_id, initiative: PopcornInitiative):
        super().__init__(guild_id, channel_id, initiative)
        self.gm_ids = repo.get_gm_ids(guild_id)
        self.allowed_ids = list(self.gm_ids)  # GMs are always allowed
        
        # If there's a current participant, find their owner_id 
        if initiative.current:
            current_participant = next((p for p in initiative.participants 
                                      if p.id == initiative.current), None)
            if current_participant and current_participant.owner_id:
                self.allowed_ids.append(current_participant.owner_id)

        # If initiative.current is None, it's the first pick (GM chooses)
        if initiative.current is None:
            unique_participants = {}
            for p in initiative.participants:
                unique_participants[p.id] = p
            options = [SelectOption(label=p.name, value=p.id) for p in unique_participants.values()]
            self.add_item(FirstPickerSelect(options, self))
        else:
            options = []
            # If it's the end of the round, allow picking anyone (including yourself)
            if initiative.is_round_end():
                for p in initiative.participants:
                    options.append(SelectOption(label=p.name, value=p.id))
            else:
                for pid in initiative.remaining_in_round:
                    name = initiative.get_participant_name(pid)
                    options.append(SelectOption(label=name, value=pid))
            if options:
                self.add_item(PopcornNextSelect(options, self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the current participant's owner or GM to interact
        return str(interaction.user.id) in self.allowed_ids

    async def update_view(self, interaction: discord.Interaction):
        new_view = PopcornInitiativeView(self.guild_id, self.channel_id, self.initiative)
        # Show "Round X!" at the start of a round (when remaining_in_round was just reset)
        if self.initiative.is_round_end():
            await interaction.response.send_message(
                content=f"**Round {self.initiative.round_number}!**\nPick who goes first.",
                view=new_view
            )
        elif self.initiative.current:
            next_name = self.initiative.get_participant_name(self.initiative.current)
            await interaction.response.send_message(
                content=f"🔔 It's now **{next_name}**'s turn!",
                view=new_view
            )
        else:
            await interaction.response.send_message(
                content="GM: Pick who goes first.",
                view=new_view
            )

class FirstPickerSelect(ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="Pick who goes first...", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        first_id = self.values[0]
        initiative = self.parent_view.initiative
        # Set the first turn
        initiative.current = first_id
        initiative.remaining_in_round = [p.id for p in initiative.participants if p.id != first_id]
        # Save updated initiative state to DB
        repo.update_initiative_state(self.parent_view.guild_id, self.parent_view.channel_id, initiative.to_dict())
        await self.parent_view.update_view(interaction)

class PopcornNextSelect(ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="Pick who goes next...", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        next_id = self.values[0]
        initiative = self.parent_view.initiative
        initiative.advance_turn(next_id)
        repo.update_initiative_state(self.parent_view.guild_id, self.parent_view.channel_id, initiative.to_dict())
        await self.parent_view.update_view(interaction)