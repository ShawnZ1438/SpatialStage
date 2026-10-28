"""Focused sidebar layout checks, callable from the existing browser smoke runner."""

def check_sidebar(page):
    from playwright.sync_api import expect
    page.locator('#modePerform').click()
    toggle = page.locator('#sidebarToggle')
    expect(toggle).to_be_visible()
    for width in [1570, 1280, 1024, 700]:
        page.set_viewport_size({'width': width, 'height': 950})
        for theme in ['dark', 'graphite', 'warm', 'light']:
            page.select_option('#themeSelect', theme)
            if toggle.get_attribute('aria-expanded') == 'false':
                toggle.click()
            before = page.locator('.main').bounding_box()['width']
            selected = page.evaluate('state.selectedCueId')
            next_id = page.evaluate('state.status.next_cue_id')
            toggle.focus()
            toggle.press('Space')
            expect(toggle).to_have_attribute('aria-expanded', 'false')
            expect(page.locator('#settingsSidebar')).not_to_be_visible()
            after = page.locator('.main').bounding_box()['width']
            if width > 700:
                assert after > before + 150, (width, before, after)
            assert page.evaluate('state.selectedCueId') == selected
            assert page.evaluate('state.status.next_cue_id') == next_id
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            # Exercise the same coordinate inversion used by real pointer events.
            result = page.evaluate('''() => {
              const svg = document.querySelector('#performMap svg');
              const g = StageMap.geometry(state.project.speakers);
              const p = svg.createSVGPoint(); p.x = g.px(1); p.y = g.py(-1);
              const screen = p.matrixTransform(svg.getScreenCTM());
              return mapPoint({clientX:screen.x,clientY:screen.y});
            }''')
            assert result == {'x':1,'y':-1}, result
            # Mode switch restores the full sidebar without discarding the preference.
            page.locator('#modeEdit').click()
            expect(page.locator('#settingsSidebar')).to_be_visible()
            expect(toggle).not_to_be_visible()
            page.locator('#modePerform').click()
            expect(toggle).to_have_attribute('aria-expanded', 'false')
            assert page.evaluate('state.selectedCueId') == selected
            toggle.press('Enter')
            expect(toggle).to_have_attribute('aria-expanded', 'true')
            expect(page.locator('#settingsSidebar')).to_be_visible()
    # Do not lose a pending edit merely by changing layout/mode.
    page.evaluate("window.__sidebarNotes=state.project.cues[0].notes; state.project.cues[0].notes='pending sidebar probe';saveQueue.changed()")
    toggle.click()
    page.locator('#modeEdit').click()
    page.locator('#modePerform').click()
    assert page.evaluate("saveQueue.dirty && state.project.cues[0].notes==='pending sidebar probe'")
    page.evaluate("state.project.cues[0].notes=window.__sidebarNotes")
    page.evaluate('saveNow()')
    page.set_viewport_size({'width':1570,'height':950})
    print('PASS sidebar: 4 themes x 4 widths, keyboard, width release, coordinates, modes, pending edits')
