import * as React from 'react';

import { cn } from '@/lib/utils';

type ProgressProps = React.ComponentProps<'div'> & {
  value: number;
};

function Progress({ className, value, ...props }: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      className={cn('h-2 w-full overflow-hidden rounded-full bg-muted', className)}
      {...props}
    >
      <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${clamped}%` }} />
    </div>
  );
}

export { Progress };
