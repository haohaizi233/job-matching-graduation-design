from pathlib import Path
import base64,mimetypes,re,json
base=Path(__file__).parent
html=(base/'index.html').read_text()
css=(base/'styles.css').read_text()
js=(base/'app.js').read_text()
resources={}
for path in (base/'assets').glob('*'):
  mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
  resources[path.name]=f'data:{mime};base64,'+base64.b64encode(path.read_bytes()).decode()
# replace css image URL references
for name,url in resources.items():
  css=css.replace(f"assets/{name}",url)
# replace original image src in markup
for name,url in resources.items():
  html=html.replace(f'src="assets/{name}"',f'src="{url}"')
html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+css+'</style>')
html=html.replace('<script src="app.js"></script>',f'<script>window.__embeddedAssets={json.dumps(resources,separators=(",",":"))};</script><script>'+js+'</script>')
(base/'standalone.html').write_text(html)
print('standalone',len(html),'bytes resources',len(resources))
