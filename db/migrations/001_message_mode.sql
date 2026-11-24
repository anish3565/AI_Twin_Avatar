-- Records which mode (avatar, voice or text) the visitor was in for each message.
-- Safe to run more than once. Existing rows keep mode = null.
alter table messages
    add column if not exists mode text
    check (mode in ('avatar', 'voice', 'text'));
