import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/**
 * The artist overview fetches the profile, the upcoming list and the related
 * artists in parallel; this covers the whole trip with one honest sentence
 * instead of a page that looks frozen.
 */
export default async function ArtistLoading() {
  const t = await getTranslations('common');

  return <LoadingState size="page" message={t('loading')} />;
}
