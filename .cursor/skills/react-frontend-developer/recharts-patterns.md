# Recharts Patterns Reference

## Installation

```bash
npm install recharts
```

## Basic Bar Chart

```typescript
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface ChartData {
  period: string;
  value: number;
}

interface UsageChartProps {
  data: ChartData[];
  metric: 'cost' | 'requests' | 'tokens';
}

const METRIC_COLORS = {
  cost: 'var(--color-chart-cost)',      // #00d4aa
  requests: 'var(--color-chart-requests)', // #6366f1
  tokens: 'var(--color-chart-tokens)',   // #f59e0b
};

export function UsageBarChart({ data, metric }: UsageChartProps) {
  return (
    <div role="img" aria-label={`Bar chart showing ${metric} over time`}>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
          <XAxis
            dataKey="period"
            stroke="#666666"
            tick={{ fill: '#a1a1a1', fontSize: 12 }}
          />
          <YAxis
            stroke="#666666"
            tick={{ fill: '#a1a1a1', fontSize: 12 }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1a1a1a',
              border: '1px solid #2a2a2a',
              borderRadius: '8px',
              color: '#ffffff',
            }}
          />
          <Legend />
          <Bar
            dataKey="value"
            name={metric.charAt(0).toUpperCase() + metric.slice(1)}
            fill={METRIC_COLORS[metric]}
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

## Line Chart

```typescript
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

export function UsageLineChart({ data, metric }: UsageChartProps) {
  return (
    <div role="img" aria-label={`Line chart showing ${metric} over time`}>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
          <XAxis
            dataKey="period"
            stroke="#666666"
            tick={{ fill: '#a1a1a1', fontSize: 12 }}
          />
          <YAxis
            stroke="#666666"
            tick={{ fill: '#a1a1a1', fontSize: 12 }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1a1a1a',
              border: '1px solid #2a2a2a',
              borderRadius: '8px',
              color: '#ffffff',
            }}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="value"
            name={metric.charAt(0).toUpperCase() + metric.slice(1)}
            stroke={METRIC_COLORS[metric]}
            strokeWidth={2}
            dot={{ fill: METRIC_COLORS[metric], strokeWidth: 2 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

## Multi-Series Chart

```typescript
interface MultiSeriesData {
  period: string;
  cost: number;
  requests: number;
  tokens: number;
}

export function MultiSeriesChart({ data }: { data: MultiSeriesData[] }) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
        <XAxis dataKey="period" stroke="#666666" tick={{ fill: '#a1a1a1' }} />
        <YAxis yAxisId="left" stroke="#666666" tick={{ fill: '#a1a1a1' }} />
        <YAxis yAxisId="right" orientation="right" stroke="#666666" tick={{ fill: '#a1a1a1' }} />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1a1a1a',
            border: '1px solid #2a2a2a',
            borderRadius: '8px',
          }}
        />
        <Legend />
        <Line yAxisId="left" type="monotone" dataKey="cost" stroke="#00d4aa" />
        <Line yAxisId="left" type="monotone" dataKey="requests" stroke="#6366f1" />
        <Line yAxisId="right" type="monotone" dataKey="tokens" stroke="#f59e0b" />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

## Custom Tooltip

```typescript
interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload) return null;

  return (
    <div className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg p-3">
      <p className="text-[var(--color-text-secondary)] text-sm mb-2">{label}</p>
      {payload.map((entry, index) => (
        <p key={index} style={{ color: entry.color }} className="text-sm">
          {entry.name}: {formatValue(entry.value, entry.name)}
        </p>
      ))}
    </div>
  );
}

// Usage
<Tooltip content={<CustomTooltip />} />
```

## Period Label Formatting

```typescript
function formatPeriodLabel(period: string): string {
  // Date: "2026-01-15" → "Jan 15"
  if (period.length === 10) {
    const date = new Date(period);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
  
  // Month: "2026-01" → "Jan 2026"
  if (period.length === 7) {
    const [year, month] = period.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1);
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  }
  
  // Week: "2026-W03" → "Week 3"
  if (period.includes('W')) {
    return `Week ${period.split('W')[1]}`;
  }
  
  return period;
}

// Usage
<XAxis dataKey="period" tickFormatter={formatPeriodLabel} />
```

## Value Formatting

```typescript
function formatValue(value: number, metric: string): string {
  if (metric === 'cost') {
    return `$${value.toFixed(2)}`;
  }
  
  if (metric === 'tokens' && value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  
  return value.toLocaleString();
}

// Usage in YAxis
<YAxis tickFormatter={(value) => formatValue(value, metric)} />
```

## Empty State

```typescript
interface ChartContainerProps {
  data: ChartData[];
  children: React.ReactNode;
}

export function ChartContainer({ data, children }: ChartContainerProps) {
  if (data.length === 0) {
    return (
      <div className="h-80 flex items-center justify-center bg-[var(--color-bg-secondary)] rounded-lg">
        <p className="text-[var(--color-text-muted)]">No data to display</p>
      </div>
    );
  }

  return <>{children}</>;
}
```

## Chart Wrapper Component

```typescript
type ChartType = 'bar' | 'line';

interface UsageChartProps {
  data: ChartData[];
  metric: 'cost' | 'requests' | 'tokens';
  chartType?: ChartType;
}

export function UsageChart({ data, metric, chartType = 'bar' }: UsageChartProps) {
  if (data.length === 0) {
    return (
      <div
        role="img"
        aria-label="Empty chart"
        className="h-80 flex items-center justify-center"
      >
        <p className="text-[var(--color-text-muted)]">No data to display</p>
      </div>
    );
  }

  const ChartComponent = chartType === 'bar' ? UsageBarChart : UsageLineChart;

  return (
    <div
      role="img"
      aria-label={`${chartType} chart showing ${metric} over time`}
    >
      <ChartComponent data={data} metric={metric} />
    </div>
  );
}
```

## Theme Constants

```typescript
// constants/chartTheme.ts
export const CHART_THEME = {
  colors: {
    cost: '#00d4aa',
    requests: '#6366f1',
    tokens: '#f59e0b',
  },
  grid: {
    stroke: '#2a2a2a',
    strokeDasharray: '3 3',
  },
  axis: {
    stroke: '#666666',
    tick: {
      fill: '#a1a1a1',
      fontSize: 12,
    },
  },
  tooltip: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #2a2a2a',
    borderRadius: '8px',
    color: '#ffffff',
  },
} as const;
```

## Accessibility

- Always wrap charts in `role="img"` with descriptive `aria-label`
- Include text alternatives for key data points
- Ensure sufficient color contrast
- Provide legend for multi-series charts

```typescript
<div
  role="img"
  aria-label={`Bar chart showing ${metric}. Peak value: ${Math.max(...data.map(d => d.value))} on ${peakDate}`}
>
  <ResponsiveContainer>
    {/* chart content */}
  </ResponsiveContainer>
</div>
```
