'use client';

import React, { useState } from 'react';
import {
  Edit3,
  Plus,
  Trash2,
  Download,
  Copy,
  Check,
  Clock,
  FileText,
  Tag,
  Sparkles
} from 'lucide-react';
import { LegalNote } from '../lib/types';
import { downloadTextFile } from '../lib/restore';

interface NotesPanelProps {
  notes: LegalNote[];
  onAddNote: (note: Omit<LegalNote, 'id' | 'created_at'>) => void;
  onUpdateNote: (id: string, updated: Partial<LegalNote>) => void;
  onDeleteNote: (id: string) => void;
}

const CATEGORY_EMOJIS: Record<string, string> = {
  General: '📝',
  Risk: '⚠️',
  Strategy: '⚖️',
  Obligations: '📌',
  'AI Insight': '💡',
};

export const NotesPanel: React.FC<NotesPanelProps> = ({
  notes,
  onAddNote,
  onUpdateNote,
  onDeleteNote,
}) => {
  const [activeNoteId, setActiveNoteId] = useState<string | null>(
    notes.length > 0 ? notes[0].id : null
  );
  const [newTitle, setNewTitle] = useState<string>('');
  const [newContent, setNewContent] = useState<string>('');
  const [newCategory, setNewCategory] = useState<LegalNote['category']>('General');
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  const activeNote = notes.find((n) => n.id === activeNoteId);

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    onAddNote({
      title: newTitle.trim(),
      content: newContent.trim(),
      category: newCategory,
    });

    setNewTitle('');
    setNewContent('');
    setIsCreating(false);
  };

  const handleDownloadAllNotes = () => {
    if (notes.length === 0) return;
    const compiled = notes
      .map(
        (n) =>
          `# ${CATEGORY_EMOJIS[n.category || 'General']} ${n.title} [${n.category || 'General'}]\n*Created: ${n.created_at}*\n\n${n.content}\n\n---\n`
      )
      .join('\n');
    downloadTextFile(compiled, `matter-case-notes-${Date.now()}.md`);
  };

  const handleCopyNote = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-4">
      {/* Notion Page View Layout */}
      <div className="bg-white border border-[#e9e9e7] rounded-2xl shadow-2xs overflow-hidden flex flex-col md:flex-row h-[720px]">
        {/* Left Sub-Sidebar: Notion Notes Pages List */}
        <div className="w-full md:w-72 bg-[#f7f7f5] border-r border-[#e9e9e7] flex flex-col flex-shrink-0">
          <div className="p-3 border-b border-[#e9e9e7] flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-sm">📑</span>
              <span className="text-xs font-bold text-[#37352f] uppercase tracking-wider">
                Case Pages ({notes.length})
              </span>
            </div>

            <button
              onClick={() => setIsCreating(true)}
              className="p-1 rounded hover:bg-[#efefed] text-[#787774] hover:text-[#37352f] transition-colors cursor-pointer"
              title="Add New Note Page"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          <div className="p-2 overflow-y-auto space-y-1 flex-1">
            {notes.length === 0 ? (
              <div className="text-center py-16 text-[#787774] text-xs space-y-2">
                <FileText className="w-8 h-8 mx-auto text-[#b4b2ac]" />
                <p>No notes created yet.</p>
                <button
                  onClick={() => setIsCreating(true)}
                  className="text-indigo-600 font-semibold hover:underline text-xs cursor-pointer"
                >
                  Create your first note page
                </button>
              </div>
            ) : (
              notes.map((n) => (
                <div
                  key={n.id}
                  onClick={() => {
                    setActiveNoteId(n.id);
                    setIsCreating(false);
                  }}
                  className={`p-2.5 rounded-lg border transition-all cursor-pointer flex flex-col space-y-1 ${
                    activeNoteId === n.id && !isCreating
                      ? 'bg-white border-[#d3d1cb] shadow-2xs text-[#37352f]'
                      : 'bg-transparent border-transparent hover:bg-[#efefed] text-[#5f5e5b]'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-1.5 truncate">
                      <span className="text-sm flex-shrink-0">
                        {CATEGORY_EMOJIS[n.category || 'General'] || '📝'}
                      </span>
                      <span className="font-semibold text-xs truncate max-w-[150px]">
                        {n.title}
                      </span>
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteNote(n.id);
                        if (activeNoteId === n.id) {
                          const remaining = notes.filter((item) => item.id !== n.id);
                          setActiveNoteId(remaining.length > 0 ? remaining[0].id : null);
                        }
                      }}
                      className="text-[#b4b2ac] hover:text-rose-600 p-0.5 rounded cursor-pointer"
                      title="Delete Note"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>

                  <p className="text-[11px] text-[#787774] line-clamp-1 pl-5">
                    {n.content || '(Empty page)'}
                  </p>
                </div>
              ))
            )}
          </div>

          {notes.length > 0 && (
            <div className="p-2.5 border-t border-[#e9e9e7] bg-[#f7f7f5]">
              <button
                onClick={handleDownloadAllNotes}
                className="w-full flex items-center justify-center space-x-1.5 py-1.5 px-3 rounded-lg border border-[#e9e9e7] hover:bg-[#efefed] text-xs text-[#37352f] transition-colors cursor-pointer"
              >
                <Download className="w-3.5 h-3.5 text-[#787774]" />
                <span>Download All Notes (.md)</span>
              </button>
            </div>
          )}
        </div>

        {/* Right Canvas: Notion Page Canvas */}
        <div className="flex-1 bg-white flex flex-col overflow-y-auto">
          {isCreating ? (
            /* Notion New Page Form */
            <form onSubmit={handleCreateSubmit} className="p-6 sm:p-8 flex-1 flex flex-col space-y-5 max-w-3xl mx-auto w-full">
              <div className="flex items-center justify-between border-b border-[#e9e9e7] pb-3">
                <div className="flex items-center space-x-2">
                  <span className="text-2xl">📝</span>
                  <span className="text-xs font-bold uppercase tracking-wider text-[#787774]">
                    New Legal Note Page
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  className="text-xs text-[#787774] hover:text-[#37352f] cursor-pointer"
                >
                  Cancel
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-[#787774] uppercase mb-1">
                    Page Title
                  </label>
                  <input
                    type="text"
                    required
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    placeholder="e.g. Escrow Undertakings & Risk Assessment"
                    className="w-full text-xs px-3 py-2 rounded-lg border border-[#e9e9e7] focus:outline-none focus:ring-1 focus:ring-[#37352f]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-[#787774] uppercase mb-1">
                    Category Tag
                  </label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value as any)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-[#e9e9e7] focus:outline-none focus:ring-1 focus:ring-[#37352f] bg-white text-[#37352f]"
                  >
                    <option value="General">📝 General</option>
                    <option value="Risk">⚠️ Risk & Liability</option>
                    <option value="Strategy">⚖️ Legal Strategy</option>
                    <option value="Obligations">📌 Obligations & Deadlines</option>
                    <option value="AI Insight">💡 AI Insight</option>
                  </select>
                </div>
              </div>

              <div className="flex-1 flex flex-col">
                <label className="block text-[11px] font-semibold text-[#787774] uppercase mb-1">
                  Page Content
                </label>
                <textarea
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  placeholder="Start typing your legal thoughts, notes, case citations, or paste analysis from the AI Copilot..."
                  className="w-full flex-1 text-xs sm:text-sm px-4 py-3 rounded-lg border border-[#e9e9e7] focus:outline-none focus:ring-1 focus:ring-[#37352f] leading-relaxed font-sans resize-none min-h-[300px]"
                />
              </div>

              <div className="flex justify-end space-x-2 pt-3 border-t border-[#e9e9e7]">
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  className="px-3.5 py-2 text-xs font-medium text-[#787774] hover:bg-[#efefed] rounded-lg cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs font-semibold text-white bg-[#37352f] hover:bg-[#5f5e5b] rounded-lg cursor-pointer shadow-2xs"
                >
                  Save Page
                </button>
              </div>
            </form>
          ) : activeNote ? (
            /* Notion Page View / Live Editor */
            <div className="p-6 sm:p-10 flex-1 flex flex-col max-w-3xl mx-auto w-full space-y-4">
              {/* Top Action Bar */}
              <div className="flex items-center justify-between text-xs text-[#787774] pb-2 border-b border-[#e9e9e7]/50">
                <div className="flex items-center space-x-2">
                  <span className="text-xs bg-[#f7f7f5] px-2 py-0.5 rounded border border-[#e9e9e7] font-medium">
                    {CATEGORY_EMOJIS[activeNote.category || 'General']} {activeNote.category || 'General'}
                  </span>
                  <span>Created: {activeNote.created_at}</span>
                </div>

                <div className="flex items-center space-x-1">
                  <button
                    onClick={() => handleCopyNote(activeNote.content)}
                    className="p-1 hover:bg-[#efefed] rounded cursor-pointer"
                    title="Copy content"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>

                  <button
                    onClick={() =>
                      downloadTextFile(
                        activeNote.content,
                        `${activeNote.title.toLowerCase().replace(/\s+/g, '-')}.md`
                      )
                    }
                    className="p-1 hover:bg-[#efefed] rounded cursor-pointer"
                    title="Download Markdown"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>

                  <button
                    onClick={() => onDeleteNote(activeNote.id)}
                    className="p-1 hover:bg-rose-50 hover:text-rose-600 rounded cursor-pointer"
                    title="Delete page"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Notion Page Title & Icon */}
              <div className="flex items-center space-x-3 pt-2">
                <span className="text-3xl select-none">
                  {CATEGORY_EMOJIS[activeNote.category || 'General'] || '📝'}
                </span>
                <input
                  type="text"
                  value={activeNote.title}
                  onChange={(e) => onUpdateNote(activeNote.id, { title: e.target.value })}
                  placeholder="Untitled Page"
                  className="text-2xl font-bold text-[#37352f] border-none bg-transparent focus:outline-none focus:ring-0 p-0 w-full"
                />
              </div>

              {/* Notion Page Content Textarea */}
              <div className="flex-1 flex flex-col pt-2">
                <textarea
                  value={activeNote.content}
                  onChange={(e) => onUpdateNote(activeNote.id, { content: e.target.value })}
                  placeholder="Write your legal observations, analysis, and notes..."
                  className="w-full flex-1 text-sm text-[#37352f] leading-relaxed font-sans border-none focus:outline-none focus:ring-0 p-0 resize-none min-h-[400px]"
                />
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-[#787774] text-xs space-y-2">
              <FileText className="w-10 h-10 text-[#d3d1cb]" />
              <p>Select a note page or click + to create a new one.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
