'use client';

import React, { useState, useEffect } from 'react';
import {
  Bot,
  Sparkles,
  Send,
  Loader2,
  Copy,
  Check,
  Download,
  BookOpen,
  Scale,
  Calendar,
  FileCheck2,
  FileText,
  Swords,
  Clock,
  ShieldCheck,
  PlusCircle,
  Key,
  RotateCcw
} from 'lucide-react';
import { Block, DetectedEntity, SelfPromptAction, AIChatMessage } from '../lib/types';
import { compileProtectedDocument, downloadTextFile, restoreProtectedText } from '../lib/restore';

interface AILegalStudioProps {
  blocks: Block[];
  entities: DetectedEntity[];
  includeHidden: boolean;
  onExecutePrompt: (provider: string, apiKey: string, model: string, prompt: string) => Promise<{ summary: string; inbound_warnings?: string[] } | string>;
  onAddToNotes: (title: string, content: string, category?: any) => void;
  isLoading: boolean;
}

// Phase 1 Task Rule: Only 'summarise' is active; other tasks flagged off until Phase 2
// Phase 1: summarise only. Set NEXT_PUBLIC_ENABLE_PHASE2_TASKS=true at build time to show the other tasks.
const ENABLE_PHASE2_EXTENDED_TASKS = process.env.NEXT_PUBLIC_ENABLE_PHASE2_TASKS === 'true';

const ALL_SELF_PROMPTS: SelfPromptAction[] = [
  {
    id: 'summary',
    title: 'Executive Legal Summary',
    badge: 'Overview',
    description: 'Summarize core dispute, parties, and factual background.',
    prompt: 'Provide a structured executive legal summary of this matter: 1. Parties and context, 2. Core commercial dispute, 3. Proposed resolution, 4. Immediate procedural next steps.'
  },
  {
    id: 'risks',
    title: 'Risk & Liability Analysis',
    badge: 'Risk',
    description: 'Analyze legal risks, exposures, and regulatory issues.',
    prompt: 'Perform a comprehensive legal risk and liability assessment on this document: 1. Financial exposure, 2. Breach and enforcement risks, 3. Regulatory or SRA compliance obligations.'
  },
  {
    id: 'obligations',
    title: 'Obligations & Deadlines',
    badge: 'Deadlines',
    description: 'Extract all action items, conditions, and timetable.',
    prompt: 'Extract all legal obligations, conditions precedent, undertakings, and procedural deadlines from this document into a clear Markdown table with responsible parties and due dates.'
  },
  {
    id: 'advice_memo',
    title: 'Draft Client Advice Memo',
    badge: 'Drafting',
    description: 'Draft a formal advice memorandum for the client.',
    prompt: 'Draft a formal, privileged Client Legal Advice Memorandum based on this document. Outline executive recommendations, legal strengths, tactical posture, and proposed next actions.'
  },
  {
    id: 'rebuttal',
    title: 'Rebuttal & Defences',
    badge: 'Strategy',
    description: 'Synthesize tactical defences and opposing weaknesses.',
    prompt: 'Analyze opposing party claims in this document and draft strategic rebuttal arguments, jurisdictional weaknesses, failure to mitigate defences, and procedural counter-points.'
  },
  {
    id: 'timeline',
    title: 'Chronological Timeline',
    badge: 'Chronology',
    description: 'Construct chronological order of facts and events.',
    prompt: 'Construct a precise chronological timeline of all relevant dates, communications, filings, and milestones mentioned in this document.'
  }
];

const SELF_PROMPTS: SelfPromptAction[] = ENABLE_PHASE2_EXTENDED_TASKS
  ? ALL_SELF_PROMPTS
  : ALL_SELF_PROMPTS.filter((p) => p.id === 'summary');

