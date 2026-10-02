import { redirect } from 'next/navigation';

type Props = {
  params: Promise<{ locale: string }>;
};

/**
 * The global community has been retired.
 *
 * Community is artist-scoped: every conversation belongs to one artist and is
 * reached from that artist's page. This route exists only so old links and
 * bookmarks land somewhere sensible instead of a 404.
 */
export default async function RetiredCommunityPage({ params }: Props) {
  const { locale } = await params;

  redirect(`/${locale}/artists`);
}