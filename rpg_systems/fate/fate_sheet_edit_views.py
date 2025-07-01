import discord
from discord import ui, SelectOption
from core.shared_views import PaginatedSelectView, EditNameModal, EditNotesModal
from rpg_systems.fate.aspect import Aspect
from rpg_systems.fate.fate_character import FateCharacter, get_character, SYSTEM
from rpg_systems.fate.fate_sheet import FateSheet
from data.repositories.repository_factory import repositories

class FateSheetEditView(ui.View):
    def __init__(self, editor_id: int, char_id: str):
        super().__init__(timeout=120)
        self.editor_id = editor_id
        self.char_id = char_id
        self.add_item(RollButton(char_id, editor_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.editor_id:
            await interaction.response.send_message("You can't edit this character.", ephemeral=True)
            return False
        return True

    @ui.button(label="Edit Stress", style=discord.ButtonStyle.primary, row=1)
    async def edit_stress(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(EditStressModal(self.char_id))

    @ui.button(label="Edit Consequences", style=discord.ButtonStyle.primary, row=1)
    async def edit_consequences(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Editing consequences:", view=EditConsequencesView(interaction.guild.id, self.editor_id, self.char_id))

    @ui.button(label="Edit Fate Points/Refresh", style=discord.ButtonStyle.primary, row=1)
    async def edit_fate_points(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(EditFatePointsModal(self.char_id))

    @ui.button(label="Edit Name", style=discord.ButtonStyle.secondary, row=2)
    async def edit_name(self, interaction: discord.Interaction, button: ui.Button):
        character = get_character(self.char_id)
        await interaction.response.send_modal(
            EditNameModal(
                self.char_id,
                character.name if character else "",
                SYSTEM,
                lambda editor_id, char_id: (FateSheet().format_full_sheet(get_character(char_id)), FateSheetEditView(editor_id, char_id))
            )
        )

    @ui.button(label="Edit Aspects", style=discord.ButtonStyle.secondary, row=2)
    async def edit_aspects(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Editing aspects:", view=EditAspectsView(interaction.guild.id, self.editor_id, self.char_id))

    @ui.button(label="Edit Skills", style=discord.ButtonStyle.secondary, row=2)
    async def edit_skills(self, interaction: discord.Interaction, button: ui.Button):
        character = get_character(self.char_id)
        
        # Create a view with buttons for different skill operations
        view = SkillManagementView(character, self.editor_id, self.char_id)
        await interaction.response.send_message(
            "Choose how you want to manage skills:",
            view=view,
            ephemeral=True
        )

    @ui.button(label="Edit Notes", style=discord.ButtonStyle.secondary, row=2)
    async def edit_notes(self, interaction: discord.Interaction, button: ui.Button):
        character = get_character(self.char_id)
        notes = "\n".join(character.notes) if character and character.notes else ""
        await interaction.response.send_modal(
            EditNotesModal(
                self.char_id,
                notes,
                SYSTEM,
                lambda editor_id, char_id: (FateSheet().format_full_sheet(get_character(char_id)), FateSheetEditView(editor_id, char_id))
            )
        )

    @ui.button(label="Edit Stunts", style=discord.ButtonStyle.secondary, row=3)
    async def edit_stunts(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Editing stunts:", view=EditStuntsView(interaction.guild.id, self.editor_id, self.char_id))

class EditAspectsView(ui.View):
    def __init__(self, guild_id: int, user_id: int, char_id: str):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.user_id = user_id
        self.char_id = char_id
        self.page = 0

        self.char = None
        self.aspects = []
        self.max_page = 0
        self.load_data()
        self.render()

    def load_data(self):
        self.char = get_character(self.char_id)
        if not self.char:
            self.aspects = []
        else:
            self.aspects = self.char.aspects
        self.max_page = max(0, len(self.aspects) - 1)

    def render(self):
        self.clear_items()
        if self.aspects:
            current_aspect = self.aspects[self.page]
            aspect_name = current_aspect.name
            is_hidden = current_aspect.is_hidden
            
            label = f"{self.page + 1}/{len(self.aspects)}: {aspect_name[:30]}"
            self.add_item(ui.Button(label=label, disabled=True, row=0))
            
            # Add view description button if there is a description
            if current_aspect.description:  # Changed from description key access
                self.add_item(ui.Button(label="📖 View Description", style=discord.ButtonStyle.primary, row=0, custom_id="view_desc"))
            
            # Navigation buttons
            if self.page > 0:
                self.add_item(ui.Button(label="◀️ Prev", style=discord.ButtonStyle.secondary, row=1, custom_id="prev"))
            if self.page < self.max_page:
                self.add_item(ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, row=1, custom_id="next"))
            
            # Action buttons
            self.add_item(ui.Button(label="✏️ Edit", style=discord.ButtonStyle.primary, row=2, custom_id="edit"))
            self.add_item(ui.Button(label="🗑 Remove", style=discord.ButtonStyle.danger, row=2, custom_id="remove"))
            
            # Visibility toggle
            toggle_label = "🙈 Hide" if not is_hidden else "👁 Unhide"
            toggle_style = discord.ButtonStyle.secondary if not is_hidden else discord.ButtonStyle.success
            self.add_item(ui.Button(label=toggle_label, style=toggle_style, row=2, custom_id="toggle_hidden"))
        
        # Add aspect button and done button
        self.add_item(ui.Button(label="➕ Add New", style=discord.ButtonStyle.success, row=3, custom_id="add"))
        self.add_item(ui.Button(label="✅ Done", style=discord.ButtonStyle.secondary, row=3, custom_id="done"))
        
        # Assign callbacks
        for item in self.children:
            if isinstance(item, ui.Button) and item.custom_id:
                item.callback = self.make_callback(item.custom_id)

    def make_callback(self, cid):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("You can't edit this character.", ephemeral=True)
                return

            self.char = get_character(self.char_id)
            self.aspects = self.char.aspects

            if cid == "prev":
                self.page = max(0, self.page - 1)
            elif cid == "next":
                self.page = min(self.max_page, self.page + 1)
            elif cid == "view_desc":
                current_aspect = self.aspects[self.page]
                name = current_aspect.name
                description = current_aspect.description
                await interaction.response.send_message(
                    f"**{name}**\n{description}", 
                    ephemeral=True
                )
                return
            elif cid == "edit":
                await interaction.response.send_modal(EditAspectModal(self.char_id, self.page, self.aspects[self.page]))
                return
            elif cid == "remove":
                del self.aspects[self.page]
                self.char.aspects = self.aspects
                repositories.character.upsert_character(interaction.guild.id, self.char, system=SYSTEM)
                self.page = max(0, self.page - 1)
            elif cid == "toggle_hidden":
                current_aspect = self.aspects[self.page]
                current_aspect.is_hidden = not current_aspect.is_hidden
                self.char.aspects = self.aspects
                repositories.character.upsert_character(interaction.guild.id, self.char, system=SYSTEM)
            elif cid == "add":
                await interaction.response.send_modal(AddAspectModal(self.char_id))
                return
            elif cid == "done":
                await interaction.response.edit_message(
                    content="✅ Done editing aspects.", 
                    embed=FateSheet().format_full_sheet(self.char), 
                    view=FateSheetEditView(interaction.user.id, self.char_id)
                )
                return

            # Save changes and update view
            repositories.character.upsert_character(interaction.guild.id, self.char, system=SYSTEM)
            self.load_data()
            self.render()
            await interaction.response.edit_message(embed=FateSheet().format_full_sheet(self.char), view=self)
        
        return callback

class EditConsequencesView(ui.View):
    def __init__(self, guild_id: int, user_id: int, char_id: str):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.user_id = user_id
        self.char_id = char_id
        self.page = 0

        self.char = get_character(self.char_id)
        self.consequences = self.char.consequences if self.char else []
        self.max_page = max(0, len(self.consequences) - 1)
        self.render()

    def render(self):
        self.clear_items()
        if self.consequences:
            label = f"{self.page + 1}/{len(self.consequences)}: {self.consequences[self.page][:30]}"
            self.add_item(ui.Button(label=label, disabled=True, row=0))
            if self.page > 0:
                self.add_item(ui.Button(label="◀️ Prev", style=discord.ButtonStyle.secondary, row=1, custom_id="prev"))
            if self.page < self.max_page:
                self.add_item(ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, row=1, custom_id="next"))
            self.add_item(ui.Button(label="✏️ Edit", style=discord.ButtonStyle.primary, row=2, custom_id="edit"))
            self.add_item(ui.Button(label="🗑 Remove", style=discord.ButtonStyle.danger, row=2, custom_id="remove"))
        self.add_item(ui.Button(label="➕ Add New", style=discord.ButtonStyle.success, row=3, custom_id="add"))
        self.add_item(ui.Button(label="✅ Done", style=discord.ButtonStyle.secondary, row=3, custom_id="done"))
        for item in self.children:
            if isinstance(item, ui.Button) and item.custom_id:
                item.callback = self.make_callback(item.custom_id)

    def make_callback(self, cid):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("You can't edit this character.", ephemeral=True)
                return

            self.char = get_character(self.char_id)
            self.consequences = self.char.consequences if self.char else []

            if cid == "prev":
                self.page = max(0, self.page - 1)
            elif cid == "next":
                self.page = min(self.max_page, self.page + 1)
            elif cid == "edit":
                await interaction.response.send_modal(EditConsequenceModal(self.char_id, self.page, self.consequences[self.page]))
                return
            elif cid == "remove":
                del self.consequences[self.page]
                self.char.consequences = self.consequences
                repositories.character.upsert_character(interaction.guild.id, self.char, system=SYSTEM)
                self.page = max(0, self.page - 1)
            elif cid == "add":
                await interaction.response.send_modal(AddConsequenceModal(self.char_id))
                return
            elif cid == "done":
                await interaction.response.edit_message(content="✅ Done editing consequences.", embed=FateSheet().format_full_sheet(self.char), view=FateSheetEditView(interaction.user.id, self.char_id))
                return

            repositories.character.upsert_character(interaction.guild.id, self.char, system=SYSTEM)
            self.render()
            await interaction.response.edit_message(view=self)
        return callback

class EditStuntsView(ui.View):
    def __init__(self, guild_id: int, user_id: int, char_id: str):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.user_id = user_id
        self.char_id = char_id
        self.page = 0

        self.char = None
        self.stunts = {}  # Dictionary of {name: description}
        self.stunt_names = []  # List of stunt names for pagination
        self.max_page = 0
        self.load_data()
        self.render()

    def load_data(self):
        self.char = get_character(self.char_id)
        if not self.char:
            self.stunts = {}
            self.stunt_names = []
        else:
            self.stunts = self.char.stunts
            self.stunt_names = list(self.stunts.keys())
        self.max_page = max(0, len(self.stunt_names) - 1)

    def render(self):
        self.clear_items()
        if self.stunt_names:
            current_stunt = self.stunt_names[self.page]
            label = f"{self.page + 1}/{len(self.stunt_names)}: {current_stunt[:30]}"
            self.add_item(ui.Button(label=label, disabled=True, row=0))
            
            # Description button to view full description
            self.add_item(ui.Button(label="📖 View Description", style=discord.ButtonStyle.primary, row=0, custom_id="view_desc"))
            
            if self.page > 0:
                self.add_item(ui.Button(label="◀️ Prev", style=discord.ButtonStyle.secondary, row=1, custom_id="prev"))
            if self.page < self.max_page:
                self.add_item(ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, row=1, custom_id="next"))
            
            self.add_item(ui.Button(label="✏️ Edit", style=discord.ButtonStyle.primary, row=2, custom_id="edit"))
            self.add_item(ui.Button(label="🗑 Remove", style=discord.ButtonStyle.danger, row=2, custom_id="remove"))
        
        self.add_item(ui.Button(label="➕ Add New", style=discord.ButtonStyle.success, row=3, custom_id="add"))
        self.add_item(ui.Button(label="✅ Done", style=discord.ButtonStyle.secondary, row=3, custom_id="done"))
        
        for item in self.children:
            if isinstance(item, ui.Button) and item.custom_id:
                item.callback = self.make_callback(item.custom_id)

    def make_callback(self, cid):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("You can't edit this character.", ephemeral=True)
                return

            self.char = get_character(self.char_id)
            self.stunts = self.char.stunts
            self.stunt_names = list(self.stunts.keys())

            if cid == "prev":
                self.page = max(0, self.page - 1)
            elif cid == "next":
                self.page = min(self.max_page, self.page + 1)
            elif cid == "view_desc":
                current_stunt = self.stunt_names[self.page]
                description = self.stunts.get(current_stunt, "No description available")
                await interaction.response.send_message(
                    f"**{current_stunt}**\n{description}", 
                    ephemeral=True
                )
                return
            elif cid == "edit":
                current_stunt = self.stunt_names[self.page]
                description = self.stunts.get(current_stunt, "")
                await interaction.response.send_modal(
                    EditStuntModal(self.char_id, current_stunt, description)
                )
                return
            elif cid == "remove":
                current_stunt = self.stunt_names[self.page]
                del self.stunts[current_stunt]
                self.char.stunts = self.stunts
                repositories.character.upsert_character(interaction.guild.id, self.char, system=SYSTEM)
                self.stunt_names.remove(current_stunt)
                self.max_page = max(0, len(self.stunt_names) - 1)
                self.page = min(self.page, self.max_page)
            elif cid == "add":
                await interaction.response.send_modal(AddStuntModal(self.char_id))
                return
            elif cid == "done":
                await interaction.response.edit_message(
                    content="✅ Done editing stunts.", 
                    embed=FateSheet().format_full_sheet(self.char), 
                    view=FateSheetEditView(interaction.user.id, self.char_id)
                )
                return

            # Save changes and update view
            repositories.character.upsert_character(interaction.guild.id, self.char, system=SYSTEM)
            self.load_data()
            self.render()
            await interaction.response.edit_message(view=self)
            
        return callback

class SkillManagementView(ui.View):
    def __init__(self, character, editor_id, char_id):
        super().__init__(timeout=120)
        self.character = character
        self.editor_id = editor_id
        self.char_id = char_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.editor_id:
            await interaction.response.send_message("You can't edit this character.", ephemeral=True)
            return False
        return True

    @ui.button(label="Edit Existing Skill", style=discord.ButtonStyle.primary, row=0)
    async def edit_existing_skill(self, interaction: discord.Interaction, button: ui.Button):
        skills = self.character.skills if self.character.skills else {}
        if not skills:
            await interaction.response.edit_message(
                content="This character doesn't have any skills yet. Add some first!",
                view=None
            )
            return

        skill_options = [SelectOption(label=k, value=k) for k in sorted(skills.keys())]

        async def on_skill_selected(view, interaction2, skill):
            current_value = skills.get(skill, 0)
            await interaction2.response.send_modal(EditSkillValueModal(self.char_id, skill, current_value))

        await interaction.response.edit_message(
            content="Select a skill to edit:",
            view=PaginatedSelectView(
                skill_options, 
                on_skill_selected, 
                interaction.user.id, 
                prompt="Select a skill to edit:"
            )
        )

    @ui.button(label="Add New Skill", style=discord.ButtonStyle.success, row=0)
    async def add_new_skill(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AddSkillModal(self.char_id))

    @ui.button(label="Remove Skill", style=discord.ButtonStyle.danger, row=0)
    async def remove_skill(self, interaction: discord.Interaction, button: ui.Button):
        skills = self.character.skills if self.character.skills else {}
        if not skills:
            await interaction.response.edit_message(
                content="This character doesn't have any skills to remove.",
                view=None
            )
            return

        skill_options = [SelectOption(label=k, value=k) for k in sorted(skills.keys())]

        async def on_skill_selected(view, interaction2, skill):
            # Remove the selected skill
            skills = self.character.skills
            if skill in skills:
                del skills[skill]
                self.character.skills = skills
                repositories.character.upsert_character(interaction2.guild.id, self.character, system=SYSTEM)
                embed = FateSheet().format_full_sheet(self.character)
                view = FateSheetEditView(interaction2.user.id, self.char_id)
                await interaction2.response.edit_message(
                    content=f"✅ Removed skill: **{skill}**",
                    embed=embed,
                    view=view
                )
            else:
                await interaction2.response.edit_message(
                    content=f"❌ Skill not found: {skill}",
                    view=None
                )

        await interaction.response.edit_message(
            content="Select a skill to remove:",
            view=PaginatedSelectView(
                skill_options, 
                on_skill_selected, 
                interaction.user.id, 
                prompt="Select a skill to remove:"
            )
        )

    @ui.button(label="Bulk Edit Skills", style=discord.ButtonStyle.secondary, row=1)
    async def bulk_edit_skills(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BulkEditSkillsModal(self.char_id))

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        character = get_character(self.char_id)
        embed = FateSheet().format_full_sheet(character)
        view = FateSheetEditView(interaction.user.id, self.char_id)
        await interaction.response.edit_message(
            content="Operation cancelled.",
            embed=embed,
            view=view
        )

class RollButton(ui.Button):
    def __init__(self, char_id, editor_id):
        super().__init__(label="Roll", style=discord.ButtonStyle.primary, row=0)
        self.char_id = char_id
        self.editor_id = editor_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.editor_id:
            await interaction.response.send_message("You can't roll for this character.", ephemeral=True)
            return
        character = get_character(self.char_id)
        skills = character.skills if character else {}
        skill_options = [SelectOption(label=k, value=k) for k in sorted(skills.keys())]

        async def on_skill_selected(view, interaction2, skill):
            result = FateSheet().roll(character, skill=skill)
            await interaction2.response.send_message(result, ephemeral=True)

        await interaction.response.send_message(
            "Select a skill to roll:",
            view=PaginatedSelectView(skill_options, on_skill_selected, interaction.user.id, prompt="Select a skill to roll:"),
            ephemeral=True
        )

class EditAspectModal(ui.Modal, title="Edit Aspect"):
    def __init__(self, char_id: str, index: int, aspect: Aspect):
        super().__init__()
        self.char_id = char_id
        self.index = index
        
        self.name_field = ui.TextInput(
            label="Aspect Name",
            default=aspect.name,
            max_length=100,
            required=True
        )
        self.add_item(self.name_field)
        
        self.description_field = ui.TextInput(
            label="Description (optional)",
            default=aspect.description,
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )
        self.add_item(self.description_field)
        
        # Add free invokes field
        self.free_invokes_field = ui.TextInput(
            label="Free Invokes (number)",
            default=str(aspect.free_invokes),
            max_length=2,
            required=False
        )
        self.add_item(self.free_invokes_field)

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        aspects = character.aspects
        if self.index >= len(aspects):
            await interaction.response.send_message("❌ Aspect not found.", ephemeral=True)
            return
        
        # Update the aspect with new values
        aspects[self.index].name = self.name_field.value.strip()
        aspects[self.index].description = self.description_field.value.strip()
        
        # Handle the free invokes value
        try:
            free_invokes = int(self.free_invokes_field.value.strip() or "0")
            aspects[self.index].free_invokes = max(0, free_invokes)  # Ensure non-negative
        except ValueError:
            # If conversion fails, default to 0
            aspects[self.index].free_invokes = 0
        
        # Save changes
        character.aspects = aspects
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import EditAspectsView
        await interaction.response.edit_message(
            content="✅ Aspect updated.", 
            embed=FateSheet().format_full_sheet(character), 
            view=EditAspectsView(interaction.guild.id, interaction.user.id, self.char_id)
        )

class AddAspectModal(ui.Modal, title="Add Aspect"):
    def __init__(self, char_id: str):
        super().__init__()
        self.char_id = char_id
        
        self.name_field = ui.TextInput(
            label="Aspect Name",
            max_length=100,
            required=True
        )
        self.add_item(self.name_field)
        
        self.description_field = ui.TextInput(
            label="Description (optional)",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )
        self.add_item(self.description_field)
        
        # Add free invokes field
        self.free_invokes_field = ui.TextInput(
            label="Free Invokes (number)",
            default="0",
            max_length=2,
            required=False
        )
        self.add_item(self.free_invokes_field)
        
        # Add hidden checkbox (simulated with text field since modal doesn't have checkboxes)
        self.is_hidden_field = ui.TextInput(
            label="Hidden? (yes/no)",
            default="no",
            max_length=3,
            required=False
        )
        self.add_item(self.is_hidden_field)

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        aspects = character.aspects
        
        # Process the free invokes input
        try:
            free_invokes = int(self.free_invokes_field.value.strip() or "0")
            free_invokes = max(0, free_invokes)  # Ensure non-negative
        except ValueError:
            free_invokes = 0
            
        # Process the is_hidden input
        is_hidden = self.is_hidden_field.value.lower().strip() in ["yes", "y", "true", "1"]
        
        # Create new aspect as an Aspect object
        new_aspect = Aspect(
            name=self.name_field.value.strip(),
            description=self.description_field.value.strip(),
            is_hidden=is_hidden,
            free_invokes=free_invokes
        )
        
        aspects.append(new_aspect)
        character.aspects = aspects
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import EditAspectsView
        await interaction.response.edit_message(
            content="✅ Aspect added.", 
            embed=FateSheet().format_full_sheet(character), 
            view=EditAspectsView(interaction.guild.id, interaction.user.id, self.char_id)
        )

class EditStressModal(ui.Modal, title="Edit Stress"):
    physical = ui.TextInput(label="Physical Stress (e.g. 1 1 0)", required=False)
    mental = ui.TextInput(label="Mental Stress (e.g. 1 0)", required=False)

    def __init__(self, char_id):
        super().__init__()
        self.char_id = char_id

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        stress = character.stress
        stress["physical"] = [bool(int(x)) for x in self.physical.value.split()]
        stress["mental"] = [bool(int(x)) for x in self.mental.value.split()]
        character.stress = stress
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import FateSheetEditView
        await interaction.response.edit_message(
            content="✅ Stress updated!", 
            embed=FateSheet().format_full_sheet(character), 
            view=FateSheetEditView(interaction.user.id, self.char_id)
        )

class EditFatePointsModal(ui.Modal, title="Edit Fate Points/Refresh"):
    fate_points = ui.TextInput(label="Fate Points", required=True)
    refresh = ui.TextInput(label="Refresh", required=True)

    def __init__(self, char_id):
        super().__init__()
        self.char_id = char_id
        
        # Get current values to show as defaults
        character = get_character(char_id)
        if character:
            self.fate_points.default = str(character.fate_points)
            self.refresh.default = str(character.refresh)

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        try:
            character.fate_points = int(self.fate_points.value)
            character.refresh = int(self.refresh.value)
        except ValueError:
            await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
            return
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import FateSheetEditView
        await interaction.response.edit_message(
            content="✅ Fate Points and Refresh updated.", 
            embed=FateSheet().format_full_sheet(character), 
            view=FateSheetEditView(interaction.user.id, self.char_id)
        )

class EditConsequenceModal(ui.Modal, title="Edit Consequence"):
    def __init__(self, char_id: str, index: int, current: str):
        super().__init__()
        self.char_id = char_id
        self.index = index
        self.add_item(ui.TextInput(label="Consequence", default=current, max_length=100))

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        consequences = character.consequences
        if self.index >= len(consequences):
            await interaction.response.send_message("❌ Consequence not found.", ephemeral=True)
            return
        consequences[self.index] = self.children[0].value.strip()
        character.consequences = consequences
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import EditConsequencesView
        await interaction.response.edit_message(
            content="✅ Consequence updated.", 
            view=EditConsequencesView(interaction.guild.id, interaction.user.id, self.char_id)
        )

class AddConsequenceModal(ui.Modal, title="Add Consequence"):
    def __init__(self, char_id: str):
        super().__init__()
        self.char_id = char_id
        self.add_item(ui.TextInput(label="New Consequence", max_length=100))

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        consequences = character.consequences
        consequences.append(self.children[0].value.strip())
        character.consequences = consequences
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import EditConsequencesView
        await interaction.response.edit_message(
            content="✅ Consequence added.", 
            view=EditConsequencesView(interaction.guild.id, interaction.user.id, self.char_id)
        )

class EditSkillValueModal(ui.Modal, title="Edit Skill Value"):
    def __init__(self, char_id: str, skill: str, current_value: int = 0):
        super().__init__()
        self.char_id = char_id
        self.skill = skill
        label = f"Set value for {skill} (-3 to 6)"
        if len(label) > 45:
            label = label[:42] + "..."
        self.value_field = ui.TextInput(
            label=label,
            required=True,
            default=str(current_value),
            max_length=3
        )
        self.add_item(self.value_field)

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        value = self.value_field.value.strip()
        try:
            value_int = int(value)
            if value_int < -3 or value_int > 6:
                raise ValueError
        except Exception:
            await interaction.response.send_message("❌ Please enter an integer from -3 to 6.", ephemeral=True)
            return
        skills = character.skills
        skills[self.skill] = value_int
        character.skills = skills
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import FateSheetEditView
        embed = FateSheet().format_full_sheet(character)
        view = FateSheetEditView(interaction.user.id, self.char_id)
        await interaction.response.edit_message(content=f"✅ {self.skill} updated.", embed=embed, view=view)

class AddSkillModal(ui.Modal, title="Add New Skill"):
    skill_name = ui.TextInput(label="Skill Name", required=True, max_length=50)
    skill_value = ui.TextInput(label="Skill Value (-3 to 6)", required=True, default="0", max_length=2)

    def __init__(self, char_id: str):
        super().__init__()
        self.char_id = char_id

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        
        # Validate skill value
        try:
            value_int = int(self.skill_value.value.strip())
            if value_int < -3 or value_int > 6:
                await interaction.response.send_message("❌ Skill value must be between -3 and 6.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid integer for skill value.", ephemeral=True)
            return
        
        # Add the new skill
        skills = character.skills
        skill_name = self.skill_name.value.strip()
        
        if not skill_name:
            await interaction.response.send_message("❌ Skill name cannot be empty.", ephemeral=True)
            return
            
        if skill_name in skills:
            await interaction.response.send_message(f"❌ Skill '{skill_name}' already exists. Use edit instead.", ephemeral=True)
            return
            
        skills[skill_name] = value_int
        character.skills = skills
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import FateSheetEditView
        embed = FateSheet().format_full_sheet(character)
        view = FateSheetEditView(interaction.user.id, self.char_id)
        await interaction.response.edit_message(
            content=f"✅ Added new skill: **{skill_name}** (+{value_int if value_int >= 0 else value_int})",
            embed=embed,
            view=view
        )

class BulkEditSkillsModal(ui.Modal, title="Bulk Edit Skills"):
    def __init__(self, char_id: str):
        super().__init__()
        self.char_id = char_id
        
        # Get current skills to show as default
        character = get_character(char_id)
        skills = character.skills if character and character.skills else {}
        
        self.skills_text = ui.TextInput(
            label="Skills (format: Skill1:2,Skill2:1,Skill3:-1)",
            style=discord.TextStyle.paragraph,
            required=False,
            default=", ".join(f"{k}:{v}" for k, v in skills.items()),
            max_length=1000
        )
        self.add_item(self.skills_text)

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        skills_dict = FateCharacter.parse_and_validate_skills(self.skills_text.value)
        
        if not skills_dict:
            skills_dict = {}  # Allow clearing all skills

        # Replace all skills with the new set
        character.skills = skills_dict
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import FateSheetEditView
        embed = FateSheet().format_full_sheet(character)
        view = FateSheetEditView(interaction.user.id, self.char_id)
        await interaction.response.edit_message(
            content="✅ Skills updated!",
            embed=embed,
            view=view
        )
    
class EditStuntModal(ui.Modal, title="Edit Stunt"):
    def __init__(self, char_id: str, stunt_name: str, description: str):
        super().__init__()
        self.char_id = char_id
        self.original_name = stunt_name
        
        self.name_field = ui.TextInput(
            label="Stunt Name",
            default=stunt_name,
            max_length=100,
            required=True
        )
        self.add_item(self.name_field)
        
        self.description_field = ui.TextInput(
            label="Description",
            default=description,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True
        )
        self.add_item(self.description_field)

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        stunts = character.stunts
        
        new_name = self.name_field.value.strip()
        description = self.description_field.value.strip()
        
        if not new_name:
            await interaction.response.send_message("❌ Stunt name cannot be empty.", ephemeral=True)
            return
        
        # If name changed, remove old stunt and add with new name
        if new_name != self.original_name:
            if new_name in stunts and new_name != self.original_name:
                await interaction.response.send_message(f"❌ A stunt with the name '{new_name}' already exists.", ephemeral=True)
                return
            
            del stunts[self.original_name]
            
        stunts[new_name] = description
        character.stunts = stunts
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import EditStuntsView
        await interaction.response.edit_message(
            content=f"✅ Stunt '{new_name}' updated.",
            view=EditStuntsView(interaction.guild.id, interaction.user.id, self.char_id)
        )

class AddStuntModal(ui.Modal, title="Add New Stunt"):
    def __init__(self, char_id: str):
        super().__init__()
        self.char_id = char_id
        
        self.name_field = ui.TextInput(
            label="Stunt Name",
            max_length=100,
            required=True
        )
        self.add_item(self.name_field)
        
        self.description_field = ui.TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True
        )
        self.add_item(self.description_field)

    async def on_submit(self, interaction: discord.Interaction):
        character = get_character(self.char_id)
        stunts = character.stunts
        
        name = self.name_field.value.strip()
        description = self.description_field.value.strip()
        
        if not name:
            await interaction.response.send_message("❌ Stunt name cannot be empty.", ephemeral=True)
            return
            
        if name in stunts:
            await interaction.response.send_message(f"❌ A stunt with the name '{name}' already exists.", ephemeral=True)
            return
            
        stunts[name] = description
        character.stunts = stunts
        repositories.character.upsert_character(interaction.guild.id, character, system=SYSTEM)
        
        # Local import to avoid circular dependency
        from rpg_systems.fate.fate_sheet_edit_views import EditStuntsView
        await interaction.response.edit_message(
            content=f"✅ Added new stunt: '{name}'",
            view=EditStuntsView(interaction.guild.id, interaction.user.id, self.char_id)
        )
