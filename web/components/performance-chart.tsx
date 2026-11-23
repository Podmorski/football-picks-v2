'use client';

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { cn } from '@/lib/utils';

export type ChartPoint = { label: string; value: number };

export default function PerformanceChart({
  points,
  ariaLabel,
  valueLabel = 'Value',
  className,
}: {
  points: ChartPoint[];
  ariaLabel: string;
  valueLabel?: string;
  className?: string;
}) {
  // A single point is not a series; do not draw an invented trend.
  if (points.length < 2) return null;

  return (
    <figure className={cn('rounded-2xl border border-border bg-card p-4', className)} role="img" aria-label={ariaLabel}>
      <div className="h-56 w-full text-primary">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="currentColor" strokeOpacity={0.14} strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: 'currentColor', opacity: 0.7 }}
              tickLine={false}
              axisLine={{ strokeOpacity: 0.2 }}
              minTickGap={16}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'currentColor', opacity: 0.7 }}
              tickLine={false}
              axisLine={false}
              width={44}
              tickFormatter={(value: number) => value.toFixed(0)}
            />
            <Tooltip
              formatter={(value) => [Number(value).toFixed(2), valueLabel]}
              contentStyle={{
                background: 'var(--card)',
                border: '1px solid var(--border)',
                borderRadius: 12,
                color: 'var(--card-foreground)',
                fontSize: 12,
              }}
              labelStyle={{ color: 'var(--muted-foreground)' }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="currentColor"
              strokeWidth={2}
              fill="currentColor"
              fillOpacity={0.12}
              dot={{ r: 2, fill: 'currentColor' }}
              activeDot={{ r: 3 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
