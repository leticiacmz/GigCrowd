'use client';

import { useState, useEffect } from 'react';

export type ThemeMode = 'system' | 'light' | 'dark';

export function useTheme() {
  const [theme, setTheme] = useState<ThemeMode>('system');

  // Check for persisted preference
  useEffect(() => {
    const savedTheme = localStorage.getItem('gigcrowd-theme');
    const systemMatch = window.matchMedia('(prefers-color-scheme: dark)').matches;

    if (savedTheme) {
      setTheme(savedTheme as ThemeMode);
    } else if (systemMatch) {
      setTheme('dark');
    } else {
      setTheme('light');
    }
  }, []);

  // Persist changes
  useEffect(() => {
    const themeToSave = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme;
    localStorage.setItem('gigcrowd-theme', themeToSave);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => {
      if (prev === 'system') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark';
      }
      return prev === 'light' ? 'dark' : 'light';
    });
  };

  return { theme, toggleTheme };
}