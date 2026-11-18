'use client';

import { useState } from 'react';

import type { OutcomeMeta, ScopeKey, Top10Row } from '@/lib/types';

const SCOPES: { key: ScopeKey; label: string }[] = [
  { key: 'home', label: 'Home only' },
  { key: 'away', label: 'Away only' },
  { key: 'last10', label: 'Last 10' },
];

type Props = {
  outcomes: OutcomeMeta[];
  top10: Record<string, Partial<Record<ScopeKey, Top10Row[]>>>;
};

export default function OutcomeSelector({ outcomes, top10 }: Props) {
  const [selected, setSelected] = useState('tg_3plus');
  const groups = Array.from(new Set(outcomes.map((outcome) => outcome.group)));
  const rows = top10[selected] ?? {};

  return (
    <section>
      <div className="controls">
        <label htmlFor="outcome-select">Outcome</label>
        <select
          id="outcome-select"
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
        >
          {groups.map((group) => (
            <optgroup key={group} label={group}>
              {outcomes
                .filter((outcome) => outcome.group === group)
                .map((outcome) => (
                  <option key={outcome.id} value={outcome.id}>
                    {outcome.label}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
        <span className="sub">ranked by Wilson lower bound · minimum n = 5</span>
      </div>

      <div className="grid-3">
        {SCOPES.map((scope) => {
          const list = rows[scope.key] ?? [];
          return (
            <div key={scope.key}>
              <h3 className="scope-title">{scope.label}</h3>
              {list.length === 0 ? (
                <p className="empty">No team reaches n = 5 for this outcome yet.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Team</th>
                        <th>Rate</th>
                        <th>n</th>
                        <th>95% CI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((row, index) => (
                        <tr key={row.team}>
                          <td className="rank">{index + 1}</td>
                          <td>{row.team}</td>
                          <td className="rate">{(row.rate * 100).toFixed(1)}%</td>
                          <td className="num">{row.n}</td>
                          <td className="num sub">
                            {(row.lo * 100).toFixed(1)}–{(row.hi * 100).toFixed(1)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
