export interface PublicNavLink {
  href: string;
  label: string;
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
    { href: `/${locale}/events`, label: labels.events ?? 'Events' },
  ];
}
