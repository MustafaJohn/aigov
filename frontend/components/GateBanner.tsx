'use client';

import React from 'react';
import { CheckCircle2, XCircle, FileText, Info } from 'lucide-react';
import { ParseReport } from '../lib/types';

interface GateBannerProps {
  report: ParseReport;
}

export const GateBanner: React.FC<GateBannerProps> = ({ report }) => {
  if (report.status === 'BLOCKED') {
    return (
      <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-rose-900 shadow-2xs">
        <div className="flex items-start space-x-3">
          <XCircle className="h-5 w-5 text-rose-600 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="font-bold text-xs bg-rose-600 text-white px-2 py-0.5 rounded tracking-wide uppercase">
                Intake Blocked
              </span>
              <h3 className="font-semibold text-rose-950 text-sm">{report.summary}</h3>
            </div>
            <p className="text-xs text-rose-800 leading-relaxed">
              {report.gate_reason || 'This document could not be extracted.'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Smooth, non-intrusive status for ready documents (No annoying warnings or roadblocks)
  return (
    <div className="bg-white border border-slate-200 rounded-xl px-4 py-2.5 flex items-center justify-between shadow-2xs flex-wrap gap-2">
      <div className="flex items-center space-x-2.5">
        <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
        <span className="text-xs font-semibold text-slate-800">
          Document Intake Complete
        </span>
        <span className="text-xs text-slate-500">
          ({report.total_blocks} blocks parsed)
        </span>
      </div>

      <div className="flex items-center space-x-3 text-xs text-slate-500">
        {report.hidden_items_count > 0 && (
          <span className="inline-flex items-center space-x-1 text-[11px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
            <Info className="w-3 h-3 text-slate-400" />
            <span>{report.hidden_items_count} metadata entries screened</span>
          </span>
        )}
        <span className="text-emerald-700 font-medium bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full text-[11px]">
          Ready for Review
        </span>
      </div>
    </div>
  );
};
