import React, { useEffect, useRef } from 'react';
import { Bot, Gavel } from 'lucide-react';

export default function DebateFeed({ wsBase, messages, setMessages, setJudgeResult, setIsRunning }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    let ws = null;
    let reconnectTimeout = null;

    const connect = () => {
      ws = new WebSocket(`${wsBase}/ws/debate`);
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'agent_message' || data.type === 'hypothesis' || data.type === 'attack') {
            setMessages(prev => [...prev, data]);
          } else if (data.type === 'judge_verdict' || data.type === 'judge_conclusion') {
            setMessages(prev => [...prev, { ...data, sender: 'Judge' }]);
            setJudgeResult(data);
            setIsRunning(false); // Stop the simulation
          }
        } catch (e) {
          console.error("Debate WS Error:", e);
        }
      };

      ws.onclose = () => {
        reconnectTimeout = setTimeout(connect, 1000);
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [wsBase, setMessages, setJudgeResult, setIsRunning]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar bg-slate-900/50">
      {messages.length === 0 ? (
        <div className="h-full flex items-center justify-center text-slate-600 text-sm italic">
          Waiting for agents to begin debate...
        </div>
      ) : (
        messages.map((msg, i) => {
          const isJudge = msg.sender === 'Judge' || msg.type?.includes('judge');
          
          return (
            <div 
              key={i} 
              className={`p-4 rounded-xl shadow-md border ${
                isJudge 
                  ? 'bg-emerald-900/20 border-emerald-500/30 ring-1 ring-emerald-500/10' 
                  : 'bg-slate-800/80 border-slate-700/50'
              } animate-fade-in-up`}
            >
              <div className="flex items-center gap-2 mb-2">
                <div className={`p-1.5 rounded-lg ${isJudge ? 'bg-emerald-500/20 text-emerald-400' : 'bg-primary/20 text-primary'}`}>
                  {isJudge ? <Gavel size={14} /> : <Bot size={14} />}
                </div>
                <span className={`text-sm font-bold ${isJudge ? 'text-emerald-400' : 'text-slate-300'}`}>
                  {msg.sender || msg.agent_id || 'System'}
                </span>
                {msg.type === 'attack' && <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded ml-auto">Attack</span>}
                {msg.type === 'hypothesis' && <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded ml-auto">Hypothesis</span>}
              </div>
              
              <div className="text-slate-300 text-sm leading-relaxed prose prose-invert max-w-none">
                {msg.content || msg.message || msg.verdict}
              </div>

              {isJudge && msg.confidence && (
                <div className="mt-3 pt-3 border-t border-emerald-500/20 flex items-center justify-between">
                  <span className="text-xs text-emerald-500/70 uppercase tracking-wider font-semibold">Confidence</span>
                  <span className="text-sm text-emerald-400 font-bold">{msg.confidence}</span>
                </div>
              )}
            </div>
          );
        })
      )}
      <div ref={bottomRef} />
    </div>
  );
}
