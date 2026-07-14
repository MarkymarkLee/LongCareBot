from collections.abc import AsyncIterator

import asyncpg

from .config import Settings


class PatientNotFoundError(ValueError):
    """Raised when an operation references a patient not present in patients."""


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

    async def patient_exists(self, patient_id: str) -> bool:
        async with self.acquire() as conn:
            return bool(await conn.fetchval("SELECT 1 FROM patients WHERE id = $1", patient_id))

    async def create_member(
        self, member_id: str, display_name: str, email: str | None, is_patient: bool
    ) -> None:
        async with self.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """INSERT INTO members(id, display_name, email, is_patient)
                       VALUES($1, $2, $3, $4)""",
                    member_id, display_name, email, is_patient,
                )
                if is_patient:
                    await conn.execute("INSERT INTO patients(id) VALUES($1)", member_id)

    async def add_family_member(self, patient_id: str, member_id: str) -> None:
        await self.require_patient(patient_id)
        async with self.acquire() as conn:
            await conn.execute(
                """INSERT INTO patient_family_members(patient_id, member_id)
                   SELECT $1, id FROM members WHERE id = $2 AND is_patient = false
                   ON CONFLICT DO NOTHING""",
                patient_id, member_id,
            )

    async def member_can_access_patient(self, member_id: str, patient_id: str) -> bool:
        async with self.acquire() as conn:
            return bool(await conn.fetchval(
                """SELECT 1 FROM patient_family_members
                   WHERE member_id = $1 AND patient_id = $2""",
                member_id, patient_id,
            ))

    async def require_patient(self, patient_id: str) -> None:
        if not await self.patient_exists(patient_id):
            raise PatientNotFoundError(f"Patient '{patient_id}' does not exist")

    async def known_answers(self, patient_id: str) -> list[dict[str, str]]:
        await self.require_patient(patient_id)
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """SELECT question, answer, ask_time::text AS ask_time
                   FROM question_answers
                   WHERE patient_id = $1
                   ORDER BY ask_time DESC""",
                patient_id,
            )
        return [dict(row) for row in rows]

    async def save_answer(self, patient_id: str, question: str, answer: str) -> None:
        await self.require_patient(patient_id)
        async with self.acquire() as conn:
            await conn.execute(
                "INSERT INTO question_answers(patient_id, question, answer) VALUES($1, $2, $3)",
                patient_id,
                question,
                answer,
            )

    async def create_family_notification(self, patient_id: str, question: str) -> int:
        await self.require_patient(patient_id)
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
