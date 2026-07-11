import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Play, RotateCcw, AlertTriangle, TerminalSquare, LogOut, Clock } from 'lucide-react';
import { API_URL, WS_BASE } from './api';
import Graph from './components/Graph';
import DebateFeed from './components/DebateFeed';
import RevealModal from './components/RevealModal';
import AuthPage from './components/AuthPage';

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [scenarios, setScenarios] = useState([]);
  const [activeScenario, setActiveScenario] = useState(null);
  const [debateMessages, setDebateMessages] = useState([]);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [judgeResult, setJudgeResult] = useState(null);
  const [groundTruth, setGroundTruth] = useState(null);
  const [isRevealed, setIsRevealed] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runHistory, setRunHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  // ── Auth ──────────────────────────────────────────────────────────────────
  const handleLogin = (newToken) => setToken(newToken);

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken(null);
  };

  // ── Load scenarios ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!token) return;
    axios.get(`${API_URL}/scenarios`)
      .then(res => setScenarios(res.data))
      .catch(err => {
        if (err.response?.status === 401) handleLogout();
        else console.error('Failed to fetch scenarios:', err);
      });
  }, [token]);

  // ── Load run history ──────────────────────────────────────────────────────
  const fetchHistory = () => {
    if (!token) return;
    axios.get(`${API_URL}/runs`, { headers: authHeaders })
      .then(res => setRunHistory(res.data))
      .catch(err => console.error('Failed to fetch run history:', err));
  };

  useEffect(() => { fetchHistory(); }, [token]);

  // ── Start a scenario ──────────────────────────────────────────────────────
  const handleStartScenario = async (scenarioId) => {
    setDebateMessages([]);
    setGraphData({ nodes: [], links: [] });
    setJudgeResult(null);
    setGroundTruth(null);
    setIsRevealed(false);
    setIsRunning(true);
    setActiveScenario(scenarioId);

    try {
      await axios.post(
        `${API_URL}/scenario/${scenarioId}/start?speed=4.0&mock=true`,
        {},
        { headers: authHeaders }
      );
      fetchHistory(); // refresh history after starting
    } catch (err) {
      if (err.response?.status === 401) handleLogout();
      else console.error('Failed to start scenario', err);
      setIsRunning(false);
    }
  };

  // ── Reveal ground truth ───────────────────────────────────────────────────
  const handleReveal = async () => {
    if (!activeScenario) return;
    try {
      const res = await axios.get(`${API_URL}/scenario/${activeScenario}/ground-truth`);
      setGroundTruth(res.data);
      setIsRevealed(true);
    } catch (err) {
      console.error('Failed to fetch ground truth', err);
    }
  };

  // ── Render auth gate ──────────────────────────────────────────────────────
  if (!token) {
    return <AuthPage onLogin={handleLogin} />;
  }

  // ── Main dashboard ────────────────────────────────────────────────────────
  return (
    <div className="flex h-full w-full bg-background text-slate-200 overflow-hidden font-sans">

      {/* LEFT SIDEBAR: Control Panel */}
      <aside className="w-80 bg-surface border-r border-slate-800 flex flex-col z-10 shadow-2xl">
        <div className="p-6 border-b border-slate-800">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center text-primary border border-primary/30">
              <TerminalSquare size={20} />
            </div>
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
              Incident Mesh
            </h1>
          </div>
          <p className="text-xs text-slate-400 uppercase tracking-widest font-semibold mt-4">Chaos Scenarios</p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {scenarios.map(s => (
            <div
              key={s.id}
              className={`p-4 rounded-xl border transition-all cursor-pointer ${
                activeScenario === s.id && isRunning
                  ? 'bg-primary/10 border-primary/50 ring-1 ring-primary/20'
                  : 'bg-slate-900 border-slate-800 hover:border-slate-700'
              }`}
              onClick={() => !isRunning && handleStartScenario(s.id)}
            >
              <h3 className="font-semibold text-slate-200 mb-1">{s.name}</h3>
              <p className="text-sm text-slate-500 mb-4 line-clamp-2">{s.description}</p>

              <button
                onClick={(e) => { e.stopPropagation(); handleStartScenario(s.id); }}
                disabled={isRunning}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-primary hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white text-sm font-medium"
              >
                {isRunning && activeScenario === s.id ? (
                  <><RotateCcw size={16} className="animate-spin" /> Running...</>
                ) : (
                  <><Play size={16} fill="currentColor" /> Start Scenario</>
                )}
              </button>
            </div>
          ))}
        </div>

        {/* Run History toggle */}
        <div className="border-t border-slate-800">
          <button
            onClick={() => setShowHistory(v => !v)}
            className="w-full flex items-center gap-2 px-4 py-3 text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-colors"
          >
            <Clock size={14} />
            Run History ({runHistory.length})
          </button>
          {showHistory && (
            <div className="max-h-48 overflow-y-auto px-4 pb-4 space-y-2">
              {runHistory.length === 0 && <p className="text-xs text-slate-600 italic">No runs yet</p>}
              {runHistory.map(r => (
                <div key={r.id} className="flex items-center justify-between text-xs bg-slate-900 rounded-lg px-3 py-2 border border-slate-800">
                  <span className="text-slate-400 truncate">{r.scenario_id}</span>
                  <span className={`ml-2 shrink-0 px-1.5 py-0.5 rounded font-medium ${
                    r.status === 'completed' ? 'text-emerald-400 bg-emerald-500/10' :
                    r.status === 'failed' ? 'text-red-400 bg-red-500/10' :
                    r.status === 'running' ? 'text-blue-400 bg-blue-500/10' :
                    'text-slate-400 bg-slate-800'
                  }`}>{r.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Logout */}
        <div className="border-t border-slate-800 p-4">
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-colors text-sm"
          >
            <LogOut size={14} /> Sign Out
          </button>
        </div>
      </aside>

      {/* MIDDLE: Causal Graph */}
      <main className="flex-1 relative flex flex-col">
        {/* Header Overlay */}
        <div className="absolute top-0 left-0 right-0 p-6 flex justify-between items-start z-10 pointer-events-none">
          <div className="bg-slate-900/80 backdrop-blur-md px-4 py-2 rounded-full border border-slate-800 text-sm font-medium flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-slate-600'}`} />
            {isRunning ? 'System Mesh Active' : 'System Idle'}
          </div>

          {judgeResult && !isRevealed && (
            <button
              onClick={handleReveal}
              className="pointer-events-auto bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white px-6 py-3 rounded-full shadow-lg shadow-emerald-500/20 font-semibold flex items-center gap-2 transform hover:scale-105 transition-all"
            >
              <AlertTriangle size={18} />
              Reveal Ground Truth
            </button>
          )}
        </div>

        {/* The Graph */}
        <div className="flex-1 w-full bg-[#0B0F19]">
          <Graph
            graphData={graphData}
            setGraphData={setGraphData}
            wsBase={WS_BASE}
            isRunning={isRunning}
          />
        </div>
      </main>

      {/* RIGHT SIDEBAR: Debate Feed */}
      <aside className="w-[400px] bg-slate-900 border-l border-slate-800 flex flex-col z-10 shadow-2xl relative">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-surface/50 backdrop-blur-sm sticky top-0 z-20">
          <h2 className="font-semibold flex items-center gap-2 text-slate-200">
            <span className="w-2 h-2 rounded-full bg-blue-500" />
            Agent Debate Log
          </h2>
          <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded">Live</span>
        </div>

        <DebateFeed
          wsBase={WS_BASE}
          messages={debateMessages}
          setMessages={setDebateMessages}
          setJudgeResult={setJudgeResult}
          setIsRunning={setIsRunning}
        />
      </aside>

      {/* Reveal Modal */}
      {isRevealed && judgeResult && groundTruth && (
        <RevealModal
          judgeResult={judgeResult}
          groundTruth={groundTruth}
          onClose={() => setIsRevealed(false)}
        />
      )}
    </div>
  );
}

export default App;
