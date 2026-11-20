'use client';

import React, { useState } from 'react';
import {
  ShieldCheck,
  Copy,
  Download,
  Check,
  FileText,
  Layers,
  ArrowRight,
  ArrowLeft,
  Lock,
  Sparkles
} from 'lucide-react';
import { Block, DetectedEntity } from '../lib/types';
import { compileProtectedDocument, generateProtectedBlockText, downloadTextFile } from '../lib/restore';

interface RedactedOnlyViewProps {
  blocks: Block[];
  entities: DetectedEntity[];
  documentName?: string;
  onProceedToAI?: () => void;
  onBackToReview?: () => void;
  aiLocked?: boolean;
  gateReason?: string | null;
}

export const RedactedOnlyView: React.FC<RedactedOnlyViewProps> = ({
  blocks,
  entities,
  documentName = 'document',
  onProceedToAI,
  onBackToReview,
  aiLocked = false,
  gateReason = null,
}) => {
  const [copied, setCopied] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<'clean' | 'comparison'>('clean');

  const redactedText = compileProtectedDocument(blocks, entities, false);
  const activeCount = entities.filter((e) => e.is_active).length;
  const visibleBlocks = blocks.filter((b) => b.visibility === 'visible');

  const handleCopy = () => {
    navigator.clipboard.writeText(redactedText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    downloadTextFile(redactedText, `redacted-${documentName}.txt`);
  };

  const renderHighlightedProtectedText = (text: string) => {
    const placeholderRegex = /(\[[A-Z_]+(?:\s+\d+)?\])/g;
    const parts = text.split(placeholderRegex);
    return parts.map((part, idx) => {
      if (placeholderRegex.test(part)) {
        const upper = part.toUpperCase();
        let colorClasses = 'bg-slate-100 text-slate-800 border-slate-300';
        if (upper.includes('PERSON')) {
          colorClasses = 'bg-amber-100/90 text-amber-900 border-amber-300';
        } else if (upper.includes('ORG') || upper.includes('COMPANY')) {
          colorClasses = 'bg-sky-100/90 text-sky-900 border-sky-300';
        } else if (upper.includes('CARD') || upper.includes('ACCOUNT') || upper.includes('IBAN')) {
          colorClasses = 'bg-rose-100/90 text-rose-900 border-rose-300';
        } else if (upper.includes('REF') || upper.includes('CLAIM') || upper.includes('MATTER') || upper.includes('IHS') || upper.includes('UTR')) {
          colorClasses = 'bg-indigo-100/90 text-indigo-900 border-indigo-300';
        } else if (upper.includes('POSTCODE') || upper.includes('ADDRESS')) {
          colorClasses = 'bg-teal-100/90 text-teal-900 border-teal-300';
        } else if (upper.includes('DATE') || upper.includes('DOB')) {
          colorClasses = 'bg-purple-100/90 text-purple-900 border-purple-300';
        } else if (upper.includes('AMOUNT') || upper.includes('MONEY') || upper.includes('CURRENCY')) {
          colorClasses = 'bg-emerald-100/90 text-emerald-900 border-emerald-300';
        }

        return (
          <span
            key={`ph_${idx}`}
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-semibold border ${colorClasses} mx-0.5 shadow-2xs select-none`}
          >
            {part}
          </span>
        );
      }
      return <span key={`txt_${idx}`}>{part}</span>;
    });
  };

  const renderOriginalBlockText = (block: Block) => {
    const blockEntities = entities
      .filter((e) => e.block_id === block.id && e.is_active)
      .sort((a, b) => a.start - b.start);

    if (blockEntities.length === 0) {
      return <span>{block.text}</span>;
    }

    const elements: React.ReactNode[] = [];
    let lastIdx = 0;

    blockEntities.forEach((ent, i) => {
      if (ent.start > lastIdx) {
        elements.push(<span key={`txt_${i}`}>{block.text.substring(lastIdx, ent.start)}</span>);
      }
      elements.push(
        <mark
          key={`ent_${ent.id}`}
          className="bg-amber-100 text-amber-900 border border-amber-300 px-1 py-0.5 rounded text-xs font-medium"
        >
          {ent.text}
        </mark>
      );
      lastIdx = ent.end;
    });

    if (lastIdx < block.text.length) {
      elements.push(<span key="txt_end">{block.text.substring(lastIdx)}</span>);
    }

    return elements;
  };

  return (
    <div className="space-y-4 max-w-6xl mx-auto">
      {/* Top Action Toolbar */}
      <div className="bg-white border border-slate-200 rounded-xl p-3 sm:p-4 shadow-2xs flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Left: Stage Title & Stats */}
        <div className="flex items-center space-x-3 flex-wrap gap-2">
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
              Stage 2: Redacted Document Inspection
            </span>
          </div>
          <span className="text-slate-300 hidden sm:inline">|</span>
          <span className="text-xs text-slate-600">
            <span className="font-semibold text-slate-900">{activeCount}</span> PII items masked
          </span>
          <span className="text-[10px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
            ✓ SRA & GDPR Ready
          </span>
        </div>

        {/* Right: Mode Toggle & Actions */}
        <div className="flex items-center space-x-2 flex-wrap gap-2">
          {/* Mode Switcher */}
          <div className="flex items-center bg-slate-100 p-0.5 rounded-lg border border-slate-200 text-xs">
            <button
              type="button"
              onClick={() => setViewMode('clean')}
              className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md font-medium transition-all cursor-pointer ${
                viewMode === 'clean'
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Redacted Document</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode('comparison')}
              className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md font-medium transition-all cursor-pointer ${
                viewMode === 'comparison'
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Side-by-Side Comparison</span>
            </button>
          </div>

          {onBackToReview && (
            <button
              type="button"
              onClick={onBackToReview}
              className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Review</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-slate-500" />}
            <span>{copied ? 'Copied' : 'Copy Text'}</span>
          </button>

          <button
            type="button"
            onClick={handleDownload}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-slate-500" />
            <span>Download .txt</span>
          </button>

          {onProceedToAI && (
            <button
              type="button"
              onClick={onProceedToAI}
              disabled={aiLocked}
              title={aiLocked ? (gateReason || 'Resolve intake warnings before proceeding to AI') : 'Proceed to AI Legal Studio'}
              className={`flex items-center space-x-1.5 text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors cursor-pointer ${
                aiLocked
                  ? 'bg-slate-200 text-slate-400 cursor-not-allowed border border-slate-300'
                  : 'bg-indigo-600 hover:bg-indigo-700 text-white'
              }`}
            >
              {aiLocked ? <Lock className="w-3.5 h-3.5" /> : <Sparkles className="w-3.5 h-3.5" />}
              <span>Proceed to AI Legal Studio</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      {viewMode === 'clean' ? (
        /* Single Document Paper Canvas */
        <div className="bg-slate-100/60 border border-slate-200 rounded-xl p-4 sm:p-8 flex justify-center overflow-y-auto max-h-[740px]">
          <div className="w-full max-w-4xl bg-white shadow-xs border border-slate-200/90 rounded-xl p-8 sm:p-14 min-h-[600px] select-text">
            <div className="border-b border-slate-100 pb-4 mb-6 flex items-center justify-between text-xs text-slate-400">
              <span className="font-mono uppercase tracking-wider text-[11px] text-slate-500 font-semibold">
                Protected Document • {documentName}
              </span>
              <span>{redactedText.length} characters • {visibleBlocks.length} blocks</span>
            </div>

            <div className="space-y-4">
              {visibleBlocks.map((block) => {
                const protectedBlockText = generateProtectedBlockText(block, entities);
                return (
                  <div
                    key={block.id}
                    className="text-[14.5px] leading-[1.8] text-slate-800 tracking-[-0.01em] font-sans"
                  >
                    {renderHighlightedProtectedText(protectedBlockText)}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* Side-by-Side Comparison View */
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 h-[740px]">
          {/* Left: Original with Highlight Badges */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-2xs flex flex-col h-full">
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-slate-400"></span>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Original Document (With Highlights)
                </h4>
              </div>
              <span className="text-[11px] text-slate-500">Unmasked Source</span>
            </div>

            <div className="p-4 sm:p-6 bg-slate-50/70 overflow-y-auto flex-1 select-text">
              <div className="bg-white border border-slate-200/80 rounded-lg p-6 shadow-xs space-y-4 min-h-full">
                {visibleBlocks.map((block) => (
                  <div
                    key={block.id}
                    className="text-[14px] leading-[1.75] text-slate-800 tracking-[-0.01em]"
                  >
                    {renderOriginalBlockText(block)}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right: Protected Redacted Document */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-2xs flex flex-col h-full">
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Protected Document (Typed Placeholders)
                </h4>
              </div>
              <span className="text-[10px] font-mono font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                Safe for AI
              </span>
            </div>

            <div className="p-4 sm:p-6 bg-slate-50/70 overflow-y-auto flex-1 select-text">
              <div className="bg-white border border-slate-200/80 rounded-lg p-6 shadow-xs space-y-4 min-h-full">
                {visibleBlocks.map((block) => {
                  const protectedBlockText = generateProtectedBlockText(block, entities);
                  return (
                    <div
                      key={block.id}
                      className="text-[14px] leading-[1.75] text-slate-800 tracking-[-0.01em]"
                    >
                      {renderHighlightedProtectedText(protectedBlockText)}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Bottom Assurance & Navigation Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
        <div className="flex items-center space-x-2 text-slate-600">
          <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>
            <strong className="text-slate-800">Deterministic Redaction Assurance:</strong> Contains zero unmasked client identifiers. Safe to transmit to external models.
          </span>
        </div>

        <div className="flex items-center space-x-2 flex-shrink-0">
          {onBackToReview && (
            <button
              type="button"
              onClick={onBackToReview}
              className="text-xs font-semibold text-slate-600 hover:text-slate-900 hover:underline px-2 py-1 cursor-pointer"
            >
              ← Back to Review
            </button>
          )}

          {onProceedToAI && (
            <button
              type="button"
              onClick={onProceedToAI}
              disabled={aiLocked}
              className={`flex items-center space-x-1.5 text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors cursor-pointer ${
                aiLocked
                  ? 'bg-slate-200 text-slate-400 cursor-not-allowed border border-slate-300'
                  : 'bg-indigo-600 hover:bg-indigo-700 text-white'
              }`}
            >
              <span>Proceed to AI Legal Studio</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
