/*
  The main navigation's public destinations.

  There is no general Artists tab: artists are opened one at a time from a
  lineup, an event or a search. `publicNavItems` is the single list the
  desktop bar and the mobile menu both read, so holding the rule here holds
  it for both, and the rule is testable without rendering a component.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { publicNavItems } from './navigation.ts';

test('the main navigation has no general artists tab', () => {
  for (const locale of ['en', 'pt-BR', 'es'] as const) {
    const items = publicNavItems(locale, {
      events: 'Eventos',
    });

    const hrefs = items.map((item) => item.href);

    assert.ok(
      hrefs.every((href) => !href.endsWith('/artists')),
      `no artists destination for ${locale}, got ${JSON.stringify(hrefs)}`,
    );

    // The destination that replaced it still ships, localised and prefixed.
    assert.ok(hrefs.includes(`/${locale}/events`));
    assert.ok(hrefs.every((href) => href.startsWith(`/${locale}/`)));
  }
});

test('a missing label falls back to English rather than going blank', () => {
  const [events] = publicNavItems('en', {});

  assert.equal(events.label, 'Events');
});
