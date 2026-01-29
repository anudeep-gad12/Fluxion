// Benchmarks page showing GAIA benchmark results

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Trophy, DollarSign, Cpu, ExternalLink, FileText, Play, Globe, Code, FileSearch } from 'lucide-react';
import { TracesModal } from '@/components/TracesModal';

// Benchmark data from docs/BENCHMARKS.md
const BENCHMARK_RESULTS = {
  model: 'gpt-oss-120b',
  provider: 'DeepInfra',
  date: 'January 2026',
  totalQuestions: 127,
  totalCorrect: 58,
  overallAccuracy: 45.7,
  overallRank: 18,
  totalSystems: 32,
  estimatedCost: 5,
  levels: [
    { level: 1, accuracy: 64.3, questions: 42, correct: 27, rank: 11 },
    { level: 2, accuracy: 37.9, questions: 66, correct: 25, rank: 19 },
    { level: 3, accuracy: 31.6, questions: 19, correct: 6, rank: 16 },
  ],
};

const COMPARISON_DATA = [
  { system: 'HAL + Claude Sonnet 4.5', overall: 74.6, l1: 82.1, l2: 72.7, l3: 65.4, cost: 178 },
  { system: 'HAL + Claude Opus 4.1', overall: 68.5, l1: 71.7, l2: 70.9, l3: 53.9, cost: 562 },
  { system: 'HAL + GPT-5 Medium', overall: 59.4, l1: 67.9, l2: 58.1, l3: 46.2, cost: 105 },
  { system: 'HF + o4-mini Low', overall: 47.9, l1: 58.5, l2: 47.7, l3: 26.9, cost: 81 },
  { system: 'This Agent (gpt-oss-120b)', overall: 45.7, l1: 64.3, l2: 37.9, l3: 31.6, cost: 5, isOurs: true },
  { system: 'HAL + Gemini 2.0 Flash', overall: 32.7, l1: 43.4, l2: 32.6, l3: 11.5, cost: 8 },
  { system: 'HAL + DeepSeek R1', overall: 30.3, l1: 43.4, l2: 27.9, l3: 11.5, cost: 73 },
  { system: 'HAL + DeepSeek V3', overall: 29.4, l1: 38.7, l2: 32.0, l3: 1.9, cost: 17 },
];

