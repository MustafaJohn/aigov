'use client';

import React, { useState } from 'react';
import {
  Sparkles,
  X,
  Send,
  Loader2,
  Copy,
  Check,
  Download,
  PlusCircle,
  RotateCcw,
  Bot
} from 'lucide-react';
import { AIChatMessage, SelfPromptAction } from '../lib/types';
import { downloadTextFile } from '../lib/restore';

interface AICopilotDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onExecutePrompt: (provider: string, apiKey: string, model: string, prompt: string) => Promise<string>;
  onAddToNotes: (title: string, content: string, category?: any) => void;
  isLoading: boolean;
}

const QUICK_SELF_PROMPTS: SelfPromptAction[] = [
  {
    id: 'summary',
    title: 'Executive Summary',
    badge: 'Summary',
    description: 'Summarize matter background & parties',
    prompt: 'Provide a structured executive legal summary of this matter: 1. Parties and context, 2. Core commercial dispute, 3. Proposed resolution, 4. Immediate procedural next steps.'
  },
  {
    id: 'risks',
    title: 'Risk & Liability Check',
    badge: 'Risk',
    description: 'Analyze breach risks & liabilities',
    prompt: 'Perform a comprehensive legal risk and liability assessment on this document: 1. Financial exposure, 2. Breach and enforcement risks, 3. Regulatory or SRA compliance obligations.'
  },
  {
    id: 'obligations',
    title: 'Obligations & Deadlines',
    badge: 'Deadlines',
    description: 'Action items & timetable table',
    prompt: 'Extract all legal obligations, conditions precedent, undertakings, and procedural deadlines from this document into a clear Markdown table with responsible parties and due dates.'
  },
  {
    id: 'advice_memo',
    title: 'Draft Client Advice Memo',
    badge: 'Drafting',
    description: 'Privileged formal advice memo',
    prompt: 'Draft a formal, privileged Client Legal Advice Memorandum based on this document. Outline executive recommendations, legal strengths, tactical posture, and proposed next actions.'
  },
  {
    id: 'rebuttal',
    title: 'Rebuttal & Defences',
    badge: 'Strategy',
    description: 'Counter-arguments & defences',
    prompt: 'Analyze opposing party claims in this document and draft strategic rebuttal arguments, jurisdictional weaknesses, failure to mitigate defences, and procedural counter-points.'
  },
  {
    id: 'timeline',
    title: 'Chronological Timeline',
    badge: 'Timeline',
    description: 'Sequence of events & filings',
    prompt: 'Construct a precise chronological timeline of all relevant dates, communications, filings, and milestones mentioned in this document.'
  }
];

