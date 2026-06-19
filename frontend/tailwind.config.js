import typography from '@tailwindcss/typography';

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Editorial Research Lab — distinctive display + body pairing.
      // Fraunces (variable serif) for headlines, Noto Serif SC for
      // Chinese editorial accents, Noto Sans SC for body, and
      // JetBrains Mono for tabular numbers / status chips.
      fontFamily: {
        display: ['"Fraunces"', '"Noto Serif SC"', 'Georgia', 'serif'],
        serif: ['"Noto Serif SC"', '"Fraunces"', 'Georgia', 'serif'],
        sans: [
          '"Noto Sans SC"',
          '"Inter"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          'system-ui',
          'sans-serif',
        ],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Menlo', 'monospace'],
      },
      colors: {
        // Warm paper background palette.
        paper: {
          50: '#FCFBF6',
          100: '#F7F4EB',
          200: '#EFEADC',
          300: '#E6E1D2',
        },
        // Ink for text — neutral with a brown undertone, not pure grey.
        ink: {
          50: '#F2EFE7',
          400: '#A6A29B',
          500: '#6B6B6B',
          700: '#3A3A3A',
          900: '#1A1A1A',
        },
        // Single accent: deep claret. Hat tip to the brand without
        // mimicking the platform's saturated red.
        claret: {
          50: '#FBEFEF',
          100: '#F5DCDC',
          200: '#EAB8B8',
          400: '#C13B3B',
          500: '#A62D2D',
          600: '#8C2424',
          700: '#6F1B1B',
        },
        // Sage accent for success / running states.
        sage: {
          50: '#F0F2EC',
          100: '#DDE3D4',
          400: '#7C8F62',
          500: '#5F7448',
          600: '#4A5C37',
        },
        rule: '#E6E1D2',
      },
      borderRadius: {
        '4xl': '2rem',
      },
      boxShadow: {
        paper: '0 1px 0 0 #E6E1D2, 0 12px 32px -16px rgba(26,26,26,0.10)',
        inset: 'inset 0 -1px 0 0 #E6E1D2',
        lift: '0 1px 0 rgba(26,26,26,0.06), 0 6px 18px -8px rgba(26,26,26,0.08)',
      },
      letterSpacing: {
        tightish: '-0.012em',
        tighter: '-0.025em',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'pulse-dot': {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.5s cubic-bezier(0.2, 0.65, 0.3, 1) both',
        'fade-in': 'fade-in 0.4s ease-out both',
        'pulse-dot': 'pulse-dot 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [typography],
};
