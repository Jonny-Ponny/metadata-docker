import { writable } from 'svelte/store';

const getInitialTheme = () => {
  if (typeof localStorage !== 'undefined') {
    const saved = localStorage.getItem('theme');
    if (saved) return saved;
  }
  if (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
};

export const theme = writable(getInitialTheme());

// Apply theme to body and save to localStorage
theme.subscribe(value => {
  if (typeof document !== 'undefined') {
    // Add a class to temporarily disable transitions
    document.body.classList.add('no-transitions');
    
    // Force a reflow to ensure the class is applied
    document.body.offsetHeight;
    
    // Apply the theme class
    if (value === 'dark') {
      document.body.classList.add('dark');
    } else {
      document.body.classList.remove('dark');
    }
    
    // Remove the no-transitions class after the theme is applied
    requestAnimationFrame(() => {
      setTimeout(() => {
        document.body.classList.remove('no-transitions');
      }, 10);
    });
    
    localStorage.setItem('theme', value);
  }
});

export const toggleTheme = () => {
  theme.update(t => (t === 'light' ? 'dark' : 'light'));
};