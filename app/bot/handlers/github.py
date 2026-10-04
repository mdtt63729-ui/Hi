from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.bot.states.states import GitofyStates
from app.bot.keyboards.main import main_kb, back_kb
from app.database.repository import save_connection, get_connection, disconnect, save_repo
from app.github.client import GitHubClient

router = Router()


def _message(ev):
    return ev if isinstance(ev, Message) else ev.message


async def _open_github_connection(m: Message, state: FSMContext):
    # Set the FSM state before sending the prompt so the very next message
    # is guaranteed to be handled by the PAT handler.
    await state.set_state(GitofyStates.waiting_pat)
    await m.answer(
        '🔐 Connect GitHub\n\n'
        'Send your GitHub Personal Access Token in your next message.\n'
        'No command is required. The token will be deleted when possible.'
    )


@router.message(Command('connect'))
async def connect_command(m: Message, state: FSMContext):
    await _open_github_connection(m, state)


@router.callback_query(F.data == 'github')
async def connect_callback(c: CallbackQuery, state: FSMContext):
    # Acknowledge the Telegram callback immediately.  Doing this first avoids
    # the button appearing stuck/loading while the bot sends the next message.
    await c.answer()
    if not c.message:
        return
    await _open_github_connection(c.message, state)


@router.message(GitofyStates.waiting_pat)
async def pat(m: Message, state: FSMContext):
    token = (m.text or '').strip()
    if not token:
        await m.answer('❌ Please send a GitHub Personal Access Token.')
        return

    # Remove the secret from the chat as early as Telegram permits.
    try:
        await m.delete()
    except Exception:
        pass

    status = await m.answer('🔄 GitHub token received.\nValidation is running…')
    gh = GitHubClient(token)
    try:
        # These calls are deliberately kept separate so a successful identity
        # check is not mistaken for a complete GitHub connection.
        info = await gh.user()
        await gh.rate_limit()
        await gh.repos(page=1, per_page=1)

        perms = {
            'identity': True,
            'repository_api': True,
            'actions_api': True,
        }
        await save_connection(m.from_user.id, token, info, perms)
        await state.clear()

        # Never use Telegram Markdown/HTML with server/API-generated values.
        # GitHub usernames and upstream exception text can contain characters
        # that Telegram interprets as entities/tags and cause HTTP 400.
        username = str(info.get('login') or 'unknown')
        await status.edit_text(
            '✅ GitHub connection successful.\n\n'
            f'👤 Username: {username}\n'
            '🟢 Connection: Active\n'
            '📦 Repository access: OK\n'
            '⚙️ GitHub Actions access: Ready',
            reply_markup=main_kb(),
        )
    except Exception as exc:
        # Do not echo raw exception strings into Telegram formatting.  The raw
        # text may contain <tags>, backslashes, Markdown markers, or secrets.
        try:
            await state.set_state(GitofyStates.waiting_pat)
            await status.edit_text(
                '❌ GitHub connection failed.\n\n'
                'The token could not be validated.\n'
                'Please send a valid GitHub Personal Access Token again.'
            )
        except Exception:
            await m.answer(
                '❌ GitHub connection failed.\n\n'
                'Please send a valid GitHub Personal Access Token again.'
            )
    finally:
        await gh.close()


@router.message(Command('disconnect'))
async def disc(m: Message):
    await disconnect(m.from_user.id)
    await m.answer('🔐 GitHub disconnected.', reply_markup=main_kb())


@router.message(Command('repos'))
@router.callback_query(F.data == 'repos')
async def repos(ev):
    m = _message(ev)
    c = await get_connection(m.from_user.id)
    if not c:
        await m.answer('🔐 Connect GitHub first.', reply_markup=back_kb())
        return

    from app.utils.security import decrypt
    from app.config import settings
    gh = GitHubClient(decrypt(c.encrypted_pat, settings.encryption_key))
    try:
        rs = await gh.repos()
        for r in rs:
            await save_repo(m.from_user.id, r)
        lines = ['📦 Repositories'] + [
            f'• {r["name"]} — {r.get("visibility", "unknown")} — 🌿 {r.get("default_branch") or "main"}'
            for r in rs[:30]
        ]
        await m.answer('\n'.join(lines), reply_markup=back_kb())
    finally:
        await gh.close()
