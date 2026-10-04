def progress_bar(percent, width=20):
    p=max(0,min(100,int(percent))); filled=round(width*p/100); return '█'*filled+'░'*(width-filled)
def esc(s): return str(s).replace('_','\\_').replace('*','\\*').replace('`','\\`')
