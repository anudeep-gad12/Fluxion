// Benchmarks page showing GAIA benchmark results

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Trophy, DollarSign, Cpu, ExternalLink, FileText, Play, Globe, Code, FileSearch } from 'lucide-react';
import { TracesModal } from '@/components/TracesModal';

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

const COMPARISON_DATA = [
  { system: 'HAL + Claude Sonnet 4.5', overall: 74.6, l1: 82.1, l2: 72.7, l3: 65.4, cost: 178 },
  { system: 'HAL + Claude Opus 4.1', overall: 68.5, l1: 71.7, l2: 70.9, l3: 53.9, cost: 562 },
  { system: 'HAL + GPT-5 Medium', overall: 59.4, l1: 67.9, l2: 58.1, l3: 46.2, cost: 105 },
  { system: 'This Agent (GPT-5-mini)', overall: 50.4, l1: 66.7, l2: 45.5, l3: 31.6, cost: 8, isOurs: true },
  { system: 'HF + o4-mini Low', overall: 47.9, l1: 58.5, l2: 47.7, l3: 26.9, cost: 81 },
  { system: 'This Agent (gpt-oss-120b)', overall: 45.7, l1: 64.3, l2: 37.9, l3: 31.6, cost: 4, isOurs: true },
  { system: 'HAL + Gemini 2.0 Flash', overall: 32.7, l1: 43.4, l2: 32.6, l3: 11.5, cost: 8 },
  { system: 'HAL + DeepSeek R1', overall: 30.3, l1: 43.4, l2: 27.9, l3: 11.5, cost: 73 },
  { system: 'HAL + DeepSeek V3', overall: 29.4, l1: 38.7, l2: 32.0, l3: 1.9, cost: 17 },
];

const bestModel = MODELS[0]; // GPT-5-mini (best results)
const deployedModel = MODELS[1]; // gpt-oss-120b (deployed)

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

          <Card className="bg-gradient-to-br from-violet-50 to-purple-50 border-violet-200">
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-violet-600" />
                Two Models Tested
              </CardDescription>
              <CardTitle className="text-3xl sm:text-4xl text-violet-700">2</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs sm:text-sm text-violet-800">
                Same scaffold, different LLMs
              </p>
              <p className="text-xs text-violet-600 mt-1">
                {bestModel.model} (best) &middot; {deployedModel.model} (deployed)
              </p>
            </CardContent>
          </Card>
        </section>

        {/* About This Agent */}
        <Card className="border-indigo-200 bg-gradient-to-br from-indigo-50/50 to-slate-50">
          <CardHeader>
            <CardTitle>About This Agent</CardTitle>
            <CardDescription>
              Single-agent scaffold with planning, tool use, and execution tracing
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              End-to-end agent system with multi-step planning, tool orchestration,
              execution tracing, and real-time streaming. The same scaffold runs with
              different LLM backends — currently deployed with {deployedModel.model} (open-weight,
              120B MoE reasoning model) and benchmarked with {bestModel.model} (OpenAI).
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
                <Badge variant="success" className="mt-0.5 shrink-0">Best</Badge>
                <span>
                  GPT-5-mini reaches 50.4% overall — competitive with mid-tier leaderboard systems
                  that use multi-agent frameworks and frontier models costing 10-100x more.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="success" className="mt-0.5 shrink-0">Cost</Badge>
                <span>
                  $4-8 for 127 questions vs $100-500+ for frontier systems —
                  <strong className="text-emerald-600"> 10-100x more cost efficient</strong>.
                  Just $0.03-0.07 per question.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="default" className="mt-0.5 shrink-0">Open</Badge>
                <span>
                  gpt-oss-120b (open-weight, self-hostable) reaches 45.7% — only 4.7% behind GPT-5-mini
                  at half the cost. Same scaffold, proving the architecture carries most of the value.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="outline" className="mt-0.5 shrink-0">L1</Badge>
                <span>
                  Both models score 64-67% on Level 1, competitive with Claude-3.7 Sonnet and Haiku 4.5.
                  The biggest gap is Level 2 where GPT-5-mini gains +7.6% over gpt-oss-120b.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Badge variant="outline" className="mt-0.5 shrink-0">Traces</Badge>
                <span>
                  Full evaluation traces captured for all 127 questions with both models.{' '}
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
