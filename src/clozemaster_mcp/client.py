"""Clozemaster session held in a local browser profile."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from playwright.sync_api import Page, sync_playwright

HOME = "https://www.clozemaster.com/"
LOGIN_URL = "https://www.clozemaster.com/login"
TOKEN = re.compile(r"[^\s.,;:!?«»()]+")

PROFILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "clozemaster-mcp" / "profile"


class ClozemasterError(RuntimeError):
    pass


class LoginRequired(ClozemasterError):
    pass


def profile_dir() -> Path:
    PROFILE.mkdir(parents=True, exist_ok=True)
    return PROFILE


@contextmanager
def browser(headless: bool) -> Iterator[Page]:
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir()),
            headless=headless,
            viewport={"width": 1100, "height": 800},
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            yield page
        finally:
            context.close()


def _logged_in(page: Page) -> bool:
    if "/login" in page.url or "/sign_in" in page.url:
        return False
    return bool(
        page.evaluate(
            "() => typeof $ === 'function' && !!document.querySelector('meta[name=\"csrf-token\"]')"
        )
    )


def open_dashboard(page: Page) -> None:
    page.goto(HOME, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    if not _logged_in(page):
        raise LoginRequired(
            "Clozemaster is logged out. Run the login tool and sign in in the window it opens."
        )


def login() -> str:
    """Open a visible window and wait until the dashboard is signed in."""
    with browser(headless=False) as page:
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        if _logged_in(page):
            return "Already signed in. The session stays in the local browser profile."
        try:
            page.wait_for_function(
                "() => !location.pathname.includes('login') && !location.pathname.includes('sign_in') && typeof $ === 'function'",
                timeout=300_000,
            )
        except Exception as exc:
            raise LoginRequired(
                "Sign-in was not finished. Run the login tool again and complete it in the window."
            ) from exc
    return "Signed in. The session stays in the local browser profile."


def ajax(
    page: Page,
    url: str,
    method: str = "get",
    json_body: dict | None = None,
    form: dict | None = None,
) -> Any:
    result = page.evaluate(
        """async (payload) => {
          return await new Promise((resolve) => {
            const opts = { url: payload.url, method: payload.method, dataType: 'json' };
            if (payload.jsonBody !== undefined && payload.jsonBody !== null) {
              opts.contentType = 'application/json';
              opts.data = JSON.stringify(payload.jsonBody);
            } else if (payload.form) {
              opts.data = payload.form;
            }
            if (typeof $ !== 'function') {
              resolve({ ok: false, status: 0, body: 'page has no Clozemaster session' });
              return;
            }
            $.ajax(opts)
              .done((data, _s, xhr) => resolve({ ok: true, status: xhr.status, data }))
              .fail((xhr) => resolve({
                ok: false,
                status: xhr.status,
                body: String(xhr.responseText || '').slice(0, 500)
              }));
          });
        }""",
        {"url": url, "method": method, "jsonBody": json_body, "form": form},
    )
    if not result["ok"]:
        body = result.get("body") or ""
        if result["status"] in (0, 401) or "login" in body.lower():
            raise LoginRequired(
                "Clozemaster session expired. Run the login tool and sign in again."
            )
        raise ClozemasterError(f"{method.upper()} {url} failed ({result['status']}): {body}")
    return result["data"]


def poll(page: Page, data: Any) -> Any:
    for _ in range(20):
        if not isinstance(data, dict):
            return data
        status = data.get("status")
        if status in (None, "complete"):
            break
        job = data.get("url") or data.get("bulkCollectionClozeSentencesUpsertUrl")
        if not job:
            break
        if data.get("errors"):
            raise ClozemasterError(str(data["errors"]))
        page.wait_for_timeout(1000)
        data = ajax(page, job, "get")
    if isinstance(data, dict) and data.get("errors"):
        raise ClozemasterError(str(data["errors"]))
    return data


def user_pairings(page: Page) -> list[dict]:
    """Language pairings this account has used, not the full Clozemaster catalogue."""
    data = ajax(page, "https://www.clozemaster.com/api/v1/lp")
    rows = []
    for pairing in data.get("languagePairings") or []:
        if not (
            pairing.get("playing")
            or pairing.get("daysPlayedCount")
            or pairing.get("score")
            or pairing.get("currentDashboard")
        ):
            continue
        rows.append(
            {
                "id": pairing["id"],
                "slug": pairing.get("slug"),
            }
        )
    return rows


def own_collections(page: Page) -> list[dict]:
    """Collections this account created, most recently practiced first.

    A collection that has never been played sorts after every played one.
    """
    found = []
    for pairing in user_pairings(page):
        data = ajax(
            page,
            f"https://www.clozemaster.com/api/v1/lp/{pairing['id']}/c",
            form={"filter": "mine"},
        )
        for collection in data.get("collections") or []:
            found.append(
                {
                    "id": collection.get("id"),
                    "name": collection.get("name"),
                    "slug": collection.get("slug"),
                    "pairingId": pairing["id"],
                    "pairing": pairing.get("slug"),
                    "sentences": collection.get("numSentences"),
                    "playing": collection.get("numPlaying"),
                    "lastPlayedAt": collection.get("lastPlayedAt"),
                }
            )
    found.sort(
        key=lambda collection: (
            collection.get("lastPlayedAt") is not None,
            collection.get("lastPlayedAt") or "",
        ),
        reverse=True,
    )
    if found:
        found[0]["default"] = True
    return found


def collection_by_name(collections: list[dict], collection_name: str) -> dict:
    """Match a collection name. A full name wins. Otherwise one name that contains the text."""
    wanted = collection_name.strip().casefold()
    if not wanted:
        raise ClozemasterError("Collection name is empty.")
    names = [(collection, (collection.get("name") or "").strip().casefold()) for collection in collections]
    exact = [collection for collection, name in names if name == wanted]
    matches = exact or [collection for collection, name in names if wanted in name]
    if len(matches) == 1:
        return matches[0]
    label = collection_name.strip()
    listed = ", ".join(
        f"{collection['id']} {collection.get('name')!r} ({collection.get('pairing')})"
        for collection in matches
    )
    if not matches:
        raise ClozemasterError(f"No collection name contains {label!r}.")
    raise ClozemasterError(
        f"More than one collection name contains {label!r}. Pass collection_id. Matches: {listed}."
    )


def resolve_collection(
    page: Page,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> dict:
    collections = own_collections(page)
    if not collections:
        raise ClozemasterError("This account has no collections.")
    name = collection_name.strip() if collection_name else ""
    if collection_id is None and not name:
        return collections[0]
    chosen = None
    if collection_id is not None:
        wanted = int(collection_id)
        for collection in collections:
            if collection["id"] == wanted:
                chosen = collection
                break
        if chosen is None:
            raise ClozemasterError(f"Collection {wanted} is not on this account.")
    if name:
        named = collection_by_name(collections, name)
        if chosen is not None and chosen["id"] != named["id"]:
            raise ClozemasterError(
                f"collection_id {chosen['id']} is {chosen.get('name')!r}, not {name!r}."
            )
        return named
    return chosen


def collection_base(collection: dict) -> str:
    return (
        f"https://www.clozemaster.com/api/v1/lp/{collection['pairingId']}/c/{collection['id']}"
    )


def plain(text: str) -> str:
    return text.replace("{{", "").replace("}}", "").strip()


def cloze_of(text: str) -> str:
    match = re.search(r"\{\{(.*?)\}\}", text or "")
    return match.group(1) if match else ""


def _key(text: str) -> str:
    return plain(text).casefold()


def with_cloze(sentence: str, cloze: str) -> str:
    if "{{" in sentence:
        if f"{{{{{cloze}}}}}" not in sentence and "{{" + cloze + "}}" not in sentence:
            raise ClozemasterError("The braced cloze does not match the cloze word.")
        return sentence
    pattern = re.compile(rf"(?<!\w){re.escape(cloze)}(?!\w)")
    braced, count = pattern.subn("{{" + cloze + "}}", sentence, count=1)
    if count != 1:
        raise ClozemasterError(
            "The cloze must appear once as its own word in the sentence."
        )
    return braced


def list_collections(page: Page) -> list[dict]:
    return own_collections(page)


def list_sentences(
    page: Page,
    collection_id: int | None,
    query: str = "",
    collection: dict | None = None,
    collection_name: str | None = None,
) -> list[dict]:
    collection = collection or resolve_collection(page, collection_id, collection_name)
    base = collection_base(collection)
    rows: list[dict] = []
    page_no = 1
    total = None
    while total is None or len(rows) < total:
        data = ajax(
            page,
            f"{base}/ccs",
            form={
                "context": "sentences",
                "page": page_no,
                "per_page": 100,
                "query": query,
                "scope": "all",
            },
        )
        total = data.get("total") or 0
        batch = data.get("collectionClozeSentences") or []
        if not batch:
            break
        for sentence in batch:
            rows.append(
                {
                    "id": sentence.get("id"),
                    "text": sentence.get("text"),
                    "translation": sentence.get("translation"),
                    "notes": sentence.get("notes"),
                    "ignored": sentence.get("ignored"),
                    "cloze": cloze_of(sentence.get("text") or ""),
                }
            )
        page_no += 1
        if page_no > 50:
            break
    return rows


def add_sentence(
    page: Page,
    sentence: str,
    translation: str,
    cloze: str,
    note: str,
    collection_id: int | None,
    collection_name: str | None = None,
) -> dict:
    collection = resolve_collection(page, collection_id, collection_name)
    ready, skipped = plan_additions(
        list_sentences(page, None, collection=collection),
        [{"sentence": sentence, "translation": translation, "cloze": cloze, "note": note}],
    )
    if skipped:
        raise ClozemasterError(skipped[0]["reason"])
    text = ready[0]["text"]
    data = ajax(
        page,
        f"{collection_base(collection)}/ccs",
        "post",
        json_body={
            "collection_cloze_sentence": {
                "text": text,
                "translation": translation,
                "notes": note,
                "pronunciation": None,
                "alternative_answers": [],
                "favorited": False,
                "hint": None,
                "ignored": False,
            }
        },
    )
    sentence = data.get("collectionClozeSentence") or data
    return {
        "id": sentence.get("id"),
        "text": sentence.get("text"),
        "translation": sentence.get("translation"),
        "notes": sentence.get("notes"),
    }


def update_sentence(
    page: Page,
    sentence_id: int,
    translation: str,
    note: str,
    collection_id: int | None,
    collection_name: str | None = None,
) -> dict:
    collection = resolve_collection(page, collection_id, collection_name)
    current = _sentence(page, sentence_id, collection)
    data = ajax(
        page,
        f"{collection_base(collection)}/bulk_collection_cloze_sentences_upserts",
        "post",
        json_body={
            "updates": [
                {
                    "id": sentence_id,
                    "text": current["text"],
                    "translation": translation,
                    "notes": note,
                    "pronunciation": None,
                }
            ]
        },
    )
    data = poll(page, data)
    updated = _sentence(page, sentence_id, collection)
    return {
        "id": sentence_id,
        "text": updated["text"],
        "translation": updated["translation"],
        "notes": updated["notes"],
        "status": data.get("status") if isinstance(data, dict) else None,
    }


def delete_sentence(
    page: Page,
    sentence_id: int,
    sentence: str,
    collection_id: int | None,
    collection_name: str | None = None,
) -> dict:
    collection = resolve_collection(page, collection_id, collection_name)
    current = _sentence(page, sentence_id, collection)
    if plain(current["text"]) != plain(sentence):
        raise ClozemasterError(
            "Refused to delete. The sentence text does not match that sentence id."
        )
    ajax(
        page,
        f"{collection_base(collection)}/ccs/delete",
        "post",
        json_body={"collection_cloze_sentence_id": sentence_id},
    )
    return {"deleted": sentence_id, "text": current["text"]}


def ignore_sentence(
    page: Page,
    sentence_id: int,
    collection_id: int | None,
    collection_name: str | None = None,
) -> dict:
    collection = resolve_collection(page, collection_id, collection_name)
    current = _sentence(page, sentence_id, collection)
    ajax(
        page,
        f"{collection_base(collection)}/ccs/ignore_all",
        "put",
        form={"collection_cloze_sentence_id": sentence_id},
    )
    return {"ignored": sentence_id, "text": current["text"]}


def next_cards(
    page: Page, collection_id: int | None, collection_name: str | None = None
) -> dict:
    collection = resolve_collection(page, collection_id, collection_name)
    data = ajax(page, f"{collection_base(collection)}/play")
    cards = []
    for sentence in (data.get("collectionClozeSentences") or [])[:10]:
        cards.append(
            {
                "id": sentence.get("id"),
                "text": sentence.get("text"),
                "translation": sentence.get("translation"),
            }
        )
    return {
        "numNew": data.get("numNew"),
        "numReview": data.get("numReview"),
        "cards": cards,
    }


def _sentence(page: Page, sentence_id: int, collection: dict) -> dict:
    for sentence in list_sentences(page, None, collection=collection):
        if sentence["id"] == sentence_id:
            return sentence
    raise ClozemasterError(f"Sentence {sentence_id} is not in that collection.")


def plan_additions(
    existing: list[dict],
    cards: list[dict],
    ignore_ids: set[int] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split cards into ones to add and ones already covered.

    The same sentence may be added again when the cloze is a new word.
    A sentence that already hides that same word is skipped.
    A cloze that is already hidden on any other card is skipped.
    """
    ignored = ignore_ids or set()
    kept = [row for row in existing if row.get("id") not in ignored]
    sentences: dict[str, set[str]] = {}
    clozes: set[str] = set()
    for row in kept:
        word = _key(cloze_of(row.get("text") or ""))
        sentences.setdefault(_key(row.get("text") or ""), set()).add(word)
        if word:
            clozes.add(word)
    ready: list[dict] = []
    skipped: list[dict] = []
    for card in cards:
        sentence = str(card.get("sentence") or "").strip()
        translation = str(card.get("translation") or "").strip()
        cloze = str(card.get("cloze") or "").strip()
        note = str(card.get("note") or "")
        if not sentence or not cloze:
            skipped.append(
                {
                    "sentence": sentence,
                    "cloze": cloze,
                    "reason": "A card needs a sentence and a cloze.",
                }
            )
            continue
        try:
            text = with_cloze(sentence, cloze)
        except ClozemasterError as exc:
            skipped.append({"sentence": sentence, "cloze": cloze, "reason": str(exc)})
            continue
        sentence_key = _key(sentence)
        cloze_key = _key(cloze)
        if cloze_key in sentences.get(sentence_key, set()):
            skipped.append(
                {
                    "sentence": sentence,
                    "cloze": cloze,
                    "reason": "That sentence already hides this cloze.",
                }
            )
            continue
        if cloze_key in clozes:
            skipped.append(
                {
                    "sentence": sentence,
                    "cloze": cloze,
                    "reason": "That cloze is already a card.",
                }
            )
            continue
        ready.append(
            {
                "text": text,
                "sentence": sentence,
                "translation": translation,
                "cloze": cloze,
                "note": note,
            }
        )
        sentences.setdefault(sentence_key, set()).add(cloze_key)
        clozes.add(cloze_key)
    return ready, skipped


