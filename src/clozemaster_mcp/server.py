"""MCP tools for the signed-in Clozemaster collection API."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from clozemaster_mcp.client import (
    ClozemasterError,
    LoginRequired,
    add_sentence,
    add_sentences,
    browser,
    create_collection,
    delete_sentence,
    find_by_cloze,
    ignore_sentence,
    list_collections,
    list_sentences,
    login,
    next_cards,
    open_dashboard,
    replace_sentence,
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
        "collection_name to choose another collection. A shorter piece of the "
        "name is enough when only one collection contains it. Pass "
        "collection_id when more than one collection matches. "
        "If a tool says the session has expired, ask the user to run login and "
        "sign in in the window. Do not ask for their password. "
        "Add several cards with the lesson tool. A card is skipped when that "
        "sentence already hides the same cloze, or when that cloze is already "
        "a card. The same sentence may be added again with a new cloze. "
        "These tools do not delete a collection and do not reset progress."
    ),
)


def _run(work):
    try:
        with browser(headless=True) as page:
            open_dashboard(page)
            return json.dumps(work(page), ensure_ascii=False, indent=2)
    except (LoginRequired, ClozemasterError) as exc:
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


@mcp.tool()
def clozemaster_add_sentences(
    cards: list[dict],
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> str:
    """Add many cards in one call. Each card has sentence, translation, cloze, and note.

    A card is skipped when that sentence already hides the same cloze, or when
    that cloze is already a card. The same sentence is added when the cloze is new.
    """
    return _run(lambda page: add_sentences(page, cards, collection_id, collection_name))


@mcp.tool()
def clozemaster_find_cloze(
    cloze: str,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> str:
    """Find the card whose hidden word is cloze. Returns its id and sentence."""
    return _run(lambda page: find_by_cloze(page, cloze, collection_id, collection_name))


@mcp.tool()
def clozemaster_replace_sentence(
    sentence_id: int,
    sentence: str,
    replacement: str,
    collection_id: int | None = None,
    collection_name: str | None = None,
    cloze: str | None = None,
    translation: str | None = None,
    note: str | None = None,
) -> str:
    """Replace one sentence. Adds the new sentence, then deletes the old card.

    sentence must match the current card. The cloze, translation, and note stay
    unless new ones are passed. Progress on the old card is dropped.
    """
    return _run(
        lambda page: replace_sentence(
            page,
            sentence_id,
            sentence,
            replacement,
            collection_id,
            collection_name,
            cloze,
            translation,
            note,
        )
    )


@mcp.tool()
def clozemaster_create_collection(
    name: str,
    pairing: str | None = None,
    description: str = "",
) -> str:
    """Create a collection. pairing is a language slug such as ell-eng.

    When pairing is omitted, the collection uses the language of the course
    practiced most recently. Cards are played in the order they were added.
    """
    return _run(lambda page: create_collection(page, name, pairing, description))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
