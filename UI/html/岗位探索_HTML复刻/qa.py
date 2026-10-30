from playwright.sync_api import sync_playwright
from pathlib import Path
import json
root=Path('/mnt/data/jobs_recreation')
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-gpu'])
    page=browser.new_page(viewport={'width':1448,'height':1086},device_scale_factor=1)
    page.on('pageerror',lambda err:errors.append(str(err)))
    page.set_content((root/'standalone.html').read_text(),wait_until='load',timeout=30000)
    page.wait_for_timeout(350)
    page.screenshot(path=str(root/'preview-desktop.png'),full_page=False)
    print('desktop',page.title(),page.locator('.job-card').count(),page.locator('#resultCount').inner_text())
    for name,selector in [('banner','.explore-banner'),('filters','.search-panel'),('metrics','.results-meta'),('sort','.sort-bar'),('row1','.job-card')]:
        el=page.locator(selector).first
        print(name,el.bounding_box())
    # control tests
    page.locator('button[data-view="grid"]').click(); assert page.locator('#jobResults').evaluate("e=>e.classList.contains('grid-view')")
    page.locator('button[data-view="list"]').click()
    page.locator('#keyword').fill('阿里巴巴')
    page.locator('.search-cta').first.click()
    assert page.locator('.job-card').count()==2, 'filter search should return two Alibaba sample jobs'
    assert '算法工程师' in page.locator('.job-card').first.inner_text()
    page.screenshot(path=str(root/'preview-filtered.png'),full_page=False)
    page.locator('#resetFilters').click()
    assert page.locator('.job-card').count()==5
    page.locator('.job-card').first.locator('button[data-detail]').click()
    assert page.locator('#jobModal').is_visible()
    page.locator('#modalMatch').click()
    assert '移出匹配' in page.locator('#modalMatch').inner_text()
    page.locator('#closeModal').click()
    page.locator('#showMoreJobs').click()
    assert page.locator('.job-card').count()==8
    print('desktop interaction pass', 'errors',errors)
    assert not errors, errors
    mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
    mobile.on('pageerror',lambda err:errors.append(str(err)))
    mobile.set_content((root/'standalone.html').read_text(),wait_until='load',timeout=30000)
    mobile.screenshot(path=str(root/'preview-mobile.png'),full_page=True)
    overflow=mobile.evaluate('document.documentElement.scrollWidth - window.innerWidth')
    print('mobile overflow',overflow,'cards',mobile.locator('.job-card').count(),'errors',errors)
    assert overflow<=1, 'horizontal overflow'
    assert not errors,errors
    browser.close()
