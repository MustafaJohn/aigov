'use client';

import React from 'react';
import { ShieldCheck, FileText, Bot, Edit3, Download, RotateCcw } from 'lucide-react';

interface HeaderProps {
  onReset: () => void;
  activeSection: 'intake' | 'redaction' | 'ai' | 'notes';
  onNavigateSection: (section: 'intake' | 'redaction' | 'ai' | 'notes') => void;
  documentName?: string;
  hasDocument: boolean;
  notesCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  onReset,
  activeSection,
  onNavigateSection,
  documentName,
  hasDocument,
  notesCount,
}) => {
  return (
    <header className="border-b border-slate-200 bg-white/90 backdrop-blur sticky top-0 z-50 shadow-2xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center space-x-3">
          <div className="h-9 w-9 rounded-xl bg-slate-900 flex items-center justify-center text-white shadow-sm">
            <ShieldCheck className="h-5 w-5 text-indigo-400" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-slate-900 tracking-tight text-lg">LexGateway</span>
              <span className="text-[10px] bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full font-semibold border border-indigo-100">
                Safe AI Workspace
              </span>
            </div>
            <p className="text-[11px] text-slate-500 hidden sm:block">Legal PII Redaction & AI Intelligence</p>
          </div>
        </div>

        {/* Workspace Sections Navigation */}
        {hasDocument && (
          <nav className="flex items-center space-x-1 bg-slate-100/80 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => onNavigateSection('redaction')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeSection === 'redaction'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Redaction Studio</span>
            </button>

            <button
              onClick={() => onNavigateSection('ai')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeSection === 'ai'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Bot className="w-3.5 h-3.5" />
              <span>AI Legal Assistant</span>
            </button>

            <button
              onClick={() => onNavigateSection('notes')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeSection === 'notes'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Notes</span>
              {notesCount > 0 && (
                <span className="ml-1 px-1.5 py-0.2 bg-indigo-100 text-indigo-800 text-[10px] rounded-full font-bold">
                  {notesCount}
                </span>
              )}
            </button>
          </nav>
        )}

        {/* Right Actions */}
        <div className="flex items-center space-x-3">
          {documentName && (
            <div className="hidden lg:flex items-center space-x-1.5 text-xs text-slate-700 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg max-w-xs truncate">
              <FileText className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
              <span className="truncate font-medium">{documentName}</span>
            </div>
          )}

          <button
            onClick={onReset}
            className="flex items-center space-x-1 text-xs text-slate-600 hover:text-slate-900 bg-white border border-slate-200 hover:bg-slate-50 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
            title="Upload New Document"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">New Intake</span>
          </button>
        </div>
      </div>
    </header>
  );
};
