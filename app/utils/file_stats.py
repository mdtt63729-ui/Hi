from pathlib import Path
from zipfile import ZipFile

def zip_stats(path):
    p = Path(path)
    with ZipFile(p) as z:
        entries = [i for i in z.infolist() if not i.is_dir()]
        return {
            "size_bytes": p.stat().st_size,
            "file_count": len(entries),
            "expanded_bytes": sum(i.file_size for i in entries),
        }

def fmt_bytes(n):
    n=float(n or 0)
    for unit in ("B","KB","MB","GB","TB"):
        if n < 1024 or unit == "TB": return f"{n:.2f} {unit}"
        n /= 1024
