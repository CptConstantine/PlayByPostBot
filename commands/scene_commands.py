import discord
from discord.ext import commands
from discord import app_commands
from core import shared_views
from data import repo
import core.factories as factories

async def npc_name_autocomplete(interaction: discord.Interaction, current: str):
    all_chars = repo.get_all_characters(interaction.guild.id)
    scene_npcs = set(repo.get_scene_npc_ids(interaction.guild.id))
    npcs = [
        c for c in all_chars
        if c.is_npc and c.id not in scene_npcs and current.lower() in c.name.lower()
    ]
    options = [c.name for c in npcs]
    return [app_commands.Choice(name=name, value=name) for name in options[:25]]

class SceneCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    scene_group = app_commands.Group(name="scene", description="Scene management commands")

    @scene_group.command(name="add", description="Add an NPC to the current scene.")
    @app_commands.describe(npc_name="The name of the NPC to add to the scene")
    @app_commands.autocomplete(npc_name=npc_name_autocomplete)
    async def scene_add(self, interaction: discord.Interaction, npc_name: str):
        if not repo.is_gm(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("❌ Only GMs can manage the scene.", ephemeral=True)
            return
        npc = repo.get_character(interaction.guild.id, npc_name)
        if not npc:
            await interaction.response.send_message("❌ NPC not found. Did you create it with `/createnpc`?", ephemeral=True)
            return
        scene_npcs = repo.get_scene_npc_ids(interaction.guild.id)
        if npc.id in scene_npcs:
            await interaction.response.send_message("⚠️ That NPC is already in the scene.", ephemeral=True)
            return
        repo.add_scene_npc(interaction.guild.id, npc.id)
        await interaction.response.send_message(f"✅ **{npc_name}** added to the scene.", ephemeral=True)

    @scene_group.command(name="remove", description="Remove an NPC from the current scene.")
    @app_commands.describe(npc_name="The name of the NPC to remove from the scene")
    @app_commands.autocomplete(npc_name=npc_name_autocomplete)
    async def scene_remove(self, interaction: discord.Interaction, npc_name: str):
        if not repo.is_gm(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("❌ Only GMs can manage the scene.", ephemeral=True)
            return
        scene_npcs = repo.get_scene_npc_ids(interaction.guild.id)
        npc = repo.get_character(interaction.guild.id, npc_name)
        if not npc:
            await interaction.response.send_message("❌ NPC not found.", ephemeral=True)
            return
        if npc.id not in scene_npcs:
            await interaction.response.send_message("❌ That NPC isn't in the scene.", ephemeral=True)
            return
        repo.remove_scene_npc(interaction.guild.id, npc.id)
        await interaction.response.send_message(f"🗑️ **{npc_name}** removed from the scene.", ephemeral=True)

    @scene_group.command(name="clear", description="Clear all NPCs from the current scene.")
    async def scene_clear(self, interaction: discord.Interaction):
        if not repo.is_gm(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("❌ Only GMs can manage the scene.", ephemeral=True)
            return
        repo.clear_scenes(interaction.guild.id)
        await interaction.response.send_message("🧹 Scene NPC list cleared.", ephemeral=True)

    @scene_group.command(name="view", description="View the current scene.")
    async def scene_view(self, interaction: discord.Interaction):
        system = repo.get_system(interaction.guild.id)
        sheet = factories.get_specific_sheet(system)
        npc_ids = repo.get_scene_npc_ids(interaction.guild.id)
        is_gm = repo.is_gm(interaction.guild.id, interaction.user.id)
        lines = []
        for npc_id in npc_ids:
            npc = repo.get_character_by_id(interaction.guild.id, npc_id)
            if npc:
                lines.append(sheet.format_npc_scene_entry(npc, is_gm))
        notes = repo.get_scene_notes(interaction.guild.id)
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
        view = shared_views.SceneNotesEditView(interaction.guild.id, is_gm)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

async def setup_scene_commands(bot: commands.Bot):
    await bot.add_cog(SceneCommands(bot))