class ProgressService:
    def calc(self, completed, total):
        return round(completed / total * 100, 2) if total else None

    def bar(self, percent, width=20):
        percent = max(0.0, min(100.0, float(percent)))
        filled = int(percent * width / 100)
        return '█' * filled + '░' * (width - filled)

    def render(self, completed, total):
        p = self.calc(completed, total)
        if p is None:
            return f'Completed: {completed}\nProgress: Calculating…'
        return f'Completed: {completed}/{total}\n[{self.bar(p)}] {p:.0f}%'

    def render_percent(self, percent, label='Processing'):
        p = max(0.0, min(100.0, float(percent)))
        return f'{label}\n[{self.bar(p)}] {p:.0f}%'
