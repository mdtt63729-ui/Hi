from aiogram import Router, F
from aiogram.types import CallbackQuery
from app.bot.keyboards.main import back_kb
from app.database.connection import get_connection
from app.config import settings
from app.utils.security import decrypt
from app.github.client import GitHubClient
from app.github.pat_capabilities import render_report

router = Router()

@router.callback_query(F.data == 'pat:capabilities')
async def pat_capabilities(c: CallbackQuery):
    conn = await get_connection(c.from_user.id)
    if not conn:
        await c.message.edit_text('🔐 GitHub is not connected.', reply_markup=back_kb())
        return await c.answer()
    gh = GitHubClient(decrypt(conn.encrypted_pat, settings.encryption_key))
    try:
        # Classic PATs expose X-OAuth-Scopes. Fine-grained PATs generally do not;
        # for those we show the feature catalog and let GitHub endpoint checks decide.
        r = await gh.user()
        scopes = set()
        try:
            response = await gh.client.get(gh.base + '/user')
            header = response.headers.get('X-OAuth-Scopes','')
            scopes = {x.strip() for x in header.split(',') if x.strip()}
        except Exception:
            pass
        text = render_report(scopes, fine_grained=not bool(scopes))
        await c.message.edit_text(text, reply_markup=back_kb(), parse_mode='HTML')
    finally:
        await gh.close()
    await c.answer()
