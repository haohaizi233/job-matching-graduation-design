from pathlib import Path
import re, base64, json
p=Path(__file__).parent
html=(p/'index.html').read_text(encoding='utf-8')
css=(p/'styles.css').read_text(encoding='utf-8')
js=(p/'app.js').read_text(encoding='utf-8')
assets={f.name: 'data:image/png;base64,'+base64.b64encode(f.read_bytes()).decode() for f in (p/'assets').glob('*.png')}
css=css.replace("url('assets/banner-campus.png')", "url('"+assets['banner-campus.png']+"')")
html=re.sub(r'src="assets/([^"]+)"',lambda m:'src="'+assets[m.group(1)]+'"',html)
html=html.replace('<link rel="stylesheet" href="styles.css">','<style>\n'+css+'\n</style>')
js="const ASSET_DATA="+json.dumps(assets,ensure_ascii=False)+";\n"+js.replace('const src = name => `assets/${name}`;','const src = name => ASSET_DATA[name] || "";')
html=html.replace('<script src="app.js"></script>','<script>\n'+js+'\n</script>')
(p/'standalone.html').write_text(html,encoding='utf-8')
print('written',p/'standalone.html',(p/'standalone.html').stat().st_size,'bytes')
