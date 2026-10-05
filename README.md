# Clozemaster MCP

A local [MCP](https://modelcontextprotocol.io) server for a signed-in Clozemaster account. It calls the same JSON API the website uses. There is no API key.

Sign-in happens in a browser window the server opens. The password stays in that window. The session is stored in a Chrome profile under `%LOCALAPPDATA%\clozemaster-mcp\profile`, which is outside this repo.

## Credentials

Do not commit passwords, session cookies, CSRF tokens, or the browser profile. They stay on this PC. `.gitignore` already excludes `.env`, `profile/`, and `.profile/`. If a future change needs a secret, keep it out of the repo and out of the README.

When a tool is called without a collection id, it uses the collection this account practiced most recently. Pass `collection_id` to use a different one.

The tools work for any language pairing on the account. A card's sentence is in the collection's target language, and its translation is in the base language. They can list collections and cards, add a card, change its translation and note, delete one card when the sentence text matches, hide a card from play, and read the next play cards. They do not delete a collection and do not reset progress.

## Install

```powershell
cd C:\Dev\Github\clozemaster-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m playwright install chromium
```

Cursor is configured to launch `.\.venv\Scripts\python.exe -m clozemaster_mcp`. After the first install, reload MCP servers. Then run the `clozemaster_login` tool and sign in in the window it opens.

## Tools

| Tool | What it does |
|---|---|
| `clozemaster_login` | Opens the sign-in window and waits up to five minutes |
| `clozemaster_list_collections` | Lists your collections, most recently practiced first |
| `clozemaster_list_sentences` | Lists cards, with an optional search |
| `clozemaster_add_sentence` | Adds one card and marks the cloze |
| `clozemaster_update_sentence` | Changes the translation and the note |
| `clozemaster_delete_sentence` | Deletes one card when the sentence text matches |
| `clozemaster_ignore_sentence` | Hides one card from play |
| `clozemaster_next_cards` | Reads the next play cards |
