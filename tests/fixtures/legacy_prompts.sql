CREATE TABLE prompts (
    id INTEGER PRIMARY KEY,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    prompt TEXT,
    model TEXT,
    response TEXT
);

INSERT INTO prompts (prompt, model, response)
VALUES ('old question', 'old model', 'old answer');

