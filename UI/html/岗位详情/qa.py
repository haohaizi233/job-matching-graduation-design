from playwright.sync_api import sync_playwright
from pathlib import Path
import json, threading, http.server, socketserver
root=Path(__file__).parent
class Silent(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server=socketserver.TCPServer(("127.0.0.1",0),lambda *args,**kwargs:Silent(*args,directory=str(root),**kwargs))
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f"http://127.0.0.1:{server.server_address[1]}/index.html"
results={}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1448,'height':1086},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content((root/'standalone.html').read_text(encoding='utf-8'),wait_until='load')
    page.screenshot(path=str(root/'preview-desktop.png'),full_page=False)
    elements=['.topbar','.sidebar','.workspace','.breadcrumb','.detail-grid','.job-hero','.detail-tabs','.responsibility','.requirements','.skills','.company-info','.match-preview','.skill-match','.condition-match','.advice']
    for key in elements:
      b=page.locator(key).bounding_box(); results[key]={k:round(v,1) for k,v in b.items()} if b else None
    print('Desktop boxes:',json.dumps(results,ensure_ascii=False,indent=2))
    print('page errors',errors)
    page.locator('[data-tab="company"]').click()
    print('company tab visible?',page.locator('#tabCompany').is_visible())
    page.locator('[data-tab="duties"]').click()
    page.locator('#saveJob').click()
    print('save label',page.locator('#saveJob').inner_text())
    page.locator('#heroMatch').click()
    print('modal visible?',page.locator('#modalBackdrop').is_visible())
    page.locator('#closeModal').click()
    page.set_viewport_size({'width':390,'height':844})
    page.set_content((root/'standalone.html').read_text(encoding='utf-8'),wait_until='load')
    page.screenshot(path=str(root/'preview-mobile.png'),full_page=True)
    print('mobile scrollWidth innerWidth',page.evaluate('({w:document.documentElement.scrollWidth,iw:innerWidth})'))
    browser.close()
