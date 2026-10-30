from playwright.sync_api import sync_playwright
from pathlib import Path
p=Path(__file__).resolve().parent
with sync_playwright() as w:
 browser=w.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 for name,width,height in [('desktop',1672,941),('mobile',390,844)]:
  page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
  errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
  page.set_content((p/'standalone.html').read_text(encoding='utf-8'),wait_until='load')
  page.screenshot(path=str(p/f'preview-{name}.png'),full_page=(name=='mobile'))
  print(name,'title',page.title(),'js-errors',errors,'horizontalOverflow',page.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
  if name=='desktop':
   for selector in ['.banner','.stats','.upper-panels','.records','.detail','.mid-grid','.sicon']:
    elem=page.locator(selector).first
    print(selector,elem.bounding_box())
   print('rows',page.locator('#recordRows tr[data-row]').count())
   page.locator('button[data-tab="dislike"]').click();print('tab dislike rows',page.locator('#recordRows tr[data-row]').count())
   page.locator('button[data-tab="all"]').click()
   page.locator('tr[data-row="2"]').click();print('selected detail',page.locator('#detailCompany').inner_text())
   page.locator('button[data-fb="interest"]').click();print('edited',page.locator('button[data-fb="interest"]').get_attribute('aria-pressed'))
   page.locator('#editFeedback').click();page.locator('#remark').fill('这是一条更新后的反馈');page.locator('#editFeedback').click();print('remark',page.locator('#remark').input_value())
   page.locator('button[data-days="30"]').click();print('chart polylines',page.locator('#trendChart polyline').count())
   page.screenshot(path=str(p/'preview-interactive.png'))
  page.close()
 browser.close()
