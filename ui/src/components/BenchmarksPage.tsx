// Benchmarks page showing GAIA benchmark results

import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { TracesModal } from '@/components/TracesModal';
import { cn } from '@/lib/utils';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList } from 'recharts';

type SortColumn = 'rank' | 'overall' | 'l1' | 'l2' | 'l3' | 'cost';
type SortDirection = 'asc' | 'desc';

// Benchmark data from gaia_results/best_runs/SUMMARY.md
const MODELS = [
  {
    id: 'gpt-5-mini',
    model: 'GPT-5-mini',
    provider: 'OpenAI',
    date: 'January 31, 2026',
    totalQuestions: 127,
    totalCorrect: 64,
    overallAccuracy: 50.4,
    estimatedCost: 8,
    costPerQuestion: 0.065,
    isDeployed: false,
    levels: [
      { level: 1, accuracy: 66.7, questions: 42, correct: 28 },
      { level: 2, accuracy: 45.5, questions: 66, correct: 30 },
      { level: 3, accuracy: 31.6, questions: 19, correct: 6 },
    ],
  },
  {
    id: 'gpt-oss-120b',
    model: 'gpt-oss-120b',
    provider: 'DeepInfra',
    date: 'January 21-22, 2026',
    totalQuestions: 127,
    totalCorrect: 58,
    overallAccuracy: 45.7,
    estimatedCost: 4,
    costPerQuestion: 0.031,
    isDeployed: true,
    levels: [
      { level: 1, accuracy: 64.3, questions: 42, correct: 27 },
      { level: 2, accuracy: 37.9, questions: 66, correct: 25 },
      { level: 3, accuracy: 31.6, questions: 19, correct: 6 },
    ],
  },
];

