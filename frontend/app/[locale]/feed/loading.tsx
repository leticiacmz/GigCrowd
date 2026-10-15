import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/**
 * Shown by the router the moment a reader asks for the timeline, before the
 * client component has mounted - the gap that used to look like a dead link.
 * The message is the feed's own, so it says what is really being waited on.
 */
export default async function FeedLoading() {
  const t = await getTranslations('feed');

  return <LoadingState size="page" message={t('loading')} />;
}
