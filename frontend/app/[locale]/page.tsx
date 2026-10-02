import { getTranslations } from 'next-intl/server';
import Link from 'next/link';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';

interface LocalePageProps {
  params: {
    locale: string;
  };
}

export default async function LocaleHomePage({ params }: LocalePageProps) {
  const locale = params.locale;

  const t = await getTranslations('home');
  const nav = await getTranslations('nav');

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center px-4 pt-2 pb-8">
      <section className="max-w-4xl text-center">
        <h1 className="text-[72px] sm:text-[96px] font-black tracking-tight bg-gradient-to-r from-accent via-secondary to-accent bg-clip-text text-transparent drop-shadow-[0_0_6px_rgba(255,0,255,0.12)] mb-6">
          GigCrowd
        </h1>

        <h2 className="text-3xl sm:text-4xl font-bold mb-5">{t('tagline')}</h2>

        <p className="text-muted text-lg max-w-xl mx-auto mb-10">
          {t('subtitle')}
        </p>

        <div className="flex justify-center gap-4 flex-wrap">
          <Link href={`/${locale}/events`}>
            <Button variant="neon" size="md" animated>
              {nav('exploreEvents')}
            </Button>
          </Link>

          <Link href={`/${locale}/register`}>
            <Button variant="outlineGradient" size="md" animated>
              {nav('joinGigCrowd')}
            </Button>
          </Link>
        </div>
      </section>

      <section className="grid md:grid-cols-3 gap-6 max-w-5xl w-full mt-10">
        <Card className="p-5 text-center transition-all hover:border-accent hover:shadow-[0_0_20px_rgba(255,0,255,0.15)]">
          <h3 className="text-lg font-bold mb-3">{nav('discoverArtists')}</h3>
          <p className="text-sm leading-relaxed text-muted">
            {t('discoverArtistsBody')}
          </p>
        </Card>

        <Card className="p-5 text-center transition-all hover:border-secondary hover:shadow-[0_0_20px_rgba(0,255,255,0.15)]">
          <h3 className="text-lg font-bold mb-3">{nav('trackShows')}</h3>
          <p className="text-sm leading-relaxed text-muted">
            {t('trackShowsBody')}
          </p>
        </Card>

        <Card className="p-5 text-center transition-all hover:border-accent hover:shadow-[0_0_20px_rgba(255,0,255,0.15)]">
          <h3 className="text-lg font-bold mb-3">{nav('shareStories')}</h3>
          <p className="text-sm leading-relaxed text-muted">
            {t('shareStoriesBody')}
          </p>
        </Card>
      </section>
    </div>
  );
}