// HAL Princeton GAIA Leaderboard data (January 2026)
// Source: https://hal.cs.princeton.edu/gaia
const COMPARISON_DATA = [
  { rank: 1, system: 'HAL + Claude Sonnet 4.5', overall: 74.55, l1: 82.07, l2: 72.68, l3: 65.39, cost: 178 },
  { rank: 2, system: 'HAL + Claude Sonnet 4.5 High', overall: 70.91, l1: 77.36, l2: 74.42, l3: 46.15, cost: 180 },
  { rank: 3, system: 'HAL + Claude Opus 4.1 High', overall: 68.48, l1: 71.70, l2: 70.93, l3: 53.85, cost: 562 },
  { rank: 4, system: 'HAL + Claude Opus 4 High', overall: 64.85, l1: 71.70, l2: 67.44, l3: 42.31, cost: 666 },
  { rank: 5, system: 'HAL + Claude-3.7 Sonnet High', overall: 64.24, l1: 67.92, l2: 63.95, l3: 57.69, cost: 122 },
  { rank: 6, system: 'HAL + Claude Opus 4.1', overall: 64.24, l1: 71.70, l2: 66.28, l3: 42.31, cost: 642 },
  { rank: 7, system: 'HF + GPT-5 Medium', overall: 62.80, l1: 73.58, l2: 62.79, l3: 38.46, cost: 360 },
  { rank: 8, system: 'HAL + GPT-5 Medium', overall: 59.39, l1: 67.92, l2: 58.14, l3: 46.15, cost: 105 },
  { rank: 9, system: 'HAL + o4-mini Low', overall: 58.18, l1: 71.70, l2: 51.16, l3: 53.85, cost: 73 },
  { rank: 10, system: 'HF + Claude Opus 4', overall: 57.58, l1: 66.04, l2: 56.98, l3: 42.31, cost: 1686 },
  { rank: 11, system: 'HAL + Claude-3.7 Sonnet', overall: 56.36, l1: 62.26, l2: 55.81, l3: 46.15, cost: 131 },
  { rank: 12, system: 'HAL + Claude Haiku 4.5', overall: 56.36, l1: 62.26, l2: 51.16, l3: 61.54, cost: 131 },
  { rank: 13, system: 'HF + o4-mini High', overall: 55.76, l1: 69.81, l2: 51.16, l3: 42.31, cost: 185 },
  { rank: 14, system: 'HAL + o4-mini High', overall: 54.55, l1: 60.38, l2: 53.49, l3: 46.15, cost: 59 },
  { rank: 15, system: 'HF + GPT-4.1', overall: 50.30, l1: 58.49, l2: 50.00, l3: 34.62, cost: 110 },
  { rank: '~15', system: 'This Agent (GPT-5-mini)', overall: 50.4, l1: 66.7, l2: 45.5, l3: 31.6, cost: 8, isOurs: true },
  { rank: 16, system: 'HAL + GPT-4.1', overall: 49.70, l1: 52.83, l2: 55.81, l3: 23.08, cost: 74 },
  { rank: 17, system: 'HF + o4-mini Low', overall: 47.88, l1: 58.49, l2: 47.67, l3: 26.92, cost: 81 },
  { rank: '~18', system: 'This Agent (gpt-oss-120b)', overall: 45.7, l1: 64.3, l2: 37.9, l3: 31.6, cost: 4, isOurs: true },
  { rank: 18, system: 'HF + Claude-3.7 Sonnet', overall: 36.97, l1: 39.62, l2: 39.53, l3: 23.08, cost: 415 },
  { rank: 19, system: 'HF + Claude-3.7 Sonnet High', overall: 35.76, l1: 45.28, l2: 33.72, l3: 23.08, cost: 114 },
  { rank: 20, system: 'HAL + Gemini 2.0 Flash', overall: 32.73, l1: 43.40, l2: 32.56, l3: 11.54, cost: 8 },
  { rank: 21, system: 'HF + o3 Medium', overall: 32.73, l1: 39.62, l2: 31.40, l3: 23.08, cost: 136 },
  { rank: 22, system: 'HF + Claude Sonnet 4.5', overall: 30.91, l1: 37.74, l2: 31.40, l3: 15.38, cost: 452 },
  { rank: 23, system: 'HF + Claude Sonnet 4.5 High', overall: 30.91, l1: 39.62, l2: 27.91, l3: 23.08, cost: 535 },
  { rank: 24, system: 'HAL + DeepSeek R1', overall: 30.30, l1: 43.40, l2: 27.91, l3: 11.54, cost: 73 },
  { rank: 25, system: 'HAL + Claude Opus 4', overall: 30.30, l1: 33.96, l2: 27.91, l3: 30.77, cost: 273 },
  { rank: 26, system: 'HAL + DeepSeek V3', overall: 29.39, l1: 38.68, l2: 31.97, l3: 1.93, cost: 17 },
  { rank: 27, system: 'HF + DeepSeek V3', overall: 28.48, l1: 35.85, l2: 30.23, l3: 7.69, cost: 77 },
  { rank: 28, system: 'HF + Claude Opus 4.1', overall: 28.48, l1: 41.51, l2: 24.42, l3: 15.38, cost: 1307 },
  { rank: 29, system: 'HAL + o3 Medium', overall: 28.48, l1: 37.74, l2: 26.74, l3: 15.38, cost: 2829 },
  { rank: 30, system: 'HF + Claude Opus 4.1 High', overall: 25.45, l1: 35.85, l2: 23.26, l3: 11.54, cost: 1474 },
  { rank: 31, system: 'HF + DeepSeek R1', overall: 24.85, l1: 30.19, l2: 24.42, l3: 15.38, cost: 143 },
  { rank: 32, system: 'HF + Gemini 2.0 Flash', overall: 19.39, l1: 24.53, l2: 19.77, l3: 7.69, cost: 19 },
];

const bestModel = MODELS[0]; // GPT-5-mini (best results)

