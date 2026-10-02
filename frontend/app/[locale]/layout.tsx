import { Inter } from 'next/font/google';

import { notFound } from 'next/navigation';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages, setRequestLocale } from 'next-intl/server';

import Navbar from '@/components/Navbar';

import '../globals.css';
import { locales, type Locale } from '../i18n';

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'GigCrowd',
  description: 'A social platform for live music experiences',
  icons: {
    icon: '/favicon.ico',
  },
};

/**
 * Runs before first paint so the resolved theme is applied without a flash.
 * Must stay in sync with `components/use-theme.ts`.
 *
 * The document language is not handled here: it is rendered from the route
 * segment below, so it is correct in the very first byte the server sends
 * rather than only once a browser executes script.
 */
const themeBootstrapScript = `(function(){try{
var s=localStorage.getItem('gigcrowd-theme');
var t=(s==='light'||s==='dark')?s:(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-theme',t);
}catch(e){}})();`;

interface LocaleLayoutProps {
  children: React.ReactNode;
  params: {
    locale: string;
  };
}

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: LocaleLayoutProps) {
  const locale = params.locale;

  if (!locales.includes(locale as Locale)) {
    notFound();
  }

  setRequestLocale(locale);

  const messages = await getMessages({ locale });

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        <link rel="manifest" href="/manifest.json" />
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>

      <body className={inter.className}>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Navbar messages={messages} />
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
