"""MCP tools for the signed-in Clozemaster collection API."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from clozemaster_mcp.client import (
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
        "Clozemaster tools for the signed-in account, for any language pairing. "
        "A card's sentence is in the collection's target language and its "
        "translation is in the base language. They work on any collection that "
        "account created. When collection_id and collection_name are omitted, "
        "the tools use the collection practiced most recently. Pass "
        "collection_name to choose another collection by its name, or "
        "collection_id when two collections share a name. "
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
    """List this account's collections, most recently practiced first.

    The first collection is the default used when no collection is named.
    """
    return _run(list_collections)


@mcp.tool()
def clozemaster_list_sentences(
    query: str = "",
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> str:
    """List cards in a collection. Defaults to the last course practiced.

    query filters by Clozemaster's sentence search. collection_name chooses
    a collection by its name. collection_id chooses one when names collide.
    """
    return _run(
        lambda page: list_sentences(
            page, collection_id, query, collection_name=collection_name
        )
    )


@mcp.tool()
def clozemaster_add_sentence(
    sentence: str,
    translation: str,
    cloze: str,
    note: str,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> str:
    """Add one card. cloze must be one whole word in sentence.

    sentence is the target language. translation is the base language.
    The server marks the cloze with double braces. note is the dictionary line.
    collection_name chooses the collection by its name.
    """
    return _run(
        lambda page: add_sentence(
            page, sentence, translation, cloze, note, collection_id, collection_name
        )
    )


@mcp.tool()
def clozemaster_update_sentence(
    sentence_id: int,
    translation: str,
    note: str,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> str:
    """Change the translation and note of an existing card. The sentence stays as it is.

    collection_name chooses the collection by its name.
    """
    return _run(
        lambda page: update_sentence(
            page, sentence_id, translation, note, collection_id, collection_name
        )
    )


@mcp.tool()
def clozemaster_delete_sentence(
    sentence_id: int,
    sentence: str,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> str:
    """Delete one card. sentence must match that card's text, or the delete is refused.

    This drops progress on that card only. collection_name chooses the collection by its name.
    """
    return _run(
        lambda page: delete_sentence(
            page, sentence_id, sentence, collection_id, collection_name
        )
    )


@mcp.tool()
def clozemaster_ignore_sentence(
    sentence_id: int,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> str:
    """Hide one card from play. The card stays in the collection.

    collection_name chooses the collection by its name.
    """
    return _run(
        lambda page: ignore_sentence(page, sentence_id, collection_id, collection_name)
    )


@mcp.tool()
def clozemaster_next_cards(
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> str:
    """Read the next play cards for a collection. This does not submit an answer.

    collection_name chooses the collection by its name.
    """
    return _run(lambda page: next_cards(page, collection_id, collection_name))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
