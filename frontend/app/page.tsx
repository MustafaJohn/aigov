'use client';

import React, { useState, useEffect } from 'react';
import { NotionSidebar } from '../components/NotionSidebar';
import { NotionTopBar } from '../components/NotionTopBar';
import { NotionPageHeader } from '../components/NotionPageHeader';
import { IntakeScreen } from '../components/IntakeScreen';
import { GateBanner } from '../components/GateBanner';
import { SideBySideReview } from '../components/SideBySideReview';
import { RedactedOnlyView } from '../components/RedactedOnlyView';
import { AILegalStudio } from '../components/AILegalStudio';
import { AICopilotDrawer } from '../components/AICopilotDrawer';
import { EntityDatabaseTable } from '../components/EntityDatabaseTable';
import { NotesPanel } from '../components/NotesPanel';
import { ExportModal } from '../components/ExportModal';
import { DocumentIR, DetectedEntity, LegalNote } from '../lib/types';
import { compileProtectedDocument, generateNextJargon } from '../lib/restore';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

const DEFAULT_NOTES: LegalNote[] = [
  {
    id: 'note_init_1',
    title: 'Dispute Summary & Escrow Terms',
    content: 'Review ongoing commercial dispute and escrow settlement terms. Ensure SRA compliance undertakings are verified by the senior managing partner prior to any disbursement.',
    created_at: new Date().toLocaleDateString(),
    category: 'Strategy'
  },
  {
    id: 'note_init_2',
    title: 'Bank Facilities Verification',
    content: 'Verify sort code and client account details under UK MLR 2017 before executing settlement transfer.',
    created_at: new Date().toLocaleDateString(),
    category: 'Risk'
  }
];

