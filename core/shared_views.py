import re
import discord
from discord import Interaction, TextStyle, ui
from core import factories
from core.models import BaseCharacter, RollModifiers
from core.utils import get_character, roll_formula
from data import repo

class PaginatedSelectView(ui.View):
    def __init__(self, options, select_callback, user_id, prompt="Select an option:", page=0, page_size=25):
        super().__init__(timeout=60)
        self.options = options
        self.select_callback = select_callback  # function(view, interaction, value)
        self.user_id = user_id
        self.prompt = prompt
        self.page = page
        self.page_size = page_size

        page_options = options[page*page_size:(page+1)*page_size]
        self.add_item(PaginatedSelect(page_options, self))

        if page > 0:
            self.add_item(PaginatedPrevButton(self))
        if (page+1)*page_size < len(options):
            self.add_item(PaginatedNextButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

class PaginatedSelect(ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="Select...", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        await self.parent_view.select_callback(self.parent_view, interaction, value)

class PaginatedPrevButton(ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="Previous", style=discord.ButtonStyle.secondary, row=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=self.parent_view.prompt,
            view=PaginatedSelectView(
                self.parent_view.options,
                self.parent_view.select_callback,
                self.parent_view.user_id,
                self.parent_view.prompt,
                page=self.parent_view.page - 1,
                page_size=self.parent_view.page_size
            )
        )

class PaginatedNextButton(ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="Next", style=discord.ButtonStyle.secondary, row=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=self.parent_view.prompt,
            view=PaginatedSelectView(
                self.parent_view.options,
                self.parent_view.select_callback,
                self.parent_view.user_id,
                self.parent_view.prompt,
                page=self.parent_view.page + 1,
                page_size=self.parent_view.page_size
            )
        )

class SceneNotesEditView(discord.ui.View):
    def __init__(self, guild_id, is_gm):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.is_gm = is_gm
        if is_gm:
            self.add_item(SceneNotesButton(guild_id))

class SceneNotesButton(discord.ui.Button):
    def __init__(self, guild_id):
        super().__init__(label="Edit Scene Notes", style=discord.ButtonStyle.primary)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        if not repo.is_gm(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("❌ Only GMs can edit scene notes.", ephemeral=True)
            return
        await interaction.response.send_modal(EditSceneNotesModal(self.guild_id))  # No need to pass interaction.message

class EditSceneNotesModal(discord.ui.Modal, title="Edit Scene Notes"):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        current_notes = repo.get_scene_notes(guild_id) or ""
        self.notes = discord.ui.TextInput(
            label="Scene Notes",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000,
            default=current_notes
        )
        self.add_item(self.notes)

    async def on_submit(self, interaction: discord.Interaction):
        repo.set_scene_notes(self.guild_id, self.notes.value)
        # Rebuild the scene embed and view
        system = repo.get_system(self.guild_id)
        sheet = factories.get_specific_sheet(system)
        npc_ids = repo.get_scene_npc_ids(self.guild_id)
        is_gm = repo.is_gm(self.guild_id, interaction.user.id)
        lines = []
        for npc_id in npc_ids:
            npc = repo.get_character(self.guild_id, npc_id)
            if npc:
                lines.append(sheet.format_npc_scene_entry(npc, is_gm))
        notes = repo.get_scene_notes(self.guild_id)
        description = ""
        if notes:
            description += f"**Notes:**\n{notes}\n\n"
        if lines:
            description += "\n\n".join(lines)
        else:
            description += "📭 No NPCs are currently in the scene."
        embed = discord.Embed(
            title="🎭 The Current Scene",
            description=description,
            color=discord.Color.purple()
        )
        view = SceneNotesEditView(self.guild_id, is_gm)
        await interaction.response.edit_message(embed=embed, view=view)

class EditNameModal(ui.Modal, title="Edit Character Name"):
    def __init__(self, char_id: str, current_name: str, system: str, make_view_embed):
        super().__init__()
        self.char_id = char_id
        self.system = system
        self.make_view_embed = make_view_embed
        self.name_input = ui.TextInput(
            label="New Name",
            default=current_name,
            max_length=100
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: Interaction):
        character = get_character(interaction.guild.id, self.char_id)
        if not character:
            await interaction.response.send_message("❌ Character not found.", ephemeral=True)
            return
        new_name = self.name_input.value.strip()
        if not new_name:
            await interaction.response.send_message("❌ Name cannot be empty.", ephemeral=True)
            return
        character.name = new_name
        repo.set_character(interaction.guild.id, character, system=self.system)
        embed, view = self.make_view_embed(interaction.user.id, self.char_id)
        await interaction.response.edit_message(content="✅ Name updated.", embed=embed, view=view)

class EditNotesModal(ui.Modal, title="Edit Notes"):
    def __init__(self, char_id: str, notes: str, system: str, make_view_embed):
        super().__init__()
        self.char_id = char_id
        self.system = system
        self.make_view_embed = make_view_embed
        self.notes_field = ui.TextInput(
            label="Notes",
            style=TextStyle.paragraph,
            required=False,
            default=notes,
            max_length=2000
        )
        self.add_item(self.notes_field)

    async def on_submit(self, interaction: Interaction):
        character = get_character(interaction.guild.id, self.char_id)
        character.notes = [line for line in self.notes_field.value.splitlines() if line.strip()]
        repo.set_character(interaction.guild.id, character, system=self.system)
        embed, view = self.make_view_embed(interaction.user.id, self.char_id)
        await interaction.response.edit_message(content="✅ Notes updated.", embed=embed, view=view)

class RequestRollView(ui.View):
    def __init__(self, roll_formula: RollModifiers = None, difficulty: int = None):
        super().__init__(timeout=300)
        self.roll_formula_obj = roll_formula
        self.difficulty = difficulty
        self.add_item(EditRequestedRollButton(roll_formula, difficulty))
        self.add_item(FinalizeRollButton(roll_formula, difficulty))

class EditRequestedRollButton(ui.Button):
    def __init__(self, roll_formula: RollModifiers = None, difficulty: int = None):
        super().__init__(label="Modify Roll", style=discord.ButtonStyle.primary)
        self.roll_formula_obj = roll_formula
        self.difficulty = difficulty

    async def callback(self, interaction: discord.Interaction):
        character = repo.get_active_character(interaction.guild.id, interaction.user.id)
        if not character:
            await interaction.response.send_message("❌ Active character not found. Use /setactive to set your active character.", ephemeral=True)
            return
        await character.edit_requested_roll(interaction, self.roll_formula_obj, difficulty=self.difficulty)

class RollModifiersView(ui.View):
    """
    Base class for system-specific RollFormulaViews.
    Provides shared variables and structure for roll input views.
    Each modifier/property is shown as a button; clicking it opens a modal to edit its value.
    """
    def __init__(self, roll_formula_obj: RollModifiers, character: BaseCharacter, difficulty: int = None):
        super().__init__(timeout=300)
        self.roll_formula_obj = roll_formula_obj  # The RollFormula object being edited
        self.character = character                # The character making the roll
        self.difficulty = difficulty  

        self.modifier_buttons = {}

        # Create a button for each key in the roll formula
        dice_pattern = re.compile(r"^\s*\d*d\d+([+-]\d+)?\s*$", re.IGNORECASE)
        for key, value in self.roll_formula_obj.to_dict().items():
            is_numeric = False
            try:
                int(value)
                is_numeric = True
            except (ValueError, TypeError):
                pass
            if is_numeric or dice_pattern.match(str(value)):
                button = EditModifierButton(key, str(value), self)
                self.modifier_buttons[key] = button
                self.add_item(button)

        # Add a button to add new modifiers
        self.add_item(AddModifierButton(self))

    def add_modifier_button(self, label="modifier", value="0"):
        button = EditModifierButton(label, value, self)
        self.modifier_buttons[label] = button
        self.add_item(button)

    async def update_modifier(self, interaction: discord.Interaction, key: str, value: str):
        # Update the RollFormula object and button label
        self.roll_formula_obj[key] = value
        button = self.modifier_buttons[key]
        button.label = f"{key}: {value}"
        await interaction.response.edit_message(view=self)

class EditModifierButton(discord.ui.Button):
    def __init__(self, key: str, value: str, parent_view: RollModifiersView):
        super().__init__(label=f"{key}: {value}", row=1, style=discord.ButtonStyle.secondary)
        self.key = key
        self.value = value
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EditModifierModal(self.key, self.value, self.parent_view, interaction))

class EditModifierModal(discord.ui.Modal, title="Edit Modifier"):
    def __init__(self, key: str, value: str, parent_view: RollModifiersView, original_interaction: discord.Interaction):
        super().__init__()
        self.key = key
        self.parent_view = parent_view
        self.original_interaction = original_interaction
        self.value_input = discord.ui.TextInput(
            label=f"Value for {key}",
            default=value,
            required=True,
            max_length=20
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.parent_view.update_modifier(interaction, self.key, self.value_input.value)

class AddModifierButton(discord.ui.Button):
    def __init__(self, parent_view: RollModifiersView):
        super().__init__(label="Add Modifier", row=0, style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # Open a modal to ask for new modifier key and value
        await interaction.response.send_modal(AddModifierModal(self.parent_view, interaction))

class AddModifierModal(discord.ui.Modal, title="Add Modifier"):
    def __init__(self, parent_view: RollModifiersView, original_interaction: discord.Interaction):
        super().__init__()
        self.parent_view = parent_view
        self.original_interaction = original_interaction
        self.key_input = discord.ui.TextInput(
            label="Modifier Name",
            placeholder="e.g. bonus, penalty, situational",
            required=True,
            max_length=30
        )
        self.value_input = discord.ui.TextInput(
            label="Modifier Value",
            placeholder="e.g. +2, -1, 0",
            required=True,
            max_length=10
        )
        self.add_item(self.key_input)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip()
        value = self.value_input.value.strip()
        self.parent_view.roll_formula_obj[key] = value
        self.parent_view.add_modifier_button(label=key, value=value)
        await interaction.response.edit_message(view=self.parent_view)

class FinalizeRollButton(discord.ui.Button):
    def __init__(self, roll_formula_obj: RollModifiers = None, difficulty: int = None):
        super().__init__(label="Roll", style=discord.ButtonStyle.success)
        self.roll_formula_obj = roll_formula_obj
        self.difficulty = difficulty

    async def callback(self, interaction: discord.Interaction):
        character = repo.get_active_character(interaction.guild.id, interaction.user.id)
        await character.send_roll_message(
            interaction,
            self.roll_formula_obj,
            self.difficulty
        )