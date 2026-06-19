---
name: react-frontend-developer
description: >-
  Develop React frontend applications with TypeScript, TailwindCSS, React Query, and Recharts.
  Follows feature-based architecture, barrel exports, and accessibility best practices.
  Use when writing React components, creating hooks, implementing data visualization,
  or structuring frontend projects. For architectural principles (feature-based modularization,
  the Hive pattern, hexagonal concepts applied to frontend), see also the software-architect skill.
---

# React Frontend Developer

React/TypeScript implementation patterns for the feature-based architecture described in the `software-architect` skill.

## Technology Stack

- **React 18** with TypeScript 5.x
- **Vite** for build and dev server
- **TailwindCSS** with CSS variables for design tokens
- **React Query** (@tanstack/react-query) for server state
- **Recharts** for data visualization
- **React Router** for navigation

## Project Structure

The feature-based structure below implements the modular architecture described in the `software-architect` skill. Each feature is a self-contained module with its own barrel export (the module's public API).

```
src/
├── main.tsx                 # Entry point
├── App.tsx                  # Root component, routing
├── index.css                # Global styles, design tokens
├── vite-env.d.ts
│
├── features/                # Feature modules (bounded contexts)
│   ├── auth/
│   │   ├── index.ts         # Barrel export
│   │   ├── components/
│   │   │   └── ApiKeyInput.tsx
│   │   ├── hooks/
│   │   │   └── useAuth.ts
│   │   ├── types/
│   │   │   └── AuthState.ts
│   │   └── __tests__/
│   │       └── ApiKeyInput.test.tsx
│   │
│   └── usage/
│       ├── index.ts
│       ├── components/
│       │   ├── UsageChart.tsx
│       │   ├── UsageSummaryCard.tsx
│       │   └── DateRangeSelector.tsx
│       ├── hooks/
│       │   └── useUsageData.ts
│       ├── types/
│       │   └── UsageSummary.ts
│       └── __tests__/
│
├── shared/                  # Cross-feature reusable components
│   ├── index.ts
│   ├── components/
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Input.tsx
│   │   ├── Select.tsx
│   │   ├── Spinner.tsx
│   │   └── Alert.tsx
│   ├── hooks/
│   │   └── useStatus.ts
│   └── types/
│       └── ApiResponse.ts
│
└── services/                # API and utilities
    ├── index.ts
    ├── apiClient.ts
    └── queryClient.ts
```

## Barrel Exports

Every feature folder has an `index.ts` re-exporting its public API:

```typescript
// features/usage/index.ts
export { UsageChart } from './components/UsageChart';
export { UsageSummaryCard } from './components/UsageSummaryCard';
export { DateRangeSelector } from './components/DateRangeSelector';
export { useUsageData } from './hooks/useUsageData';
export type { UsageSummary } from './types/UsageSummary';
```

Import from barrel, not deep paths:
```typescript
// Good
import { UsageChart, useUsageData } from '@/features/usage';

// Avoid
import { UsageChart } from '@/features/usage/components/UsageChart';
```

## Component Patterns

### Functional Components

```typescript
interface UsageChartProps {
  data: AggregatedUsage[];
  metric: 'cost' | 'requests' | 'tokens';
  chartType?: 'bar' | 'line';
}

export function UsageChart({ data, metric, chartType = 'bar' }: UsageChartProps) {
  if (data.length === 0) {
    return <EmptyState message="No data to display" />;
  }

  return (
    <div role="img" aria-label={`${chartType} chart showing ${metric}`}>
      <ResponsiveContainer width="100%" height={320}>
        {chartType === 'bar' ? (
          <BarChart data={data}>
            {/* chart config */}
          </BarChart>
        ) : (
          <LineChart data={data}>
            {/* chart config */}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
```

### Status Union Type

Use status union for loading states (not boolean flags):

```typescript
type Status = 'idle' | 'loading' | 'success' | 'error';

const [status, setStatus] = useState<Status>('idle');

// Or use React Query's status directly
const { status, data, error } = useQuery({...});
```

### Props Interface Naming

```typescript
// Component props: ComponentNameProps
interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'destructive';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  children: React.ReactNode;
}

// Event handlers: onAction
interface FormProps {
  onSubmit: (data: FormData) => void;
  onCancel: () => void;
}
```

## React Query Patterns

### Query Hook

```typescript
import { useQuery } from '@tanstack/react-query';
import { fetchDailyActiveUsers } from '@/services/apiClient';

export function useUsageData(dateRange: DateRange) {
  return useQuery({
    queryKey: ['usage', 'daily-active-users', dateRange],
    queryFn: () => fetchDailyActiveUsers(dateRange),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
```

### Using Query Hook

```typescript
function Dashboard() {
  const { status, data, error, refetch } = useUsageData(dateRange);

  if (status === 'loading') return <Spinner />;
  if (status === 'error') return <Alert variant="error">{error.message}</Alert>;

  return <UsageChart data={data} />;
}
```

### Query Client Setup

```typescript
// services/queryClient.ts
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
```

## API Client

```typescript
// services/apiClient.ts
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080';

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Request failed');
  }
  const json = await response.json();
  return json.data; // Unwrap ApiResponse wrapper
}

export async function fetchDailyActiveUsers(range: DateRange) {
  const params = new URLSearchParams({
    start_date: range.startDate,
    end_date: range.endDate,
  });
  return fetchJson<DailyActiveUsers[]>(`/api/analytics/daily-active-users?${params}`);
}
```

## Design Tokens

### CSS Variables (index.css)

```css
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
```

### TailwindCSS with Variables

```typescript
// In components, reference CSS variables
<div className="bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)]">

// Or extend Tailwind config
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        'bg-primary': 'var(--color-bg-primary)',
        'bg-secondary': 'var(--color-bg-secondary)',
        accent: 'var(--color-accent)',
      },
    },
  },
};
```

## Shared Components

### Button

```typescript
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'destructive';
  isLoading?: boolean;
}

export function Button({
  variant = 'primary',
  isLoading,
  disabled,
  children,
  className,
  ...props
}: ButtonProps) {
  const baseStyles = 'px-4 py-3 rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2';
  
  const variants = {
    primary: 'bg-[var(--color-accent)] text-[var(--color-bg-primary)] hover:bg-[var(--color-accent-hover)] focus:ring-[var(--color-accent)]',
    secondary: 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
    destructive: 'text-[var(--color-error)] hover:text-[var(--color-text-primary)]',
  };

  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${disabled || isLoading ? 'opacity-50 cursor-not-allowed' : ''} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <>
          <Spinner size="sm" className="mr-2" />
          Loading...
        </>
      ) : (
        children
      )}
    </button>
  );
}
```

### Card

```typescript
interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export function Card({ title, children, className }: CardProps) {
  return (
    <article
      className={`bg-[var(--color-bg-secondary)] rounded-lg p-6 border border-[var(--color-border)] ${className}`}
      aria-labelledby={title ? 'card-title' : undefined}
    >
      {title && (
        <h2 id="card-title" className="text-lg font-semibold mb-4">
          {title}
        </h2>
      )}
      {children}
    </article>
  );
}
```

### Spinner

```typescript
interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function Spinner({ size = 'md', className }: SpinnerProps) {
  const sizes = { sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' };

  return (
    <div
      role="status"
      aria-label="Loading"
      className={`${sizes[size]} border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin ${className}`}
    />
  );
}
```

## Accessibility

### Focus Indicators

```css
/* All interactive elements need visible focus */
.focus-ring {
  @apply focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-2 focus:ring-offset-[var(--color-bg-primary)];
}
```

### ARIA Patterns

```typescript
// Icons are decorative
<svg aria-hidden="true">{/* icon */}</svg>

// Form inputs with labels
<label htmlFor="api-key">API Key</label>
<input id="api-key" aria-describedby="api-key-error" />
{error && <p id="api-key-error" role="alert">{error}</p>}

// Loading states
<div role="status" aria-label="Loading">
  <Spinner />
</div>

// Charts
<div role="img" aria-label="Bar chart showing cost over time">
  <BarChart />
</div>
```

### Keyboard Navigation

- All interactive elements must be focusable
- Tab order follows visual order
- Enter/Space activates buttons
- Escape closes modals/dropdowns

## File Naming

| Type | Convention | Example |
|------|------------|---------|
| Components | PascalCase | `UsageChart.tsx` |
| Hooks | camelCase with `use` | `useUsageData.ts` |
| Types | PascalCase | `UsageSummary.ts` |
| Services | camelCase | `apiClient.ts` |
| Tests | Component + `.test` | `UsageChart.test.tsx` |

## Testing

### Test Location

Tests in `__tests__` folder at feature level:
```
features/usage/
├── components/
│   └── UsageChart.tsx
└── __tests__/
    └── UsageChart.test.tsx
```

### Test Example

```typescript
import { render, screen } from '@testing-library/react';
import { UsageChart } from '../components/UsageChart';

describe('UsageChart', () => {
  it('renders empty state when no data', () => {
    render(<UsageChart data={[]} metric="cost" />);
    expect(screen.getByText('No data to display')).toBeInTheDocument();
  });

  it('renders bar chart by default', () => {
    render(<UsageChart data={mockData} metric="cost" />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      'bar chart showing cost'
    );
  });
});
```

## Checklist

Before committing:

- [ ] Components use TypeScript with explicit props interfaces
- [ ] Feature folders have barrel exports (`index.ts`)
- [ ] Imports use barrel exports, not deep paths
- [ ] React Query used for server state (not useState)
- [ ] Status union type for loading states
- [ ] CSS variables used for design tokens
- [ ] All interactive elements have focus indicators
- [ ] Form inputs have associated labels
- [ ] Icons have `aria-hidden="true"`
- [ ] Charts have `role="img"` with `aria-label`
- [ ] Tests in `__tests__` folder