export default function Home() {
  const [activeView, setActiveView] = useState<'intake' | 'review' | 'redacted_only' | 'ai' | 'notes' | 'database'>('intake');
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [isCopilotOpen, setIsCopilotOpen] = useState<boolean>(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState<boolean>(false);

  const [docIR, setDocIR] = useState<DocumentIR | null>(null);
  const [entities, setEntities] = useState<DetectedEntity[]>([]);
  const [notes, setNotes] = useState<LegalNote[]>(DEFAULT_NOTES);
  const [activeNoteId, setActiveNoteId] = useState<string | null>(DEFAULT_NOTES[0].id);

  const [includeHidden, setIncludeHidden] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [currentProvider, setCurrentProvider] = useState<string>('demo');

  // Load notes from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem('lexgateway_notes');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setNotes(parsed);
          setActiveNoteId(parsed[0].id);
        }
      }
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  // Sync notes to localStorage
  const saveNotes = (updated: LegalNote[]) => {
    setNotes(updated);
    try {
      localStorage.setItem('lexgateway_notes', JSON.stringify(updated));
    } catch {
      // Ignore
    }
  };

  // Reset to Intake
  const handleReset = () => {
    setActiveView('intake');
    setDocIR(null);
    setEntities([]);
    setErrorMessage(null);
  };

  // File Upload Handler
  const handleFileUpload = async (file: File) => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${BACKEND_URL}/api/documents/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error (${res.status})`);
      }

      const data = await res.json();
      setDocIR(data.ir);
      setEntities(data.detection.entities || []);
      setActiveView('review');
    } catch (err: any) {
      setErrorMessage(`Failed to intake document: ${err.message}. Ensure backend is running on ${BACKEND_URL}.`);
    } finally {
      setIsLoading(false);
    }
  };

  // 1-Click Synthetic Case Load
  const handleSyntheticLoad = async (content: string) => {
    const syntheticFile = new File([content], 'Commercial_Dispute_Memo.txt', {
      type: 'text/plain',
    });
    await handleFileUpload(syntheticFile);
  };

  // Toggle Highlight / Unhighlight
  const handleToggleEntity = (entityId: string) => {
    setEntities((prev) =>
      prev.map((e) => (e.id === entityId ? { ...e, is_active: !e.is_active } : e))
    );
  };

  // Permanently Remove an Entity
  const handleRemoveEntity = (entityId: string) => {
    setEntities((prev) => prev.filter((e) => e.id !== entityId));
  };

  // Manual Highlighting (Text selection or custom term input)
  const handleAddManualEntity = (term: string, targetBlockId?: string) => {
    if (!docIR || !term.trim()) return;

    const cleanTerm = term.trim();
    const newEntities: DetectedEntity[] = [];
    const nextJargon = generateNextJargon(entities);

    const blocksToSearch = targetBlockId
      ? docIR.blocks.filter((b) => b.id === targetBlockId)
      : docIR.blocks;

    blocksToSearch.forEach((block) => {
      const text = block.text;
      let startIdx = text.toLowerCase().indexOf(cleanTerm.toLowerCase());

      while (startIdx !== -1) {
        const endIdx = startIdx + cleanTerm.length;
        const matchedSubstring = text.substring(startIdx, endIdx);

        const alreadyExists = entities.some(
          (e) => e.block_id === block.id && e.start === startIdx && e.end === endIdx
        );

        if (!alreadyExists) {
          newEntities.push({
            id: `ent_manual_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
            block_id: block.id,
            start: startIdx,
            end: endIdx,
            text: matchedSubstring,
            type: 'MANUAL',
            placeholder: nextJargon,
            confidence: 1.0,
            is_active: true,
            is_manual: true,
          });
        }

        startIdx = text.toLowerCase().indexOf(cleanTerm.toLowerCase(), endIdx);
      }
    });

    if (newEntities.length > 0) {
      setEntities((prev) => [...prev, ...newEntities]);
    }
  };

  // AI Prompt Execution
  const handleExecutePrompt = async (
    provider: string,
    apiKey: string,
    selectedModel: string,
    prompt: string
  ): Promise<string> => {
    if (!docIR) throw new Error('No document loaded.');
    setCurrentProvider(provider);

    const compiledProtectedText = compileProtectedDocument(
      docIR.blocks,
      entities,
      includeHidden
    );

    const res = await fetch(`${BACKEND_URL}/api/llm/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider,
        api_key: apiKey,
        model: selectedModel,
        protected_text: compiledProtectedText,
        instructions: prompt,
      }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `AI Inference error (${res.status})`);
    }

    const data = await res.json();
    if (!data.success) {
      throw new Error(data.error || 'AI execution failed');
    }

    return data.summary;
  };

  // Notes Handlers
  const handleAddNote = (newNoteData: Omit<LegalNote, 'id' | 'created_at'>) => {
    const newNote: LegalNote = {
      id: `note_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      title: newNoteData.title,
      content: newNoteData.content,
      category: newNoteData.category || 'General',
      created_at: new Date().toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }),
    };
    saveNotes([newNote, ...notes]);
    setActiveNoteId(newNote.id);
  };

  const handleUpdateNote = (id: string, updated: Partial<LegalNote>) => {
    saveNotes(notes.map((n) => (n.id === id ? { ...n, ...updated } : n)));
  };

  const handleDeleteNote = (id: string) => {
    const remaining = notes.filter((n) => n.id !== id);
    saveNotes(remaining);
    if (activeNoteId === id) {
      setActiveNoteId(remaining.length > 0 ? remaining[0].id : null);
    }
  };

  return (
    <div className="flex h-screen bg-white text-[#37352f] overflow-hidden font-sans">
      {/* 1. Left Notion-Style Collapsible Sidebar */}
      <NotionSidebar
        activeView={activeView}
        onSelectView={(v) => setActiveView(v)}
        hasDocument={!!docIR}
        documentName={docIR?.source.filename}
        notes={notes}
        activeNoteId={activeNoteId}
        onSelectNote={(noteId) => {
          setActiveNoteId(noteId);
          setActiveView('notes');
        }}
        onNewNote={() => {
          handleAddNote({ title: 'Untitled Page', content: '', category: 'General' });
          setActiveView('notes');
        }}
        onNewIntake={handleReset}
        isOpen={isSidebarOpen}
        onToggleOpen={() => setIsSidebarOpen(!isSidebarOpen)}
        entitiesCount={entities.length}
        activeEntitiesCount={entities.filter((e) => e.is_active).length}
        provider={currentProvider}
      />

      {/* 2. Main Workspace Canvas Area */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top Notion Breadcrumb & Actions Bar */}
        <NotionTopBar
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          documentName={docIR?.source.filename}
          activeView={activeView}
          onOpenAICopilot={() => setIsCopilotOpen(!isCopilotOpen)}
          isCopilotOpen={isCopilotOpen}
          onOpenExportModal={() => setIsExportModalOpen(true)}
          onNewIntake={handleReset}
          hasDocument={!!docIR}
        />

        {/* Scrollable Document Canvas */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-8 lg:px-12 py-6 bg-white">
          <div className="max-w-6xl mx-auto w-full space-y-4">
            {errorMessage && (
              <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-xl p-3 flex items-center justify-between shadow-2xs">
                <span>{errorMessage}</span>
                <button
                  onClick={() => setErrorMessage(null)}
                  className="text-rose-600 font-bold hover:underline cursor-pointer ml-4"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Document Intake View */}
            {(!docIR || activeView === 'intake') && (
              <IntakeScreen
                onFileUpload={handleFileUpload}
                onSyntheticLoad={handleSyntheticLoad}
                isLoading={isLoading}
              />
            )}

            {/* If Document Loaded: Render Notion Page Properties Header */}
            {docIR && activeView !== 'intake' && (
              <>
                <NotionPageHeader
                  docIR={docIR}
                  entities={entities}
                  activeView={activeView}
                  onSelectView={(v) => setActiveView(v)}
                  notesCount={notes.length}
                />

                {/* View 1: Side-by-Side Review Studio */}
                {activeView === 'review' && (
                  <SideBySideReview
                    blocks={docIR.blocks}
                    entities={entities}
                    onToggleEntity={handleToggleEntity}
                    onAddManualEntity={handleAddManualEntity}
                    onRemoveEntity={handleRemoveEntity}
                    includeHidden={includeHidden}
                    onToggleIncludeHidden={() => setIncludeHidden(!includeHidden)}
                    onProceedToAI={() => setActiveView('ai')}
                  />
                )}

                {/* View 2: Redacted Text Only */}
                {activeView === 'redacted_only' && (
                  <RedactedOnlyView
                    blocks={docIR.blocks}
                    entities={entities}
                    documentName={docIR.source.filename}
                  />
                )}

                {/* View 3: Full-Page Notion AI Studio */}
                {activeView === 'ai' && (
                  <AILegalStudio
                    blocks={docIR.blocks}
                    entities={entities}
                    includeHidden={includeHidden}
                    onExecutePrompt={handleExecutePrompt}
                    onAddToNotes={(title, content, category) => {
                      handleAddNote({ title, content, category });
                      setActiveView('notes');
                    }}
                    isLoading={isLoading}
                  />
                )}

                {/* View 4: Entity Database Table */}
                {activeView === 'database' && (
                  <EntityDatabaseTable
                    entities={entities}
                    onToggleEntity={handleToggleEntity}
                    onRemoveEntity={handleRemoveEntity}
                    onAddManualEntity={handleAddManualEntity}
                  />
                )}

                {/* View 5: Notion Case Notes */}
                {activeView === 'notes' && (
                  <NotesPanel
                    notes={notes}
                    onAddNote={handleAddNote}
                    onUpdateNote={handleUpdateNote}
                    onDeleteNote={handleDeleteNote}
                  />
                )}
              </>
            )}
          </div>
        </main>
      </div>

      {/* 3. Notion AI Copilot Slide-Over Drawer (Right Side) */}
      <AICopilotDrawer
        isOpen={isCopilotOpen}
        onClose={() => setIsCopilotOpen(false)}
        onExecutePrompt={handleExecutePrompt}
        onAddToNotes={(title, content, category) => {
          handleAddNote({ title, content, category });
          setIsCopilotOpen(false);
          setActiveView('notes');
        }}
        isLoading={isLoading}
      />

      {/* 4. Export & Download Hub Modal */}
      <ExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        documentName={docIR?.source.filename}
        blocks={docIR?.blocks || []}
        entities={entities}
        notes={notes}
      />
    </div>
  );
}
