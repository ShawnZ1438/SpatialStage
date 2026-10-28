"""Cue selection must retain the operator's scrolled viewport; never starts audio."""
def check_cue_scroll(page):
    from playwright.sync_api import expect
    for mode, collapsed in [('Edit', False), ('Perform', False), ('Perform', True)]:
        page.locator('#mode' + mode).click()
        if mode == 'Perform':
            toggle = page.locator('#sidebarToggle')
            if (toggle.get_attribute('aria-expanded') == 'false') != collapsed:
                toggle.click()
        for index in [24, 25, 24, 28]:
            row = page.locator('.perf-cue').nth(index)
            row.scroll_into_view_if_needed()
            before = page.locator('#cueListBody').evaluate('(e)=>e.scrollTop')
            assert before > 0
            page.evaluate('window.__scrollBody=document.querySelector("#cueListBody");window.__next=state.status.next_cue_id')
            row.click()
            assert page.evaluate('window.__scrollBody===document.querySelector("#cueListBody")')
            assert page.locator('#cueListBody').evaluate('(e)=>e.scrollTop') == before
            expect(row).to_have_class(__import__('re').compile(r'.*selected.*'))
            assert page.evaluate('state.status.next_cue_id===window.__next')
            row.press('Enter')
            assert page.locator('#cueListBody').evaluate('(e)=>e.scrollTop') == before
        if mode == 'Edit':
            field = page.locator('input[data-lf="delay_s"]').first
            old = field.input_value()
            before = page.locator('#cueListBody').evaluate('(e)=>e.scrollTop')
            field.fill(str(float(old) + .1));field.press('Tab')
            assert page.locator('#cueListBody').evaluate('(e)=>e.scrollTop') == before
            field = page.locator('input[data-lf="delay_s"]').first
            field.fill(old);field.press('Tab')
            page.evaluate('saveNow()')
        # A genuine structural render (e.g. layer path edit) also keeps scroll.
        result = page.evaluate('''() => {
          const cue=currentCue(), layer=cue.layers[0];
          const original=structuredClone(cue), before=$('cueListBody').scrollTop;
          layer.position_deg=(layer.position_deg+1)%360;
          render(true);
          const after=$('cueListBody').scrollTop;
          Object.assign(cue,original);render(true);
          return {before,after};
        }''')
        assert result['before'] == result['after'], result
        # Pending programming is not lost on selection or a layout change.
        assert page.evaluate('''() => {
          const cue=currentCue(), old=cue.notes;cue.notes='pending scroll probe';
          selectCue(state.project.cues[24].id);render(true);
          const retained=cue.notes==='pending scroll probe';cue.notes=old;return retained;
        }''')
    print('PASS cue scroll: repeated lower-row click/Enter, Edit/Performance, sidebar expanded/collapsed, layer rerender, NEXT and pending programming')
