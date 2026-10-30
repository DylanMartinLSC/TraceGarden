import importlib.metadata as md
import json
import shutil
from pathlib import Path

target=Path('third-party-licenses');target.mkdir(exist_ok=True)
rows=[]
for dist in md.distributions():
    name=dist.metadata['Name']
    if name=='tracegarden':continue
    folder=target/name;folder.mkdir(exist_ok=True)
    for file in dist.files or []:
        if any(token in str(file).lower() for token in ['license','copying','notice']):
            source=dist.locate_file(file)
            if source.is_file():
                # Preserve paths: multiple bundled libraries may have same license filename.
                dest=folder/str(file).replace('..','_')
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,dest)
    (folder/'METADATA.txt').write_text(dist.read_text('METADATA') or '',encoding='utf-8')
    rows.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),'homepage':dist.metadata.get('Home-page')})
Path('dependency-licenses.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')

