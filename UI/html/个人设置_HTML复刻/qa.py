from pathlib import Path
from playwright.sync_api import sync_playwright
import json
ROOT = Path(__file__).parent
s = (ROOT / 'standalone.html').read_text(encoding='utf-8')
report = {'desktop_viewport':[1672,941], 'mobile_viewport':[390,844], 'checks': {}, 'metrics': {}}
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page = browser.new_page(viewport={'width':1672,'height':941})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(s,wait_until='load')
    report['checks']['images_loaded']=page.evaluate('''() => [...document.images].every(i=>i.complete&&i.naturalWidth>0)''')
    report['metrics']['images_count']=page.locator('img').count()
    report['checks']['no_javascript_errors']=(len(errors)==0)
    report['metrics']['javascript_errors']=errors
    for selector in ('.hero','.profile-card','.basic-card','.security-card','.device-card','.notice-card','.privacy-card','.resume-card','.prefs-card'):
        b=page.locator(selector).bounding_box()
        report['metrics'][selector.strip('.')+'_box']={k:round(b[k]) for k in ('x','y','width','height')}
    report['checks']['desktop_no_overflow']=page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    report['checks']['all_4_privacy_rows']=page.locator('.privacy-card .setting-row').count()==4
    report['checks']['all_4_preference_rows']=page.locator('.prefs-card .pref-row').count()==4
    report['checks']['all_3_device_rows']=page.locator('.device-card .device-item').count()==3
    page.locator('#nickname').fill('毕业生小李')
    report['checks']['nickname_updates']=page.locator('#profileDisplayName').inner_text()=='毕业生小李'
    page.locator('[data-setting="email"]').click()
    report['checks']['toggle_works']=page.locator('[data-setting="email"]').get_attribute('aria-checked')=='false'
    page.locator('[data-modal="password"]').click()
    report['checks']['password_dialog']=page.locator('#dialogTitle').inner_text()=='修改密码'
    page.locator('#modalClose').click()
    page.locator('[data-add="cities"]').click()
    report['checks']['add_city_dialog']=page.locator('#dialogTitle').inner_text()=='添加期望城市'
    page.locator('#modalClose').click()
    report['checks']['all_dialogs_close']=not page.locator('#overlay').get_attribute('class').endswith('active')
    mobile=browser.new_page(viewport={'width':390,'height':844})
    mobile.set_content(s,wait_until='load')
    report['checks']['mobile_no_overflow']=mobile.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    report['checks']['mobile_images_loaded']=mobile.evaluate('''() => [...document.images].every(i=>i.complete&&i.naturalWidth>0)''')
    mobile.screenshot(path=str(ROOT/'preview-mobile.png'),full_page=True)
    browser.close()
report['status']='PASS' if all(report['checks'].values()) else 'FAIL'
(ROOT/'qa-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
