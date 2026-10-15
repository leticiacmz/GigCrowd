import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/**
 * The gigography, with the exact sentence agreed for it: the page is
 * fetching this artist's events, not generic content.
 */
export default async function ArtistEventsLoading() {
  const t = await getTranslations('artistEvents');

  return <LoadingState size="page" message={t('loading')} />;
}
