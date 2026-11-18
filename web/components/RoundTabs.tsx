'use client';

import RoundList from '@/components/RoundList';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { RoundDocument, RoundView } from '@/lib/types';

const ORDER = ['most_likely', 'stand_out'] as const;

export default function RoundTabs({ round }: { round: RoundDocument }) {
  const views: Record<string, RoundView> =
    round.views ?? {
      most_likely: { label: 'Most likely', picks: round.picks ?? [], hits: 0, settled_count: 0 },
    };

  const available = ORDER.filter((key) => views[key]);
  if (available.length === 0) {
    return <p className="text-sm text-muted-foreground">No picks in this round.</p>;
  }

  return (
    <Tabs defaultValue={available[0]}>
      <TabsList>
        {available.map((key) => (
          <TabsTrigger key={key} value={key}>
            {views[key].label} ({views[key].picks.length})
          </TabsTrigger>
        ))}
      </TabsList>
      {available.map((key) => (
        <TabsContent key={key} value={key}>
          <RoundList picks={views[key].picks} showLift={key === 'stand_out'} />
        </TabsContent>
      ))}
    </Tabs>
  );
}
