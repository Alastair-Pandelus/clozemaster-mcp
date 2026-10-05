"""MCP tools for the signed-in Clozemaster collection API."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from clozemaster_mcp.client import (
    B1_COLLECTION_ID,
    LoginRequired,
    add_sentence,
    browser,
    delete_sentence,
    ignore_sentence,
    list_collections,
    list_sentences,
    login,
    next_cards,
    open_dashboard,
    update_sentence,
)

mcp = MCPServer(
    "clozemaster",
    instructions=(
        "Clozemaster tools for the signed-in account. The default collection is "
        f"Greek School of Glasgow - B1, id {B1_COLLECTION_ID}. "
        "If a tool says the session has expired, ask the user to run login and "
        "sign in in the window. Do not ask for their password. "
        "These tools do not delete a collection and do not reset progress."
    ),
)


def _run(work):
    try:
        with browser(headless=True) as page:
            open_dashboard(page)
            return json.dumps(work(page), ensure_ascii=False, indent=2)
    except LoginRequired as exc:
        return str(exc)


@mcp.tool()
def clozemaster_login() -> str:
    """Open Clozemaster in a window so the user can sign in.

    The password stays in that window. The session is stored in a browser
    profile on this PC, outside the repo. Wait until this returns before
    calling the other tools.
    """
    try:
        return login()
    except LoginRequired as exc:
        return str(exc)


@mcp.tool()
def clozemaster_list_collections() -> str:
    """List Clozemaster collections on the Greek–English account."""
    return _run(list_collections)


@mcp.tool()
def clozemaster_list_sentences(query: str = "", collection_id: int | None = None) -> str:
    """List cards in a collection. Defaults to the B1 course.

    query filters by Clozemaster's sentence search. collection_id overrides
    the default B1 collection.
    """
    return _run(lambda page: list_sentences(page, collection_id, query))


@mcp.tool()
def clozemaster_add_sentence(
    greek: str,
    english: str,
    cloze: str,
    note: str,
    collection_id: int | None = None,
) -> str:
    """Add one card. cloze must be one whole word in greek.

    The server marks that word with double braces. note is the dictionary line.
    """
    return _run(
        lambda page: add_sentence(page, greek, english, cloze, note, collection_id)
    )


@mcp.tool()
def clozemaster_update_sentence(
    sentence_id: int,
    english: str,
    note: str,
    collection_id: int | None = None,
) -> str:
    """Change the English and note of an existing card. The Greek stays as it is."""
    return _run(
        lambda page: update_sentence(page, sentence_id, english, note, collection_id)
    )


@mcp.tool()
def clozemaster_delete_sentence(
    sentence_id: int,
    greek: str,
    collection_id: int | None = None,
) -> str:
    """Delete one card. greek must match that card's sentence, or the delete is refused.

    This drops progress on that card only.
    """
    return _run(lambda page: delete_sentence(page, sentence_id, greek, collection_id))


@mcp.tool()
def clozemaster_ignore_sentence(
    sentence_id: int,
    collection_id: int | None = None,
) -> str:
    """Hide one card from play. The card stays in the collection."""
    return _run(lambda page: ignore_sentence(page, sentence_id, collection_id))


@mcp.tool()
def clozemaster_next_cards(collection_id: int | None = None) -> str:
    """Read the next play cards for a collection. This does not submit an answer."""
    return _run(lambda page: next_cards(page, collection_id))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
