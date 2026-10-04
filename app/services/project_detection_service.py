from pathlib import Path
def detect_project(root):
    p=Path(root); names={x.name for x in p.iterdir()} if p.exists() else set()
    android=any((p/x).exists() for x in ['settings.gradle','settings.gradle.kts','build.gradle','build.gradle.kts','gradlew','app'])
    return {'android':android,'gradle':android or 'gradlew' in names,'kotlin':any(x.suffix=='.kt' for x in p.rglob('*') if x.is_file()),'java':any(x.suffix=='.java' for x in p.rglob('*') if x.is_file()),'node':(p/'package.json').exists(),'python':(p/'pyproject.toml').exists() or (p/'requirements.txt').exists(),'web':(p/'package.json').exists() and (p/'src').exists()}
