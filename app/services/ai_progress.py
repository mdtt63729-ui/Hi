import asyncio, time

class AIFixProgress:
    """One Telegram message that reflects completed work; never reaches 100 early."""
    def __init__(self, message):
        self.message = message
        self.percent = 0
        self.model = None
        self.head_model = 'gemini-3.7-flash'
        self.lock = asyncio.Lock()
        self.last_edit = 0.0
        self.selected_model = 'auto'
        self.selected_model = 'auto'

    async def update(self, percent, message, *, model=None, force=False):
        async with self.lock:
            p = max(self.percent, min(99, int(percent)))
            if not force and p == self.percent and time.monotonic() - self.last_edit < 0.4:
                return
            self.percent = p
            if model:
                self.model = model
            fixer = self.model or ('Auto — Head AI selecting…' if self.selected_model=='auto' else self.selected_model)
            provider = getattr(self, 'fixer_provider', None)
            fix_line = f'🔧 Fixing with: {fixer}' + (f' ({provider})' if provider else '')
            lines = [f'🤖 Head AI: {self._head_name()}', fix_line, '', f'{self.bar(p)} {p}%', message]
            try:
                await self.message.edit_text('\n'.join(lines))
                self.last_edit = time.monotonic()
            except Exception:
                pass

    async def finish(self, success, message, *, files=0, model=None):
        self.percent = 100
        if model: self.model = model
        head = self._head_name()
        fixer = self.model or ('Auto — Head AI selected specialist' if self.selected_model=='auto' else self.selected_model)
        status = '✅ AI fix completed' if success else '❌ AI fix stopped'
        text = f'🤖 Head AI: {head}\n🔧 Fixing with: {fixer}\n\n{self.bar(100)} 100%\n{status}\n\n{message}'
        if files is not None:
            text += f'\n📄 Files pushed: {files}'
        try: await self.message.edit_text(text)
        except Exception: pass

    def _head_name(self):
        # The UI is populated by the orchestrator before the first real update when available.
        return getattr(self, 'head_model', 'Gemini')

    @staticmethod
    def bar(percent, width=24):
        p = max(0, min(100, int(percent)))
        filled = int(width * p / 100)
        return '█' * filled + '░' * (width - filled)
