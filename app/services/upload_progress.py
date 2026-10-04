import asyncio, time

class ProgressReporter:
    """Coalesces progress edits so transfers stay fast while Telegram stays readable."""
    def __init__(self, message, label, total):
        self.message = message
        self.label = label
        self.total = max(int(total or 0), 1)
        self.last = -1
        self.last_edit = 0.0
        self.lock = asyncio.Lock()

    def percent(self, done):
        return max(0, min(100, int((done / self.total) * 100)))

    @staticmethod
    def bar(p, width=24):
        filled = int(p * width / 100)
        return "█" * filled + "░" * (width - filled)

    async def update(self, done, extra=""):
        p = self.percent(done)
        now = time.monotonic()
        # Never hold up transfer for Telegram edits.  Update at least every 0.25s or 1%.
        if p == self.last or (now - self.last_edit < 0.25 and p < 100):
            return
        self.last, self.last_edit = p, now
        text = f"⏳ {self.label}\n\n[{self.bar(p)}] {p}%\n{done:,} / {self.total:,} bytes"
        if extra: text += f"\n\n{extra}"
        try:
            await self.message.edit_text(text)
        except Exception:
            pass

    async def finish(self, text):
        try: await self.message.edit_text(text)
        except Exception: pass
