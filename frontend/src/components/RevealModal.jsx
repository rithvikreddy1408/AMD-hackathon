import React from 'react';
import { X, CheckCircle, AlertOctagon, ArrowRight } from 'lucide-react';

export default function RevealModal({ judgeResult, groundTruth, onClose }) {
  // Determine if the judge got it right
  const isMatch = judgeResult?.root_cause?.toLowerCase().includes(groundTruth?.root_cause_service?.toLowerCase());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-surface border border-slate-800 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="p-6 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-cyan-400">
            Ground Truth Reveal
          </h2>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors">
            <X size={24} />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            
            {/* Judge Conclusion */}
            <div className="bg-slate-900 rounded-xl p-6 border border-slate-800 relative">
              <div className="absolute -top-3 left-6 px-3 py-1 bg-blue-500/20 text-blue-400 border border-blue-500/30 text-xs font-bold tracking-wider uppercase rounded-full">
                Judge Agent Conclusion
              </div>
              <div className="mt-4 space-y-4">
                <div>
                  <div className="text-sm text-slate-400 mb-1">Diagnosed Root Cause</div>
                  <div className="text-lg font-medium text-white">{judgeResult?.root_cause || "Unknown"}</div>
                </div>
                <div>
                  <div className="text-sm text-slate-400 mb-1">Confidence</div>
                  <div className="text-3xl font-bold text-blue-400">{judgeResult?.confidence || "N/A"}</div>
                </div>
                <div>
                  <div className="text-sm text-slate-400 mb-1">Recommended Fix</div>
                  <div className="text-sm text-slate-300 p-3 bg-slate-950 rounded-lg border border-slate-800">
                    {judgeResult?.fix || judgeResult?.recommendation || "N/A"}
                  </div>
                </div>
              </div>
            </div>

            {/* Scripted Ground Truth */}
            <div className="bg-slate-900 rounded-xl p-6 border border-slate-800 relative">
              <div className="absolute -top-3 left-6 px-3 py-1 bg-amber-500/20 text-amber-400 border border-amber-500/30 text-xs font-bold tracking-wider uppercase rounded-full">
                Scripted Ground Truth
              </div>
              <div className="mt-4 space-y-4">
                <div>
                  <div className="text-sm text-slate-400 mb-1">Actual Root Cause Service</div>
                  <div className="text-lg font-medium text-white">{groundTruth?.root_cause_service || groundTruth?.root_cause || "Unknown"}</div>
                </div>
                <div>
                  <div className="text-sm text-slate-400 mb-1">Incident Trigger</div>
                  <div className="text-sm text-slate-300 p-3 bg-slate-950 rounded-lg border border-slate-800">
                    {groundTruth?.description || groundTruth?.trigger || "N/A"}
                  </div>
                </div>
              </div>
            </div>

          </div>

          {/* Result Banner */}
          <div className={`mt-8 p-6 rounded-xl border flex items-center justify-center gap-4 shadow-lg ${
            isMatch 
              ? 'bg-emerald-900/30 border-emerald-500/50 shadow-emerald-900/20' 
              : 'bg-red-900/30 border-red-500/50 shadow-red-900/20'
          }`}>
            {isMatch ? (
              <>
                <CheckCircle className="text-emerald-400 w-12 h-12" />
                <div>
                  <h3 className="text-2xl font-bold text-emerald-400">Match Confirmed</h3>
                  <p className="text-emerald-500/80 font-medium">The Incident Mesh successfully identified the root cause.</p>
                </div>
              </>
            ) : (
              <>
                <AlertOctagon className="text-red-400 w-12 h-12" />
                <div>
                  <h3 className="text-2xl font-bold text-red-400">Mismatch</h3>
                  <p className="text-red-500/80 font-medium">The system failed to correctly identify the scripted ground truth.</p>
                </div>
              </>
            )}
          </div>

        </div>

      </div>
    </div>
  );
}
