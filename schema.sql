CREATE TABLE IF NOT EXISTS question_answers (
    id BIGSERIAL PRIMARY KEY,
    patient_id TEXT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    ask_time TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS family_members (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    email TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS question_answers_patient_time_idx
    ON question_answers (patient_id, ask_time DESC);

CREATE TABLE IF NOT EXISTS family_notifications (
    id BIGSERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    answer TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS family_members_patient_idx ON family_members (patient_id);
