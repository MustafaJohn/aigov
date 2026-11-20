'use client';

import React from 'react';
import { Check, AlertCircle, XCircle } from 'lucide-react';
import { ParseReport } from '../lib/types';

interface GateBannerProps {
  report: ParseReport;
  /** True once the lawyer has confirmed they read the intake warnings. Required before AI dispatch. */
  acknowledged?: boolean;
  onAcknowledge?: () => void;
}

export const GateBanner: React.FC<GateBannerProps> = ({ report, acknowledged = false, onAcknowledge }) => {
  // If the document is cleanly ready with no warnings, do not render any redundant banners.
  if (report.status === 'READY') {
    return null;
  }

  // Handle Blocked documents
  if (report.status === 'BLOCKED') {
    return (
      <div className="bg-rose-50/90 border border-rose-200 rounded-xl p-4 text-rose-950 shadow-2xs space-y-1.5 my-2">
        <div className="flex items-center space-x-2.5">
          <XCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <h3 className="text-xs font-semibold text-rose-950 tracking-tight">
            Document Ingestion Blocked: {report.summary}
          </h3>
        </div>
        <p className="text-xs text-rose-800 pl-6 leading-relaxed">
          {report.gate_reason || 'This document could not be processed due to formatting or structural restrictions.'}
        </p>
      </div>
    );
  }

  // Handle Ready with Warnings (scanned pages, metadata entries, interactive form fields)
  if (report.status === 'READY_WITH_WARNINGS' && report.warnings.length > 0) {
    return (
      <div className="bg-slate-50/90 border border-slate-200 rounded-xl p-3.5 shadow-2xs space-y-2 my-2 transition-all">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <span className="text-xs font-semibold text-slate-800">
              Intake Observations ({report.warnings.length})
            </span>
            <span className="text-[11px] text-slate-500 hidden sm:inline">•</span>
            <span className="text-[11px] text-slate-600">{report.summary}</span>
          </div>

          <div>
            {acknowledged ? (
              <span className="inline-flex items-center space-x-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-md">
                <Check className="w-3 h-3 text-emerald-600" />
                <span>Acknowledged</span>
              </span>
            ) : (
              <span className="text-[10px] font-medium text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                Review required for AI dispatch
              </span>
            )}
          </div>
        </div>

        <div className="text-xs text-slate-600 pl-6 space-y-1">
          {report.warnings.map((w, idx) => (
            <div key={idx} className="flex items-start space-x-1.5">
              <span className="text-slate-400 select-none">•</span>
              <span>{w}</span>
            </div>
          ))}
        </div>

        {!acknowledged && onAcknowledge && (
          <div className="pl-6 pt-1">
            <button
              type="button"
              onClick={onAcknowledge}
              className="text-xs font-medium text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 px-3 py-1.5 rounded-lg transition-colors cursor-pointer shadow-2xs inline-flex items-center space-x-1.5"
            >
              <Check className="w-3.5 h-3.5 text-emerald-600" />
              <span>Acknowledge Observations</span>
            </button>
          </div>
        )}
      </div>
    );
  }

  return null;
};
