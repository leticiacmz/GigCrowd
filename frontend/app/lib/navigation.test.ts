/*
  The main navigation's public destinations.

  There is no general Artists tab: artists are opened one at a time from a
  lineup, an event or a search. There is no Feed tab either: the logo is
  the timeline for a signed-in reader. `publicNavItems` is the single list
  the desktop bar and the mobile menu both read, so holding the rules here
  holds them for both, and each is testable without rendering a component.
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

test('the main navigation has no feed tab - the logo is the timeline', () => {
  for (const locale of ['en', 'pt-BR', 'es'] as const) {
    const items = publicNavItems(locale, {});

    assert.ok(
      items.every((item) => !item.href.endsWith('/feed')),
      `no feed destination for ${locale}`,
    );
  }
});

test('a destination drawn as an icon says which icon', () => {
  const [events] = publicNavItems('en', {});

  // The magnifier is the desktop bar's presentation of Events; the label
  // stays its accessible name, so the icon is never the only thing that
  // names the link.
  assert.equal(events.icon, 'search');
  assert.equal(events.label, 'Events');
});

test('a missing label falls back to English rather than going blank', () => {
  const [events] = publicNavItems('en', {});

  assert.equal(events.label, 'Events');
});
