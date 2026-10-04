-- Purchases record which email provider they came from so fixture (demo mailbox) purchases
-- are labelled end to end and can be removed once a real mailbox is connected.
ALTER TABLE purchases ADD COLUMN provider TEXT NOT NULL DEFAULT '';
ALTER TABLE purchases ADD COLUMN is_fixture INTEGER NOT NULL DEFAULT 0;
-- Backfill: the fixture mailbox's message ids all start with "fx-".
UPDATE purchases SET is_fixture = 1, provider = 'fixture' WHERE source_message_ids LIKE '%"fx-%';
