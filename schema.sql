CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT,
    is_patient BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, is_patient)
);

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
    member_is_patient BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT patients_member_is_patient_fk
        FOREIGN KEY (id, member_is_patient) REFERENCES members(id, is_patient),
    CONSTRAINT patients_member_is_patient_check CHECK (member_is_patient = true)
);

CREATE TABLE IF NOT EXISTS patient_family_members (
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (patient_id, member_id),
    CONSTRAINT family_member_must_not_be_patient CHECK (patient_id <> member_id)
);

CREATE TABLE IF NOT EXISTS question_answers (
    id BIGSERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    ask_time TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS family_notifications (
    id BIGSERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    answer TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS question_answers_patient_time_idx
    ON question_answers (patient_id, ask_time DESC);
CREATE INDEX IF NOT EXISTS patient_family_members_member_idx
    ON patient_family_members (member_id);
