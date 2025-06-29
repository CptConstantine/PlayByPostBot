from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import discord

class NotesMixin:
    def add_note(self, note: str):
        if "notes" not in self.data or not isinstance(self.data["notes"], list):
            self.data["notes"] = []
        self.data["notes"].append(note)

    def get_notes(self) -> List[str]:
        return self.data.get("notes", [])

class BaseRpgObj(ABC, NotesMixin):
    """
    Abstract base class for a "thing".
    """
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseRpgObj":
        """Deserialize an entity from a dict."""
        return cls(data)

    @property
    def id(self) -> str:
        return self.data.get("id")

    @id.setter
    def id(self, value: str):
        self.data["id"] = value

    @property
    def owner_id(self) -> Optional[str]:
        return self.data.get("owner_id")

    @owner_id.setter
    def owner_id(self, value: str):
        self.data["owner_id"] = value

    @property
    def notes(self) -> list:
        return self.data.get("notes", [])

    @notes.setter
    def notes(self, value: list):
        self.data["notes"] = value

class BaseSheet(ABC):
    @abstractmethod
    def format_full_sheet(self, character: Dict[str, Any]) -> discord.Embed:
        """Return a Discord Embed representing the full character sheet."""
        pass

    @abstractmethod
    def format_npc_scene_entry(self, npc: Dict[str, Any], is_gm: bool) -> str:
        """Return a string for displaying an NPC in a scene summary."""
        pass

class BaseInitiative(ABC):
    """
    Abstract base class for initiative.
    System-specific initiative classes should inherit from this and implement all methods.
    """
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseInitiative":
        """Deserialize an entity from a dict."""
        return cls(data)

    @property
    def type(self) -> str:
        return self.data.get("type")

    @type.setter
    def type(self, value: str):
        self.data["type"] = value

    @property
    def remaining_in_round(self) -> list:
        return self.data.get("remaining_in_round", [])

    @remaining_in_round.setter
    def remaining_in_round(self, value: list):
        self.data["remaining_in_round"] = value

    @property
    def round_number(self) -> int:
        # Pythonic: default to 1 if not set
        return self.data.get("round_number", 1)

    @round_number.setter
    def round_number(self, value: int):
        self.data["round_number"] = value

class RollModifiers(ABC):
    """
    A flexible container for roll parameters (e.g., skill, attribute, modifiers).
    Non-modifier properties (like skill, attribute) are stored in a separate dictionary.
    Modifiers are stored in self.modifiers.
    """
    def __init__(self, roll_parameters_dict: dict = None):
        self.modifiers = {}  # Store direct numeric modifiers (e.g., mod1, mod2)
        if roll_parameters_dict:
            for key, modifier in roll_parameters_dict.items():
                self.modifiers[key] = modifier

    def __getitem__(self, key):
        return self.modifiers.get(key)

    def __setitem__(self, key, value):
        self.modifiers[key] = value

    def to_dict(self):
        return dict(self.modifiers)

    def get_modifiers(self, character: "BaseCharacter") -> Dict[str, str]:
        """
        Returns a dictionary of all modifiers
        """
        return dict(self.modifiers)

    def __repr__(self):
        return f"RollModifiers(modifiers={self.modifiers})"
    
class BaseEntity(BaseRpgObj):
    """
    Abstract base class for a "thing".
    """
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseRpgObj":
        """Deserialize an entity from a dict."""
        return cls(data)

    @property
    def entity_type(self) -> str:
        return self.data.get("entity_type")

    @entity_type.setter
    def entity_type(self, value: str):
        self.data["entity_type"] = value

    @property
    def name(self) -> str:
        return self.data.get("name")

    @name.setter
    def name(self, value: str):
        self.data["name"] = value
    
    @property
    def avatar_url(self):
        return self.data.get("avatar_url", '')
    
    @avatar_url.setter
    def avatar_url(self, url):
        self.data["avatar_url"] = url

class BaseCharacter(BaseEntity):
    """
    Abstract base class for a character (PC or NPC).
    System-specific character classes should inherit from this and implement all methods.
    """
    SYSTEM_SPECIFIC_CHARACTER = {}
    SYSTEM_SPECIFIC_NPC = {}

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        if not hasattr(self, 'SYSTEM_SPECIFIC_CHARACTER'):
            raise NotImplementedError("SYSTEM_SPECIFIC_CHARACTER must be defined in the subclass.")
        if not hasattr(self, 'SYSTEM_SPECIFIC_NPC'):
            raise NotImplementedError("SYSTEM_SPECIFIC_NPC must be defined in the subclass.")

    @property
    def is_npc(self) -> bool:
        return self.data.get("entity_type") == "npc"

    @is_npc.setter
    def is_npc(self, value: bool):
        self.data["entity_type"] = "npc" if value else "pc"

    @staticmethod
    def create_base_character(id, name, owner_id, is_npc=False, notes=None, avatar_url=None, system_specific_fields=None):
        """
        Helper method to create a standardized character dictionary.
        
        Args:
            id (str): Unique character ID
            name (str): Character name
            owner_id (str): ID of the character's owner
            is_npc (bool): Whether the character is an NPC
            notes (list): List of character notes
            avatar_url (str): URL to character's avatar image
            additional_fields: Any additional system-specific fields
            
        Returns:
            dict: A properly formatted character dictionary
        """
        character = {
            "id": str(id),
            "name": name,
            "owner_id": str(owner_id),
            "entity_type": "npc" if is_npc else "pc",
            "notes": notes or [],
            "avatar_url": avatar_url or '',
        }
        
        # Add any additional fields
        if system_specific_fields:
            for key, value in system_specific_fields.items():
                character[key] = value
            
        return character

    @abstractmethod
    def apply_defaults(self, is_npc=False, guild_id=None):
        """Apply system-specific default fields to a character dict."""
        pass
    
    @abstractmethod
    async def edit_requested_roll(self, interaction: discord.Interaction, roll_parameters: dict, difficulty: int = None):
        """
        Abstract method to handle a roll request for this character.
        Should return a discord.ui.View or send a message with the result.
        """
        pass

    @abstractmethod
    async def send_roll_message(self, interaction: discord.Interaction, roll_formula_obj: RollModifiers, difficulty: int = None):
        """
        Abstract method to handle a roll request for this character.
        Should return a discord.ui.View or send a message with the result.
        """
        pass