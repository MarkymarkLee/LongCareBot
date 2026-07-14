from collections.abc import AsyncIterator

import asyncpg

from .config import Settings


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.settings.database_url, min_size=1, max_size=10)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        if not self.pool:
            raise RuntimeError("Database has not been connected")
        return self.pool.acquire()

    async def known_answers(self, patient_id: str | None) -> list[dict[str, str]]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """SELECT question, answer, ask_time::text AS ask_time
                   FROM question_answers
                   WHERE patient_id IS NULL OR patient_id = $1
                   ORDER BY ask_time DESC""",
                patient_id,
            )
        return [dict(row) for row in rows]

    async def save_answer(self, patient_id: str | None, question: str, answer: str) -> None:
        async with self.acquire() as conn:
            await conn.execute(
                "INSERT INTO question_answers(patient_id, question, answer) VALUES($1, $2, $3)",
                patient_id,
                question,
                answer,
            )

    async def create_family_notification(self, patient_id: str, question: str) -> int:
        async with self.acquire() as conn:
            notification_id = await conn.fetchval(
                """INSERT INTO family_notifications(patient_id, question)
                   VALUES($1, $2) RETURNING id""",
                patient_id,
                question,
            )
            await conn.execute(
                "SELECT pg_notify('family_question', $1)",
                f"{notification_id}:{patient_id}:{question}",
            )
            return notification_id

    async def family_member_can_access(self, member_id: str, patient_id: str) -> bool:
        async with self.acquire() as conn:
            return bool(await conn.fetchval(
                """SELECT 1 FROM family_members
                   WHERE id = $1 AND patient_id = $2 AND active = true""",
                member_id,
                patient_id,
            ))

    async def answer_family_notification(self, notification_id: int, patient_id: str, answer: str) -> bool:
        async with self.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """UPDATE family_notifications
                       SET status = 'answered', answer = $1, answered_at = now()
                       WHERE id = $2 AND patient_id = $3 AND status = 'pending'
                       RETURNING question""",
                    answer,
                    notification_id,
                    patient_id,
                )
                if row is None:
                    return False
                await conn.execute(
                    "INSERT INTO question_answers(patient_id, question, answer) VALUES($1, $2, $3)",
                    patient_id,
                    row["question"],
                    answer,
                )
                return True
