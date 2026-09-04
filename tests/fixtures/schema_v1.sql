PRAGMA user_version = 1;

CREATE TABLE prompts (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    key TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    model TEXT NOT NULL,
    response TEXT NOT NULL
);

INSERT INTO prompts (key, prompt, model, response)
VALUES ('resp_v1', 'version one question', 'version-one-model', 'version one answer');
