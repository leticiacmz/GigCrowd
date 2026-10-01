import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'GigCrowd',
  description: 'A social platform for live music experiences',
  icons: {
    icon: '/favicon.ico',
  },
};

/**
 * Runs before first paint so the resolved theme (and document language)
 * are applied without a flash. Must stay in sync with `components/use-theme.ts`.
 */
const themeBootstrapScript = `(function(){try{
var s=localStorage.getItem('gigcrowd-theme');
var t=(s==='light'||s==='dark')?s:(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-theme',t);
var seg=location.pathname.split('/')[1];
if(['en','pt-BR','es'].indexOf(seg)!==-1){document.documentElement.setAttribute('lang',seg);}
}catch(e){}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="manifest" href="/manifest.json" />
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body className={inter.className}>
        {children}
      </body>
    </html>
  );
}