export const AILegalStudio: React.FC<AILegalStudioProps> = ({
  blocks,
  entities,
  includeHidden,
  onExecutePrompt,
  onAddToNotes,
  isLoading,
}) => {
  const [provider, setProvider] = useState<'demo' | 'openai' | 'anthropic' | 'gemini'>('demo');
  const [apiKey, setApiKey] = useState<string>('');
  const [model, setModel] = useState<string>('demo-legal-fast');
  const [customPrompt, setCustomPrompt] = useState<string>('');
  const [chatHistory, setChatHistory] = useState<AIChatMessage[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showConfig, setShowConfig] = useState<boolean>(false);
  const [outputViewMode, setOutputViewMode] = useState<Record<string, 'restored' | 'raw' | 'side_by_side'>>({});

  const activeEntities = entities.filter((e) => e.is_active);
  const compiledText = compileProtectedDocument(blocks, entities, includeHidden);

  // Self-prompt trigger
  const handleTriggerSelfPrompt = async (item: SelfPromptAction) => {
    const userMsg: AIChatMessage = {
      id: `msg_${Date.now()}_u`,
      sender: 'user',
      text: item.prompt,
      promptTitle: item.title,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setChatHistory((prev) => [...prev, userMsg]);

    try {
      const res = await onExecutePrompt(provider, apiKey, model, item.prompt);
      const summaryText = typeof res === 'string' ? res : res.summary;
      const inboundWarnings = typeof res === 'object' ? (res.inbound_warnings || []) : [];
      const aiMsg: AIChatMessage = {
        id: `msg_${Date.now()}_a`,
        sender: 'assistant',
        text: summaryText,
        inbound_warnings: inboundWarnings,
        promptTitle: item.title,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setChatHistory((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const errorMsg: AIChatMessage = {
        id: `msg_${Date.now()}_err`,
        sender: 'assistant',
        text: `Error generating response: ${err.message}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setChatHistory((prev) => [...prev, errorMsg]);
    }
  };

  // Custom prompt submit
  const handleCustomSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customPrompt.trim() || isLoading) return;

    const promptText = customPrompt.trim();
    setCustomPrompt('');

    const userMsg: AIChatMessage = {
      id: `msg_${Date.now()}_u`,
      sender: 'user',
      text: promptText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setChatHistory((prev) => [...prev, userMsg]);

    try {
      const res = await onExecutePrompt(provider, apiKey, model, promptText);
      const summaryText = typeof res === 'string' ? res : res.summary;
      const inboundWarnings = typeof res === 'object' ? (res.inbound_warnings || []) : [];
      const aiMsg: AIChatMessage = {
        id: `msg_${Date.now()}_a`,
        sender: 'assistant',
        text: summaryText,
        inbound_warnings: inboundWarnings,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setChatHistory((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const errorMsg: AIChatMessage = {
        id: `msg_${Date.now()}_err`,
        sender: 'assistant',
        text: `Error: ${err.message}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setChatHistory((prev) => [...prev, errorMsg]);
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDownload = (text: string, title?: string) => {
    const filename = `${title ? title.toLowerCase().replace(/\s+/g, '-') : 'ai-analysis'}-${Date.now()}.md`;
    downloadTextFile(text, filename);
  };

  return (
    <div className="space-y-6">
      {/* Header & Protection Banner */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shadow-2xs">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-bold text-sm text-slate-900">AI Legal Intelligence Studio</h3>
              <span className="text-[10px] bg-emerald-50 text-emerald-800 font-semibold px-2 py-0.5 rounded-full border border-emerald-200 flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-emerald-600" />
                Protected (Typed Placeholders)
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Only the protected text is sent to the AI provider. Real values are restored in your browser.
            </p>
          </div>
        </div>

        {/* Model & Config Button */}
        <div className="flex items-center space-x-2.5">
          <button
            type="button"
            onClick={() => setShowConfig(!showConfig)}
            className="flex items-center space-x-1.5 text-xs text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
          >
            <Key className="w-3.5 h-3.5 text-slate-500" />
            <span className="font-medium">
              Provider: <strong className="capitalize">{provider}</strong>
            </span>
          </button>

          {chatHistory.length > 0 && (
            <button
              type="button"
              onClick={() => setChatHistory([])}
              className="flex items-center space-x-1 text-xs text-slate-500 hover:text-slate-800 px-2.5 py-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
              title="Clear Chat History"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Clear</span>
            </button>
          )}
        </div>
      </div>

      {/* Collapsible Provider & BYOK Settings */}
      {showConfig && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              AI Provider & BYOK Settings
            </h4>
            <span className="text-[11px] text-slate-400">API keys held in temporary browser memory only</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            {(['demo', 'openai', 'anthropic', 'gemini'] as const).map((p) => (
              <label
                key={p}
                className={`border rounded-xl p-3 cursor-pointer transition-all flex flex-col justify-between ${
                  provider === p
                    ? 'border-indigo-600 bg-indigo-50/40 text-indigo-950 font-semibold'
                    : 'border-slate-200 hover:border-slate-300 text-slate-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase">{p === 'demo' ? '⚡ Instant Demo' : p}</span>
                  <input
                    type="radio"
                    name="provider_select"
                    checked={provider === p}
                    onChange={() => {
                      setProvider(p);
                      if (p === 'demo') setModel('demo-fast');
                      if (p === 'openai') setModel('gpt-4o-mini');
                      if (p === 'anthropic') setModel('claude-3-5-sonnet-20241022');
                      if (p === 'gemini') setModel('gemini-1.5-flash');
                    }}
                    className="sr-only"
                  />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  {p === 'demo' ? 'Works instantly without API keys' : `Bring your own ${p} key`}
                </p>
              </label>
            ))}
          </div>

          {provider !== 'demo' && (
            <div className="pt-2">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {provider.toUpperCase()} API Key:
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={`sk-... for ${provider}`}
                className="w-full text-xs font-mono px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              />
            </div>
          )}
        </div>
      )}

      {/* ⚡ Self-Prompt Quick Actions Grid (Reduces prompt time!) */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5 shadow-2xs space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-amber-500" />
            <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              1-Click Self-Prompts (Instant Legal Workflows)
            </h4>
          </div>
          <span className="text-[11px] text-slate-500">Click any card to run immediately</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {SELF_PROMPTS.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={isLoading}
              onClick={() => handleTriggerSelfPrompt(item)}
              className="text-left p-3.5 rounded-xl border border-slate-200 hover:border-indigo-500 hover:bg-indigo-50/30 transition-all group flex flex-col justify-between cursor-pointer disabled:opacity-50"
            >
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800 group-hover:text-indigo-600 transition-colors">
                    {item.title}
                  </span>
                  <span className="text-[10px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full group-hover:bg-indigo-100 group-hover:text-indigo-800 transition-colors">
                    {item.badge}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 line-clamp-2">
                  {item.description}
                </p>
              </div>

              <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-indigo-600 font-medium">
                <span>Run with 1-click</span>
                <span className="group-hover:translate-x-0.5 transition-transform">➔</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Conversation & Results Stream */}
      {chatHistory.length > 0 && (
        <div className="space-y-4">
          {chatHistory.map((msg) => (
            <div
              key={msg.id}
              className={`rounded-xl border p-5 shadow-2xs transition-all ${
                msg.sender === 'user'
                  ? 'bg-slate-50/80 border-slate-200'
                  : 'bg-white border-slate-200'
              }`}
            >
              <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
                <div className="flex items-center space-x-2">
                  <span
                    className={`w-6 h-6 rounded-lg flex items-center justify-center text-xs font-bold ${
                      msg.sender === 'user'
                        ? 'bg-slate-200 text-slate-700'
                        : 'bg-indigo-600 text-white'
                    }`}
                  >
                    {msg.sender === 'user' ? 'Q' : 'AI'}
                  </span>
                  <span className="text-xs font-bold text-slate-800">
                    {msg.promptTitle || (msg.sender === 'user' ? 'Prompt' : 'Legal Analysis')}
                  </span>
                </div>

                <div className="flex items-center space-x-2 text-xs text-slate-400">
                  <span>{msg.timestamp}</span>
                  {msg.sender === 'assistant' && (
                    <>
                      <button
                        onClick={() => handleCopy(msg.text, msg.id)}
                        className="p-1 text-slate-500 hover:text-slate-800 rounded hover:bg-slate-100 cursor-pointer"
                        title="Copy text"
                      >
                        {copiedId === msg.id ? (
                          <Check className="w-3.5 h-3.5 text-emerald-600" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>

                      <button
                        onClick={() => handleDownload(msg.text, msg.promptTitle)}
                        className="p-1 text-slate-500 hover:text-indigo-600 rounded hover:bg-slate-100 cursor-pointer"
                        title="Download as Markdown"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>

                      <button
                        onClick={() =>
                          onAddToNotes(
                            msg.promptTitle || 'AI Analysis',
                            msg.text,
                            'AI Insight'
                          )
                        }
                        className="flex items-center space-x-1 text-[11px] text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 px-2 py-0.5 rounded cursor-pointer"
                        title="Save response directly to your Notes workspace"
                      >
                        <PlusCircle className="w-3 h-3" />
                        <span>Add to Notes</span>
                      </button>
                    </>
                  )}
                </div>
              </div>

              {msg.sender === 'user' ? (
                <div className="prose prose-sm max-w-none text-slate-800 text-xs sm:text-sm font-sans whitespace-pre-wrap leading-relaxed">
                  {msg.text}
                </div>
              ) : (
                (() => {
                  const restoreRes = restoreProtectedText(msg.text, entities);
                  const mode = outputViewMode[msg.id] || 'restored';

                  return (
                    <div className="space-y-3">
                      {/* Inbound Warnings Notice (shown beside/above text, not injected inside it) */}
                      {msg.inbound_warnings && msg.inbound_warnings.length > 0 && (
                        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 space-y-1">
                          <div className="font-semibold flex items-center gap-1.5 text-amber-800">
                            <ShieldCheck className="w-4 h-4 text-amber-600 flex-shrink-0" />
                            <span>AI Governance Notice (Inbound Scan):</span>
                          </div>
                          <ul className="list-disc list-inside space-y-0.5 text-amber-800 text-[11px]">
                            {msg.inbound_warnings.map((warn, wIdx) => (
                              <li key={wIdx}>{warn}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* View Switcher & Restoration Status Banner (Deliverable 9) */}
                      <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                        <div className="flex items-center space-x-1">
                          <span className="text-[11px] font-semibold text-slate-500 mr-1">View:</span>
                          <button
                            type="button"
                            onClick={() => setOutputViewMode(prev => ({ ...prev, [msg.id]: 'restored' }))}
                            className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors cursor-pointer ${
                              mode === 'restored'
                                ? 'bg-indigo-600 text-white shadow-2xs'
                                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                            }`}
                          >
                            Restored View
                          </button>
                          <button
                            type="button"
                            onClick={() => setOutputViewMode(prev => ({ ...prev, [msg.id]: 'raw' }))}
                            className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors cursor-pointer ${
                              mode === 'raw'
                                ? 'bg-indigo-600 text-white shadow-2xs'
                                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                            }`}
                          >
                            Protected AI Output
                          </button>
                          <button
                            type="button"
                            onClick={() => setOutputViewMode(prev => ({ ...prev, [msg.id]: 'side_by_side' }))}
                            className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors cursor-pointer ${
                              mode === 'side_by_side'
                                ? 'bg-indigo-600 text-white shadow-2xs'
                                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                            }`}
                          >
                            Side-by-Side
                          </button>
                        </div>

                        <div className="flex items-center space-x-2 text-[11px]">
                          <span className="font-medium text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                            ✓ Restored {restoreRes.restoredCount} of {restoreRes.totalPlaceholders} placeholders
                          </span>
                          {restoreRes.unrestoredTokens.length > 0 && (
                            <span className="font-medium text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                              ⚠️ {restoreRes.unrestoredTokens.length} unrestored: {restoreRes.unrestoredTokens.join(', ')}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Display Mode Content */}
                      {mode === 'restored' && (
                        <div className="prose prose-sm max-w-none text-slate-800 text-xs sm:text-sm font-sans whitespace-pre-wrap leading-relaxed p-1">
                          {restoreRes.restoredText}
                        </div>
                      )}

                      {mode === 'raw' && (
                        <div className="prose prose-sm max-w-none text-slate-800 text-xs sm:text-sm font-mono whitespace-pre-wrap leading-relaxed bg-slate-50/70 p-3 rounded-lg border border-slate-200">
                          {msg.text}
                        </div>
                      )}

                      {mode === 'side_by_side' && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                          <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 space-y-2">
                            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200 pb-1">
                              Protected AI Output (Tokens Sent/Received)
                            </div>
                            <div className="font-mono text-xs text-slate-800 whitespace-pre-wrap leading-relaxed">
                              {msg.text}
                            </div>
                          </div>
                          <div className="rounded-lg border border-indigo-200 bg-indigo-50/20 p-3 space-y-2">
                            <div className="text-[10px] font-bold text-indigo-700 uppercase tracking-wider border-b border-indigo-100 pb-1">
                              Restored View (Client Identities Reconstituted)
                            </div>
                            <div className="font-sans text-xs sm:text-sm text-slate-800 whitespace-pre-wrap leading-relaxed">
                              {restoreRes.restoredText}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()
              )}
            </div>
          ))}
        </div>
      )}

      {/* Loading Indicator */}
      {isLoading && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 flex items-center justify-center space-x-3 text-indigo-900 text-xs">
          <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
          <span className="font-medium">
            Generating legal analysis safely using {provider.toUpperCase()}...
          </span>
        </div>
      )}

      {/* Interactive Custom Prompt Input */}
      <form onSubmit={handleCustomSubmit} className="bg-white border border-slate-200 rounded-xl p-3 shadow-2xs space-y-2">
        <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
          Ask a specific question or custom prompt:
        </label>
        <div className="flex items-center space-x-2">
          <input
            type="text"
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            disabled={isLoading}
            placeholder="e.g. What are the tax or SRA compliance implications of the proposed £450k settlement?"
            className="flex-1 text-xs px-3.5 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 bg-slate-50/50"
          />
          <div className="hidden sm:flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-[11px] font-medium flex-shrink-0" title="Outbound gate checks prompt and document for unmasked sensitive items">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span>Outbound Gate Active</span>
          </div>
          <button
            type="submit"
            disabled={!customPrompt.trim() || isLoading}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white px-4 py-2.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-colors cursor-pointer flex-shrink-0"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Send</span>
          </button>
        </div>
      </form>
    </div>
  );
};
