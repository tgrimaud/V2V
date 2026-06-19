# Vite + React + TypeScript Setup Reference

## Initialize Project

```bash
npm create vite@latest cursor-dashboard-frontend -- --template react-ts
cd cursor-dashboard-frontend
npm install
```

## Install Dependencies

```bash
# Core dependencies
npm install @tanstack/react-query react-router-dom recharts

# TailwindCSS
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Types
npm install -D @types/react-router-dom

# Testing (optional)
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

## Configuration Files

### tailwind.config.js

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-primary': 'var(--color-bg-primary)',
        'bg-secondary': 'var(--color-bg-secondary)',
        'bg-tertiary': 'var(--color-bg-tertiary)',
        'border': 'var(--color-border)',
        'text-primary': 'var(--color-text-primary)',
        'text-secondary': 'var(--color-text-secondary)',
        'text-muted': 'var(--color-text-muted)',
        'accent': 'var(--color-accent)',
        'accent-hover': 'var(--color-accent-hover)',
        'error': 'var(--color-error)',
        'warning': 'var(--color-warning)',
        'success': 'var(--color-success)',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
```

### vite.config.ts

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
```

### tsconfig.json (paths)

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### .env.example

```bash
VITE_API_URL=http://localhost:8080
```

### .eslintrc.cjs

```javascript
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
  },
}
```

### .prettierrc

```json
{
  "semi": true,
  "singleQuote": true,
  "tabWidth": 2,
  "trailingComma": "es5",
  "printWidth": 100
}
```

## Directory Structure Setup

```bash
# Create feature structure
mkdir -p src/features/auth/{components,hooks,types,__tests__}
mkdir -p src/features/usage/{components,hooks,types,__tests__}
mkdir -p src/shared/{components,hooks,types}
mkdir -p src/services

# Create barrel exports
touch src/features/auth/index.ts
touch src/features/usage/index.ts
touch src/shared/index.ts
touch src/services/index.ts
```

## Initial Files

### src/index.css

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* Backgrounds */
  --color-bg-primary: #0a0a0a;
  --color-bg-secondary: #141414;
  --color-bg-tertiary: #1a1a1a;

  /* Borders */
  --color-border: #2a2a2a;

  /* Text */
  --color-text-primary: #ffffff;
  --color-text-secondary: #a1a1a1;
  --color-text-muted: #666666;

  /* Accent */
  --color-accent: #00d4aa;
  --color-accent-hover: #00f0c0;

  /* Semantic */
  --color-error: #ef4444;
  --color-warning: #f59e0b;
  --color-success: #10b981;

  /* Chart palette */
  --color-chart-cost: #00d4aa;
  --color-chart-requests: #6366f1;
  --color-chart-tokens: #f59e0b;
}

body {
  margin: 0;
  background-color: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

### src/main.tsx

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './services/queryClient';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
```

### src/services/queryClient.ts

```typescript
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
```

### src/services/apiClient.ts

```typescript
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080';

interface ApiResponse<T> {
  data: T;
  meta: {
    timestamp: string;
    request_id: string;
  };
}

interface ErrorResponse {
  code: string;
  message: string;
  timestamp: string;
}

export class ApiError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`);

  if (!response.ok) {
    const error: ErrorResponse = await response.json();
    throw new ApiError(error.code, error.message);
  }

  const json: ApiResponse<T> = await response.json();
  return json.data;
}

export async function fetchDailyActiveUsers(startDate: string, endDate: string) {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  return fetchJson<DailyActiveUsers[]>(`/api/analytics/daily-active-users?${params}`);
}

export async function fetchTeamMembers() {
  return fetchJson<TeamMember[]>('/api/team/members');
}
```

### src/services/index.ts

```typescript
export { queryClient } from './queryClient';
export { fetchDailyActiveUsers, fetchTeamMembers, ApiError } from './apiClient';
```

## Running the Application

```bash
# Development
npm run dev

# Build
npm run build

# Preview production build
npm run preview

# Lint
npm run lint

# Type check
npx tsc --noEmit
```

## Testing Setup (Optional)

### vitest.config.ts

```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
```

### src/test/setup.ts

```typescript
import '@testing-library/jest-dom';
```

### package.json scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview",
    "test": "vitest",
    "test:ui": "vitest --ui"
  }
}
```
