// Final answer component - displays the final answer prominently

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { XCircle, Sparkles } from 'lucide-react';
import type { Run } from '@/types';
import { AnswerMarkdown, extractAnswer } from '@/components/AnswerMarkdown';

interface FinalAnswerProps {
  run: Run;
}


export function FinalAnswer({ run }: FinalAnswerProps) {
  if (run.status === 'running') {
    return null;
  }

  const isSuccess = run.status === 'succeeded';
  const displayAnswer = isSuccess && run.final_answer ? extractAnswer(run.final_answer) : '';

  return (
    <Card className={isSuccess ? 'border-green-300 bg-gradient-to-br from-green-50 to-emerald-50' : 'border-red-200 bg-red-50'}>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center gap-2">
          {isSuccess ? (
            <Sparkles className="h-5 w-5 text-green-600" />
          ) : (
            <XCircle className="h-5 w-5 text-red-600" />
          )}
          <CardTitle className="text-base font-semibold">
            {isSuccess ? 'Final Answer' : 'Run Failed'}
          </CardTitle>
          <Badge variant={isSuccess ? 'success' : 'destructive'}>
            {run.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="py-3 px-4">
        {isSuccess && displayAnswer ? (
          <AnswerMarkdown content={displayAnswer} />
        ) : isSuccess ? (
          <div className="text-sm text-gray-600 italic">
            The task completed successfully.
          </div>
        ) : run.error_detail ? (
          <div className="text-sm text-red-700">
            <p className="font-medium">{run.error_code || 'Error'}</p>
            <p className="mt-1">{run.error_detail}</p>
          </div>
        ) : (
          <div className="text-sm text-red-600">
            The run failed without additional details.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