export const AICopilotDrawer: React.FC<AICopilotDrawerProps> = ({
  isOpen,
  onClose,
  onExecutePrompt,
  onAddToNotes,
  isLoading,
}) => {
  const [messages, setMessages] = useState<AIChatMessage[]>([]);
  const [customInput, setCustomInput] = useState<string>('');
  const [provider, setProvider] = useState<'demo' | 'openai' | 'anthropic' | 'gemini'>('demo');
  const [apiKey, setApiKey] = useState<string>('');
  const [model, setModel] = useState<string>('demo-fast');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSelfPrompt = async (item: SelfPromptAction) => {
    const userMsg: AIChatMessage = {
      id: `msg_${Date.now()}_u`,
      sender: 'user',
      text: item.prompt,
      promptTitle: item.title,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const answer = await onExecutePrompt(provider, apiKey, model, item.prompt);
      const aiMsg: AIChatMessage = {
        id: `msg_${Date.now()}_a`,
        sender: 'assistant',
        text: answer,
        promptTitle: item.title,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `msg_${Date.now()}_err`,
          sender: 'assistant',
          text: `Error: ${err.message}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    }
  };

  const handleCustomSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customInput.trim() || isLoading) return;

    const promptText = customInput.trim();
    setCustomInput('');

    const userMsg: AIChatMessage = {
      id: `msg_${Date.now()}_u`,
      sender: 'user',
      text: promptText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const answer = await onExecutePrompt(provider, apiKey, model, promptText);
      const aiMsg: AIChatMessage = {
        id: `msg_${Date.now()}_a`,
        sender: 'assistant',
        text: answer,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `msg_${Date.now()}_err`,
          sender: 'assistant',
          text: `Error: ${err.message}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <aside className="w-80 sm:w-96 bg-white border-l border-[#e9e9e7] h-screen fixed right-0 top-0 shadow-xl flex flex-col z-50 select-none text-[#37352f]">
      {/* Drawer Header */}
      <div className="p-3.5 border-b border-[#e9e9e7] flex items-center justify-between bg-[#f7f7f5]">
        <div className="flex items-center space-x-2">
          <div className="w-6 h-6 rounded-md bg-purple-600 text-white flex items-center justify-center shadow-2xs">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-[#37352f]">Notion AI Copilot</h3>
            <p className="text-[10px] text-[#787774]">Safe Reasoning on XXX/XYZ Text</p>
          </div>
        </div>

        <div className="flex items-center space-x-1">
          {messages.length > 0 && (
            <button
              onClick={() => setMessages([])}
              className="p-1 rounded hover:bg-[#efefed] text-[#787774] cursor-pointer"
              title="Clear conversation"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[#efefed] text-[#787774] hover:text-[#37352f] cursor-pointer"
            title="Close Drawer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 1-Click Self-Prompts (Quick Pills) */}
      <div className="p-3 border-b border-[#e9e9e7] bg-[#fdfdfc] space-y-2">
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#787774]">
          1-Click Self-Prompts
        </span>
        <div className="grid grid-cols-2 gap-1.5">
          {QUICK_SELF_PROMPTS.map((sp) => (
            <button
              key={sp.id}
              onClick={() => handleSelfPrompt(sp)}
              disabled={isLoading}
              className="text-left p-2 rounded-lg border border-[#e9e9e7] hover:border-purple-300 hover:bg-purple-50/40 text-[11px] font-medium text-[#37352f] transition-all cursor-pointer truncate disabled:opacity-50"
              title={sp.prompt}
            >
              <div className="truncate font-semibold">{sp.title}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Chat Messages Stream */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 font-sans text-xs">
        {messages.length === 0 ? (
          <div className="py-12 text-center text-[#787774] text-xs space-y-2">
            <Bot className="w-8 h-8 mx-auto text-[#b4b2ac]" />
            <p className="font-medium">Notion AI is ready.</p>
            <p className="text-[11px] text-[#787774] max-w-xs mx-auto">
              Click any self-prompt above or ask a question. The AI reasons on the safe redacted text.
            </p>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`p-3 rounded-xl border text-xs ${
                m.sender === 'user'
                  ? 'bg-[#f7f7f5] border-[#e9e9e7]'
                  : 'bg-white border-[#e9e9e7] shadow-2xs'
              }`}
            >
              <div className="flex items-center justify-between text-[10px] font-bold text-[#787774] mb-1.5 border-b border-[#e9e9e7]/60 pb-1">
                <span>{m.promptTitle || (m.sender === 'user' ? 'Prompt' : 'AI Analysis')}</span>
                {m.sender === 'assistant' && (
                  <div className="flex items-center space-x-1 font-normal">
                    <button
                      onClick={() => handleCopy(m.text, m.id)}
                      className="p-1 hover:bg-[#efefed] rounded cursor-pointer"
                      title="Copy"
                    >
                      {copiedId === m.id ? (
                        <Check className="w-3 h-3 text-emerald-600" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                    </button>
                    <button
                      onClick={() => downloadTextFile(m.text, `${m.promptTitle || 'analysis'}.md`)}
                      className="p-1 hover:bg-[#efefed] rounded cursor-pointer"
                      title="Download Markdown"
                    >
                      <Download className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => onAddToNotes(m.promptTitle || 'AI Insight', m.text, 'AI Insight')}
                      className="flex items-center gap-0.5 px-1.5 py-0.5 bg-purple-50 text-purple-800 rounded font-semibold cursor-pointer"
                      title="Save to Notes"
                    >
                      <PlusCircle className="w-2.5 h-2.5" />
                      <span>Note</span>
                    </button>
                  </div>
                )}
              </div>
              <div className="whitespace-pre-wrap leading-relaxed text-[#37352f]">
                {m.text}
              </div>
            </div>
          ))
        )}

        {isLoading && (
          <div className="p-3 rounded-xl bg-purple-50 border border-purple-200 text-purple-900 text-xs flex items-center space-x-2">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-600" />
            <span>AI is reasoning on protected text...</span>
          </div>
        )}
      </div>

      {/* Drawer Input Bar */}
      <form onSubmit={handleCustomSubmit} className="p-2.5 border-t border-[#e9e9e7] bg-white">
        <div className="flex items-center space-x-1.5">
          <input
            type="text"
            value={customInput}
            onChange={(e) => setCustomInput(e.target.value)}
            disabled={isLoading}
            placeholder="Ask AI Copilot about this case..."
            className="flex-1 text-xs px-3 py-2 rounded-lg border border-[#e9e9e7] focus:outline-none focus:ring-1 focus:ring-purple-500 bg-[#f7f7f5]"
          />
          <button
            type="submit"
            disabled={!customInput.trim() || isLoading}
            className="p-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-40 cursor-pointer"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </form>
    </aside>
  );
};
