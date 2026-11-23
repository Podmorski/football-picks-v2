'use client';

import * as React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';

import { cn } from '@/lib/utils';

function Sheet({ children, ...props }: Dialog.DialogProps) {
  return <Dialog.Root {...props}>{children}</Dialog.Root>;
}

const SheetTrigger = Dialog.Trigger;

function SheetContent({
  className,
  children,
  title,
  description,
  ...props
}: React.ComponentProps<typeof Dialog.Content> & {
  title: string;
  description?: string;
}) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 data-[state=open]:animate-in data-[state=closed]:animate-out" />
      <Dialog.Content
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex w-[min(20rem,90vw)] flex-col gap-4 border-l border-border bg-card p-5 shadow-xl',
          'focus:outline-none',
          className,
        )}
        {...props}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <Dialog.Title className="text-base font-semibold tracking-tight">{title}</Dialog.Title>
            {description ? (
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">{description}</Dialog.Description>
            ) : (
              <Dialog.Description className="sr-only">Site navigation</Dialog.Description>
            )}
          </div>
          <Dialog.Close
            aria-label="Close menu"
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="h-5 w-5" />
          </Dialog.Close>
        </div>
        {children}
      </Dialog.Content>
    </Dialog.Portal>
  );
}

export { Sheet, SheetTrigger, SheetContent };
