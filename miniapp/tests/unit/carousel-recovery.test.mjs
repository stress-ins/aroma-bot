import assert from 'node:assert/strict';
import test from 'node:test';
import { createCoreModule } from '../../static/js/core.js';

const { generationStateMarkup } = createCoreModule({
  escapeHtml: (value) => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll("'", '&#39;'),
  uiIcon: () => '',
});
const draft = (payload, extra = {}) => ({ kind: 'carousel', draft_id: '4906a2d5', payload, ...extra });

test('legacy empty draft exposes full generation retry even after error was cleared', () => {
  const html = generationStateMarkup(draft({ slides: [], generation_stage: '' }));
  assert.match(html, /Карусель не создана/);
  assert.match(html, /data-action="regenerateCarouselAll"/);
  assert.match(html, /4906a2d5/);
});

test('blank and null slide text exposes recovery', () => {
  for (const slide of [' ', { heading: null, body: null }, { text: 0 }]) {
    const html = generationStateMarkup(draft({ slides: [slide] }));
    assert.match(html, /Карусель не создана/);
    assert.match(html, /Повторить генерацию/);
  }
});

test('failed carousel displays safe error message and retry', () => {
  const html = generationStateMarkup(draft({ slides: ['Slide'], generation_stage: 'error', generation_message: '<script>error</script>' }));
  assert.match(html, /Повторить генерацию/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});

test('pending and completed drafts do not offer error retry', () => {
  const pending = generationStateMarkup(draft({ slides: [] }, { generation_pending: true, generation_stage: 'slides' }));
  assert.doesNotMatch(pending, /Повторить генерацию/);
  assert.match(pending, /Собираю структуру карусели/);
  assert.equal(generationStateMarkup(draft({ slides: ['Slide'] })), '');
});

test('payload pending state also shows progress without offering retry', () => {
  const html = generationStateMarkup(draft({ slides: [], generation_pending: true, generation_stage: 'slides' }));
  assert.match(html, /Собираю структуру карусели/);
  assert.doesNotMatch(html, /Повторить генерацию/);
});
