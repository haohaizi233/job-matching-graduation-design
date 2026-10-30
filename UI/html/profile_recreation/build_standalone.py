from pathlib import Path
from base64 import b64encode
from mimetypes import guess_type
import re
root=Path(__file__).resolve().parent
h=(root/'index.html').read_text('utf-8')
css=(root/'styles.css').read_text('utf-8'); js=(root/'app.js').read_text('utf-8')
h=h.replace('<link rel="stylesheet" href="styles.css">','<style>\n'+css+'\n</style>')
h=h.replace('<script src="app.js"></script>','<script>\n'+js+'\n</script>')
def repl(m):
    path=m.group(1)
    b=(root/path).read_bytes();mime=guess_type(path)[0] or 'image/png'
    return 'src="data:'+mime+';base64,'+b64encode(b).decode()+'"'
h=re.sub(r'src="(assets/[^\"]+)"',repl,h)
(root/'standalone.html').write_text(h,'utf-8')
print('standalone',len(h),'bytes')