def _create_cards(page: Page, collection: dict, ready: list[dict]) -> list[dict]:
    if not ready:
        return []
    data = ajax(
        page,
        f"{collection_base(collection)}/bulk_collection_cloze_sentences_upserts",
        "post",
        json_body={
            "creates_only": True,
            "updates": [
                {
                    "id": None,
                    "text": card["text"],
                    "translation": card["translation"],
                    "notes": card["note"],
                    "pronunciation": None,
                }
                for card in ready
            ],
        },
    )
    poll(page, data)
    created = []
    found = {
        _key(row["text"]): row
        for row in list_sentences(page, None, collection=collection)
    }
    for card in ready:
        row = found.get(_key(card["text"]))
        created.append(
            {
                "id": None if row is None else row.get("id"),
                "text": card["text"],
                "translation": card["translation"],
                "notes": card["note"],
                "cloze": card["cloze"],
            }
        )
    missing = [card["sentence"] for card in created if card["id"] is None]
    if missing:
        raise ClozemasterError(f"Clozemaster did not store: {missing[0]}")
    return created


def add_sentences(
    page: Page,
    cards: list[dict],
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> dict:
    collection = resolve_collection(page, collection_id, collection_name)
    ready, skipped = plan_additions(list_sentences(page, None, collection=collection), cards)
    added = _create_cards(page, collection, ready)
    return {
        "collection": collection.get("name"),
        "added": added,
        "skipped": skipped,
    }


def find_by_cloze(
    page: Page,
    cloze: str,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> list[dict]:
    collection = resolve_collection(page, collection_id, collection_name)
    wanted = _key(cloze)
    if not wanted:
        raise ClozemasterError("Cloze is empty.")
    return [
        row
        for row in list_sentences(page, None, collection=collection)
        if _key(cloze_of(row.get("text") or "")) == wanted
    ]


def replace_sentence(
    page: Page,
    sentence_id: int,
    sentence: str,
    replacement: str,
    collection_id: int | None = None,
    collection_name: str | None = None,
    cloze: str | None = None,
    translation: str | None = None,
    note: str | None = None,
) -> dict:
    """Add the replacement sentence, then delete the old card.

    The old card is deleted only after the new card exists. Progress on the
    old card is dropped. The new card starts unplayed.
    """
    collection = resolve_collection(page, collection_id, collection_name)
    current = _sentence(page, sentence_id, collection)
    if plain(current["text"]) != plain(sentence):
        raise ClozemasterError(
            "Refused to replace. The sentence text does not match that sentence id."
        )
    word = (cloze or cloze_of(current["text"])).strip()
    if not word:
        raise ClozemasterError("The card has no cloze to carry onto the new sentence.")
    if _key(replacement) == _key(sentence):
        raise ClozemasterError("The replacement is the same sentence.")
    ready, skipped = plan_additions(
        list_sentences(page, None, collection=collection),
        [
            {
                "sentence": replacement,
                "translation": current["translation"] if translation is None else translation,
                "cloze": word,
                "note": current["notes"] or "" if note is None else note,
            }
        ],
        ignore_ids={sentence_id},
    )
    if skipped:
        raise ClozemasterError(skipped[0]["reason"])
    added = _create_cards(page, collection, ready)
    ajax(
        page,
        f"{collection_base(collection)}/ccs/delete",
        "post",
        json_body={"collection_cloze_sentence_id": sentence_id},
    )
    return {"removed": sentence_id, "added": added[0]}


def resolve_pairing(page: Page, pairing: str | None) -> dict:
    data = ajax(page, "https://www.clozemaster.com/api/v1/lp")
    pairings = data.get("languagePairings") or []
    if pairing and pairing.strip():
        wanted = pairing.strip().casefold()
        exact = [item for item in pairings if (item.get("slug") or "").casefold() == wanted]
        matches = exact or [
            item for item in pairings if wanted in (item.get("slug") or "").casefold()
        ]
        if len(matches) == 1:
            return {"id": matches[0]["id"], "slug": matches[0].get("slug")}
        if not matches:
            raise ClozemasterError(
                f"No language pairing matches {pairing.strip()!r}. Use a slug such as ell-eng."
            )
        listed = ", ".join(item.get("slug") or "" for item in matches[:8])
        raise ClozemasterError(
            f"More than one pairing matches {pairing.strip()!r}: {listed}."
        )
    collections = own_collections(page)
    if not collections:
        raise ClozemasterError(
            "Pass pairing, such as ell-eng. This account has no collection to take a language from."
        )
    return {"id": collections[0]["pairingId"], "slug": collections[0].get("pairing")}


def create_collection(
    page: Page,
    name: str,
    pairing: str | None = None,
    description: str = "",
) -> dict:
    label = name.strip()
    if not label:
        raise ClozemasterError("Collection name is empty.")
    language = resolve_pairing(page, pairing)
    existing = [
        collection
        for collection in own_collections(page)
        if collection.get("pairingId") == language["id"]
        and (collection.get("name") or "").strip().casefold() == label.casefold()
    ]
    if existing:
        raise ClozemasterError(
            f"A collection named {label!r} already exists on {language['slug']} (id {existing[0]['id']})."
        )
    data = ajax(
        page,
        f"https://www.clozemaster.com/api/v1/lp/{language['id']}/c",
        "post",
        json_body={
            "collection": {
                "name": label,
                "description": description,
                "play_order": "id",
                "public": False,
                "use_clozes_as_multiple_choice_options": False,
            }
        },
    )
    collection = data.get("collection") or data
    return {
        "id": collection.get("id"),
        "name": collection.get("name") or label,
        "slug": collection.get("slug"),
        "pairing": language["slug"],
        "pairingId": language["id"],
    }
