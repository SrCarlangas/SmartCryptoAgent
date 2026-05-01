import { useEffect, useRef } from 'react';
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useBotStore } from '../store/botStore';

export function PriceChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const lastTsRef = useRef<number>(0);
  const dataRef = useRef<LineData[]>([]);
  const price = useBotStore((s) => s.dashboard?.price ?? 0);
  const lastTickTs = useBotStore((s) => s.lastTickTs);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 320,
      layout: {
        background: { color: 'transparent' },
        textColor: '#cbd5e1',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      rightPriceScale: { borderColor: '#334155' },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: true,
      },
    });
    chartRef.current = chart;
    seriesRef.current = chart.addLineSeries({
      color: '#fbbf24',
      lineWidth: 2,
    });

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || price <= 0) return;
    const nowSec = Math.floor(Date.now() / 1000);
    // Garantizar timestamps estrictamente crecientes
    const time = (nowSec <= lastTsRef.current ? lastTsRef.current + 1 : nowSec) as UTCTimestamp;
    lastTsRef.current = time as number;
    const point: LineData = { time, value: price };
    dataRef.current = [...dataRef.current.slice(-299), point];
    seriesRef.current.update(point);
  }, [price, lastTickTs]);

  return (
    <div className="w-full bg-slate-900/40 border border-slate-800 rounded-lg p-2">
      <div className="text-xs text-slate-400 px-2 pb-1">
        Precio BTC en vivo (ticks acumulados)
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
