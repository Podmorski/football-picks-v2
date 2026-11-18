'use client';

import * as React from 'react';

import { cn } from '@/lib/utils';

type TabsContextValue = { value: string; setValue: (value: string) => void };
const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabs() {
  const context = React.useContext(TabsContext);
  if (!context) throw new Error('Tabs components must be used inside <Tabs>');
  return context;
}

type TabsProps = React.ComponentProps<'div'> & {
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
};

function Tabs({ defaultValue = '', value, onValueChange, className, children, ...props }: TabsProps) {
  const [internal, setInternal] = React.useState(defaultValue);
  const current = value ?? internal;
  const setValue = React.useCallback(
    (next: string) => {
      setInternal(next);
      onValueChange?.(next);
    },
    [onValueChange],
  );

  return (
    <TabsContext.Provider value={{ value: current, setValue }}>
      <div className={cn('w-full', className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

function TabsList({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      role="tablist"
      className={cn('inline-flex flex-wrap items-center gap-1 rounded-lg bg-muted p-1', className)}
      {...props}
    />
  );
}

type TabsTriggerProps = React.ComponentProps<'button'> & { value: string };

function TabsTrigger({ value, className, ...props }: TabsTriggerProps) {
  const context = useTabs();
  const active = context.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => context.setValue(value)}
      className={cn(
        'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({ value, className, ...props }: React.ComponentProps<'div'> & { value: string }) {
  const context = useTabs();
  if (context.value !== value) return null;
  return <div role="tabpanel" className={cn('mt-4', className)} {...props} />;
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
