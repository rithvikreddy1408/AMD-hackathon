import React, { useEffect, useRef, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

export default function Graph({ graphData, setGraphData, wsBase, isRunning }) {
  const fgRef = useRef();

  useEffect(() => {
    if (!isRunning) return;

    let ws = null;
    let reconnectTimeout = null;

    const connect = () => {
      ws = new WebSocket(`${wsBase}/ws/graph`);
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'edge') {
            setGraphData(prev => {
              const nodes = [...prev.nodes];
              const links = [...prev.links];
              
              // Ensure source exists
              if (!nodes.find(n => n.id === data.source)) {
                nodes.push({ id: data.source, label: data.source, val: 1.5 });
              }
              // Ensure target exists
              if (!nodes.find(n => n.id === data.target)) {
                nodes.push({ id: data.target, label: data.target, val: 1.5 });
              }
              
              // Add or update link
              const existingLink = links.find(l => l.source === data.source && l.target === data.target);
              if (!existingLink) {
                links.push({
                  source: data.source,
                  target: data.target,
                  weight: data.weight,
                  timestamp: Date.now()
                });
              } else {
                existingLink.weight = data.weight;
                existingLink.timestamp = Date.now();
              }
              
              return { nodes, links };
            });
          }
        } catch (e) {
          console.error("Graph WS Error:", e);
        }
      };

      ws.onclose = () => {
        if (isRunning) {
          reconnectTimeout = setTimeout(connect, 1000);
        }
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [wsBase, isRunning, setGraphData]);

  // Center graph when data changes
  useEffect(() => {
    if (fgRef.current && graphData.nodes.length > 0) {
      fgRef.current.d3Force('charge').strength(-400);
      fgRef.current.d3Force('link').distance(100);
    }
  }, [graphData]);

  return (
    <div className="w-full h-full relative">
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeLabel="label"
        nodeColor={node => '#3B82F6'} // Tailwind primary
        nodeRelSize={6}
        linkColor={() => 'rgba(148, 163, 184, 0.4)'} // Slate 400 with opacity
        linkWidth={link => Math.max(1, (link.weight || 0) * 5)}
        linkDirectionalParticles={2}
        linkDirectionalParticleSpeed={d => (d.weight || 0) * 0.01}
        backgroundColor="#0B0F19"
        onNodeDragEnd={node => {
          node.fx = node.x;
          node.fy = node.y;
        }}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = node.id;
          const fontSize = 12/globalScale;
          ctx.font = `${fontSize}px Inter, sans-serif`;
          ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          
          // Draw node circle
          ctx.beginPath();
          ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI, false);
          ctx.fillStyle = '#3B82F6';
          ctx.fill();
          
          // Draw text
          ctx.fillStyle = '#F8FAFC';
          ctx.fillText(label, node.x, node.y + 14);
        }}
      />
      {graphData.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-500 font-medium">
          Start a scenario to begin causality embedding
        </div>
      )}
    </div>
  );
}
