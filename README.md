# Clozemaster MCP

A local [MCP](https://modelcontextprotocol.io) server for a signed-in Clozemaster account. It calls the same JSON API the website uses. There is no API key.

Sign-in happens in a browser window the server opens. The password stays in that window. The session is stored in a Chrome profile under `%LOCALAPPDATA%\clozemaster-mcp\profile`, which is outside this repo.

The default collection is Greek School of Glasgow - B1, id `119463`.

The tools can list collections and cards, add a card, change its English and note, delete one card when the Greek text matches, hide a card from play, and read the next play cards. They do not delete a collection and do not reset progress.

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
| `clozemaster_list_collections` | Lists your Greek–English collections |
| `clozemaster_list_sentences` | Lists cards, with an optional search |
| `clozemaster_add_sentence` | Adds one card and marks the cloze |
| `clozemaster_update_sentence` | Changes the English and the note |
| `clozemaster_delete_sentence` | Deletes one card when the Greek text matches |
| `clozemaster_ignore_sentence` | Hides one card from play |
| `clozemaster_next_cards` | Reads the next play cards |
