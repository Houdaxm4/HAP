"use client";

import { useState } from "react";
import type { AnalysisDetail } from "@/lib/types";

export default function AnalysisChatTab({ analysis }: { analysis: AnalysisDetail }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState(analysis.chatHistory);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed) return;

    const now = new Date().toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    });

    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", content: trimmed, timestamp: now },
      {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: `Analyzing your question in context of the ${analysis.ticker} ${analysis.type} run...`,
        timestamp: now,
      },
    ]);
    setInput("");
  };

  return (
    <div className="flex h-[400px] flex-col rounded border border-hap-border bg-hap-panel">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`max-w-[85%] rounded-lg px-4 py-3 ${
              msg.role === "assistant"
                ? "rounded-tl-none border border-hap-border bg-hap-panel-elevated"
                : "ml-auto rounded-tr-none border border-hap-orange/30 bg-hap-orange/10"
            }`}
          >
            <p className="text-sm leading-relaxed">{msg.content}</p>
            <p className="mt-1 text-[10px] text-hap-muted">{msg.timestamp}</p>
          </div>
        ))}
      </div>
      <div className="border-t border-hap-border p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder={`Ask about ${analysis.ticker}...`}
            className="flex-1 rounded border border-hap-border bg-background px-3 py-2 text-sm focus:border-hap-orange/50 focus:outline-none focus:ring-1 focus:ring-hap-orange/30"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="rounded bg-hap-orange px-4 py-2 text-sm font-semibold text-black hover:bg-hap-orange-dim disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
