"""Headless basic front-end interactions, no soundcard needed."""
from playwright.sync_api import sync_playwright
from pathlib import Path

with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=b.new_page(viewport={'width':1570,'height':900},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8765/',wait_until='domcontentloaded')
    page.wait_for_selector('#projectSelect option',timeout=15000)
    print('title',page.title(),'projects',page.locator('#projectSelect option').count())
    page.locator('#globalEnvelopeEnabled').check()
    page.locator('#globalAddPoint').click()
    print('global keyframes',page.locator('.global-key-row').count())
    page.locator('#settingsToggle').click()
    page.wait_for_selector('#stageDialog[open]')
    page.locator('input[data-speaker="0"][data-key="x_m"]').fill('-2.25')
    page.locator('input[data-speaker="0"][data-key="x_m"]').dispatch_event('change')
    page.locator('#previewSettings').click()
    page.wait_for_timeout(500)
    print('calibration',page.locator('#calibrationHints').inner_text()[:160])
    page.locator('#saveSettings').click()
    page.wait_for_timeout(600)
    print('stage closed',not page.locator('#stageDialog').evaluate('(e)=>e.open'))
    page.screenshot(path='/mnt/data/SpatialStage-v0.2-preview.png',full_page=True)
    print('errors:',errors)
    b.close()
