'use client';

import React, { useState } from 'react';
import {
  PanelLeft,
  PanelLeftClose,
  Download,
  Bot,
  RotateCcw,
  Sparkles,
  ChevronRight,
  Share2,
  FileText,
  Check,
  Lock
} from 'lucide-react';

interface NotionTopBarProps {
  isSidebarOpen: boolean;
  onToggleSidebar: () => void;
  documentName?: string;
  activeView: string;
  onOpenAICopilot: () => void;
  isCopilotOpen: boolean;
  onOpenExportModal: () => void;
  onNewIntake: () => void;
  hasDocument: boolean;
}

export const NotionTopBar: React.FC<NotionTopBarProps> = ({
  isSidebarOpen,
  onToggleSidebar,
  documentName,
  activeView,
  onOpenAICopilot,
  isCopilotOpen,
  onOpenExportModal,
  onNewIntake,
  hasDocument,
}) => {
  const getViewLabel = (view: string) => {
    switch (view) {
      case 'intake':
        return 'Document Intake';
      case 'review':
        return 'Redaction Studio';
      case 'database':
        return 'Entity Database';
      case 'ai':
        return 'Notion AI Copilot';
      case 'notes':
        return 'Case Notes';
      default:
        return 'Workspace';
    }
  };

  return (
    <header className="h-11 border-b border-[#e9e9e7] bg-white px-3 flex items-center justify-between text-xs text-[#37352f] sticky top-0 z-30 select-none">
      {/* Left: Sidebar Toggle & Breadcrumbs */}
      <div className="flex items-center space-x-2 truncate">
        <button
          onClick={onToggleSidebar}
          className="p-1 rounded hover:bg-[#efefed] text-[#787774] hover:text-[#37352f] transition-colors cursor-pointer"
          title={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {isSidebarOpen ? (
            <PanelLeftClose className="w-4 h-4" />
          ) : (
            <PanelLeft className="w-4 h-4" />
          )}
        </button>

        {/* Breadcrumb Trail */}
        <div className="flex items-center space-x-1.5 text-[#787774] text-xs truncate">
          <span className="hover:text-[#37352f] cursor-pointer">LexGateway</span>
          <ChevronRight className="w-3 h-3 text-[#b4b2ac]" />

          {documentName && (
            <>
              <span className="hover:text-[#37352f] cursor-pointer max-w-[150px] sm:max-w-[200px] truncate">
                {documentName}
              </span>
              <ChevronRight className="w-3 h-3 text-[#b4b2ac]" />
            </>
          )}

          <span className="font-semibold text-[#37352f] truncate">
            {getViewLabel(activeView)}
          </span>
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center space-x-1.5">
        {hasDocument && (
          <>
            {/* Toggle AI Copilot Side Drawer */}
            <button
              onClick={onOpenAICopilot}
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer ${
                isCopilotOpen
                  ? 'bg-purple-100 text-purple-900 font-semibold'
                  : 'text-[#37352f] hover:bg-[#efefed]'
              }`}
              title="Toggle Notion AI Copilot Drawer"
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-600" />
              <span className="hidden sm:inline">Ask AI</span>
            </button>

            {/* Export & Download Menu */}
            <button
              onClick={onOpenExportModal}
              className="flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs text-[#37352f] hover:bg-[#efefed] transition-colors cursor-pointer"
              title="Download & Export Hub"
            >
              <Download className="w-3.5 h-3.5 text-[#787774]" />
              <span className="hidden sm:inline">Export</span>
            </button>
          </>
        )}

        <button
          onClick={onNewIntake}
          className="flex items-center space-x-1 px-2 py-1 rounded-md text-xs text-[#787774] hover:text-[#37352f] hover:bg-[#efefed] transition-colors cursor-pointer"
          title="New Intake / Upload"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span className="hidden md:inline">Reset</span>
        </button>
      </div>
    </header>
  );
};
