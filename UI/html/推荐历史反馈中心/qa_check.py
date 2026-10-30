import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).parent
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
  page=await b.new_page(viewport={'width':1448,'height':1086},device_scale_factor=1)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.set_content((ROOT/'standalone.html').read_text(encoding='utf-8'),wait_until='load')
  await page.screenshot(path=str(ROOT/'preview-desktop.png'),full_page=False)
  keys=['.hero','.stats','.content-grid','.history','.result','.metric-bar','.feedback-overview','.job-filters','.job-row']
  for k in keys:
   print(k,await page.locator(k).first.bounding_box())
  bad=await page.locator('img').evaluate_all('(nodes)=>nodes.filter(x=>!x.complete||!x.naturalWidth).map(x=>x.outerHTML.slice(0,120))')
  print('image count',await page.locator('img').count(),'broken',len(bad),bad[:2]); assert not bad
  assert await page.locator('.hist-row').count()==8
  assert await page.locator('.job-row').count()==6
  # feedback
  await page.locator('.job-row').first.get_by_role('button',name='不感兴趣').click()
  assert await page.locator('.job-row').first.locator('button.dislike').get_attribute('aria-pressed')=='true'
  # history selection
  await page.locator('.hist-row').nth(1).click()
  assert '2024-10-15' in await page.locator('#resultTitle').inner_text()
  # statuses
  await page.locator('#historyStatus').select_option('expired')
  assert await page.locator('.hist-row').count()==3
  await page.locator('#historyStatus').select_option('all')
  await page.locator('#feedbackFilter').select_option('sent')
  assert await page.locator('.job-row').count()==1
  await page.locator('#feedbackFilter').select_option('all')
  await page.locator('#jobSearch').fill('字节')
  assert await page.locator('.job-row').count()==2
  await page.locator('#jobSearch').fill('')
  await page.locator('#rerun').click()
  assert await page.locator('.modal-cover').count()==1
  await page.locator('[data-close]').click()
  assert await page.locator('.modal-cover').count()==0
  print('desktop JS errors',errors)
  assert not errors
  mobile=await b.new_page(viewport={'width':390,'height':844},device_scale_factor=1,is_mobile=True,has_touch=True)
  errs=[];mobile.on('pageerror',lambda e:errs.append(str(e)))
  await mobile.set_content((ROOT/'standalone.html').read_text(encoding='utf-8'),wait_until='load')
  await mobile.screenshot(path=str(ROOT/'preview-mobile.png'),full_page=True)
  width=await mobile.evaluate('({inner:window.innerWidth,scroll:document.documentElement.scrollWidth,body:document.body.scrollWidth})')
  print('mobile width',width,'js errors',errs)
  assert width['scroll']<=width['inner']+1 and not errs
  await b.close()
if __name__=='__main__': asyncio.run(main())
