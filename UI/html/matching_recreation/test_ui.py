from pathlib import Path
from playwright.sync_api import sync_playwright
p=Path(__file__).parent
html=(p/'standalone.html').read_text(encoding='utf-8')
with sync_playwright() as play:
 browser=play.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-gpu'])
 desktop=browser.new_page(viewport={'width':1448,'height':1086},device_scale_factor=1)
 errors=[]
 desktop.on('pageerror',lambda err:errors.append(str(err)))
 desktop.set_content(html,wait_until='load')
 desktop.screenshot(path=str(p/'preview-desktop.png'))
 boxes={s:desktop.locator(s).first.bounding_box() for s in ['.hero','.settings-panel','.results-panel','.result-card','.overview','.distribution','.notice']}
 print('desktop boxes',boxes)
 print('initial cards',desktop.locator('.result-card').count(),'images broken',desktop.locator('img').evaluate_all('(imgs)=>imgs.filter(i=>!i.complete||i.naturalWidth===0).map(i=>i.alt)'))
 assert desktop.locator('.result-card').count()==20
 assert not errors,errors
 assert boxes['.hero']['x']==212 and boxes['.hero']['y']==75
 assert boxes['.result-card']['y']==428
 assert abs(boxes['.notice']['y']-954)<3
 # details modal
 desktop.locator('[data-detail]').first.click()
 assert desktop.locator('#modal').is_visible()
 assert desktop.locator('#modalTitle').inner_text()=='后端开发工程师'
 desktop.locator('#modalOkay').click()
 assert not desktop.locator('#modal').is_visible()
 # saving a job
 desktop.locator('[data-save]').first.click()
 assert desktop.locator('[data-save]').first.get_attribute('class').find('is-saved')>=0
 # selecting mode
 desktop.locator('[data-strategy="accuracy"]').click()
 assert desktop.locator('.strategy.active').get_attribute('data-strategy')=='accuracy'
 # city filtering
 desktop.locator('#city').select_option(label='北京')
 assert 0<desktop.locator('.result-card').count()<20
 desktop.locator('#category').select_option(label='算法/机器学习')
 count_alg=desktop.locator('.result-card').count()
 assert 0<count_alg<20
 # reset
 desktop.locator('#resetSettings').click()
 assert desktop.locator('.result-card').count()==20
 # match generation
 desktop.locator('#topk').select_option('5')
 desktop.locator('#startMatching').click()
 desktop.wait_for_timeout(750)
 assert desktop.locator('.result-card').count()==5
 assert '5' in desktop.locator('#matchedCount').inner_text()
 desktop.screenshot(path=str(p/'preview-filtered.png'))
 assert not errors,errors
 print('desktop checks passed, JS errors',errors)
 mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1,is_mobile=True,has_touch=True)
 mobile_errors=[];mobile.on('pageerror',lambda e:mobile_errors.append(str(e)))
 mobile.set_content(html,wait_until='load')
 mobile.screenshot(path=str(p/'preview-mobile.png'))
 width=mobile.evaluate('document.documentElement.scrollWidth')
 print('mobile scrollwidth:',width,'viewport:',mobile.evaluate('window.innerWidth'),'error:',mobile_errors)
 assert width<=390, f'mobile overflow width {width}'
 assert not mobile_errors
 browser.close()
print('ALL CHECKS PASS')
