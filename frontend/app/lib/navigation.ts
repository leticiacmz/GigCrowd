export interface PublicNavLink {
  href: string;
  label: string;
  /**
   * Which inline icon names this destination, when it is drawn as one.
   *
   * Only destinations whose meaning is carried by a conventional glyph get
   * one: a magnifier means "find events", and needs no word beside it on a
   * desktop bar. The label is still the link's accessible name, so an icon
   * is never the only thing telling a screen reader where the link goes.
   */
  icon?: 'search';
}

/**
 * The public destinations in the main navigation, as one pure list.
 *
 * There is no general Artists entry. Artists are reached from a lineup, an
 * event or a search - one artist at a time, on demand - so a browsing tab
 * that lists the whole catalogue is no longer a path through the product.
 * Community is absent for the same reason it has been absent from the bar:
 * it lives inside an artist, with no global destination to link to.
 *
 * Both the desktop bar and the mobile menu read this list, so the two
 * cannot drift, and being pure makes "no artists tab" a rule a test can
 * hold without rendering a component.
 */
export function publicNavItems(
  locale: string,
  labels: Record<string, string | undefined>,
): PublicNavLink[] {
  return [
    {
      href: `/${locale}/events`,
      label: labels.events ?? 'Events',
      icon: 'search',
    },
  ];
}
