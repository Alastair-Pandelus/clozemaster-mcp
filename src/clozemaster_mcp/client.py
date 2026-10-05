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


def resolve_collection(page: Page, collection_id: int | None) -> dict:
    collections = own_collections(page)
    if not collections:
        raise ClozemasterError("This account has no collections.")
    if collection_id is None:
        return collections[0]
    wanted = int(collection_id)
    for collection in collections:
        if collection["id"] == wanted:
            return collection
    raise ClozemasterError(f"Collection {wanted} is not on this account.")


def collection_base(collection: dict) -> str:
    return (
        f"https://www.clozemaster.com/api/v1/lp/{collection['pairingId']}/c/{collection['id']}"
    )


def plain(text: str) -> str:
    return text.replace("{{", "").replace("}}", "").strip()


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
) -> list[dict]:
    collection = collection or resolve_collection(page, collection_id)
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
) -> dict:
    collection = resolve_collection(page, collection_id)
    text = with_cloze(sentence, cloze)
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
) -> dict:
    collection = resolve_collection(page, collection_id)
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
) -> dict:
    collection = resolve_collection(page, collection_id)
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


def ignore_sentence(page: Page, sentence_id: int, collection_id: int | None) -> dict:
    collection = resolve_collection(page, collection_id)
    current = _sentence(page, sentence_id, collection)
    ajax(
        page,
        f"{collection_base(collection)}/ccs/ignore_all",
        "put",
        form={"collection_cloze_sentence_id": sentence_id},
    )
    return {"ignored": sentence_id, "text": current["text"]}


def next_cards(page: Page, collection_id: int | None) -> dict:
    collection = resolve_collection(page, collection_id)
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
