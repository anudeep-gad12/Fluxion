// Benchmarks page showing GAIA benchmark results

import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Trophy, DollarSign, ExternalLink, FileText, Play, Globe, Code, FileSearch, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { TracesModal } from '@/components/TracesModal';
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
      // Default: rank ascending, others descending (higher is better for accuracy)
      setSortDirection(column === 'rank' || column === 'cost' ? 'asc' : 'desc');
    }
  };

  // Helper to extract numeric rank
  const getRankNumber = (rank: number | string): number => {
    return typeof rank === 'string' ? parseFloat(rank.replace('~', '')) : rank;
  };

  const sortedData = useMemo(() => {
    return [...COMPARISON_DATA].sort((a, b) => {
      let aVal: number;
      let bVal: number;

      if (sortColumn === 'rank') {
        // Handle string ranks like "~15" by extracting the number
        aVal = getRankNumber(a.rank);
        bVal = getRankNumber(b.rank);
      } else {
        aVal = a[sortColumn];
        bVal = b[sortColumn];
      }

      if (sortDirection === 'asc') {
        return aVal - bVal;
      } else {
        return bVal - aVal;
      }
    });
  }, [sortColumn, sortDirection]);

  // Show rows up to and including our systems + a few more for context, rest behind "Show more"
  const defaultVisible = 8;
  const visibleData = useMemo(() => {
    if (showAll) return sortedData;
    return sortedData.filter((row, i) => row.isOurs || i < defaultVisible);
  }, [sortedData, showAll]);

  const SortHeader = ({ column, label }: { column: SortColumn; label: string }) => (
    <th
      className="text-right py-3 px-4 font-medium cursor-pointer hover:bg-muted/50 select-none"
      onClick={() => handleSort(column)}
    >
      <div className="flex items-center justify-end gap-1">
        {label}
        {sortColumn === column ? (
          sortDirection === 'asc' ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" />
        )}
      </div>
    </th>
  );

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-slate-50 via-white to-blue-50">
      {/* Header */}
      <header className="border-b bg-white/80 backdrop-blur-sm flex-shrink-0">
        <div className="max-w-6xl mx-auto px-3 sm:px-4 py-3 sm:py-4 flex items-center gap-3 sm:gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate('/conversations')}
            className="h-11 w-11 sm:h-10 sm:w-10"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1">
            <h1 className="text-lg sm:text-xl font-bold">Benchmarks</h1>
            <p className="text-xs sm:text-sm text-muted-foreground">GAIA Benchmark Performance</p>
          </div>
          <Button
            onClick={() => navigate('/conversations')}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          >
            <Play className="h-4 w-4" />
            <span className="hidden sm:inline">Try the Agent</span>
            <span className="sm:hidden">Try it</span>
          </Button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-3 sm:px-4 py-4 sm:py-6 md:py-8 space-y-6 sm:space-y-8">
        {/* Hero Stats */}
        <section className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
          <Card className="bg-gradient-to-br from-amber-50 to-orange-50 border-amber-200">
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-2">
                <Trophy className="h-4 w-4 text-amber-600" />
                Best Accuracy
              </CardDescription>
              <CardTitle className="text-3xl sm:text-4xl text-amber-700">{bestModel.overallAccuracy}%</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs sm:text-sm text-amber-800">
                {bestModel.totalCorrect}/{bestModel.totalQuestions} correct with {bestModel.model}
              </p>
              <p className="text-xs text-amber-600 mt-1">
                L1: {bestModel.levels[0].accuracy}% &middot; L2: {bestModel.levels[1].accuracy}% &middot; L3: {bestModel.levels[2].accuracy}%
              </p>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-emerald-50 to-green-50 border-emerald-200">
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-emerald-600" />
                Cost Efficiency
              </CardDescription>
              <CardTitle className="text-3xl sm:text-4xl text-emerald-700">$4-8</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs sm:text-sm text-emerald-800">
                Per full evaluation (127 questions)
              </p>
              <p className="text-xs text-emerald-600 mt-1">
                10-100x cheaper than frontier systems
              </p>
            </CardContent>
          </Card>
        </section>

        {/* Results by Level */}
        <Card>
          <CardHeader>
            <CardTitle>Results by Difficulty Level</CardTitle>
            <CardDescription>
              Evaluated on 127 questions from the validation set (no file attachments). Same scaffold, two different LLMs.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-4 font-medium">Level</th>
                    {MODELS.map((m) => (
                      <th key={m.id} className="text-right py-3 px-4 font-medium" colSpan={1}>
                        {m.model}
                        {m.isDeployed && <span className="text-xs text-muted-foreground ml-1">(deployed)</span>}
                      </th>
                    ))}
                    <th className="text-right py-3 px-4 font-medium">Questions</th>
                  </tr>
                </thead>
                <tbody>
                  {[0, 1, 2].map((i) => (
                    <tr key={i} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="py-3 px-4">
                        <span className="font-medium">Level {i + 1}</span>
                      </td>
                      {MODELS.map((m) => (
                        <td key={m.id} className="text-right py-3 px-4 font-mono">
                          <span className="font-bold text-blue-600">{m.levels[i].accuracy.toFixed(1)}%</span>
                          <span className="text-muted-foreground ml-1">({m.levels[i].correct})</span>
                        </td>
                      ))}
                      <td className="text-right py-3 px-4 font-mono text-muted-foreground">
                        {MODELS[0].levels[i].questions}
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-muted/30 font-medium">
                    <td className="py-3 px-4">Overall</td>
                    {MODELS.map((m) => (
                      <td key={m.id} className="text-right py-3 px-4 font-mono">
                        <span className="font-bold text-blue-600">{m.overallAccuracy.toFixed(1)}%</span>
                        <span className="text-muted-foreground ml-1">({m.totalCorrect})</span>
                      </td>
                    ))}
                    <td className="text-right py-3 px-4 font-mono text-muted-foreground">127</td>
                  </tr>
                  <tr className="bg-emerald-50/50">
                    <td className="py-3 px-4 text-emerald-700">Cost</td>
                    {MODELS.map((m) => (
                      <td key={m.id} className="text-right py-3 px-4 font-mono text-emerald-700 font-medium">
                        ${m.estimatedCost}
                      </td>
                    ))}
                    <td className="text-right py-3 px-4 text-xs text-emerald-600">total</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden space-y-4">
              {MODELS.map((m) => (
                <div key={m.id} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-medium">{m.model}</h4>
                    {m.isDeployed && <Badge variant="outline" className="text-xs">deployed</Badge>}
                  </div>
                  {m.levels.map((level) => (
                    <div key={level.level} className="bg-slate-50 rounded-lg p-3 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">Level {level.level}</span>
                        <span className="font-mono font-bold text-blue-600 text-sm">
                          {level.accuracy.toFixed(1)}%
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground font-mono">
                        {level.correct} / {level.questions} correct
                      </div>
                    </div>
                  ))}
                  <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Overall</span>
                      <span className="font-mono font-bold text-blue-600">
                        {m.overallAccuracy.toFixed(1)}%
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground font-mono">
                      {m.totalCorrect} / {m.totalQuestions} &middot; ${m.estimatedCost} total cost
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Accuracy vs Cost Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Accuracy vs Cost</CardTitle>
            <CardDescription>
              This scaffold (blue) compared to HAL and HuggingFace agent scaffolds on the GAIA leaderboard.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] sm:h-[400px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={isMobile ? { top: 10, right: 15, bottom: 20, left: 5 } : { top: 20, right: 30, bottom: 60, left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis
                    type="number"
                    dataKey="cost"
                    name="Cost"
                    scale="log"
                    domain={[1, 3000]}
                    ticks={isMobile ? [5, 50, 500] : [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500]}
                    tickFormatter={(value) => `$${value}`}
                    tick={{ fontSize: isMobile ? 10 : 12 }}
                    label={isMobile ? undefined : { value: 'Cost ($)', position: 'bottom', offset: 40 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="overall"
                    name="Accuracy"
                    domain={[15, 80]}
                    tickFormatter={(value) => `${value}%`}
                    tick={{ fontSize: isMobile ? 10 : 12 }}
                    label={isMobile ? undefined : { value: 'Overall Accuracy (%)', angle: -90, position: 'insideLeft', offset: 10 }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-white border rounded-lg shadow-lg p-3 text-sm">
                            <p className="font-medium">{data.system}</p>
                            <p className="text-muted-foreground">Accuracy: <span className="font-mono">{data.overall}%</span></p>
                            <p className="text-muted-foreground">Cost: <span className="font-mono">${data.cost}</span></p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  {/* Other systems */}
                  <Scatter
                    name="Other Systems"
                    data={COMPARISON_DATA.filter(d => !d.isOurs)}
                    fill="#94a3b8"
                    fillOpacity={0.6}
                  >
                    <LabelList
                      dataKey="system"
                      position="top"
                      offset={8}
                      className="text-[10px] fill-slate-500"
                      formatter={(value) => {
                        const v = String(value || '');
                        // Above us
                        if (v.includes('Claude Sonnet 4.5') && !v.includes('High') && v.startsWith('HAL')) return isMobile ? 'Sonnet 4.5' : 'Claude Sonnet 4.5';
                        if (v.includes('GPT-5 Medium') && v.startsWith('HAL')) return isMobile ? 'GPT-5 Med' : 'GPT-5 Medium';
                        if (v.includes('o4-mini Low') && v.startsWith('HAL')) return 'o4-mini';
                        // Below us — systems we beat
                        if (v === 'HAL + o3 Medium') return isMobile ? 'o3 $2.8k' : 'o3 Medium ($2.8k)';
                        if (v === 'HAL + Claude Opus 4') return isMobile ? 'Opus 4' : 'Claude Opus 4';
                        if (v.includes('Gemini 2.0 Flash') && v.startsWith('HAL')) return isMobile ? 'Gemini' : 'Gemini Flash';
                        // Desktop-only — more systems we beat
                        if (isMobile) return '';
                        if (v === 'HF + Claude Opus 4.1 High') return 'Claude Opus 4.1 High';
                        if (v === 'HF + Claude Opus 4.1') return 'Claude Opus 4.1';
                        if (v === 'HF + Claude-3.7 Sonnet') return 'Claude-3.7 Sonnet';
                        if (v === 'HAL + DeepSeek R1') return 'DeepSeek R1';
                        return '';
                      }}
                    />
                  </Scatter>
                  {/* Our systems - on top with labels */}
                  <Scatter
                    name="Our Systems"
                    data={COMPARISON_DATA.filter(d => d.isOurs)}
                    fill="#3b82f6"
                    fillOpacity={1}
                    shape={(props: { cx?: number; cy?: number }) => (
                      <circle cx={props.cx} cy={props.cy} r={8} fill="#3b82f6" stroke="#1d4ed8" strokeWidth={2} />
                    )}
                  >
                    <LabelList
                      dataKey="system"
                      position={isMobile ? 'top' : 'right'}
                      offset={isMobile ? 8 : 12}
                      className={isMobile ? 'text-[10px] fill-blue-700 font-medium' : 'text-xs fill-blue-700 font-medium'}
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
          </CardContent>
        </Card>

        {/* Comparison with Top Systems */}
        <Card>
          <CardHeader>
            <CardTitle>Comparison with Top Systems</CardTitle>
            <CardDescription>
              Leaderboard data from{' '}
              <a
                href="https://hal.cs.princeton.edu/gaia"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:underline"
              >
                HAL Princeton GAIA Leaderboard
              </a>
              {' '}(January 2026). This agent is not on the official leaderboard — results are self-evaluated on the same validation set, ranked by overall accuracy.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Desktop table */}
            <div className="hidden lg:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th
                      className="text-center py-3 px-2 font-medium w-12 cursor-pointer hover:bg-muted/50 select-none"
                      onClick={() => handleSort('rank')}
                    >
                      <div className="flex items-center justify-center gap-1">
                        #
                        {sortColumn === 'rank' ? (
                          sortDirection === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
                        ) : (
                          <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" />
                        )}
                      </div>
                    </th>
                    <th className="text-left py-3 px-4 font-medium">System</th>
                    <SortHeader column="overall" label="Overall" />
                    <SortHeader column="l1" label="L1" />
                    <SortHeader column="l2" label="L2" />
                    <SortHeader column="l3" label="L3" />
                    <SortHeader column="cost" label="Cost" />
                  </tr>
                </thead>
                <tbody>
                  {visibleData.map((row) => (
                    <tr
                      key={row.system}
                      className={`border-b last:border-0 hover:bg-muted/50 ${
                        row.isOurs ? 'bg-blue-50 font-medium' : ''
                      }`}
                    >
                      <td className="text-center py-3 px-2 text-muted-foreground font-mono text-xs">
                        {row.rank}
                      </td>
                      <td className="py-3 px-4">
                        {row.system}
                      </td>
                      <td className="text-right py-3 px-4 font-mono">{row.overall}%</td>
                      <td className="text-right py-3 px-4 font-mono">{row.l1}%</td>
                      <td className="text-right py-3 px-4 font-mono">{row.l2}%</td>
                      <td className="text-right py-3 px-4 font-mono">{row.l3}%</td>
                      <td className="text-right py-3 px-4">
                        <span className={row.isOurs ? 'text-emerald-600 font-bold' : 'text-muted-foreground'}>
                          ${row.cost}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!showAll && sortedData.length > defaultVisible && (
                <button
                  onClick={() => setShowAll(true)}
                  className="text-sm text-blue-500 hover:underline w-full text-center py-3"
                >
                  Show more
                </button>
              )}
            </div>

            {/* Tablet horizontal scroll */}
            <div className="hidden md:block lg:hidden overflow-x-auto">
              <table className="w-full text-sm min-w-[650px]">
                <thead>
                  <tr className="border-b">
                    <th
                      className="text-center py-3 px-2 font-medium w-12 cursor-pointer hover:bg-muted/50 select-none"
                      onClick={() => handleSort('rank')}
                    >
                      <div className="flex items-center justify-center gap-1">
                        #
                        {sortColumn === 'rank' ? (
                          sortDirection === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
                        ) : (
                          <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" />
                        )}
                      </div>
                    </th>
                    <th className="text-left py-3 px-4 font-medium">System</th>
                    <SortHeader column="overall" label="Overall" />
                    <SortHeader column="l1" label="L1" />
                    <SortHeader column="l2" label="L2" />
                    <SortHeader column="l3" label="L3" />
                    <SortHeader column="cost" label="Cost" />
                  </tr>
                </thead>
                <tbody>
                  {visibleData.map((row) => (
                    <tr
                      key={row.system}
                      className={`border-b last:border-0 hover:bg-muted/50 ${
                        row.isOurs ? 'bg-blue-50 font-medium' : ''
                      }`}
                    >
                      <td className="text-center py-3 px-2 text-muted-foreground font-mono text-xs">
                        {row.rank}
                      </td>
                      <td className="py-3 px-4">
                        {row.system}
                      </td>
                      <td className="text-right py-3 px-4 font-mono">{row.overall}%</td>
                      <td className="text-right py-3 px-4 font-mono">{row.l1}%</td>
                      <td className="text-right py-3 px-4 font-mono">{row.l2}%</td>
                      <td className="text-right py-3 px-4 font-mono">{row.l3}%</td>
                      <td className="text-right py-3 px-4">
                        <span className={row.isOurs ? 'text-emerald-600 font-bold' : 'text-muted-foreground'}>
                          ${row.cost}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!showAll && sortedData.length > defaultVisible && (
                <button
                  onClick={() => setShowAll(true)}
                  className="text-sm text-blue-500 hover:underline w-full text-center py-3"
                >
                  Show more
                </button>
              )}
            </div>

            {/* Mobile compact list */}
            <div className="md:hidden space-y-0.5">
              {/* Mobile sort selector */}
              <div className="flex items-center gap-2 text-sm mb-2">
                <span className="text-muted-foreground">Sort by:</span>
                <select
                  value={`${sortColumn}-${sortDirection}`}
                  onChange={(e) => {
                    const [col, dir] = e.target.value.split('-') as [SortColumn, SortDirection];
                    setSortColumn(col);
                    setSortDirection(dir);
                  }}
                  className="border rounded px-2 py-1 text-sm bg-white"
                >
                  <option value="cost-asc">Cost (lowest)</option>
                  <option value="rank-asc">Rank (best first)</option>
                  <option value="overall-desc">Overall % (highest)</option>
                </select>
              </div>
              {/* Column headers */}
              <div className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] text-muted-foreground font-medium border-b">
                <span className="w-6 shrink-0">#</span>
                <span className="flex-1">System</span>
                <span className="w-14 text-right shrink-0">Score</span>
                <span className="w-10 text-right shrink-0">Cost</span>
              </div>
              {visibleData.map((row) => (
                <div
                  key={row.system}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded text-[13px] ${
                    row.isOurs
                      ? 'bg-blue-50 border border-blue-200 font-medium'
                      : ''
                  }`}
                >
                  <span className="text-[11px] text-muted-foreground font-mono w-6 shrink-0">{row.rank}</span>
                  <span className="flex-1 truncate">
                    {row.system.replace(/^(HAL|HF) \+ /, '')}
                  </span>
                  <span className="font-mono font-bold text-[13px] w-14 text-right shrink-0">{row.overall}%</span>
                  <span className={`font-mono text-xs w-10 text-right shrink-0 ${
                    row.isOurs ? 'text-emerald-600 font-bold' : 'text-muted-foreground'
                  }`}>${row.cost}</span>
                </div>
              ))}
              {!showAll && sortedData.length > defaultVisible && (
                <button
                  onClick={() => setShowAll(true)}
                  className="text-sm text-blue-500 hover:underline w-full text-center py-2"
                >
                  Show more
                </button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* About Section - Agent + GAIA combined */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card className="border-indigo-200 bg-gradient-to-br from-indigo-50/50 to-slate-50">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">About This Agent</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Single-agent scaffold with multi-step planning, tool orchestration,
                and execution tracing.
              </p>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline" className="border-indigo-200 text-indigo-700">
                  <Globe className="h-3 w-3 mr-1" />
                  Web Search
                </Badge>
                <Badge variant="outline" className="border-indigo-200 text-indigo-700">
                  <FileSearch className="h-3 w-3 mr-1" />
                  Content Extraction
                </Badge>
                <Badge variant="outline" className="border-indigo-200 text-indigo-700">
                  <Code className="h-3 w-3 mr-1" />
                  Python Execution
                </Badge>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                About GAIA Benchmark
                <a
                  href="https://arxiv.org/abs/2311.12983"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-500 hover:text-blue-700"
                >
                  <ExternalLink className="h-4 w-4" />
                </a>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Real-world questions requiring reasoning, web browsing, and tool use.
                Conceptually simple for humans (92% accuracy) yet challenging for most advanced AIs.
              </p>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">Reasoning</Badge>
                <Badge variant="outline">Web Browsing</Badge>
                <Badge variant="outline">Tool Use</Badge>
                <Badge variant="outline">Multi-step Tasks</Badge>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Key Observations */}
        <Card>
          <CardHeader>
            <CardTitle>Takeaways</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li className="flex items-start gap-3">
                <Badge variant="success" className="mt-0.5 shrink-0">Cost</Badge>
                <span>$4-8 for 127 questions across both models</span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="secondary" className="mt-0.5 shrink-0">Models</Badge>
                <span>+4.7% accuracy delta between open-weight and GPT-5-mini on the same scaffold</span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="outline" className="mt-0.5 shrink-0">Levels</Badge>
                <span>L1 and L3 within 3%; L2 shows the largest gap (+7.6%)</span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="default" className="mt-0.5 shrink-0">Traces</Badge>
                <span>
                  Evaluation traces with aggregate stats per run.{' '}
                  <button
                    onClick={() => setTracesModalOpen(true)}
                    className="text-blue-500 hover:underline inline-flex items-center gap-1"
                  >
                    <FileText className="h-3 w-3" />
                    View traces
                  </button>
                </span>
              </li>
            </ul>
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center text-sm text-muted-foreground pb-8">
          <p>
            Models: {MODELS.map(m => m.model).join(' · ')} • Evaluated: January 2026
          </p>
          <p className="mt-2 text-xs">
            * Questions with file attachments were excluded from this evaluation
          </p>
          <p className="mt-2">
            <a
              href="https://hal.cs.princeton.edu/gaia"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-500 hover:underline"
            >
              View HAL Princeton GAIA Leaderboard
            </a>
          </p>
        </div>
        </div>
      </main>

      {/* Traces Modal */}
      <TracesModal open={tracesModalOpen} onOpenChange={setTracesModalOpen} />
    </div>
  );
}