export function BenchmarksPage() {
  const navigate = useNavigate();
  const [tracesModalOpen, setTracesModalOpen] = useState(false);

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
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          <Card className="bg-gradient-to-br from-amber-50 to-orange-50 border-amber-200">
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-2">
                <Trophy className="h-4 w-4 text-amber-600" />
                Level 1 Rank
              </CardDescription>
              <CardTitle className="text-3xl sm:text-4xl text-amber-700">#{BENCHMARK_RESULTS.levels[0].rank}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs sm:text-sm text-amber-800">
                {BENCHMARK_RESULTS.levels[0].accuracy}% accuracy on Level 1
              </p>
              <p className="text-xs text-amber-600 mt-1">
                Competitive with Claude-3.7 Sonnet
              </p>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-emerald-50 to-green-50 border-emerald-200">
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-emerald-600" />
                Cost Efficiency
              </CardDescription>
              <CardTitle className="text-3xl sm:text-4xl text-emerald-700">~${BENCHMARK_RESULTS.estimatedCost}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs sm:text-sm text-emerald-800">
                Per full evaluation run
              </p>
              <p className="text-xs text-emerald-600 mt-1">
                vs $100-500+ for frontier models
              </p>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-violet-50 to-purple-50 border-violet-200">
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-violet-600" />
                Open-Weight Model
              </CardDescription>
              <CardTitle className="text-3xl sm:text-4xl text-violet-700">#{BENCHMARK_RESULTS.overallRank}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs sm:text-sm text-violet-800">
                Overall rank of {BENCHMARK_RESULTS.totalSystems} systems
              </p>
              <p className="text-xs text-violet-600 mt-1">
                Using {BENCHMARK_RESULTS.model}
              </p>
            </CardContent>
          </Card>
        </section>

        {/* About This Agent */}
        <Card className="border-indigo-200 bg-gradient-to-br from-indigo-50/50 to-slate-50">
          <CardHeader>
            <CardTitle>About This Agent</CardTitle>
            <CardDescription>
              Full agent scaffold with planning, tool use, and execution tracing
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              End-to-end agent system powered by {BENCHMARK_RESULTS.model}, a 120B
              Mixture-of-Experts open-weight reasoning model. Multi-step planning,
              tool orchestration, execution tracing, and real-time streaming.
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

        {/* About GAIA */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
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
            <CardDescription>
              General AI Assistants - A benchmark for real-world AI assistant capabilities
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              GAIA proposes real-world questions requiring fundamental abilities such as reasoning,
              multi-modality handling, web browsing, and tool-use proficiency. Questions are
              conceptually simple for humans (92% accuracy) yet challenging for most advanced AIs.
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">Reasoning</Badge>
              <Badge variant="outline">Web Browsing</Badge>
              <Badge variant="outline">Tool Use</Badge>
              <Badge variant="outline">Multi-step Tasks</Badge>
            </div>
          </CardContent>
        </Card>

        {/* Results by Level */}
        <Card>
          <CardHeader>
            <CardTitle>Results by Difficulty Level</CardTitle>
            <CardDescription>
              Evaluated on {BENCHMARK_RESULTS.totalQuestions} questions from the validation set (no file attachments)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-4 font-medium">Level</th>
                    <th className="text-right py-3 px-4 font-medium">Accuracy</th>
                    <th className="text-right py-3 px-4 font-medium">Correct</th>
                    <th className="text-right py-3 px-4 font-medium">Total</th>
                    <th className="text-right py-3 px-4 font-medium">Rank</th>
                  </tr>
                </thead>
                <tbody>
                  {BENCHMARK_RESULTS.levels.map((level) => (
                    <tr key={level.level} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="py-3 px-4">
                        <span className="font-medium">Level {level.level}</span>
                      </td>
                      <td className="text-right py-3 px-4 font-mono font-bold text-blue-600">
                        {level.accuracy.toFixed(1)}%
                      </td>
                      <td className="text-right py-3 px-4 font-mono">{level.correct}</td>
                      <td className="text-right py-3 px-4 font-mono text-muted-foreground">
                        {level.questions}
                      </td>
                      <td className="text-right py-3 px-4">
                        <Badge variant={level.rank <= 15 ? 'default' : 'secondary'}>
                          #{level.rank}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-muted/30 font-medium">
                    <td className="py-3 px-4">Overall</td>
                    <td className="text-right py-3 px-4 font-mono font-bold text-blue-600">
                      {BENCHMARK_RESULTS.overallAccuracy.toFixed(1)}%
                    </td>
                    <td className="text-right py-3 px-4 font-mono">{BENCHMARK_RESULTS.totalCorrect}</td>
                    <td className="text-right py-3 px-4 font-mono text-muted-foreground">
                      {BENCHMARK_RESULTS.totalQuestions}
                    </td>
                    <td className="text-right py-3 px-4">
                      <Badge>#{BENCHMARK_RESULTS.overallRank}</Badge>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden space-y-3">
              {BENCHMARK_RESULTS.levels.map((level) => (
                <div key={level.level} className="bg-slate-50 rounded-lg p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-lg">Level {level.level}</span>
                    <Badge variant={level.rank <= 15 ? 'default' : 'secondary'}>
                      #{level.rank}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <div className="text-xs text-slate-500">Accuracy</div>
                      <div className="font-mono font-bold text-blue-600">
                        {level.accuracy.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Correct / Total</div>
                      <div className="font-mono">
                        {level.correct} / {level.questions}
                      </div>
                    </div>
                  </div>
                </div>
              ))}

              {/* Overall summary card */}
              <div className="bg-blue-50 rounded-lg p-4 space-y-2 border-2 border-blue-200">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-lg">Overall</span>
                  <Badge>#{BENCHMARK_RESULTS.overallRank}</Badge>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-xs text-slate-500">Accuracy</div>
                    <div className="font-mono font-bold text-blue-600">
                      {BENCHMARK_RESULTS.overallAccuracy.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Correct / Total</div>
                    <div className="font-mono">
                      {BENCHMARK_RESULTS.totalCorrect} / {BENCHMARK_RESULTS.totalQuestions}
                    </div>
                  </div>
                </div>
              </div>
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
              {' '}(January 2026). This agent's results are self-evaluated on the same validation set.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Desktop table */}
            <div className="hidden lg:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-4 font-medium">System</th>
                    <th className="text-right py-3 px-4 font-medium">Overall</th>
                    <th className="text-right py-3 px-4 font-medium">L1</th>
                    <th className="text-right py-3 px-4 font-medium">L2</th>
                    <th className="text-right py-3 px-4 font-medium">L3</th>
                    <th className="text-right py-3 px-4 font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON_DATA.map((row) => (
                    <tr
                      key={row.system}
                      className={`border-b last:border-0 hover:bg-muted/50 ${
                        row.isOurs ? 'bg-blue-50 font-medium' : ''
                      }`}
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          {row.system}
                          {row.isOurs && (
                            <Badge variant="default" className="text-xs">This System</Badge>
                          )}
                        </div>
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
            </div>

            {/* Tablet horizontal scroll */}
            <div className="hidden md:block lg:hidden overflow-x-auto">
              <table className="w-full text-sm min-w-[600px]">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-4 font-medium">System</th>
                    <th className="text-right py-3 px-4 font-medium">Overall</th>
                    <th className="text-right py-3 px-4 font-medium">L1</th>
                    <th className="text-right py-3 px-4 font-medium">L2</th>
                    <th className="text-right py-3 px-4 font-medium">L3</th>
                    <th className="text-right py-3 px-4 font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON_DATA.map((row) => (
                    <tr
                      key={row.system}
                      className={`border-b last:border-0 hover:bg-muted/50 ${
                        row.isOurs ? 'bg-blue-50 font-medium' : ''
                      }`}
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          {row.system}
                          {row.isOurs && (
                            <Badge variant="default" className="text-xs">This System</Badge>
                          )}
                        </div>
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
            </div>

            {/* Mobile cards */}
            <div className="md:hidden space-y-3">
              {COMPARISON_DATA.map((row) => (
                <div
                  key={row.system}
                  className={`rounded-lg p-4 space-y-3 ${
                    row.isOurs
                      ? 'bg-blue-50 border-2 border-blue-200'
                      : 'bg-slate-50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className="font-medium text-sm">{row.system}</div>
                      {row.isOurs && (
                        <Badge variant="default" className="text-xs mt-1">
                          This System
                        </Badge>
                      )}
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-slate-500">Overall</div>
                      <div className="font-mono font-bold text-base">
                        {row.overall}%
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <div className="text-slate-500">L1</div>
                      <div className="font-mono">{row.l1}%</div>
                    </div>
                    <div>
                      <div className="text-slate-500">L2</div>
                      <div className="font-mono">{row.l2}%</div>
                    </div>
                    <div>
                      <div className="text-slate-500">L3</div>
                      <div className="font-mono">{row.l3}%</div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-slate-200">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500">Cost</span>
                      <span className={`font-mono font-medium ${
                        row.isOurs ? 'text-emerald-600' : 'text-slate-600'
                      }`}>
                        ${row.cost}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Key Observations */}
        <Card>
          <CardHeader>
            <CardTitle>Key Observations</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm">
              <li className="flex items-start gap-3">
                <Badge variant="success" className="mt-0.5 shrink-0">L1</Badge>
                <span>
                  This agent's 64.3% on Level 1 is competitive with systems using Claude-3.7 Sonnet and
                  Haiku 4.5, despite using an open-weight model.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="success" className="mt-0.5 shrink-0">Cost</Badge>
                <span>
                  Estimated ~$5 for full evaluation vs $100-500+ for frontier model systems —
                  <strong className="text-emerald-600"> 20-100x more cost efficient</strong>.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="default" className="mt-0.5 shrink-0">Open</Badge>
                <span>
                  This agent achieves GPT-4.1 tier performance using gpt-oss-120b, an open-weight reasoning model
                  that can be self-hosted.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="outline" className="mt-0.5 shrink-0">📊</Badge>
                <span>
                  Full evaluation traces were captured for all {BENCHMARK_RESULTS.totalQuestions} questions.
                  Per GAIA guidelines, question-answer pairs are not published to prevent benchmark contamination.{' '}
                  <button
                    onClick={() => setTracesModalOpen(true)}
                    className="text-blue-500 hover:underline inline-flex items-center gap-1"
                  >
                    <FileText className="h-3 w-3" />
                    View results
                  </button>
                </span>
              </li>
            </ul>
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center text-sm text-muted-foreground pb-8">
          <p>
            Model: {BENCHMARK_RESULTS.model} • Evaluated: {BENCHMARK_RESULTS.date}
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
