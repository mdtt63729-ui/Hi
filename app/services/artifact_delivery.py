"""Reliable GitHub Actions artifact discovery and Telegram delivery."""
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.utils.security import sign_value
from app.config import settings
import base64, json

# Callback payloads must stay tiny. The signed payload is also useful for the
# optional HTTP download endpoint.
def _token(owner, repo, artifact_id, user_id):
    payload = base64.urlsafe_b64encode(json.dumps({
        "o": owner, "r": repo, "a": int(artifact_id), "u": int(user_id)
    }, separators=(",", ":")).encode()).decode().rstrip("=")
    return sign_value(payload, settings.artifact_signing_secret, 1800) if settings.artifact_signing_secret else None


def artifact_keyboard(owner, repo, artifact_id, user_id):
    b = InlineKeyboardBuilder()
    token = _token(owner, repo, artifact_id, user_id)
    # Telegram callback_data is limited to 64 bytes. The signed token is often
    # longer, so use a short in-process key and let the callback resolve it.
    from app.services.artifact_store import put
    key = put(owner, repo, int(artifact_id), int(user_id), token)
    b.button(text="📥 Download Artifact", callback_data=f"artifact:download:{key}")
    b.button(text="🔗 GitHub Artifact", url=f"https://github.com/{owner}/{repo}/actions/artifacts/{artifact_id}")
    b.adjust(1)
    return b.as_markup()


async def deliver_artifacts(message, gh, owner, repo, run_id):
    """Deliver only artifacts belonging to *this* workflow run.

    The old implementation listed every artifact in the repository, which
    could return unrelated/expired artifacts. The run-scoped endpoint avoids
    that and makes download IDs deterministic.
    """
    data = await gh.run_artifacts(owner, repo, run_id)
    items = [x for x in data.get("artifacts", []) if not x.get("expired")]
    if not items:
        await message.answer("📦 No non-expired artifacts were found for this workflow.")
        return []

    sent = []
    for a in items[:10]:
        aid = a.get("id")
        name = a.get("name") or f"artifact-{aid}"
        size = int(a.get("size_in_bytes") or 0)
        kb = artifact_keyboard(owner, repo, aid, message.from_user.id)
        await message.answer(
            f"📦 *{name}*\nSize: {size:,} bytes\n\nChoose an action below.",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        # Small artifacts are also sent directly, so there is no dependency on
        # a browser redirect or a second download service.
        if size and size <= 49 * 1024 * 1024:
            try:
                response = await gh.artifact_response(owner, repo, aid)
                payload = response.content
                if payload.startswith(b"PK"):
                    await message.answer_document(
                        BufferedInputFile(payload, filename=f"{name}.zip")
                    )
                    sent.append(name)
            except Exception:
                # The button remains available and the callback will retry.
                pass
    return sent
