'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  ShieldAlert,
  ArrowRight,
  Eye,
  EyeOff,
  Check,
  Download,
  Plus,
  Trash2,
  Sparkles,
  Search,
  Filter,
  FileText
} from 'lucide-react';
import { Block, DetectedEntity } from '../lib/types';
import { generateProtectedBlockText, compileProtectedDocument, downloadTextFile, generateNextJargon } from '../lib/restore';

interface SideBySideReviewProps {
  blocks: Block[];
  entities: DetectedEntity[];
  onToggleEntity: (entityId: string) => void;
  onAddManualEntity: (text: string, blockId?: string, start?: number, end?: number) => void;
  onRemoveEntity: (entityId: string) => void;
  includeHidden: boolean;
  onToggleIncludeHidden: () => void;
  onProceedToAI: () => void;
  onSaveDocument?: () => void;
  onAddQuickNote?: (title: string, content: string) => void;
}

export const SideBySideReview: React.FC<SideBySideReviewProps> = ({
  blocks,
  entities,
  onToggleEntity,
  onAddManualEntity,
  onRemoveEntity,
  includeHidden,
  onToggleIncludeHidden,
  onProceedToAI,
  onSaveDocument,
  onAddQuickNote,
}) => {
  const [selectedTypeFilter, setSelectedTypeFilter] = useState<string>('ALL');
  const [customTerm, setCustomTerm] = useState<string>('');
  const [selectedText, setSelectedText] = useState<string>('');
  const [selectionContext, setSelectionContext] = useState<{ blockId?: string; start?: number; end?: number } | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [showQuickNoteModal, setShowQuickNoteModal] = useState<boolean>(false);
  const [quickNoteTitle, setQuickNoteTitle] = useState<string>('');
  const [quickNoteText, setQuickNoteText] = useState<string>('');
  const [noteSavedToast, setNoteSavedToast] = useState<boolean>(false);

  const displayBlocks = blocks.filter((b) => {
    if (b.visibility === 'visible') return true;
    if (includeHidden && (b.visibility === 'hidden' || b.visibility === 'metadata')) {
      return true;
    }
    return false;
  });

  const hiddenBlocksCount = blocks.filter(
    (b) => b.visibility === 'hidden' || b.visibility === 'metadata'
  ).length;

  const activeEntitiesCount = entities.filter((e) => e.is_active).length;
  const entityTypes = Array.from(new Set(entities.map((e) => e.type)));

  // Listen to user text selection inside the original document view
  const handleMouseUp = () => {
    const sel = window.getSelection();
    if (sel && sel.toString().trim().length > 0) {
      const text = sel.toString().trim();
      setSelectedText(text);

      // Try to determine the block ID if selection occurred inside a block container
      const anchorNode = sel.anchorNode;
      const element = anchorNode instanceof HTMLElement ? anchorNode : anchorNode?.parentElement;
      const blockEl = element?.closest('[data-block-id]');
      const blockId = blockEl?.getAttribute('data-block-id') || undefined;
      setSelectionContext({ blockId });
    } else {
      setSelectedText('');
      setSelectionContext(null);
    }
  };

  const handleManualHighlightClick = () => {
    if (!selectedText) return;
    onAddManualEntity(selectedText, selectionContext?.blockId);
    setSelectedText('');
    setSelectionContext(null);
    window.getSelection()?.removeAllRanges();
  };

  const handleAddCustomTermSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customTerm.trim()) return;
    onAddManualEntity(customTerm.trim());
    setCustomTerm('');
  };

  const handleDownloadRedacted = () => {
    const text = compileProtectedDocument(blocks, entities, includeHidden);
    downloadTextFile(text, 'redacted-document.txt');
  };

  // Deliverable 5: Deduplicate entities by unique canonical value and track uncertain items
  const [resolvedUncertainKeys, setResolvedUncertainKeys] = useState<Set<string>>(new Set());

  const entityGroups = React.useMemo(() => {
    const map = new Map<string, {
      key: string;
      text: string;
      type: string;
      placeholder: string;
      ids: string[];
      count: number;
      isActive: boolean;
      isManual: boolean;
      confidence: number;
      isUncertain: boolean;
    }>();

    for (const ent of entities) {
      const key = `${ent.text.trim().toLowerCase()}__${ent.type}`;
      if (!map.has(key)) {
        map.set(key, {
          key,
          text: ent.text.trim(),
          type: ent.type,
          placeholder: ent.placeholder || '[PROTECTED]',
          ids: [ent.id],
          count: 1,
          isActive: ent.is_active,
          isManual: Boolean((ent as any).is_manual),
          confidence: ent.confidence ?? 1.0,
          isUncertain: !((ent as any).is_manual) && (ent.confidence !== undefined && ent.confidence < 0.94)
        });
      } else {
        const existing = map.get(key)!;
        existing.ids.push(ent.id);
        existing.count += 1;
        if (ent.is_active) existing.isActive = true;
      }
    }
    return Array.from(map.values());
  }, [entities]);

  const uncertainGroups = entityGroups.filter((g) => g.isUncertain && !resolvedUncertainKeys.has(g.key));
  const unresolvedUncertainCount = uncertainGroups.length;

  const handleToggleGroup = (grp: typeof entityGroups[0]) => {
    const shouldActivate = !grp.isActive;
    grp.ids.forEach((id) => {
      const current = entities.find((e) => e.id === id);
      if (current && current.is_active !== shouldActivate) {
        onToggleEntity(id);
      }
    });
  };

  const handleConfirmUncertain = (grpKey: string, ids: string[]) => {
    ids.forEach((id) => {
      const current = entities.find((e) => e.id === id);
      if (current && !current.is_active) {
        onToggleEntity(id);
      }
    });
    setResolvedUncertainKeys((prev) => new Set([...prev, grpKey]));
  };

  const handleDismissUncertain = (grpKey: string, ids: string[]) => {
    ids.forEach((id) => {
      const current = entities.find((e) => e.id === id);
      if (current && current.is_active) {
        onToggleEntity(id);
      }
    });
    setResolvedUncertainKeys((prev) => new Set([...prev, grpKey]));
  };

  const filteredGroups = entityGroups.filter((grp) => {
    if (selectedTypeFilter !== 'ALL' && grp.type !== selectedTypeFilter) return false;
    if (searchQuery.trim() && !grp.text.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  // Render original text with clickable highlight marks
  const renderOriginalText = (block: Block) => {
    const blockEntities = entities
      .filter((e) => e.block_id === block.id)
      .sort((a, b) => a.start - b.start);

    if (blockEntities.length === 0) {
      return <span>{block.text}</span>;
    }

    const elements: React.ReactNode[] = [];
    let lastIdx = 0;

    blockEntities.forEach((ent, i) => {
      // Text before entity
      if (ent.start > lastIdx) {
        elements.push(
          <span key={`txt_${i}`}>{block.text.substring(lastIdx, ent.start)}</span>
        );
      }

      // Entity highlight mark
      elements.push(
        <mark
          key={`ent_${ent.id}`}
          onClick={(e) => {
            e.stopPropagation();
            onToggleEntity(ent.id);
          }}
          title={`Click to ${ent.is_active ? 'unhighlight' : 'highlight'} (${ent.type} -> ${ent.placeholder})`}
          className={`px-1.5 py-0.5 rounded text-xs font-mono font-medium cursor-pointer transition-all select-none ${
            ent.is_active
              ? ent.is_manual
                ? 'bg-purple-200 text-purple-950 border border-purple-300 hover:bg-purple-300'
                : 'bg-amber-200 text-amber-950 border border-amber-300 hover:bg-amber-300'
              : 'bg-slate-200 text-slate-400 line-through hover:bg-slate-300'
          }`}
        >
          {ent.text}
          <span className="ml-1 text-[9px] font-bold opacity-75">
            ({ent.placeholder})
          </span>
        </mark>
      );
      lastIdx = ent.end;
    });

    if (lastIdx < block.text.length) {
      elements.push(
        <span key="txt_end">{block.text.substring(lastIdx)}</span>
      );
    }

    return elements;
  };

  return (
    <div className="space-y-4">
      {/* Action Toolbar */}
      <div className="bg-white border border-slate-200 rounded-xl p-3 sm:p-4 shadow-2xs flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Left: Stats & Status */}
        <div className="flex items-center space-x-3 flex-wrap gap-2">
          <div className="flex items-center space-x-2 text-xs">
            <span className="font-semibold text-slate-800">{activeEntitiesCount}</span>
            <span className="text-slate-500">of {entities.length} items redacted</span>
            <span className="text-slate-300">|</span>
            <span className="text-indigo-600 font-mono text-[11px] font-semibold bg-indigo-50 px-2 py-0.5 rounded">
              Typed Placeholders: [TYPE N]
            </span>
          </div>

          {hiddenBlocksCount > 0 && (
            <button
              type="button"
              onClick={onToggleIncludeHidden}
              className={`flex items-center space-x-1.5 text-xs px-2.5 py-1 rounded-lg border transition-all cursor-pointer ${
                includeHidden
                  ? 'bg-indigo-50 border-indigo-200 text-indigo-700 font-medium'
                  : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'
              }`}
            >
              {includeHidden ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
              <span>{includeHidden ? 'Hidden Content Included' : `Exclude Hidden (${hiddenBlocksCount})`}</span>
            </button>
          )}
        </div>

        {/* Right: Actions */}
        <div className="flex items-center space-x-2">
          {onAddQuickNote && (
            <button
              type="button"
              onClick={() => setShowQuickNoteModal(true)}
              className="flex items-center space-x-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 px-3 py-2 rounded-lg transition-colors shadow-2xs cursor-pointer"
              title="Add a legal observation or note to this document"
            >
              <Plus className="w-3.5 h-3.5 text-slate-500" />
              <span>Add Note</span>
            </button>
          )}

          <button
            type="button"
            onClick={onSaveDocument || handleDownloadRedacted}
            className="flex items-center space-x-1.5 text-xs font-semibold text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 px-3.5 py-2 rounded-lg transition-colors shadow-2xs cursor-pointer"
            title="Save and download the protected document"
          >
            <Check className="w-3.5 h-3.5 text-emerald-600" />
            <span>Save Document</span>
          </button>

          <button
            type="button"
            onClick={onProceedToAI}
            disabled={unresolvedUncertainCount > 0}
            className={`flex items-center space-x-1.5 text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors cursor-pointer ${
              unresolvedUncertainCount > 0
                ? 'bg-slate-200 text-slate-400 cursor-not-allowed border border-slate-300'
                : 'bg-indigo-600 hover:bg-indigo-700 text-white'
            }`}
            title={unresolvedUncertainCount > 0 ? `Please confirm or dismiss ${unresolvedUncertainCount} uncertain item(s) before proceeding` : 'Proceed to AI Assistant'}
          >
            {unresolvedUncertainCount > 0 ? (
              <span className="flex items-center space-x-1">
                <span>Gate: Resolve {unresolvedUncertainCount} Uncertain Items</span>
              </span>
            ) : (
              <span>Open in AI Assistant</span>
            )}
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Quick Note Creation Modal */}
      {showQuickNoteModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-2xs flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-md w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                Add Note to Matter
              </h4>
              <button
                onClick={() => setShowQuickNoteModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                  Note Title
                </label>
                <input
                  type="text"
                  value={quickNoteTitle}
                  onChange={(e) => setQuickNoteTitle(e.target.value)}
                  placeholder="e.g. Identity & Redaction Observations"
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                  Observations / Content
                </label>
                <textarea
                  value={quickNoteText}
                  onChange={(e) => setQuickNoteText(e.target.value)}
                  placeholder="Add your legal notes, client instructions, or compliance reminders..."
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 min-h-[100px]"
                />
              </div>
            </div>

            <div className="flex justify-end space-x-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowQuickNoteModal(false)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!quickNoteText.trim()}
                onClick={() => {
                  if (onAddQuickNote && quickNoteText.trim()) {
                    onAddQuickNote(quickNoteTitle.trim() || 'Matter Note', quickNoteText.trim());
                    setQuickNoteTitle('');
                    setQuickNoteText('');
                    setShowQuickNoteModal(false);
                    setNoteSavedToast(true);
                    setTimeout(() => setNoteSavedToast(false), 3000);
                  }
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg cursor-pointer"
              >
                Save Note
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Note Saved Toast */}
      {noteSavedToast && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs rounded-xl p-3 flex items-center justify-between shadow-2xs">
          <span>✓ Note saved to matter workspace!</span>
        </div>
      )}

      {/* Floating / Active Selection Banner for Manual Highlighting */}
      {selectedText && (
        <div className="bg-indigo-600 text-white rounded-xl px-4 py-3 flex items-center justify-between shadow-md animate-in fade-in slide-in-from-top-2 duration-150">
          <div className="flex items-center space-x-2 text-xs truncate mr-4">
            <span className="font-semibold uppercase tracking-wider text-[10px] bg-white/20 px-2 py-0.5 rounded">
              Selected Text
            </span>
            <span className="font-mono bg-indigo-700/80 px-2 py-0.5 rounded max-w-xs truncate">
              &quot;{selectedText}&quot;
            </span>
          </div>

          <button
            onClick={handleManualHighlightClick}
            className="flex items-center space-x-1.5 bg-white text-indigo-700 hover:bg-indigo-50 text-xs font-bold px-3.5 py-1.5 rounded-lg shadow-sm transition-colors cursor-pointer flex-shrink-0"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Redact Selection (as XXX/XYZ)</span>
          </button>
        </div>
      )}

      {/* Main Studio Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Side: Original Document & Selection */}
        <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl shadow-2xs flex flex-col h-[680px]">
          <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="w-2.5 h-2.5 rounded-full bg-slate-400"></span>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Original Document
              </h4>
            </div>
            <span className="text-[11px] text-slate-500">
              Select any text to redact • Click highlights to toggle
            </span>
          </div>

          <div
            onMouseUp={handleMouseUp}
            className="p-4 overflow-y-auto space-y-3 flex-1 font-sans text-sm text-slate-800 leading-relaxed select-text"
          >
            {displayBlocks.map((block) => (
              <div
                key={block.id}
                data-block-id={block.id}
                className={`p-3 rounded-lg border transition-colors ${
                  block.visibility !== 'visible'
                    ? 'bg-amber-50/50 border-amber-200 text-slate-700'
                    : 'bg-slate-50/40 border-slate-100 hover:border-slate-300'
                }`}
              >
                {block.visibility !== 'visible' && (
                  <span className="text-[10px] uppercase font-mono font-bold text-amber-700 mr-2">
                    [{block.type}]
                  </span>
                )}
                {renderOriginalText(block)}
              </div>
            ))}
          </div>
        </div>

        {/* Center: Redaction Inspector & Manual Term Controller */}
        <div className="lg:col-span-3 bg-white border border-slate-200 rounded-xl shadow-2xs flex flex-col h-[680px]">
          <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-indigo-600" />
              Redacted Items ({entities.length})
            </h4>
          </div>

          {/* Quick Add Custom Word/Phrase to Redact */}
          <div className="p-2.5 border-b border-slate-100 bg-slate-50/50">
            <form onSubmit={handleAddCustomTermSubmit} className="flex items-center space-x-1.5">
              <input
                type="text"
                value={customTerm}
                onChange={(e) => setCustomTerm(e.target.value)}
                placeholder="Type word/phrase to redact..."
                className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 bg-white"
              />
              <button
                type="submit"
                disabled={!customTerm.trim()}
                className="bg-indigo-600 text-white p-1.5 rounded-lg hover:bg-indigo-700 disabled:opacity-40 cursor-pointer flex-shrink-0"
                title="Add Redaction Term"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>

          {/* Type Filter & Search */}
          <div className="p-2 border-b border-slate-100 space-y-1.5">
            <div className="relative">
              <Search className="w-3 h-3 text-slate-400 absolute left-2.5 top-2.5" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter entities..."
                className="w-full text-[11px] pl-7 pr-2.5 py-1.5 rounded-md border border-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div className="flex flex-wrap gap-1">
              <button
                onClick={() => setSelectedTypeFilter('ALL')}
                className={`text-[10px] px-2 py-0.5 rounded font-medium cursor-pointer ${
                  selectedTypeFilter === 'ALL'
                    ? 'bg-slate-800 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                All ({entities.length})
              </button>
              {entityTypes.map((t) => (
                <button
                  key={t}
                  onClick={() => setSelectedTypeFilter(t)}
                  className={`text-[10px] px-2 py-0.5 rounded font-medium cursor-pointer ${
                    selectedTypeFilter === t
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Deliverable 5: Uncertain Items Resolution Gate */}
          {unresolvedUncertainCount > 0 && (
            <div className="m-2 p-3 rounded-lg bg-amber-50 border border-amber-200 space-y-2">
              <div className="flex items-center justify-between text-xs font-bold text-amber-900">
                <span className="flex items-center space-x-1.5">
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
                  <span>Uncertain Items Gate ({unresolvedUncertainCount} pending)</span>
                </span>
              </div>
              <p className="text-[11px] text-amber-800 leading-normal">
                Confirm or dismiss each uncertain detection below before proceeding to AI dispatch.
              </p>
              <div className="space-y-1.5 pt-1">
                {uncertainGroups.map((grp) => (
                  <div key={`unc_${grp.key}`} className="flex items-center justify-between gap-2 p-2 rounded bg-white border border-amber-200 text-xs">
                    <div className="overflow-hidden">
                      <div className="font-semibold text-slate-900 truncate">{grp.text}</div>
                      <div className="text-[10px] text-slate-500">{grp.type} (Tier: Uncertain)</div>
                    </div>
                    <div className="flex items-center space-x-1 flex-shrink-0">
                      <button
                        type="button"
                        onClick={() => handleConfirmUncertain(grp.key, grp.ids)}
                        className="px-2 py-1 rounded text-[10px] font-semibold bg-emerald-600 text-white hover:bg-emerald-700 cursor-pointer shadow-2xs"
                        title="Confirm redaction for all instances"
                      >
                        Confirm
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDismissUncertain(grp.key, grp.ids)}
                        className="px-2 py-1 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200 border border-slate-300 cursor-pointer"
                        title="Dismiss and keep clear"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Deduplicated Entity Cards List (Deliverable 5) */}
          <div className="p-2 overflow-y-auto space-y-1.5 flex-1 text-xs">
            {filteredGroups.length === 0 ? (
              <div className="text-center py-8 text-slate-400 text-xs">
                No matching redacted items found.
              </div>
            ) : (
              filteredGroups.map((grp) => (
                <div
                  key={grp.key}
                  className={`p-2.5 rounded-lg border transition-all flex items-center justify-between gap-2 ${
                    grp.isActive
                      ? grp.isManual
                        ? 'bg-purple-50/80 border-purple-200 text-slate-900'
                        : 'bg-amber-50/70 border-amber-200 text-slate-900'
                      : 'bg-slate-50 border-slate-200 text-slate-400 opacity-60'
                  }`}
                >
                  <div
                    onClick={() => handleToggleGroup(grp)}
                    className="space-y-0.5 overflow-hidden flex-1 cursor-pointer"
                  >
                    <div className="flex items-center space-x-1.5">
                      <span className="font-medium truncate text-xs">{grp.text}</span>
                      {grp.count > 1 && (
                        <span className="text-[9px] font-semibold px-1.5 py-0.2 rounded-full bg-slate-200 text-slate-700">
                          {grp.count}×
                        </span>
                      )}
                    </div>
                    <div className="flex items-center space-x-1.5 text-[10px] font-mono">
                      <span className="text-slate-500 font-semibold">{grp.type}</span>
                      <span className="text-slate-300">→</span>
                      <span className="text-indigo-600 font-bold bg-indigo-50/60 px-1 rounded">
                        {grp.placeholder}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center space-x-1 flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => handleToggleGroup(grp)}
                      className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] transition-colors cursor-pointer ${
                        grp.isActive
                          ? 'bg-emerald-500 text-white'
                          : 'bg-slate-200 text-slate-500 hover:bg-slate-300'
                      }`}
                      title={grp.isActive ? 'Click to unhighlight all mentions' : 'Click to highlight all mentions'}
                    >
                      {grp.isActive ? <Check className="w-3 h-3" /> : '×'}
                    </button>

                    <button
                      type="button"
                      onClick={() => grp.ids.forEach((id) => onRemoveEntity(id))}
                      className="w-5 h-5 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center transition-colors cursor-pointer"
                      title="Permanently remove all instances of this highlight"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Side: Live Redacted Preview (With XXX / XYZ Jargon) */}
        <div className="lg:col-span-4 bg-white border border-slate-200 rounded-xl shadow-2xs flex flex-col h-[680px]">
          <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Redacted Document Preview
              </h4>
            </div>
            <span className="text-[10px] font-mono font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
              PROTECTED PREVIEW (TYPED PLACEHOLDERS)
            </span>
          </div>

          <div className="p-4 overflow-y-auto space-y-3 flex-1 font-mono text-xs text-slate-700 bg-slate-50/40 leading-relaxed select-text">
            {displayBlocks.map((block) => (
              <div
                key={block.id}
                className="p-3 rounded-lg border border-slate-200 bg-white"
              >
                {generateProtectedBlockText(block, entities)}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
