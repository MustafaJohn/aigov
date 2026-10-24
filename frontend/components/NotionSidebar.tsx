'use client';

import React from 'react';
import {
  FileText,
  ShieldCheck,
  Bot,
  Edit3,
  Database,
  Plus,
  Search,
  Upload,
  Settings,
  Sparkles,
  ChevronRight,
  ChevronDown,
  Layers,
  Scale,
  Lock,
  ExternalLink,
  Download,
  PanelLeftClose,
  PanelLeft
} from 'lucide-react';
import { LegalNote } from '../lib/types';

interface NotionSidebarProps {
  activeView: 'intake' | 'review' | 'redacted_only' | 'ai' | 'notes' | 'database';
  onSelectView: (view: 'intake' | 'review' | 'redacted_only' | 'ai' | 'notes' | 'database') => void;
  hasDocument: boolean;
  documentName?: string;
  notes: LegalNote[];
  activeNoteId?: string | null;
  onSelectNote: (noteId: string) => void;
  onNewNote: () => void;
  onNewIntake: () => void;
  isOpen: boolean;
  onToggleOpen: () => void;
  entitiesCount: number;
  activeEntitiesCount: number;
  provider: string;
}

export const NotionSidebar: React.FC<NotionSidebarProps> = ({
  activeView,
  onSelectView,
  hasDocument,
  documentName,
  notes,
  activeNoteId,
  onSelectNote,
  onNewNote,
  onNewIntake,
  isOpen,
  onToggleOpen,
  entitiesCount,
  activeEntitiesCount,
  provider,
}) => {
  if (!isOpen) {
    return (
      <div className="fixed top-3 left-3 z-50">
        <button
          onClick={onToggleOpen}
          className="p-1.5 rounded-lg bg-white/90 hover:bg-slate-100 border border-slate-200 text-slate-600 shadow-2xs transition-colors cursor-pointer"
          title="Expand Sidebar"
        >
          <PanelLeft className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <aside className="w-64 bg-[#f7f7f5] border-r border-[#e9e9e7] flex flex-col h-screen select-none text-[#37352f] transition-all flex-shrink-0 z-40">
      {/* Workspace Header */}
      <div className="p-3 border-b border-[#e9e9e7]/70 flex items-center justify-between">
        <div className="flex items-center space-x-2.5 truncate">
          <div className="w-6 h-6 rounded-md bg-[#37352f] text-white flex items-center justify-center font-bold text-xs shadow-2xs">
            ⚖️
          </div>
          <div className="truncate">
            <h1 className="text-xs font-semibold text-[#37352f] leading-tight truncate">
              LexGateway Legal
            </h1>
            <p className="text-[10px] text-[#787774] truncate">Private Legal Workspace</p>
          </div>
        </div>

        <button
          onClick={onToggleOpen}
          className="p-1 rounded hover:bg-[#efefed] text-[#787774] hover:text-[#37352f] transition-colors cursor-pointer"
          title="Collapse Sidebar"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Quick Action Buttons */}
      <div className="p-2 space-y-0.5">
        <button
          onClick={onNewIntake}
          className="w-full flex items-center space-x-2 text-xs text-[#37352f] hover:bg-[#efefed] px-2.5 py-1.5 rounded-md transition-colors cursor-pointer font-medium"
        >
          <Upload className="w-3.5 h-3.5 text-[#787774]" />
          <span>Intake New Document</span>
        </button>

        <button
          onClick={onNewNote}
          className="w-full flex items-center space-x-2 text-xs text-[#37352f] hover:bg-[#efefed] px-2.5 py-1.5 rounded-md transition-colors cursor-pointer font-medium"
        >
          <Plus className="w-3.5 h-3.5 text-[#787774]" />
          <span>New Note Page</span>
        </button>
      </div>

      {/* Workspace Navigation Links */}
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-4 text-xs">
        {/* Core Views */}
        <div>
          <div className="px-2 pb-1 text-[10px] font-bold text-[#787774] uppercase tracking-wider">
            Workspace Views
          </div>

          <div className="space-y-0.5">
            <button
              onClick={() => onSelectView('intake')}
              className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-md transition-colors cursor-pointer ${
                activeView === 'intake'
                  ? 'bg-[#efefed] font-semibold text-[#37352f]'
                  : 'text-[#5f5e5b] hover:bg-[#efefed] hover:text-[#37352f]'
              }`}
            >
              <div className="flex items-center space-x-2">
                <FileText className="w-3.5 h-3.5 text-[#787774]" />
                <span>Intake & Parsing</span>
              </div>
            </button>

            {hasDocument && (
              <>
                <button
                  onClick={() => onSelectView('review')}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-md transition-colors cursor-pointer ${
                    activeView === 'review'
                      ? 'bg-[#efefed] font-semibold text-[#37352f]'
                      : 'text-[#5f5e5b] hover:bg-[#efefed] hover:text-[#37352f]'
                  }`}
                >
                  <div className="flex items-center space-x-2 truncate">
                    <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
                    <span className="truncate">Redaction Studio</span>
                  </div>
                  {activeEntitiesCount > 0 && (
                    <span className="text-[10px] bg-amber-100 text-amber-900 px-1.5 py-0.2 rounded font-mono font-medium">
                      {activeEntitiesCount}
                    </span>
                  )}
                </button>

                <button
                  onClick={() => onSelectView('database')}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-md transition-colors cursor-pointer ${
                    activeView === 'database'
                      ? 'bg-[#efefed] font-semibold text-[#37352f]'
                      : 'text-[#5f5e5b] hover:bg-[#efefed] hover:text-[#37352f]'
                  }`}
                >
                  <div className="flex items-center space-x-2">
                    <Database className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Entity Database</span>
                  </div>
                  <span className="text-[10px] text-[#787774]">Table</span>
                </button>

                <button
                  onClick={() => onSelectView('ai')}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-md transition-colors cursor-pointer ${
                    activeView === 'ai'
                      ? 'bg-[#efefed] font-semibold text-[#37352f]'
                      : 'text-[#5f5e5b] hover:bg-[#efefed] hover:text-[#37352f]'
                  }`}
                >
                  <div className="flex items-center space-x-2">
                    <Bot className="w-3.5 h-3.5 text-purple-600" />
                    <span>Notion AI Copilot</span>
                  </div>
                  <span className="text-[9px] bg-purple-100 text-purple-800 px-1.5 py-0.2 rounded font-semibold">
                    1-Click
                  </span>
                </button>
              </>
            )}

            <button
              onClick={() => onSelectView('notes')}
              className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-md transition-colors cursor-pointer ${
                activeView === 'notes'
                  ? 'bg-[#efefed] font-semibold text-[#37352f]'
                  : 'text-[#5f5e5b] hover:bg-[#efefed] hover:text-[#37352f]'
              }`}
            >
              <div className="flex items-center space-x-2">
                <Edit3 className="w-3.5 h-3.5 text-amber-600" />
                <span>Case Notes</span>
              </div>
              {notes.length > 0 && (
                <span className="text-[10px] text-[#787774] font-medium">
                  {notes.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* Current Active Document */}
        {hasDocument && (
          <div>
            <div className="px-2 pb-1 text-[10px] font-bold text-[#787774] uppercase tracking-wider flex items-center justify-between">
              <span>Active Document</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            </div>

            <div className="px-2.5 py-2 rounded-md bg-white border border-[#e9e9e7] space-y-1">
              <div className="flex items-center space-x-1.5 text-xs font-semibold text-[#37352f] truncate">
                <span>📄</span>
                <span className="truncate">{documentName || 'Document'}</span>
              </div>
              <div className="flex items-center justify-between text-[10px] text-[#787774]">
                <span>Masked: XXX / XYZ</span>
                <span className="font-mono text-emerald-700 font-medium">Ready</span>
              </div>
            </div>
          </div>
        )}

        {/* Recent Notes Pages */}
        <div>
          <div className="px-2 pb-1 text-[10px] font-bold text-[#787774] uppercase tracking-wider flex items-center justify-between">
            <span>Notes Pages</span>
            <button
              onClick={onNewNote}
              className="text-[#787774] hover:text-[#37352f] cursor-pointer"
              title="Add Note Page"
            >
              <Plus className="w-3 h-3" />
            </button>
          </div>

          <div className="space-y-0.5">
            {notes.map((note) => (
              <button
                key={note.id}
                onClick={() => {
                  onSelectNote(note.id);
                  onSelectView('notes');
                }}
                className={`w-full flex items-center space-x-2 px-2.5 py-1.5 rounded-md text-left transition-colors cursor-pointer truncate ${
                  activeView === 'notes' && activeNoteId === note.id
                    ? 'bg-[#efefed] font-semibold text-[#37352f]'
                    : 'text-[#5f5e5b] hover:bg-[#efefed] hover:text-[#37352f]'
                }`}
              >
                <span className="text-xs">
                  {note.category === 'Risk' ? '⚠️' : note.category === 'Strategy' ? '⚖️' : note.category === 'AI Insight' ? '💡' : '📝'}
                </span>
                <span className="truncate flex-1">{note.title}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Footer / Model BYOK Indicator */}
      <div className="p-3 border-t border-[#e9e9e7] bg-[#f7f7f5] text-xs text-[#787774] flex items-center justify-between">
        <div className="flex items-center space-x-2 truncate">
          <div className="w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0"></div>
          <span className="truncate text-[11px]">
            Model: <strong className="text-[#37352f] capitalize">{provider}</strong>
          </span>
        </div>

        <div className="text-[10px] bg-[#efefed] text-[#37352f] px-2 py-0.5 rounded font-mono border border-[#e9e9e7]">
          BYOK
        </div>
      </div>
    </aside>
  );
};
