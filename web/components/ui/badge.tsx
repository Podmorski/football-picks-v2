import * as React from 'react';

import { cn } from '@/lib/utils';

const VARIANTS: Record<string, string> = {
  default: 'border-transparent bg-primary text-primary-foreground',
  secondary: 'border-transparent bg-muted text-foreground',
  outline: 'border-border text-foreground',
  success: 'border-transparent bg-success/15 text-success',
  warning: 'border-transparent bg-warning/20 text-foreground',
  value: 'border-transparent bg-amber-500/15 text-amber-700',
  destructive: 'border-transparent bg-destructive/15 text-destructive',
};

type BadgeProps = React.ComponentProps<'span'> & {
  variant?: keyof typeof VARIANTS;
};

function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}

export { Badge };
