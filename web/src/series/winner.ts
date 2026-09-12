export interface WinnerBar {
  backend: string;
  fraction: number;
}

export interface WinnerSummary {
  bars: WinnerBar[];
  noRobustWinner: boolean;
}

export function winnerBars(
  ws: Record<string, number>
): WinnerSummary {
  const bars = Object.entries(ws)
    .map(([backend, fraction]) => ({ backend, fraction }))
    .sort((a, b) => b.fraction - a.fraction);
  const max = bars.length ? bars[0].fraction : 0;
  return { bars, noRobustWinner: max < 0.6 };
}
