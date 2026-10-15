import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/** Notifications announce loading as loading, never as their own title. */
export default async function NotificationsLoading() {
  const t = await getTranslations('common');

  return <LoadingState size="page" message={t('loading')} />;
}
