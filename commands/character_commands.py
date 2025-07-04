import uuid
import discord
from discord import app_commands
from discord.ext import commands
from core.models import BaseCharacter, EntityType, RelationshipType
from data.repositories.repository_factory import repositories
import core.factories as factories
import json

async def pc_switch_name_autocomplete(interaction: discord.Interaction, current: str):
    all_chars = repositories.character.get_all_by_guild(interaction.guild.id)
    pcs = [
        c for c in all_chars
        if not c.is_npc and str(c.owner_id) == str(interaction.user.id)
    ]
    options = [c.name for c in pcs if current.lower() in c.name.lower()]
    return [app_commands.Choice(name=name, value=name) for name in options[:25]]

async def pc_name_gm_autocomplete(interaction: discord.Interaction, current: str):
    all_chars = repositories.character.get_all_by_guild(interaction.guild.id)
    pcs = [c for c in all_chars if not c.is_npc]
    options = [c.name for c in pcs if current.lower() in c.name.lower()]
    return [app_commands.Choice(name=name, value=name) for name in options[:25]]

async def character_or_npc_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for commands that can target both PCs and NPCs"""
    all_chars = repositories.character.get_all_by_guild(interaction.guild.id)
    
    # Check if user is GM
    is_gm = await repositories.server.has_gm_permission(interaction.guild.id, interaction.user)
    
    # Filter characters based on permissions
    options = []
    for c in all_chars:
        if c.is_npc and is_gm:
            # GMs can see all NPCs
            options.append(c.name)
        elif not c.is_npc and (str(c.owner_id) == str(interaction.user.id) or is_gm):
            # Users can see their own PCs, GMs can see all PCs
            options.append(c.name)
    
    # Filter by current input
    filtered_options = [name for name in options if current.lower() in name.lower()]
    return [app_commands.Choice(name=name, value=name) for name in filtered_options[:25]]

async def owner_entity_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for entities that can own other entities"""
    is_gm = await repositories.server.has_gm_permission(str(interaction.guild.id), interaction.user)
    
    if is_gm:
        # GMs can see all entities as potential owners
        entities = repositories.character.get_all_by_guild(str(interaction.guild.id))
    else:
        # Users can only use their own entities as owners
        entities = repositories.character.get_user_characters(str(interaction.guild.id), str(interaction.user.id))
    
    # Filter by current input
    filtered_entities = [
        entity for entity in entities 
        if current.lower() in entity.name.lower()
    ]
    
    return [
        app_commands.Choice(name=f"{entity.name} ({entity.entity_type.value})", value=entity.name)
        for entity in filtered_entities[:25]
    ]

class CharacterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    character_group = app_commands.Group(name="character", description="Character management commands")
    
    create_group = app_commands.Group(name="create", description="Create characters and NPCs", parent=character_group)
    
    @create_group.command(name="pc", description="Create a new player character (PC) with a required name")
    @app_commands.describe(
        char_name="The name of your new character",
        owner="Optional: Entity that will own this character (for companions, minions, etc.)"
    )
    @app_commands.autocomplete(owner=owner_entity_autocomplete)
    async def create_pc(self, interaction: discord.Interaction, char_name: str, owner: str = None):
        await interaction.response.defer(ephemeral=True)
        system = repositories.server.get_system(interaction.guild.id)
        CharacterClass = factories.get_specific_character(system)
        existing = repositories.character.get_character_by_name(interaction.guild.id, char_name)
        if existing:
            await interaction.followup.send(f"❌ A character named `{char_name}` already exists.", ephemeral=True)
            return
        
        # Validate owner entity if specified
        owner_entity = None
        if owner and owner.strip():
            owner_entity = repositories.character.get_character_by_name(interaction.guild.id, owner)
            if not owner_entity:
                await interaction.followup.send(f"❌ Owner entity `{owner}` not found.", ephemeral=True)
                return
            
            # Check if user can use this entity as an owner
            is_gm = await repositories.server.has_gm_permission(interaction.guild.id, interaction.user)
            if not is_gm and str(owner_entity.owner_id) != str(interaction.user.id):
                await interaction.followup.send("❌ You can only create characters owned by entities you control.", ephemeral=True)
                return
        
        # Create a new Character instance using the helper method
        char_id = str(uuid.uuid4())
        character_dict = BaseCharacter.build_entity_dict(
            id=char_id,
            name=char_name,
            owner_id=interaction.user.id,
            is_npc=False
        )
        
        character = CharacterClass(character_dict)
        character.apply_defaults(EntityType.PC, guild_id=interaction.guild.id)
        repositories.character.upsert_character(interaction.guild.id, character, system=system)
        
        # Create ownership relationship if owner specified
        if owner_entity:
            repositories.relationship.create_relationship(
                guild_id=str(interaction.guild.id),
                from_entity_id=owner_entity.id,
                to_entity_id=char_id,
                relationship_type=RelationshipType.OWNS.value,
                metadata={"created_by": str(interaction.user.id)}
            )
            owner_info = f" owned by **{owner}**"
        else:
            owner_info = ""
        
        # Set as active if no active character exists
        if not repositories.active_character.get_active_character(interaction.guild.id, interaction.user.id):
            repositories.active_character.set_active_character(str(interaction.guild.id), str(interaction.user.id), char_id)
        
        await interaction.followup.send(f'📝 Created {system.upper()} character: **{char_name}**{owner_info}.', ephemeral=True)

    @create_group.command(name="npc", description="GM: Create a new NPC with a required name")
    @app_commands.describe(
        npc_name="The name of the new NPC",
        owner="Optional: Entity that will own this NPC (for companions, minions, etc.)"
    )
    @app_commands.autocomplete(owner=owner_entity_autocomplete)
    async def create_npc(self, interaction: discord.Interaction, npc_name: str, owner: str = None):
        await interaction.response.defer(ephemeral=True)
        if not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
            await interaction.followup.send("❌ Only GMs can create NPCs.", ephemeral=True)
            return
            
        system = repositories.server.get_system(interaction.guild.id)
        CharacterClass = factories.get_specific_character(system)
        existing = repositories.character.get_character_by_name(interaction.guild.id, npc_name)
        if existing:
            await interaction.followup.send(f"❌ An NPC named `{npc_name}` already exists.", ephemeral=True)
            return
        
        # Validate owner entity if specified
        owner_entity = None
        if owner and owner.strip():
            owner_entity = repositories.character.get_character_by_name(interaction.guild.id, owner)
            if not owner_entity:
                await interaction.followup.send(f"❌ Owner entity `{owner}` not found.", ephemeral=True)
                return
            
        # Create a new Character instance using the helper method
        npc_id = str(uuid.uuid4())
        character_dict = BaseCharacter.build_entity_dict(
            id=npc_id,
            name=npc_name,
            owner_id=interaction.user.id,
            is_npc=True
        )
        
        character = CharacterClass(character_dict)
        character.apply_defaults(EntityType.NPC, guild_id=interaction.guild.id)
        repositories.character.upsert_character(interaction.guild.id, character, system=system)
        
        # Create ownership relationship if owner specified
        if owner_entity:
            repositories.relationship.create_relationship(
                guild_id=str(interaction.guild.id),
                from_entity_id=owner_entity.id,
                to_entity_id=npc_id,
                relationship_type=RelationshipType.OWNS.value,
                metadata={"created_by": str(interaction.user.id)}
            )
            owner_info = f" owned by **{owner}**"
        else:
            owner_info = ""
        
        await interaction.followup.send(f"🤖 Created NPC: **{npc_name}**{owner_info}", ephemeral=True)

    @character_group.command(name="list", description="List characters and NPCs")
    @app_commands.describe(
        show_npcs="Show NPCs (GM only)",
        owned_by="Filter by owner entity",
        show_relationships="Show ownership relationships"
    )
    @app_commands.autocomplete(owned_by=character_or_npc_autocomplete)
    async def list_characters(self, interaction: discord.Interaction, show_npcs: bool = False, owned_by: str = None, show_relationships: bool = False):
        await interaction.response.defer(ephemeral=True)
        
        system = repositories.server.get_system(interaction.guild.id)
        
        # Get characters based on filters
        if owned_by:
            owner_entity = repositories.character.get_character_by_name(interaction.guild.id, owned_by)
            if not owner_entity:
                await interaction.followup.send(f"❌ Owner entity '{owned_by}' not found.", ephemeral=True)
                return
            
            # Get entities owned by this entity
            owned_entities = repositories.relationship.get_children(
                str(interaction.guild.id), 
                owner_entity.id, 
                RelationshipType.OWNS.value
            )
            characters = owned_entities
            title = f"Characters owned by {owned_by}"
        else:
            characters = repositories.character.get_all_by_guild(interaction.guild.id, system)
            title = "Characters"
        
        # Filter by user's permissions
        if not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
            if show_npcs:
                await interaction.followup.send("❌ Only GMs can view NPCs.", ephemeral=True)
                return
            # Show only user's characters
            characters = [char for char in characters if char.owner_id == str(interaction.user.id)]
        else:
            # GM can see all, but filter NPCs if requested
            if not show_npcs:
                characters = [char for char in characters if not char.is_npc]
            
            if show_npcs:
                title += " (NPCs included)"

        if not characters:
            await interaction.followup.send("No characters found.", ephemeral=True)
            return

        # Create embed
        embed = discord.Embed(title=title, color=discord.Color.blue())
        
        if show_relationships:
            # Show detailed relationship information
            character_info = []
            for char in characters:
                owners = repositories.relationship.get_parents(
                    str(interaction.guild.id), 
                    char.id, 
                    RelationshipType.OWNS.value
                )
                
                controlled_by = repositories.relationship.get_parents(
                    str(interaction.guild.id), 
                    char.id, 
                    RelationshipType.CONTROLS.value
                )
                
                owned_entities = repositories.relationship.get_children(
                    str(interaction.guild.id), 
                    char.id, 
                    RelationshipType.OWNS.value
                )
                
                info = f"**{char.name}** ({'NPC' if char.is_npc else 'PC'})"
                if owners:
                    info += f"\n  *Owned by: {', '.join([o.name for o in owners])}*"
                if controlled_by:
                    info += f"\n  *Controlled by: {', '.join([c.name for c in controlled_by])}*"
                if owned_entities:
                    info += f"\n  *Owns: {', '.join([e.name for e in owned_entities])}*"
                
                character_info.append(info)
            
            embed.description = "\n\n".join(character_info)
        else:
            # Simple list grouped by type
            pcs = [char for char in characters if not char.is_npc]
            npcs = [char for char in characters if char.is_npc]
            
            if pcs:
                pc_lines = []
                for char in pcs:
                    owned_entities = repositories.relationship.get_children(
                        str(interaction.guild.id), 
                        char.id, 
                        RelationshipType.OWNS.value
                    )
                    owned_info = f" ({len(owned_entities)} owned)" if owned_entities else ""
                    pc_lines.append(f"• {char.name}{owned_info}")
                
                embed.add_field(
                    name=f"Player Characters ({len(pcs)})",
                    value="\n".join(pc_lines)[:1024],
                    inline=False
                )
            
            if npcs:
                npc_lines = []
                for char in npcs:
                    owned_entities = repositories.relationship.get_children(
                        str(interaction.guild.id), 
                        char.id, 
                        RelationshipType.OWNS.value
                    )
                    owned_info = f" ({len(owned_entities)} owned)" if owned_entities else ""
                    npc_lines.append(f"• {char.name}{owned_info}")
                
                embed.add_field(
                    name=f"NPCs ({len(npcs)})",
                    value="\n".join(npc_lines)[:1024],
                    inline=False
                )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @character_group.command(name="delete", description="Delete a character or NPC")
    @app_commands.describe(char_name="Name of the character/NPC to delete")
    @app_commands.autocomplete(char_name=character_or_npc_autocomplete)
    async def delete_character(self, interaction: discord.Interaction, char_name: str):
        character = repositories.character.get_character_by_name(interaction.guild.id, char_name)
        if not character:
            await interaction.response.send_message("❌ Character not found.", ephemeral=True)
            return

        # Check permissions
        if character.is_npc and not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
            await interaction.response.send_message("❌ Only GMs can delete NPCs.", ephemeral=True)
            return
        
        if not character.is_npc and character.owner_id != str(interaction.user.id):
            if not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
                await interaction.response.send_message("❌ You can only delete your own characters.", ephemeral=True)
                return

        # Check if this character owns other entities
        owned_entities = repositories.relationship.get_children(
            str(interaction.guild.id), 
            character.id, 
            RelationshipType.OWNS.value
        )
        
        if owned_entities:
            entity_names = [entity.name for entity in owned_entities]
            await interaction.response.send_message(
                f"❌ Cannot delete **{char_name}** because it owns other entities: {', '.join(entity_names)}.\n"
                f"Please transfer or delete these entities first, or use `/relationship remove` to remove the ownership relationships.",
                ephemeral=True
            )
            return

        # Show confirmation
        view = ConfirmDeleteCharacterView(character)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to delete **{char_name}** ({'NPC' if character.is_npc else 'PC'})?\n"
            f"This action cannot be undone.",
            view=view,
            ephemeral=True
        )

    @character_group.command(name="sheet", description="View a character or NPC's full sheet")
    @app_commands.describe(char_name="Leave blank to view your character, or enter an NPC name")
    async def sheet(self, interaction: discord.Interaction, char_name: str = None):
        character = None
        if not char_name:
            character = repositories.active_character.get_active_character(interaction.guild.id, interaction.user.id)
            if not character:
                await interaction.response.send_message("❌ No active character set. Use `/character switch` to choose one.", ephemeral=True)
                return
        else:
            character = repositories.character.get_character_by_name(interaction.guild.id, char_name)
            if not character:
                await interaction.response.send_message("❌ Character not found.", ephemeral=True)
                return

        if character.is_npc and not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
            await interaction.response.send_message("❌ Only the GM can view NPCs.", ephemeral=True)
            return

        system = repositories.server.get_system(interaction.guild.id)
        sheet_view = factories.get_specific_sheet_view(system, interaction.user.id, character.id)
        embed = character.format_full_sheet()  # Call method directly on character
        await interaction.response.send_message(embed=embed, view=sheet_view, ephemeral=True)

    @character_group.command(name="export", description="Export your character or an NPC (if GM) as a JSON file")
    @app_commands.describe(char_name="Leave blank to export your character, or enter an NPC name")
    async def export(self, interaction: discord.Interaction, char_name: str = None):
        await interaction.response.defer(ephemeral=True)
        system = repositories.server.get_system(interaction.guild.id)
        
        if char_name is None:
            # Get user's PC
            user_chars = repositories.character.get_user_characters(interaction.guild.id, interaction.user.id)
            character = user_chars[0] if user_chars else None
            if not character:
                await interaction.followup.send("❌ You don't have a character to export.", ephemeral=True)
                return
        else:
            character = repositories.character.get_character_by_name(interaction.guild.id, char_name)
            if not character:
                await interaction.followup.send("❌ Character not found.", ephemeral=True)
                return
                
            if character.is_npc and not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
                await interaction.followup.send("❌ Only the GM can export NPCs.", ephemeral=True)
                return
            elif not character.is_npc and str(character.owner_id) != str(interaction.user.id):
                await interaction.followup.send("❌ You can only export your own character.", ephemeral=True)
                return
        
        # Export character data including relationships
        export_data = character.data.copy()
        export_data["system"] = system
        
        # Add relationship information to export
        relationships = repositories.relationship.get_relationships_for_entity(
            interaction.guild.id, 
            character.id
        )
            
        # Export relationships as metadata
        export_data['relationships'] = []
        for rel in relationships:
            # Get the other entity's name for clarity
            if rel.from_entity_id == character.id:
                other_entity = repositories.character.get_by_id(rel.to_entity_id)
                if other_entity:
                    export_data['relationships'].append({
                        'type': 'outgoing',
                        'relationship_type': rel.relationship_type,
                        'target_name': other_entity.name,
                        'target_id': rel.to_entity_id,
                        'metadata': rel.metadata
                    })
            else:
                other_entity = repositories.character.get_by_id(rel.from_entity_id)
                if other_entity:
                    export_data['relationships'].append({
                        'type': 'incoming',
                        'relationship_type': rel.relationship_type,
                        'source_name': other_entity.name,
                        'source_id': rel.from_entity_id,
                        'metadata': rel.metadata
                    })
        
        import io
        file_content = json.dumps(export_data, indent=2)
        file = discord.File(io.BytesIO(file_content.encode('utf-8')), filename=f"{character.name}.json")
        await interaction.followup.send(f"📁 Exported **{character.name}** with relationship data.", file=file, ephemeral=True)

    @character_group.command(name="import", description="Import a character or NPC from a JSON file. The owner will be set to you")
    @app_commands.describe(file="A .json file exported from this bot")
    async def import_char(self, interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        
        if not file.filename.endswith('.json'):
            await interaction.followup.send("❌ Only .json files are supported.", ephemeral=True)
            return
            
        try:
            file_bytes = await file.read()
            data = json.loads(file_bytes.decode('utf-8'))
        except Exception:
            await interaction.followup.send("❌ Could not decode or parse the file. Make sure it's a valid JSON export from this bot.", ephemeral=True)
            return
            
        system = repositories.server.get_system(interaction.guild.id)
        CharacterClass = factories.get_specific_character(system)
        
        # Extract key fields from imported data
        id = data.get("id") or str(uuid.uuid4())
        name = data.get("name", "Imported Character")
        is_npc = data.get("is_npc", False)
        notes = data.get("notes", [])
        avatar_url = data.get("avatar_url")
        
        # Use the helper method
        character_dict = BaseCharacter.build_entity_dict(
            id=id,
            name=name,
            owner_id=interaction.user.id,  # Always set owner to current user
            is_npc=is_npc,
            notes=notes,
            avatar_url=avatar_url
        )
        
        # Copy over any system-specific fields
        system_fields = CharacterClass.ENTITY_DEFAULTS.get_defaults(EntityType.NPC if is_npc else EntityType.PC)
        for key in system_fields:
            if key in data:
                character_dict[key] = data[key]
    
        character = CharacterClass(character_dict)
        character.apply_defaults(entity_type=EntityType.NPC if is_npc else EntityType.PC, guild_id=interaction.guild.id)
        
        if character.is_npc and not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
            await interaction.followup.send("❌ Only GMs can import NPCs.", ephemeral=True)
            return

        # Save character first
        repositories.character.upsert_character(interaction.guild.id, character, system=system)
        
        # Handle relationships if they exist in the export
        relationships_created = 0
        if 'relationships' in data:
            for rel_data in data['relationships']:
                try:
                    if rel_data['type'] == 'outgoing':
                        # This character has a relationship TO another entity
                        # Try to find the target entity by name
                        target_entity = repositories.character.get_character_by_name(
                            interaction.guild.id, 
                            rel_data['target_name']
                        )
                        if target_entity:
                            repositories.relationship.create_relationship(
                                str(interaction.guild.id),
                                character.id,
                                target_entity.id,
                                rel_data['relationship_type'],
                                rel_data.get('metadata', {})
                            )
                            relationships_created += 1
                    elif rel_data['type'] == 'incoming':
                        # Another entity has a relationship TO this character
                        # Try to find the source entity by name
                        source_entity = repositories.character.get_character_by_name(
                            interaction.guild.id, 
                            rel_data['source_name']
                        )
                        if source_entity:
                            repositories.relationship.create_relationship(
                                str(interaction.guild.id),
                                source_entity.id,
                                character.id,
                                rel_data['relationship_type'],
                                rel_data.get('metadata', {})
                            )
                            relationships_created += 1
                except Exception as e:
                    # Log the error but don't fail the entire import
                    print(f"Error creating relationship during import: {e}")
        
        success_message = f"✅ Imported {'NPC' if character.is_npc else 'character'} **{character.name}**."
        if relationships_created > 0:
            success_message += f" Created {relationships_created} relationships."
        
        await interaction.followup.send(success_message, ephemeral=True)

    @character_group.command(name="transfer", description="GM: Transfer a PC to another player")
    @app_commands.describe(
        char_name="Name of the character to transfer",
        new_owner="The user to transfer ownership to"
    )
    @app_commands.autocomplete(char_name=pc_name_gm_autocomplete)
    async def transfer(self, interaction: discord.Interaction, char_name: str, new_owner: discord.Member):
        if not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
            await interaction.response.send_message("❌ Only GMs can transfer characters.", ephemeral=True)
            return
            
        character = repositories.character.get_character_by_name(interaction.guild.id, char_name)
        if not character or character.is_npc:
            await interaction.response.send_message("❌ PC not found.", ephemeral=True)
            return
            
        character.owner_id = new_owner.id
        system = repositories.server.get_system(interaction.guild.id)
        repositories.character.upsert_character(interaction.guild.id, character, system=system)
        await interaction.response.send_message(
            f"✅ Ownership of `{char_name}` transferred to {new_owner.display_name}.", ephemeral=True
        )

    @character_group.command(name="switch", description="Set your active character (PC) for this server")
    @app_commands.describe(char_name="The name of your character to set as active")
    @app_commands.autocomplete(char_name=pc_switch_name_autocomplete)
    async def switch(self, interaction: discord.Interaction, char_name: str):
        user_chars = repositories.character.get_user_characters(interaction.guild.id, interaction.user.id)
        character = next(
            (c for c in user_chars if c.name.lower() == char_name.lower()),
            None
        )
        if not character:
            await interaction.response.send_message(f"❌ You don't have a character named `{char_name}`.", ephemeral=True)
            return
            
        repositories.active_character.set_active_character(str(interaction.guild.id), str(interaction.user.id), character.id)
        await interaction.response.send_message(f"✅ `{char_name}` is now your active character.", ephemeral=True)

    @character_group.command(name="setavatar", description="Set your character's avatar image")
    @app_commands.describe(
        avatar_url="URL to an image for your character's avatar",
        char_name="Optional: Character/NPC name (defaults to your active character)"
    )
    @app_commands.autocomplete(char_name=character_or_npc_autocomplete)
    async def character_setavatar(self, interaction: discord.Interaction, avatar_url: str, char_name: str = None):
        """Set an avatar image URL for your character or an NPC (if GM)"""
        
        # Determine which character to set avatar for
        character = None
        if char_name:
            # User specified a character name
            character = repositories.character.get_character_by_name(interaction.guild.id, char_name)
            if not character:
                await interaction.response.send_message(f"❌ Character '{char_name}' not found.", ephemeral=True)
                return
                
            # Check permissions
            if character.is_npc:
                # Only GMs can set NPC avatars
                if not await repositories.server.has_gm_permission(interaction.guild.id, interaction.user):
                    await interaction.response.send_message("❌ Only GMs can set NPC avatars.", ephemeral=True)
                    return
            else:
                # Only the owner can set PC avatars (unless GM)
                is_gm = await repositories.server.has_gm_permission(interaction.guild.id, interaction.user)
                if str(character.owner_id) != str(interaction.user.id) and not is_gm:
                    await interaction.response.send_message("❌ You can only set avatars for your own characters.", ephemeral=True)
                    return
        else:
            # No character specified, use active character
            character = repositories.active_character.get_active_character(interaction.guild.id, interaction.user.id)
            if not character:
                await interaction.response.send_message("❌ You don't have an active character set. Use `/character switch` to choose one or specify a character name.", ephemeral=True)
                return
        
        # Basic URL validation
        if not avatar_url.startswith(("http://", "https://")):
            await interaction.response.send_message("❌ Please provide a valid image URL starting with http:// or https://", ephemeral=True)
            return
        
        # Save the avatar URL to the character
        character.avatar_url = avatar_url
        system = repositories.server.get_system(interaction.guild.id)
        repositories.character.upsert_character(interaction.guild.id, character, system=system)

        # Show a preview
        embed = discord.Embed(
            title="Avatar Updated",
            description=f"Avatar for **{character.name}** has been set.",
            color=discord.Color.green()
        )
        embed.set_image(url=avatar_url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @character_group.command(name="narration", description="Get help with character narration formatting")
    async def character_narration_help(self, interaction: discord.Interaction):
        """Display help information about speaking as characters and GM narration"""
        
        embed = discord.Embed(
            title="📢 Character Narration Guide",
            description="How to speak as characters or narrate as a GM in play-by-post games",
            color=discord.Color.blue()
        )

        # Check if there are any channel restrictions set up
        channel_permissions = repositories.channel_permissions.get_all_channel_permissions(str(interaction.guild.id))
        has_restrictions = len(channel_permissions) > 0
        
        embed.add_field(
            name="Speaking as Your Character",
            value=(
                "Type a message starting with `pc::` followed by what your character says.\n"
                "Example: `pc::I draw my sword and advance cautiously.`\n\n"
                "Your active character will be used. Make sure to set an active character first with `/character switch`."
            ),
            inline=False
        )
        
        embed.add_field(
            name="For GMs: Speaking as NPCs",
            value=(
                "**Basic Format**\n"
                "`npc::Character Name::Message content`\n"
                "Example: `npc::Bartender::What'll it be, stranger?`\n\n"
                "**With Custom Display Name**\n"
                "`npc::Character Name::Display Name::Message content`\n"
                "Example: `npc::Mysterious Figure::Hooded Stranger::Keep your voice down!`\n\n"
                "**On-the-fly NPCs**\n"
                "If you use a name that doesn't exist in the database, the bot will still create a temporary character to display the message."
            ),
            inline=False
        )
        
        embed.add_field(
            name="GM Narration",
            value=(
                "As a GM, you can narrate scenes with a distinctive format:\n"
                "`gm::Your narration text here`\n"
                "Example: `gm::The ground trembles as thunder rumbles overhead. The storm is getting closer.`\n\n"
                "GM narration appears with a purple embed and your avatar as the GM."
            ),
            inline=False
        )

        # Add channel restrictions info if they exist
        if has_restrictions:
            embed.add_field(
                name="⚠️ Channel Restrictions",
                value=(
                    "Narration commands (`pc::`, `npc::`, `gm::`) are **not allowed** in **Out-of-Character (OOC)** channels.\n"
                    "Use these commands in **In-Character (IC)** or **Unrestricted** channels to maintain immersion.\n\n"
                    "GMs can configure channel types with `/setup channel type`."
                ),
                inline=False
            )
        
        embed.add_field(
            name="Text Formatting",
            value=(
                "You can use Discord's standard formatting in your messages:\n"
                "• *Italics*: `*text*` or `_text_`\n"
                "• **Bold**: `**text**`\n"
                "• __Underline__: `__text__`\n"
                "• ~~Strikethrough~~: `~~text~~`\n"
                "• `Code`: `` `text` ``\n"
                "• ```Block quotes```: \\```text\\```"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Character Avatars",
            value=(
                "Set your character's avatar with the command:\n"
                "`/character setavatar [url]`\n\n"
                "This avatar will appear with your character's messages."
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ConfirmDeleteCharacterView(discord.ui.View):
    def __init__(self, character: BaseCharacter):
        super().__init__(timeout=60)
        self.character = character

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Delete the character (this will also delete all relationships)
        repositories.character.delete_character(interaction.guild.id, self.character.id)
        await interaction.response.edit_message(
            content=f"✅ Deleted character **{self.character.name}**.",
            view=None
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Deletion cancelled.",
            view=None
        )

async def setup_character_commands(bot: commands.Bot):
    await bot.add_cog(CharacterCommands(bot))