export function BenchmarksPage() {
  const navigate = useNavigate();
  const [tracesModalOpen, setTracesModalOpen] = useState(false);
  const [sortColumn, setSortColumn] = useState<SortColumn>('cost');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const mobileBreakpoint = 768;
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' && window.innerWidth < mobileBreakpoint);
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < mobileBreakpoint);
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, [mobileBreakpoint]);

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection(column === 'rank' || column === 'cost' ? 'asc' : 'desc');
    }
  };

  const getRankNumber = (rank: number | string): number => {
    return typeof rank === 'string' ? parseFloat(rank.replace('~', '')) : rank;
  };

  const sortedData = useMemo(() => {
    return [...COMPARISON_DATA].sort((a, b) => {
      let aVal: number;
      let bVal: number;
      if (sortColumn === 'rank') {
        aVal = getRankNumber(a.rank);
        bVal = getRankNumber(b.rank);
      } else {
        aVal = a[sortColumn];
        bVal = b[sortColumn];
      }
      return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
    });
  }, [sortColumn, sortDirection]);

  const defaultVisible = 8;
  const visibleData = useMemo(() => {
    if (showAll) return sortedData;
    return sortedData.filter((row, i) => row.isOurs || i < defaultVisible);
  }, [sortedData, showAll]);

  const SortHeader = ({ column, label }: { column: SortColumn; label: string }) => (
    <th
      className="text-right py-2 px-3 font-normal cursor-pointer hover:text-zinc-300 select-none text-zinc-500"
      onClick={() => handleSort(column)}
    >
      <span className="inline-flex items-center justify-end gap-1">
        {label}
        {sortColumn === column ? (
          sortDirection === 'asc' ? ' ↑' : ' ↓'
        ) : ''}
      </span>
    </th>
  );

  return (
    <div className="h-screen flex flex-col bg-zinc-950">
      {/* Header */}
      <header className="border-b border-zinc-800 flex-shrink-0">
        <div className="max-w-6xl mx-auto px-3 sm:px-4 py-2 flex items-center justify-between font-mono text-xs">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/conversations')}
              className="text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              [back]
            </button>
            <span className="text-zinc-600">benchmarks · gaia</span>
          </div>
          <button
            onClick={() => navigate('/conversations')}
            className="text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            [try agent]
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-3 sm:px-4 py-4 sm:py-6 md:py-8 space-y-6 sm:space-y-8 font-mono">

        {/* Hero Stats */}
        <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="border border-zinc-800 p-4">
            <p className="text-xs text-zinc-600 mb-1">best accuracy</p>
            <p className="text-2xl text-zinc-100">{bestModel.overallAccuracy}%</p>
            <p className="text-xs text-zinc-500 mt-2">
              {bestModel.totalCorrect}/{bestModel.totalQuestions} correct · {bestModel.model}
            </p>
            <p className="text-xs text-zinc-600 mt-1">
              L1: {bestModel.levels[0].accuracy}% · L2: {bestModel.levels[1].accuracy}% · L3: {bestModel.levels[2].accuracy}%
            </p>
          </div>
          <div className="border border-zinc-800 p-4">
            <p className="text-xs text-zinc-600 mb-1">cost efficiency</p>
            <p className="text-2xl text-zinc-100">$4-8</p>
            <p className="text-xs text-zinc-500 mt-2">
              per full evaluation (127 questions)
            </p>
            <p className="text-xs text-zinc-600 mt-1">
              10-100x cheaper than frontier systems
            </p>
          </div>
        </section>

        {/* Results by Level */}
        <section>
          <p className="text-xs text-zinc-500 mb-3">─── results by difficulty level ───</p>
          <p className="text-xs text-zinc-600 mb-4">
            127 questions from the validation set (no file attachments). Same scaffold, two LLMs.
          </p>

          {/* Desktop table */}
          <div className="hidden md:block border border-zinc-800 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left py-2 px-3 font-normal text-zinc-500">level</th>
                  {MODELS.map((m) => (
                    <th key={m.id} className="text-right py-2 px-3 font-normal text-zinc-500">
                      {m.model}{m.isDeployed ? ' *' : ''}
                    </th>
                  ))}
                  <th className="text-right py-2 px-3 font-normal text-zinc-500">n</th>
                </tr>
              </thead>
              <tbody>
                {[0, 1, 2].map((i) => (
                  <tr key={i} className="border-b border-zinc-800 last:border-0 hover:bg-zinc-900">
                    <td className="py-2 px-3 text-zinc-400">L{i + 1}</td>
                    {MODELS.map((m) => (
                      <td key={m.id} className="text-right py-2 px-3">
                        <span className="text-zinc-200">{m.levels[i].accuracy.toFixed(1)}%</span>
                        <span className="text-zinc-600 ml-1">({m.levels[i].correct})</span>
                      </td>
                    ))}
                    <td className="text-right py-2 px-3 text-zinc-600">
                      {MODELS[0].levels[i].questions}
                    </td>
                  </tr>
                ))}
                <tr className="bg-zinc-900/50">
                  <td className="py-2 px-3 text-zinc-300">total</td>
                  {MODELS.map((m) => (
                    <td key={m.id} className="text-right py-2 px-3">
                      <span className="text-zinc-100">{m.overallAccuracy.toFixed(1)}%</span>
                      <span className="text-zinc-600 ml-1">({m.totalCorrect})</span>
                    </td>
                  ))}
                  <td className="text-right py-2 px-3 text-zinc-600">127</td>
                </tr>
                <tr className="border-t border-zinc-800">
                  <td className="py-2 px-3 text-zinc-600">cost</td>
                  {MODELS.map((m) => (
                    <td key={m.id} className="text-right py-2 px-3 text-zinc-500">
                      ${m.estimatedCost}
                    </td>
                  ))}
                  <td className="text-right py-2 px-3 text-zinc-700">total</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {MODELS.map((m) => (
              <div key={m.id} className="border border-zinc-800 p-3 space-y-2">
                <p className="text-xs text-zinc-400">
                  {m.model}{m.isDeployed ? ' (deployed)' : ''}
                </p>
                {m.levels.map((level) => (
                  <div key={level.level} className="flex items-center justify-between text-xs">
                    <span className="text-zinc-600">L{level.level}</span>
                    <span>
                      <span className="text-zinc-200">{level.accuracy.toFixed(1)}%</span>
                      <span className="text-zinc-600 ml-1">{level.correct}/{level.questions}</span>
                    </span>
                  </div>
                ))}
                <div className="flex items-center justify-between text-xs pt-1 border-t border-zinc-800">
                  <span className="text-zinc-400">total</span>
                  <span>
                    <span className="text-zinc-100">{m.overallAccuracy.toFixed(1)}%</span>
                    <span className="text-zinc-600 ml-2">${m.estimatedCost}</span>
                  </span>
                </div>
              </div>
            ))}
          </div>

          <p className="text-xs text-zinc-700 mt-2">* deployed model</p>
        </section>

        {/* Accuracy vs Cost Chart */}
        <section>
          <p className="text-xs text-zinc-500 mb-3">─── accuracy vs cost ───</p>
          <p className="text-xs text-zinc-600 mb-4">
            this scaffold compared to HAL and HuggingFace agents on the GAIA leaderboard.
          </p>
          <div className="border border-zinc-800 p-4">
            <div className="h-[300px] sm:h-[400px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={isMobile ? { top: 10, right: 15, bottom: 20, left: 5 } : { top: 20, right: 30, bottom: 60, left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    type="number"
                    dataKey="cost"
                    name="Cost"
                    scale="log"
                    domain={[1, 3000]}
                    ticks={isMobile ? [5, 50, 500] : [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500]}
                    tickFormatter={(value) => `$${value}`}
                    tick={{ fontSize: isMobile ? 10 : 11, fill: '#71717a', fontFamily: 'IBM Plex Mono, monospace' }}
                    label={isMobile ? undefined : { value: 'cost ($)', position: 'bottom', offset: 40, fill: '#71717a', fontFamily: 'IBM Plex Mono, monospace', fontSize: 11 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="overall"
                    name="Accuracy"
                    domain={[15, 80]}
                    tickFormatter={(value) => `${value}%`}
                    tick={{ fontSize: isMobile ? 10 : 11, fill: '#71717a', fontFamily: 'IBM Plex Mono, monospace' }}
                    label={isMobile ? undefined : { value: 'accuracy (%)', angle: -90, position: 'insideLeft', offset: 10, fill: '#71717a', fontFamily: 'IBM Plex Mono, monospace', fontSize: 11 }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-zinc-900 border border-zinc-700 p-2 text-xs font-mono">
                            <p className="text-zinc-200">{data.system}</p>
                            <p className="text-zinc-500">{data.overall}% · ${data.cost}</p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Scatter
                    name="Other Systems"
                    data={COMPARISON_DATA.filter(d => !d.isOurs)}
                    fill="#52525b"
                    fillOpacity={0.6}
                  >
                    <LabelList
                      dataKey="system"
                      position="top"
                      offset={8}
                      className="text-[10px] fill-zinc-600"
                      formatter={(value) => {
                        const v = String(value || '');
                        if (v.includes('Claude Sonnet 4.5') && !v.includes('High') && v.startsWith('HAL')) return isMobile ? 'Sonnet 4.5' : 'Claude Sonnet 4.5';
                        if (v.includes('GPT-5 Medium') && v.startsWith('HAL')) return isMobile ? 'GPT-5 Med' : 'GPT-5 Medium';
                        if (v.includes('o4-mini Low') && v.startsWith('HAL')) return 'o4-mini';
                        if (v === 'HAL + o3 Medium') return isMobile ? 'o3 $2.8k' : 'o3 Medium ($2.8k)';
                        if (v === 'HAL + Claude Opus 4') return isMobile ? 'Opus 4' : 'Claude Opus 4';
                        if (v.includes('Gemini 2.0 Flash') && v.startsWith('HAL')) return isMobile ? 'Gemini' : 'Gemini Flash';
                        if (isMobile) return '';
                        if (v === 'HF + Claude Opus 4.1 High') return 'Claude Opus 4.1 High';
                        if (v === 'HF + Claude Opus 4.1') return 'Claude Opus 4.1';
                        if (v === 'HF + Claude-3.7 Sonnet') return 'Claude-3.7 Sonnet';
                        if (v === 'HAL + DeepSeek R1') return 'DeepSeek R1';
                        return '';
                      }}
                    />
                  </Scatter>
                  <Scatter
                    name="Our Systems"
                    data={COMPARISON_DATA.filter(d => d.isOurs)}
                    fill="#d4d4d8"
                    fillOpacity={1}
                    shape={(props: { cx?: number; cy?: number }) => (
                      <circle cx={props.cx} cy={props.cy} r={8} fill="#d4d4d8" stroke="#a1a1aa" strokeWidth={2} />
                    )}
                  >
                    <LabelList
                      dataKey="system"
                      position={isMobile ? 'top' : 'right'}
                      offset={isMobile ? 8 : 12}
                      className={isMobile ? 'text-[10px] fill-zinc-200 font-medium' : 'text-xs fill-zinc-200 font-medium'}
                      formatter={(value) => {
                        const v = String(value || '');
                        if (isMobile) {
                          if (v.includes('GPT-5-mini')) return 'GPT-5-mini';
                          if (v.includes('gpt-oss-120b')) return 'gpt-oss-120b';
                          return 'Ours';
                        }
                        if (v.includes('GPT-5-mini')) return 'This Scaffold (GPT-5-mini)';
                        if (v.includes('gpt-oss-120b')) return 'This Scaffold (gpt-oss-120b)';
                        return 'This Scaffold';
                      }}
                    />
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>

        {/* Comparison with Top Systems */}
        <section>
          <p className="text-xs text-zinc-500 mb-3">─── leaderboard comparison ───</p>
          <p className="text-xs text-zinc-600 mb-4">
            data from{' '}
            <a
              href="https://hal.cs.princeton.edu/gaia"
              target="_blank"
              rel="noopener noreferrer"
              className="text-zinc-500 hover:text-zinc-300"
            >
              hal.cs.princeton.edu/gaia
            </a>
            {' '}(jan 2026). this agent is not on the official leaderboard — results are self-evaluated on the same validation set.
          </p>

          {/* Desktop table */}
          <div className="hidden lg:block border border-zinc-800 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th
                    className="text-center py-2 px-2 font-normal w-10 cursor-pointer hover:text-zinc-300 select-none text-zinc-500"
                    onClick={() => handleSort('rank')}
                  >
                    #{sortColumn === 'rank' ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ''}
                  </th>
                  <th className="text-left py-2 px-3 font-normal text-zinc-500">system</th>
                  <SortHeader column="overall" label="overall" />
                  <SortHeader column="l1" label="L1" />
                  <SortHeader column="l2" label="L2" />
                  <SortHeader column="l3" label="L3" />
                  <SortHeader column="cost" label="cost" />
                </tr>
              </thead>
              <tbody>
                {visibleData.map((row) => (
                  <tr
                    key={row.system}
                    className={cn(
                      'border-b border-zinc-800 last:border-0 hover:bg-zinc-900',
                      row.isOurs && 'bg-zinc-800/50'
                    )}
                  >
                    <td className="text-center py-2 px-2 text-zinc-600">{row.rank}</td>
                    <td className={cn('py-2 px-3', row.isOurs ? 'text-zinc-200' : 'text-zinc-400')}>
                      {row.system}
                    </td>
                    <td className="text-right py-2 px-3 text-zinc-300">{row.overall}%</td>
                    <td className="text-right py-2 px-3 text-zinc-500">{row.l1}%</td>
                    <td className="text-right py-2 px-3 text-zinc-500">{row.l2}%</td>
                    <td className="text-right py-2 px-3 text-zinc-500">{row.l3}%</td>
                    <td className={cn('text-right py-2 px-3', row.isOurs ? 'text-zinc-200' : 'text-zinc-600')}>
                      ${row.cost}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!showAll && sortedData.length > defaultVisible && (
              <button
                onClick={() => setShowAll(true)}
                className="text-xs text-zinc-600 hover:text-zinc-400 w-full text-center py-2 border-t border-zinc-800"
              >
                [show all]
              </button>
            )}
          </div>

          {/* Tablet horizontal scroll */}
          <div className="hidden md:block lg:hidden border border-zinc-800 overflow-x-auto">
            <table className="w-full text-xs min-w-[650px]">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th
                    className="text-center py-2 px-2 font-normal w-10 cursor-pointer hover:text-zinc-300 select-none text-zinc-500"
                    onClick={() => handleSort('rank')}
                  >
                    #{sortColumn === 'rank' ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ''}
                  </th>
                  <th className="text-left py-2 px-3 font-normal text-zinc-500">system</th>
                  <SortHeader column="overall" label="overall" />
                  <SortHeader column="l1" label="L1" />
                  <SortHeader column="l2" label="L2" />
                  <SortHeader column="l3" label="L3" />
                  <SortHeader column="cost" label="cost" />
                </tr>
              </thead>
              <tbody>
                {visibleData.map((row) => (
                  <tr
                    key={row.system}
                    className={cn(
                      'border-b border-zinc-800 last:border-0 hover:bg-zinc-900',
                      row.isOurs && 'bg-zinc-800/50'
                    )}
                  >
                    <td className="text-center py-2 px-2 text-zinc-600">{row.rank}</td>
                    <td className={cn('py-2 px-3', row.isOurs ? 'text-zinc-200' : 'text-zinc-400')}>
                      {row.system}
                    </td>
                    <td className="text-right py-2 px-3 text-zinc-300">{row.overall}%</td>
                    <td className="text-right py-2 px-3 text-zinc-500">{row.l1}%</td>
                    <td className="text-right py-2 px-3 text-zinc-500">{row.l2}%</td>
                    <td className="text-right py-2 px-3 text-zinc-500">{row.l3}%</td>
                    <td className={cn('text-right py-2 px-3', row.isOurs ? 'text-zinc-200' : 'text-zinc-600')}>
                      ${row.cost}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!showAll && sortedData.length > defaultVisible && (
              <button
                onClick={() => setShowAll(true)}
                className="text-xs text-zinc-600 hover:text-zinc-400 w-full text-center py-2 border-t border-zinc-800"
              >
                [show all]
              </button>
            )}
          </div>

          {/* Mobile compact list */}
          <div className="md:hidden">
            <div className="flex items-center gap-2 text-xs mb-2">
              <span className="text-zinc-600">sort:</span>
              <select
                value={`${sortColumn}-${sortDirection}`}
                onChange={(e) => {
                  const [col, dir] = e.target.value.split('-') as [SortColumn, SortDirection];
                  setSortColumn(col);
                  setSortDirection(dir);
                }}
                className="border border-zinc-800 px-2 py-1 text-xs bg-zinc-950 text-zinc-400 font-mono"
              >
                <option value="cost-asc">cost (lowest)</option>
                <option value="rank-asc">rank (best)</option>
                <option value="overall-desc">accuracy (highest)</option>
              </select>
            </div>
            <div className="border border-zinc-800">
              <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-zinc-600 border-b border-zinc-800">
                <span className="w-5 shrink-0">#</span>
                <span className="flex-1">system</span>
                <span className="w-12 text-right shrink-0">score</span>
                <span className="w-10 text-right shrink-0">cost</span>
              </div>
              {visibleData.map((row) => (
                <div
                  key={row.system}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 text-xs border-b border-zinc-800 last:border-0',
                    row.isOurs && 'bg-zinc-800/50'
                  )}
                >
                  <span className="text-[10px] text-zinc-600 w-5 shrink-0">{row.rank}</span>
                  <span className={cn('flex-1 truncate', row.isOurs ? 'text-zinc-200' : 'text-zinc-500')}>
                    {row.system.replace(/^(HAL|HF) \+ /, '')}
                  </span>
                  <span className="text-zinc-300 w-12 text-right shrink-0">{row.overall}%</span>
                  <span className={cn('text-xs w-10 text-right shrink-0', row.isOurs ? 'text-zinc-200' : 'text-zinc-600')}>
                    ${row.cost}
                  </span>
                </div>
              ))}
              {!showAll && sortedData.length > defaultVisible && (
                <button
                  onClick={() => setShowAll(true)}
                  className="text-xs text-zinc-600 hover:text-zinc-400 w-full text-center py-2 border-t border-zinc-800"
                >
                  [show all]
                </button>
              )}
            </div>
          </div>
        </section>

        {/* About + Takeaways */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-zinc-800 p-4">
            <p className="text-xs text-zinc-500 mb-3">about this agent</p>
            <p className="text-xs text-zinc-600 mb-3">
              single-agent scaffold with multi-step planning, tool orchestration, and execution tracing.
            </p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-600">
              <span>web_search</span>
              <span>content_extraction</span>
              <span>python_execution</span>
            </div>
          </div>
          <div className="border border-zinc-800 p-4">
            <p className="text-xs text-zinc-500 mb-3">
              about gaia{' '}
              <a
                href="https://arxiv.org/abs/2311.12983"
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-600 hover:text-zinc-400"
              >
                [paper]
              </a>
            </p>
            <p className="text-xs text-zinc-600 mb-3">
              real-world questions requiring reasoning, web browsing, and tool use.
              92% human accuracy, challenging for most AIs.
            </p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-600">
              <span>reasoning</span>
              <span>web_browsing</span>
              <span>tool_use</span>
              <span>multi_step</span>
            </div>
          </div>
        </section>

        {/* Takeaways */}
        <section className="border border-zinc-800 p-4">
          <p className="text-xs text-zinc-500 mb-3">─── takeaways ───</p>
          <div className="space-y-2 text-xs">
            <p className="text-zinc-500">
              <span className="text-zinc-600 mr-2">[cost]</span>
              $4-8 for 127 questions across both models
            </p>
            <p className="text-zinc-500">
              <span className="text-zinc-600 mr-2">[models]</span>
              +4.7% accuracy delta between open-weight and GPT-5-mini on the same scaffold
            </p>
            <p className="text-zinc-500">
              <span className="text-zinc-600 mr-2">[levels]</span>
              L1 and L3 within 3%; L2 shows the largest gap (+7.6%)
            </p>
            <p className="text-zinc-500">
              <span className="text-zinc-600 mr-2">[traces]</span>
              evaluation traces with aggregate stats per run.{' '}
              <button
                onClick={() => setTracesModalOpen(true)}
                className="text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                [view traces]
              </button>
            </p>
          </div>
        </section>

        {/* Footer */}
        <div className="text-center text-xs text-zinc-700 pb-8 space-y-1">
          <p>{MODELS.map(m => m.model).join(' · ')} · january 2026</p>
          <p>* questions with file attachments excluded</p>
          <p>
            <a
              href="https://hal.cs.princeton.edu/gaia"
              target="_blank"
              rel="noopener noreferrer"
              className="text-zinc-600 hover:text-zinc-400"
            >
              hal.cs.princeton.edu/gaia
            </a>
          </p>
        </div>
        </div>
      </main>

      <TracesModal open={tracesModalOpen} onOpenChange={setTracesModalOpen} />
    </div>
  );
}
