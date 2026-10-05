"""Clozemaster session held in a local browser profile."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from playwright.sync_api import Page, sync_playwright

PAIRING_ID = 4
B1_COLLECTION_ID = 119463
HOME = "https://www.clozemaster.com/l/ell-eng"
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


def collection_base(collection_id: int | None) -> str:
    cid = B1_COLLECTION_ID if collection_id is None else int(collection_id)
    return f"https://www.clozemaster.com/api/v1/lp/{PAIRING_ID}/c/{cid}"


def plain(text: str) -> str:
    return text.replace("{{", "").replace("}}", "").strip()


def with_cloze(greek: str, cloze: str) -> str:
    if "{{" in greek:
        if f"{{{{{cloze}}}}}" not in greek and "{{" + cloze + "}}" not in greek:
            raise ClozemasterError("The braced cloze does not match the cloze word.")
        return greek
    pattern = re.compile(rf"(?<!\w){re.escape(cloze)}(?!\w)")
    braced, count = pattern.subn("{{" + cloze + "}}", greek, count=1)
    if count != 1:
        raise ClozemasterError(
            "The cloze must appear once as its own word in the Greek sentence."
        )
    return braced


def list_collections(page: Page) -> list[dict]:
    data = ajax(
        page,
        f"https://www.clozemaster.com/api/v1/lp/{PAIRING_ID}/c",
        form={"filter": "mine"},
    )
    rows = []
    for collection in data.get("collections") or []:
        rows.append(
            {
                "id": collection.get("id"),
                "name": collection.get("name"),
                "slug": collection.get("slug"),
                "sentences": collection.get("numSentences"),
                "playing": collection.get("numPlaying"),
            }
        )
    return rows


def list_sentences(page: Page, collection_id: int | None, query: str = "") -> list[dict]:
    base = collection_base(collection_id)
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
    greek: str,
    english: str,
    cloze: str,
    note: str,
    collection_id: int | None,
) -> dict:
    text = with_cloze(greek, cloze)
    data = ajax(
        page,
        f"{collection_base(collection_id)}/ccs",
        "post",
        json_body={
            "collection_cloze_sentence": {
                "text": text,
                "translation": english,
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
    english: str,
    note: str,
    collection_id: int | None,
) -> dict:
    current = _sentence(page, sentence_id, collection_id)
    data = ajax(
        page,
        f"{collection_base(collection_id)}/bulk_collection_cloze_sentences_upserts",
        "post",
        json_body={
            "updates": [
                {
                    "id": sentence_id,
                    "text": current["text"],
                    "translation": english,
                    "notes": note,
                    "pronunciation": None,
                }
            ]
        },
    )
    data = poll(page, data)
    updated = _sentence(page, sentence_id, collection_id)
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
    greek: str,
    collection_id: int | None,
) -> dict:
    current = _sentence(page, sentence_id, collection_id)
    if plain(current["text"]) != plain(greek):
        raise ClozemasterError(
            "Refused to delete. The Greek text does not match that sentence id."
        )
    ajax(
        page,
        f"{collection_base(collection_id)}/ccs/delete",
        "post",
        json_body={"collection_cloze_sentence_id": sentence_id},
    )
    return {"deleted": sentence_id, "text": current["text"]}


def ignore_sentence(page: Page, sentence_id: int, collection_id: int | None) -> dict:
    current = _sentence(page, sentence_id, collection_id)
    ajax(
        page,
        f"{collection_base(collection_id)}/ccs/ignore_all",
        "put",
        form={"collection_cloze_sentence_id": sentence_id},
    )
    return {"ignored": sentence_id, "text": current["text"]}


def next_cards(page: Page, collection_id: int | None) -> dict:
    data = ajax(page, f"{collection_base(collection_id)}/play")
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


def _sentence(page: Page, sentence_id: int, collection_id: int | None) -> dict:
    for sentence in list_sentences(page, collection_id):
        if sentence["id"] == sentence_id:
            return sentence
    raise ClozemasterError(f"Sentence {sentence_id} is not in that collection.")
