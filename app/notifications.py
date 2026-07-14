from dataclasses import dataclass

from .db import Database


@dataclass
class FamilyNotifier:
    """Persistence-backed notifier; deliver the row through Web Push/WebSocket in production."""

    db: Database

    async def notify(self, patient_id: str, question: str) -> int:
        return await self.db.create_family_notification(patient_id, question)
