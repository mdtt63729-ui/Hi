import re
class TelegramFormatter:
 def sanitize(self,text):
  return str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
 def render(self,text): return self.sanitize(text)
 def progress(self,completed,total,width=20):
  total=max(int(total),0); completed=max(0,min(int(completed),total))
  pct=(completed/total*100) if total else 0
  filled=int(pct*width/100)
  return f'[{"█"*filled}{"░"*(width-filled)}] {pct:.0f}% ({completed}/{total} = {pct:.0f}%)'
