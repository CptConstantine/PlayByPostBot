from typing import Dict, List
from .base_repository import BaseRepository
from data.models import HomebrewRule
from datetime import datetime

class HomebrewRepository(BaseRepository[HomebrewRule]):
    def __init__(self):
        super().__init__('homebrew_rules')
    
    def to_dict(self, entity: HomebrewRule) -> dict:
        return {
            'guild_id': entity.guild_id,
            'rule_name': entity.rule_name,
            'rule_text': entity.rule_text,
            'created_at': entity.created_at or datetime.now(),
            'updated_at': datetime.now()
        }
    
    def from_dict(self, data: dict) -> HomebrewRule:
        return HomebrewRule(
            guild_id=data['guild_id'],
            rule_name=data['rule_name'],
            rule_text=data['rule_text'],
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
    
    def get_all_homebrew_rules(self, guild_id: str) -> List[HomebrewRule]:
        """Return dictionary mapping rule names to rule text"""
        return self.find_all_by_column('guild_id', str(guild_id))
    
    def upsert_rule(self, guild_id: str, rule_name: str, rule_text: str) -> None:
        rule = HomebrewRule(
            guild_id=str(guild_id),
            rule_name=rule_name,
            rule_text=rule_text
        )
        self.save(rule, conflict_columns=['guild_id', 'rule_name'])
    
    def remove_rule(self, guild_id: str, rule_name: str) -> bool:
        deleted_count = self.delete(
            "guild_id = %s AND rule_name = %s",
            (str(guild_id), rule_name)
        )
        return deleted_count > 0