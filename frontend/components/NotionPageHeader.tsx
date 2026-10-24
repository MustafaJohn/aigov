'use client';

import React from 'react';
import {
  FileText,
  ShieldCheck,
  Bot,
  Edit3,
  Database,
  Layers,
  Sparkles,
  Download,
  Info
} from 'lucide-react';
import { DocumentIR, DetectedEntity } from '../lib/types';

interface NotionPageHeaderProps {
  docIR?: DocumentIR | null;
  entities: DetectedEntity[];
  activeView: 'intake' | 'review' | 'redacted_only' | 'ai' | 'notes' | 'database';
  onSelectView: (view: 'intake' | 'review' | 'redacted_only' | 'ai' | 'notes' | 'database') => void;
  notesCount: number;
}

export const NotionPageHeader: React.FC<NotionPageHeaderProps> = ({
  docIR,
  entities,
  activeView,
  onSelectView,
  notesCount,
}) => {
  if (!docIR) return null;

  const activeCount = entities.filter((e) => e.is_active).length;

  return (
    <div className="pb-4 mb-4 border-b border-[#e9e9e7]">
      {/* Notion Document Title */}
      <div className="flex items-center space-x-3 mb-3">
        <span className="text-3xl select-none">📄</span>
        <h1 className="text-2xl font-bold text-[#37352f] tracking-tight">
          {docIR.source.filename}
        </h1>
      </div>

      {/* Notion Page Properties Table */}
      <div className="bg-[#f7f7f5] rounded-xl p-3 border border-[#e9e9e7] mb-4 text-xs space-y-1.5 max-w-3xl">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[#787774]">
          <div className="flex items-center space-x-1.5">
            <span className="text-[11px] font-medium">Status:</span>
            <span className="text-emerald-800 font-semibold bg-emerald-100/70 px-1.5 py-0.5 rounded text-[10px]">
              ● Ready
            </span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="text-[11px] font-medium">Protection:</span>
            <span className="font-mono text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded text-[10px] font-bold">
              XXX / XYZ Jargon
            </span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="text-[11px] font-medium">Blocks:</span>
            <span className="text-[#37352f] font-semibold text-[11px]">
              {docIR.blocks.length} blocks
            </span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="text-[11px] font-medium">PII Items:</span>
            <span className="text-amber-800 font-semibold bg-amber-100/70 px-1.5 py-0.5 rounded text-[10px]">
              {activeCount} of {entities.length} masked
            </span>
          </div>
        </div>
      </div>

      {/* Notion Views Tab Switcher */}
      <div className="flex items-center space-x-1 border-b border-[#e9e9e7] -mb-4 overflow-x-auto">
        <button
          onClick={() => onSelectView('review')}
          className={`flex items-center space-x-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-all cursor-pointer whitespace-nowrap ${
            activeView === 'review'
              ? 'border-[#37352f] text-[#37352f] font-semibold'
              : 'border-transparent text-[#787774] hover:text-[#37352f] hover:border-[#e9e9e7]'
          }`}
        >
          <Layers className="w-3.5 h-3.5 text-indigo-600" />
          <span>Side-by-Side Review</span>
        </button>

        <button
          onClick={() => onSelectView('redacted_only')}
          className={`flex items-center space-x-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-all cursor-pointer whitespace-nowrap ${
            activeView === 'redacted_only'
              ? 'border-[#37352f] text-[#37352f] font-semibold'
              : 'border-transparent text-[#787774] hover:text-[#37352f] hover:border-[#e9e9e7]'
          }`}
        >
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          <span>Redacted Text Only</span>
        </button>

        <button
          onClick={() => onSelectView('ai')}
          className={`flex items-center space-x-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-all cursor-pointer whitespace-nowrap ${
            activeView === 'ai'
              ? 'border-[#37352f] text-[#37352f] font-semibold'
              : 'border-transparent text-[#787774] hover:text-[#37352f] hover:border-[#e9e9e7]'
          }`}
        >
          <Bot className="w-3.5 h-3.5 text-purple-600" />
          <span>Notion AI Studio</span>
          <span className="text-[9px] bg-purple-100 text-purple-800 font-bold px-1 rounded">
            Self-Prompt
          </span>
        </button>

        <button
          onClick={() => onSelectView('database')}
          className={`flex items-center space-x-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-all cursor-pointer whitespace-nowrap ${
            activeView === 'database'
              ? 'border-[#37352f] text-[#37352f] font-semibold'
              : 'border-transparent text-[#787774] hover:text-[#37352f] hover:border-[#e9e9e7]'
          }`}
        >
          <Database className="w-3.5 h-3.5 text-blue-600" />
          <span>Entity Database</span>
          <span className="text-[10px] text-[#787774] font-mono">({entities.length})</span>
        </button>

        <button
          onClick={() => onSelectView('notes')}
          className={`flex items-center space-x-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-all cursor-pointer whitespace-nowrap ${
            activeView === 'notes'
              ? 'border-[#37352f] text-[#37352f] font-semibold'
              : 'border-transparent text-[#787774] hover:text-[#37352f] hover:border-[#e9e9e7]'
          }`}
        >
          <Edit3 className="w-3.5 h-3.5 text-amber-600" />
          <span>Case Notes</span>
          {notesCount > 0 && (
            <span className="text-[10px] text-[#787774] font-mono">({notesCount})</span>
          )}
        </button>
      </div>
    </div>
  );
};
